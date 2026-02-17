"""Tests for TextTargetLanguageFilter."""

import pytest
from unittest.mock import MagicMock, patch


class TestTextTargetLanguageFilter:
    """Test suite for TextTargetLanguageFilter."""

    @pytest.fixture
    def mock_fasttext_model(self):
        """Create a mock FastText model."""
        mock_model = MagicMock()

        def mock_predict(text, k=1):
            # Simulate language detection based on text content
            if "hello" in text.lower() or "english" in text.lower():
                return (["__label__eng_Latn"], [0.95])
            elif "bonjour" in text.lower() or "français" in text.lower():
                return (["__label__fra_Latn"], [0.92])
            elif "你好" in text or "中文" in text:
                return (["__label__zho_Hans"], [0.88])
            elif "hola" in text.lower() or "español" in text.lower():
                return (["__label__spa_Latn"], [0.90])
            elif "こんにちは" in text:
                return (["__label__jpn_Jpan"], [0.85])
            elif not text.strip():
                return ([], [])
            else:
                # Default to English with low confidence
                return (["__label__eng_Latn"], [0.50])

        mock_model.predict = mock_predict
        return mock_model

    @pytest.fixture
    def filter_with_mock(self, mock_fasttext_model):
        """Create a TextTargetLanguageFilter with mocked model."""
        with patch(
            "mega_data_factory.operators.filters.text_target_language_filter._get_fasttext_model"
        ) as mock_get_model:
            mock_get_model.return_value = mock_fasttext_model
            from mega_data_factory.operators.filters.text_target_language_filter import (
                TextTargetLanguageFilter,
            )

            filter_instance = TextTargetLanguageFilter(
                target_languages=["eng"],
                min_score=0.65,
            )
            # Force model loading
            filter_instance._model = mock_fasttext_model
            yield filter_instance

    def test_filter_english_documents(self, filter_with_mock):
        """Test filtering keeps English documents."""
        records = [
            {"text": "Hello, this is an English document."},
            {"text": "Bonjour, ceci est un document français."},
            {"text": "这是一个中文文档。"},
        ]

        keep_flags = filter_with_mock.should_keep_batch(records)

        assert keep_flags == [True, False, False]
        # Check that language columns were added
        assert records[0]["language"] == "eng"
        assert records[0]["language_score"] == 0.95
        assert records[1]["language"] == "fra"
        assert records[2]["language"] == "zho"

    def test_filter_multiple_target_languages(self, mock_fasttext_model):
        """Test filtering with multiple target languages."""
        with patch(
            "mega_data_factory.operators.filters.text_target_language_filter._get_fasttext_model"
        ) as mock_get_model:
            mock_get_model.return_value = mock_fasttext_model
            from mega_data_factory.operators.filters.text_target_language_filter import (
                TextTargetLanguageFilter,
            )

            filter_instance = TextTargetLanguageFilter(
                target_languages=["eng", "fra"],
                min_score=0.65,
            )
            filter_instance._model = mock_fasttext_model

            records = [
                {"text": "Hello, English text."},
                {"text": "Bonjour, texte français."},
                {"text": "这是中文。"},
            ]

            keep_flags = filter_instance.should_keep_batch(records)

            assert keep_flags == [True, True, False]

    def test_filter_by_score_threshold(self, mock_fasttext_model):
        """Test filtering by confidence score threshold."""
        with patch(
            "mega_data_factory.operators.filters.text_target_language_filter._get_fasttext_model"
        ) as mock_get_model:
            mock_get_model.return_value = mock_fasttext_model
            from mega_data_factory.operators.filters.text_target_language_filter import (
                TextTargetLanguageFilter,
            )

            # High threshold filter
            filter_instance = TextTargetLanguageFilter(
                target_languages=None,  # Accept all languages
                min_score=0.90,
            )
            filter_instance._model = mock_fasttext_model

            records = [
                {"text": "Hello, English text."},  # score 0.95
                {"text": "这是中文。"},  # score 0.88
                {"text": "random gibberish xyz"},  # score 0.50
            ]

            keep_flags = filter_instance.should_keep_batch(records)

            assert keep_flags == [True, False, False]

    def test_filter_no_target_language(self, mock_fasttext_model):
        """Test filtering with no target language (score only)."""
        with patch(
            "mega_data_factory.operators.filters.text_target_language_filter._get_fasttext_model"
        ) as mock_get_model:
            mock_get_model.return_value = mock_fasttext_model
            from mega_data_factory.operators.filters.text_target_language_filter import (
                TextTargetLanguageFilter,
            )

            filter_instance = TextTargetLanguageFilter(
                target_languages=None,
                min_score=0.65,
            )
            filter_instance._model = mock_fasttext_model

            records = [
                {"text": "Hello, English text."},  # eng, 0.95
                {"text": "Bonjour, français."},  # fra, 0.92
                {"text": "这是中文。"},  # zho, 0.88
                {"text": "random xyz"},  # eng, 0.50
            ]

            keep_flags = filter_instance.should_keep_batch(records)

            # All pass except low confidence
            assert keep_flags == [True, True, True, False]

    def test_filter_empty_text(self, filter_with_mock):
        """Test handling of empty text."""
        records = [
            {"text": ""},
            {"text": None},
            {"text": "Hello, English text."},
        ]

        keep_flags = filter_with_mock.should_keep_batch(records)

        # Empty text gets score 0.0, which is below threshold
        assert keep_flags == [False, False, True]
        assert records[0]["language"] == "unknown"
        assert records[0]["language_score"] == 0.0

    def test_filter_bytes_text(self, filter_with_mock):
        """Test handling of bytes text field."""
        records = [
            {"text": b"Hello, English text."},
        ]

        keep_flags = filter_with_mock.should_keep_batch(records)

        assert keep_flags == [True]
        assert records[0]["language"] == "eng"

    def test_filter_disable_output_columns(self, mock_fasttext_model):
        """Test disabling output columns."""
        with patch(
            "mega_data_factory.operators.filters.text_target_language_filter._get_fasttext_model"
        ) as mock_get_model:
            mock_get_model.return_value = mock_fasttext_model
            from mega_data_factory.operators.filters.text_target_language_filter import (
                TextTargetLanguageFilter,
            )

            filter_instance = TextTargetLanguageFilter(
                target_languages=["eng"],
                add_language_column=False,
                add_score_column=False,
            )
            filter_instance._model = mock_fasttext_model

            records = [{"text": "Hello, English text."}]

            keep_flags = filter_instance.should_keep_batch(records)

            assert keep_flags == [True]
            assert "language" not in records[0]
            assert "language_score" not in records[0]

    def test_filter_custom_field_names(self, mock_fasttext_model):
        """Test custom field names."""
        with patch(
            "mega_data_factory.operators.filters.text_target_language_filter._get_fasttext_model"
        ) as mock_get_model:
            mock_get_model.return_value = mock_fasttext_model
            from mega_data_factory.operators.filters.text_target_language_filter import (
                TextTargetLanguageFilter,
            )

            filter_instance = TextTargetLanguageFilter(
                target_languages=["eng"],
                text_field="content",
                language_field="detected_lang",
                language_score_field="lang_confidence",
            )
            filter_instance._model = mock_fasttext_model

            records = [{"content": "Hello, English text."}]

            keep_flags = filter_instance.should_keep_batch(records)

            assert keep_flags == [True]
            assert records[0]["detected_lang"] == "eng"
            assert records[0]["lang_confidence"] == 0.95

    def test_filter_empty_batch(self, filter_with_mock):
        """Test handling of empty batch."""
        records = []

        keep_flags = filter_with_mock.should_keep_batch(records)

        assert keep_flags == []

    def test_filter_single_target_language_string(self, mock_fasttext_model):
        """Test single target language as string."""
        with patch(
            "mega_data_factory.operators.filters.text_target_language_filter._get_fasttext_model"
        ) as mock_get_model:
            mock_get_model.return_value = mock_fasttext_model
            from mega_data_factory.operators.filters.text_target_language_filter import (
                TextTargetLanguageFilter,
            )

            filter_instance = TextTargetLanguageFilter(
                target_languages="eng",  # String instead of list
                min_score=0.65,
            )
            filter_instance._model = mock_fasttext_model

            records = [
                {"text": "Hello, English text."},
                {"text": "Bonjour, français."},
            ]

            keep_flags = filter_instance.should_keep_batch(records)

            assert keep_flags == [True, False]

    def test_output_schema(self, filter_with_mock):
        """Test output schema."""
        import pyarrow as pa

        schema = filter_with_mock.get_output_schema()

        assert "language" in schema
        assert "language_score" in schema
        assert schema["language"] == pa.string()
        assert schema["language_score"] == pa.float32()

    def test_output_schema_disabled_columns(self, mock_fasttext_model):
        """Test output schema with disabled columns."""
        with patch(
            "mega_data_factory.operators.filters.text_target_language_filter._get_fasttext_model"
        ) as mock_get_model:
            mock_get_model.return_value = mock_fasttext_model
            from mega_data_factory.operators.filters.text_target_language_filter import (
                TextTargetLanguageFilter,
            )

            filter_instance = TextTargetLanguageFilter(
                add_language_column=False,
                add_score_column=False,
            )

            schema = filter_instance.get_output_schema()

            assert schema == {}


class TestPreprocessText:
    """Test text preprocessing functions."""

    def test_preprocess_newlines(self):
        """Test newline normalization."""
        from mega_data_factory.operators.filters.text_target_language_filter import (
            _preprocess_text,
        )

        text = "Hello\nWorld\r\nTest\tTab"
        result = _preprocess_text(text)

        assert "\n" not in result
        assert "\r" not in result
        assert "\t" not in result
        assert result == "Hello World Test Tab"

    def test_preprocess_multiple_spaces(self):
        """Test multiple space normalization."""
        from mega_data_factory.operators.filters.text_target_language_filter import (
            _preprocess_text,
        )

        text = "Hello    World   Test"
        result = _preprocess_text(text)

        assert result == "Hello World Test"

    def test_preprocess_strip(self):
        """Test leading/trailing whitespace stripping."""
        from mega_data_factory.operators.filters.text_target_language_filter import (
            _preprocess_text,
        )

        text = "  Hello World  "
        result = _preprocess_text(text)

        assert result == "Hello World"


class TestParseLanguageLabel:
    """Test language label parsing."""

    def test_parse_standard_label(self):
        """Test parsing standard FastText label."""
        from mega_data_factory.operators.filters.text_target_language_filter import (
            _parse_language_label,
        )

        assert _parse_language_label("__label__eng_Latn") == "eng"
        assert _parse_language_label("__label__zho_Hans") == "zho"
        assert _parse_language_label("__label__fra_Latn") == "fra"

    def test_parse_label_without_prefix(self):
        """Test parsing label without __label__ prefix."""
        from mega_data_factory.operators.filters.text_target_language_filter import (
            _parse_language_label,
        )

        assert _parse_language_label("eng_Latn") == "eng"
        assert _parse_language_label("zho_Hans") == "zho"

    def test_parse_simple_label(self):
        """Test parsing simple label without script."""
        from mega_data_factory.operators.filters.text_target_language_filter import (
            _parse_language_label,
        )

        assert _parse_language_label("eng") == "eng"
        assert _parse_language_label("__label__eng") == "eng"
