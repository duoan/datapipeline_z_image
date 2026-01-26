# URLFilter

Filter records based on URL criteria using the approach from RefinedWeb.

## Overview

Implements three-part URL filtering from [RefinedWeb (arXiv:2306.01116)](https://arxiv.org/pdf/2306.01116) Section G.1:

1. **Domain Blocklist** (G.1.1) - Filters adult/spam/fraudulent domains
2. **URL Word Scoring** (G.1.2) - Scores URLs based on word severity weights
3. **High-Quality Source Exclusion** (G.1.3) - Excludes curated sources to prevent overlap

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url_field` | `str` | `"url"` | Name of the URL field in records |
| `blocklist_paths` | `list[str]` | `None` | Paths to files containing blocked domains |
| `blocklist_domains` | `list[str]` | `None` | List of domains to block directly |
| `word_weights` | `dict[str, float]` | `None` | Dict mapping words to severity weights (0-1) |
| `use_default_words` | `bool` | `True` | Include default adult/spam word list |
| `score_threshold` | `float` | `0.5` | URL score threshold for filtering (0-1) |
| `check_subdomains` | `bool` | `True` | Check if URL domain is subdomain of blocked domain |
| `exclude_quality_sources` | `bool` | `False` | Exclude high-quality source domains |
| `quality_source_domains` | `list[str]` | `None` | Additional quality source domains |
| `use_default_quality_sources` | `bool` | `True` | Use default quality source list |

## Filtering Logic

A URL is **filtered out** if any of the following conditions are met:

1. Domain is in the blocklist
2. URL score >= threshold (based on word weights)
3. Domain is a high-quality source (when `exclude_quality_sources=True`)

## Default Word Weights

Words are assigned severity weights from 0 to 1 (higher = more severe):

| Category | Words | Weight |
|----------|-------|--------|
| Adult | porn, xxx, nsfw, hentai | 1.0 |
| Adult | nude, naked, erotic, fetish | 0.9 |
| Adult | sex, escort | 0.8 |
| Gambling | casino, gambling | 0.9 |
| Gambling | betting, jackpot | 0.7-0.8 |
| Violence/Illegal | gore, warez | 0.9 |
| Spam | free-money, get-rich | 0.8 |

## Default Quality Sources (G.1.3)

When `exclude_quality_sources=True`, these domains are filtered to prevent overlap with curated corpora:

- **Knowledge**: wikipedia.org, wikidata.org, wikimedia.org
- **Academic**: arxiv.org, pubmed.gov, scholar.google.com, nature.com
- **Code**: github.com, gitlab.com, stackoverflow.com
- **Books**: gutenberg.org, archive.org

## Usage

### Basic Usage

```yaml
stages:
  - name: content_filtering
    operators:
      - name: url_filter
        params:
          score_threshold: 0.5
```

### With Quality Source Exclusion

```yaml
- name: url_filter
  params:
    score_threshold: 0.5
    exclude_quality_sources: true  # Exclude Wikipedia, arXiv, GitHub, etc.
```

### Custom Blocklist

```yaml
- name: url_filter
  params:
    blocklist_paths:
      - "/path/to/custom_blocklist.txt"
    blocklist_domains:
      - "spam-domain.com"
      - "malware-site.net"
```

### Custom Word Weights

```yaml
- name: url_filter
  params:
    word_weights:
      "custom-bad-word": 0.9
      "another-word": 0.7
    use_default_words: true  # Also include defaults
```

## Performance

- **Throughput**: ~20,000 records/sec
- **Memory**: Minimal (regex pattern + domain sets)

## Reference

- [RefinedWeb Paper](https://arxiv.org/pdf/2306.01116) - Section G.1: URL Filtering
