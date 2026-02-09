"""
Text Length Filter

Filters records based on text length criteria.
"""

from typing import Any

from mega_data_factory.framework import Filter

FIELD_TEXT_LENGTH = "text_length"
FIELD_TEXT = "text"
SUPPORTED_LENGTH_TYPES = {"char", "word", "sentence", "line", "paragraph"}

# Try to load Rust backend (optional acceleration)
RUST_TEXT_LENGTH_AVAILABLE = False
_length_keep_batch_rust = None

try:
    from mega_data_factory import rust_operators as _rust_module  # type: ignore

    _length_keep_batch_rust = getattr(_rust_module, "text_length_keep_batch", None)
    if _length_keep_batch_rust is not None:
        RUST_TEXT_LENGTH_AVAILABLE = True
except ImportError:
    pass


class TextLengthFilter(Filter):
    """Filter records based on text length.

    Supports multiple length types:
    - char
    - word
    - sentence
    - line
    - paragraph

    For backward compatibility:
    - min_length/max_length remain supported
    - lower_bound/upper_bound can be used as aliases
    - char mode keeps prior behavior by default (ignore_punctuation=False)
    - text_length_field is used only for char mode optimization when punctuation is not ignored
    """

    def __init__(
        self,
        min_length: int = 0,
        max_length: int | None = None,
        text_field: str = FIELD_TEXT,
        text_length_field: str = FIELD_TEXT_LENGTH,
        length_type: str = "char",
        lower_bound: int | None = None,
        upper_bound: int | None = None,
        ignore_punctuation: bool = False,
    ):
        """Initialize text length filter.

        Args:
            min_length: Minimum text length (inclusive). Default: 0
            max_length: Maximum text length (inclusive). None means no upper limit.
            text_field: Name of the text field to calculate length from.
            text_length_field: Name of the pre-computed text length field (char mode only).
            length_type: Length type, one of {char, word, sentence, line, paragraph}.
            lower_bound: Alias for min_length (takes precedence when set).
            upper_bound: Alias for max_length (takes precedence when set).
            ignore_punctuation: If True, punctuation is excluded in char/word counting.
        """
        super().__init__()
        if length_type not in SUPPORTED_LENGTH_TYPES:
            raise ValueError(f"length_type must be one of {sorted(SUPPORTED_LENGTH_TYPES)}, got '{length_type}'")

        self.min_length = lower_bound if lower_bound is not None else min_length
        self.max_length = upper_bound if upper_bound is not None else max_length
        self.text_field = text_field
        self.text_length_field = text_length_field
        self.length_type = length_type
        self.ignore_punctuation = ignore_punctuation

    def _get_text(self, record: dict[str, Any]) -> str:
        text = record.get(self.text_field)
        if text is None:
            return ""
        if isinstance(text, bytes):
            return text.decode("utf-8", errors="ignore")
        if isinstance(text, str):
            return text
        return str(text)

    def _keep_by_length(self, length: int) -> bool:
        keep = length >= self.min_length
        if self.max_length is not None:
            keep = keep and length <= self.max_length
        return keep

    def should_keep_batch(self, records: list[dict[str, Any]]) -> list[bool]:
        """Determine which records meet text length criteria."""
        if not records:
            return []

        if not (RUST_TEXT_LENGTH_AVAILABLE and _length_keep_batch_rust):
            raise RuntimeError("TextLengthFilter requires Rust backend: mega_data_factory.rust_operators.text_length_keep_batch")

        # Keep O(1) pre-computed char-length optimization in Python for compatibility.
        if self.length_type == "char" and not self.ignore_punctuation:
            results: list[bool | None] = [None] * len(records)
            rust_texts: list[str] = []
            rust_indices: list[int] = []

            for idx, record in enumerate(records):
                if self.text_length_field in record and isinstance(record[self.text_length_field], (int, float)):
                    results[idx] = self._keep_by_length(int(record[self.text_length_field]))
                else:
                    rust_indices.append(idx)
                    rust_texts.append(self._get_text(record))

            if rust_texts:
                rust_results = list(
                    _length_keep_batch_rust(
                        rust_texts,
                        self.min_length,
                        self.max_length,
                        self.length_type,
                        self.ignore_punctuation,
                    )
                )
                for idx, keep in zip(rust_indices, rust_results, strict=False):
                    results[idx] = bool(keep)

            return [bool(v) for v in results]

        texts = [self._get_text(record) for record in records]
        return list(
            _length_keep_batch_rust(
                texts,
                self.min_length,
                self.max_length,
                self.length_type,
                self.ignore_punctuation,
            )
        )
