"""
Utility modules for mega_data_factory.

This package contains shared utilities used across different components.
"""

from .resiliparse_utils import (
    MIN_TEXT_LENGTH_FOR_DETECTION,
    UNKNOWN_LANGUAGE,
    UNKNOWN_LANGUAGE_SCORE,
    TextExtractionResult,
    decode_html_content,
    detect_language_fast,
    extract_text_from_html,
    get_text_from_record,
)
from .video_utils import (
    VideoLoader,
    compute_file_hash,
    compute_stream_hash,
    extract_video_metadata,
    get_video_frame,
    get_video_frames,
    get_video_from_record,
)

__all__ = [
    # Resiliparse utilities
    "TextExtractionResult",
    "decode_html_content",
    "detect_language_fast",
    "extract_text_from_html",
    "get_text_from_record",
    # Constants
    "UNKNOWN_LANGUAGE",
    "UNKNOWN_LANGUAGE_SCORE",
    "MIN_TEXT_LENGTH_FOR_DETECTION",
    # Video utilities
    "VideoLoader",
    "compute_file_hash",
    "compute_stream_hash",
    "extract_video_metadata",
    "get_video_frame",
    "get_video_frames",
    "get_video_from_record",
]
