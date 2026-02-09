"""Ellipsis line ratio filter."""

from typing import Any

from mega_data_factory.framework import Filter

FIELD_TEXT = "text"
ELLIPSIS_SUFFIXES = ("...", ". . .", "…")


class TextEllipsisLineRatioFilter(Filter):
    """Filter by fraction of non-empty lines ending with ellipsis."""

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
            lines = [line for line in self._get_text(record).splitlines() if line]
            ellipsis_count = sum(1 for line in lines if line.endswith(ELLIPSIS_SUFFIXES))
            ratio = ellipsis_count / max(len(lines), 1)
            results.append(ratio <= self.max_ratio)
        return results
