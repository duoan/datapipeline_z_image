# TextEllipsisLineRatioFilter

Filter records by the ratio of non-empty lines ending with ellipsis.

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text_field` | `str` | `"text"` | Input text field |
| `max_ratio` | `float` | `inf` | Maximum allowed ellipsis-line ratio |

Ellipsis endings counted by default: `...`, `. . .`, `…`.

## Filtering Logic

For each record:

1. Split text into lines and keep only non-empty lines.
2. Count lines ending with an ellipsis suffix.
3. Compute `ratio = ellipsis_lines / max(non_empty_lines, 1)`.
4. Keep record when `ratio <= max_ratio`.

## Usage

```yaml
- name: text_ellipsis_line_ratio_filter
  params:
    max_ratio: 0.3
```

