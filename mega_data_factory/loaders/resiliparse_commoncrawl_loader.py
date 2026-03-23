"""CommonCrawl WARC DataLoader with FastWARC and configurable text extraction.

This loader uses FastWARC (C++/Cython) for WARC parsing (1.3x-6.5x faster than warcio)
and supports both Resiliparse and Rust for HTML text extraction.
"""

from __future__ import annotations

import gzip
import os
import time
from collections.abc import Iterator
from typing import Any

import requests
from fastwarc.stream_io import FileStream, GZipStream
from fastwarc.warc import ArchiveIterator, WarcRecordType

from mega_data_factory.framework import DataLoader
from mega_data_factory.utils.resiliparse_utils import decode_html_content, extract_text_from_html


class ResiliparseCommonCrawlLoader(DataLoader):
    """High-performance CommonCrawl WARC loader using FastWARC.

    This loader provides significant performance improvements over the warcio-based
    CommonCrawlLoader:
    - FastWARC: 1.3x-6.5x faster WARC parsing (C++/Cython)
    - Configurable text extraction: Resiliparse (rule-based) or Rust (Readability)
    - Robust encoding detection using uchardet

    Text Extraction Options:
    - Resiliparse (default): Rule-based extraction with configurable boilerplate removal
    - Rust (use_rust_extractor=True): Readability algorithm for intelligent content detection

    Features:
    - Main content extraction / boilerplate removal
    - Robust encoding detection and HTML parsing
    - Configurable text extraction options
    - Optional Rust extractor for Readability-based content detection

    Example:
        # Use Resiliparse (default)
        loader = ResiliparseCommonCrawlLoader(
            crawl_id="CC-MAIN-2024-51",
            main_content=True,  # Enable boilerplate removal
        )

        # Use Rust Readability
        loader = ResiliparseCommonCrawlLoader(
            crawl_id="CC-MAIN-2024-51",
            use_rust_extractor=True,  # Use Rust/Readability
        )
    """

    def __init__(
        self,
        crawl_id: str,
        base_url: str = "https://data.commoncrawl.org/",
        cache_dir: str | None = None,
        num_files: int | None = None,
        *,
        # Text extraction options
        use_rust_extractor: bool = False,  # Use Rust Readability instead of Resiliparse
        main_content: bool = True,  # Boilerplate removal (Resiliparse only)
        preserve_formatting: bool | str = True,  # Preserve formatting (Resiliparse only)
        min_text_length: int = 50,  # Minimum extracted text length
        min_html_length: int = 100,  # Minimum HTML content length
        # WARC parsing options
        strict_mode: bool = False,  # False for compatibility with non-standard WARCs
    ):
        """Initialize the Resiliparse CommonCrawl loader.

        Args:
            crawl_id: CommonCrawl crawl ID (e.g., "CC-MAIN-2024-51")
            base_url: Base URL for CommonCrawl data
            cache_dir: Directory to cache downloaded WARC files
            num_files: Number of WARC files to process (None for all)
            use_rust_extractor: Use Rust (Readability) for text extraction instead of Resiliparse.
                                Rust provides intelligent content detection but requires compilation.
                                Resiliparse is rule-based and more configurable.
            main_content: Enable boilerplate removal (Resiliparse only, ignored if use_rust_extractor=True)
            preserve_formatting: Preserve block-level formatting (Resiliparse only)
            min_text_length: Minimum extracted text length to keep
            min_html_length: Minimum HTML content length to process
            strict_mode: Enforce strict WARC spec compliance
        """
        self.crawl_id = crawl_id
        self.base_url = base_url.rstrip("/") + "/"
        self.cache_dir = cache_dir or os.path.expanduser("~/.cache/commoncrawl")
        self.num_files = num_files
        self.use_rust_extractor = use_rust_extractor
        self.main_content = main_content
        self.preserve_formatting = preserve_formatting
        self.min_text_length = min_text_length
        self.min_html_length = min_html_length
        self.strict_mode = strict_mode
        self._file_list: list[str] | None = None

        # Lazy import Rust module to avoid import errors if not compiled
        self._rust_html_extract_text = None

    def _get_rust_extractor(self):
        """Lazy load Rust html_extract_text module."""
        if self._rust_html_extract_text is None:
            try:
                from mega_data_factory.rust_operators import html_extract_text

                self._rust_html_extract_text = html_extract_text
            except ImportError as e:
                raise ImportError(
                    "Rust html_extract_text not available. "
                    "Please build the Rust extension with 'maturin develop --release' "
                    "or set use_rust_extractor=False to use Resiliparse."
                ) from e
        return self._rust_html_extract_text

    def get_file_list(self, max_samples: int | None = None, num_workers: int = 1) -> list[str]:
        """Get list of WARC file paths."""
        if self._file_list is not None:
            return self._file_list

        # Calculate files needed: ~5K records per file
        num_files = self.num_files
        if num_files is None and max_samples:
            num_files = max(num_workers, max_samples // 5000 + 1)

        url = f"{self.base_url}crawl-data/{self.crawl_id}/warc.paths.gz"
        paths = []

        r = requests.get(url, stream=True, timeout=300)
        r.raise_for_status()
        r.raw.decode_content = False

        for line in gzip.GzipFile(fileobj=r.raw):
            path = line.decode("utf-8", errors="ignore").strip()
            if path:
                paths.append(path)
                if num_files and len(paths) >= num_files:
                    break

        self._file_list = paths
        extractor = "Rust/Readability" if self.use_rust_extractor else "Resiliparse"
        print(f"[ResiliparseCommonCrawl] {len(paths)} WARC files, extractor: {extractor}")
        return paths

    def load_files(
        self,
        file_list: list[str],
        worker_id: int | None = None,
        checkpoint: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Load WARC files and yield records with extracted text.

        Uses FastWARC for streaming WARC parsing.
        Text extraction uses either Resiliparse or Rust based on use_rust_extractor.
        """
        label = f"W{worker_id}" if worker_id is not None else "L"
        skip = checkpoint.get("records_processed", 0) if checkpoint else 0
        count = 0
        yielded = 0

        # Get extractor function
        if self.use_rust_extractor:
            html_extract_text = self._get_rust_extractor()
            extractor_name = "Rust/Readability"
        else:
            extractor_name = "Resiliparse"

        for warc_path in file_list:
            print(f"[{label}] Starting to process: {warc_path.split('/')[-1]}")
            local_path = self._download(warc_path)
            print(f"[{label}] File ready, opening: {local_path.split('/')[-1]}")

            # Use FastWARC for high-performance WARC parsing
            record_count = 0
            # Create FastWARC stream (FileStream handles file opening)
            file_stream = FileStream(local_path)
            gzip_stream = GZipStream(file_stream)

            # Create archive iterator with filters
            archive = ArchiveIterator(
                gzip_stream,
                record_types=WarcRecordType.response,  # Only response records
                strict_mode=self.strict_mode,
                parse_http=True,
            )

            print(f"[{label}] Starting FastWARC ArchiveIterator (extractor: {extractor_name})...")
            for record in archive:
                record_count += 1
                if record_count == 1:
                    print(f"[{label}] First record received from FastWARC")

                # Check HTTP content type
                content_type = record.http_content_type or ""
                if "text/html" not in content_type.lower():
                    continue

                # Get URL and date from headers
                url = record.headers.get("WARC-Target-URI", "")
                warc_date = record.headers.get("WARC-Date", "")

                # Read HTML content with robust encoding handling
                try:
                    raw_content = record.reader.read()
                    # Use Resiliparse's robust encoding detection and decoding
                    html_content = decode_html_content(raw_content, charset=record.http_charset)
                except Exception:
                    continue

                if not html_content or len(html_content) < self.min_html_length:
                    continue

                count += 1
                if count <= skip:
                    continue

                # Extract text using selected extractor
                try:
                    if self.use_rust_extractor:
                        # Rust Readability extractor
                        result = html_extract_text(html_content)
                        if result is None:
                            continue
                        title, text, text_length = result
                    else:
                        # Resiliparse extractor
                        result = extract_text_from_html(
                            html_content,
                            main_content=self.main_content,
                            preserve_formatting=self.preserve_formatting,
                        )
                        title = result.title
                        text = result.text
                        text_length = result.text_length
                except Exception as e:
                    print(f"[{label}] Text extraction error: {e}")
                    continue

                if not text or text_length < self.min_text_length:
                    continue

                yielded += 1

                if yielded == 1:
                    print(f"[{label}] First record yielded!")

                yield {
                    "crawl_id": self.crawl_id,
                    "warc_path": warc_path,
                    "url": url,
                    "warc_date": warc_date,
                    "title": title,
                    "text": text,
                    "text_length": text_length,
                }

            print(f"[{label}] FastWARC: {record_count} records scanned, {count} HTML, {yielded} yielded")

        print(f"[{label}] Total: {count} HTML records parsed, {yielded} yielded")

    def _download(self, warc_path: str) -> str:
        """Download WARC to cache."""
        os.makedirs(os.path.join(self.cache_dir, self.crawl_id), exist_ok=True)
        filename = warc_path.rsplit("/", 1)[-1]
        local_path = os.path.join(self.cache_dir, self.crawl_id, filename)

        if os.path.exists(local_path):
            return local_path

        print(f"[DL] {filename}...")
        url = f"{self.base_url}{warc_path}"

        for attempt in range(3):
            try:
                r = requests.get(url, stream=True, timeout=300)
                r.raise_for_status()
                tmp = local_path + ".tmp"
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(131072):
                        f.write(chunk)
                os.rename(tmp, local_path)
                print(f"[DL] {filename} done ({os.path.getsize(local_path) // 1048576}MB)")
                return local_path
            except Exception as e:
                if attempt == 2:
                    raise RuntimeError(f"Download failed: {warc_path}") from e
                time.sleep(2**attempt)

        return local_path
