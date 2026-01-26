# ImageClipEmbeddingRefiner

Extract CLIP image embeddings using OpenCLIP models.

## Overview

Computes semantic embeddings for images using CLIP vision encoders. **GPU Optimized** 🖥️ - uses batch inference with FP16 support for maximum throughput.

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `image_clip_emb_{model}` | `list<float32>` | Normalized embedding vector |

Field name is auto-generated from model name (e.g., `image_clip_emb_vit_l_14`).

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | `str` | `"ViT-B-32"` | OpenCLIP model name |
| `pretrained` | `str` | `"openai"` | Pretrained weights |
| `device` | `str` | `"auto"` | Device: "auto", "cuda", "mps", "cpu" |
| `normalize` | `bool` | `True` | Normalize to unit length |
| `feature_field_name` | `str` | `None` | Custom output field name |
| `inference_batch_size` | `int` | `32` | GPU batch size |
| `use_fp16` | `bool` | `True` | Use FP16 (CUDA only) |
| `preprocess_workers` | `int` | `4` | Preprocessing threads |

## Usage

### Basic Usage

```yaml
stages:
  - name: embedding
    operators:
      - name: image_clip_embedding_refiner
    worker:
      resources:
        gpu: 1
```

### High-Quality Model

```yaml
- name: image_clip_embedding_refiner
  params:
    model_name: "ViT-L-14"
    pretrained: "openai"
    use_fp16: true
    inference_batch_size: 64
```

### Custom Pretrained Weights

```yaml
- name: image_clip_embedding_refiner
  params:
    model_name: "ViT-B-32"
    pretrained: "laion400m_e32"  # LAION-trained weights
```

## Available Models

| Model | Dim | Speed | Quality | Memory |
|-------|-----|-------|---------|--------|
| `ViT-B-32` | 512 | Fast | Good | ~400MB |
| `ViT-B-16` | 512 | Medium | Better | ~600MB |
| `ViT-L-14` | 768 | Slow | Best | ~1.2GB |

## Memory Optimization

Only the visual tower is loaded - text encoder is discarded:
- ViT-L-14: ~1.2GB instead of ~2GB
- Enables larger batch sizes

## Performance

| Config | Throughput | Notes |
|--------|------------|-------|
| ViT-B-32, FP16, batch=64 | ~300 rec/sec | A100 |
| ViT-L-14, FP16, batch=32 | ~130 rec/sec | A100 |
| ViT-B-32, FP32, MPS | ~100 rec/sec | M1 Pro |

## Use Cases

- **Semantic Search**: Find similar images by embedding distance
- **Filtering**: CLIP score with text queries (DataComp style)
- **Clustering**: Group semantically similar images
- **Deduplication**: Semantic near-duplicate detection

## Reference

- [CLIP (arXiv:2103.00020)](https://arxiv.org/abs/2103.00020) - Original CLIP paper
- [OpenCLIP](https://github.com/mlfoundations/open_clip) - Open-source implementation
- [DataComp (arXiv:2304.14108)](https://arxiv.org/pdf/2304.14108) - CLIP filtering benchmark
