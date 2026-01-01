"""Thread Retriever - Retrieves thread context for Oracle queries."""

from __future__ import annotations

import logging
from typing import List, Optional

from ..models.oracle import SourceReference
from ..models.thread import ThreadSearchResult
from .thread_service import ThreadService, get_thread_service

logger = logging.getLogger(__name__)


class ThreadRetriever:
    """Retrieves thread context for Oracle context assembly."""

    def __init__(self, thread_service: ThreadService | None = None):
        """Initialize with thread service."""
        self._service = thread_service or get_thread_service()

    def search(
        self,
        user_id: str,
        query: str,
        project_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[ThreadSearchResult]:
        """
        Search threads for relevant content.

        Args:
            user_id: User ID for scoping
            query: Search query
            project_id: Optional project filter
            limit: Max results

        Returns:
            List of ThreadSearchResult
        """
        response = self._service.search_threads(
            user_id=user_id,
            query=query,
            project_id=project_id,
            limit=limit,
        )
        return response.results

    def format_citations(
        self,
        results: List[ThreadSearchResult],
    ) -> List[SourceReference]:
        """
        Convert search results to SourceReference citations.

        Args:
            results: Search results from search()

        Returns:
            List of SourceReference for Oracle response
        """
        citations = []
        for result in results:
            citations.append(SourceReference(
                path=f"thread:{result.thread_id}#{result.entry_id[:8]}",
                source_type="thread",
                snippet=result.content[:500] if result.content else None,
                score=result.score,
                metadata={
                    "thread_id": result.thread_id,
                    "entry_id": result.entry_id,
                    "author": result.author,
                    "timestamp": result.timestamp.isoformat() if result.timestamp else None,
                },
            ))
        return citations

    def get_context_for_query(
        self,
        user_id: str,
        query: str,
        project_id: Optional[str] = None,
        max_tokens: int = 4000,
    ) -> tuple[str, List[SourceReference]]:
        """
        Get thread context and citations for an Oracle query.

        Args:
            user_id: User ID
            query: The user's question
            project_id: Optional project scope
            max_tokens: Approximate token limit for context

        Returns:
            Tuple of (context_text, citations)
        """
        # Search for relevant threads
        results = self.search(
            user_id=user_id,
            query=query,
            project_id=project_id,
            limit=10,  # Get top 10 results
        )

        if not results:
            return "", []

        # Build context string
        context_parts = ["## Thread History\n"]
        char_limit = max_tokens * 4  # Rough chars to tokens
        current_chars = len(context_parts[0])
        included_results = []

        for result in results:
            entry_text = f"\n### Thread: {result.thread_id}\n"
            entry_text += f"**{result.author}** ({result.timestamp.strftime('%Y-%m-%d %H:%M') if result.timestamp else 'unknown'}):\n"
            entry_text += f"{result.content}\n"

            if current_chars + len(entry_text) > char_limit:
                break

            context_parts.append(entry_text)
            current_chars += len(entry_text)
            included_results.append(result)

        context = "".join(context_parts)
        citations = self.format_citations(included_results)

        return context, citations


# Singleton for dependency injection
_thread_retriever: ThreadRetriever | None = None


def get_thread_retriever() -> ThreadRetriever:
    """Get or create the thread retriever singleton."""
    global _thread_retriever
    if _thread_retriever is None:
        _thread_retriever = ThreadRetriever()
    return _thread_retriever
