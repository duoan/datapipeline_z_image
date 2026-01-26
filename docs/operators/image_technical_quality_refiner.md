# ImageTechnicalQualityRefiner

Assess technical image quality: compression artifacts and information entropy.

## Overview

Evaluates image technical quality using two key metrics. **Rust Accelerated** 🦀 - automatically uses Rust backend when available for 3-10x faster processing.

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `image_compression_artifacts` | `float32` | Artifact score (0-1, higher = more artifacts) |
| `image_information_entropy` | `float32` | Shannon entropy (higher = more detail) |

## Parameters

None - this refiner has no configurable parameters.

## Usage

```yaml
stages:
  - name: quality_assessment
    operators:
      - name: image_technical_quality_refiner  # 🦀 Rust accelerated
```

## Metrics Explained

### Compression Artifacts (0-1)

Combines JPEG blockiness detection with compression ratio analysis:

| Score | Quality | Description |
|-------|---------|-------------|
| 0.0-0.3 | High | Minimal visible artifacts |
| 0.3-0.6 | Medium | Some compression visible |
| 0.6-0.8 | Low | Noticeable blockiness |
| 0.8-1.0 | Poor | Severe compression damage |

**Algorithm:**
1. Detect 8x8 block boundaries (JPEG artifact pattern)
2. Measure pixel discontinuities at boundaries
3. Calculate compression ratio score
4. Combine: `0.6 × blockiness + 0.4 × compression_score`

### Information Entropy

Shannon entropy measuring image complexity:

| Entropy | Content Type |
|---------|--------------|
| < 3.0 | Simple (solid colors, gradients) |
| 3.0-5.0 | Moderate (graphics, illustrations) |
| 5.0-7.0 | Complex (photographs) |
| > 7.0 | Very complex (noise, dense text) |

**Algorithm:**
1. Calculate histogram for each RGB channel
2. Compute Shannon entropy: `H = -Σ p(x) log₂ p(x)`
3. Average across channels

## Rust vs Python

| Backend | Throughput | Notes |
|---------|------------|-------|
| 🦀 Rust | ~2,500 rec/sec | Auto-selected when available |
| Python | ~800 rec/sec | Fallback |

The Rust backend uses:
- `image` crate for decoding
- `rayon` for parallel batch processing
- Optimized memory layout

## Performance

- **Throughput**: ~2,500 records/sec (Rust)
- **Memory**: ~50MB per batch of 256 images

## Reference

- [Imagen 3 (arXiv:2408.07009)](https://arxiv.org/abs/2408.07009) - Image quality assessment
- [Z-Image (arXiv:2511.22699)](https://arxiv.org/pdf/2511.22699) - Technical quality filtering
