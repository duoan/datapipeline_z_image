"""
Filter operators package.

This package contains filter implementations.
Filters are automatically registered when this package is imported.
"""

from mega_data_factory.framework import OperatorRegistry

from .image_quality_filter import ImageQualityFilter

# Register all filters with the framework
OperatorRegistry.register("ImageQualityFilter", ImageQualityFilter)

__all__ = [
    "ImageQualityFilter",
]
