"""Deduplication operators package - lazy loaded to avoid heavy dependencies."""

from mega_data_factory.framework import OperatorRegistry

# Text dedup (no heavy dependencies)
from .text_exact_dedup import TextExactDeduplicator

# Video dedup (minimal dependencies - requests for URL loading)
from .video_deduplicator import VideoDeduplicator
from .video_exact_byte_level_dedup import VideoExactByteLevelDeduplicator
from .video_exact_stream_level_dedup import VideoExactStreamLevelDeduplicator

OperatorRegistry.register("TextExactDeduplicator", TextExactDeduplicator)
OperatorRegistry.register("VideoExactByteLevelDeduplicator", VideoExactByteLevelDeduplicator)
OperatorRegistry.register("VideoExactStreamLevelDeduplicator", VideoExactStreamLevelDeduplicator)


def _register_image_dedup():
    """Lazy register image dedup that depends on PIL."""
    from .image_phash_dedup import ImagePhashDeduplicator

    OperatorRegistry.register("ImagePhashDeduplicator", ImagePhashDeduplicator)


try:
    _register_image_dedup()
except ImportError:
    pass


__all__ = [
    "TextExactDeduplicator",
    "VideoDeduplicator",
    "VideoExactByteLevelDeduplicator",
    "VideoExactStreamLevelDeduplicator",
]
