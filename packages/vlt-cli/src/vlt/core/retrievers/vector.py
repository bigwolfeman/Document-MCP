"""Vector search retriever using cosine similarity.

T043: Vector search retriever that implements IRetriever interface.
Uses embedder to generate query embeddings and performs cosine similarity
search against stored chunk embeddings in the database.
"""

import logging
import numpy as np
from typing import List, Optional
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from vlt.core.retrievers.base import (
    BaseRetriever,
    RetrievalResult,
    SourceType,
    RetrievalMethod,
    RetrieverError
)
from vlt.core.models import CodeChunk
from vlt.core.coderag.embedder import get_embedding
from vlt.db import SessionLocal
from vlt.config import Settings


logger = logging.getLogger(__name__)


class VectorRetriever(BaseRetriever):
    """Vector search retriever using cosine similarity.

    This retriever:
    1. Generates an embedding for the query using the embedder
    2. Computes cosine similarity against all stored chunk embeddings
    3. Returns top-k results ordered by similarity score

    Attributes:
        project_id: Project identifier to scope search
        settings: Configuration settings (for embedding API)
        db: Database session
    """

    def __init__(
        self,
        project_id: str,
        settings: Optional[Settings] = None,
        db: Optional[Session] = None
    ):
        """Initialize vector retriever.

        Args:
            project_id: Project identifier to scope search
            settings: Optional settings instance (uses default if None)
            db: Optional database session (creates new if None)
        """
        self.project_id = project_id
        self.settings = settings or Settings()
        self._db = db
        self._owns_db = db is None
        super().__init__()

    def _initialize(self) -> None:
        """Check if embeddings are available."""
        if not self.settings.openrouter_api_key:
            logger.warning("Vector retriever initialized without OpenRouter API key - will be unavailable")

    @property
    def name(self) -> str:
        """Get retriever name."""
        return "vector"

    @property
    def available(self) -> bool:
        """Check if retriever is available.

        Returns:
            True if OpenRouter API key is configured, False otherwise
        """
        return bool(self.settings.openrouter_api_key)

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
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._owns_db and self._db:
            self._db.close()

    async def retrieve(self, query: str, limit: int = 20) -> List[RetrievalResult]:
        """Retrieve relevant code chunks using vector similarity.

        Args:
            query: Natural language question or search query
            limit: Maximum number of results to return (default: 20)

        Returns:
            List of retrieval results ordered by descending similarity score

        Raises:
            RetrieverError: If embedding generation or search fails
        """
        if not self.available:
            logger.warning("Vector retriever called but API key not configured")
            return []

        try:
            # Generate query embedding
            logger.debug(f"Generating embedding for query: {query[:50]}...")
            query_embedding = await get_embedding(query, self.settings)

            if query_embedding is None:
                raise RetrieverError(
                    "Failed to generate query embedding",
                    retriever_name=self.name
                )

            # Convert to numpy array for cosine similarity computation
            query_vector = np.array(query_embedding, dtype=np.float32)
            query_norm = np.linalg.norm(query_vector)

            if query_norm == 0:
                raise RetrieverError(
                    "Query embedding has zero magnitude",
                    retriever_name=self.name
                )

            # Normalize query vector
            query_vector = query_vector / query_norm

            # Fetch all chunks with embeddings for this project
            stmt = select(CodeChunk).where(
                CodeChunk.project_id == self.project_id,
                CodeChunk.embedding.is_not(None)
            )
            chunks = self.db.scalars(stmt).all()

            if not chunks:
                logger.info(f"No chunks with embeddings found for project: {self.project_id}")
                return []

            # Compute cosine similarity for each chunk
            scored_chunks = []
            for chunk in chunks:
                try:
                    # Deserialize embedding from bytes
                    chunk_vector = np.frombuffer(chunk.embedding, dtype=np.float32)
                    chunk_norm = np.linalg.norm(chunk_vector)

                    if chunk_norm == 0:
                        logger.warning(f"Chunk {chunk.id} has zero-magnitude embedding, skipping")
                        continue

                    # Normalize and compute cosine similarity
                    chunk_vector = chunk_vector / chunk_norm
                    similarity = float(np.dot(query_vector, chunk_vector))

                    # Clamp to [0, 1] range (should already be, but floating point errors)
                    similarity = max(0.0, min(1.0, similarity))

                    scored_chunks.append((chunk, similarity))

                except Exception as e:
                    logger.warning(f"Error computing similarity for chunk {chunk.id}: {e}")
                    continue

            # Sort by similarity (descending) and take top-k
            scored_chunks.sort(key=lambda x: x[1], reverse=True)
            top_chunks = scored_chunks[:limit]

            # Convert to RetrievalResult objects
            results = []
            for chunk, score in top_chunks:
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
                    retrieval_method=RetrievalMethod.VECTOR,
                    score=score,
                    token_count=chunk.token_count or len(content.split()),
                    metadata=metadata
                ))

            logger.info(f"Vector search returned {len(results)} results")
            return results

        except RetrieverError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in vector retrieval: {e}", exc_info=True)
            raise RetrieverError(
                f"Vector retrieval failed: {str(e)}",
                retriever_name=self.name
            ) from e


# Convenience function for standalone use
async def search_vector(
    query: str,
    project_id: str,
    limit: int = 20,
    settings: Optional[Settings] = None,
    db: Optional[Session] = None
) -> List[RetrievalResult]:
    """Standalone function to perform vector search.

    Args:
        query: Natural language question or search query
        project_id: Project identifier to scope search
        limit: Maximum number of results to return
        settings: Optional settings instance
        db: Optional database session

    Returns:
        List of retrieval results ordered by descending similarity
    """
    async with VectorRetriever(project_id, settings, db) as retriever:
        return await retriever.retrieve(query, limit)
