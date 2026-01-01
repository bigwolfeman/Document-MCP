"""Base retriever interface and implementations for multi-source knowledge retrieval.

This module defines the IRetriever protocol for duck-typed retrieval implementations
and BaseRetriever ABC for common functionality across all retrievers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Protocol, Optional, Dict, Any, Set
from enum import Enum
import logging


# ============================================================================
# Enumerations
# ============================================================================

class SourceType(str, Enum):
    """Type of knowledge source for a retrieval result."""
    VAULT = "vault"  # Document-MCP markdown notes
    CODE = "code"  # Code chunks from CodeRAG
    THREAD = "thread"  # vlt thread nodes
    DEFINITION = "definition"  # Symbol definition (ctags/SCIP)
    REFERENCE = "reference"  # Symbol reference/usage


class RetrievalMethod(str, Enum):
    """Method used to retrieve a result."""
    VECTOR = "vector"  # Semantic similarity search
    BM25 = "bm25"  # Keyword-based search
    GRAPH = "graph"  # Graph traversal (calls, imports)
    CTAGS = "ctags"  # ctags symbol lookup
    SCIP = "scip"  # SCIP code intelligence
    HYBRID = "hybrid"  # Combined methods


# ============================================================================
# Value Objects
# ============================================================================

@dataclass
class RetrievalResult:
    """A single piece of evidence from any retrieval path.

    This is the universal return type for all retrievers in the oracle system.
    Each result represents a single piece of context that might be relevant to
    answering a user's question.

    Attributes:
        content: The actual text content to include in context
        source_type: What kind of knowledge source this came from
        source_path: Path/ID to the original source (file:line, note path, thread ID)
        retrieval_method: How this result was found
        score: Relevance score (0.0-1.0, normalized across methods)
        token_count: Approximate token count of content
        metadata: Source-specific additional data

    Metadata by Source Type:
        - code: {file_path, chunk_type, qualified_name, lineno, language, signature}
        - vault: {note_path, title, snippet, updated}
        - thread: {thread_id, node_id, author, timestamp}
        - definition: {file_path, lineno, kind, scope}
        - reference: {file_path, lineno, usage_context}
    """
    content: str
    source_type: SourceType
    source_path: str
    retrieval_method: RetrievalMethod
    score: float  # 0.0-1.0, normalized
    token_count: int
    metadata: Dict[str, Any]


# ============================================================================
# Protocol Interface (Duck Typing)
# ============================================================================

class IRetriever(Protocol):
    """Protocol interface for retriever implementations.

    This uses Python's structural subtyping (PEP 544) to allow duck typing.
    Any class that implements these methods is compatible with IRetriever,
    regardless of whether it explicitly inherits from it.

    This is the preferred interface for type hints when accepting retrievers
    from external code, as it allows maximum flexibility.
    """

    async def retrieve(self, query: str, limit: int = 20) -> List[RetrievalResult]:
        """Retrieve relevant results for a query.

        Args:
            query: Natural language question or search query
            limit: Maximum number of results to return

        Returns:
            List of retrieval results, ordered by descending relevance score

        Raises:
            RetrieverError: If retrieval fails
        """
        ...

    @property
    def name(self) -> str:
        """Get the retriever's name (e.g., 'vector', 'bm25', 'graph').

        Returns:
            Human-readable name for this retriever
        """
        ...

    @property
    def available(self) -> bool:
        """Check if this retriever is ready to use.

        A retriever may be unavailable if its required indexes are not initialized,
        its API keys are missing, or its dependencies are not installed.

        Returns:
            True if retriever can be used, False otherwise
        """
        ...


# ============================================================================
# Abstract Base Class
# ============================================================================

class BaseRetriever(ABC):
    """Abstract base class for retriever implementations.

    Provides common functionality for all retrievers including logging,
    error handling, and property defaults. Concrete retrievers should
    inherit from this class and implement the abstract retrieve() method.

    Attributes:
        logger: Logger instance for this retriever
    """

    def __init__(self):
        """Initialize base retriever with logging."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._initialize()

    def _initialize(self) -> None:
        """Hook for subclass initialization.

        Override this method to perform initialization tasks like checking
        for required dependencies, loading indexes, or validating configuration.
        This is called automatically after __init__.
        """
        pass

    @abstractmethod
    async def retrieve(self, query: str, limit: int = 20) -> List[RetrievalResult]:
        """Retrieve relevant results for a query.

        This is the core method that must be implemented by all concrete retrievers.

        Args:
            query: Natural language question or search query
            limit: Maximum number of results to return

        Returns:
            List of retrieval results, ordered by descending relevance score

        Raises:
            RetrieverError: If retrieval fails
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the retriever's name.

        Returns:
            Human-readable name for this retriever (e.g., 'vector', 'bm25', 'graph')
        """
        raise NotImplementedError

    @property
    def available(self) -> bool:
        """Check if this retriever is ready to use.

        Default implementation returns True. Override to add availability checks
        such as verifying indexes exist, API keys are configured, etc.

        Returns:
            True if retriever can be used, False otherwise
        """
        return True

    async def retrieve_safe(self, query: str, limit: int = 20) -> List[RetrievalResult]:
        """Safely retrieve results with error handling.

        This wrapper method catches exceptions from retrieve() and returns an
        empty list on failure, logging the error. Use this in orchestration
        code where you want graceful degradation.

        Args:
            query: Natural language question or search query
            limit: Maximum number of results to return

        Returns:
            List of retrieval results, or empty list on error
        """
        if not self.available:
            self.logger.warning(f"Retriever '{self.name}' is not available, skipping")
            return []

        try:
            self.logger.debug(f"Retrieving with {self.name} retriever: query='{query[:50]}...', limit={limit}")
            results = await self.retrieve(query, limit)
            self.logger.info(f"Retrieved {len(results)} results from {self.name} retriever")
            return results
        except Exception as e:
            self.logger.error(f"Error in {self.name} retriever: {e}", exc_info=True)
            return []

    def __repr__(self) -> str:
        """String representation of this retriever."""
        return f"{self.__class__.__name__}(name='{self.name}', available={self.available})"


# ============================================================================
# Exceptions
# ============================================================================

class RetrieverError(Exception):
    """Base exception for retriever errors."""

    def __init__(self, message: str, retriever_name: Optional[str] = None):
        """Initialize retriever error.

        Args:
            message: Error message
            retriever_name: Name of the retriever that failed (optional)
        """
        self.retriever_name = retriever_name
        super().__init__(message)


class RetrieverNotAvailableError(RetrieverError):
    """Raised when a retriever is not available for use."""
    pass


class RetrieverQueryError(RetrieverError):
    """Raised when a retrieval query fails."""
    pass


# ============================================================================
# Result Merging and Deduplication (T046)
# ============================================================================

def merge_results(
    results_by_retriever: List[List[RetrievalResult]]
) -> List[RetrievalResult]:
    """Merge and deduplicate results from multiple retrievers.

    This function:
    1. Combines results from all retrievers
    2. Deduplicates by (file_path, lineno) or chunk_id
    3. Combines scores from multiple retrievers
    4. Tags each result with its source retriever(s)
    5. Sorts by combined score (descending)

    Args:
        results_by_retriever: List of result lists, one per retriever

    Returns:
        Merged and deduplicated list of results, ordered by score

    Algorithm:
        - For exact duplicates: average the scores and track all retrieval methods
        - For unique results: keep as-is
        - Sort final list by combined score (descending)
    """
    from collections import defaultdict

    # Key: (file_path, lineno) tuple for deduplication
    # Value: dict with combined metadata
    result_map: Dict[tuple, dict] = {}

    for results in results_by_retriever:
        for result in results:
            # Create deduplication key from metadata
            file_path = result.metadata.get("file_path", result.source_path.split(":")[0])
            lineno = result.metadata.get("lineno", 0)

            # Try to extract lineno from source_path if not in metadata
            if lineno == 0 and ":" in result.source_path:
                try:
                    lineno = int(result.source_path.split(":")[-1])
                except (ValueError, IndexError):
                    pass

            key = (file_path, lineno)

            if key in result_map:
                # Duplicate found - combine scores and methods
                existing = result_map[key]

                # Average scores (could also use max or weighted average)
                existing["scores"].append(result.score)
                existing["combined_score"] = sum(existing["scores"]) / len(existing["scores"])

                # Track all retrieval methods
                method = result.retrieval_method.value
                if method not in existing["retrieval_methods"]:
                    existing["retrieval_methods"].append(method)

                # Update retrieval method to HYBRID if multiple sources
                if len(existing["retrieval_methods"]) > 1:
                    existing["result"].retrieval_method = RetrievalMethod.HYBRID

                # Update score to combined score
                existing["result"].score = existing["combined_score"]

                # Add retrieval methods to metadata
                existing["result"].metadata["retrieval_methods"] = existing["retrieval_methods"]

            else:
                # New result
                result_map[key] = {
                    "result": result,
                    "scores": [result.score],
                    "combined_score": result.score,
                    "retrieval_methods": [result.retrieval_method.value]
                }

                # Initialize retrieval_methods in metadata
                result.metadata["retrieval_methods"] = [result.retrieval_method.value]

    # Extract results and sort by combined score
    merged = [item["result"] for item in result_map.values()]
    merged.sort(key=lambda r: r.score, reverse=True)

    return merged


def deduplicate_results(results: List[RetrievalResult]) -> List[RetrievalResult]:
    """Deduplicate a single list of results by location.

    This is a simpler version of merge_results for when you have
    results from a single source that may contain duplicates.

    Args:
        results: List of retrieval results (possibly with duplicates)

    Returns:
        Deduplicated list of results, preserving order

    Deduplication key: (file_path, lineno)
    """
    seen: Set[tuple] = set()
    deduped: List[RetrievalResult] = []

    for result in results:
        # Create deduplication key
        file_path = result.metadata.get("file_path", result.source_path.split(":")[0])
        lineno = result.metadata.get("lineno", 0)

        # Try to extract lineno from source_path if not in metadata
        if lineno == 0 and ":" in result.source_path:
            try:
                lineno = int(result.source_path.split(":")[-1])
            except (ValueError, IndexError):
                pass

        key = (file_path, lineno)

        if key not in seen:
            seen.add(key)
            deduped.append(result)

    return deduped
