"""
LLM Response Parser Refiner

Post-processes LLM responses by extracting structured data, validating schemas,
and mapping fields. Designed to chain after LLMOnline/OfflineSynthesisRefiner
in the same pipeline stage.

Supports three parse modes:
  - json:  Extract JSON from response (handles markdown code blocks), validate
           against a schema, and map nested fields to top-level record fields.
  - regex: Extract named groups from response using a regex pattern.
  - jmespath: Query JSON responses with JMESPath expressions (requires jmespath pkg).
"""

import json
import logging
import re
from typing import Any

import pyarrow as pa

from mega_data_factory.framework import Refiner

logger = logging.getLogger(__name__)

# Matches ```json ... ``` or ``` ... ``` fenced code blocks
_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n?(.*?)```",
    re.DOTALL,
)


def _extract_json(text: str) -> Any:
    """Best-effort JSON extraction from LLM response text.

    Tries in order:
      1. Fenced code block (```json ... ``` or ``` ... ```)
      2. First { ... } or [ ... ] substring
      3. Raw text as JSON
    """
    # Try fenced code blocks first
    for match in _JSON_FENCE_RE.finditer(text):
        candidate = match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    # Try to find raw JSON object/array
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    # Last resort: try the whole text
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def _resolve_path(obj: Any, path: str) -> Any:
    """Resolve a dot-separated path into a nested dict/list.

    Examples:
        _resolve_path({"a": {"b": 1}}, "a.b") -> 1
        _resolve_path({"items": [{"x": 1}]}, "items.0.x") -> 1
    """
    for key in path.split("."):
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, (list, tuple)):
            try:
                obj = obj[int(key)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return obj


def _validate_schema(
    data: Any,
    required_fields: list[str] | None = None,
    field_types: dict[str, str] | None = None,
) -> list[str]:
    """Validate extracted data against a simple schema.

    Returns a list of validation error messages (empty = valid).
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        errors.append(f"expected dict, got {type(data).__name__}")
        return errors

    if required_fields:
        for field in required_fields:
            if _resolve_path(data, field) is None:
                errors.append(f"missing required field: {field}")

    type_map = {"str": str, "int": int, "float": (int, float), "bool": bool, "list": list, "dict": dict}
    if field_types:
        for field, expected_type_name in field_types.items():
            value = _resolve_path(data, field)
            if value is None:
                continue
            expected = type_map.get(expected_type_name)
            if expected and not isinstance(value, expected):
                errors.append(f"field '{field}': expected {expected_type_name}, got {type(value).__name__}")

    return errors


class LLMResponseParserRefiner(Refiner):
    """Post-processor that extracts structured data from LLM responses.

    Chain this after an LLM synthesis refiner to parse, validate, and flatten
    the raw response into structured record fields.

    Parse modes:
        - **json**: Extracts JSON from the response text (handles markdown
          fences), validates against a schema, and maps nested fields to
          top-level record fields via field_mapping.
        - **regex**: Applies a regex with named groups to the response text,
          each named group becomes a record field.
        - **jmespath**: Parses the response as JSON, then applies JMESPath
          expression(s) to extract fields (requires ``jmespath`` package).

    Config example (YAML)::

        - name: llm_response_parser_refiner
          params:
            input_field: llm_response
            parse_mode: json
            field_mapping:
              answer: "result.answer"
              confidence: "result.confidence"
              tags: "metadata.tags"
            required_fields: ["result.answer"]
            field_types:
              result.answer: str
              result.confidence: float
            parsed_json_field: llm_parsed   # optional: store full parsed JSON
            validation_error_field: llm_parse_error
    """

    def __init__(
        self,
        # Input
        input_field: str = "llm_response",
        # Parse mode
        parse_mode: str = "json",
        # JSON mode options
        field_mapping: dict[str, str] | None = None,
        required_fields: list[str] | None = None,
        field_types: dict[str, str] | None = None,
        parsed_json_field: str | None = None,
        # Regex mode options
        regex_pattern: str | None = None,
        # JMESPath mode options
        jmespath_expressions: dict[str, str] | None = None,
        # Output
        validation_error_field: str = "llm_parse_error",
        # Defaults for missing extractions
        default_value: Any = None,
    ):
        """Initialize the response parser.

        Args:
            input_field: Record field containing the raw LLM response to parse.
            parse_mode: Parsing strategy ("json", "regex", or "jmespath").
            field_mapping: Maps output field names to dot-paths into the parsed JSON.
                Example: {"answer": "result.answer", "score": "result.score"}
            required_fields: Dot-paths that must exist in the parsed JSON (json mode).
            field_types: Dot-path -> expected type name for validation.
                Supported types: "str", "int", "float", "bool", "list", "dict".
            parsed_json_field: If set, stores the full parsed JSON object as a
                JSON string in this field.
            regex_pattern: Regex with named groups for regex mode.
                Example: r"Answer: (?P<answer>.+?)\\nScore: (?P<score>\\d+)"
            jmespath_expressions: Maps output field names to JMESPath expressions.
                Example: {"answer": "result.answer", "tags": "metadata.tags[*].name"}
            validation_error_field: Field to store validation error messages.
            default_value: Default value for fields that couldn't be extracted.
        """
        super().__init__()

        self.input_field = input_field
        self.parse_mode = parse_mode
        self.field_mapping = field_mapping or {}
        self.required_fields = required_fields
        self.field_types = field_types
        self.parsed_json_field = parsed_json_field
        self.regex_pattern = re.compile(regex_pattern, re.DOTALL) if regex_pattern else None
        self.jmespath_expressions = jmespath_expressions or {}
        self.validation_error_field = validation_error_field
        self.default_value = default_value

        if parse_mode == "regex" and self.regex_pattern is None:
            raise ValueError("regex_pattern is required when parse_mode='regex'")
        if parse_mode == "jmespath" and not self.jmespath_expressions:
            raise ValueError("jmespath_expressions is required when parse_mode='jmespath'")

        # Lazy-load jmespath
        self._jmespath = None

    def _parse_json(self, record: dict) -> None:
        """Parse response as JSON, validate, and map fields."""
        text = record.get(self.input_field, "")
        if not text:
            record[self.validation_error_field] = "empty_input"
            return

        parsed = _extract_json(str(text))
        if parsed is None:
            record[self.validation_error_field] = "json_parse_failed"
            for field_name in self.field_mapping:
                record[field_name] = self.default_value
            return

        # Store full parsed JSON if requested
        if self.parsed_json_field:
            record[self.parsed_json_field] = json.dumps(parsed, ensure_ascii=False)

        # Validate schema
        errors = _validate_schema(parsed, self.required_fields, self.field_types)
        record[self.validation_error_field] = "; ".join(errors) if errors else ""

        # Map fields
        for field_name, json_path in self.field_mapping.items():
            value = _resolve_path(parsed, json_path)
            if value is None:
                record[field_name] = self.default_value
            elif isinstance(value, (dict, list)):
                record[field_name] = json.dumps(value, ensure_ascii=False)
            else:
                record[field_name] = value

    def _parse_regex(self, record: dict) -> None:
        """Extract named groups from response using regex."""
        text = record.get(self.input_field, "")
        if not text:
            record[self.validation_error_field] = "empty_input"
            return

        match = self.regex_pattern.search(str(text))
        if match is None:
            record[self.validation_error_field] = "regex_no_match"
            for group_name in self.regex_pattern.groupindex:
                record[group_name] = self.default_value
            return

        record[self.validation_error_field] = ""
        for group_name in self.regex_pattern.groupindex:
            record[group_name] = match.group(group_name)

    def _parse_jmespath(self, record: dict) -> None:
        """Parse response as JSON and apply JMESPath expressions."""
        if self._jmespath is None:
            import jmespath

            self._jmespath = jmespath

        text = record.get(self.input_field, "")
        if not text:
            record[self.validation_error_field] = "empty_input"
            return

        parsed = _extract_json(str(text))
        if parsed is None:
            record[self.validation_error_field] = "json_parse_failed"
            for field_name in self.jmespath_expressions:
                record[field_name] = self.default_value
            return

        record[self.validation_error_field] = ""
        for field_name, expr in self.jmespath_expressions.items():
            try:
                value = self._jmespath.search(expr, parsed)
                if isinstance(value, (dict, list)):
                    record[field_name] = json.dumps(value, ensure_ascii=False)
                else:
                    record[field_name] = value if value is not None else self.default_value
            except Exception as e:
                record[field_name] = self.default_value
                logger.debug("JMESPath error for '%s': %s", expr, e)

    def refine_batch(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return

        handler = {
            "json": self._parse_json,
            "regex": self._parse_regex,
            "jmespath": self._parse_jmespath,
        }.get(self.parse_mode)

        if handler is None:
            raise ValueError(f"Unknown parse_mode '{self.parse_mode}'. Use: json, regex, jmespath")

        for record in records:
            try:
                handler(record)
            except Exception as e:
                logger.error("Parse error: %s", e)
                record[self.validation_error_field] = f"parse_error: {e}"

    def get_output_schema(self) -> dict[str, pa.DataType]:
        schema: dict[str, pa.DataType] = {}

        if self.parse_mode == "json":
            for field_name in self.field_mapping:
                schema[field_name] = pa.string()
        elif self.parse_mode == "regex" and self.regex_pattern:
            for group_name in self.regex_pattern.groupindex:
                schema[group_name] = pa.string()
        elif self.parse_mode == "jmespath":
            for field_name in self.jmespath_expressions:
                schema[field_name] = pa.string()

        if self.parsed_json_field:
            schema[self.parsed_json_field] = pa.large_string()
        schema[self.validation_error_field] = pa.string()

        return schema
