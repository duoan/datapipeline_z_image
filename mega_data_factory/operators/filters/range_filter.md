# Range Filter

Filters records based on numeric value range for a given column.

## Overview

The Range Filter allows you to filter records based on whether a numeric field value falls within a specified range. It supports open-ended ranges where either the minimum or maximum bound can be omitted.

## Features

- **Flexible Range**: Specify min, max, or both bounds
- **Inclusive Bounds**: Range is inclusive on both ends [min, max]
- **Missing Value Handling**: Configurable behavior for missing or non-numeric values
- **Type Coercion**: Automatically converts string values to numbers when possible

## Usage

### YAML Configuration

```yaml
stages:
  - name: quality_filter
    operators:
      # Filter records where score is between 5.0 and 10.0
      - name: range_filter
        params:
          field: "score"
          min_value: 5.0
          max_value: 10.0

      # Filter records where score >= 4.5 (no upper bound)
      - name: range_filter
        params:
          field: "video_aesthetic_score"
          min_value: 4.5

      # Filter records where duration <= 300 seconds (no lower bound)
      - name: range_filter
        params:
          field: "video_duration"
          max_value: 300
```

### Python API

```python
from mega_data_factory.operators.filters import RangeFilter

# Filter records where score is between 5.0 and 10.0
filter = RangeFilter(field="score", min_value=5.0, max_value=10.0)

# Filter records where score >= 4.5 (no upper bound)
filter = RangeFilter(field="score", min_value=4.5)

# Filter records where score <= 8.0 (no lower bound)
filter = RangeFilter(field="score", max_value=8.0)

# Keep records with missing values
filter = RangeFilter(field="score", min_value=5.0, keep_missing=True)

# Apply filter
records = [{"score": 5.0}, {"score": 4.0}, {"score": None}]
results = filter.should_keep_batch(records)
# results: [True, False, False]
```

## Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `field` | str | (required) | Name of the field to filter on |
| `min_value` | float/int | None | Minimum value (inclusive). None means no lower bound |
| `max_value` | float/int | None | Maximum value (inclusive). None means no upper bound |
| `keep_missing` | bool | False | If True, keep records where field is missing or non-numeric |

**Note**: At least one of `min_value` or `max_value` must be specified.

## Examples

### Video Aesthetic Score Filtering

Filter out videos with low aesthetic scores:

```yaml
stages:
  - name: video_aesthetic_scoring
    operators:
      - name: video_aesthetic_score_refiner
        params:
          use_precomputed_embeddings: false
          num_frames: 8
      - name: range_filter
        params:
          field: "video_aesthetic_score"
          min_value: 4.5  # Keep videos with score >= 4.5
```

### Video Duration Filtering

Keep only videos within a certain duration range:

```yaml
stages:
  - name: duration_filter
    operators:
      - name: range_filter
        params:
          field: "video_duration"
          min_value: 5.0    # At least 5 seconds
          max_value: 300.0  # At most 5 minutes
```

### Image Quality Filtering

Filter images based on quality score:

```yaml
stages:
  - name: quality_filter
    operators:
      - name: range_filter
        params:
          field: "image_quality_score"
          min_value: 0.7  # Keep high quality images
```

## Behavior

### Missing Values

By default (`keep_missing=False`), records with missing or non-numeric values are rejected:

```python
filter = RangeFilter(field="score", min_value=5.0)
records = [
    {"score": 6.0},    # Kept (6.0 >= 5.0)
    {"score": 4.0},    # Rejected (4.0 < 5.0)
    {"score": None},   # Rejected (missing)
    {"other": 7.0},    # Rejected (field missing)
    {"score": "abc"},  # Rejected (non-numeric)
]
```

Set `keep_missing=True` to keep records with missing values:

```python
filter = RangeFilter(field="score", min_value=5.0, keep_missing=True)
# Now records with missing/non-numeric values are kept
```

### Type Coercion

String values are automatically converted to numbers:

```python
filter = RangeFilter(field="score", min_value=5.0)
records = [
    {"score": "6.5"},  # Kept (converted to 6.5)
    {"score": "abc"},  # Rejected (cannot convert)
]
```

## Performance

The Range Filter is a lightweight, pure-Python filter with O(n) complexity where n is the number of records. It's suitable for filtering on any numeric field without requiring additional dependencies.
