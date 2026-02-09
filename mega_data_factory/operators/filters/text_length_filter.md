# TextLengthFilter

Filter records based on text length criteria across multiple modes.

## Overview

A simple but essential filter for text pipelines. Filters out documents that are too short (likely low quality) or too long (potential data quality issues or duplicates).

Used in pipelines like [FineWeb](https://huggingface.co/spaces/HuggingFaceFW/blogpost-fineweb-v1) and [RefinedWeb](https://arxiv.org/pdf/2306.01116).

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_length` | `int` | `0` | Minimum length (inclusive). Backward-compatible with char mode |
| `max_length` | `int \| None` | `None` | Maximum length (inclusive). `None` means no upper limit |
| `lower_bound` | `int \| None` | `None` | Alias for `min_length` (takes precedence when set) |
| `upper_bound` | `int \| None` | `None` | Alias for `max_length` (takes precedence when set) |
| `text_field` | `str` | `"text"` | Name of the text field to measure |
| `text_length_field` | `str` | `"text_length"` | Name of pre-computed length field (used in `char` mode) |
| `length_type` | `str` | `"char"` | One of: `char`, `word`, `sentence`, `line`, `paragraph` |
| `ignore_punctuation` | `bool` | `false` | For `char`/`word`: whether punctuation is excluded |

## Filtering Logic

A record is **kept** if:

```
lower_bound <= length(text, length_type) <= upper_bound
```

If no upper bound is set, only the lower bound is checked.

## Length Calculation

Length depends on `length_type`:

1. `char`: character count (or alphanumeric-only when `ignore_punctuation=true`)
2. `word`: word count (punctuation can be counted as separate tokens when `ignore_punctuation=false`)
3. `sentence`: count of `.`, `!`, `?` (minimum 1 for non-empty text)
4. `line`: number of lines
5. `paragraph`: non-empty blocks split by double newlines (minimum 1 for non-empty text)

Optimization: in `char` mode, if `ignore_punctuation=false` and `text_length_field` exists, it is used directly (O(1)).

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
          length_type: "char"
```

### Word Count Filtering

```yaml
- name: text_length_filter
  params:
    length_type: "word"
    lower_bound: 50
    upper_bound: 50000
    ignore_punctuation: true
```

### Sentence Count Filtering

```yaml
- name: text_length_filter
  params:
    length_type: "sentence"
    lower_bound: 3
    upper_bound: 500
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
