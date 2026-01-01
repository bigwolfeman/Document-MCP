"""Lazy LLM evaluation for thread summaries.

This module implements lazy evaluation for thread summaries and embeddings,
following the principle: "generate on read, not on write".

Key requirements from FR-046 to FR-050:
- FR-046: NO LLM calls during write operations (vlt thread push)
- FR-047: Generate summaries on-demand when threads are read or queried
- FR-048: Cache generated summaries and embeddings for reuse
- FR-049: Detect stale cached artifacts and regenerate incrementally
- FR-050: Track "last_summarized_node_id" for incremental summarization

Architecture:
- ThreadSummaryManager: Handles cache checking, staleness detection, and regeneration
- Staleness detection: Compare last_summarized_node_id with thread's latest node
- Incremental regeneration: Only summarize nodes after last_summarized_node_id
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from vlt.core.models import Thread, Node, ThreadSummaryCache
from vlt.core.interfaces import ILLMProvider
from vlt.db import SessionLocal

logger = logging.getLogger(__name__)


class ThreadSummaryManager:
    """Manager for lazy LLM evaluation of thread summaries.

    This class implements the lazy evaluation pattern for thread summarization:
    1. NO LLM calls during writes (thread push)
    2. Generate summaries on-demand during reads
    3. Cache summaries for reuse
    4. Detect staleness and regenerate incrementally

    Attributes:
        llm_provider: LLM provider for summary generation
        db: Database session (optional, creates new if None)
    """

    def __init__(self, llm_provider: ILLMProvider, db: Optional[Session] = None):
        """Initialize summary manager.

        Args:
            llm_provider: LLM provider for generating summaries
            db: Optional database session (creates new if None)
        """
        self.llm_provider = llm_provider
        self._owns_db = db is None
        self.db = db or SessionLocal()

    def check_staleness(self, thread_id: str) -> Tuple[bool, Optional[str], int]:
        """Check if cached summary is stale (FR-049).

        Compares the last_node_id in the cache with the latest node in the thread.
        If there are new nodes since the last summary, the cache is stale.

        Args:
            thread_id: Thread identifier

        Returns:
            Tuple of (is_stale, last_summarized_node_id, new_node_count)
            - is_stale: True if cache is stale or missing
            - last_summarized_node_id: ID of last summarized node (None if no cache)
            - new_node_count: Number of nodes since last summary
        """
        # Check if cache exists
        cache = self.db.scalar(
            select(ThreadSummaryCache)
            .where(ThreadSummaryCache.thread_id == thread_id)
        )

        if not cache:
            # No cache exists - need to summarize all nodes
            node_count = self.db.scalar(
                select(func.count(Node.id))
                .where(Node.thread_id == thread_id)
            )
            logger.debug(f"No cache for thread {thread_id}, {node_count} nodes to summarize")
            return True, None, node_count or 0

        # Get the last node in thread
        latest_node = self.db.scalar(
            select(Node)
            .where(Node.thread_id == thread_id)
            .order_by(desc(Node.sequence_id))
            .limit(1)
        )

        if not latest_node:
            # Thread has no nodes (edge case)
            logger.warning(f"Thread {thread_id} has cache but no nodes")
            return False, cache.last_node_id, 0

        # Compare last_node_id from cache with latest node
        if cache.last_node_id == latest_node.id:
            # Cache is up to date
            logger.debug(f"Cache for thread {thread_id} is up to date")
            return False, cache.last_node_id, 0

        # Cache is stale - count new nodes
        last_summarized_node = self.db.get(Node, cache.last_node_id)

        if not last_summarized_node:
            # Last summarized node was deleted - need full re-summarization
            logger.warning(f"Last summarized node {cache.last_node_id} not found, full re-summarization needed")
            node_count = self.db.scalar(
                select(func.count(Node.id))
                .where(Node.thread_id == thread_id)
            )
            return True, None, node_count or 0

        # Count nodes after the last summarized node
        new_node_count = self.db.scalar(
            select(func.count(Node.id))
            .where(Node.thread_id == thread_id)
            .where(Node.sequence_id > last_summarized_node.sequence_id)
        )

        logger.debug(f"Thread {thread_id} has {new_node_count} new nodes since last summary")
        return True, cache.last_node_id, new_node_count or 0

    def get_cached_summary(self, thread_id: str) -> Optional[str]:
        """Get cached summary if it exists and is fresh (FR-048).

        Args:
            thread_id: Thread identifier

        Returns:
            Cached summary text or None if cache is stale/missing
        """
        is_stale, _, _ = self.check_staleness(thread_id)

        if is_stale:
            logger.debug(f"Cache for thread {thread_id} is stale, returning None")
            return None

        cache = self.db.scalar(
            select(ThreadSummaryCache)
            .where(ThreadSummaryCache.thread_id == thread_id)
        )

        if cache:
            logger.debug(f"Returning fresh cached summary for thread {thread_id}")
            return cache.summary

        return None

    def generate_summary(
        self,
        thread_id: str,
        force: bool = False
    ) -> str:
        """Generate or retrieve thread summary (FR-047).

        This is the main entry point for lazy summary generation.
        It checks the cache first, and only generates a summary if needed.

        Args:
            thread_id: Thread identifier
            force: Force regeneration even if cache is fresh

        Returns:
            Thread summary text
        """
        # Check cache first (unless force=True)
        if not force:
            cached = self.get_cached_summary(thread_id)
            if cached:
                logger.info(f"Using cached summary for thread {thread_id}")
                return cached

        # Check staleness to determine if we need incremental or full summarization
        is_stale, last_node_id, new_node_count = self.check_staleness(thread_id)

        if new_node_count == 0 and not force:
            # Edge case: thread has no nodes
            logger.warning(f"Thread {thread_id} has no nodes to summarize")
            return "No content in this thread yet."

        # Decide between incremental and full summarization
        if last_node_id and not force:
            logger.info(f"Performing incremental summarization for thread {thread_id} ({new_node_count} new nodes)")
            return self._incremental_summarize(thread_id, last_node_id, new_node_count)
        else:
            logger.info(f"Performing full summarization for thread {thread_id}")
            return self._full_summarize(thread_id)

    def _incremental_summarize(
        self,
        thread_id: str,
        last_node_id: str,
        new_node_count: int
    ) -> str:
        """Incrementally summarize new nodes only (FR-050).

        This is the core optimization: instead of re-summarizing the entire thread,
        we only summarize nodes that were added since the last summary.

        Args:
            thread_id: Thread identifier
            last_node_id: ID of last summarized node
            new_node_count: Number of new nodes

        Returns:
            Updated summary text
        """
        # Get existing cache
        cache = self.db.scalar(
            select(ThreadSummaryCache)
            .where(ThreadSummaryCache.thread_id == thread_id)
        )

        if not cache:
            logger.error(f"Incremental summarization called but no cache exists for {thread_id}")
            return self._full_summarize(thread_id)

        # Get last summarized node to find its sequence_id
        last_node = self.db.get(Node, last_node_id)
        if not last_node:
            logger.error(f"Last node {last_node_id} not found, falling back to full summarization")
            return self._full_summarize(thread_id)

        # Get only NEW nodes (after last_node)
        new_nodes = self.db.scalars(
            select(Node)
            .where(Node.thread_id == thread_id)
            .where(Node.sequence_id > last_node.sequence_id)
            .order_by(Node.sequence_id)
        ).all()

        if not new_nodes:
            logger.warning(f"No new nodes found for incremental summarization of {thread_id}")
            return cache.summary

        # Format new content
        new_content = "\n".join([f"- {node.content}" for node in new_nodes])

        # Generate incremental summary using LLM
        # The LLM sees the current summary + new content and produces an updated summary
        logger.debug(f"Calling LLM for incremental summary: {len(cache.summary)} chars current, {len(new_content)} chars new")

        updated_summary = self.llm_provider.generate_summary(
            context=cache.summary,
            new_content=new_content
        )

        # Update cache with new summary and latest node
        latest_node = new_nodes[-1]
        cache.summary = updated_summary
        cache.last_node_id = latest_node.id
        cache.node_count = cache.node_count + len(new_nodes)
        cache.generated_at = datetime.now(timezone.utc)

        # Note: We could track tokens_used here if the LLM provider returns it
        # For now, keeping model_used from original cache

        self.db.commit()

        logger.info(f"Incremental summary generated for {thread_id}: {len(new_nodes)} new nodes summarized")
        return updated_summary

    def _full_summarize(self, thread_id: str) -> str:
        """Generate full summary from all thread nodes.

        Used when:
        1. No cache exists yet
        2. Last summarized node was deleted
        3. Force regeneration requested

        Args:
            thread_id: Thread identifier

        Returns:
            Full summary text
        """
        # Get all nodes
        nodes = self.db.scalars(
            select(Node)
            .where(Node.thread_id == thread_id)
            .order_by(Node.sequence_id)
        ).all()

        if not nodes:
            logger.warning(f"Thread {thread_id} has no nodes")
            return "No content in this thread yet."

        # Format all content
        full_content = "\n".join([f"- {node.content}" for node in nodes])

        # Generate summary from scratch
        logger.debug(f"Calling LLM for full summary: {len(nodes)} nodes, {len(full_content)} chars")

        summary = self.llm_provider.generate_summary(
            context="",  # No prior context for full summarization
            new_content=full_content
        )

        # Create or update cache
        cache = self.db.scalar(
            select(ThreadSummaryCache)
            .where(ThreadSummaryCache.thread_id == thread_id)
        )

        latest_node = nodes[-1]

        if cache:
            # Update existing cache
            cache.summary = summary
            cache.last_node_id = latest_node.id
            cache.node_count = len(nodes)
            cache.generated_at = datetime.now(timezone.utc)
            # model_used stays the same (or could be updated if needed)
        else:
            # Create new cache entry
            cache = ThreadSummaryCache(
                id=str(uuid.uuid4()),
                thread_id=thread_id,
                summary=summary,
                last_node_id=latest_node.id,
                node_count=len(nodes),
                model_used="default",  # Could extract from llm_provider if available
                tokens_used=0,  # Could track if LLM provider returns it
                generated_at=datetime.now(timezone.utc)
            )
            self.db.add(cache)

        self.db.commit()

        logger.info(f"Full summary generated for {thread_id}: {len(nodes)} nodes summarized")
        return summary

    def invalidate_cache(self, thread_id: str) -> None:
        """Invalidate (delete) cached summary for a thread.

        Useful for forcing regeneration or cleanup.

        Args:
            thread_id: Thread identifier
        """
        cache = self.db.scalar(
            select(ThreadSummaryCache)
            .where(ThreadSummaryCache.thread_id == thread_id)
        )

        if cache:
            self.db.delete(cache)
            self.db.commit()
            logger.info(f"Invalidated cache for thread {thread_id}")
        else:
            logger.debug(f"No cache to invalidate for thread {thread_id}")

    def get_cache_stats(self, thread_id: str) -> Optional[dict]:
        """Get cache statistics for a thread.

        Useful for debugging and monitoring.

        Args:
            thread_id: Thread identifier

        Returns:
            Dictionary with cache stats or None if no cache
        """
        cache = self.db.scalar(
            select(ThreadSummaryCache)
            .where(ThreadSummaryCache.thread_id == thread_id)
        )

        if not cache:
            return None

        is_stale, _, new_node_count = self.check_staleness(thread_id)

        return {
            "thread_id": thread_id,
            "last_node_id": cache.last_node_id,
            "node_count": cache.node_count,
            "model_used": cache.model_used,
            "tokens_used": cache.tokens_used,
            "generated_at": cache.generated_at.isoformat(),
            "is_stale": is_stale,
            "new_nodes_since_summary": new_node_count
        }

    def __del__(self):
        """Cleanup database session if we own it."""
        if self._owns_db and self.db:
            try:
                self.db.close()
            except Exception:
                pass


# Fix missing import
from sqlalchemy import func


# Convenience functions for standalone usage

def get_thread_summary(
    thread_id: str,
    llm_provider: ILLMProvider,
    db: Optional[Session] = None,
    force: bool = False
) -> str:
    """Get or generate thread summary using lazy evaluation.

    Convenience function for getting summaries without creating a manager instance.

    Args:
        thread_id: Thread identifier
        llm_provider: LLM provider for summary generation
        db: Optional database session
        force: Force regeneration even if cache is fresh

    Returns:
        Thread summary text
    """
    manager = ThreadSummaryManager(llm_provider, db)
    return manager.generate_summary(thread_id, force=force)


def check_summary_staleness(
    thread_id: str,
    db: Optional[Session] = None
) -> Tuple[bool, Optional[str], int]:
    """Check if thread summary cache is stale.

    Args:
        thread_id: Thread identifier
        db: Optional database session

    Returns:
        Tuple of (is_stale, last_node_id, new_node_count)
    """
    # Create a dummy LLM provider since we don't need it for staleness check
    from vlt.lib.llm import OpenRouterLLMProvider
    manager = ThreadSummaryManager(OpenRouterLLMProvider(), db)
    return manager.check_staleness(thread_id)
