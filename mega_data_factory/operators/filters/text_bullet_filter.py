"""Bullet line ratio filter."""

from typing import Any

from mega_data_factory.framework import Filter

FIELD_TEXT = "text"
BULLET_PREFIXES = ("●", "•", "*", "-")


class TextBulletFilter(Filter):
    """Filter by fraction of lines that start with bullet markers."""

    def __init__(self, text_field: str = FIELD_TEXT, max_bullet_ratio: float = float("inf")):
        super().__init__()
        self.text_field = text_field
        self.max_bullet_ratio = max_bullet_ratio

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
            lines = self._get_text(record).split("\n")
            if not lines:
                results.append(True)
                continue
            bullet_count = sum(1 for line in lines if line.startswith(BULLET_PREFIXES))
            ratio = bullet_count / len(lines)
            results.append(ratio <= self.max_bullet_ratio)
        return results
