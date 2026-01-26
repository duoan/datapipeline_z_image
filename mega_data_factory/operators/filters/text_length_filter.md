# TextLengthFilter

Filter records based on text length criteria.

## Overview

A simple but essential filter for text pipelines. Filters out documents that are too short (likely low quality) or too long (potential data quality issues or duplicates).

Used in pipelines like [FineWeb](https://huggingface.co/spaces/HuggingFaceFW/blogpost-fineweb-v1) and [RefinedWeb](https://arxiv.org/pdf/2306.01116).

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_length` | `int` | `0` | Minimum text length (inclusive, in characters) |
| `max_length` | `int \| None` | `None` | Maximum text length (inclusive). `None` means no upper limit |
| `text_field` | `str` | `"text"` | Name of the text field to measure |
| `text_length_field` | `str` | `"text_length"` | Name of pre-computed length field (if available) |

## Filtering Logic

A record is **kept** if:
```
min_length <= text_length <= max_length
```

If `max_length` is `None`, only the minimum is checked.

## Length Calculation

The filter intelligently determines text length:

1. **Pre-computed field**: If `text_length_field` exists in the record, uses it directly (O(1))
2. **Calculate from text**: Otherwise, computes `len(text)` on the fly

This optimization works well with loaders that provide `text_length` (like `CommonCrawlLoader`).

## Usage

### Basic Usage

```yaml
stages:
  - name: content_filtering
    operators:
      - name: text_length_filter
        params:
          min_length: 100
          max_length: 100000
```

### Minimum Only (No Upper Limit)

```yaml
- name: text_length_filter
  params:
    min_length: 200  # At least 200 characters
    # max_length: None (default)
```

### Custom Field Names

```yaml
- name: text_length_filter
  params:
    min_length: 50
    text_field: "content"           # Use "content" instead of "text"
    text_length_field: "char_count" # Use "char_count" instead of "text_length"
```

### Typical Ranges by Pipeline

| Pipeline | min_length | max_length | Notes |
|----------|------------|------------|-------|
| FineWeb | 200 | None | Quality focus |
| RefinedWeb | 100 | 100000 | Balance coverage |
| General web | 50 | 500000 | Broad filtering |

## Performance

- **Throughput**: ~2,000,000 records/sec
- **Memory**: Negligible

This is one of the fastest filters since it only performs integer comparisons.

## Combining with Other Filters

Typically used early in the pipeline to quickly remove obviously bad content:

```yaml
stages:
  - name: content_filtering
    operators:
      - name: url_filter           # First: URL-based filtering
        params:
          score_threshold: 0.5
      - name: text_length_filter   # Second: Length filtering
        params:
          min_length: 100
          max_length: 100000
      # Then: More expensive filters (language, perplexity, etc.)
```

## Reference

- [FineWeb](https://huggingface.co/spaces/HuggingFaceFW/blogpost-fineweb-v1) - 15T token dataset
- [RefinedWeb](https://arxiv.org/pdf/2306.01116) - Section G.2: Text Filtering
