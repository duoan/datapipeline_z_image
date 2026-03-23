"""Resiliparse utilities for HTML text extraction and language detection.

This module provides utility functions wrapping Resiliparse for:
- HTML to plain text extraction with boilerplate removal
- Character encoding detection
- Fast language detection
"""

from __future__ import annotations

from typing import Any, NamedTuple

from resiliparse.extract.html2text import extract_plain_text
from resiliparse.parse.encoding import bytes_to_str, detect_encoding
from resiliparse.parse.lang import detect_fast

# Constants for language detection
UNKNOWN_LANGUAGE = "unknown"
UNKNOWN_LANGUAGE_SCORE = 9999
MIN_TEXT_LENGTH_FOR_DETECTION = 50


class TextExtractionResult(NamedTuple):
    """Result of HTML text extraction."""

    title: str
    text: str
    text_length: int


def extract_text_from_html(
    html: str,
    *,
    main_content: bool = True,
    preserve_formatting: bool | str = True,
    alt_texts: bool = False,
    links: bool = False,
    list_bullets: bool = True,
    form_fields: bool = False,
    noscript: bool = False,
    comments: bool | None = None,
    skip_elements: list[str] | None = None,
) -> TextExtractionResult:
    """Extract plain text from HTML using Resiliparse.

    Args:
        html: HTML content as string
        main_content: Apply heuristics for extracting only "main-content" elements (boilerplate removal)
        preserve_formatting: Preserve basic block-level formatting (use 'minimal_html' for minimal HTML markup)
        alt_texts: Include alt texts from images
        links: Include link URLs in output
        list_bullets: Insert bullets/numbers for list items
        form_fields: Extract form fields and their values
        noscript: Extract contents of <noscript> elements
        comments: Treat comment sections as main content
        skip_elements: List of CSS selectors for elements to skip

    Returns:
        TextExtractionResult with title, text, and text_length
    """
    if not html or len(html) < 50:
        return TextExtractionResult(title="", text="", text_length=0)

    try:
        # Extract text with Resiliparse
        text = extract_plain_text(
            html,
            preserve_formatting=preserve_formatting,
            main_content=main_content,
            list_bullets=list_bullets,
            alt_texts=alt_texts,
            links=links,
            form_fields=form_fields,
            noscript=noscript,
            comments=comments,
            skip_elements=skip_elements,
        )

        if not text:
            return TextExtractionResult(title="", text="", text_length=0)

        # Extract title from HTML (simple regex approach for speed)
        title = _extract_title(html)

        # Clean up text
        text = text.strip()
        text_length = len(text)

        return TextExtractionResult(title=title, text=text, text_length=text_length)

    except Exception:
        return TextExtractionResult(title="", text="", text_length=0)


def _extract_title(html: str) -> str:
    """Extract title from HTML using simple string search.

    Args:
        html: HTML content

    Returns:
        Extracted title or empty string
    """
    # Simple and fast title extraction
    title_start = html.find("<title")
    if title_start == -1:
        return ""

    # Find the closing > of opening tag
    tag_end = html.find(">", title_start)
    if tag_end == -1:
        return ""

    title_end = html.find("</title>", tag_end)
    if title_end == -1:
        return ""

    title = html[tag_end + 1 : title_end].strip()
    # Clean up title (remove extra whitespace)
    title = " ".join(title.split())

    return title[:500]  # Limit title length


def decode_html_content(
    content: bytes,
    charset: str | None = None,
    *,
    fallback_encodings: tuple[str, ...] = ("utf-8", "cp1252"),
) -> str:
    """Decode HTML content with robust encoding handling.

    Args:
        content: Raw HTML bytes
        charset: Known charset (e.g., from HTTP headers)
        fallback_encodings: Fallback encodings to try if primary fails

    Returns:
        Decoded string
    """
    if not content:
        return ""

    # Detect encoding if not provided
    if not charset:
        charset = detect_encoding(content, from_html_meta=True)

    # Decode using Resiliparse's robust decoder
    return bytes_to_str(
        content,
        encoding=charset or "utf-8",
        errors="ignore",
        fallback_encodings=fallback_encodings,
        strip_bom=True,
    )


def detect_language_fast(text: str, cutoff: int = 1200) -> tuple[str, int]:
    """Detect language using fast out-of-place measure.

    This is 3-5x faster than FastText and 60x faster than langid.

    Args:
        text: Text to analyze
        cutoff: OOP rank cutoff (values above this return "unknown")

    Returns:
        Tuple of (language_code, oop_rank)
    """
    if not text or len(text) < 50:
        return ("unknown", 9999)

    return detect_fast(text, cutoff=cutoff)


def get_text_from_record(record: dict[str, Any], field: str = "text") -> str:
    """Extract text from a record dictionary.

    This is a shared utility for language filters to avoid code duplication.

    Args:
        record: Input record dictionary
        field: Name of the text field to extract

    Returns:
        Text string (empty string if not found or invalid)
    """
    text = record.get(field)
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="ignore")
    elif not isinstance(text, str):
        text = str(text)
    return text.strip()
