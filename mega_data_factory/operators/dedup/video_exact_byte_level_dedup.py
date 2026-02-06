"""
Video Exact Byte-Level Deduplication

Deduplicates video records based on exact file hash (byte-level comparison).
Uses cryptographic hashing (SHA-256 or MD5) to identify identical video files.
"""

import logging

from mega_data_factory.operators.dedup.video_deduplicator import VideoDeduplicator
from mega_data_factory.utils.video_utils import compute_file_hash

logger = logging.getLogger(__name__)


class VideoExactByteLevelDeduplicator(VideoDeduplicator):
    """Deduplicates video records based on exact file hash.

    Computes cryptographic hash (SHA-256 or MD5) of the entire video file
    to identify exact duplicates. This is a byte-level comparison that
    considers the entire file including container metadata.

    Two videos are considered duplicates only if they are byte-for-byte identical.
    Videos with the same content but different containers/encodings will NOT
    be detected as duplicates. For content-level deduplication, use
    VideoExactStreamLevelDeduplicator instead.

    Features:
    - Supports local files and remote URLs (with caching)
    - Configurable hash algorithm (SHA-256, MD5, SHA-512)
    - Memory-efficient streaming hash computation

    Reference:
    - Similar to file deduplication in backup systems
    - Fast and reliable for exact duplicate detection
    """

    def __init__(
        self,
        video_field: str = "video",
        video_url_field: str = "video_url",
        video_path_field: str = "video_path",
        hash_algorithm: str = "sha256",
        cache_dir: str | None = None,
        download_timeout: int = 60,
        max_file_size: int | None = None,
    ):
        """Initialize video byte-level deduplicator.

        Args:
            video_field: Field name for video data (dict with "path" key, or path string).
            video_url_field: Field name for video URL.
            video_path_field: Field name for video file path.
            hash_algorithm: Hash algorithm: "sha256", "md5", "sha512".
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

    def get_existing_hash_fields(self) -> list[str]:
        """Get field names to check for pre-computed hash."""
        return ["video_hash", "file_hash"]

    def compute_hash(self, file_path: str) -> str | None:
        """Compute file hash from video file.

        Args:
            file_path: Path to the video file.

        Returns:
            Hash string or None if computation failed.
        """
        try:
            return compute_file_hash(file_path, self.hash_algorithm)
        except OSError as e:
            logger.warning(f"Failed to read video file {file_path}: {e}")
            return None
