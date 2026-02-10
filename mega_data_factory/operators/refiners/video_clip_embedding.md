# Video CLIP Embedding Refiner

Extracts video embeddings using OpenCLIP models by extracting frames from videos.

## Overview

This refiner enriches records with CLIP embedding features for semantic analysis of video content. It extracts representative frames from videos and computes CLIP embeddings using the visual encoder.

## Features

- **Multiple Frame Extraction**: Extract single or multiple frames from videos
- **Flexible Frame Selection**: Choose frame position (first, middle, last) or uniform sampling
- **Multi-Frame Aggregation**: Average or max-pool embeddings across multiple frames
- **GPU Acceleration**: Supports CUDA and MPS (Apple Silicon) for fast inference
- **FP16 Support**: Half-precision inference for faster processing on CUDA
- **Video Loading**: Supports local files and URLs with automatic caching

## Requirements

- OpenCLIP library (`pip install open-clip-torch`)
- OpenCV for frame extraction (`pip install opencv-python`)
- PyTorch

## Usage

### Basic Usage (Single Frame)

```yaml
stages:
  - name: video_embedding
    operators:
      - type: VideoClipEmbeddingRefiner
        model_name: "ViT-L-14"
        pretrained: "openai"
        frame_position: "middle"
```

### Multi-Frame Embedding

```yaml
stages:
  - name: video_embedding
    operators:
      - type: VideoClipEmbeddingRefiner
        model_name: "ViT-L-14"
        pretrained: "openai"
        num_frames: 8
        frame_aggregation: "mean"
```

### Python API

```python
from mega_data_factory.operators.refiners import VideoClipEmbeddingRefiner

# Single frame embedding
refiner = VideoClipEmbeddingRefiner(
    model_name="ViT-L-14",
    pretrained="openai",
    frame_position="middle",
)

# Multi-frame embedding with averaging
refiner = VideoClipEmbeddingRefiner(
    model_name="ViT-L-14",
    pretrained="openai",
    num_frames=8,
    frame_aggregation="mean",
)

# Process records
records = [{"video_path": "video1.mp4"}, {"video_url": "https://example.com/video2.mp4"}]
refiner.refine_batch(records)
```

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | str | "ViT-L-14" | OpenCLIP model name |
| `pretrained` | str | "openai" | Pretrained weights identifier |
| `device` | str | "auto" | Device: "cpu", "cuda", "mps", or "auto" |
| `normalize` | bool | True | Normalize embeddings to unit length |
| `feature_field_name` | str | None | Custom output field name |
| `inference_batch_size` | int | 32 | Batch size for GPU inference |
| `use_fp16` | bool | True | Use FP16 half precision (CUDA only) |
| `preprocess_workers` | int | 4 | Threads for parallel preprocessing |
| `frame_position` | str | "middle" | Frame position: "first", "middle", "last" |
| `num_frames` | int | 1 | Number of frames to extract |
| `frame_aggregation` | str | "mean" | Aggregation method: "mean" or "max" |
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
| `video_clip_emb_{model_name}` | list[float] | CLIP embedding vector (e.g., `video_clip_emb_vit_l_14`) |

## Model Options

Common model configurations:

| Model | Pretrained | Embedding Dim | Notes |
|-------|------------|---------------|-------|
| ViT-B-32 | openai | 512 | Faster, smaller |
| ViT-L-14 | openai | 768 | Better quality, required for aesthetic scoring |
| ViT-H-14 | laion2b_s32b_b79k | 1024 | Largest, best quality |

## Frame Extraction Strategies

### Single Frame (`num_frames=1`)

- `frame_position="first"`: First frame of the video
- `frame_position="middle"`: Middle frame (default)
- `frame_position="last"`: Last frame

### Multiple Frames (`num_frames > 1`)

Frames are uniformly sampled across the video duration.

### Aggregation Methods

- `frame_aggregation="mean"`: Average embeddings (default, more stable)
- `frame_aggregation="max"`: Max-pool embeddings (captures salient features)

## Integration with Aesthetic Scoring

For video aesthetic scoring, use ViT-L-14 embeddings:

```yaml
stages:
  - name: video_embedding
    operators:
      - type: VideoClipEmbeddingRefiner
        model_name: "ViT-L-14"
        pretrained: "openai"

  - name: video_aesthetic
    operators:
      - type: VideoAestheticScoreRefiner
        embedding_field: "video_clip_emb_vit_l_14"
```

## Performance Tips

1. **Use GPU**: CUDA provides 10-50x speedup over CPU
2. **Enable FP16**: Reduces memory and increases throughput on CUDA
3. **Batch Processing**: Larger batches are more efficient
4. **Single Frame**: Use `num_frames=1` for faster processing when quality is sufficient
5. **Persistent Cache**: Enable for repeated processing of same videos
