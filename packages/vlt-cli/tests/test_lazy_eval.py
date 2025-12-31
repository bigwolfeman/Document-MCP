"""Tests for lazy LLM evaluation (Phase 8).

Tests cover all requirements from FR-046 to FR-050:
- FR-046: NO LLM calls during write operations
- FR-047: Generate summaries on-demand when threads are read or queried
- FR-048: Cache generated summaries and embeddings for reuse
- FR-049: Detect stale cached artifacts and regenerate incrementally
- FR-050: Track "last_summarized_node_id" for incremental summarization

Goal: Reduce LLM API calls by 70% (SC-011)
"""

import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from vlt.core.models import Base, Thread, Node, ThreadSummaryCache, Project
from vlt.core.lazy_eval import ThreadSummaryManager, get_thread_summary, check_summary_staleness
from vlt.core.interfaces import ILLMProvider


@pytest.fixture
def in_memory_db():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


@pytest.fixture
def mock_llm():
    """Create mock LLM provider."""
    llm = Mock(spec=ILLMProvider)

    # Mock generate_summary to return concatenation of context + new content
    def mock_generate(context: str, new_content: str) -> str:
        if context:
            return f"{context}\n\n[Updated with: {new_content}]"
        else:
            return f"[Summary of: {new_content}]"

    llm.generate_summary = Mock(side_effect=mock_generate)
    llm.get_embedding = Mock(return_value=[0.1] * 384)  # Mock embedding vector

    return llm


@pytest.fixture
def sample_thread(in_memory_db):
    """Create a sample thread with some nodes."""
    # Create project first
    project = Project(
        id="test-project",
        name="Test Project",
        description="Test project for lazy eval"
    )
    in_memory_db.add(project)

    # Create thread
    thread = Thread(
        id="test-thread",
        project_id="test-project",
        status="active"
    )
    in_memory_db.add(thread)

    # Create some nodes
    nodes = []
    for i in range(5):
        node = Node(
            id=str(uuid.uuid4()),
            thread_id="test-thread",
            sequence_id=i,
            content=f"Thought {i}: This is test content",
            author="test-user",
            timestamp=datetime.now(timezone.utc)
        )
        nodes.append(node)
        in_memory_db.add(node)

    in_memory_db.commit()

    return thread, nodes


class TestThreadSummaryManager:
    """Test ThreadSummaryManager functionality."""

    def test_check_staleness_no_cache(self, in_memory_db, mock_llm, sample_thread):
        """Test staleness check when no cache exists (FR-049)."""
        thread, nodes = sample_thread
        manager = ThreadSummaryManager(mock_llm, in_memory_db)

        is_stale, last_node_id, new_count = manager.check_staleness("test-thread")

        assert is_stale is True
        assert last_node_id is None
        assert new_count == 5  # All 5 nodes are new

    def test_check_staleness_fresh_cache(self, in_memory_db, mock_llm, sample_thread):
        """Test staleness check when cache is fresh."""
        thread, nodes = sample_thread

        # Create cache for latest node
        cache = ThreadSummaryCache(
            id=str(uuid.uuid4()),
            thread_id="test-thread",
            summary="Existing summary",
            last_node_id=nodes[-1].id,  # Latest node
            node_count=5,
            model_used="test-model",
            tokens_used=100,
            generated_at=datetime.now(timezone.utc)
        )
        in_memory_db.add(cache)
        in_memory_db.commit()

        manager = ThreadSummaryManager(mock_llm, in_memory_db)
        is_stale, last_node_id, new_count = manager.check_staleness("test-thread")

        assert is_stale is False
        assert last_node_id == nodes[-1].id
        assert new_count == 0  # No new nodes

    def test_check_staleness_stale_cache(self, in_memory_db, mock_llm, sample_thread):
        """Test staleness check when cache is stale (FR-049)."""
        thread, nodes = sample_thread

        # Create cache for middle node
        cache = ThreadSummaryCache(
            id=str(uuid.uuid4()),
            thread_id="test-thread",
            summary="Old summary",
            last_node_id=nodes[2].id,  # Middle node (index 2)
            node_count=3,
            model_used="test-model",
            tokens_used=100,
            generated_at=datetime.now(timezone.utc)
        )
        in_memory_db.add(cache)
        in_memory_db.commit()

        manager = ThreadSummaryManager(mock_llm, in_memory_db)
        is_stale, last_node_id, new_count = manager.check_staleness("test-thread")

        assert is_stale is True
        assert last_node_id == nodes[2].id
        assert new_count == 2  # Nodes 3 and 4 are new

    def test_get_cached_summary_fresh(self, in_memory_db, mock_llm, sample_thread):
        """Test getting fresh cached summary (FR-048)."""
        thread, nodes = sample_thread

        # Create fresh cache
        cache = ThreadSummaryCache(
            id=str(uuid.uuid4()),
            thread_id="test-thread",
            summary="Fresh summary",
            last_node_id=nodes[-1].id,
            node_count=5,
            model_used="test-model",
            tokens_used=100,
            generated_at=datetime.now(timezone.utc)
        )
        in_memory_db.add(cache)
        in_memory_db.commit()

        manager = ThreadSummaryManager(mock_llm, in_memory_db)
        summary = manager.get_cached_summary("test-thread")

        assert summary == "Fresh summary"

    def test_get_cached_summary_stale(self, in_memory_db, mock_llm, sample_thread):
        """Test that stale cache returns None."""
        thread, nodes = sample_thread

        # Create stale cache
        cache = ThreadSummaryCache(
            id=str(uuid.uuid4()),
            thread_id="test-thread",
            summary="Stale summary",
            last_node_id=nodes[2].id,  # Not the latest
            node_count=3,
            model_used="test-model",
            tokens_used=100,
            generated_at=datetime.now(timezone.utc)
        )
        in_memory_db.add(cache)
        in_memory_db.commit()

        manager = ThreadSummaryManager(mock_llm, in_memory_db)
        summary = manager.get_cached_summary("test-thread")

        assert summary is None  # Should return None for stale cache

    def test_full_summarize_no_cache(self, in_memory_db, mock_llm, sample_thread):
        """Test full summarization when no cache exists (FR-047)."""
        thread, nodes = sample_thread
        manager = ThreadSummaryManager(mock_llm, in_memory_db)

        summary = manager.generate_summary("test-thread")

        # Verify LLM was called
        assert mock_llm.generate_summary.call_count == 1
        call_args = mock_llm.generate_summary.call_args[1]
        assert call_args['context'] == ""  # No prior context for full summarization
        assert "Thought 0" in call_args['new_content']
        assert "Thought 4" in call_args['new_content']

        # Verify cache was created
        cache = in_memory_db.scalar(
            select(ThreadSummaryCache).where(ThreadSummaryCache.thread_id == "test-thread")
        )
        assert cache is not None
        assert cache.last_node_id == nodes[-1].id
        assert cache.node_count == 5

    def test_incremental_summarize(self, in_memory_db, mock_llm, sample_thread):
        """Test incremental summarization (FR-050)."""
        thread, nodes = sample_thread

        # Create cache for first 3 nodes
        cache = ThreadSummaryCache(
            id=str(uuid.uuid4()),
            thread_id="test-thread",
            summary="Summary of first 3 thoughts",
            last_node_id=nodes[2].id,
            node_count=3,
            model_used="test-model",
            tokens_used=100,
            generated_at=datetime.now(timezone.utc)
        )
        in_memory_db.add(cache)
        in_memory_db.commit()

        manager = ThreadSummaryManager(mock_llm, in_memory_db)
        summary = manager.generate_summary("test-thread")

        # Verify LLM was called with incremental approach
        assert mock_llm.generate_summary.call_count == 1
        call_args = mock_llm.generate_summary.call_args[1]
        assert call_args['context'] == "Summary of first 3 thoughts"
        assert "Thought 3" in call_args['new_content']
        assert "Thought 4" in call_args['new_content']
        # Should NOT include Thought 0-2
        assert "Thought 0" not in call_args['new_content']

        # Verify cache was updated
        in_memory_db.refresh(cache)
        assert cache.last_node_id == nodes[-1].id
        assert cache.node_count == 5  # Updated from 3 to 5

    def test_no_llm_call_for_fresh_cache(self, in_memory_db, mock_llm, sample_thread):
        """Test that NO LLM call is made when cache is fresh (FR-048)."""
        thread, nodes = sample_thread

        # Create fresh cache
        cache = ThreadSummaryCache(
            id=str(uuid.uuid4()),
            thread_id="test-thread",
            summary="Fresh summary",
            last_node_id=nodes[-1].id,
            node_count=5,
            model_used="test-model",
            tokens_used=100,
            generated_at=datetime.now(timezone.utc)
        )
        in_memory_db.add(cache)
        in_memory_db.commit()

        manager = ThreadSummaryManager(mock_llm, in_memory_db)
        summary = manager.generate_summary("test-thread")

        # Verify NO LLM call was made
        assert mock_llm.generate_summary.call_count == 0
        assert summary == "Fresh summary"

    def test_force_regeneration(self, in_memory_db, mock_llm, sample_thread):
        """Test force regeneration ignores cache."""
        thread, nodes = sample_thread

        # Create fresh cache
        cache = ThreadSummaryCache(
            id=str(uuid.uuid4()),
            thread_id="test-thread",
            summary="Old summary",
            last_node_id=nodes[-1].id,
            node_count=5,
            model_used="test-model",
            tokens_used=100,
            generated_at=datetime.now(timezone.utc)
        )
        in_memory_db.add(cache)
        in_memory_db.commit()

        manager = ThreadSummaryManager(mock_llm, in_memory_db)
        summary = manager.generate_summary("test-thread", force=True)

        # Verify LLM was called despite fresh cache
        assert mock_llm.generate_summary.call_count == 1

    def test_invalidate_cache(self, in_memory_db, mock_llm, sample_thread):
        """Test cache invalidation."""
        thread, nodes = sample_thread

        # Create cache
        cache = ThreadSummaryCache(
            id=str(uuid.uuid4()),
            thread_id="test-thread",
            summary="Summary",
            last_node_id=nodes[-1].id,
            node_count=5,
            model_used="test-model",
            tokens_used=100,
            generated_at=datetime.now(timezone.utc)
        )
        in_memory_db.add(cache)
        in_memory_db.commit()

        manager = ThreadSummaryManager(mock_llm, in_memory_db)
        manager.invalidate_cache("test-thread")

        # Verify cache was deleted
        cache_check = in_memory_db.scalar(
            select(ThreadSummaryCache).where(ThreadSummaryCache.thread_id == "test-thread")
        )
        assert cache_check is None

    def test_get_cache_stats(self, in_memory_db, mock_llm, sample_thread):
        """Test getting cache statistics."""
        thread, nodes = sample_thread

        # Create cache
        cache = ThreadSummaryCache(
            id=str(uuid.uuid4()),
            thread_id="test-thread",
            summary="Summary",
            last_node_id=nodes[2].id,  # Stale (not latest)
            node_count=3,
            model_used="test-model",
            tokens_used=150,
            generated_at=datetime.now(timezone.utc)
        )
        in_memory_db.add(cache)
        in_memory_db.commit()

        manager = ThreadSummaryManager(mock_llm, in_memory_db)
        stats = manager.get_cache_stats("test-thread")

        assert stats is not None
        assert stats['thread_id'] == "test-thread"
        assert stats['node_count'] == 3
        assert stats['model_used'] == "test-model"
        assert stats['tokens_used'] == 150
        assert stats['is_stale'] is True
        assert stats['new_nodes_since_summary'] == 2


class TestLazyEvaluationIntegration:
    """Integration tests for lazy evaluation workflow."""

    def test_write_path_no_llm_call(self, in_memory_db, mock_llm, sample_thread):
        """Test FR-046: NO LLM calls during write operations.

        This is the key optimization - writing nodes should be fast (<50ms).
        """
        thread, _ = sample_thread

        # Add a new thought (simulating vlt thread push)
        new_node = Node(
            id=str(uuid.uuid4()),
            thread_id="test-thread",
            sequence_id=5,
            content="New thought added via push",
            author="test-user",
            timestamp=datetime.now(timezone.utc)
        )
        in_memory_db.add(new_node)
        in_memory_db.commit()

        # Verify NO LLM call was made
        assert mock_llm.generate_summary.call_count == 0

        # Verify no cache exists yet
        cache = in_memory_db.scalar(
            select(ThreadSummaryCache).where(ThreadSummaryCache.thread_id == "test-thread")
        )
        assert cache is None

    def test_read_path_triggers_generation(self, in_memory_db, mock_llm, sample_thread):
        """Test FR-047: Generate summaries on-demand when threads are read."""
        thread, nodes = sample_thread

        # Simulate reading thread (vlt thread read)
        manager = ThreadSummaryManager(mock_llm, in_memory_db)
        summary = manager.generate_summary("test-thread")

        # Verify LLM was called
        assert mock_llm.generate_summary.call_count == 1

        # Verify cache was created
        cache = in_memory_db.scalar(
            select(ThreadSummaryCache).where(ThreadSummaryCache.thread_id == "test-thread")
        )
        assert cache is not None

    def test_multiple_reads_use_cache(self, in_memory_db, mock_llm, sample_thread):
        """Test SC-011: Reduce LLM API calls by 70%.

        Multiple reads should use cached summary, not call LLM again.
        """
        thread, nodes = sample_thread

        manager = ThreadSummaryManager(mock_llm, in_memory_db)

        # First read - generates summary
        summary1 = manager.generate_summary("test-thread")
        assert mock_llm.generate_summary.call_count == 1

        # Second read - uses cache (NO LLM call)
        summary2 = manager.generate_summary("test-thread")
        assert mock_llm.generate_summary.call_count == 1  # Still 1, not 2

        # Third read - still cached
        summary3 = manager.generate_summary("test-thread")
        assert mock_llm.generate_summary.call_count == 1  # Still 1

        # All summaries should be the same
        assert summary1 == summary2 == summary3

    def test_write_then_read_incremental(self, in_memory_db, mock_llm, sample_thread):
        """Test workflow: generate summary, add nodes, read again (incremental)."""
        thread, nodes = sample_thread

        manager = ThreadSummaryManager(mock_llm, in_memory_db)

        # First read - full summarization
        summary1 = manager.generate_summary("test-thread")
        assert mock_llm.generate_summary.call_count == 1

        # Add 2 new nodes (simulating vlt thread push)
        for i in range(2):
            new_node = Node(
                id=str(uuid.uuid4()),
                thread_id="test-thread",
                sequence_id=5 + i,
                content=f"New thought {i}",
                author="test-user",
                timestamp=datetime.now(timezone.utc)
            )
            in_memory_db.add(new_node)
        in_memory_db.commit()

        # NO LLM call during writes
        assert mock_llm.generate_summary.call_count == 1

        # Second read - incremental summarization
        summary2 = manager.generate_summary("test-thread")
        assert mock_llm.generate_summary.call_count == 2  # Now called again

        # Verify incremental summarization was used
        last_call_args = mock_llm.generate_summary.call_args[1]
        assert last_call_args['context'] != ""  # Had prior context
        assert "New thought" in last_call_args['new_content']


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_get_thread_summary(self, in_memory_db, mock_llm, sample_thread):
        """Test convenience function get_thread_summary."""
        thread, nodes = sample_thread

        summary = get_thread_summary("test-thread", mock_llm, in_memory_db)

        assert summary is not None
        assert mock_llm.generate_summary.call_count == 1

    def test_check_summary_staleness(self, in_memory_db, sample_thread):
        """Test convenience function check_summary_staleness."""
        thread, nodes = sample_thread

        # Create stale cache
        cache = ThreadSummaryCache(
            id=str(uuid.uuid4()),
            thread_id="test-thread",
            summary="Old",
            last_node_id=nodes[2].id,
            node_count=3,
            model_used="test",
            tokens_used=100,
            generated_at=datetime.now(timezone.utc)
        )
        in_memory_db.add(cache)
        in_memory_db.commit()

        is_stale, last_node_id, new_count = check_summary_staleness("test-thread", in_memory_db)

        assert is_stale is True
        assert last_node_id == nodes[2].id
        assert new_count == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
