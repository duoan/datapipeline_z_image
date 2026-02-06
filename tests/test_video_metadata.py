"""
Tests for Video Metadata Refiner

Tests the VideoMetadataRefiner operator that extracts video metadata using FFprobe.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pyarrow as pa
import pytest

from mega_data_factory.operators.refiners.video_metadata import (
    FIELD_AUDIO_CHANNELS,
    FIELD_AUDIO_CODEC,
    FIELD_AUDIO_SAMPLE_RATE,
    FIELD_VIDEO_BITRATE,
    FIELD_VIDEO_CODEC,
    FIELD_VIDEO_DURATION,
    FIELD_VIDEO_FPS,
    FIELD_VIDEO_HEIGHT,
    FIELD_VIDEO_METADATA,
    FIELD_VIDEO_WIDTH,
    VideoMetadataRefiner,
)
from mega_data_factory.utils.video_utils import extract_video_metadata


def ffprobe_available() -> bool:
    """Check if FFprobe is available."""
    try:
        result = subprocess.run(
            ["ffprobe", "-version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def ffmpeg_available() -> bool:
    """Check if FFmpeg is available."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def sample_video(temp_dir):
    """Create a sample video file using FFmpeg."""
    if not ffmpeg_available():
        pytest.skip("FFmpeg not available")

    video_path = os.path.join(temp_dir, "sample.mp4")

    # Create a simple test video using FFmpeg
    # 2 seconds, 320x240, 30fps, with audio
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=2:size=320x240:rate=30",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=2",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        video_path,
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        pytest.skip(f"Failed to create sample video: {result.stderr.decode()}")

    return video_path


@pytest.fixture
def video_only_file(temp_dir):
    """Create a video file without audio."""
    if not ffmpeg_available():
        pytest.skip("FFmpeg not available")

    video_path = os.path.join(temp_dir, "video_only.mp4")

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=1:size=640x480:rate=24",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-an",  # No audio
        video_path,
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        pytest.skip(f"Failed to create video-only file: {result.stderr.decode()}")

    return video_path


class TestExtractVideoMetadata:
    """Tests for the extract_video_metadata utility function."""

    @pytest.mark.skipif(not ffprobe_available(), reason="FFprobe not available")
    def test_extract_metadata_basic(self, sample_video):
        """Test basic metadata extraction."""
        metadata = extract_video_metadata(sample_video)

        assert metadata is not None
        assert "format" in metadata
        assert "streams" in metadata
        assert "video" in metadata
        assert "audio" in metadata

    @pytest.mark.skipif(not ffprobe_available(), reason="FFprobe not available")
    def test_extract_format_info(self, sample_video):
        """Test format information extraction."""
        metadata = extract_video_metadata(sample_video)

        assert metadata is not None
        fmt = metadata["format"]

        assert fmt["format_name"] is not None
        assert fmt["duration"] is not None
        assert fmt["duration"] > 0
        assert fmt["size"] is not None
        assert fmt["size"] > 0

    @pytest.mark.skipif(not ffprobe_available(), reason="FFprobe not available")
    def test_extract_video_stream(self, sample_video):
        """Test video stream extraction."""
        metadata = extract_video_metadata(sample_video)

        assert metadata is not None
        video = metadata["video"]

        assert video is not None
        assert video["codec_type"] == "video"
        assert video["codec_name"] == "h264"
        assert video["width"] == 320
        assert video["height"] == 240
        assert video["fps"] is not None
        assert video["fps"] > 0

    @pytest.mark.skipif(not ffprobe_available(), reason="FFprobe not available")
    def test_extract_audio_stream(self, sample_video):
        """Test audio stream extraction."""
        metadata = extract_video_metadata(sample_video)

        assert metadata is not None
        audio = metadata["audio"]

        assert audio is not None
        assert audio["codec_type"] == "audio"
        assert audio["codec_name"] == "aac"
        assert audio["sample_rate"] is not None
        assert audio["channels"] is not None

    @pytest.mark.skipif(not ffprobe_available(), reason="FFprobe not available")
    def test_extract_video_only(self, video_only_file):
        """Test metadata extraction for video without audio."""
        metadata = extract_video_metadata(video_only_file)

        assert metadata is not None
        assert metadata["video"] is not None
        assert metadata["audio"] is None

    def test_extract_nonexistent_file(self):
        """Test extraction with non-existent file."""
        metadata = extract_video_metadata("/nonexistent/video.mp4")
        assert metadata is None

    def test_extract_invalid_file(self, temp_dir):
        """Test extraction with invalid file."""
        invalid_path = os.path.join(temp_dir, "invalid.mp4")
        with open(invalid_path, "w") as f:
            f.write("not a video")

        metadata = extract_video_metadata(invalid_path)
        # FFprobe may return None or partial metadata for invalid files
        # The important thing is it doesn't crash


class TestVideoMetadataRefiner:
    """Tests for the VideoMetadataRefiner operator."""

    def test_init_default(self):
        """Test default initialization."""
        refiner = VideoMetadataRefiner()

        assert refiner.video_field == "video"
        assert refiner.video_url_field == "video_url"
        assert refiner.video_path_field == "video_path"
        assert refiner.include_full_metadata is True

    def test_init_custom(self):
        """Test custom initialization."""
        refiner = VideoMetadataRefiner(
            video_field="my_video",
            video_url_field="my_url",
            video_path_field="my_path",
            timeout=120,
            include_full_metadata=False,
        )

        assert refiner.video_field == "my_video"
        assert refiner.video_url_field == "my_url"
        assert refiner.video_path_field == "my_path"
        assert refiner.include_full_metadata is False

    @pytest.mark.skipif(not ffprobe_available(), reason="FFprobe not available")
    def test_refine_batch_local_file(self, sample_video):
        """Test refining batch with local file."""
        refiner = VideoMetadataRefiner()

        records = [{"video_path": sample_video}]
        refiner.refine_batch(records)

        record = records[0]
        assert FIELD_VIDEO_DURATION in record
        assert record[FIELD_VIDEO_DURATION] is not None
        assert record[FIELD_VIDEO_DURATION] > 0

        assert FIELD_VIDEO_WIDTH in record
        assert record[FIELD_VIDEO_WIDTH] == 320

        assert FIELD_VIDEO_HEIGHT in record
        assert record[FIELD_VIDEO_HEIGHT] == 240

        assert FIELD_VIDEO_CODEC in record
        assert record[FIELD_VIDEO_CODEC] == "h264"

        assert FIELD_VIDEO_METADATA in record
        assert record[FIELD_VIDEO_METADATA] is not None

        # Verify JSON is valid
        metadata = json.loads(record[FIELD_VIDEO_METADATA])
        assert "format" in metadata
        assert "video" in metadata

    @pytest.mark.skipif(not ffprobe_available(), reason="FFprobe not available")
    def test_refine_batch_video_only(self, video_only_file):
        """Test refining batch with video-only file."""
        refiner = VideoMetadataRefiner()

        records = [{"video_path": video_only_file}]
        refiner.refine_batch(records)

        record = records[0]
        assert record[FIELD_VIDEO_WIDTH] == 640
        assert record[FIELD_VIDEO_HEIGHT] == 480
        assert record[FIELD_VIDEO_CODEC] == "h264"

        # Audio fields should be None
        assert record[FIELD_AUDIO_CODEC] is None
        assert record[FIELD_AUDIO_SAMPLE_RATE] is None
        assert record[FIELD_AUDIO_CHANNELS] is None

    def test_refine_batch_missing_video(self):
        """Test refining batch with missing video."""
        refiner = VideoMetadataRefiner()

        records = [{"other_field": "value"}]
        refiner.refine_batch(records)

        record = records[0]
        assert record[FIELD_VIDEO_DURATION] is None
        assert record[FIELD_VIDEO_WIDTH] is None
        assert record[FIELD_VIDEO_HEIGHT] is None
        assert record[FIELD_VIDEO_METADATA] is None

    def test_refine_batch_nonexistent_file(self):
        """Test refining batch with non-existent file."""
        refiner = VideoMetadataRefiner()

        records = [{"video_path": "/nonexistent/video.mp4"}]
        refiner.refine_batch(records)

        record = records[0]
        assert record[FIELD_VIDEO_DURATION] is None
        assert record[FIELD_VIDEO_WIDTH] is None

    def test_refine_batch_without_full_metadata(self, sample_video):
        """Test refining batch without full metadata."""
        if not ffprobe_available():
            pytest.skip("FFprobe not available")

        refiner = VideoMetadataRefiner(include_full_metadata=False)

        records = [{"video_path": sample_video}]
        refiner.refine_batch(records)

        record = records[0]
        # Individual fields should be present
        assert FIELD_VIDEO_WIDTH in record
        assert FIELD_VIDEO_HEIGHT in record

        # Full metadata field should not be present
        assert FIELD_VIDEO_METADATA not in record

    @pytest.mark.skipif(not ffprobe_available(), reason="FFprobe not available")
    def test_refine_batch_multiple_records(self, sample_video, video_only_file):
        """Test refining batch with multiple records."""
        refiner = VideoMetadataRefiner()

        records = [
            {"video_path": sample_video},
            {"video_path": video_only_file},
            {"video_path": "/nonexistent.mp4"},
        ]
        refiner.refine_batch(records)

        # First record - video with audio
        assert records[0][FIELD_VIDEO_WIDTH] == 320
        assert records[0][FIELD_AUDIO_CODEC] == "aac"

        # Second record - video only
        assert records[1][FIELD_VIDEO_WIDTH] == 640
        assert records[1][FIELD_AUDIO_CODEC] is None

        # Third record - non-existent
        assert records[2][FIELD_VIDEO_WIDTH] is None

    def test_get_output_schema(self):
        """Test output schema generation."""
        refiner = VideoMetadataRefiner()
        schema = refiner.get_output_schema()

        assert FIELD_VIDEO_DURATION in schema
        assert schema[FIELD_VIDEO_DURATION] == pa.float64()

        assert FIELD_VIDEO_WIDTH in schema
        assert schema[FIELD_VIDEO_WIDTH] == pa.int32()

        assert FIELD_VIDEO_HEIGHT in schema
        assert schema[FIELD_VIDEO_HEIGHT] == pa.int32()

        assert FIELD_VIDEO_FPS in schema
        assert schema[FIELD_VIDEO_FPS] == pa.float64()

        assert FIELD_VIDEO_CODEC in schema
        assert schema[FIELD_VIDEO_CODEC] == pa.string()

        assert FIELD_VIDEO_BITRATE in schema
        assert schema[FIELD_VIDEO_BITRATE] == pa.int64()

        assert FIELD_AUDIO_CODEC in schema
        assert schema[FIELD_AUDIO_CODEC] == pa.string()

        assert FIELD_AUDIO_SAMPLE_RATE in schema
        assert schema[FIELD_AUDIO_SAMPLE_RATE] == pa.int32()

        assert FIELD_AUDIO_CHANNELS in schema
        assert schema[FIELD_AUDIO_CHANNELS] == pa.int32()

        assert FIELD_VIDEO_METADATA in schema
        assert schema[FIELD_VIDEO_METADATA] == pa.string()

    def test_get_output_schema_without_full_metadata(self):
        """Test output schema without full metadata."""
        refiner = VideoMetadataRefiner(include_full_metadata=False)
        schema = refiner.get_output_schema()

        assert FIELD_VIDEO_METADATA not in schema
        assert FIELD_VIDEO_WIDTH in schema

    def test_cleanup_batch(self, temp_dir):
        """Test batch cleanup."""
        refiner = VideoMetadataRefiner(cache_dir=temp_dir)

        # Cleanup should work even with no downloads
        cleaned = refiner.cleanup_batch()
        assert cleaned == 0


class TestVideoMetadataRefinerWithMock:
    """Tests using mocked FFprobe responses."""

    def test_refine_with_mocked_metadata(self):
        """Test refining with mocked metadata extraction."""
        mock_metadata = {
            "format": {
                "duration": 120.5,
                "size": 15728640,
                "bit_rate": 1048576,
            },
            "streams": [],
            "video": {
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "fps": 29.97,
                "bit_rate": 1000000,
            },
            "audio": {
                "codec_name": "aac",
                "sample_rate": 48000,
                "channels": 2,
            },
        }

        refiner = VideoMetadataRefiner()

        with patch.object(refiner._video_loader, "load", return_value="/fake/path.mp4"):
            with patch(
                "mega_data_factory.operators.refiners.video_metadata.extract_video_metadata",
                return_value=mock_metadata,
            ):
                records = [{"video_path": "/some/video.mp4"}]
                refiner.refine_batch(records)

                record = records[0]
                assert record[FIELD_VIDEO_DURATION] == 120.5
                assert record[FIELD_VIDEO_WIDTH] == 1920
                assert record[FIELD_VIDEO_HEIGHT] == 1080
                assert record[FIELD_VIDEO_FPS] == 29.97
                assert record[FIELD_VIDEO_CODEC] == "h264"
                assert record[FIELD_AUDIO_CODEC] == "aac"
                assert record[FIELD_AUDIO_SAMPLE_RATE] == 48000
                assert record[FIELD_AUDIO_CHANNELS] == 2

    def test_refine_with_failed_extraction(self):
        """Test refining when metadata extraction fails."""
        refiner = VideoMetadataRefiner()

        with patch.object(refiner._video_loader, "load", return_value="/fake/path.mp4"):
            with patch(
                "mega_data_factory.operators.refiners.video_metadata.extract_video_metadata",
                return_value=None,
            ):
                records = [{"video_path": "/some/video.mp4"}]
                refiner.refine_batch(records)

                record = records[0]
                assert record[FIELD_VIDEO_DURATION] is None
                assert record[FIELD_VIDEO_WIDTH] is None

    def test_refine_with_failed_load(self):
        """Test refining when video loading fails."""
        refiner = VideoMetadataRefiner()

        with patch.object(refiner._video_loader, "load", return_value=None):
            records = [{"video_url": "https://example.com/video.mp4"}]
            refiner.refine_batch(records)

            record = records[0]
            assert record[FIELD_VIDEO_DURATION] is None
            assert record[FIELD_VIDEO_WIDTH] is None


class TestVideoMetadataRefinerIntegration:
    """Integration tests for VideoMetadataRefiner."""

    @pytest.mark.skipif(not ffprobe_available(), reason="FFprobe not available")
    def test_full_pipeline_simulation(self, sample_video, temp_dir):
        """Test a full pipeline simulation with multiple batches."""
        refiner = VideoMetadataRefiner(
            cache_dir=temp_dir,
            include_full_metadata=True,
        )

        # Process first batch
        batch1 = [
            {"video_path": sample_video},
            {"video_path": sample_video},  # Duplicate
        ]
        refiner.refine_batch(batch1)

        assert batch1[0][FIELD_VIDEO_WIDTH] == 320
        assert batch1[1][FIELD_VIDEO_WIDTH] == 320

        # Cleanup first batch
        refiner.cleanup_batch()

        # Process second batch
        batch2 = [{"video_path": sample_video}]
        refiner.refine_batch(batch2)

        assert batch2[0][FIELD_VIDEO_WIDTH] == 320

        # Final cleanup
        refiner.cleanup_batch()

    @pytest.mark.skipif(not ffprobe_available(), reason="FFprobe not available")
    def test_metadata_json_parsing(self, sample_video):
        """Test that metadata JSON can be parsed and used."""
        refiner = VideoMetadataRefiner()

        records = [{"video_path": sample_video}]
        refiner.refine_batch(records)

        # Parse the JSON metadata
        metadata = json.loads(records[0][FIELD_VIDEO_METADATA])

        # Verify structure
        assert "format" in metadata
        assert "streams" in metadata
        assert "video" in metadata

        # Verify we can access nested data
        assert metadata["format"]["duration"] > 0
        assert metadata["video"]["width"] == 320
        assert metadata["video"]["height"] == 240

        # Verify streams list
        assert len(metadata["streams"]) >= 1
        video_streams = [s for s in metadata["streams"] if s["codec_type"] == "video"]
        assert len(video_streams) == 1
