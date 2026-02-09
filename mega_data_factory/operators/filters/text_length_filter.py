"""
Text Length Filter

Filters records based on text length criteria.
"""

import unicodedata
from typing import Any

from mega_data_factory.framework import Filter

FIELD_TEXT_LENGTH = "text_length"
FIELD_TEXT = "text"
SUPPORTED_LENGTH_TYPES = {"char", "word", "sentence", "line", "paragraph"}


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

    def _count_words(self, text: str) -> int:
        count = 0
        in_word = False
        for ch in text:
            if ch.isalnum():
                if not in_word:
                    count += 1
                    in_word = True
            elif not self.ignore_punctuation and unicodedata.category(ch).startswith("P"):
                count += 1
                in_word = False
            else:
                in_word = False
        return count

    def _count_sentences(self, text: str) -> int:
        if not text.strip():
            return 0
        return max(1, sum(1 for ch in text if ch in ".!?"))

    def _count_paragraphs(self, text: str) -> int:
        if not text.strip():
            return 0
        return max(1, sum(1 for p in text.split("\n\n") if p.strip()))

    def _calculate_length(self, text: str) -> int:
        if self.length_type == "word":
            return self._count_words(text)
        if self.length_type == "sentence":
            return self._count_sentences(text)
        if self.length_type == "line":
            return len(text.splitlines())
        if self.length_type == "paragraph":
            return self._count_paragraphs(text)

        # char mode
        if self.ignore_punctuation:
            return sum(1 for ch in text if ch.isalnum())
        return len(text)

    def _get_length(self, record: dict[str, Any]) -> int:
        """Get record length based on configured length type."""
        if self.length_type == "char" and not self.ignore_punctuation and self.text_length_field in record:
            length = record[self.text_length_field]
            if isinstance(length, (int, float)):
                return int(length)

        return self._calculate_length(self._get_text(record))

    def should_keep_batch(self, records: list[dict[str, Any]]) -> list[bool]:
        """Determine which records meet text length criteria."""
        results = []
        for record in records:
            length = self._get_length(record)

            keep = length >= self.min_length
            if self.max_length is not None:
                keep = keep and length <= self.max_length

            results.append(keep)
        return results
