"""
Pydantic schemas for Vlt Oracle feature.

This module defines data transfer objects (DTOs) and value objects for the oracle
orchestration, retrieval, and API response layers.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# Enums

class SourceType(str, Enum):
    """Type of knowledge source for a retrieval result."""
    VAULT = "vault"
    CODE = "code"
    THREAD = "thread"
    DEFINITION = "definition"
    REFERENCE = "reference"


class RetrievalMethod(str, Enum):
    """Method used to retrieve a result."""
    VECTOR = "vector"
    BM25 = "bm25"
    GRAPH = "graph"
    CTAGS = "ctags"
    SCIP = "scip"


# Value Objects

class RetrievalResult(BaseModel):
    """A single result from any retrieval path."""

    content: str = Field(..., description="Retrieved text content")
    source_type: SourceType = Field(..., description="Type of knowledge source")
    source_path: str = Field(..., description="Path/ID to source (file:line, note path, thread ID)")
    retrieval_method: RetrievalMethod = Field(..., description="Retrieval method used")
    score: float = Field(..., ge=0.0, le=1.0, description="Relevance score (0.0-1.0, normalized)")
    token_count: int = Field(..., description="Approximate tokens in content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Source-specific metadata")


class OracleQuery(BaseModel):
    """Input to oracle orchestrator."""

    question: str = Field(..., description="Natural language question")
    sources: Optional[List[str]] = Field(None, description="Filter: ['vault', 'code', 'threads'] or None for all")
    explain: bool = Field(False, description="Include retrieval traces in response")
    project_id: str = Field(..., description="Project context")
    user_id: str = Field(..., description="User making request")
    max_results: int = Field(20, description="Max results per retrieval path")
    max_context_tokens: int = Field(16000, description="Token budget for synthesis")
    include_repo_map: bool = Field(True, description="Include repo map slice")
    include_tests: bool = Field(True, description="Boost test files in ranking")


class OracleResponse(BaseModel):
    """Output from oracle orchestrator."""

    answer: str = Field(..., description="Synthesized markdown answer")
    sources: List[RetrievalResult] = Field(..., description="Cited sources with scores (top-k)")
    repo_map_slice: Optional[str] = Field(None, description="Included portion of repo map")
    traces: Optional[Dict[str, Any]] = Field(None, description="Debug info (if explain=true)")
    query_type: str = Field(..., description="Detected query type (definition, reference, conceptual)")
    model: str = Field(..., description="Model used for synthesis")
    tokens_used: int = Field(..., description="Total tokens consumed")
    cost_cents: float = Field(..., description="Estimated cost in cents")
    duration_ms: int = Field(..., description="Processing time in milliseconds")


# API Response Schemas

class CodeChunkSchema(BaseModel):
    """Code chunk for API responses (without embedding blob)."""

    id: str = Field(..., description="Unique identifier")
    project_id: str = Field(..., description="Parent project")
    file_path: str = Field(..., description="Relative path from project root")
    file_hash: str = Field(..., description="MD5 hash for change detection")
    chunk_type: str = Field(..., description="Type: function, class, method, module")
    name: str = Field(..., description="Symbol name")
    qualified_name: str = Field(..., description="Full path (e.g., VaultService.search_notes)")
    language: str = Field(..., description="Programming language")
    lineno: int = Field(..., description="Start line number (1-indexed)")
    end_lineno: int = Field(..., description="End line number")
    imports: Optional[str] = Field(None, description="Import statements used by this chunk")
    class_context: Optional[str] = Field(None, description="Enclosing class header (for methods)")
    signature: Optional[str] = Field(None, description="Full function/method signature with types")
    decorators: Optional[str] = Field(None, description="Decorator lines")
    docstring: Optional[str] = Field(None, description="Extracted documentation string")
    body: str = Field(..., description="Function/method body")
    retrieval_method: Optional[RetrievalMethod] = Field(None, description="How this chunk was retrieved")
    token_count: Optional[int] = Field(None, description="Approximate token count")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class RepoMapStats(BaseModel):
    """Statistics for a generated repository map."""

    files_included: int = Field(..., description="Number of files in map")
    symbols_included: int = Field(..., description="Number of symbols in map")
    symbols_total: int = Field(..., description="Total symbols before pruning")
    token_count: int = Field(..., description="Token count of map text")


class RepoMapSchema(BaseModel):
    """Repository map for API responses."""

    map: str = Field(..., description="Generated Aider-style map text")
    stats: RepoMapStats = Field(..., description="Map statistics")
    scope_applied: Optional[str] = Field(None, description="Subdirectory scope (null = entire repo)")
