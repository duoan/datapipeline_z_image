# TextAvgWordLengthFilter

Filter records by average word length.

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text_field` | `str` | `"text"` | Input text field |
| `lower_bound` | `float` | `0.0` | Minimum allowed average word length |
| `upper_bound` | `float` | `inf` | Maximum allowed average word length |

## Filtering Logic

For each record:

1. Split text by whitespace into words.
2. Compute average word length.
3. Keep record when `lower_bound <= avg_word_len <= upper_bound`.

Special case:
- If no words are found, the record is dropped.

## Usage

```yaml
- name: text_avg_word_length_filter
  params:
    lower_bound: 3.0
    upper_bound: 12.0
```

