"""Average word length filter."""

from typing import Any

from mega_data_factory.framework import Filter

FIELD_TEXT = "text"


class TextAvgWordLengthFilter(Filter):
    """Filter by average word length."""

    def __init__(
        self,
        text_field: str = FIELD_TEXT,
        lower_bound: float = 0.0,
        upper_bound: float = float("inf"),
    ):
        super().__init__()
        self.text_field = text_field
        self.lower_bound = lower_bound
        self.upper_bound = upper_bound

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
            word_lens = [len(word) for word in self._get_text(record).split()]
            if not word_lens:
                results.append(False)
                continue
            avg_word_len = sum(word_lens) / len(word_lens)
            results.append(self.lower_bound <= avg_word_len <= self.upper_bound)
        return results
