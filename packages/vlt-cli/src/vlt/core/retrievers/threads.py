"""Thread retriever for vlt development history and memory.

T070: Retrieves context from vlt threads using existing seek functionality.
Implements IRetriever interface for integration with hybrid retrieval.
"""

import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from vlt.core.retrievers.base import BaseRetriever, RetrievalResult, SourceType, RetrievalMethod
from vlt.core.service import SqliteVaultService
from vlt.db import SessionLocal


logger = logging.getLogger(__name__)


class ThreadRetriever(BaseRetriever):
    """Retrieves relevant thread nodes from vlt development history.

    Uses the existing vlt thread seek functionality to find relevant
    development context, decisions, and historical knowledge stored
    in threads.

    Attributes:
        project_id: Project identifier for scoping search
        service: SqliteVaultService instance for thread operations
        db: Database session
    """

    def __init__(
        self,
        project_id: str,
        service: Optional[SqliteVaultService] = None,
        db: Optional[Session] = None
    ):
        """Initialize thread retriever.

        Args:
            project_id: Project identifier for scoping search
            service: Optional service instance (creates new if None)
            db: Optional database session (creates new if None)
        """
        super().__init__()

        self.project_id = project_id
        self.service = service or SqliteVaultService()

        # Track if we own the db session (for cleanup)
        self._owns_db = db is None
        self.db = db or SessionLocal()

        self.logger.info(f"Initialized ThreadRetriever for project: {project_id}")

    @property
    def name(self) -> str:
        """Get retriever name."""
        return "threads"

    @property
    def available(self) -> bool:
        """Check if thread retrieval is available.

        Returns:
            True if project has threads available for search
        """
        # Check if the project has any threads
        try:
            threads = self.service.list_threads(self.project_id, self.db)
            return len(threads) > 0
        except Exception as e:
            self.logger.warning(f"Error checking thread availability: {e}")
            return False

    async def retrieve(self, query: str, limit: int = 20) -> List[RetrievalResult]:
        """Retrieve relevant thread nodes using semantic search.

        Args:
            query: Natural language question or search query
            limit: Maximum number of results to return (default: 20)

        Returns:
            List of retrieval results from thread search
        """
        if not query.strip():
            self.logger.warning("Empty query provided to thread retriever")
            return []

        self.logger.debug(f"Searching threads for: '{query[:50]}...' (limit={limit})")

        try:
            # Use the service's seek functionality for semantic thread search
            # The seek method performs vector similarity search across thread nodes
            seek_results = self.service.seek_threads(
                project_id=self.project_id,
                query=query,
                limit=limit,
                db=self.db
            )

            if not seek_results:
                self.logger.info("No thread results found")
                return []

            self.logger.info(f"Thread search returned {len(seek_results)} results")

            # Convert to RetrievalResult objects
            retrieval_results = []

            for thread_result in seek_results[:limit]:
                # Extract fields from thread result
                # Expected format from seek_threads:
                # {
                #   "thread_id": "auth-design",
                #   "node_id": 42,
                #   "content": "Decided to use JWT with 90-day expiry...",
                #   "author": "claude",
                #   "timestamp": "2025-01-15T10:30:00Z",
                #   "score": 0.85
                # }

                thread_id = thread_result.get("thread_id", "unknown")
                node_id = thread_result.get("node_id", 0)
                content = thread_result.get("content", "")
                author = thread_result.get("author", "")
                timestamp = thread_result.get("timestamp", "")
                score = thread_result.get("score", 0.5)

                # Build source path: thread:thread_id#node_id
                source_path = f"thread:{thread_id}#{node_id}"

                # Estimate token count (rough: 1 token ≈ 4 characters)
                token_count = len(content) // 4

                # Format content with context
                formatted_content = f"[Thread: {thread_id}, Node: {node_id}]\n{content}"

                result = RetrievalResult(
                    content=formatted_content,
                    source_type=SourceType.THREAD,
                    source_path=source_path,
                    retrieval_method=RetrievalMethod.VECTOR,  # seek uses vector similarity
                    score=float(score),
                    token_count=token_count,
                    metadata={
                        "thread_id": thread_id,
                        "node_id": node_id,
                        "author": author,
                        "timestamp": timestamp,
                        "project_id": self.project_id
                    }
                )

                retrieval_results.append(result)

            self.logger.info(f"Converted {len(retrieval_results)} thread results to RetrievalResult")
            return retrieval_results

        except Exception as e:
            self.logger.error(f"Error in thread retrieval: {e}", exc_info=True)
            return []

    def __del__(self):
        """Cleanup database session if we own it."""
        if self._owns_db and self.db:
            try:
                self.db.close()
            except Exception:
                pass


# Convenience function for standalone usage
async def search_threads(
    query: str,
    project_id: str,
    limit: int = 20,
    service: Optional[SqliteVaultService] = None,
    db: Optional[Session] = None
) -> List[RetrievalResult]:
    """Search vlt threads for relevant development context.

    Convenience function for standalone thread search without creating
    a retriever instance.

    Args:
        query: Natural language question or search query
        project_id: Project identifier for scoping search
        limit: Maximum number of results to return (default: 20)
        service: Optional service instance
        db: Optional database session

    Returns:
        List of retrieval results from threads
    """
    retriever = ThreadRetriever(project_id=project_id, service=service, db=db)
    return await retriever.retrieve(query, limit)
