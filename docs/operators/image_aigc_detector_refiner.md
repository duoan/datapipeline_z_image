# ImageAIGCDetectorRefiner

Detect AI-generated images (AIGC - AI Generated Content).

## Overview

Classifies images as real or AI-generated using a trained detector model. Useful for filtering synthetic content from training datasets.

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `image_aigc_score` | `float32` | AI-generated probability (0-1) |
| `image_is_aigc` | `bool` | Binary classification result |

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_path` | `str` | `None` | Path to custom AIGC detector model |
| `threshold` | `float` | `0.5` | Classification threshold |
| `clip_embedding_field` | `str` | `"image_clip_emb_vit_l_14"` | Input CLIP embedding field |

## Usage

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

  - name: aigc_detection
    operators:
      - name: image_aigc_detector_refiner
        params:
          threshold: 0.7  # Conservative threshold
```

## Score Interpretation

| Score | Interpretation |
|-------|----------------|
| < 0.3 | Likely real |
| 0.3-0.7 | Uncertain |
| > 0.7 | Likely AI-generated |

## Detectable Content

- Diffusion models (Stable Diffusion, DALL-E, Midjourney)
- GANs (StyleGAN, BigGAN)
- Other generative models

## Limitations

- May struggle with heavily edited real images
- New generation methods may evade detection
- Threshold tuning needed for specific use cases

## Performance

- **Throughput**: ~50,000 records/sec (CPU, after embeddings)
- **Memory**: ~10MB model

## Reference

- [Imagen 3 (arXiv:2408.07009)](https://arxiv.org/abs/2408.07009) - AIGC detection in data curation
- [Z-Image (arXiv:2511.22699)](https://arxiv.org/pdf/2511.22699) - Synthetic content filtering
