# TextAlphabeticWordRationFilter

Filter records by the ratio of words that do not contain alphabetic characters.

## Overview

This filter removes text that is dominated by numeric/symbol-heavy tokens (for example IDs, hashes, or noisy strings).

Note: the operator name uses `ration` (not `ratio`) to match the current implementation.

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text_field` | `str` | `"text"` | Input text field |
| `max_ratio` | `float` | `inf` | Maximum allowed fraction of non-alphabetic words |

## Filtering Logic

For each record:

1. Split text by whitespace into words.
2. Count words that contain no alphabetic character (`a-z`, `A-Z`, Unicode letters).
3. Compute `ratio = non_alpha_words / total_words`.
4. Keep record when `ratio <= max_ratio`.

Special cases:
- If there is exactly 1 word, the record is dropped.
- If there are 0 words, the record is kept.

## Usage

```yaml
- name: text_alphabetic_word_ration_filter
  params:
    max_ratio: 0.2
```

