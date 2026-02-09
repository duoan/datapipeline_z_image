#!/usr/bin/env python3
"""
Tests for Video Deduplication Operators

Tests both VideoExactByteLevelDeduplicator and VideoExactStreamLevelDeduplicator.
"""

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mega_data_factory.operators.dedup.video_deduplicator import VideoDeduplicator
from mega_data_factory.operators.dedup.video_exact_byte_level_dedup import (
    VideoExactByteLevelDeduplicator,
)
from mega_data_factory.operators.dedup.video_exact_stream_level_dedup import (
    VideoExactStreamLevelDeduplicator,
)
from mega_data_factory.utils.video_utils import (
    VideoLoader,
    compute_file_hash,
    get_video_from_record,
)


def create_test_video_file(content: str = "test_video_content", suffix: str = ".mp4") -> str:
    """Create a temporary test video file."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=suffix, delete=False) as f:
        f.write(content.encode("utf-8"))
        return f.name


def cleanup_temp_file(path: str):
    """Clean up temporary file."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


class TestVideoLoader:
    """Tests for VideoLoader utility."""

    def test_load_local_file(self):
        """Test loading a local file."""
        temp_file = create_test_video_file("local_video_content")
        try:
            loader = VideoLoader()
            result = loader.load(temp_file)
            assert result == temp_file
        finally:
            cleanup_temp_file(temp_file)

    def test_load_nonexistent_file(self):
        """Test loading a nonexistent file returns None."""
        loader = VideoLoader()
        result = loader.load("/nonexistent/path/video.mp4")
        assert result is None

    def test_load_empty_path(self):
        """Test loading empty path returns None."""
        loader = VideoLoader()
        result = loader.load("")
        assert result is None

    def test_cache_directory_creation(self):
        """Test that cache directory is created."""
        cache_dir = tempfile.mkdtemp()
        try:
            shutil.rmtree(cache_dir)  # Remove to test creation
            VideoLoader(cache_dir=cache_dir)
            assert Path(cache_dir).exists()
        finally:
            shutil.rmtree(cache_dir, ignore_errors=True)

    def test_is_url_detection(self):
        """Test URL detection."""
        loader = VideoLoader()
        assert loader._is_url("http://example.com/video.mp4")
        assert loader._is_url("https://example.com/video.mp4")
        assert not loader._is_url("/local/path/video.mp4")
        assert not loader._is_url("relative/path/video.mp4")

    def test_cleanup_batch(self):
        """Test batch cleanup functionality."""
        cache_dir = tempfile.mkdtemp()
        try:
            loader = VideoLoader(cache_dir=cache_dir)

            # Simulate downloading a file by manually adding to tracked files
            test_file = Path(cache_dir) / "test_video.mp4"
            test_file.write_bytes(b"test content")
            loader._batch_downloaded_files.add(str(test_file))

            assert test_file.exists()
            assert loader.get_batch_downloaded_count() == 1

            # Cleanup should remove the file
            cleaned = loader.cleanup_batch()
            assert cleaned == 1
            assert not test_file.exists()
            assert loader.get_batch_downloaded_count() == 0
        finally:
            shutil.rmtree(cache_dir, ignore_errors=True)

    def test_persistent_cache_no_cleanup(self):
        """Test that persistent cache skips cleanup."""
        cache_dir = tempfile.mkdtemp()
        try:
            loader = VideoLoader(cache_dir=cache_dir, persistent_cache=True)

            # Simulate downloading a file
            test_file = Path(cache_dir) / "test_video.mp4"
            test_file.write_bytes(b"test content")
            loader._batch_downloaded_files.add(str(test_file))

            # Cleanup should not remove the file when persistent_cache=True
            cleaned = loader.cleanup_batch()
            assert cleaned == 0
            assert test_file.exists()
        finally:
            shutil.rmtree(cache_dir, ignore_errors=True)


class TestComputeFileHash:
    """Tests for compute_file_hash function."""

    def test_sha256_hash(self):
        """Test SHA-256 hash computation."""
        temp_file = create_test_video_file("test_content_for_hash")
        try:
            result = compute_file_hash(temp_file, algorithm="sha256")
            expected = hashlib.sha256(b"test_content_for_hash").hexdigest()
            assert result == expected
        finally:
            cleanup_temp_file(temp_file)

    def test_md5_hash(self):
        """Test MD5 hash computation."""
        temp_file = create_test_video_file("test_content_for_md5")
        try:
            result = compute_file_hash(temp_file, algorithm="md5")
            expected = hashlib.md5(b"test_content_for_md5").hexdigest()
            assert result == expected
        finally:
            cleanup_temp_file(temp_file)

    def test_different_content_different_hash(self):
        """Test that different content produces different hashes."""
        temp_file1 = create_test_video_file("content_one")
        temp_file2 = create_test_video_file("content_two")
        try:
            hash1 = compute_file_hash(temp_file1)
            hash2 = compute_file_hash(temp_file2)
            assert hash1 != hash2
        finally:
            cleanup_temp_file(temp_file1)
            cleanup_temp_file(temp_file2)

    def test_same_content_same_hash(self):
        """Test that same content produces same hash."""
        temp_file1 = create_test_video_file("identical_content")
        temp_file2 = create_test_video_file("identical_content")
        try:
            hash1 = compute_file_hash(temp_file1)
            hash2 = compute_file_hash(temp_file2)
            assert hash1 == hash2
        finally:
            cleanup_temp_file(temp_file1)
            cleanup_temp_file(temp_file2)


class TestGetVideoFromRecord:
    """Tests for get_video_from_record function."""

    def test_video_bytes_in_dict(self):
        """Test extracting video bytes from dict."""
        record = {"video": {"bytes": b"video_data"}}
        result = get_video_from_record(record)
        assert result == b"video_data"

    def test_video_path_in_dict(self):
        """Test extracting video path from dict."""
        record = {"video": {"path": "/path/to/video.mp4"}}
        result = get_video_from_record(record)
        assert result == "/path/to/video.mp4"

    def test_video_bytes_direct(self):
        """Test extracting direct video bytes."""
        record = {"video": b"direct_video_data"}
        result = get_video_from_record(record)
        assert result == b"direct_video_data"

    def test_video_url_field(self):
        """Test extracting video URL."""
        record = {"video_url": "https://example.com/video.mp4"}
        result = get_video_from_record(record)
        assert result == "https://example.com/video.mp4"

    def test_video_path_field(self):
        """Test extracting video path field."""
        record = {"video_path": "/local/video.mp4"}
        result = get_video_from_record(record)
        assert result == "/local/video.mp4"

    def test_no_video_data(self):
        """Test record with no video data."""
        record = {"id": "123", "title": "No video"}
        result = get_video_from_record(record)
        assert result is None

    def test_custom_field_names(self):
        """Test custom field names."""
        record = {"my_video": {"bytes": b"custom_video"}}
        result = get_video_from_record(record, video_field="my_video")
        assert result == b"custom_video"


class TestVideoDeduplicatorBase:
    """Tests for VideoDeduplicator base class."""

    def test_base_class_is_abstract(self):
        """Test that base class cannot be instantiated directly."""
        with pytest.raises(TypeError):
            # VideoDeduplicator is abstract, should not be instantiated
            dedup = VideoDeduplicator()
            # If we get here, try to call compute_hash which should fail
            dedup.compute_hash("/some/path")

    def test_get_existing_hash_fields_default(self):
        """Test default existing hash fields is empty."""
        # Use a concrete subclass to test
        dedup = VideoExactByteLevelDeduplicator()
        # The base class returns empty list, but subclasses override
        assert isinstance(dedup.get_existing_hash_fields(), list)


class TestVideoExactByteLevelDeduplicator:
    """Tests for VideoExactByteLevelDeduplicator."""

    def test_init_default_params(self):
        """Test initialization with default parameters."""
        dedup = VideoExactByteLevelDeduplicator()
        assert dedup.video_field == "video"
        assert dedup.video_url_field == "video_url"
        assert dedup.hash_algorithm == "sha256"

    def test_init_custom_params(self):
        """Test initialization with custom parameters."""
        dedup = VideoExactByteLevelDeduplicator(
            video_field="my_video",
            hash_algorithm="md5",
            max_file_size=1000000,
        )
        assert dedup.video_field == "my_video"
        assert dedup.hash_algorithm == "md5"
        assert dedup.max_file_size == 1000000

    def test_compute_hash_from_file(self):
        """Test hash computation from file."""
        temp_file = create_test_video_file("test_video_content")
        try:
            dedup = VideoExactByteLevelDeduplicator(hash_algorithm="sha256")
            result = dedup.compute_hash(temp_file)
            expected = hashlib.sha256(b"test_video_content").hexdigest()
            assert result == expected
        finally:
            cleanup_temp_file(temp_file)

    def test_get_dedup_keys_batch_with_file(self):
        """Test getting dedup keys from records with file paths."""
        temp_file = create_test_video_file("file_video_content")
        try:
            dedup = VideoExactByteLevelDeduplicator()
            records = [{"id": "1", "video_path": temp_file}]
            keys = dedup.get_dedup_keys_batch(records)
            assert len(keys) == 1
            expected = hashlib.sha256(b"file_video_content").hexdigest()
            assert keys[0] == expected
        finally:
            cleanup_temp_file(temp_file)

    def test_get_dedup_keys_batch_with_existing_hash(self):
        """Test that existing hash is used if present."""
        dedup = VideoExactByteLevelDeduplicator()
        records = [
            {"id": "1", "video_hash": "precomputed_hash_123"},
            {"id": "2", "file_hash": "another_precomputed_hash"},
        ]
        keys = dedup.get_dedup_keys_batch(records)
        assert keys[0] == "precomputed_hash_123"
        assert keys[1] == "another_precomputed_hash"

    def test_get_dedup_keys_batch_fallback_to_id(self):
        """Test fallback to record ID when video cannot be processed."""
        dedup = VideoExactByteLevelDeduplicator()
        records = [{"id": "fallback_id_123"}]  # No video data
        keys = dedup.get_dedup_keys_batch(records)
        # Fallback keys are prefixed with __fallback_id__ to distinguish from actual hashes
        assert keys[0] == "__fallback_id__fallback_id_123"

    def test_bytes_not_supported(self):
        """Test that bytes input is not supported (memory-unfriendly)."""
        dedup = VideoExactByteLevelDeduplicator()
        records = [{"id": "1", "video": {"bytes": b"test_video_bytes"}}]
        keys = dedup.get_dedup_keys_batch(records)
        # Should fall back to ID since bytes are not supported
        # Fallback keys are prefixed with __fallback_id__
        assert keys[0] == "__fallback_id__1"

    def test_existing_hash_fields(self):
        """Test that existing hash fields are correctly defined."""
        dedup = VideoExactByteLevelDeduplicator()
        fields = dedup.get_existing_hash_fields()
        assert "video_hash" in fields
        assert "file_hash" in fields


class TestVideoExactStreamLevelDeduplicator:
    """Tests for VideoExactStreamLevelDeduplicator."""

    def test_init_default_params(self):
        """Test initialization with default parameters."""
        dedup = VideoExactStreamLevelDeduplicator()
        assert dedup.video_field == "video"
        assert dedup.hash_algorithm == "md5"
        assert dedup.include_audio is False

    def test_init_custom_params(self):
        """Test initialization with custom parameters."""
        dedup = VideoExactStreamLevelDeduplicator(
            video_field="my_video",
            hash_algorithm="sha256",
            include_audio=True,
        )
        assert dedup.video_field == "my_video"
        assert dedup.hash_algorithm == "sha256"
        assert dedup.include_audio is True

    def test_get_dedup_keys_batch_with_existing_hash(self):
        """Test that existing stream hash is used if present."""
        dedup = VideoExactStreamLevelDeduplicator()
        records = [
            {"id": "1", "video_stream_hash": "precomputed_stream_hash"},
            {"id": "2", "stream_hash": "another_stream_hash"},
        ]
        keys = dedup.get_dedup_keys_batch(records)
        assert keys[0] == "precomputed_stream_hash"
        assert keys[1] == "another_stream_hash"

    def test_get_dedup_keys_batch_fallback_to_id(self):
        """Test fallback to record ID when video cannot be processed."""
        dedup = VideoExactStreamLevelDeduplicator()
        records = [{"id": "fallback_id_456"}]  # No video data
        keys = dedup.get_dedup_keys_batch(records)
        # Fallback keys are prefixed with __fallback_id__ to distinguish from actual hashes
        assert keys[0] == "__fallback_id__fallback_id_456"

    def test_bytes_not_supported(self):
        """Test that bytes input is not supported (memory-unfriendly)."""
        dedup = VideoExactStreamLevelDeduplicator()
        records = [{"id": "1", "video": {"bytes": b"test_video_bytes"}}]
        keys = dedup.get_dedup_keys_batch(records)
        # Should fall back to ID since bytes are not supported
        # Fallback keys are prefixed with __fallback_id__
        assert keys[0] == "__fallback_id__1"

    def test_existing_hash_fields(self):
        """Test that existing hash fields are correctly defined."""
        dedup = VideoExactStreamLevelDeduplicator()
        fields = dedup.get_existing_hash_fields()
        assert "video_stream_hash" in fields
        assert "stream_hash" in fields


class TestIntegration:
    """Integration tests for video deduplication."""

    def test_byte_level_dedup_identifies_duplicates(self):
        """Test that byte-level dedup correctly identifies duplicate files."""
        temp_file1 = create_test_video_file("duplicate_content")
        temp_file2 = create_test_video_file("duplicate_content")
        temp_file3 = create_test_video_file("unique_content")
        try:
            dedup = VideoExactByteLevelDeduplicator()
            records = [
                {"id": "1", "video_path": temp_file1},
                {"id": "2", "video_path": temp_file2},
                {"id": "3", "video_path": temp_file3},
            ]
            keys = dedup.get_dedup_keys_batch(records)
            assert keys[0] == keys[1]  # Duplicates
            assert keys[0] != keys[2]  # Unique
        finally:
            cleanup_temp_file(temp_file1)
            cleanup_temp_file(temp_file2)
            cleanup_temp_file(temp_file3)

    def test_mixed_input_formats(self):
        """Test deduplication with mixed input formats."""
        temp_file = create_test_video_file("file_content")
        try:
            dedup = VideoExactByteLevelDeduplicator()
            records = [
                {"id": "1", "video_path": temp_file},
                {"id": "2", "video_hash": "precomputed"},
                {"id": "3"},  # No video data - falls back to ID
            ]
            keys = dedup.get_dedup_keys_batch(records)
            assert len(keys) == 3
            assert keys[0] == hashlib.sha256(b"file_content").hexdigest()
            assert keys[1] == "precomputed"
            # Fallback keys are prefixed with __fallback_id__
            assert keys[2] == "__fallback_id__3"
        finally:
            cleanup_temp_file(temp_file)


def check_ffmpeg_available() -> bool:
    """Check if FFmpeg is available."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def run_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("Video Deduplication Operators Tests")
    print("=" * 60)
    print()

    test_classes = [
        TestVideoLoader,
        TestComputeFileHash,
        TestGetVideoFromRecord,
        TestVideoDeduplicatorBase,
        TestVideoExactByteLevelDeduplicator,
        TestVideoExactStreamLevelDeduplicator,
        TestIntegration,
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = []

    for test_class in test_classes:
        print(f"Running {test_class.__name__}...")
        instance = test_class()

        for method_name in dir(instance):
            if method_name.startswith("test_"):
                total_tests += 1
                try:
                    getattr(instance, method_name)()
                    print(f"  ✓ {method_name}")
                    passed_tests += 1
                except Exception as e:
                    print(f"  ✗ {method_name}: {e}")
                    failed_tests.append((test_class.__name__, method_name, str(e)))

        print()

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Tests passed: {passed_tests}/{total_tests}")

    if failed_tests:
        print("\nFailed tests:")
        for class_name, method_name, error in failed_tests:
            print(f"  - {class_name}.{method_name}: {error}")

    # Check FFmpeg availability
    print()
    if check_ffmpeg_available():
        print("✓ FFmpeg is available (stream-level dedup will work)")
    else:
        print("⚠ FFmpeg not found (stream-level dedup requires FFmpeg)")

    return len(failed_tests) == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
