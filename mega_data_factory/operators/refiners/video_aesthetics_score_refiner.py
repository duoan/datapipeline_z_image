"""
Video Aesthetic Quality Refiner

Predicts aesthetic quality scores for videos using CLIP+MLP model from:
- https://github.com/christophschuhmann/improved-aesthetic-predictor
- https://huggingface.co/ttj/sac-logos-ava1-l14-linearMSE

The model outputs a score (typically 1-10) predicting how visually appealing
a video is, based on training from professional annotators (AVA dataset + LAION logos).

Following the OpenVid-1M approach, this refiner samples multiple frames uniformly
across the video and computes the average aesthetic score for better representation.

Requirements:
- Pre-computed CLIP ViT-L-14 embeddings (768-dim) OR direct video processing
- Use VideoClipEmbeddingRefiner with model_name="ViT-L-14" first for embedding mode

Usage:
    # Option 1: Use pre-computed embeddings (faster if embeddings already exist)
    clip_refiner = VideoClipEmbeddingRefiner(model_name="ViT-L-14")
    aesthetic_refiner = VideoAestheticScoreRefiner(
        embedding_field="video_clip_emb_vit_l_14",
    )

    # Option 2: Direct video processing with multi-frame sampling (OpenVid-1M style)
    aesthetic_refiner = VideoAestheticScoreRefiner(
        use_precomputed_embeddings=False,
        num_frames=8,  # Sample 8 frames uniformly
        score_aggregation="mean",  # Average the scores
    )

Output fields:
- video_aesthetic_score: Aesthetic quality score (higher = more visually appealing, typically 1-10)
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
import open_clip
import pyarrow as pa
import torch
import torch.nn as nn
from huggingface_hub import hf_hub_download
from PIL import Image

from mega_data_factory.framework import Refiner
from mega_data_factory.operators.video_operator import VideoOperatorMixin
from mega_data_factory.utils.video_utils import get_video_frames

logger = logging.getLogger(__name__)

# Field name constant
FIELD_VIDEO_AESTHETIC_SCORE = "video_aesthetic_score"

# Required embedding dimension for the aesthetic predictor (ViT-L/14)
REQUIRED_EMBEDDING_DIM = 768


class AestheticMLP(nn.Module):
    """MLP model for aesthetic score prediction.

    Architecture from: https://github.com/christophschuhmann/improved-aesthetic-predictor
    Input: CLIP ViT-L/14 embeddings (768 dimensions)
    Output: Aesthetic score (typically 1-10)
    """

    def __init__(self, input_size: int = 768):
        super().__init__()
        self.input_size = input_size
        self.layers = nn.Sequential(
            nn.Linear(self.input_size, 1024),
            nn.Dropout(0.2),
            nn.Linear(1024, 128),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.Dropout(0.1),
            nn.Linear(64, 16),
            nn.Linear(16, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.layers(x)


class VideoAestheticScoreRefiner(VideoOperatorMixin, Refiner):
    """Refiner for predicting aesthetic quality scores for videos using CLIP+MLP.

    Uses the improved-aesthetic-predictor model trained on AVA dataset + LAION logos.
    The model predicts how visually appealing a video is on a scale of ~1-10.

    Following the OpenVid-1M approach, this refiner samples multiple frames uniformly
    across the video and computes the average aesthetic score for better representation.

    Can operate in two modes:
    1. Embedding mode: Uses pre-computed CLIP ViT-L-14 embeddings (768-dim)
    2. Direct mode: Extracts multiple frames from videos and computes embeddings internally

    Output fields:
    - video_aesthetic_score: Aesthetic quality score (higher = more visually appealing)
    """

    def __init__(
        self,
        embedding_field: str | None = None,
        use_precomputed_embeddings: bool = True,
        model_repo: str = "ttj/sac-logos-ava1-l14-linearMSE",
        model_filename: str = "model.safetensors",
        clip_model_name: str = "ViT-L-14",
        clip_pretrained: str = "openai",
        device: str = "auto",
        inference_batch_size: int = 32,
        use_fp16: bool = True,
        preprocess_workers: int = 4,
        num_frames: int = 8,
        score_aggregation: str = "mean",
        video_field: str = "video",
        video_url_field: str = "video_url",
        video_path_field: str = "video_path",
        cache_dir: str | None = None,
        timeout: int = 60,
        max_file_size: int | None = None,
        persistent_cache: bool = False,
        **kwargs: Any,
    ):
        """Initialize video aesthetic quality refiner.

        Args:
            embedding_field: Field name containing pre-computed CLIP ViT-L-14 embeddings (768-dim).
                             Use "video_clip_emb_vit_l_14" from VideoClipEmbeddingRefiner.
                             Required if use_precomputed_embeddings=True.
            use_precomputed_embeddings: If True, use pre-computed embeddings from embedding_field.
                                        If False, extract frames and compute embeddings internally.
            model_repo: Hugging Face model repository for the aesthetic predictor MLP
            model_filename: Filename of the model weights in the repo
            clip_model_name: OpenCLIP model name for direct mode (default: "ViT-L-14")
            clip_pretrained: Pretrained weights for CLIP model (default: "openai")
            device: Device to run model on ("cpu", "cuda", "mps", or "auto")
            inference_batch_size: Batch size for inference (default: 32)
            use_fp16: Use FP16 half precision for faster inference (default: True)
            preprocess_workers: Number of threads for parallel frame preprocessing
            num_frames: Number of frames to sample uniformly from each video (default: 8)
                        Following OpenVid-1M approach for better video representation.
            score_aggregation: How to aggregate scores from multiple frames.
                               Options: "mean" (default), "median", "min", "max"
            video_field: Field name for video data (dict with bytes/path, or direct path)
            video_url_field: Field name for video URL
            video_path_field: Field name for video file path
            cache_dir: Directory to cache downloaded videos
            timeout: Download timeout in seconds
            max_file_size: Maximum file size in bytes to download
            persistent_cache: If True, keep downloaded files across batches
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(**kwargs)

        self.use_precomputed_embeddings = use_precomputed_embeddings
        self.embedding_field = embedding_field
        self.inference_batch_size = inference_batch_size
        self.preprocess_workers = preprocess_workers
        self.num_frames = num_frames
        self.score_aggregation = score_aggregation

        # Validate configuration
        if use_precomputed_embeddings and not embedding_field:
            raise ValueError(
                "embedding_field is required when use_precomputed_embeddings=True. "
                "Use VideoClipEmbeddingRefiner first to generate embeddings, "
                "or set use_precomputed_embeddings=False for direct video processing."
            )

        if score_aggregation not in ("mean", "median", "min", "max"):
            raise ValueError(f"Invalid score_aggregation: {score_aggregation}. Must be one of: mean, median, min, max")

        # Initialize video loading functionality from mixin (needed for direct mode)
        if not use_precomputed_embeddings:
            self._init_video_loader(
                video_field=video_field,
                video_url_field=video_url_field,
                video_path_field=video_path_field,
                cache_dir=cache_dir,
                timeout=timeout,
                max_file_size=max_file_size,
                persistent_cache=persistent_cache,
            )

        # Handle device selection
        if device == "auto":
            if torch.backends.mps.is_available():
                device = "mps"
                logger.info("Auto-detected MPS (Mac GPU)")
            elif torch.cuda.is_available():
                device = "cuda"
                logger.info("Auto-detected CUDA")
            else:
                device = "cpu"
                logger.info("Using CPU")

        if device == "mps" and not torch.backends.mps.is_available():
            device = "cpu"
        elif device == "cuda" and not torch.cuda.is_available():
            device = "cpu"

        self.device = torch.device(device)

        # FP16 support (not for MPS which has limited fp16 support)
        self.use_fp16 = use_fp16 and device == "cuda"
        self.dtype = torch.float16 if self.use_fp16 else torch.float32

        if use_precomputed_embeddings:
            logger.info(f"Using pre-computed embeddings from field: '{embedding_field}'")
        else:
            logger.info(f"Direct video processing mode: sampling {num_frames} frames uniformly")
            logger.info(f"Score aggregation method: {score_aggregation}")
            # Load CLIP model for direct mode
            logger.info(f"Loading OpenCLIP model: {clip_model_name}/{clip_pretrained}...")
            model, _, self.preprocess = open_clip.create_model_and_transforms(
                clip_model_name, pretrained=clip_pretrained, device=self.device
            )
            self.visual = model.visual
            self.visual.eval()
            if self.use_fp16:
                self.visual = self.visual.half()
            del model

        logger.info(f"Required embedding dimension: {REQUIRED_EMBEDDING_DIM} (CLIP ViT-L/14)")

        # Load aesthetic predictor MLP from Hugging Face
        logger.info(f"Loading aesthetic predictor MLP from: {model_repo}...")
        self._load_aesthetic_mlp(model_repo, model_filename)

        # Thread pool initialized lazily (can't pickle ThreadPoolExecutor for Ray)
        self._executor = None

        logger.info(f"Video Aesthetic Quality Refiner initialized. Output field: {FIELD_VIDEO_AESTHETIC_SCORE}")

    def _load_aesthetic_mlp(self, model_repo: str, model_filename: str) -> None:
        """Load the aesthetic predictor MLP from Hugging Face."""
        # Download model from Hugging Face
        model_path = hf_hub_download(repo_id=model_repo, filename=model_filename)

        # Initialize MLP with CLIP ViT-L/14 embedding size (768)
        self.aesthetic_mlp = AestheticMLP(input_size=REQUIRED_EMBEDDING_DIM)

        # Load weights - handle both safetensors and pth formats
        if model_filename.endswith(".safetensors"):
            from safetensors.torch import load_file

            state_dict = load_file(model_path)
        else:
            state_dict = torch.load(model_path, map_location="cpu", weights_only=True)

        self.aesthetic_mlp.load_state_dict(state_dict)
        self.aesthetic_mlp.to(self.device)
        self.aesthetic_mlp.eval()

        # Convert MLP to FP16 if enabled (but predictions will be cast to float32)
        if self.use_fp16:
            self.aesthetic_mlp = self.aesthetic_mlp.half()
            logger.info("Aesthetic MLP using FP16 half precision")

        logger.info("Aesthetic predictor MLP loaded successfully")

    def _get_embeddings_from_field(self, records: list[dict[str, Any]]) -> tuple[torch.Tensor, list[int]]:
        """Extract embeddings from the specified field in records.

        Returns:
            Tuple of (embeddings tensor, valid_indices list)
        """
        embeddings = []
        valid_indices = []

        for i, record in enumerate(records):
            emb = record.get(self.embedding_field)
            if emb is not None:
                emb_array = np.array(emb, dtype=np.float32)
                if len(emb_array) == REQUIRED_EMBEDDING_DIM:
                    embeddings.append(emb_array)
                    valid_indices.append(i)
                else:
                    logger.warning(
                        f"Embedding dim mismatch at index {i}: got {len(emb_array)}, expected {REQUIRED_EMBEDDING_DIM}"
                    )

        if not embeddings:
            return torch.tensor([]), []

        # Stack and convert to tensor
        embeddings_tensor = torch.from_numpy(np.stack(embeddings)).to(self.device, dtype=self.dtype)
        return embeddings_tensor, valid_indices

    def _extract_frames(self, record: dict[str, Any]) -> list[Image.Image]:
        """Extract multiple frames uniformly from a video (OpenVid-1M style)."""
        local_path = self._get_local_video_path(record)
        if not local_path:
            return []
        return get_video_frames(local_path, num_frames=self.num_frames, sampling_strategy="uniform")

    def _preprocess_frame(self, frame: Image.Image) -> torch.Tensor | None:
        """Preprocess a single frame for CLIP model."""
        if frame is None:
            return None
        try:
            if frame.mode != "RGB":
                frame = frame.convert("RGB")
            return self.preprocess(frame)
        except Exception as e:
            logger.warning(f"Failed to preprocess frame: {e}")
            return None

    def _aggregate_scores(self, scores: np.ndarray) -> float:
        """Aggregate multiple frame scores into a single video score."""
        if len(scores) == 0:
            return 0.0

        if self.score_aggregation == "mean":
            return float(np.mean(scores))
        elif self.score_aggregation == "median":
            return float(np.median(scores))
        elif self.score_aggregation == "min":
            return float(np.min(scores))
        elif self.score_aggregation == "max":
            return float(np.max(scores))
        else:
            return float(np.mean(scores))

    def _compute_video_aesthetic_score(self, record: dict[str, Any]) -> float:
        """Compute aesthetic score for a single video by sampling multiple frames.

        This follows the OpenVid-1M approach:
        1. Sample num_frames uniformly across the video
        2. Compute CLIP embedding for each frame
        3. Predict aesthetic score for each frame
        4. Aggregate scores (mean by default)
        """
        # Extract frames uniformly
        frames = self._extract_frames(record)
        if not frames:
            return 0.0

        # Preprocess frames
        tensors = []
        for frame in frames:
            tensor = self._preprocess_frame(frame)
            if tensor is not None:
                tensors.append(tensor)

        if not tensors:
            return 0.0

        # Compute CLIP embeddings for all frames
        batch_tensor = torch.stack(tensors).to(self.device, dtype=self.dtype)
        with torch.inference_mode():
            embeddings = self.visual(batch_tensor)
            # L2 normalize embeddings (required for aesthetic predictor)
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)

            # Predict aesthetic scores for all frames
            scores = self.aesthetic_mlp(embeddings.to(self.aesthetic_mlp.layers[0].weight.dtype))
            scores = scores.float().cpu().numpy().flatten()

        # Aggregate scores across frames
        return self._aggregate_scores(scores)

    def refine_batch(self, records: list[dict[str, Any]]) -> None:
        """Predict aesthetic scores for a batch of videos inplace (GPU batch inference)."""
        if not records:
            return

        # Initialize all records with default score (0.0)
        for record in records:
            record[FIELD_VIDEO_AESTHETIC_SCORE] = 0.0

        if self.use_precomputed_embeddings:
            # Process using pre-computed embeddings (single embedding per video)
            for batch_start in range(0, len(records), self.inference_batch_size):
                batch_end = min(batch_start + self.inference_batch_size, len(records))
                batch_records = records[batch_start:batch_end]

                try:
                    embeddings, valid_indices = self._get_embeddings_from_field(batch_records)

                    if len(valid_indices) == 0:
                        continue

                    # Predict aesthetic scores
                    with torch.inference_mode():
                        scores = self.aesthetic_mlp(embeddings.to(self.aesthetic_mlp.layers[0].weight.dtype))
                        scores = scores.float().cpu().numpy().flatten()

                    for j, idx in enumerate(valid_indices):
                        batch_records[idx][FIELD_VIDEO_AESTHETIC_SCORE] = float(scores[j])

                except Exception as e:
                    logger.warning(f"Batch inference failed: {e}")
        else:
            # Direct mode: process each video with multi-frame sampling
            # Use thread pool for parallel video processing
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=self.preprocess_workers)

            # Process videos in parallel
            try:
                scores = list(self._executor.map(self._compute_video_aesthetic_score, records))
                for i, score in enumerate(scores):
                    records[i][FIELD_VIDEO_AESTHETIC_SCORE] = score
            except Exception as e:
                logger.warning(f"Parallel video processing failed: {e}")
                # Fallback to sequential processing
                for record in records:
                    try:
                        record[FIELD_VIDEO_AESTHETIC_SCORE] = self._compute_video_aesthetic_score(record)
                    except Exception as e2:
                        logger.warning(f"Failed to compute aesthetic score: {e2}")

    def get_output_schema(self) -> dict[str, pa.DataType]:
        """Return output schema for new fields added by this refiner."""
        return {
            FIELD_VIDEO_AESTHETIC_SCORE: pa.float32(),
        }
