# TextTargetLanguageFilter

Filters text documents based on language detection using the FastText language identification model from CCNet (Facebook).

## Overview

This filter uses the FastText language identification model to:
1. Detect the language of text documents
2. Filter out documents that don't match the target language(s)
3. Filter out documents with low language detection confidence scores
4. Optionally add detected language and confidence score as new columns

## Model

Uses the [facebook/fasttext-language-identification](https://huggingface.co/facebook/fasttext-language-identification) model from Hugging Face, which supports 176 languages.

## Installation

Requires `fasttext` and `huggingface_hub`:

```bash
pip install fasttext huggingface_hub
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `target_languages` | `list[str]` or `str` or `None` | `None` | Target language code(s) to keep. If `None`, all languages are accepted (only score threshold applies). |
| `min_score` | `float` | `0.65` | Minimum language detection confidence score (0.0 to 1.0). Documents below this threshold are filtered out. |
| `text_field` | `str` | `"text"` | Name of the text field to analyze. |
| `language_field` | `str` | `"language"` | Name of the output field for detected language. |
| `language_score_field` | `str` | `"language_score"` | Name of the output field for confidence score. |
| `add_language_column` | `bool` | `True` | If `True`, add detected language to output records. |
| `add_score_column` | `bool` | `True` | If `True`, add confidence score to output records. |

## Common Language Codes

| Code | Language |
|------|----------|
| `eng` | English |
| `zho` | Chinese |
| `fra` | French |
| `deu` | German |
| `spa` | Spanish |
| `jpn` | Japanese |
| `kor` | Korean |
| `rus` | Russian |
| `ara` | Arabic |
| `por` | Portuguese |
| `ita` | Italian |
| `nld` | Dutch |
| `pol` | Polish |
| `tur` | Turkish |
| `vie` | Vietnamese |
| `tha` | Thai |
| `hin` | Hindi |

## YAML Configuration Examples

### Filter for English only

```yaml
stages:
  - name: language_filter
    operators:
      - type: TextTargetLanguageFilter
        params:
          target_languages: ["eng"]
          min_score: 0.65
```

### Filter for multiple languages

```yaml
stages:
  - name: language_filter
    operators:
      - type: TextTargetLanguageFilter
        params:
          target_languages: ["eng", "fra", "deu"]
          min_score: 0.7
```

### Keep all languages but filter by confidence

```yaml
stages:
  - name: language_filter
    operators:
      - type: TextTargetLanguageFilter
        params:
          target_languages: null  # Accept all languages
          min_score: 0.8         # But require high confidence
```

### Disable output columns

```yaml
stages:
  - name: language_filter
    operators:
      - type: TextTargetLanguageFilter
        params:
          target_languages: ["eng"]
          add_language_column: false
          add_score_column: false
```

## Python Usage

```python
from mega_data_factory.operators.filters import TextTargetLanguageFilter

# Create filter for English documents
filter = TextTargetLanguageFilter(
    target_languages=["eng"],
    min_score=0.65
)

# Process records
records = [
    {"text": "Hello, this is an English document."},
    {"text": "Bonjour, ceci est un document français."},
    {"text": "这是一个中文文档。"},
]

keep_flags = filter.should_keep_batch(records)
# keep_flags = [True, False, False]

# Records are enriched with language info
print(records[0])
# {"text": "Hello...", "language": "eng", "language_score": 0.98}
```

## Output Schema

When `add_language_column` and/or `add_score_column` are enabled:

| Field | Type | Description |
|-------|------|-------------|
| `language` | `string` | Detected language code (e.g., "eng", "zho") |
| `language_score` | `float32` | Confidence score (0.0 to 1.0) |

## Performance Notes

- The FastText model is loaded lazily on first use
- Model is shared across all filter instances (singleton pattern)
- Model download happens once and is cached by `huggingface_hub`
- FastText inference is very fast (~10,000+ documents/second on CPU)

## References

- [CCNet Paper](https://arxiv.org/abs/1911.00359) - "CCNet: Extracting High Quality Monolingual Datasets from Web Crawl Data"
- [FastText Language Identification](https://fasttext.cc/docs/en/language-identification.html)
- [Hugging Face Model](https://huggingface.co/facebook/fasttext-language-identification)
