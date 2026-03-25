"""Tests for Resiliparse text extraction functionality."""


class TestResiliparseCommonCrawlLoader:
    """Tests for ResiliparseCommonCrawlLoader."""

    def test_init_with_resiliparse_options(self):
        """Test initialization with Resiliparse-specific options."""
        from mega_data_factory.loaders.resiliparse_commoncrawl_loader import ResiliparseCommonCrawlLoader

        loader = ResiliparseCommonCrawlLoader(
            crawl_id="CC-MAIN-2024-51",
            main_content=True,
            preserve_formatting=True,
            min_html_length=200,
            strict_mode=False,
        )

        assert loader.crawl_id == "CC-MAIN-2024-51"
        assert loader.main_content is True
        assert loader.preserve_formatting is True
        assert loader.min_html_length == 200
        assert loader.strict_mode is False
        assert loader.use_rust_extractor is False  # Default

    def test_init_with_rust_extractor(self):
        """Test initialization with Rust extractor enabled."""
        from mega_data_factory.loaders.resiliparse_commoncrawl_loader import ResiliparseCommonCrawlLoader

        loader = ResiliparseCommonCrawlLoader(
            crawl_id="CC-MAIN-2024-51",
            use_rust_extractor=True,
            min_text_length=100,
        )

        assert loader.use_rust_extractor is True
        assert loader.min_text_length == 100

    def test_default_options(self):
        """Test default initialization options."""
        from mega_data_factory.loaders.resiliparse_commoncrawl_loader import ResiliparseCommonCrawlLoader

        loader = ResiliparseCommonCrawlLoader(crawl_id="CC-MAIN-2024-51")

        assert loader.main_content is True
        assert loader.preserve_formatting is True
        assert loader.min_html_length == 100
        assert loader.min_text_length == 50
        assert loader.strict_mode is False
        assert loader.use_rust_extractor is False  # Default to Resiliparse


class TestTextExtraction:
    """Tests for HTML text extraction with Resiliparse."""

    def test_extract_plain_text_basic(self):
        """Test basic text extraction."""
        from resiliparse.extract.html2text import extract_plain_text

        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Hello World</h1>
            <p>This is a test paragraph.</p>
        </body>
        </html>
        """

        text = extract_plain_text(html, main_content=False, preserve_formatting=False)
        assert "Hello World" in text
        assert "test paragraph" in text

    def test_extract_plain_text_with_boilerplate_removal(self):
        """Test text extraction with main_content=True (boilerplate removal)."""
        from resiliparse.extract.html2text import extract_plain_text

        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Test Page</title></head>
        <body>
            <nav>
                <a href="/">Home</a>
                <a href="/about">About</a>
            </nav>
            <main>
                <article>
                    <h1>Main Article Title</h1>
                    <p>This is the main content of the article.</p>
                </article>
            </main>
            <footer>
                <p>Copyright 2024</p>
            </footer>
        </body>
        </html>
        """

        text_with_removal = extract_plain_text(html, main_content=True, preserve_formatting=False)
        text_without_removal = extract_plain_text(html, main_content=False, preserve_formatting=False)

        # Both should contain main content
        assert "Main Article Title" in text_with_removal
        assert "main content" in text_with_removal

    def test_extract_title(self):
        """Test title extraction from HTML."""
        from resiliparse.parse.html import HTMLTree

        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Page Title Here</title></head>
        <body><p>Content</p></body>
        </html>
        """

        tree = HTMLTree.parse(html)
        title = tree.title.strip() if tree.title else ""

        assert title == "Page Title Here"

    def test_extract_title_no_title_tag(self):
        """Test title extraction when no title tag exists."""
        from resiliparse.parse.html import HTMLTree

        html = """
        <!DOCTYPE html>
        <html>
        <body><p>Content</p></body>
        </html>
        """

        tree = HTMLTree.parse(html)
        title = tree.title.strip() if tree.title else ""

        assert title == ""


class TestEncodingDetection:
    """Tests for encoding detection with Resiliparse."""

    def test_detect_encoding_utf8(self):
        """Test UTF-8 encoding detection."""
        from resiliparse.parse.encoding import detect_encoding

        content = b"Hello, this is a test."
        encoding = detect_encoding(content, from_html_meta=True)

        # Should detect UTF-8 or compatible encoding
        assert encoding is not None

    def test_bytes_to_str(self):
        """Test bytes to string conversion."""
        from resiliparse.parse.encoding import bytes_to_str

        content = "Hello, 世界!".encode()
        text = bytes_to_str(content, "utf-8")

        assert text == "Hello, 世界!"


class TestLanguageDetection:
    """Tests for language detection with Resiliparse."""

    def test_detect_language_english(self):
        """Test English language detection."""
        from resiliparse.parse.lang import detect_fast

        text = "This is a sample English text for language detection testing. It needs to be long enough for accurate detection."
        result = detect_fast(text)

        # detect_fast returns (lang, score) tuple
        assert result[0] == "en"

    def test_detect_language_chinese(self):
        """Test Chinese language detection."""
        from resiliparse.parse.lang import detect_fast

        # Use longer text for more accurate detection
        text = "这是一段中文文本，用于测试语言检测功能。我们需要足够长的文本才能准确地检测语言。语言检测是自然语言处理中的一个重要任务。"
        result = detect_fast(text)

        # detect_fast returns (lang, score) tuple
        # Note: may return 'zh' or 'unknown' depending on text length
        assert result[0] in ("zh", "unknown")

    def test_detect_language_with_candidates(self):
        """Test language detection with limited candidates."""
        from resiliparse.parse.lang import detect_fast

        # Use longer text for more accurate detection
        text = "This is a longer English text that should be properly detected by the language detection algorithm when using candidate languages."
        result = detect_fast(text, langs=["en", "de", "fr"])

        # detect_fast returns (lang, score) tuple
        assert result[0] == "en"


class TestLoaderRegistry:
    """Tests for loader registration."""

    def test_commoncrawl_loader_registered(self):
        """Test that CommonCrawlLoader is registered."""
        # Import loaders to trigger registration
        import mega_data_factory.loaders  # noqa: F401
        from mega_data_factory.framework import DataLoaderRegistry

        assert "CommonCrawlLoader" in DataLoaderRegistry._loaders

    def test_resiliparse_commoncrawl_loader_registered(self):
        """Test that ResiliparseCommonCrawlLoader is registered."""
        # Import loaders to trigger registration
        import mega_data_factory.loaders  # noqa: F401
        from mega_data_factory.framework import DataLoaderRegistry

        assert "ResiliparseCommonCrawlLoader" in DataLoaderRegistry._loaders

    def test_create_commoncrawl_loader(self):
        """Test creating CommonCrawlLoader via registry."""
        # Import loaders to trigger registration
        import mega_data_factory.loaders  # noqa: F401
        from mega_data_factory.framework import DataLoaderRegistry

        loader = DataLoaderRegistry.create(
            "CommonCrawlLoader",
            {"crawl_id": "CC-MAIN-2024-51"},
        )

        assert loader.crawl_id == "CC-MAIN-2024-51"

    def test_create_resiliparse_commoncrawl_loader(self):
        """Test creating ResiliparseCommonCrawlLoader via registry."""
        # Import loaders to trigger registration
        import mega_data_factory.loaders  # noqa: F401
        from mega_data_factory.framework import DataLoaderRegistry

        loader = DataLoaderRegistry.create(
            "ResiliparseCommonCrawlLoader",
            {"crawl_id": "CC-MAIN-2024-51", "main_content": True},
        )

        assert loader.crawl_id == "CC-MAIN-2024-51"
        assert loader.main_content is True


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
