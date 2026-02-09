"""Alphabetic word ratio filter."""

from typing import Any

from mega_data_factory.framework import Filter

FIELD_TEXT = "text"


class TextAlphabeticWordRationFilter(Filter):
    """Filter by fraction of words that do not contain alphabetic characters."""

    def __init__(self, text_field: str = FIELD_TEXT, max_ratio: float = float("inf")):
        super().__init__()
        self.text_field = text_field
        self.max_ratio = max_ratio

    def _get_text(self, record: dict[str, Any]) -> str:
        value = record.get(self.text_field)
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="ignore")
        if isinstance(value, str):
            return value
        return str(value)

    def should_keep_batch(self, records: list[dict[str, Any]]) -> list[bool]:
        results: list[bool] = []
        for record in records:
            words = self._get_text(record).split()
            if len(words) == 1:
                results.append(False)
                continue
            if not words:
                results.append(True)
                continue

            non_alpha_words = sum(1 for word in words if not any(ch.isalpha() for ch in word))
            ratio = non_alpha_words / len(words)
            results.append(ratio <= self.max_ratio)
        return results
