# LLMResponseParserRefiner

Post-processes LLM responses by extracting structured data, validating schemas, and mapping fields into top-level record columns. Designed to chain after `LLMOnlineSynthesisRefiner` or `LLMOfflineSynthesisRefiner` in the same pipeline stage.

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input_field` | str | `"llm_response"` | Record field containing the raw LLM response |
| `parse_mode` | str | `"json"` | Parsing strategy: `"json"`, `"regex"`, or `"jmespath"` |
| `field_mapping` | dict | `{}` | Maps output field names to dot-paths into parsed JSON (json mode) |
| `required_fields` | list[str] | `None` | Dot-paths that must exist in parsed JSON (json mode) |
| `field_types` | dict | `None` | Dot-path to expected type for validation: `str`, `int`, `float`, `bool`, `list`, `dict` |
| `parsed_json_field` | str | `None` | If set, stores full parsed JSON as a string in this field |
| `regex_pattern` | str | `None` | Regex with named groups (regex mode) |
| `jmespath_expressions` | dict | `None` | Maps output field names to JMESPath expressions (jmespath mode) |
| `validation_error_field` | str | `"llm_parse_error"` | Field for validation/parse error messages |
| `default_value` | any | `None` | Default value for fields that couldn't be extracted |

## Output Fields

Depends on the parse mode and configuration. Always includes:

| Field | Type | Description |
|-------|------|-------------|
| `llm_parse_error` | string | Parse/validation errors (empty string = success) |

Plus all fields defined in `field_mapping` (json mode), named regex groups (regex mode), or `jmespath_expressions` (jmespath mode).

## Parse Modes

### 1. JSON Mode

Extracts JSON from LLM response text, validates against a schema, and maps nested fields to top-level record fields.

Handles common LLM output patterns:

- Markdown-fenced JSON: `` ```json { ... } ``` ``
- Raw JSON objects: `{ ... }`
- JSON arrays: `[ ... ]`
- JSON mixed with surrounding text

```yaml
- name: llm_response_parser_refiner
  params:
    input_field: llm_response
    parse_mode: json
    field_mapping:
      answer: "result.answer"          # dot-path for nested access
      confidence: "result.confidence"
      first_tag: "metadata.tags.0"     # array index access
    required_fields:
      - "result.answer"
      - "result.confidence"
    field_types:
      result.answer: str
      result.confidence: float
    parsed_json_field: llm_parsed      # optional: keep full JSON
```

### 2. Regex Mode

Applies a regex with named capture groups to the raw response text. Each named group becomes a record field.

```yaml
- name: llm_response_parser_refiner
  params:
    input_field: llm_response
    parse_mode: regex
    regex_pattern: |
      Answer:\s*(?P<answer>.+?)\n.*?Score:\s*(?P<score>\d+(?:\.\d+)?)
```

This extracts `answer` and `score` fields from responses like:

```text
Answer: The capital of France is Paris.
Score: 0.95
```

### 3. JMESPath Mode

Parses the response as JSON, then applies [JMESPath](https://jmespath.org/) expressions for complex queries. Requires the `jmespath` package.

```yaml
- name: llm_response_parser_refiner
  params:
    input_field: llm_response
    parse_mode: jmespath
    jmespath_expressions:
      all_names: "items[*].name"
      top_score: "max_by(results, &score).score"
      filtered: "items[?category=='A'].name"
```

## Usage

```python
from mega_data_factory.operators.refiners.llm_synthesis import LLMResponseParserRefiner

parser = LLMResponseParserRefiner(
    input_field="llm_response",
    parse_mode="json",
    field_mapping={"answer": "answer", "score": "score"},
    required_fields=["answer"],
)
parser.refine_batch(records)

# Each record now has: answer, score, llm_parse_error
```

## Pipeline Config

### Typical: Synthesis + Parse + Filter

```yaml
stages:
  - name: synthesis_stage
    operators:
      # Step 1: Call LLM
      - name: llm_online_synthesis_refiner
        params:
          provider: openai
          model: gpt-4o-mini
          system_prompt: |
            Classify the text and return JSON:
            {"category": "...", "confidence": 0.0-1.0, "reasoning": "..."}
          prompt_template: "Classify this text: {text}"
          accounts:
            - api_key: "${OPENAI_API_KEY}"

      # Step 2: Parse structured output
      - name: llm_response_parser_refiner
        params:
          input_field: llm_response
          parse_mode: json
          field_mapping:
            category: "category"
            confidence: "confidence"
            reasoning: "reasoning"
          required_fields: ["category", "confidence"]
          field_types:
            category: str
            confidence: float

  # Step 3 (optional): Filter out parse failures
  - name: quality_filter_stage
    operators:
      - name: range_filter
        params:
          field: llm_parse_error
          # ... filter records where llm_parse_error is non-empty
```

### Regex extraction from free-text response

```yaml
operators:
  - name: llm_online_synthesis_refiner
    params:
      provider: anthropic
      model: claude-sonnet-4-20250514
      system_prompt: |
        Evaluate the text quality.
        Format your response as:
        Quality: <high|medium|low>
        Score: <0-100>
        Explanation: <your explanation>
      prompt_field: prompt
      accounts:
        - api_key: "${ANTHROPIC_API_KEY}"

  - name: llm_response_parser_refiner
    params:
      input_field: llm_response
      parse_mode: regex
      regex_pattern: 'Quality:\s*(?P<quality>\w+)\s*\nScore:\s*(?P<score>\d+)\s*\nExplanation:\s*(?P<explanation>.+)'
```

## Error Handling

The `validation_error_field` (default: `llm_parse_error`) captures all parse and validation errors:

| Error | Meaning |
|-------|---------|
| `""` (empty) | Success — all fields extracted and validated |
| `"empty_input"` | Input field was empty or missing |
| `"json_parse_failed"` | Could not extract valid JSON from response |
| `"regex_no_match"` | Regex did not match the response |
| `"missing required field: X"` | Required field not found in parsed JSON |
| `"field 'X': expected Y, got Z"` | Field type validation failed |

Records with errors are **not** filtered out — they pass through with error details and `default_value` for missing fields. Use a downstream Filter operator to remove them if needed.
