"""
Text Target Language Filter

Filters records based on language detection using FastText language classifier from CCNet.
Removes documents for which the top language scores below a configurable threshold (default: 0.65).
Optionally adds the top language and score as additional columns in the result.

Uses https://huggingface.co/facebook/fasttext-language-identification
"""

import logging
import re
from typing import Any

import pyarrow as pa

from mega_data_factory.framework import Filter

logger = logging.getLogger(__name__)

# Default field names
FIELD_TEXT = "text"
FIELD_LANGUAGE = "language"
FIELD_LANGUAGE_SCORE = "language_score"

# Lazy-loaded model
_fasttext_model = None


def _get_fasttext_model():
    """Lazy load the FastText language identification model.

    Returns:
        The loaded FastText model.

    Raises:
        ImportError: If fasttext or huggingface_hub is not installed.
    """
    global _fasttext_model
    if _fasttext_model is None:
        try:
            import fasttext
            from huggingface_hub import hf_hub_download
        except ImportError as e:
            raise ImportError(
                "TextTargetLanguageFilter requires fasttext and huggingface_hub. "
                "Install with: pip install fasttext huggingface_hub"
            ) from e

        logger.info("Downloading FastText language identification model...")
        model_path = hf_hub_download(repo_id="facebook/fasttext-language-identification", filename="model.bin")
        logger.info(f"Loading FastText model from {model_path}")
        _fasttext_model = fasttext.load_model(model_path)
        logger.info("FastText model loaded successfully")

    return _fasttext_model


def _preprocess_text(text: str) -> str:
    """Preprocess text for language detection.

    FastText expects single-line input, so we replace newlines with spaces
    and normalize whitespace.

    Args:
        text: Input text to preprocess.

    Returns:
        Preprocessed text suitable for FastText prediction.
    """
    # Replace newlines and tabs with spaces
    text = re.sub(r"[\n\r\t]+", " ", text)
    # Normalize multiple spaces to single space
    text = re.sub(r"\s+", " ", text)
    # Strip leading/trailing whitespace
    return text.strip()


def _parse_language_label(label: str) -> str:
    """Parse FastText language label to extract language code.

    FastText returns labels like '__label__eng_Latn' or '__label__zho_Hans'.
    We extract just the language code (e.g., 'eng', 'zho').

    Args:
        label: FastText label string.

    Returns:
        Language code (e.g., 'eng', 'zho', 'fra').
    """
    # Remove '__label__' prefix
    if label.startswith("__label__"):
        label = label[9:]
    # Extract language code (before underscore if present)
    if "_" in label:
        return label.split("_")[0]
    return label


class TextTargetLanguageFilter(Filter):
    """Filter records based on language detection using FastText.

    This filter uses the FastText language identification model from CCNet
    to detect the language of text documents. Documents are filtered based on:
    1. Whether the detected language matches the target language(s)
    2. Whether the language detection confidence score meets the threshold

    The filter can optionally add the detected language and score as new columns.

    Example YAML configuration:
        - type: TextTargetLanguageFilter
          params:
            target_languages: ["eng"]  # Keep only English documents
            min_score: 0.65            # Minimum confidence threshold
            add_language_column: true  # Add detected language to output
            add_score_column: true     # Add confidence score to output
    """

    def __init__(
        self,
        target_languages: list[str] | str | None = None,
        min_score: float = 0.65,
        text_field: str = FIELD_TEXT,
        language_field: str = FIELD_LANGUAGE,
        language_score_field: str = FIELD_LANGUAGE_SCORE,
        add_language_column: bool = True,
        add_score_column: bool = True,
    ):
        """Initialize text target language filter.

        Args:
            target_languages: Target language code(s) to keep. Can be a single
                language code (e.g., "eng") or a list of codes (e.g., ["eng", "fra"]).
                If None, all languages are accepted (only score threshold applies).
                Common codes: eng (English), zho (Chinese), fra (French), deu (German),
                spa (Spanish), jpn (Japanese), kor (Korean), rus (Russian).
            min_score: Minimum language detection confidence score (0.0 to 1.0).
                Documents with scores below this threshold are filtered out.
                Default: 0.65 (as recommended by CCNet).
            text_field: Name of the text field to analyze. Default: "text"
            language_field: Name of the output field for detected language.
                Default: "language"
            language_score_field: Name of the output field for confidence score.
                Default: "language_score"
            add_language_column: If True, add detected language to output records.
                Default: True
            add_score_column: If True, add confidence score to output records.
                Default: True
        """
        super().__init__()
        # Normalize target_languages to a set
        if target_languages is None:
            self.target_languages: set[str] | None = None
        elif isinstance(target_languages, str):
            self.target_languages = {target_languages.lower()}
        else:
            self.target_languages = {lang.lower() for lang in target_languages}

        self.min_score = min_score
        self.text_field = text_field
        self.language_field = language_field
        self.language_score_field = language_score_field
        self.add_language_column = add_language_column
        self.add_score_column = add_score_column

        # Model will be loaded lazily on first use
        self._model = None

    def _get_model(self):
        """Get the FastText model, loading it if necessary."""
        if self._model is None:
            self._model = _get_fasttext_model()
        return self._model

    def _get_text(self, record: dict[str, Any]) -> str:
        """Extract and preprocess text from a record.

        Args:
            record: Input record dictionary.

        Returns:
            Preprocessed text string.
        """
        text = record.get(self.text_field)
        if text is None:
            return ""
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="ignore")
        elif not isinstance(text, str):
            text = str(text)
        return _preprocess_text(text)

    def _predict_language(self, text: str) -> tuple[str, float]:
        """Predict the language of a text.

        Args:
            text: Preprocessed text to analyze.

        Returns:
            Tuple of (language_code, confidence_score).
            Returns ("unknown", 0.0) for empty text.
        """
        if not text:
            return ("unknown", 0.0)

        model = self._get_model()
        # Get top-1 prediction
        labels, scores = model.predict(text, k=1)

        if not labels or not scores:
            return ("unknown", 0.0)

        language = _parse_language_label(labels[0])
        score = float(scores[0])

        return (language, score)

    def should_keep_batch(self, records: list[dict[str, Any]]) -> list[bool]:
        """Determine which records should be kept based on language detection.

        This method also enriches records with language and score columns
        if configured to do so.

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
            language, score = self._predict_language(text)

            # Add language and score columns if configured
            if self.add_language_column:
                record[self.language_field] = language
            if self.add_score_column:
                record[self.language_score_field] = score

            # Check if record should be kept
            keep = True

            # Check score threshold
            if score < self.min_score:
                keep = False

            # Check target language if specified
            if keep and self.target_languages is not None:
                if language.lower() not in self.target_languages:
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
            schema[self.language_score_field] = pa.float32()
        return schema
