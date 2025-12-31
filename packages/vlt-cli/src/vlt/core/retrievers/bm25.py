"""BM25 keyword search retriever.

T044: BM25 search retriever that implements IRetriever interface.
Wraps the existing bm25.py search functionality and returns
RetrievalResult objects for integration with hybrid retrieval.
"""

import logging
from typing import List, Optional
from sqlalchemy.orm import Session

from vlt.core.retrievers.base import (
    BaseRetriever,
    RetrievalResult,
    SourceType,
    RetrievalMethod,
    RetrieverError
)
from vlt.core.coderag.bm25 import BM25Indexer
from vlt.core.models import CodeChunk
from vlt.db import SessionLocal


logger = logging.getLogger(__name__)


class BM25Retriever(BaseRetriever):
    """BM25 keyword search retriever.

    This retriever:
    1. Uses SQLite FTS5 BM25 ranking for keyword-based search
    2. Excels at exact matches and technical terms
    3. Complements vector search for hybrid retrieval

    Attributes:
        project_id: Project identifier to scope search
        db: Database session
        indexer: BM25 indexer instance
    """

    def __init__(self, project_id: str, db: Optional[Session] = None):
        """Initialize BM25 retriever.

        Args:
            project_id: Project identifier to scope search
            db: Optional database session (creates new if None)
        """
        self.project_id = project_id
        self._db = db
        self._owns_db = db is None
        self.indexer: Optional[BM25Indexer] = None
        super().__init__()

    def _initialize(self) -> None:
        """Initialize BM25 indexer."""
        self.indexer = BM25Indexer(self.db)

    @property
    def name(self) -> str:
        """Get retriever name."""
        return "bm25"

    @property
    def available(self) -> bool:
        """Check if retriever is available.

        Returns:
            True if BM25 index has been initialized (always true)
        """
        # BM25 index is always available (uses SQLite FTS5)
        return True

    @property
    def db(self) -> Session:
        """Get database session, creating if needed."""
        if self._db is None:
            self._db = SessionLocal()
            self._owns_db = True
        return self._db

    def __enter__(self):
        """Context manager entry."""
        if self._owns_db:
            self._db = SessionLocal()
        if self.indexer is None:
            self.indexer = BM25Indexer(self._db)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._owns_db and self._db:
            self._db.close()

    async def retrieve(self, query: str, limit: int = 20) -> List[RetrievalResult]:
        """Retrieve relevant code chunks using BM25 keyword search.

        Args:
            query: Natural language question or search query
            limit: Maximum number of results to return (default: 20)

        Returns:
            List of retrieval results ordered by descending BM25 score

        Raises:
            RetrieverError: If search fails
        """
        if self.indexer is None:
            self.indexer = BM25Indexer(self.db)

        try:
            # Perform BM25 search
            logger.debug(f"Performing BM25 search for query: {query[:50]}...")
            raw_results = self.indexer.search_bm25(
                query=query,
                limit=limit,
                project_id=self.project_id
            )

            if not raw_results:
                logger.info(f"BM25 search returned no results for project: {self.project_id}")
                return []

            # Get chunk IDs and scores
            chunk_ids = [chunk_id for chunk_id, _ in raw_results]
            score_map = {chunk_id: score for chunk_id, score in raw_results}

            # Normalize BM25 scores to [0, 1] range
            # BM25 scores from our implementation are already positive
            # (we negate the negative FTS5 scores)
            if score_map:
                max_score = max(score_map.values())
                if max_score > 0:
                    score_map = {
                        chunk_id: score / max_score
                        for chunk_id, score in score_map.items()
                    }

            # Fetch full chunk data from database
            results = []
            for chunk_id in chunk_ids:
                chunk = self.db.get(CodeChunk, chunk_id)
                if not chunk:
                    logger.warning(f"Chunk {chunk_id} not found in database")
                    continue

                # Build content from chunk components
                content_parts = []

                if chunk.signature:
                    content_parts.append(f"# Signature\n{chunk.signature}")

                if chunk.docstring:
                    content_parts.append(f"# Documentation\n{chunk.docstring}")

                if chunk.imports:
                    content_parts.append(f"# Imports\n{chunk.imports}")

                if chunk.class_context:
                    content_parts.append(f"# Class Context\n{chunk.class_context}")

                content_parts.append(f"# Code\n{chunk.body}")

                content = "\n\n".join(content_parts)

                # Build source path with line number
                source_path = f"{chunk.file_path}:{chunk.lineno}"

                # Metadata
                metadata = {
                    "file_path": chunk.file_path,
                    "chunk_type": chunk.chunk_type.value,
                    "qualified_name": chunk.qualified_name,
                    "lineno": chunk.lineno,
                    "end_lineno": chunk.end_lineno,
                    "language": chunk.language,
                    "signature": chunk.signature,
                }

                results.append(RetrievalResult(
                    content=content,
                    source_type=SourceType.CODE,
                    source_path=source_path,
                    retrieval_method=RetrievalMethod.BM25,
                    score=score_map.get(chunk_id, 0.0),
                    token_count=chunk.token_count or len(content.split()),
                    metadata=metadata
                ))

            logger.info(f"BM25 search returned {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Error in BM25 retrieval: {e}", exc_info=True)
            raise RetrieverError(
                f"BM25 retrieval failed: {str(e)}",
                retriever_name=self.name
            ) from e


# Convenience function for standalone use
async def search_bm25(
    query: str,
    project_id: str,
    limit: int = 20,
    db: Optional[Session] = None
) -> List[RetrievalResult]:
    """Standalone function to perform BM25 search.

    Args:
        query: Natural language question or search query
        project_id: Project identifier to scope search
        limit: Maximum number of results to return
        db: Optional database session

    Returns:
        List of retrieval results ordered by descending BM25 score
    """
    async with BM25Retriever(project_id, db) as retriever:
        return await retriever.retrieve(query, limit)
