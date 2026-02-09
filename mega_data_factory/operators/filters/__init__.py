"""Filter operators package - lazy loaded to avoid heavy dependencies."""

from mega_data_factory.framework import OperatorRegistry

from .text_alphabetic_word_ration_filter import TextAlphabeticWordRationFilter
from .text_avg_word_length_filter import TextAvgWordLengthFilter
from .text_bullet_filter import TextBulletFilter
from .text_ellipsis_line_ratio_filter import TextEllipsisLineRatioFilter
from .text_length_filter import TextLengthFilter
from .text_repetition_filter import TextRepetitionFilter
from .text_symbol_ratio_filter import TextSymbolRatioFilter
from .url_filter import URLFilter

# Register text-only filters (no heavy dependencies)
OperatorRegistry.register("TextLengthFilter", TextLengthFilter)
OperatorRegistry.register("UrlFilter", URLFilter)
OperatorRegistry.register("TextAlphabeticWordRationFilter", TextAlphabeticWordRationFilter)
OperatorRegistry.register("TextAvgWordLengthFilter", TextAvgWordLengthFilter)
OperatorRegistry.register("TextBulletFilter", TextBulletFilter)
OperatorRegistry.register("TextEllipsisLineRatioFilter", TextEllipsisLineRatioFilter)
OperatorRegistry.register("TextRepetitionFilter", TextRepetitionFilter)
OperatorRegistry.register("TextSymbolRatioFilter", TextSymbolRatioFilter)


def _register_image_filters():
    """Lazy register image filters that depend on PIL."""
    from .image_quality_filter import ImageQualityFilter
    OperatorRegistry.register("ImageQualityFilter", ImageQualityFilter)


# Defer heavy imports
try:
    _register_image_filters()
except ImportError:
    pass  # Skip if PIL not available


__all__ = [
    "TextLengthFilter",
    "URLFilter",
    "TextAlphabeticWordRationFilter",
    "TextAvgWordLengthFilter",
    "TextBulletFilter",
    "TextEllipsisLineRatioFilter",
    "TextRepetitionFilter",
    "TextSymbolRatioFilter",
]
