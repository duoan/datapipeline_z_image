"""Symbol ratio filter."""

from typing import Any

from mega_data_factory.framework import Filter

FIELD_TEXT = "text"
SYMBOLS = ("#", "...", ". . .", "…")


class TextSymbolRatioFilter(Filter):
    """Filter by number of symbols relative to word count."""

    def __init__(
        self,
        text_field: str = FIELD_TEXT,
        max_symbol_to_word_ratio: float = float("inf"),
    ):
        super().__init__()
        self.text_field = text_field
        self.max_symbol_to_word_ratio = max_symbol_to_word_ratio

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
            text = self._get_text(record)
            num_symbols = sum(text.count(symbol) for symbol in SYMBOLS)
            num_words = len(text.replace(". . .", "...").split())
            symbol_to_word_ratio = num_symbols / max(num_words, 1)
            results.append(symbol_to_word_ratio <= self.max_symbol_to_word_ratio)
        return results
