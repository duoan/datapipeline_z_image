# TextSymbolRatioFilter

Filter records by symbol-to-word ratio.

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text_field` | `str` | `"text"` | Input text field |
| `max_symbol_to_word_ratio` | `float` | `inf` | Maximum allowed symbol-to-word ratio |

Symbols counted by default: `#`, `...`, `. . .`, `…`.

## Filtering Logic

For each record:

1. Count occurrences of configured symbols in text.
2. Normalize `. . .` to `...` and split by whitespace to count words.
3. Compute `ratio = symbol_count / max(word_count, 1)`.
4. Keep record when `ratio <= max_symbol_to_word_ratio`.

## Usage

```yaml
- name: text_symbol_ratio_filter
  params:
    max_symbol_to_word_ratio: 0.1
```

