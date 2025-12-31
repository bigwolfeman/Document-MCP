"""Pydantic models for Oracle context persistence (009-oracle-agent)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ContextStatus(str, Enum):
    """Status of an Oracle context session."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class ExchangeRole(str, Enum):
    """Role of a participant in an Oracle exchange."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCallStatus(str, Enum):
    """Status of a tool call execution."""

    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"


class ToolCategory(str, Enum):
    """Category of Oracle tools."""

    VAULT = "vault"
    THREAD = "thread"
    CODE = "code"
    WEB = "web"
    META = "meta"


class ToolCall(BaseModel):
    """A single tool invocation within an exchange."""

    id: str = Field(..., description="OpenRouter tool_call_id")
    name: str = Field(..., description="Tool name (e.g., 'search_code')")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool parameters")
    result: Optional[str] = Field(None, description="Tool execution result")
    status: ToolCallStatus = Field(
        default=ToolCallStatus.PENDING, description="Execution status"
    )
    duration_ms: Optional[int] = Field(None, description="Execution time in milliseconds")


class OracleExchange(BaseModel):
    """A single turn in the Oracle conversation (question + tool calls + answer)."""

    id: str = Field(..., description="UUID for this exchange")
    role: ExchangeRole = Field(..., description="Role of the participant")
    content: str = Field(..., description="Message content")
    tool_calls: Optional[List[ToolCall]] = Field(
        None, description="Tools invoked in this exchange"
    )
    tool_call_id: Optional[str] = Field(
        None, description="For tool results, the ID of the originating call"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When this exchange occurred"
    )
    token_count: int = Field(0, description="Tokens in this exchange")
    key_insight: Optional[str] = Field(
        None, description="Summary for compression (important exchanges only)"
    )
    mentioned_symbols: List[str] = Field(
        default_factory=list, description="Code symbols referenced in this turn"
    )
    mentioned_files: List[str] = Field(
        default_factory=list, description="Files referenced in this turn"
    )


class OracleContext(BaseModel):
    """Persistent conversation state for a user+project pair.

    Survives sessions and model changes. Contains compressed summary,
    recent exchanges, key decisions, and token usage tracking.
    """

    id: str = Field(..., description="UUID primary key")
    user_id: str = Field(..., description="User identifier")
    project_id: str = Field(..., description="Project scope")
    session_start: datetime = Field(
        default_factory=datetime.utcnow, description="When context was created"
    )
    last_activity: Optional[datetime] = Field(
        None, description="Last interaction timestamp"
    )
    last_model: Optional[str] = Field(None, description="Model used in last turn")
    token_budget: int = Field(16000, description="Max tokens allowed")
    tokens_used: int = Field(0, description="Current token count")
    compressed_summary: Optional[str] = Field(
        None, description="Older exchanges compressed into summary"
    )
    recent_exchanges: List[OracleExchange] = Field(
        default_factory=list, description="Last N exchanges (preserved verbatim)"
    )
    key_decisions: List[str] = Field(
        default_factory=list, description="Important decisions (never compressed)"
    )
    mentioned_symbols: Optional[str] = Field(
        None, description="Comma-separated symbols mentioned across session"
    )
    mentioned_files: Optional[str] = Field(
        None, description="Comma-separated files mentioned across session"
    )
    status: ContextStatus = Field(
        default=ContextStatus.ACTIVE, description="Context session status"
    )
    compression_count: int = Field(0, description="Times context has been compressed")


class OracleContextResponse(BaseModel):
    """API response for context retrieval."""

    id: str
    project_id: str
    session_start: datetime
    last_activity: Optional[datetime]
    token_budget: int
    tokens_used: int
    tokens_remaining: int
    compressed_summary: Optional[str]
    recent_exchanges: List[OracleExchange]
    key_decisions: List[str]
    status: ContextStatus


class Tool(BaseModel):
    """Definition of a tool the Oracle can invoke."""

    name: str = Field(..., description="Unique tool identifier")
    description: str = Field(..., description="What the tool does")
    parameters: Dict[str, Any] = Field(..., description="JSON Schema for params")
    agent_scope: List[str] = Field(
        default=["oracle"], description="Which agents can use this tool"
    )
    category: ToolCategory = Field(..., description="Tool category for organization")


class Subagent(BaseModel):
    """Definition of a specialized subagent."""

    name: str = Field(..., description="Subagent identifier")
    system_prompt_path: str = Field(..., description="Path to prompt file")
    allowed_tools: List[str] = Field(..., description="Tool names it can use")
    max_turns: int = Field(10, description="Max agent loop iterations")
    model_override: Optional[str] = Field(
        None, description="Different model for this subagent"
    )


__all__ = [
    "ContextStatus",
    "ExchangeRole",
    "ToolCallStatus",
    "ToolCategory",
    "ToolCall",
    "OracleExchange",
    "OracleContext",
    "OracleContextResponse",
    "Tool",
    "Subagent",
]
