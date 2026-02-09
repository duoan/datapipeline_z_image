"""
Text New Line Removal Refiner

Normalizes text by limiting the number of consecutive newline characters.
"""

import re
from typing import Any

import pyarrow as pa

from mega_data_factory.framework import Refiner

FIELD_TEXT = "text"


class TextNewLineRemovalRefiner(Refiner):
    """Refiner that caps consecutive newlines in a text field.

    This refiner modifies `text_field` in-place and does not add new fields.
    """

    def __init__(self, text_field: str = FIELD_TEXT, max_consecutive: int = 2):
        """Initialize newline normalization refiner.

        Args:
            text_field: Name of the text field to normalize.
            max_consecutive: Maximum allowed consecutive newline characters.
        """
        super().__init__()
        if max_consecutive < 0:
            raise ValueError(f"max_consecutive must be >= 0, got {max_consecutive}")

        self.text_field = text_field
        self.max_consecutive = max_consecutive
        self._pattern = re.compile(rf"\n{{{max_consecutive + 1},}}")
        self._replacement = "\n" * max_consecutive

    def refine_batch(self, records: list[dict[str, Any]]) -> None:
        """Normalize newlines for a batch of records (in-place)."""
        for record in records:
            text = record.get(self.text_field)
            if not isinstance(text, str):
                continue
            record[self.text_field] = self._pattern.sub(self._replacement, text)

    def get_output_schema(self) -> dict[str, pa.DataType]:
        """Return output schema for fields added by this refiner.

        This refiner updates an existing field in-place and adds no new fields.
        """
        return {}
