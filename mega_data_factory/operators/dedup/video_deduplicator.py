"""
Video Deduplicator Base Class

Base class for video deduplication operators that handles video loading,
downloading, and caching. Subclasses only need to implement the hash
computation logic.
"""

import logging
import uuid
from abc import abstractmethod
from typing import Any

from mega_data_factory.framework import Deduplicator
from mega_data_factory.operators.video_operator import VideoOperatorMixin

logger = logging.getLogger(__name__)


class VideoDeduplicator(VideoOperatorMixin, Deduplicator):
    """Base class for video deduplication operators.

    Handles common video loading operations:
    - Loading videos from file paths
    - Downloading and caching videos from URLs
    - Extracting video data from various record formats

    Subclasses must implement:
    - compute_hash(file_path: str) -> str | None: Compute hash from local file
    - get_existing_hash_fields() -> list[str]: Fields to check for pre-computed hash
    """

    def __init__(
        self,
        video_field: str = "video",
        video_url_field: str = "video_url",
        video_path_field: str = "video_path",
        cache_dir: str | None = None,
        download_timeout: int = 60,
        max_file_size: int | None = None,
    ):
        """Initialize video deduplicator.

        Args:
            video_field: Field name for video data (dict with "path" key, or path string).
            video_url_field: Field name for video URL.
            video_path_field: Field name for video file path.
            cache_dir: Directory to cache downloaded videos. None for system temp.
            download_timeout: Timeout in seconds for downloading videos.
            max_file_size: Maximum file size in bytes to process. None for no limit.
        """
        super().__init__()

        # Initialize video loading functionality from mixin
        self._init_video_loader(
            video_field=video_field,
            video_url_field=video_url_field,
            video_path_field=video_path_field,
            cache_dir=cache_dir,
            timeout=download_timeout,
            max_file_size=max_file_size,
        )

    @abstractmethod
    def compute_hash(self, file_path: str) -> str | None:
        """Compute hash from a local video file.

        Args:
            file_path: Path to the local video file.

        Returns:
            Hash string or None if computation failed.
        """
        pass

    def get_existing_hash_fields(self) -> list[str]:
        """Get field names to check for pre-computed hash.

        Override this method to specify which record fields contain
        pre-computed hashes that can be used directly.

        Returns:
            List of field names to check for existing hash.
        """
        return []

    def _get_video_hash(self, record: dict[str, Any]) -> str | None:
        """Get hash for a video record.

        Args:
            record: Record containing video data.

        Returns:
            Hash string or None if video cannot be processed.
        """
        local_path = self._get_local_video_path(record)
        if local_path:
            return self.compute_hash(local_path)
        return None

    def get_dedup_keys_batch(self, records: list[dict[str, Any]]) -> list[str]:
        """Compute hashes for a batch of video records.

        Note: Downloaded video files are NOT automatically cleaned up after this method.
        The cleanup should be done at the worker/stage level after all operators have
        processed the batch. Call cleanup_batch() explicitly when ready to clean up.

        Returns:
            List of hash strings. Empty string for records that cannot be processed.
        """
        keys = []
        existing_hash_fields = self.get_existing_hash_fields()

        for record in records:
            # Check if hash is already computed and stored in record
            existing_hash = None
            for field in existing_hash_fields:
                existing_hash = record.get(field)
                if existing_hash:
                    break

            if existing_hash:
                keys.append(existing_hash)
                continue

            # Compute hash
            video_hash = self._get_video_hash(record)
            if video_hash:
                keys.append(video_hash)
            else:
                # Use record ID as fallback, or generate a unique key if no ID
                # This ensures records without computable hashes are NOT deduplicated
                record_id = record.get("id")
                if record_id:
                    # Use a prefix to distinguish from actual hashes
                    keys.append(f"__fallback_id__{record_id}")
                else:
                    # Generate a unique key to ensure this record is not deduplicated
                    keys.append(f"__fallback_uuid__{uuid.uuid4().hex}")
                logger.warning(
                    f"Could not compute video hash for record, using fallback key. Record ID: {record.get('id', 'N/A')}"
                )

        return keys
