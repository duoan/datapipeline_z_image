# ImageAestheticQualityRefiner

Predict aesthetic quality scores using CLIP-based models.

## Overview

Evaluates subjective image quality (aesthetics, composition, appeal) using a lightweight MLP trained on aesthetic ratings. Requires CLIP embeddings as input.

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `image_aesthetic_score` | `float32` | Aesthetic score (typically 1-10) |

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_path` | `str` | `None` | Path to custom aesthetic model |
| `clip_embedding_field` | `str` | `"image_clip_emb_vit_l_14"` | Input CLIP embedding field |

## Usage

### With CLIP Embeddings

```yaml
stages:
  - name: embedding
    operators:
      - name: image_clip_embedding_refiner
        params:
          model_name: "ViT-L-14"
    worker:
      resources:
        gpu: 1

  - name: scoring
    operators:
      - name: image_aesthetic_quality_refiner
        params:
          clip_embedding_field: "image_clip_emb_vit_l_14"
```

## Score Interpretation

| Score | Quality |
|-------|---------|
| < 4.0 | Poor aesthetics |
| 4.0-5.5 | Below average |
| 5.5-6.5 | Average |
| 6.5-7.5 | Good |
| > 7.5 | Excellent |

## Architecture

```
CLIP Embedding (768-dim)
    ↓
Linear(768, 1024) + ReLU + Dropout
    ↓
Linear(1024, 128) + ReLU + Dropout
    ↓
Linear(128, 64) + ReLU + Dropout
    ↓
Linear(64, 16) + ReLU
    ↓
Linear(16, 1) → Aesthetic Score
```

## Performance

- **Throughput**: ~50,000 records/sec (CPU, after embeddings)
- **Memory**: ~10MB model

## Reference

- [LAION Aesthetic Predictor](https://github.com/LAION-AI/aesthetic-predictor)
- [Z-Image (arXiv:2511.22699)](https://arxiv.org/pdf/2511.22699) - Aesthetic filtering
