# ImageQualityFilter

Filter images based on quality metrics.

## Overview

A comprehensive image quality filter that combines multiple criteria to identify and remove low-quality images. Used in pipelines like [Z-Image](https://arxiv.org/pdf/2511.22699) and [LAION-5B](https://arxiv.org/pdf/2210.08402).

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_width` | `int` | `128` | Minimum image width in pixels |
| `min_height` | `int` | `128` | Minimum image height in pixels |
| `max_width` | `int \| None` | `None` | Maximum image width |
| `max_height` | `int \| None` | `None` | Maximum image height |
| `min_aspect_ratio` | `float` | `0.2` | Minimum aspect ratio (width/height) |
| `max_aspect_ratio` | `float` | `5.0` | Maximum aspect ratio |
| `max_compression_artifacts` | `float` | `0.8` | Maximum compression artifact score (0-1) |
| `min_entropy` | `float` | `0.0` | Minimum image entropy |

## Prerequisites

This filter requires metadata fields computed by upstream refiners:

- `image_width`, `image_height` - from `ImageMetadataRefiner`
- `compression_artifacts`, `entropy` - from `ImageTechnicalQualityRefiner`

## Filtering Logic

An image is **filtered out** if ANY of these conditions are met:

```
width < min_width OR height < min_height
width > max_width OR height > max_height (if set)
aspect_ratio < min_aspect_ratio OR aspect_ratio > max_aspect_ratio
compression_artifacts > max_compression_artifacts
entropy < min_entropy
```

## Usage

### Basic Usage

```yaml
stages:
  - name: quality_filtering
    operators:
      - name: image_metadata_refiner        # Required: computes width/height
      - name: image_technical_quality_refiner  # Required: computes artifacts/entropy
      - name: image_quality_filter
        params:
          min_width: 256
          min_height: 256
          max_compression_artifacts: 0.7
```

### Strict Quality (High-Resolution Dataset)

```yaml
- name: image_quality_filter
  params:
    min_width: 512
    min_height: 512
    max_compression_artifacts: 0.5
    min_entropy: 4.0
    min_aspect_ratio: 0.5
    max_aspect_ratio: 2.0
```

### Lenient Quality (Large-Scale Crawl)

```yaml
- name: image_quality_filter
  params:
    min_width: 128
    min_height: 128
    max_compression_artifacts: 0.9  # Allow more compression
```

## Quality Metrics Explained

### Compression Artifacts (0-1)

Measures JPEG block artifacts and compression quality:
- **0.0-0.3**: High quality, minimal artifacts
- **0.3-0.6**: Moderate quality
- **0.6-0.8**: Noticeable artifacts
- **0.8-1.0**: Severe artifacts, heavily compressed

### Entropy

Measures information content/complexity:
- **< 3.0**: Very simple (solid colors, gradients)
- **3.0-5.0**: Moderate complexity
- **5.0-7.0**: High complexity (detailed photos)
- **> 7.0**: Very high complexity (noise, text-heavy)

### Aspect Ratio

Common ranges:
- **1.0**: Square images
- **0.5-2.0**: Typical photos
- **< 0.2 or > 5.0**: Likely banners, strips, or anomalies

## Performance

- **Throughput**: ~4,000,000 records/sec (filtering only)
- **Memory**: Negligible

Note: The actual bottleneck is the upstream refiners that compute the metrics.

## Reference

- [Z-Image (arXiv:2511.22699)](https://arxiv.org/pdf/2511.22699) - Image generation data curation
- [LAION-5B (arXiv:2210.08402)](https://arxiv.org/pdf/2210.08402) - Large-scale image filtering
