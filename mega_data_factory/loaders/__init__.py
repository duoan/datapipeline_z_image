"""Data Loaders package."""

from mega_data_factory.framework import DataLoaderRegistry

from .commoncrawl_loader import CommonCrawlLoader
from .huggingface_loader import HuggingFaceLoader
from .resiliparse_commoncrawl_loader import ResiliparseCommonCrawlLoader

DataLoaderRegistry.register("HuggingFaceLoader", HuggingFaceLoader)
DataLoaderRegistry.register("CommonCrawlLoader", CommonCrawlLoader)
DataLoaderRegistry.register("ResiliparseCommonCrawlLoader", ResiliparseCommonCrawlLoader)

__all__ = ["HuggingFaceLoader", "CommonCrawlLoader", "ResiliparseCommonCrawlLoader"]
