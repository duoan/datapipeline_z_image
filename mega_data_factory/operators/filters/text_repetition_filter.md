# TextRepetitionFilter

Filter repetitive text using multi-granularity repetition checks over lines, paragraphs, and word n-grams.

## Overview

This operator follows a MassiveText/Gopher-style heuristic flow and applies multiple repetition thresholds (line-level, paragraph-level, and 2-10 gram word repetition).

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text_field` | `str` | `"text"` | Input text field |

## Filtering Logic

The filter runs a sequence of repetition-fraction checks and drops a record once any threshold is exceeded.

Checks include:
- line repetition (unweighted and weighted)
- paragraph repetition (unweighted and weighted)
- word n-gram repetition for n = 2..10 with decreasing upper bounds

## Runtime Requirement

This operator currently requires the Rust backend function:

`mega_data_factory.rust_operators.text_repetition_keep_batch`

If Rust operators are not available, it raises a runtime error.

## Usage

```yaml
- name: text_repetition_filter
  params:
    text_field: text
```

