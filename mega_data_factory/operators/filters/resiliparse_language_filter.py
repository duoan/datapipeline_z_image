"""Resiliparse Fast Language Detection Filter.

Filters records based on fast language detection using Resiliparse's
out-of-place measure. This is 3-5x faster than FastText and 60x faster
than langid, making it suitable for pre-filtering large datasets.

Supports 101 languages.
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from mega_data_factory.framework import Filter
from mega_data_factory.utils.resiliparse_utils import (
    MIN_TEXT_LENGTH_FOR_DETECTION,
    UNKNOWN_LANGUAGE,
    UNKNOWN_LANGUAGE_SCORE,
    detect_language_fast,
    get_text_from_record,
)

FIELD_TEXT = "text"
FIELD_LANGUAGE = "language"
FIELD_LANGUAGE_SCORE = "language_oop_score"


class ResiliparseLanguageFilter(Filter):
    """Fast language detection filter using Resiliparse.

    This filter uses Resiliparse's fast language detection based on
    out-of-place (OOP) measure. It's much faster than FastText (3-5x)
    and langid (60x), making it ideal for pre-filtering large datasets
    before more expensive processing.

    The OOP rank indicates how far the text is from the closest-matching
    language profile. Higher values mean less accurate detection.
    Values above 1200 are usually false results.

    Supports 101 languages using ISO 639-1 codes: en, zh, de, fr, es,
    ja, ko, ru, ar, pt, it, and many more.

    Example YAML configuration:
        - name: resiliparse_language_filter
          params:
            target_languages: ["en"]  # Keep only English documents (use 2-letter codes)
            max_oop_rank: 1200        # Maximum OOP rank threshold
            add_language_column: true # Add detected language to output
            add_score_column: true    # Add OOP rank to output
    """

    # Common language code mappings (Resiliparse detect_fast returns 2-letter codes)
    # Map full names TO 2-letter codes for normalization
    LANGUAGE_ALIASES = {
        # Full name -> 2-letter code
        "english": "en",
        "chinese": "zh",
        "german": "de",
        "french": "fr",
        "spanish": "es",
        "japanese": "ja",
        "korean": "ko",
        "russian": "ru",
        "arabic": "ar",
        "portuguese": "pt",
        "italian": "it",
    }

    def __init__(
        self,
        target_languages: list[str] | str | None = None,
        max_oop_rank: int = 1200,
        text_field: str = FIELD_TEXT,
        language_field: str = FIELD_LANGUAGE,
        language_score_field: str = FIELD_LANGUAGE_SCORE,
        add_language_column: bool = True,
        add_score_column: bool = True,
        min_text_length: int = 50,
    ):
        """Initialize the Resiliparse language filter.

        Args:
            target_languages: Target language(s) to keep. Use 2-letter ISO 639-1
                codes (e.g., "en", "zh", "de") or full names (e.g., "English").
                Can be a single language or a list (e.g., ["en", "fr"]).
                If None, all languages are accepted (only OOP rank threshold applies).
            max_oop_rank: Maximum OOP rank threshold. Documents with ranks
                above this are filtered out. Default: 1200 (values above
                this are usually false results).
            text_field: Name of the text field to analyze. Default: "text"
            language_field: Name of the output field for detected language.
                Default: "language"
            language_score_field: Name of the output field for OOP rank.
                Default: "language_oop_score"
            add_language_column: If True, add detected language to output.
                Default: True
            add_score_column: If True, add OOP rank to output. Default: True
            min_text_length: Minimum text length for language detection.
                Texts shorter than this are always filtered out. Default: 50
        """
        super().__init__()

        # Normalize target_languages to a set of 2-letter language codes
        if target_languages is None:
            self.target_languages: set[str] | None = None
        elif isinstance(target_languages, str):
            self.target_languages = {self._normalize_language(target_languages)}
        else:
            self.target_languages = {self._normalize_language(lang) for lang in target_languages}

        self.max_oop_rank = max_oop_rank
        self.text_field = text_field
        self.language_field = language_field
        self.language_score_field = language_score_field
        self.add_language_column = add_language_column
        self.add_score_column = add_score_column
        self.min_text_length = min_text_length

    def _normalize_language(self, lang: str) -> str:
        """Normalize language code or name to 2-letter ISO 639-1 code.

        Resiliparse's detect_fast() returns 2-letter codes like "en", "zh", etc.
        This method normalizes user input to match that format.

        Args:
            lang: Language code or name (e.g., "en", "English", "EN")

        Returns:
            2-letter language code (e.g., "en")
        """
        lang_lower = lang.lower().strip()

        # Already a 2-letter code, return as-is
        if len(lang_lower) == 2:
            return lang_lower

        # Map full name to 2-letter code
        return self.LANGUAGE_ALIASES.get(lang_lower, lang_lower)

    def _get_text(self, record: dict[str, Any]) -> str:
        """Extract text from a record using shared utility."""
        return get_text_from_record(record, self.text_field)

    def should_keep_batch(self, records: list[dict[str, Any]]) -> list[bool]:
        """Determine which records should be kept based on language detection.

        Args:
            records: List of input records.

        Returns:
            List of boolean flags indicating which records to keep.
        """
        if not records:
            return []

        results: list[bool] = []

        for record in records:
            text = self._get_text(record)

            # Filter out short texts
            if len(text) < self.min_text_length:
                if self.add_language_column:
                    record[self.language_field] = UNKNOWN_LANGUAGE
                if self.add_score_column:
                    record[self.language_score_field] = UNKNOWN_LANGUAGE_SCORE
                results.append(False)
                continue

            # Detect language
            language, oop_rank = detect_language_fast(text, cutoff=self.max_oop_rank)

            # Add language and score columns if configured
            if self.add_language_column:
                record[self.language_field] = language
            if self.add_score_column:
                record[self.language_score_field] = oop_rank

            # Check if record should be kept
            keep = True

            # Check OOP rank threshold
            if oop_rank > self.max_oop_rank:
                keep = False

            # Check target language if specified
            if keep and self.target_languages is not None:
                if language not in self.target_languages and language != UNKNOWN_LANGUAGE:
                    keep = False

            results.append(keep)

        return results

    def get_output_schema(self) -> dict[str, pa.DataType]:
        """Return output schema for new fields added by this filter.

        Returns:
            Dictionary mapping field names to Arrow data types.
        """
        schema: dict[str, pa.DataType] = {}
        if self.add_language_column:
            schema[self.language_field] = pa.string()
        if self.add_score_column:
            schema[self.language_score_field] = pa.int64()
        return schema
