# TextBulletFilter

Filter records by bullet-line ratio.

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text_field` | `str` | `"text"` | Input text field |
| `max_bullet_ratio` | `float` | `inf` | Maximum allowed ratio of lines starting with bullet markers |

Bullet markers counted by default: `●`, `•`, `*`, `-`.

## Filtering Logic

For each record:

1. Split text by newline into lines.
2. Count lines starting with bullet markers.
3. Compute `ratio = bullet_lines / total_lines`.
4. Keep record when `ratio <= max_bullet_ratio`.

## Usage

```yaml
- name: text_bullet_filter
  params:
    max_bullet_ratio: 0.9
```

