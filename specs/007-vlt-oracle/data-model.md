# Data Model: Vlt Oracle

**Feature**: 007-vlt-oracle
**Date**: 2025-12-30
**Updated**: 2025-12-30 (v3 - Shared context, lazy LLM, delta indexing)

## Overview

The Vlt Oracle feature introduces entities for:
1. **Code indexing** (CodeChunk, BM25 index)
2. **Code graph** (CodeNode, CodeEdge)
3. **Code intelligence** (SymbolIndex via ctags)
4. **Repository map** (RepoMap, RepoMapEntry)
5. **Oracle orchestration** (OracleQuery, OracleResponse, OracleSession)
6. **Shared conversation context** (OracleConversation) - NEW
7. **Delta-based indexing** (IndexDeltaQueue) - NEW

---

## Entities

### 1. CodeChunk

A context-enriched semantic unit extracted from source code. This is the primary searchable unit.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, required | Unique identifier |
| project_id | String | FK→Project, required | Parent project |
| file_path | String | required, max 512 | Relative path from project root |
| file_hash | String | required, 32 chars | MD5 hash for change detection |
| chunk_type | Enum | required | "function", "class", "method", "module" |
| name | String | required, max 256 | Symbol name (e.g., "search_notes") |
| qualified_name | String | required, max 512 | Full path (e.g., "VaultService.search_notes") |
| language | String | required | "python", "typescript", "javascript", etc. |
| lineno | Integer | required | Start line number (1-indexed) |
| end_lineno | Integer | required | End line number |
| **imports** | Text | optional | Import statements used by this chunk |
| **class_context** | Text | optional | Enclosing class header (for methods) |
| **signature** | String | optional, max 1024 | Full function/method signature with types |
| **decorators** | Text | optional | Decorator lines (e.g., @property, @router.get) |
| **docstring** | Text | optional | Extracted documentation string |
| **body** | Text | required | Function/method body |
| embedding | Bytes | optional | Serialized numpy float32 array (qwen3-8b) |
| embedding_text | Text | optional | Text that was embedded (for debugging) |
| token_count | Integer | optional | Approximate token count of full chunk |
| created_at | DateTime | required, auto | Creation timestamp |
| updated_at | DateTime | required, auto | Last update timestamp |

**Indexes**:
- `ix_code_chunk_project_id` on (project_id)
- `ix_code_chunk_file_path` on (project_id, file_path)
- `ix_code_chunk_qualified_name` on (qualified_name)
- `ix_code_chunk_name` on (name) - for fast symbol lookup

**Full-Text Search (BM25)**:
```sql
CREATE VIRTUAL TABLE code_chunk_fts USING fts5(
    chunk_id UNINDEXED,
    name,
    qualified_name,
    signature,
    docstring,
    body,
    content='code_chunks',
    content_rowid='rowid',
    tokenize='porter unicode61'
);
```

---

### 2. CodeNode

A node in the code dependency graph representing a symbol.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | String | PK, required | Qualified name (e.g., "VaultService.search") |
| project_id | String | FK→Project, required | Parent project |
| file_path | String | required | File containing this symbol |
| node_type | Enum | required | "module", "class", "function", "method", "variable" |
| name | String | required | Short name |
| signature | String | optional | Type signature (if available) |
| lineno | Integer | optional | Definition line number |
| docstring | String | optional | Brief documentation |
| **centrality_score** | Float | optional | PageRank score for repo map prioritization |

**Indexes**:
- `ix_code_node_project_id` on (project_id)
- `ix_code_node_file_path` on (file_path)
- `ix_code_node_name` on (name)
- `ix_code_node_centrality` on (project_id, centrality_score DESC)

---

### 3. CodeEdge

A directed edge in the code dependency graph.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, required | Unique identifier |
| project_id | String | FK→Project, required | Parent project |
| source_id | String | FK→CodeNode, required | Source node (caller/importer) |
| target_id | String | FK→CodeNode, required | Target node (callee/imported) |
| edge_type | Enum | required | "calls", "imports", "inherits", "uses", "decorates" |
| lineno | Integer | optional | Line where relationship occurs |
| count | Integer | default 1 | How many times this edge appears |

**Indexes**:
- `ix_code_edge_source` on (source_id)
- `ix_code_edge_target` on (target_id)
- `ix_code_edge_type` on (project_id, edge_type)

**Edge Types**:
- `calls`: Function A calls function B
- `imports`: Module A imports from module B
- `inherits`: Class A extends class B
- `uses`: Function A references variable/constant B
- `decorates`: Decorator D applied to function F

---

### 4. SymbolDefinition (ctags)

A symbol definition from Universal Ctags index.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, required | Unique identifier |
| project_id | String | FK→Project, required | Parent project |
| name | String | required | Symbol name |
| file_path | String | required | File containing definition |
| lineno | Integer | required | Line number of definition |
| kind | String | required | ctags kind (function, class, method, etc.) |
| scope | String | optional | Enclosing scope (class name for methods) |
| signature | String | optional | Type signature if available |
| language | String | required | Programming language |

**Indexes**:
- `ix_symbol_def_name` on (project_id, name)
- `ix_symbol_def_file` on (file_path)

**Note**: This can also be stored as a ctags `tags` file and queried directly.

---

### 5. RepoMap

Generated repository structure map with centrality-based pruning.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, required | Unique identifier |
| project_id | String | FK→Project, required | Parent project |
| scope | String | optional | Subdirectory scope (null = entire repo) |
| map_text | Text | required | Generated Aider-style map text |
| token_count | Integer | required | Token count of map_text |
| max_tokens | Integer | required | Token budget used for generation |
| files_included | Integer | required | Number of files in map |
| symbols_included | Integer | required | Number of symbols in map |
| symbols_total | Integer | required | Total symbols before pruning |
| created_at | DateTime | required, auto | Generation timestamp |

**Indexes**:
- `ix_repo_map_project` on (project_id, scope)

---

### 6. RetrievalResult (Value Object)

A single result from any retrieval path.

| Field | Type | Description |
|-------|------|-------------|
| content | String | Retrieved text content |
| source_type | Enum | "vault", "code", "thread", "definition", "reference" |
| source_path | String | Path/ID to source (file:line, note path, thread ID) |
| retrieval_method | Enum | "vector", "bm25", "graph", "ctags", "scip" |
| score | Float | Relevance score (0.0-1.0, normalized) |
| token_count | Integer | Approximate tokens in content |
| metadata | Dict | Source-specific metadata |

**Metadata by Source Type**:
- **code**: `{file_path, chunk_type, qualified_name, lineno, language, signature}`
- **vault**: `{note_path, title, snippet, updated}`
- **thread**: `{thread_id, node_id, author, timestamp}`
- **definition**: `{file_path, lineno, kind, scope}`
- **reference**: `{file_path, lineno, usage_context}`

---

### 7. OracleQuery (Value Object)

Input to the oracle orchestrator.

| Field | Type | Description |
|-------|------|-------------|
| question | String | Natural language question |
| sources | List[String] | Filter: ["vault", "code", "threads"] or empty for all |
| explain | Boolean | Include retrieval traces in response |
| project_id | String | Project context |
| user_id | String | User making request |
| max_results | Integer | Max results per retrieval path (default: 20) |
| max_context_tokens | Integer | Token budget for synthesis (default: 16000) |
| include_repo_map | Boolean | Include repo map slice (default: true) |
| include_tests | Boolean | Boost test files in ranking (default: true) |

---

### 8. OracleResponse (Value Object)

Output from the oracle orchestrator.

| Field | Type | Description |
|-------|------|-------------|
| answer | String | Synthesized markdown answer |
| sources | List[RetrievalResult] | Cited sources with scores (top-k) |
| repo_map_slice | String | Included portion of repo map |
| traces | Optional[RetrievalTraces] | Debug info (if explain=true) |
| query_type | String | Detected query type (definition, reference, conceptual) |
| model | String | Model used for synthesis |
| tokens_used | Integer | Total tokens consumed |
| cost_cents | Float | Estimated cost |
| duration_ms | Integer | Processing time |

**RetrievalTraces**:
```python
RetrievalTraces:
  vector_results: List[RetrievalResult]
  bm25_results: List[RetrievalResult]
  graph_results: List[RetrievalResult]
  ctags_results: List[RetrievalResult]
  vault_results: List[RetrievalResult]
  thread_results: List[RetrievalResult]
  pre_rerank_scores: Dict[str, float]
  post_rerank_scores: Dict[str, float]
  context_budget_used: int
```

---

### 9. OracleSession

A logged oracle conversation for audit and memory.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, required | Unique identifier |
| project_id | String | FK→Project, required | Project context |
| thread_id | String | FK→Thread, required | Linked vlt thread |
| question | Text | required | User's question |
| answer | Text | required | Synthesized answer |
| query_type | String | required | Detected query type |
| sources_json | Text | required | JSON array of source citations |
| retrieval_traces_json | Text | optional | JSON traces (if --explain) |
| model_used | String | required | Synthesis model ID |
| tokens_used | Integer | required | Total tokens consumed |
| cost_cents | Float | required | Estimated cost in cents |
| duration_ms | Integer | required | Total processing time |
| created_at | DateTime | required, auto | Timestamp |

**Indexes**:
- `ix_oracle_session_project` on (project_id, created_at DESC)
- `ix_oracle_session_thread` on (thread_id)

---

### 10. OracleConversation (NEW - Shared Context)

A persistent conversation context shared across all MCP tool calls within a session.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, required | Unique identifier |
| project_id | String | FK→Project, required | Project context |
| user_id | String | required | User/agent making requests |
| session_start | DateTime | required, auto | When conversation started |
| last_activity | DateTime | required, auto | Last tool call timestamp |
| token_budget | Integer | required, default 16000 | Max tokens for context |
| tokens_used | Integer | required, default 0 | Current token usage |
| **compressed_summary** | Text | optional | Compressed older exchanges |
| **recent_exchanges_json** | Text | required, default '[]' | JSON array of recent tool calls/results |
| **mentioned_symbols** | Text | optional | JSON array of symbols discussed (for retrieval) |
| **mentioned_files** | Text | optional | JSON array of file paths discussed |
| status | Enum | required, default 'active' | "active", "compressed", "closed" |
| compression_count | Integer | default 0 | Number of times context was compressed |
| expires_at | DateTime | optional | Auto-cleanup timestamp |

**Indexes**:
- `ix_oracle_conv_project_user` on (project_id, user_id, status)
- `ix_oracle_conv_activity` on (last_activity DESC)
- `ix_oracle_conv_expires` on (expires_at) WHERE status = 'active'

**Exchange Entry Structure** (stored in recent_exchanges_json):
```json
{
  "id": "uuid",
  "timestamp": "2025-12-30T10:30:00Z",
  "tool_name": "find_definition",
  "input": {"symbol": "UserService"},
  "output_summary": "Found UserService at src/auth.py:45",
  "tokens": 150,
  "key_insights": ["UserService defined in auth.py", "class with 5 methods"]
}
```

**Compression Trigger**:
- When `tokens_used >= token_budget * 0.8` (80% threshold)
- Keep last N exchanges uncompressed (configurable, default: 5)
- Compress older exchanges to summary preserving: symbols, files, key insights

---

### 11. IndexDeltaQueue (NEW - Delta-Based Indexing)

A queue of pending file changes awaiting batch commit to the code index.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, required | Unique identifier |
| project_id | String | FK→Project, required | Project context |
| file_path | String | required, max 512 | Relative path from project root |
| change_type | Enum | required | "added", "modified", "deleted" |
| old_hash | String | optional, 32 chars | Previous content hash (for modified) |
| new_hash | String | optional, 32 chars | New content hash (null if deleted) |
| lines_changed | Integer | optional | Approximate lines changed (+ and -) |
| detected_at | DateTime | required, auto | When change was detected |
| queued_at | DateTime | required, auto | When added to queue |
| priority | Integer | default 0 | Higher = index sooner (e.g., query match) |
| status | Enum | required, default 'pending' | "pending", "indexing", "indexed", "failed" |
| error_message | Text | optional | If status = 'failed' |

**Indexes**:
- `ix_delta_queue_project_status` on (project_id, status)
- `ix_delta_queue_priority` on (project_id, priority DESC, queued_at ASC)
- `ix_delta_queue_file` on (project_id, file_path)

**Queue Status Entity** (computed, not stored):
```python
@dataclass
class DeltaQueueStatus:
    project_id: str
    queued_files: int              # Count of pending files
    total_lines_changed: int       # Sum of lines_changed
    oldest_change: datetime        # Earliest detected_at
    time_since_last_commit: timedelta
    threshold_file_count: int      # Configured (default: 5)
    threshold_line_count: int      # Configured (default: 1000)
    threshold_timeout_sec: int     # Configured (default: 300)
    should_commit: bool            # True if any threshold exceeded
    commit_reason: Optional[str]   # "file_count", "line_count", "timeout", or None
```

**Threshold Configuration** (in vlt.toml):
```toml
[coderag.delta]
file_threshold = 5       # Commit after N files changed
line_threshold = 1000    # Commit after N total lines changed
timeout_seconds = 300    # Commit after N seconds of inactivity
```

**Just-In-Time Indexing**:
When an oracle query matches a file in the delta queue:
1. Set that file's `priority = 100`
2. Index that file immediately (before query)
3. Return results including freshly indexed content

---

### 12. ThreadSummaryCache (NEW - Lazy LLM Evaluation)

Cached thread summaries with staleness tracking.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | UUID | PK, required | Unique identifier |
| thread_id | String | FK→Thread, required, unique | Thread being summarized |
| summary | Text | required | Generated summary text |
| last_node_id | String | required | ID of last node included in summary |
| node_count | Integer | required | Number of nodes summarized |
| model_used | String | required | Model that generated summary |
| tokens_used | Integer | required | Tokens consumed for generation |
| generated_at | DateTime | required, auto | When summary was generated |
| **is_stale** | Boolean | computed | True if thread has new nodes |

**Indexes**:
- `ix_thread_summary_thread` on (thread_id) UNIQUE

**Staleness Check** (computed at query time):
```sql
-- Check if summary is stale
SELECT
    tsc.id,
    tsc.summary,
    tsc.last_node_id,
    (SELECT MAX(id) FROM thread_nodes WHERE thread_id = tsc.thread_id) as current_last_node,
    tsc.last_node_id < (SELECT MAX(id) FROM thread_nodes WHERE thread_id = tsc.thread_id) as is_stale
FROM thread_summary_cache tsc
WHERE tsc.thread_id = ?
```

**Lazy Regeneration Flow**:
1. On `vlt thread push`: Only store raw content (no LLM call)
2. On `vlt thread read` or oracle query:
   - Check: is_stale?
   - If stale: regenerate summary (incremental if possible)
   - Update cache with new last_node_id

---

### 13. CodeRAGStatus (Value Object)

Health and statistics for the code index.

| Field | Type | Description |
|-------|------|-------------|
| project_id | String | Project identifier |
| indexed | Boolean | Whether any index exists |
| files_count | Integer | Total files indexed |
| chunks_count | Integer | Total code chunks |
| symbols_count | Integer | Total graph nodes |
| edges_count | Integer | Total graph edges |
| vector_index_size_bytes | Integer | Size of vector embeddings |
| bm25_index_size_bytes | Integer | Size of FTS5 index |
| repo_map_tokens | Integer | Token count of current repo map |
| languages | Dict[str, int] | Chunk count by language |
| last_indexed | DateTime | Last full index time |
| last_incremental | DateTime | Last incremental update |

---

## Entity Relationships

```
Project (existing in vlt-cli)
    │
    ├──< CodeChunk (1:N)
    │       ├── embedding (vector search)
    │       └── code_chunk_fts (BM25 search)
    │
    ├──< CodeNode (1:N)
    │       │
    │       ├──< CodeEdge.source_id (1:N)
    │       └──< CodeEdge.target_id (1:N)
    │
    ├──< SymbolDefinition (1:N)  # from ctags
    │
    ├──< RepoMap (1:N)  # scoped or full
    │
    ├──< IndexDeltaQueue (1:N)  # pending file changes [NEW]
    │
    ├──< OracleConversation (1:N)  # shared context sessions [NEW]
    │
    ├──< Thread (existing, 1:N)
    │       │
    │       ├──< OracleSession.thread_id (1:N)
    │       │
    │       └──1 ThreadSummaryCache (1:1)  # lazy-generated [NEW]
    │
    └──< OracleSession (1:N)
```

---

## Query Patterns

### Find Definition
```python
# 1. ctags lookup (fastest)
SELECT file_path, lineno, kind, scope
FROM symbol_definitions
WHERE project_id = ? AND name = ?

# 2. Graph node lookup (fallback)
SELECT id, file_path, lineno, signature
FROM code_nodes
WHERE project_id = ? AND name = ?
```

### Find References
```python
# Graph edges to find callers
SELECT cn.file_path, cn.lineno, ce.lineno as call_line
FROM code_edges ce
JOIN code_nodes cn ON ce.source_id = cn.id
WHERE ce.target_id = ? AND ce.edge_type = 'calls'
```

### BM25 Search
```python
# Full-text search on code chunks
SELECT chunk_id, bm25(code_chunk_fts) as score
FROM code_chunk_fts
WHERE code_chunk_fts MATCH ?
ORDER BY score
LIMIT 20
```

### Vector Search
```python
# Retrieve candidates, compute similarity in Python
SELECT id, embedding
FROM code_chunks
WHERE project_id = ? AND embedding IS NOT NULL

# Then: numpy cosine similarity with query embedding
```

### Get High-Centrality Nodes (for repo map)
```python
SELECT id, name, signature, centrality_score
FROM code_nodes
WHERE project_id = ?
ORDER BY centrality_score DESC
LIMIT 100
```

---

## Migration Notes

### New Tables (vlt-cli database)

```sql
-- CodeChunk table (primary search target)
CREATE TABLE code_chunks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    chunk_type TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    language TEXT NOT NULL,
    lineno INTEGER NOT NULL,
    end_lineno INTEGER NOT NULL,
    imports TEXT,
    class_context TEXT,
    signature TEXT,
    decorators TEXT,
    docstring TEXT,
    body TEXT NOT NULL,
    embedding BLOB,
    embedding_text TEXT,
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- BM25 FTS5 virtual table
CREATE VIRTUAL TABLE code_chunk_fts USING fts5(
    chunk_id UNINDEXED,
    name,
    qualified_name,
    signature,
    docstring,
    body,
    content='code_chunks',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- CodeNode table (graph nodes)
CREATE TABLE code_nodes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    file_path TEXT NOT NULL,
    node_type TEXT NOT NULL,
    name TEXT NOT NULL,
    signature TEXT,
    lineno INTEGER,
    docstring TEXT,
    centrality_score REAL
);

-- CodeEdge table (graph edges)
CREATE TABLE code_edges (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    source_id TEXT NOT NULL REFERENCES code_nodes(id),
    target_id TEXT NOT NULL REFERENCES code_nodes(id),
    edge_type TEXT NOT NULL,
    lineno INTEGER,
    count INTEGER DEFAULT 1
);

-- SymbolDefinition table (ctags)
CREATE TABLE symbol_definitions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    lineno INTEGER NOT NULL,
    kind TEXT NOT NULL,
    scope TEXT,
    signature TEXT,
    language TEXT NOT NULL
);

-- RepoMap table
CREATE TABLE repo_maps (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    scope TEXT,
    map_text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    max_tokens INTEGER NOT NULL,
    files_included INTEGER NOT NULL,
    symbols_included INTEGER NOT NULL,
    symbols_total INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- OracleSession table
CREATE TABLE oracle_sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    thread_id TEXT NOT NULL REFERENCES threads(id),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    query_type TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    retrieval_traces_json TEXT,
    model_used TEXT NOT NULL,
    tokens_used INTEGER NOT NULL,
    cost_cents REAL NOT NULL,
    duration_ms INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX ix_code_chunk_project_id ON code_chunks(project_id);
CREATE INDEX ix_code_chunk_file_path ON code_chunks(project_id, file_path);
CREATE INDEX ix_code_chunk_qualified_name ON code_chunks(qualified_name);
CREATE INDEX ix_code_chunk_name ON code_chunks(name);

CREATE INDEX ix_code_node_project_id ON code_nodes(project_id);
CREATE INDEX ix_code_node_file_path ON code_nodes(file_path);
CREATE INDEX ix_code_node_name ON code_nodes(name);
CREATE INDEX ix_code_node_centrality ON code_nodes(project_id, centrality_score DESC);

CREATE INDEX ix_code_edge_source ON code_edges(source_id);
CREATE INDEX ix_code_edge_target ON code_edges(target_id);
CREATE INDEX ix_code_edge_type ON code_edges(project_id, edge_type);

CREATE INDEX ix_symbol_def_name ON symbol_definitions(project_id, name);
CREATE INDEX ix_symbol_def_file ON symbol_definitions(file_path);

CREATE INDEX ix_repo_map_project ON repo_maps(project_id, scope);

CREATE INDEX ix_oracle_session_project ON oracle_sessions(project_id, created_at DESC);
CREATE INDEX ix_oracle_session_thread ON oracle_sessions(thread_id);

-- OracleConversation table (shared context) [NEW v3]
CREATE TABLE oracle_conversations (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    user_id TEXT NOT NULL,
    session_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    token_budget INTEGER NOT NULL DEFAULT 16000,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    compressed_summary TEXT,
    recent_exchanges_json TEXT NOT NULL DEFAULT '[]',
    mentioned_symbols TEXT,
    mentioned_files TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    compression_count INTEGER DEFAULT 0,
    expires_at TIMESTAMP
);

CREATE INDEX ix_oracle_conv_project_user ON oracle_conversations(project_id, user_id, status);
CREATE INDEX ix_oracle_conv_activity ON oracle_conversations(last_activity DESC);
CREATE INDEX ix_oracle_conv_expires ON oracle_conversations(expires_at) WHERE status = 'active';

-- IndexDeltaQueue table (delta-based indexing) [NEW v3]
CREATE TABLE index_delta_queue (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    file_path TEXT NOT NULL,
    change_type TEXT NOT NULL,  -- 'added', 'modified', 'deleted'
    old_hash TEXT,
    new_hash TEXT,
    lines_changed INTEGER,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    priority INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'indexing', 'indexed', 'failed'
    error_message TEXT
);

CREATE INDEX ix_delta_queue_project_status ON index_delta_queue(project_id, status);
CREATE INDEX ix_delta_queue_priority ON index_delta_queue(project_id, priority DESC, queued_at ASC);
CREATE INDEX ix_delta_queue_file ON index_delta_queue(project_id, file_path);

-- ThreadSummaryCache table (lazy LLM evaluation) [NEW v3]
CREATE TABLE thread_summary_cache (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL UNIQUE REFERENCES threads(id),
    summary TEXT NOT NULL,
    last_node_id TEXT NOT NULL,
    node_count INTEGER NOT NULL,
    model_used TEXT NOT NULL,
    tokens_used INTEGER NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX ix_thread_summary_thread ON thread_summary_cache(thread_id);
```

---

## Validation Summary

| Entity | Required Fields | Enums | Foreign Keys |
|--------|----------------|-------|--------------|
| CodeChunk | 13 | chunk_type, language | project_id |
| CodeNode | 5 | node_type | project_id |
| CodeEdge | 5 | edge_type | project_id, source_id, target_id |
| SymbolDefinition | 6 | - | project_id |
| RepoMap | 8 | - | project_id |
| OracleSession | 12 | - | project_id, thread_id |
| OracleConversation | 8 | status | project_id |
| IndexDeltaQueue | 7 | change_type, status | project_id |
| ThreadSummaryCache | 6 | - | thread_id |
