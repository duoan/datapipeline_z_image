# ImageVisualDegradationsRefiner

Detect visual quality degradations: blur, noise, watermarks, color issues.

## Overview

Identifies common image quality problems that affect usability for training. Complements technical quality metrics with visual degradation detection.

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `image_blur_score` | `float32` | Blur level (0-1, higher = more blur) |
| `image_noise_score` | `float32` | Noise level (0-1) |
| `image_color_cast_score` | `float32` | Color cast severity (0-1) |
| `image_has_watermark` | `bool` | Watermark detected |
| `image_has_border` | `bool` | Significant border detected |

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `blur_threshold` | `float` | `0.5` | Blur detection threshold |
| `noise_threshold` | `float` | `0.5` | Noise detection threshold |
| `watermark_detection` | `bool` | `True` | Enable watermark detection |

## Usage

```yaml
stages:
  - name: quality_assessment
    operators:
      - name: image_visual_degradations_refiner
        params:
          blur_threshold: 0.6
          watermark_detection: true
```

## Detection Methods

### Blur Detection
- Laplacian variance method
- Lower variance = more blur

### Noise Detection
- High-frequency component analysis
- Median filter difference

### Color Cast
- Channel histogram analysis
- Deviation from neutral balance

### Watermark Detection
- Edge density in typical watermark regions
- Text-like pattern detection

## Performance

- **Throughput**: ~1,000-2,000 records/sec
- **Memory**: Moderate (image processing)

## Reference

- [LAION-5B (arXiv:2210.08402)](https://arxiv.org/pdf/2210.08402) - Quality filtering
