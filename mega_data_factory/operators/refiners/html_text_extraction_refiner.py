"""HTML Text Extraction Refiner using Resiliparse.

Extracts plain text from HTML content with configurable options including
boilerplate removal and formatting preservation.
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from mega_data_factory.framework import Refiner
from mega_data_factory.utils.resiliparse_utils import extract_text_from_html

FIELD_HTML = "html"
FIELD_TEXT = "text"
FIELD_TITLE = "title"
FIELD_TEXT_LENGTH = "text_length"


class HtmlTextExtractionRefiner(Refiner):
    """Refiner for extracting plain text from HTML using Resiliparse.

    This refiner extracts plain text from HTML content with optional
    boilerplate removal (main content extraction). It's useful for
    re-processing HTML with different extraction settings.

    Features:
    - Main content extraction / boilerplate removal
    - Configurable formatting preservation
    - Title extraction
    - Text length calculation

    Example:
        refiner = HtmlTextExtractionRefiner(
            html_field="html",
            text_field="text",
            title_field="title",
            main_content=True,  # Enable boilerplate removal
        )
    """

    def __init__(
        self,
        html_field: str = FIELD_HTML,
        text_field: str = FIELD_TEXT,
        title_field: str = FIELD_TITLE,
        text_length_field: str = FIELD_TEXT_LENGTH,
        *,
        main_content: bool = True,
        preserve_formatting: bool | str = True,
        alt_texts: bool = False,
        links: bool = False,
        list_bullets: bool = True,
        min_text_length: int = 50,
    ):
        """Initialize the HTML text extraction refiner.

        Args:
            html_field: Source HTML field name
            text_field: Output text field name
            title_field: Output title field name
            text_length_field: Output text length field name
            main_content: Enable boilerplate removal (main content extraction)
            preserve_formatting: Preserve block-level formatting (use 'minimal_html' for minimal HTML)
            alt_texts: Include alt texts from images
            links: Include link URLs in output
            list_bullets: Insert bullets/numbers for list items
            min_text_length: Minimum text length to keep (shorter texts are cleared)
        """
        super().__init__()
        self.html_field = html_field
        self.text_field = text_field
        self.title_field = title_field
        self.text_length_field = text_length_field
        self.main_content = main_content
        self.preserve_formatting = preserve_formatting
        self.alt_texts = alt_texts
        self.links = links
        self.list_bullets = list_bullets
        self.min_text_length = min_text_length

    def refine_batch(self, records: list[dict[str, Any]]) -> None:
        """Extract text from HTML for a batch of records (in-place)."""
        for record in records:
            html = record.get(self.html_field)
            if not isinstance(html, str) or len(html) < 50:
                record[self.text_field] = ""
                record[self.title_field] = ""
                record[self.text_length_field] = 0
                continue

            result = extract_text_from_html(
                html,
                main_content=self.main_content,
                preserve_formatting=self.preserve_formatting,
                alt_texts=self.alt_texts,
                links=self.links,
                list_bullets=self.list_bullets,
            )

            # Filter by minimum text length
            if result.text_length < self.min_text_length:
                record[self.text_field] = ""
                record[self.title_field] = ""
                record[self.text_length_field] = 0
            else:
                record[self.text_field] = result.text
                record[self.title_field] = result.title
                record[self.text_length_field] = result.text_length

    def get_output_schema(self) -> dict[str, pa.DataType]:
        """Return output schema for fields added by this refiner."""
        return {
            self.text_field: pa.string(),
            self.title_field: pa.string(),
            self.text_length_field: pa.int64(),
        }
