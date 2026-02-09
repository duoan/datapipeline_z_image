# TextNewLineRemovalRefiner

Normalize text by limiting consecutive newline characters.

## Overview

`TextNewLineRemovalRefiner` modifies a text field in-place so that long runs of `\n`
are reduced to at most `max_consecutive`.

This is useful for cleaning noisy crawled text where documents may contain large
blank sections.

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `text_field` | `str` | `"text"` | Field to normalize |
| `max_consecutive` | `int` | `2` | Maximum allowed consecutive newlines |

## Behavior

- If `text_field` is a string, newline runs are collapsed.
- Non-string values are left unchanged.
- No new fields are added; the input field is updated in-place.

## Usage

```yaml
stages:
  - name: text_cleaning
    operators:
      - name: text_new_line_removal_refiner
        params:
          text_field: "text"
          max_consecutive: 2
```

### Example

Input:

```text
Line A



Line B
```

Output (`max_consecutive=2`):

```text
Line A

Line B
```
