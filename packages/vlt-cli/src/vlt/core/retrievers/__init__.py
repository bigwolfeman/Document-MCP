"""Retrieval implementations for multi-source knowledge retrieval.

This module provides multiple retrieval strategies for code search:
- Vector search (semantic similarity)
- BM25 search (keyword-based)
- Graph traversal (structural queries)
- Hybrid retrieval (combining all methods)
"""

from .base import (
    IRetriever,
    BaseRetriever,
    RetrievalResult,
    SourceType,
    RetrievalMethod,
    RetrieverError,
    RetrieverNotAvailableError,
    RetrieverQueryError,
    merge_results,
    deduplicate_results,
)

from .vector import VectorRetriever, search_vector
from .bm25 import BM25Retriever, search_bm25
from .graph import (
    GraphRetriever,
    search_definition,
    search_references,
)
from .hybrid import (
    hybrid_retrieve,
    hybrid_retrieve_sync,
    retrieve_vector_only,
    retrieve_bm25_only,
    retrieve_graph_only,
)

__all__ = [
    # Base classes and interfaces
    "IRetriever",
    "BaseRetriever",
    "RetrievalResult",
    "SourceType",
    "RetrievalMethod",
    # Exceptions
    "RetrieverError",
    "RetrieverNotAvailableError",
    "RetrieverQueryError",
    # Utility functions
    "merge_results",
    "deduplicate_results",
    # Retriever implementations
    "VectorRetriever",
    "BM25Retriever",
    "GraphRetriever",
    # Convenience functions
    "search_vector",
    "search_bm25",
    "search_definition",
    "search_references",
    # Hybrid retrieval
    "hybrid_retrieve",
    "hybrid_retrieve_sync",
    "retrieve_vector_only",
    "retrieve_bm25_only",
    "retrieve_graph_only",
]
