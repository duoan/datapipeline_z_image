"""
Video Metadata Refiner

Extracts comprehensive video metadata using FFprobe and stores it as a JSON field.
This is a Refiner that enriches records with video metadata information.
"""

import json
import logging
from typing import Any

import pyarrow as pa

from mega_data_factory.framework import Refiner
from mega_data_factory.operators.video_operator import VideoOperatorMixin
from mega_data_factory.utils import extract_video_metadata

logger = logging.getLogger(__name__)

# Field name constants
FIELD_VIDEO_METADATA = "video_metadata"
FIELD_VIDEO_DURATION = "video_duration"
FIELD_VIDEO_WIDTH = "video_width"
FIELD_VIDEO_HEIGHT = "video_height"
FIELD_VIDEO_FPS = "video_fps"
FIELD_VIDEO_CODEC = "video_codec"
FIELD_VIDEO_BITRATE = "video_bitrate"
FIELD_AUDIO_CODEC = "audio_codec"
FIELD_AUDIO_SAMPLE_RATE = "audio_sample_rate"
FIELD_AUDIO_CHANNELS = "audio_channels"

OUTPUT_FIELDS = [
    FIELD_VIDEO_METADATA,
    FIELD_VIDEO_DURATION,
    FIELD_VIDEO_WIDTH,
    FIELD_VIDEO_HEIGHT,
    FIELD_VIDEO_FPS,
    FIELD_VIDEO_CODEC,
    FIELD_VIDEO_BITRATE,
    FIELD_AUDIO_CODEC,
    FIELD_AUDIO_SAMPLE_RATE,
    FIELD_AUDIO_CHANNELS,
]


class VideoMetadataRefiner(VideoOperatorMixin, Refiner):
    """Refiner for extracting comprehensive video metadata using FFprobe.

    This refiner downloads/loads videos and extracts metadata including:
    - Format information (duration, size, bitrate)
    - Video stream details (codec, resolution, fps, color space)
    - Audio stream details (codec, sample rate, channels)
    - Container metadata (tags, etc.)

    The full metadata is stored as a JSON string in the `video_metadata` field,
    while commonly used fields are extracted as separate columns for easy filtering.

    Configuration:
        video_field: Field name for video data (default: "video")
        video_url_field: Field name for video URL (default: "video_url")
        video_path_field: Field name for video path (default: "video_path")
        cache_dir: Directory to cache downloaded videos (default: system temp)
        timeout: Download timeout in seconds (default: 60)
        max_file_size: Maximum file size in bytes (default: None)
        persistent_cache: Keep cache across batches (default: False)
        include_full_metadata: Include full JSON metadata (default: True)

    Output fields:
        video_metadata: Full metadata as JSON string (if include_full_metadata=True)
        video_duration: Duration in seconds
        video_width: Video width in pixels
        video_height: Video height in pixels
        video_fps: Frames per second
        video_codec: Video codec name
        video_bitrate: Video bitrate in bits/second
        audio_codec: Audio codec name
        audio_sample_rate: Audio sample rate in Hz
        audio_channels: Number of audio channels
    """

    def __init__(
        self,
        video_field: str = "video",
        video_url_field: str = "video_url",
        video_path_field: str = "video_path",
        cache_dir: str | None = None,
        timeout: int = 60,
        max_file_size: int | None = None,
        persistent_cache: bool = False,
        include_full_metadata: bool = True,
        **kwargs: Any,
    ):
        """Initialize video metadata refiner.

        Args:
            video_field: Field name for video data (dict with bytes/path, or direct path).
            video_url_field: Field name for video URL.
            video_path_field: Field name for video file path.
            cache_dir: Directory to cache downloaded videos.
            timeout: Download timeout in seconds.
            max_file_size: Maximum file size in bytes to download.
            persistent_cache: If True, keep downloaded files across batches.
            include_full_metadata: If True, include full JSON metadata field.
            **kwargs: Additional arguments passed to parent class.
        """
        super().__init__(**kwargs)
        self.include_full_metadata = include_full_metadata

        # Initialize video loading functionality from mixin
        self._init_video_loader(
            video_field=video_field,
            video_url_field=video_url_field,
            video_path_field=video_path_field,
            cache_dir=cache_dir,
            timeout=timeout,
            max_file_size=max_file_size,
            persistent_cache=persistent_cache,
        )

    def refine_batch(self, records: list[dict[str, Any]]) -> None:
        """Extract video metadata for a batch of records (inplace).

        Args:
            records: List of records to process. Modified in place.
        """
        for record in records:
            # Get local video path using mixin method
            local_path = self._get_local_video_path(record)

            if not local_path:
                logger.warning(f"Failed to load video for record: {record.get('id', 'N/A')}")
                self._set_empty_metadata(record)
                continue

            # Extract metadata using FFprobe
            metadata = extract_video_metadata(local_path)
            if not metadata:
                logger.warning(f"Failed to extract metadata from: {local_path}")
                self._set_empty_metadata(record)
                continue

            # Set metadata fields
            self._set_metadata_fields(record, metadata)

    def _set_empty_metadata(self, record: dict[str, Any]) -> None:
        """Set empty/default values for all metadata fields."""
        if self.include_full_metadata:
            record[FIELD_VIDEO_METADATA] = None
        record[FIELD_VIDEO_DURATION] = None
        record[FIELD_VIDEO_WIDTH] = None
        record[FIELD_VIDEO_HEIGHT] = None
        record[FIELD_VIDEO_FPS] = None
        record[FIELD_VIDEO_CODEC] = None
        record[FIELD_VIDEO_BITRATE] = None
        record[FIELD_AUDIO_CODEC] = None
        record[FIELD_AUDIO_SAMPLE_RATE] = None
        record[FIELD_AUDIO_CHANNELS] = None

    def _set_metadata_fields(self, record: dict[str, Any], metadata: dict[str, Any]) -> None:
        """Set metadata fields from extracted metadata."""
        # Full metadata as JSON
        if self.include_full_metadata:
            record[FIELD_VIDEO_METADATA] = json.dumps(metadata, ensure_ascii=False)

        # Format-level fields
        fmt = metadata.get("format", {})
        record[FIELD_VIDEO_DURATION] = fmt.get("duration")

        # Video stream fields
        video = metadata.get("video")
        if video:
            record[FIELD_VIDEO_WIDTH] = video.get("width")
            record[FIELD_VIDEO_HEIGHT] = video.get("height")
            record[FIELD_VIDEO_FPS] = video.get("fps")
            record[FIELD_VIDEO_CODEC] = video.get("codec_name")
            record[FIELD_VIDEO_BITRATE] = video.get("bit_rate")
        else:
            record[FIELD_VIDEO_WIDTH] = None
            record[FIELD_VIDEO_HEIGHT] = None
            record[FIELD_VIDEO_FPS] = None
            record[FIELD_VIDEO_CODEC] = None
            record[FIELD_VIDEO_BITRATE] = None

        # Audio stream fields
        audio = metadata.get("audio")
        if audio:
            record[FIELD_AUDIO_CODEC] = audio.get("codec_name")
            record[FIELD_AUDIO_SAMPLE_RATE] = audio.get("sample_rate")
            record[FIELD_AUDIO_CHANNELS] = audio.get("channels")
        else:
            record[FIELD_AUDIO_CODEC] = None
            record[FIELD_AUDIO_SAMPLE_RATE] = None
            record[FIELD_AUDIO_CHANNELS] = None

    def get_output_schema(self) -> dict[str, pa.DataType]:
        """Return output schema for new fields added by this refiner."""
        schema = {
            FIELD_VIDEO_DURATION: pa.float64(),
            FIELD_VIDEO_WIDTH: pa.int32(),
            FIELD_VIDEO_HEIGHT: pa.int32(),
            FIELD_VIDEO_FPS: pa.float64(),
            FIELD_VIDEO_CODEC: pa.string(),
            FIELD_VIDEO_BITRATE: pa.int64(),
            FIELD_AUDIO_CODEC: pa.string(),
            FIELD_AUDIO_SAMPLE_RATE: pa.int32(),
            FIELD_AUDIO_CHANNELS: pa.int32(),
        }

        if self.include_full_metadata:
            schema[FIELD_VIDEO_METADATA] = pa.string()

        return schema
