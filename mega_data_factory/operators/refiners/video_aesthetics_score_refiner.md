# Video Aesthetic Score Refiner

Predicts aesthetic quality scores for videos using CLIP+MLP model.

## Overview

This refiner predicts how visually appealing a video is on a scale of approximately 1-10. It uses the improved-aesthetic-predictor model trained on the AVA dataset and LAION logos, which was originally designed for images but works well for video frames.

**Following the OpenVid-1M approach**, this refiner samples multiple frames uniformly across the video and computes the average aesthetic score for better representation of the entire video content.

The model is based on:
- [improved-aesthetic-predictor](https://github.com/christophschuhmann/improved-aesthetic-predictor)
- [Hugging Face Model](https://huggingface.co/ttj/sac-logos-ava1-l14-linearMSE)

## Features

- **Multi-Frame Sampling**: Samples multiple frames uniformly across the video (OpenVid-1M style)
- **Score Aggregation**: Supports mean, median, min, max aggregation methods
- **Two Operating Modes**: Use pre-computed embeddings or process videos directly
- **GPU Acceleration**: Supports CUDA and MPS (Apple Silicon)
- **FP16 Support**: Half-precision inference for faster processing
- **Batch Processing**: Efficient batch inference for high throughput

## Requirements

- PyTorch
- Hugging Face Hub (`pip install huggingface-hub`)
- safetensors (`pip install safetensors`)
- OpenCLIP (for direct mode, `pip install open-clip-torch`)
- OpenCV (for direct mode, `pip install opencv-python`)

## Usage

### Option 1: Direct Video Processing (Recommended - OpenVid-1M Style)

Process videos directly with multi-frame sampling:

```yaml
stages:
  - name: video_aesthetic
    operators:
      - type: VideoAestheticScoreRefiner
        use_precomputed_embeddings: false
        num_frames: 8  # Sample 8 frames uniformly across the video
        score_aggregation: "mean"  # Average the scores
```

### Option 2: Using Pre-computed Embeddings

First extract CLIP embeddings, then compute aesthetic scores:

```yaml
stages:
  - name: video_embedding
    operators:
      - type: VideoClipEmbeddingRefiner
        model_name: "ViT-L-14"
        pretrained: "openai"
        num_frames: 8
        frame_aggregation: "mean"

  - name: video_aesthetic
    operators:
      - type: VideoAestheticScoreRefiner
        embedding_field: "video_clip_emb_vit_l_14"
```

### Python API

```python
from mega_data_factory.operators.refiners import VideoAestheticScoreRefiner

# Direct video processing with multi-frame sampling (OpenVid-1M style)
refiner = VideoAestheticScoreRefiner(
    use_precomputed_embeddings=False,
    num_frames=8,  # Sample 8 frames uniformly
    score_aggregation="mean",  # Average the scores
)

# Using pre-computed embeddings
refiner = VideoAestheticScoreRefiner(
    embedding_field="video_clip_emb_vit_l_14",
)

# Process records
records = [{"video_path": "video1.mp4"}, {"video_clip_emb_vit_l_14": [...]}]
refiner.refine_batch(records)
```

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `embedding_field` | str | None | Field with pre-computed CLIP embeddings |
| `use_precomputed_embeddings` | bool | True | Use embeddings from field vs. compute directly |
| `model_repo` | str | "ttj/sac-logos-ava1-l14-linearMSE" | HuggingFace model repo |
| `model_filename` | str | "model.safetensors" | Model weights filename |
| `clip_model_name` | str | "ViT-L-14" | CLIP model for direct mode |
| `clip_pretrained` | str | "openai" | CLIP pretrained weights |
| `device` | str | "auto" | Device: "cpu", "cuda", "mps", or "auto" |
| `inference_batch_size` | int | 32 | Batch size for inference |
| `use_fp16` | bool | True | Use FP16 half precision (CUDA only) |
| `preprocess_workers` | int | 4 | Threads for frame preprocessing |
| `num_frames` | int | 8 | Number of frames to sample uniformly (OpenVid-1M style) |
| `score_aggregation` | str | "mean" | How to aggregate frame scores: "mean", "median", "min", "max" |
| `video_field` | str | "video" | Field name for video data |
| `video_url_field` | str | "video_url" | Field name for video URL |
| `video_path_field` | str | "video_path" | Field name for video path |
| `cache_dir` | str | None | Directory to cache downloaded videos |
| `timeout` | int | 60 | Download timeout in seconds |
| `max_file_size` | int | None | Maximum file size in bytes |
| `persistent_cache` | bool | False | Keep cache across batches |

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `video_aesthetic_score` | float | Aesthetic quality score (typically 1-10) |

## Score Interpretation

| Score Range | Quality | Description |
|-------------|---------|-------------|
| 1-3 | Poor | Low visual quality, unappealing |
| 3-5 | Below Average | Some issues with composition or quality |
| 5-6 | Average | Acceptable visual quality |
| 6-7 | Good | Visually appealing |
| 7-8 | Very Good | High visual quality |
| 8-10 | Excellent | Professional-level aesthetics |

## Multi-Frame Sampling (OpenVid-1M Approach)

Following the OpenVid-1M paper, this refiner samples multiple frames uniformly across the video:

1. **Frame Extraction**: Sample `num_frames` frames uniformly distributed across the video duration
2. **Per-Frame Scoring**: Compute CLIP embedding and aesthetic score for each frame
3. **Score Aggregation**: Combine frame scores using the specified aggregation method

### Why Multi-Frame Sampling?

- **Better Representation**: A single frame may not represent the overall video quality
- **Handles Variation**: Videos often have varying quality across different scenes
- **Robust Scoring**: Averaging reduces the impact of outlier frames (e.g., black frames, transitions)

### Aggregation Methods

| Method | Description | Use Case |
|--------|-------------|----------|
| `mean` | Average of all frame scores | Default, most stable |
| `median` | Middle value, ignores outliers | When videos have occasional bad frames |
| `min` | Lowest frame score | Conservative, ensures minimum quality |
| `max` | Highest frame score | Optimistic, captures best moments |

## Operating Modes

### Direct Processing Mode (Recommended)

**Advantages:**
- Simpler pipeline (single operator)
- Multi-frame sampling built-in
- No need to store embeddings
- Better video representation

**Process:**
1. Load video
2. Sample `num_frames` frames uniformly
3. Compute CLIP embedding for each frame
4. Predict aesthetic score for each frame
5. Aggregate scores

### Pre-computed Embeddings Mode

**Advantages:**
- Faster if embeddings are already computed
- Embeddings can be reused for other tasks
- Lower memory usage during aesthetic scoring

**Requirements:**
- Must use ViT-L-14 CLIP model (768-dim embeddings)
- Embeddings must be L2-normalized
- Single embedding per video (use VideoClipEmbeddingRefiner with multi-frame aggregation)

## Example Pipeline

Complete pipeline for video aesthetic filtering:

```yaml
name: video_aesthetic_pipeline

loader:
  type: HuggingFaceLoader
  dataset_name: "my-video-dataset"
  split: "train"

stages:
  - name: metadata
    operators:
      - type: VideoMetadataRefiner

  - name: aesthetic
    operators:
      - type: VideoAestheticScoreRefiner
        use_precomputed_embeddings: false
        num_frames: 8
        score_aggregation: "mean"

  - name: filter
    operators:
      - type: ThresholdFilter
        field: "video_aesthetic_score"
        min_value: 5.0

writer:
  type: ParquetWriter
  output_path: "./output/high_quality_videos"
```

## Performance Tips

1. **Use GPU**: CUDA provides significant speedup
2. **Batch Processing**: Larger batches are more efficient
3. **FP16**: Enable for faster inference on CUDA
4. **Adjust num_frames**: Use fewer frames (4-8) for faster processing, more (16-32) for accuracy
5. **Persistent Cache**: Enable for repeated processing of same videos

## Comparison with Image Aesthetic Quality

| Feature | ImageAestheticQualityRefiner | VideoAestheticScoreRefiner |
|---------|------------------------------|----------------------------|
| Input | Single image | Video (multiple frames) |
| Frame Sampling | N/A | Uniform sampling |
| Score Aggregation | N/A | mean/median/min/max |
| Model | Same MLP | Same MLP |
| Output | Single score | Aggregated score |

## References

- [OpenVid-1M Paper](https://arxiv.org/abs/2407.02371) - Multi-frame aesthetic scoring approach
- [LAION Aesthetics](https://laion.ai/blog/laion-aesthetics/) - Aesthetic predictor model
- [improved-aesthetic-predictor](https://github.com/christophschuhmann/improved-aesthetic-predictor) - Model implementation
