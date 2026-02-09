"""
Pipeline Framework: Configuration-Driven Distributed Processing Framework

This package provides a flexible framework for building data processing pipelines.
All public APIs are exported from this module.
"""

# Config classes
# Backend classes
from .dedup_backend import (
    DedupBackend,  # Abstract base class
    ExactDedupBackend,
    SemanticDedupBackend,
)

# Base classes
from .base import (
    DataLoader,
    DataWriter,
)
from .config import (
    DataLoaderConfig,
    DataWriterConfig,
    ExecutorConfig,
    OperatorConfig,
    PipelineConfig,
    RejectedSamplesConfig,
    StageConfig,
    StageWorkerConfig,
)

# Executor
from .executor import (
    Executor,
)

# Operator classes
from .operator import (
    BatchResult,
    CombinedOperator,
    Deduplicator,
    Filter,
    Operator,
    Refiner,
)

# Registry classes
from .registry import (
    DataLoaderRegistry,
    DataWriterRegistry,
    OperatorRegistry,
)

# Stage execution (Ray Actor + batch result)
from .stage_actor import StageActor, StageBatchResult

# Export all public APIs
__all__ = [
    # Config
    "OperatorConfig",
    "StageWorkerConfig",
    "StageConfig",
    "DataLoaderConfig",
    "DataWriterConfig",
    "ExecutorConfig",
    "RejectedSamplesConfig",
    "PipelineConfig",
    # Operator
    "Operator",
    "Refiner",
    "Filter",
    "Deduplicator",
    "CombinedOperator",
    "BatchResult",
    # Backend
    "DedupBackend",  # Abstract base class
    "ExactDedupBackend",
    "SemanticDedupBackend",
    # Registry
    "OperatorRegistry",
    "DataLoaderRegistry",
    "DataWriterRegistry",
    # Base
    "DataLoader",
    "DataWriter",
    # Stage execution
    "StageActor",
    "StageBatchResult",
    # Executor
    "Executor",
]
