"""Pydantic models for Thread Sync feature."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ThreadEntry(BaseModel):
    """Single entry/node within a thread."""

    entry_id: str = Field(..., description="UUID of the entry")
    sequence_id: int = Field(..., ge=0, description="Order within thread")
    content: str = Field(..., min_length=1, max_length=100000)
    author: str = Field("user", max_length=64)
    timestamp: datetime


class Thread(BaseModel):
    """Thread synced from vlt-cli."""

    thread_id: str = Field(..., min_length=1, max_length=128)
    project_id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=256)
    status: Literal["active", "archived", "blocked"] = "active"
    created_at: datetime
    updated_at: datetime
    entries: Optional[List[ThreadEntry]] = None


class SyncRequest(BaseModel):
    """Request to sync thread entries from CLI."""

    thread_id: str = Field(..., min_length=1, max_length=128)
    project_id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=256)
    status: Literal["active", "archived", "blocked"] = "active"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    entries: List[ThreadEntry] = Field(..., min_length=1)


class SyncResponse(BaseModel):
    """Response after syncing entries."""

    thread_id: str
    synced_count: int
    last_synced_sequence: int


class SyncStatus(BaseModel):
    """Sync status for a thread."""

    thread_id: str
    last_synced_sequence: int = Field(
        -1, description="Highest synced sequence_id (-1 if never synced)"
    )
    last_sync_at: datetime
    sync_error: Optional[str] = None


class ThreadListResponse(BaseModel):
    """List of threads for a user."""

    threads: List[Thread]
    total: int


class ThreadSearchResult(BaseModel):
    """Search result from thread FTS."""

    thread_id: str
    entry_id: str
    content: str = Field(..., description="Matching content snippet")
    author: str
    timestamp: datetime
    score: float = Field(..., description="Relevance score")


class ThreadSearchResponse(BaseModel):
    """Response for thread search."""

    results: List[ThreadSearchResult]
    total: int


class SummarizeRequest(BaseModel):
    """Request to summarize a thread."""

    current_summary: Optional[str] = Field(
        None,
        description="Existing summary to update (for incremental summarization)"
    )
    entries_limit: int = Field(
        100,
        ge=1,
        le=500,
        description="Maximum number of recent entries to include in summarization"
    )


class SummarizeResponse(BaseModel):
    """Response from thread summarization."""

    thread_id: str
    summary: str = Field(..., description="Generated summary text")
    model: Optional[str] = Field(None, description="Model used for summarization")
    tokens_used: int = Field(0, description="Approximate tokens consumed")
    success: bool = Field(True, description="Whether summarization succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")


__all__ = [
    "ThreadEntry",
    "Thread",
    "SyncRequest",
    "SyncResponse",
    "SyncStatus",
    "ThreadListResponse",
    "ThreadSearchResult",
    "ThreadSearchResponse",
    "SummarizeRequest",
    "SummarizeResponse",
]
