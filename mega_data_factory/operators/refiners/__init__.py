"""Refiner operators package - lazy loaded to avoid heavy dependencies."""

from mega_data_factory.framework import OperatorRegistry

from .text_new_line_removal_refiner import TextNewLineRemovalRefiner

# Register text-only refiners (no heavy dependencies)
OperatorRegistry.register("TextNewLineRemovalRefiner", TextNewLineRemovalRefiner)


def _register_image_refiners():
    """Lazy register image refiners that depend on PIL/torch."""
    from .image_aesthetic_quality import ImageAestheticQualityRefiner
    from .image_aigc_detector import ImageAIGCDetectorRefiner
    from .image_clip_embedding import ImageClipEmbeddingRefiner
    from .image_metadata import ImageMetadataRefiner
    from .image_siglip_embedding import ImageSigLIPEmbeddingRefiner
    from .image_technical_quality import ImageTechnicalQualityRefiner
    from .image_visual_degradations import ImageVisualDegradationsRefiner

    OperatorRegistry.register("ImageMetadataRefiner", ImageMetadataRefiner)
    OperatorRegistry.register("ImageTechnicalQualityRefiner", ImageTechnicalQualityRefiner)
    OperatorRegistry.register("ImageVisualDegradationsRefiner", ImageVisualDegradationsRefiner)
    OperatorRegistry.register("ImageClipEmbeddingRefiner", ImageClipEmbeddingRefiner)
    OperatorRegistry.register("ImageSigLIPEmbeddingRefiner", ImageSigLIPEmbeddingRefiner)
    OperatorRegistry.register("ImageAestheticQualityRefiner", ImageAestheticQualityRefiner)
    OperatorRegistry.register("ImageAIGCDetectorRefiner", ImageAIGCDetectorRefiner)


def _register_video_refiners():
    """Lazy register video refiners that depend on OpenCV/torch."""
    from .video_aesthetics_score_refiner import VideoAestheticScoreRefiner
    from .video_clip_embedding import VideoClipEmbeddingRefiner
    from .video_metadata import VideoMetadataRefiner

    OperatorRegistry.register("VideoMetadataRefiner", VideoMetadataRefiner)
    OperatorRegistry.register("VideoClipEmbeddingRefiner", VideoClipEmbeddingRefiner)
    OperatorRegistry.register("VideoAestheticScoreRefiner", VideoAestheticScoreRefiner)


def _register_llm_refiners():
    """Lazy register LLM synthesis refiners."""
    from .llm_synthesis import LLMOnlineSynthesisRefiner, LLMResponseParserRefiner

    OperatorRegistry.register("LlmOnlineSynthesisRefiner", LLMOnlineSynthesisRefiner)
    OperatorRegistry.register("LlmResponseParserRefiner", LLMResponseParserRefiner)

    try:
        from .llm_synthesis import LLMOfflineSynthesisRefiner

        OperatorRegistry.register("LlmOfflineSynthesisRefiner", LLMOfflineSynthesisRefiner)
    except ImportError:
        pass


try:
    _register_image_refiners()
except ImportError:
    pass

try:
    _register_video_refiners()
except ImportError:
    pass

try:
    _register_llm_refiners()
except ImportError:
    pass


__all__ = ["TextNewLineRemovalRefiner"]
