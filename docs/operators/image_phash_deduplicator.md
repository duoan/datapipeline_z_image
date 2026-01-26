# ImagePhashDeduplicator

Deduplicate images using perceptual hashing.

## Overview

Uses perceptual hashing (pHash) to identify and remove near-duplicate images. Unlike cryptographic hashes, perceptual hashes remain similar for visually similar images even with minor modifications (resizing, compression, color adjustments).

**Rust Accelerated** 🦀 - Uses `image_hasher` crate with rayon for parallel processing.

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hash_size` | `int` | `16` | Hash size (larger = more precise, slower) |
| `image_field` | `str` | `"image"` | Field containing image bytes |
| `hash_field` | `str` | `"image_phash"` | Field to store computed hash |

## How It Works

1. **Hash Computation**: Converts image to grayscale, resizes to `hash_size × hash_size`, applies DCT, extracts hash
2. **Deduplication**: Uses distributed `DedupBackend` with bucketed storage to check for existing hashes
3. **First-seen wins**: Only the first occurrence of each hash is kept

## Algorithm

Uses Double Gradient hash algorithm:
1. Resize image to `hash_size × hash_size`
2. Convert to grayscale
3. Compute gradients in both directions
4. Generate binary hash from gradient signs

## Usage

### Basic Usage

```yaml
stages:
  - name: deduplication
    operators:
      - name: image_phash_deduplicator
```

### Custom Hash Size

```yaml
- name: image_phash_deduplicator
  params:
    hash_size: 32  # More precise (256-bit hash)
```

### Configuring Dedup Backend

```yaml
executor:
  dedup_num_buckets: 16  # Distribute state across 16 actors
```

## Hash Sizes

| Size | Bits | Precision | Speed | Use Case |
|------|------|-----------|-------|----------|
| 8 | 64 | Low | Fast | Quick filtering |
| 16 | 256 | Medium | Medium | **Recommended** |
| 32 | 1024 | High | Slow | High precision |

## Distributed Deduplication

Uses Ray actors for distributed state:

```
┌─────────────┐
│   Worker    │──hash──▶┌─────────────────┐
├─────────────┤         │ DedupBackend[0] │
│   Worker    │──hash──▶├─────────────────┤
├─────────────┤         │ DedupBackend[1] │
│   Worker    │──hash──▶├─────────────────┤
└─────────────┘         │      ...        │
                        └─────────────────┘
```

Hashes are routed to buckets based on hash value, enabling scaling to billions of images.

## Performance

- **Throughput**: ~1,500 records/sec (including image decoding)
- **Memory**: O(unique_hashes) per bucket
- **Scaling**: Linear with `dedup_num_buckets`

## Near-Duplicate Detection

To find similar (not exact) images, use the hash with Hamming distance:

```python
# Two images are similar if hamming_distance(hash1, hash2) < threshold
# Threshold of 10-15 works well for 256-bit hashes
```

## Reference

- [LAION-5B (arXiv:2210.08402)](https://arxiv.org/pdf/2210.08402) - Perceptual deduplication
- [image_hasher](https://github.com/abonander/img_hash) - Rust implementation
