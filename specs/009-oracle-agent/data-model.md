# Data Model: Oracle Agent Architecture

**Feature**: 009-oracle-agent
**Date**: 2025-12-31

## Entity Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  OracleContext  │────▶│  OracleExchange  │────▶│    ToolCall     │
│  (per user+proj)│     │  (conversation)  │     │  (tool results) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │
        │ uses
        ▼
┌─────────────────┐     ┌──────────────────┐
│      Tool       │────▶│    Subagent      │
│  (capabilities) │     │  (Librarian)     │
└─────────────────┘     └──────────────────┘
        │
        │ operates on
        ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   VaultNote     │     │     Thread       │     │   CodeChunk     │
│   (existing)    │     │   (existing)     │     │   (existing)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

---

## New Entities

### OracleContext

Persistent conversation state for a user+project pair. Survives sessions and model changes.

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| id | string | UUID primary key | Required, unique |
| user_id | string | User identifier | Required, indexed |
| project_id | string | Project scope | Required, indexed |
| session_start | datetime | When context was created | Required |
| last_activity | datetime | Last interaction | Auto-updated |
| last_model | string | Model used in last turn | Nullable |
| token_budget | integer | Max tokens allowed | Default: 16000 |
| tokens_used | integer | Current token count | Default: 0 |
| compressed_summary | text | Older exchanges compressed | Nullable |
| recent_exchanges_json | text | Last N exchanges (JSON) | Default: "[]" |
| key_decisions_json | text | Important decisions (JSON) | Default: "[]" |
| mentioned_symbols | text | Symbols referenced | Nullable |
| mentioned_files | text | Files referenced | Nullable |
| status | enum | active, suspended, closed | Default: active |
| compression_count | integer | Times compressed | Default: 0 |

**Unique Constraint**: (user_id, project_id)

**Relationships**:
- One OracleContext per user+project combination
- Contains many OracleExchanges (in recent_exchanges_json)

**State Transitions**:
```
Created → Active → Suspended (model change) → Active
                 → Closed (manual or expired)
```

---

### OracleExchange

A single turn in the conversation (question + tool calls + answer).

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| id | string | UUID | Required |
| role | enum | user, assistant, tool | Required |
| content | text | Message content | Required |
| tool_calls | list[ToolCall] | Tools invoked | Nullable |
| tool_call_id | string | For tool results | Nullable |
| timestamp | datetime | When created | Required |
| token_count | integer | Tokens in this exchange | Required |
| key_insight | string | Summary for compression | Nullable |
| mentioned_symbols | list[string] | Symbols in this turn | Default: [] |
| mentioned_files | list[string] | Files in this turn | Default: [] |

**Note**: Stored as JSON in OracleContext.recent_exchanges_json

---

### ToolCall

A single tool invocation within an exchange.

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| id | string | OpenRouter tool_call_id | Required |
| name | string | Tool name (e.g., "search_code") | Required |
| arguments | dict | Tool parameters | Required |
| result | text | Tool execution result | Filled after execution |
| status | enum | pending, success, error | Required |
| duration_ms | integer | Execution time | Nullable |

---

### Tool

A capability the Oracle can invoke. Defined in code, described in prompts.

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| name | string | Unique tool identifier | Required, unique |
| description | string | What the tool does | Required |
| parameters | dict | JSON Schema for params | Required |
| agent_scope | list[string] | Which agents can use | Default: ["oracle"] |
| category | enum | vault, thread, code, web, meta | Required |

**Static Definition** (not in database):
```python
ORACLE_TOOLS = [
    Tool(
        name="search_code",
        description="Search codebase for relevant code",
        parameters={"type": "object", "properties": {...}},
        agent_scope=["oracle", "librarian"],
        category="code"
    ),
    # ...
]
```

---

### Subagent

A specialized agent with scoped tools and own system prompt.

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| name | string | Subagent identifier | Required, unique |
| system_prompt_path | string | Path to prompt file | Required |
| allowed_tools | list[string] | Tool names it can use | Required |
| max_turns | integer | Max agent loop iterations | Default: 10 |
| model_override | string | Different model (optional) | Nullable |

**Static Definition** (not in database):
```python
LIBRARIAN_SUBAGENT = Subagent(
    name="librarian",
    system_prompt_path="librarian/system.md",
    allowed_tools=["vault_read", "vault_write", "vault_list", "vault_move", "vault_create_index"],
    max_turns=10,
    model_override="deepseek/deepseek-chat"  # Cheaper model for organization
)
```

---

## Extended Existing Entities

### Thread (extend thread_entries)

Add support for Oracle-authored entries.

| New Field | Type | Description |
|-----------|------|-------------|
| author | string | "user", "claude", "oracle", "librarian" |
| entry_type | enum | thought, decision, research, insight |

**Validation**: author must be one of allowed values

---

## Validation Rules

### OracleContext

1. token_budget must be between 4000 and 128000
2. tokens_used cannot exceed token_budget * 1.1 (10% overflow allowed before error)
3. status must be valid enum value
4. project_id must exist in user's accessible projects

### OracleExchange

1. role must be valid enum value
2. If role is "tool", tool_call_id is required
3. token_count must be positive integer
4. content cannot be empty for user/assistant roles

### ToolCall

1. name must match a defined tool
2. arguments must validate against tool's parameter schema
3. status starts as "pending", must be updated after execution

---

## SQL Schema (SQLite)

```sql
-- New table for Oracle context persistence
CREATE TABLE IF NOT EXISTS oracle_contexts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    session_start TEXT NOT NULL,
    last_activity TEXT,
    last_model TEXT,
    token_budget INTEGER DEFAULT 16000,
    tokens_used INTEGER DEFAULT 0,
    compressed_summary TEXT,
    recent_exchanges_json TEXT DEFAULT '[]',
    key_decisions_json TEXT DEFAULT '[]',
    mentioned_symbols TEXT,
    mentioned_files TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'closed')),
    compression_count INTEGER DEFAULT 0,
    UNIQUE(user_id, project_id)
);

-- Index for efficient lookup
CREATE INDEX IF NOT EXISTS idx_oracle_contexts_user_project
ON oracle_contexts(user_id, project_id);

-- Index for cleanup queries
CREATE INDEX IF NOT EXISTS idx_oracle_contexts_last_activity
ON oracle_contexts(last_activity);
```

---

## Pydantic Models

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class ContextStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"

class ExchangeRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

class ToolCallStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"

class ToolCategory(str, Enum):
    VAULT = "vault"
    THREAD = "thread"
    CODE = "code"
    WEB = "web"
    META = "meta"

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any]
    result: Optional[str] = None
    status: ToolCallStatus = ToolCallStatus.PENDING
    duration_ms: Optional[int] = None

class OracleExchange(BaseModel):
    id: str
    role: ExchangeRole
    content: str
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    timestamp: datetime
    token_count: int
    key_insight: Optional[str] = None
    mentioned_symbols: List[str] = Field(default_factory=list)
    mentioned_files: List[str] = Field(default_factory=list)

class OracleContext(BaseModel):
    id: str
    user_id: str
    project_id: str
    session_start: datetime
    last_activity: Optional[datetime] = None
    last_model: Optional[str] = None
    token_budget: int = 16000
    tokens_used: int = 0
    compressed_summary: Optional[str] = None
    recent_exchanges: List[OracleExchange] = Field(default_factory=list)
    key_decisions: List[str] = Field(default_factory=list)
    mentioned_symbols: Optional[str] = None
    mentioned_files: Optional[str] = None
    status: ContextStatus = ContextStatus.ACTIVE
    compression_count: int = 0

class Tool(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]
    agent_scope: List[str] = Field(default=["oracle"])
    category: ToolCategory

class Subagent(BaseModel):
    name: str
    system_prompt_path: str
    allowed_tools: List[str]
    max_turns: int = 10
    model_override: Optional[str] = None
```

---

## JSON Serialization

### recent_exchanges_json Format

```json
[
  {
    "id": "uuid-1",
    "role": "user",
    "content": "How does authentication work?",
    "tool_calls": null,
    "timestamp": "2025-01-15T10:30:00Z",
    "token_count": 45,
    "key_insight": null,
    "mentioned_symbols": [],
    "mentioned_files": []
  },
  {
    "id": "uuid-2",
    "role": "assistant",
    "content": "Based on my search...",
    "tool_calls": [
      {
        "id": "call_abc123",
        "name": "search_code",
        "arguments": {"query": "authentication"},
        "result": "Found 3 files...",
        "status": "success",
        "duration_ms": 234
      }
    ],
    "timestamp": "2025-01-15T10:30:05Z",
    "token_count": 1250,
    "key_insight": "Auth uses JWT with refresh tokens",
    "mentioned_symbols": ["AuthService", "JWTHandler"],
    "mentioned_files": ["auth.py", "jwt.py"]
  }
]
```

### key_decisions_json Format

```json
[
  "Using JWT with 24-hour expiry for session management",
  "Database queries go through ThreadService, not direct SQL",
  "Librarian handles all vault reorganization tasks"
]
```
