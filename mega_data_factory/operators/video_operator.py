"""
Video Operator Mixin

Provides common video loading functionality for video processing operators.
This mixin can be used by any operator that needs to load videos from
URLs or local file paths.
"""

import logging
from pathlib import Path
from typing import Any

from mega_data_factory.utils.video_utils import VideoLoader, get_video_from_record

logger = logging.getLogger(__name__)


class VideoOperatorMixin:
    """Mixin class providing video loading functionality for operators.

    This mixin provides:
    - Video loading from file paths and URLs
    - Automatic caching of downloaded videos
    - File size validation
    - Batch cleanup of downloaded files

    Usage:
        class MyVideoOperator(VideoOperatorMixin, Operator):
            def __init__(self, video_field="video", **kwargs):
                super().__init__(**kwargs)
                self._init_video_loader(video_field=video_field)

            def process(self, record):
                local_path = self._get_local_video_path(record)
                if local_path:
                    # Process the video
                    pass
    """

    # Video loader instance (initialized by _init_video_loader)
    _video_loader: VideoLoader

    # Configuration attributes (set by _init_video_loader)
    video_field: str
    video_url_field: str
    video_path_field: str
    max_file_size: int | None

    def _init_video_loader(
        self,
        video_field: str = "video",
        video_url_field: str = "video_url",
        video_path_field: str = "video_path",
        cache_dir: str | None = None,
        timeout: int = 60,
        max_file_size: int | None = None,
        persistent_cache: bool = False,
    ) -> None:
        """Initialize video loading functionality.

        This method should be called in the __init__ of classes using this mixin.

        Args:
            video_field: Field name for video data (dict with "path" key, or path string).
            video_url_field: Field name for video URL.
            video_path_field: Field name for video file path.
            cache_dir: Directory to cache downloaded videos. None for system temp.
            timeout: Timeout in seconds for downloading videos.
            max_file_size: Maximum file size in bytes to process. None for no limit.
            persistent_cache: If True, keep downloaded files across batches.
        """
        self.video_field = video_field
        self.video_url_field = video_url_field
        self.video_path_field = video_path_field
        self.max_file_size = max_file_size

        self._video_loader = VideoLoader(
            cache_dir=cache_dir,
            timeout=timeout,
            max_file_size=max_file_size,
            persistent_cache=persistent_cache,
        )

    def _check_file_size(self, file_path: str) -> bool:
        """Check if file size is within limit.

        Args:
            file_path: Path to the file.

        Returns:
            True if file size is acceptable, False otherwise.
        """
        if not self.max_file_size:
            return True

        try:
            file_size = Path(file_path).stat().st_size
            if file_size > self.max_file_size:
                logger.warning(f"Video file too large: {file_size} > {self.max_file_size}")
                return False
            return True
        except OSError as e:
            logger.warning(f"Failed to check file size: {e}")
            return False

    def _get_local_video_path(self, record: dict[str, Any]) -> str | None:
        """Get local video path from record.

        Handles multiple input formats:
        - File path in video field or video_path_field
        - URL in video_url_field (downloads and caches)

        Args:
            record: Record containing video data.

        Returns:
            Local file path or None if video cannot be loaded.
        """
        video_data = get_video_from_record(
            record,
            video_field=self.video_field,
            video_url_field=self.video_url_field,
            video_path_field=self.video_path_field,
        )

        if video_data is None:
            return None

        # Handle file path or URL (string)
        if isinstance(video_data, str):
            # Load video (downloads if URL, returns path if local)
            local_path = self._video_loader.load(video_data)
            if local_path and self._check_file_size(local_path):
                return local_path

        # Bytes are not supported (memory-unfriendly for videos)
        if isinstance(video_data, (bytes, bytearray, memoryview)):
            logger.warning("In-memory video bytes not supported. Use file path or URL.")
            return None

        return None

    def cleanup_batch(self) -> int:
        """Clean up downloaded video files from the current batch.

        This method should be called after all operators in a stage have processed
        the batch. It removes temporary video files that were downloaded from URLs.

        The RayWorker calls this method automatically after processing each batch.

        Returns:
            Number of files cleaned up.
        """
        return self._video_loader.cleanup_batch()
