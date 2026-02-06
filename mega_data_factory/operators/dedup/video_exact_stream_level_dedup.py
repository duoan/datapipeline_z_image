"""
Video Exact Stream-Level Deduplication

Deduplicates video records based on raw stream hash (content-level comparison).
Uses FFmpeg to extract raw video/audio streams and compute hash, ignoring container metadata.
"""

import logging

from mega_data_factory.operators.dedup.video_deduplicator import VideoDeduplicator
from mega_data_factory.utils.video_utils import compute_stream_hash

logger = logging.getLogger(__name__)


class VideoExactStreamLevelDeduplicator(VideoDeduplicator):
    """Deduplicates video records based on raw stream hash.

    Uses FFmpeg to extract raw video frames and compute hash, ignoring
    container metadata. This allows detecting duplicates even when videos
    have different containers (e.g., MP4 vs MKV) or metadata.

    Two videos are considered duplicates if their decoded video frames
    are identical, regardless of:
    - Container format (MP4, MKV, AVI, etc.)
    - Metadata (title, author, creation date, etc.)
    - Encoding settings (as long as decoded frames are identical)

    For byte-level comparison (faster but stricter), use
    VideoExactByteLevelDeduplicator instead.

    Features:
    - Container-agnostic deduplication
    - Supports local files and remote URLs (with caching)
    - Optional audio stream inclusion in hash

    Requirements:
    - FFmpeg must be installed and available in PATH

    Reference:
    - FFmpeg rawvideo format for consistent frame extraction
    - Similar to video fingerprinting in content identification systems
    """

    def __init__(
        self,
        video_field: str = "video",
        video_url_field: str = "video_url",
        video_path_field: str = "video_path",
        hash_algorithm: str = "md5",
        include_audio: bool = False,
        cache_dir: str | None = None,
        download_timeout: int = 120,
        max_file_size: int | None = None,
    ):
        """Initialize video stream-level deduplicator.

        Args:
            video_field: Field name for video data (dict with "path" key, or path string).
            video_url_field: Field name for video URL.
            video_path_field: Field name for video file path.
            hash_algorithm: Hash algorithm: "md5", "sha256".
            include_audio: Whether to include audio stream in hash computation.
            cache_dir: Directory to cache downloaded videos. None for system temp.
            download_timeout: Timeout in seconds for downloading videos.
            max_file_size: Maximum file size in bytes to process. None for no limit.
        """
        super().__init__(
            video_field=video_field,
            video_url_field=video_url_field,
            video_path_field=video_path_field,
            cache_dir=cache_dir,
            download_timeout=download_timeout,
            max_file_size=max_file_size,
        )
        self.hash_algorithm = hash_algorithm
        self.include_audio = include_audio

    def get_existing_hash_fields(self) -> list[str]:
        """Get field names to check for pre-computed hash."""
        return ["video_stream_hash", "stream_hash"]

    def compute_hash(self, file_path: str) -> str | None:
        """Compute stream hash from video file.

        Args:
            file_path: Path to the video file.

        Returns:
            Hash string or None if computation failed.
        """
        return compute_stream_hash(
            file_path,
            algorithm=self.hash_algorithm,
            include_audio=self.include_audio,
        )
