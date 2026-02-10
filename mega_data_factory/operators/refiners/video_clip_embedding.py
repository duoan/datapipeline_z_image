"""
Video CLIP Embedding Refiner

Extracts video embeddings using OpenCLIP models by extracting frames from videos.
This refiner enriches records with CLIP embedding features for semantic analysis.

The refiner extracts a representative frame (middle frame by default) from each video
and computes CLIP embeddings using the visual encoder.

Requirements:
- OpenCLIP library
- OpenCV for frame extraction

Usage:
    # Extract CLIP embeddings from videos using ViT-L-14 model
    clip_refiner = VideoClipEmbeddingRefiner(
        model_name="ViT-L-14",
        pretrained="openai",
        frame_position="middle",  # Extract middle frame
    )

Output fields:
- video_clip_emb_{model_name}: CLIP embedding vector (e.g., video_clip_emb_vit_l_14)
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import open_clip
import pyarrow as pa
import torch
from PIL import Image

from mega_data_factory.framework import Refiner
from mega_data_factory.operators.video_operator import VideoOperatorMixin
from mega_data_factory.utils.video_utils import get_video_frame, get_video_frames

logger = logging.getLogger(__name__)


class VideoClipEmbeddingRefiner(VideoOperatorMixin, Refiner):
    """Refiner for extracting video embeddings using OpenCLIP.

    This refiner extracts frames from videos and computes CLIP embeddings
    using the visual encoder. It supports various frame extraction strategies
    and can average embeddings across multiple frames for better representation.

    Output fields:
    - video_clip_emb_{model_name}: CLIP embedding vector
    """

    def __init__(
        self,
        model_name: str = "ViT-L-14",
        pretrained: str = "openai",
        device: str = "auto",
        normalize: bool = True,
        feature_field_name: str | None = None,
        inference_batch_size: int = 32,
        use_fp16: bool = True,
        preprocess_workers: int = 4,
        frame_position: str = "middle",
        num_frames: int = 1,
        frame_aggregation: str = "mean",
        video_field: str = "video",
        video_url_field: str = "video_url",
        video_path_field: str = "video_path",
        cache_dir: str | None = None,
        timeout: int = 60,
        max_file_size: int | None = None,
        persistent_cache: bool = False,
        **kwargs: Any,
    ):
        """Initialize Video CLIP embedding refiner.

        Args:
            model_name: OpenCLIP model name (e.g., "ViT-B-32", "ViT-L-14")
            pretrained: Pretrained weights identifier (e.g., "openai", "laion400m_e32")
            device: Device to run model on ("cpu", "cuda", "mps", or "auto")
            normalize: Whether to normalize embeddings to unit length
            feature_field_name: Name of the output field for embedding
            inference_batch_size: Batch size for GPU inference (default: 32)
            use_fp16: Use FP16 half precision for faster inference (default: True)
            preprocess_workers: Number of threads for parallel image preprocessing
            frame_position: Position to extract frame from ("middle", "first", "last")
                           Only used when num_frames=1
            num_frames: Number of frames to extract and average (default: 1)
            frame_aggregation: How to aggregate multi-frame embeddings ("mean", "max")
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
        self.inference_batch_size = inference_batch_size
        self.preprocess_workers = preprocess_workers
        self.frame_position = frame_position
        self.num_frames = num_frames
        self.frame_aggregation = frame_aggregation

        self.model_name = model_name
        self.pretrained = pretrained
        self.normalize = normalize

        # Initialize video loading functionality from mixin
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

        # Set feature field name
        if feature_field_name is None:
            normalized_model_name = model_name.lower().replace("-", "_").replace(" ", "_")
            self.feature_field_name = f"video_clip_emb_{normalized_model_name}"
        else:
            self.feature_field_name = feature_field_name

        # Load model (visual tower only)
        logger.info(f"Loading OpenCLIP model: {model_name}/{pretrained} on {device}...")
        model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained, device=self.device
        )

        # Extract visual tower only, discard text encoder to save memory
        self.visual = model.visual
        self.visual.eval()
        self.embedding_dim = self.visual.output_dim

        # Convert to FP16 if enabled
        if self.use_fp16:
            self.visual = self.visual.half()
            logger.info("Using FP16 half precision")

        # Delete full model to free memory (text tower, etc.)
        del model

        # Thread pool initialized lazily (can't pickle ThreadPoolExecutor for Ray)
        self._executor = None

        logger.info(f"Model loaded (visual tower only). Embedding dim: {self.embedding_dim}")
        logger.info(f"Output field: {self.feature_field_name}")
        logger.info(f"Frame extraction: {num_frames} frame(s), position={frame_position}")

    def _extract_frame(self, record: dict[str, Any]) -> Image.Image | None:
        """Extract a representative frame from a video."""
        local_path = self._get_local_video_path(record)
        if not local_path:
            return None

        if self.num_frames == 1:
            return get_video_frame(local_path, frame_position=self.frame_position)
        else:
            # For multi-frame, we'll handle this separately
            return get_video_frame(local_path, frame_position=self.frame_position)

    def _extract_frames(self, record: dict[str, Any]) -> list[Image.Image]:
        """Extract multiple frames from a video."""
        local_path = self._get_local_video_path(record)
        if not local_path:
            return []

        return get_video_frames(local_path, num_frames=self.num_frames, sampling_strategy="uniform")

    def _preprocess_frame(self, frame: Image.Image | None) -> torch.Tensor | None:
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

    def _process_single_frame_batch(self, records: list[dict[str, Any]]) -> tuple[list[torch.Tensor], list[int]]:
        """Process batch with single frame per video."""
        # Lazy init thread pool (can't pickle for Ray serialization)
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.preprocess_workers)

        # Extract frames in parallel
        frames = list(self._executor.map(self._extract_frame, records))

        # Preprocess frames
        tensors = []
        valid_indices = []
        for i, frame in enumerate(frames):
            tensor = self._preprocess_frame(frame)
            if tensor is not None:
                tensors.append(tensor)
                valid_indices.append(i)

        return tensors, valid_indices

    def _process_multi_frame_batch(self, records: list[dict[str, Any]]) -> tuple[list[list[torch.Tensor]], list[int]]:
        """Process batch with multiple frames per video."""
        all_frame_tensors = []
        valid_indices = []

        for i, record in enumerate(records):
            frames = self._extract_frames(record)
            if not frames:
                continue

            frame_tensors = []
            for frame in frames:
                tensor = self._preprocess_frame(frame)
                if tensor is not None:
                    frame_tensors.append(tensor)

            if frame_tensors:
                all_frame_tensors.append(frame_tensors)
                valid_indices.append(i)

        return all_frame_tensors, valid_indices

    def refine_batch(self, records: list[dict[str, Any]]) -> None:
        """Extract CLIP embeddings from a batch of videos inplace (GPU batch inference)."""
        if not records:
            return

        zero_embedding = [0.0] * self.embedding_dim

        # Initialize all records with zero embeddings first
        for record in records:
            record[self.feature_field_name] = zero_embedding

        # Process in mini-batches
        for batch_start in range(0, len(records), self.inference_batch_size):
            batch_end = min(batch_start + self.inference_batch_size, len(records))
            batch_records = records[batch_start:batch_end]

            try:
                if self.num_frames == 1:
                    # Single frame processing
                    tensors, valid_indices = self._process_single_frame_batch(batch_records)

                    if not tensors:
                        continue

                    # Batch inference
                    batch_tensor = torch.stack(tensors).to(self.device, dtype=self.dtype)
                    with torch.inference_mode():
                        features = self.visual(batch_tensor)
                        if self.normalize:
                            features = features / features.norm(dim=-1, keepdim=True)
                        embeddings = features.float().cpu().numpy().tolist()

                    for j, idx in enumerate(valid_indices):
                        batch_records[idx][self.feature_field_name] = embeddings[j]

                else:
                    # Multi-frame processing with aggregation
                    all_frame_tensors, valid_indices = self._process_multi_frame_batch(batch_records)

                    if not all_frame_tensors:
                        continue

                    for j, (frame_tensors, idx) in enumerate(zip(all_frame_tensors, valid_indices)):
                        # Stack all frames for this video
                        batch_tensor = torch.stack(frame_tensors).to(self.device, dtype=self.dtype)

                        with torch.inference_mode():
                            features = self.visual(batch_tensor)
                            if self.normalize:
                                features = features / features.norm(dim=-1, keepdim=True)

                            # Aggregate across frames
                            if self.frame_aggregation == "max":
                                aggregated = features.max(dim=0)[0]
                            else:  # "mean" or default
                                aggregated = features.mean(dim=0)

                            # Re-normalize after aggregation if needed
                            if self.normalize:
                                aggregated = aggregated / aggregated.norm()

                            embedding = aggregated.float().cpu().numpy().tolist()

                        batch_records[idx][self.feature_field_name] = embedding

            except Exception as e:
                logger.warning(f"Batch inference failed: {e}")

    def get_output_schema(self) -> dict[str, pa.DataType]:
        """Return output schema for new fields added by this refiner.

        Note: Arrow doesn't have native list types with fixed length,
        so we use list<item: float> for the embedding feature.
        """
        return {
            self.feature_field_name: pa.list_(pa.float32()),  # Variable-length list of floats
        }
