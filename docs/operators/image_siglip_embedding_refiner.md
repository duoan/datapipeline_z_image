# ImageSigLIPEmbeddingRefiner

Extract image embeddings using SigLIP2 models.

## Overview

Computes semantic embeddings using Google's SigLIP2 vision encoders. **GPU Optimized** 🖥️ - alternative to CLIP with improved training methodology.

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `image_siglip_emb` | `list<float32>` | Normalized embedding vector |

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | `str` | `"google/siglip2-so400m-patch14-384"` | HuggingFace model name |
| `device` | `str` | `"auto"` | Device: "auto", "cuda", "mps", "cpu" |
| `normalize` | `bool` | `True` | Normalize to unit length |
| `inference_batch_size` | `int` | `32` | GPU batch size |
| `use_fp16` | `bool` | `True` | Use FP16 (CUDA only) |

## Usage

```yaml
stages:
  - name: embedding
    operators:
      - name: image_siglip_embedding_refiner
        params:
          model_name: "google/siglip2-so400m-patch14-384"
          use_fp16: true
    worker:
      resources:
        gpu: 1
```

## SigLIP vs CLIP

| Aspect | SigLIP2 | CLIP |
|--------|---------|------|
| Training | Sigmoid loss | Contrastive loss |
| Batch size | Smaller effective | Large required |
| Zero-shot | Better on some tasks | Good baseline |
| Models | HuggingFace | OpenCLIP |

## Performance

- **Throughput**: ~100-150 records/sec (GPU)
- **Memory**: ~1-2GB VRAM

## Reference

- [SigLIP (arXiv:2303.15343)](https://arxiv.org/abs/2303.15343) - Sigmoid loss for language-image pre-training
- [SigLIP2](https://huggingface.co/google/siglip2-so400m-patch14-384) - Improved version
