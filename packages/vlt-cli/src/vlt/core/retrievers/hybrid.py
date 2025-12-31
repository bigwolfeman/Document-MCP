"""Hybrid retrieval orchestration for multi-source search.

T048: Parallel retrieval orchestration that runs multiple retrievers
concurrently, merges results, and optionally reranks for final output.
"""

import logging
import asyncio
from typing import List, Optional
from sqlalchemy.orm import Session

from vlt.core.retrievers.base import (
    IRetriever,
    RetrievalResult,
    merge_results
)
from vlt.core.retrievers.vector import VectorRetriever
from vlt.core.retrievers.bm25 import BM25Retriever
from vlt.core.retrievers.graph import GraphRetriever
from vlt.core.reranker import rerank
from vlt.config import Settings
from vlt.db import SessionLocal


logger = logging.getLogger(__name__)


async def hybrid_retrieve(
    query: str,
    project_id: str,
    project_path: str,
    retrievers: Optional[List[IRetriever]] = None,
    top_k: int = 20,
    use_reranking: bool = True,
    settings: Optional[Settings] = None,
    db: Optional[Session] = None
) -> List[RetrievalResult]:
    """Perform hybrid retrieval using multiple retrieval methods in parallel.

    This is the main orchestration function for hybrid retrieval. It:
    1. Runs all retrievers concurrently using asyncio.gather
    2. Merges and deduplicates results from all retrievers
    3. Optionally reranks using LLM for better relevance
    4. Returns final top-k results

    Args:
        query: Natural language question or search query
        project_id: Project identifier for scoping search
        project_path: Path to project root directory
        retrievers: Optional list of retriever instances (creates default set if None)
        top_k: Number of final results to return (default: 20)
        use_reranking: Whether to apply LLM reranking (default: True)
        settings: Optional settings instance (uses default if None)
        db: Optional database session (creates new if None)

    Returns:
        List of top-k retrieval results, merged and optionally reranked

    Example:
        ```python
        results = await hybrid_retrieve(
            query="How does authentication work?",
            project_id="my-project",
            project_path="/path/to/project",
            top_k=10
        )
        ```
    """
    if settings is None:
        settings = Settings()

    owns_db = db is None
    if owns_db:
        db = SessionLocal()

    try:
        # Create default retrievers if not provided
        if retrievers is None:
            retrievers = _create_default_retrievers(
                project_id=project_id,
                project_path=project_path,
                settings=settings,
                db=db
            )

        # Filter to only available retrievers
        available_retrievers = [r for r in retrievers if r.available]

        if not available_retrievers:
            logger.warning("No retrievers available for hybrid retrieval")
            return []

        logger.info(
            f"Running hybrid retrieval with {len(available_retrievers)} retrievers: "
            f"{[r.name for r in available_retrievers]}"
        )

        # Run all retrievers in parallel
        retrieval_tasks = [
            r.retrieve_safe(query, limit=top_k * 2)  # Get extra results for merging
            for r in available_retrievers
        ]

        results_by_retriever = await asyncio.gather(*retrieval_tasks)

        # Log retrieval results
        for retriever, results in zip(available_retrievers, results_by_retriever):
            logger.debug(f"{retriever.name} returned {len(results)} results")

        # Merge and deduplicate
        merged = merge_results(results_by_retriever)
        logger.info(f"Merged to {len(merged)} unique results")

        # Apply reranking if requested and possible
        if use_reranking and settings.openrouter_api_key:
            try:
                logger.info("Applying LLM reranking...")
                final_results = await rerank(
                    query=query,
                    candidates=merged,
                    top_k=top_k,
                    settings=settings
                )
                logger.info(f"Reranking complete, returning {len(final_results)} results")
            except Exception as e:
                logger.warning(f"Reranking failed: {e}, using merged results")
                final_results = merged[:top_k]
        else:
            # No reranking - just take top-k by score
            if not use_reranking:
                logger.debug("Reranking disabled, using score-based ranking")
            else:
                logger.debug("No API key for reranking, using score-based ranking")

            final_results = merged[:top_k]

        return final_results

    finally:
        if owns_db and db:
            db.close()


def _create_default_retrievers(
    project_id: str,
    project_path: str,
    settings: Settings,
    db: Session
) -> List[IRetriever]:
    """Create default set of retrievers for hybrid search.

    Args:
        project_id: Project identifier
        project_path: Path to project root
        settings: Settings instance
        db: Database session

    Returns:
        List of retriever instances (vector, BM25, graph)
    """
    return [
        VectorRetriever(project_id=project_id, settings=settings, db=db),
        BM25Retriever(project_id=project_id, db=db),
        GraphRetriever(project_id=project_id, project_path=project_path, db=db),
    ]


# Synchronous wrapper for convenience
def hybrid_retrieve_sync(
    query: str,
    project_id: str,
    project_path: str,
    retrievers: Optional[List[IRetriever]] = None,
    top_k: int = 20,
    use_reranking: bool = True,
    settings: Optional[Settings] = None,
    db: Optional[Session] = None
) -> List[RetrievalResult]:
    """Synchronous wrapper for hybrid_retrieve.

    Args:
        query: Natural language question or search query
        project_id: Project identifier for scoping search
        project_path: Path to project root directory
        retrievers: Optional list of retriever instances
        top_k: Number of final results to return
        use_reranking: Whether to apply LLM reranking
        settings: Optional settings instance
        db: Optional database session

    Returns:
        List of top-k retrieval results
    """
    return asyncio.run(
        hybrid_retrieve(
            query=query,
            project_id=project_id,
            project_path=project_path,
            retrievers=retrievers,
            top_k=top_k,
            use_reranking=use_reranking,
            settings=settings,
            db=db
        )
    )


# ============================================================================
# Convenience Functions for Individual Retrieval Methods
# ============================================================================

async def retrieve_vector_only(
    query: str,
    project_id: str,
    limit: int = 20,
    settings: Optional[Settings] = None,
    db: Optional[Session] = None
) -> List[RetrievalResult]:
    """Retrieve using only vector search.

    Args:
        query: Natural language question or search query
        project_id: Project identifier
        limit: Number of results to return
        settings: Optional settings instance
        db: Optional database session

    Returns:
        List of retrieval results from vector search only
    """
    retriever = VectorRetriever(project_id=project_id, settings=settings, db=db)
    return await retriever.retrieve_safe(query, limit)


async def retrieve_bm25_only(
    query: str,
    project_id: str,
    limit: int = 20,
    db: Optional[Session] = None
) -> List[RetrievalResult]:
    """Retrieve using only BM25 keyword search.

    Args:
        query: Natural language question or search query
        project_id: Project identifier
        limit: Number of results to return
        db: Optional database session

    Returns:
        List of retrieval results from BM25 search only
    """
    retriever = BM25Retriever(project_id=project_id, db=db)
    return await retriever.retrieve_safe(query, limit)


async def retrieve_graph_only(
    query: str,
    project_id: str,
    project_path: str,
    limit: int = 20,
    db: Optional[Session] = None
) -> List[RetrievalResult]:
    """Retrieve using only graph traversal.

    Args:
        query: Natural language question or search query
        project_id: Project identifier
        project_path: Path to project root
        limit: Number of results to return
        db: Optional database session

    Returns:
        List of retrieval results from graph traversal only
    """
    retriever = GraphRetriever(
        project_id=project_id,
        project_path=project_path,
        db=db
    )
    return await retriever.retrieve_safe(query, limit)
