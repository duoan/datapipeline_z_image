"""
Video Utilities

Provides video loading, caching, hashing, and metadata extraction utilities
for video processing operators.
"""

import hashlib
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Default cache directory for downloaded videos
DEFAULT_CACHE_DIR = os.path.join(tempfile.gettempdir(), "mega_data_factory_video_cache")


class VideoLoader:
    """Video loader with caching support.

    Downloads videos from URLs and caches them locally to avoid redundant downloads.
    Supports both local file paths and remote URLs.

    The loader tracks downloaded files during batch processing and provides
    cleanup_batch() to remove temporary files after processing is complete.
    """

    def __init__(
        self,
        cache_dir: str | None = None,
        timeout: int = 60,
        max_file_size: int | None = None,
        persistent_cache: bool = False,
    ):
        """Initialize video loader.

        Args:
            cache_dir: Directory to cache downloaded videos. If None, uses system temp dir.
            timeout: Request timeout in seconds for downloading videos.
            max_file_size: Maximum file size in bytes to download. None for no limit.
            persistent_cache: If True, keep downloaded files across batches.
                              If False (default), files are cleaned up after each batch.
        """
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.timeout = timeout
        self.max_file_size = max_file_size
        self.persistent_cache = persistent_cache

        # Track files downloaded in current batch for cleanup
        self._batch_downloaded_files: set[str] = set()

        # Create cache directory if it doesn't exist
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, url_or_path: str) -> str:
        """Generate a cache key from URL or path."""
        return hashlib.md5(url_or_path.encode("utf-8")).hexdigest()

    def _get_cache_path(self, url_or_path: str) -> Path:
        """Get the cache file path for a given URL or path."""
        cache_key = self._get_cache_key(url_or_path)
        # Try to preserve extension from URL
        parsed = urlparse(url_or_path)
        path = parsed.path if parsed.scheme else url_or_path
        ext = Path(path).suffix or ".mp4"
        return Path(self.cache_dir) / f"{cache_key}{ext}"

    def _is_url(self, path: str) -> bool:
        """Check if the path is a URL."""
        parsed = urlparse(path)
        return parsed.scheme in ("http", "https", "ftp", "s3", "gs")

    def _download_video(self, url: str, cache_path: Path) -> bool:
        """Download video from URL to cache path.

        Returns:
            True if download succeeded, False otherwise.
        """
        logger.info(f"Starting video download: {url}")
        try:
            # Stream download to handle large files
            with requests.get(url, stream=True, timeout=self.timeout) as response:
                response.raise_for_status()

                # Check content length if max_file_size is set
                content_length = response.headers.get("content-length")
                content_length_mb = int(content_length) / (1024 * 1024) if content_length else None

                if content_length:
                    logger.info(f"Video size: {content_length_mb:.2f} MB from {url}")
                else:
                    logger.info(f"Video size unknown (no Content-Length header) from {url}")

                if content_length and self.max_file_size:
                    if int(content_length) > self.max_file_size:
                        max_size_mb = self.max_file_size / (1024 * 1024)
                        logger.warning(
                            f"Video too large: {content_length_mb:.2f} MB > {max_size_mb:.2f} MB limit, skipping {url}"
                        )
                        return False

                # Download to temporary file first, then move to cache
                temp_path = cache_path.with_suffix(".tmp")
                total_size = 0
                with open(temp_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            total_size += len(chunk)
                            if self.max_file_size and total_size > self.max_file_size:
                                max_size_mb = self.max_file_size / (1024 * 1024)
                                logger.warning(
                                    f"Video exceeded max size during download: "
                                    f"{total_size / (1024 * 1024):.2f} MB > {max_size_mb:.2f} MB, "
                                    f"aborting {url}"
                                )
                                temp_path.unlink(missing_ok=True)
                                return False

                # Move temp file to cache
                temp_path.rename(cache_path)

                # Track downloaded file for batch cleanup
                self._batch_downloaded_files.add(str(cache_path))

                total_size_mb = total_size / (1024 * 1024)
                logger.info(
                    f"Video download completed: {total_size_mb:.2f} MB saved to {cache_path.name} "
                    f"(source: {url[:80]}{'...' if len(url) > 80 else ''})"
                )
                return True

        except requests.RequestException as e:
            logger.warning(f"Failed to download video from {url}: {e}")
            return False
        except OSError as e:
            logger.warning(f"Failed to save video to cache {cache_path}: {e}")
            return False

    def load(self, url_or_path: str) -> str | None:
        """Load video and return local file path.

        If the input is a URL, downloads and caches the video.
        If the input is a local path, returns it directly.

        Args:
            url_or_path: URL or local file path to the video.

        Returns:
            Local file path to the video, or None if loading failed.
        """
        if not url_or_path:
            return None

        # Handle local files
        if not self._is_url(url_or_path):
            if Path(url_or_path).exists():
                logger.debug(f"Using local video file: {url_or_path}")
                return url_or_path
            logger.warning(f"Local video file not found: {url_or_path}")
            return None

        # Handle URLs - check cache first
        cache_path = self._get_cache_path(url_or_path)
        if cache_path.exists():
            cache_size_mb = cache_path.stat().st_size / (1024 * 1024)
            logger.info(
                f"Video cache hit: {cache_path.name} ({cache_size_mb:.2f} MB) "
                f"for {url_or_path[:60]}{'...' if len(url_or_path) > 60 else ''}"
            )
            return str(cache_path)

        # Download and cache
        if self._download_video(url_or_path, cache_path):
            return str(cache_path)

        return None

    def load_batch(self, urls_or_paths: list[str]) -> list[str | None]:
        """Load multiple videos and return local file paths.

        Args:
            urls_or_paths: List of URLs or local file paths.

        Returns:
            List of local file paths (or None for failed loads).
        """
        return [self.load(url_or_path) for url_or_path in urls_or_paths]

    def clear_cache(self):
        """Clear the video cache directory."""
        import shutil

        if Path(self.cache_dir).exists():
            shutil.rmtree(self.cache_dir)
            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
        self._batch_downloaded_files.clear()

    def cleanup_batch(self) -> int:
        """Clean up downloaded files from the current batch.

        Removes all files that were downloaded during the current batch processing.
        This should be called after each batch is processed to free up disk space.

        If persistent_cache is True, this method does nothing.

        Returns:
            Number of files cleaned up.
        """
        if self.persistent_cache:
            logger.debug("Skipping batch cleanup: persistent_cache is enabled")
            return 0

        if not self._batch_downloaded_files:
            return 0

        total_files = len(self._batch_downloaded_files)
        cleaned_count = 0
        total_size_bytes = 0

        for file_path in self._batch_downloaded_files:
            try:
                path = Path(file_path)
                if path.exists():
                    file_size = path.stat().st_size
                    path.unlink()
                    cleaned_count += 1
                    total_size_bytes += file_size
                    logger.debug(f"Cleaned up downloaded video: {file_path}")
            except OSError as e:
                logger.warning(f"Failed to clean up video file {file_path}: {e}")

        self._batch_downloaded_files.clear()

        total_size_mb = total_size_bytes / (1024 * 1024)
        logger.info(
            f"Batch cleanup completed: {cleaned_count}/{total_files} files removed, "
            f"{total_size_mb:.2f} MB freed"
        )
        return cleaned_count

    def get_batch_downloaded_count(self) -> int:
        """Get the number of files downloaded in the current batch.

        Returns:
            Number of files downloaded.
        """
        return len(self._batch_downloaded_files)


def compute_file_hash(file_path: str, algorithm: str = "sha256", chunk_size: int = 8192) -> str:
    """Compute cryptographic hash of a file.

    Args:
        file_path: Path to the file.
        algorithm: Hash algorithm ("md5", "sha256", "sha512").
        chunk_size: Size of chunks to read at a time.

    Returns:
        Hexadecimal hash string.
    """
    hash_obj = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def compute_stream_hash(
    file_path: str,
    algorithm: str = "md5",
    include_audio: bool = True,
) -> str | None:
    """Compute hash of raw video/audio stream using FFmpeg.

    This ignores container metadata and only hashes the actual media content.
    Two videos with identical frames but different containers will have the same hash.

    Args:
        file_path: Path to the video file.
        algorithm: Hash algorithm ("md5", "sha256").
        include_audio: Whether to include audio stream in hash.

    Returns:
        Hexadecimal hash string, or None if FFmpeg failed.
    """
    try:
        # Build FFmpeg command to extract raw video frames
        # Using rawvideo format with rgb24 pixel format for consistent output
        cmd = [
            "ffmpeg",
            "-i",
            file_path,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-an" if not include_audio else "-y",  # -an removes audio
            "-",  # Output to stdout
        ]

        if include_audio:
            # For audio+video, we need a different approach
            # Extract both streams and hash them together
            cmd = [
                "ffmpeg",
                "-i",
                file_path,
                "-map",
                "0:v:0",  # First video stream
                "-map",
                "0:a:0?",  # First audio stream (optional)
                "-f",
                "nut",  # NUT container for raw streams
                "-c:v",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-c:a",
                "pcm_s16le",  # Raw PCM audio
                "-",
            ]

        # Run FFmpeg and pipe output to hasher
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

        hash_obj = hashlib.new(algorithm)
        if process.stdout is not None:
            while True:
                chunk = process.stdout.read(65536)  # 64KB chunks
                if not chunk:
                    break
                hash_obj.update(chunk)

        process.wait()

        if process.returncode != 0:
            logger.warning(f"FFmpeg returned non-zero exit code: {process.returncode}")
            return None

        return hash_obj.hexdigest()

    except FileNotFoundError:
        logger.error("FFmpeg not found. Please install FFmpeg to use stream-level deduplication.")
        return None
    except Exception as e:
        logger.warning(f"Failed to compute stream hash for {file_path}: {e}")
        return None


def get_video_from_record(
    record: dict[str, Any],
    video_field: str = "video",
    video_url_field: str = "video_url",
    video_path_field: str = "video_path",
) -> str | bytes | None:
    """Extract video data from a record.

    Supports multiple field formats:
    - video_field: Dict with "bytes" or "path" key, or direct bytes/path
    - video_url_field: URL string
    - video_path_field: Local file path string

    Args:
        record: Data record.
        video_field: Field name for video data (dict or bytes).
        video_url_field: Field name for video URL.
        video_path_field: Field name for video file path.

    Returns:
        Video bytes, file path, or URL string. None if not found.
    """
    # Try video field first (can be dict with bytes/path, or direct bytes)
    video_data = record.get(video_field)
    if video_data is not None:
        if isinstance(video_data, dict):
            if "bytes" in video_data:
                return video_data["bytes"]
            if "path" in video_data:
                return video_data["path"]
        elif isinstance(video_data, bytes):
            return video_data
        elif isinstance(video_data, str):
            return video_data

    # Try URL field
    video_url = record.get(video_url_field)
    if video_url:
        return video_url

    # Try path field
    video_path = record.get(video_path_field)
    if video_path:
        return video_path

    return None


def extract_video_metadata(file_path: str) -> dict[str, Any] | None:
    """Extract video metadata using FFprobe.

    Uses FFprobe to extract comprehensive metadata from a video file,
    including format information, stream details, and container metadata.

    Args:
        file_path: Path to the video file.

    Returns:
        Dictionary containing video metadata, or None if extraction failed.
        The dictionary contains:
        - format: Container format information (duration, size, bitrate, etc.)
        - streams: List of stream information (video, audio, subtitle streams)
        - video: Primary video stream details (codec, resolution, fps, etc.)
        - audio: Primary audio stream details (codec, sample_rate, channels, etc.)
    """
    try:
        # Run ffprobe to get JSON metadata
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.warning(f"FFprobe failed for {file_path}: {result.stderr}")
            return None

        # Parse JSON output
        probe_data = json.loads(result.stdout)

        # Build structured metadata
        metadata: dict[str, Any] = {
            "format": {},
            "streams": [],
            "video": None,
            "audio": None,
        }

        # Extract format information
        if "format" in probe_data:
            fmt = probe_data["format"]
            metadata["format"] = {
                "filename": fmt.get("filename"),
                "format_name": fmt.get("format_name"),
                "format_long_name": fmt.get("format_long_name"),
                "duration": _safe_float(fmt.get("duration")),
                "size": _safe_int(fmt.get("size")),
                "bit_rate": _safe_int(fmt.get("bit_rate")),
                "nb_streams": _safe_int(fmt.get("nb_streams")),
                "nb_programs": _safe_int(fmt.get("nb_programs")),
                "start_time": _safe_float(fmt.get("start_time")),
                "tags": fmt.get("tags", {}),
            }

        # Extract stream information
        video_stream = None
        audio_stream = None

        for stream in probe_data.get("streams", []):
            stream_info = _extract_stream_info(stream)
            metadata["streams"].append(stream_info)

            # Track primary video and audio streams
            codec_type = stream.get("codec_type")
            if codec_type == "video" and video_stream is None:
                video_stream = stream_info
            elif codec_type == "audio" and audio_stream is None:
                audio_stream = stream_info

        metadata["video"] = video_stream
        metadata["audio"] = audio_stream

        return metadata

    except FileNotFoundError:
        logger.error("FFprobe not found. Please install FFmpeg to extract video metadata.")
        return None
    except subprocess.TimeoutExpired:
        logger.warning(f"FFprobe timed out for {file_path}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse FFprobe output for {file_path}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to extract metadata from {file_path}: {e}")
        return None


def _safe_float(value: Any) -> float | None:
    """Safely convert value to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value: Any) -> int | None:
    """Safely convert value to int."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _extract_stream_info(stream: dict[str, Any]) -> dict[str, Any]:
    """Extract relevant information from a stream dictionary."""
    codec_type = stream.get("codec_type")

    base_info = {
        "index": stream.get("index"),
        "codec_type": codec_type,
        "codec_name": stream.get("codec_name"),
        "codec_long_name": stream.get("codec_long_name"),
        "profile": stream.get("profile"),
        "duration": _safe_float(stream.get("duration")),
        "bit_rate": _safe_int(stream.get("bit_rate")),
        "tags": stream.get("tags", {}),
    }

    if codec_type == "video":
        # Add video-specific fields
        base_info.update(
            {
                "width": _safe_int(stream.get("width")),
                "height": _safe_int(stream.get("height")),
                "coded_width": _safe_int(stream.get("coded_width")),
                "coded_height": _safe_int(stream.get("coded_height")),
                "pix_fmt": stream.get("pix_fmt"),
                "level": stream.get("level"),
                "color_range": stream.get("color_range"),
                "color_space": stream.get("color_space"),
                "color_transfer": stream.get("color_transfer"),
                "color_primaries": stream.get("color_primaries"),
                "field_order": stream.get("field_order"),
                "refs": _safe_int(stream.get("refs")),
                "r_frame_rate": stream.get("r_frame_rate"),
                "avg_frame_rate": stream.get("avg_frame_rate"),
                "display_aspect_ratio": stream.get("display_aspect_ratio"),
                "sample_aspect_ratio": stream.get("sample_aspect_ratio"),
                "nb_frames": _safe_int(stream.get("nb_frames")),
                "fps": _parse_frame_rate(stream.get("r_frame_rate")),
            }
        )
    elif codec_type == "audio":
        # Add audio-specific fields
        base_info.update(
            {
                "sample_rate": _safe_int(stream.get("sample_rate")),
                "channels": _safe_int(stream.get("channels")),
                "channel_layout": stream.get("channel_layout"),
                "bits_per_sample": _safe_int(stream.get("bits_per_sample")),
                "nb_frames": _safe_int(stream.get("nb_frames")),
            }
        )
    elif codec_type == "subtitle":
        # Add subtitle-specific fields
        base_info.update(
            {
                "subtitle_codec": stream.get("codec_name"),
            }
        )

    return base_info


def _parse_frame_rate(frame_rate_str: str | None) -> float | None:
    """Parse frame rate string (e.g., '30000/1001') to float."""
    if not frame_rate_str:
        return None
    try:
        if "/" in frame_rate_str:
            num, den = frame_rate_str.split("/")
            return float(num) / float(den)
        return float(frame_rate_str)
    except (ValueError, ZeroDivisionError):
        return None
