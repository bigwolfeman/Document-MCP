# Research: Oracle Agent Architecture

**Feature**: 009-oracle-agent
**Date**: 2025-12-31

## Executive Summary

Research confirms the Oracle Agent architecture is feasible with significant code reuse. The existing OracleOrchestrator in vlt-cli provides a solid 5-stage pipeline that should be migrated to the backend. Key decisions focus on eliminating subprocess calls, adding proper tool calling via OpenRouter, and implementing persistent context management.

---

## Research Area 1: Existing Oracle Implementation

### Decision: Migrate OracleOrchestrator to Backend

**Rationale**: The vlt-cli OracleOrchestrator already implements a complete 5-stage pipeline (Query Analysis → Multi-source Retrieval → Hybrid Ranking → Context Assembly → LLM Synthesis). Rather than building from scratch, migrate this architecture to the backend.

**Key Patterns to Preserve**:
- Query Analysis (pattern-based, no LLM needed) - 5-20ms
- Pluggable Retriever Protocol with universal RetrievalResult type
- Hybrid retrieval with parallel execution
- Token-budgeted context assembly by query type
- Query-type specific prompts

**What to Replace**:
| Component | Current | New |
|-----------|---------|-----|
| Oracle Bridge | Subprocess calls to vlt CLI | Direct OracleAgent class |
| Conversation History | In-memory (max 50 msg) | SQLite persistence |
| LLM Synthesis | Buffered httpx call | Streaming with tool calling |

**Alternatives Considered**:
- Keep subprocess approach: Rejected - adds 500ms+ overhead, loses context between calls
- Build entirely new pipeline: Rejected - existing patterns are well-designed

---

## Research Area 2: MCP Tools & Vault Operations

### Decision: Extend Existing FastMCP Tool Definitions

**Rationale**: 11 MCP tools already exist in the backend using FastMCP decorators. The pattern is clean and extensible.

**Existing Tools (Reusable)**:
- `list_notes`, `read_note`, `write_note`, `delete_note`, `search_notes` - Core vault operations
- `get_backlinks`, `get_tags` - Vault metadata
- `ask_oracle`, `search_code`, `find_definition`, `find_references`, `get_repo_map` - Oracle/CodeRAG

**New Tools Needed**:
| Tool | Purpose | Scope |
|------|---------|-------|
| `thread_push` | Record thought to memory | Oracle |
| `thread_read` | Get thread with summary | Oracle |
| `thread_seek` | Semantic search threads | Oracle |
| `thread_list` | List project threads | Oracle |
| `web_search` | Search the web | Oracle |
| `web_fetch` | Fetch and process URL | Oracle |
| `delegate_librarian` | Invoke Librarian subagent | Oracle only |
| `vault_move` | Move/rename notes | Librarian only |
| `vault_create_index` | Generate folder index | Librarian only |

**Tool Definition Pattern** (from FastMCP):
```python
@mcp.tool(name="tool_name", description="What it does")
async def tool_function(
    param: str = Field(..., description="Required param"),
    optional: Optional[str] = Field(default=None, description="Optional")
) -> Dict[str, Any]:
    user_id = _current_user_id()  # Auth context
    # Implementation
    return result
```

**Alternatives Considered**:
- LangChain tools: Rejected - adds dependency, FastMCP already works
- Custom tool framework: Rejected - FastMCP pattern is sufficient

---

## Research Area 3: Thread Sync Infrastructure

### Decision: Use Existing Thread Service, Add Thread API Endpoints

**Rationale**: Thread sync infrastructure exists but backend lacks full thread CRUD API. The ThreadService provides all needed operations.

**Existing Infrastructure**:
- `ThreadService` with CRUD operations
- FTS5 search index on thread entries
- Sync status tracking
- Summarization via LibrarianService

**Missing Backend APIs**:
| Endpoint | Status | Action |
|----------|--------|--------|
| `POST /api/threads/sync` | ✅ Exists | Keep |
| `GET /api/threads` | ✅ Exists | Keep |
| `GET /api/threads/{id}` | ✅ Exists | Keep |
| `POST /api/threads/{id}/summarize` | ✅ Exists | Keep |
| `POST /api/threads` | ❌ Missing | Add (Oracle creates threads) |
| `POST /api/threads/{id}/entries` | ❌ Missing | Add (Oracle pushes entries) |
| `GET /api/threads/seek` | ❌ Missing | Add (semantic search) |

**Thread Storage Schema** (existing):
```sql
threads (user_id, thread_id PK, project_id, name, status, created_at, updated_at)
thread_entries (user_id, entry_id PK, thread_id, sequence_id, content, author, timestamp)
thread_sync_status (user_id, thread_id PK, last_synced_sequence, last_sync_at, sync_error)
thread_entries_fts (content FTS5)
```

**Alternatives Considered**:
- Separate memory service: Rejected - threads already serve as memory
- External vector DB: Rejected - SQLite + local embeddings sufficient for scale

---

## Research Area 4: OpenRouter Tool Calling

### Decision: Use OpenRouter Function Calling API

**Rationale**: OpenRouter supports OpenAI-compatible function calling with parallel tool execution.

**API Format**:
```python
response = await client.post(
    "https://openrouter.ai/api/v1/chat/completions",
    json={
        "model": "anthropic/claude-sonnet-4",
        "messages": messages,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search_code",
                    "description": "Search codebase for relevant code",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                        "required": ["query"]
                    }
                }
            }
        ],
        "tool_choice": "auto",
        "parallel_tool_calls": True
    }
)
```

**Response Handling**:
```python
if response.choices[0].finish_reason == "tool_calls":
    for tool_call in response.choices[0].message.tool_calls:
        result = await execute_tool(tool_call.function.name, tool_call.function.arguments)
        messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
    # Continue agent loop
```

**Key Practices**:
- Set iteration limits for agentic loops (max 10-15 turns)
- Include tools in every request for schema validation
- Use descriptive names and comprehensive parameter descriptions

**Alternatives Considered**:
- Google Gemini function calling: Supported as fallback
- LlamaIndex agent: Adds complexity, OpenRouter direct is simpler

---

## Research Area 5: Context Window Management

### Decision: Implement OracleContext Table with Compression

**Rationale**: Existing ConversationManager in vlt-cli has good patterns (16k token budget, 80% compression threshold, keep last 5 exchanges). Port to backend with SQLite persistence.

**Context Schema** (new table):
```sql
CREATE TABLE oracle_contexts (
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
    status TEXT DEFAULT 'active',
    compression_count INTEGER DEFAULT 0,
    UNIQUE(user_id, project_id)
)
```

**Compression Strategy** (from existing code):
1. Trigger at 80% token budget
2. Keep last 5 exchanges uncompressed
3. Preserve key decisions always
4. Use cheap model (deepseek-chat) for compression
5. Target 50-70% token reduction

**Model Change Handling**:
- Track `last_model` in context
- On model switch, re-summarize for new tokenization
- Transparent to user

**Alternatives Considered**:
- File-based context: Rejected - harder to query and cleanup
- In-memory only: Rejected - loses context on restart

---

## Research Area 6: Subagent Architecture

### Decision: Librarian as First-Class Subagent

**Rationale**: The Oracle should delegate vault organization tasks to a specialized Librarian agent with scoped tools and its own system prompt.

**Delegation Pattern**:
```python
# Oracle invokes via tool
{"tool_calls": [{"function": {"name": "delegate_librarian", "arguments": {"task": "organize notes in /architecture"}}}]}

# Librarian runs with scoped tools
LIBRARIAN_TOOLS = ["vault_read", "vault_write", "vault_list", "vault_move", "vault_create_index"]

# Librarian returns result
{"files_modified": ["architecture/index.md"], "summary": "Created index with 5 linked notes"}
```

**Librarian Responsibilities**:
- Moving/renaming notes (updating wikilinks)
- Creating folder index pages
- Providing vault overviews
- Cleaning up duplicate notes

**Communication**:
- Oracle passes task description + relevant files
- Librarian runs own agent loop (max 10 turns)
- Returns structured result (success, files modified, summary)

**Alternatives Considered**:
- Single agent with all tools: Rejected - tool list becomes unwieldy
- Multiple specialized subagents: Future option, start with Librarian only

---

## Research Area 7: Prompts Architecture

### Decision: Externalize Prompts to `prompts/` Directory

**Rationale**: Constitution requires "No Magic" - explicit is better than implicit. External prompts enable hot-reload and non-dev editing.

**Directory Structure**:
```
backend/prompts/
├── oracle/
│   ├── system.md           # Main Oracle system prompt
│   ├── synthesis.md        # Answer generation
│   ├── compression.md      # Context compression
│   └── no_context.md       # "I found nothing" response
├── librarian/
│   ├── system.md           # Librarian subagent prompt
│   ├── organize.md         # Organization task prompt
│   └── index_generation.md # Create folder indexes
├── tools/
│   └── {tool_name}.md      # Detailed tool descriptions
└── templates/
    ├── research_note.md    # Template for saved research
    └── decision_record.md  # ADR-style decisions
```

**Template Engine**: Jinja2 (already used in Python ecosystem)

```python
class PromptLoader:
    def load(self, path: str, context: dict = None) -> str:
        template = self.env.get_template(path)
        return template.render(context or {})
```

**Alternatives Considered**:
- Hardcoded strings: Rejected - Constitution violation ("No Magic")
- Database-stored prompts: Overkill - files are simpler

---

## Decisions Summary

| Area | Decision | Key Rationale |
|------|----------|---------------|
| Oracle Pipeline | Migrate OracleOrchestrator to backend | Solid 5-stage architecture exists |
| Tool Framework | Extend FastMCP | 11 tools exist, pattern is clean |
| Thread Memory | Use existing ThreadService | Full CRUD exists, add 3 endpoints |
| LLM Integration | OpenRouter function calling | Parallel tools, OpenAI-compatible |
| Context Storage | New oracle_contexts table | Persists across sessions |
| Subagents | Librarian with scoped tools | Specialized vault organization |
| Prompts | External Jinja2 templates | Explicit, hot-reloadable |

---

## Open Items for Implementation

1. **Web Search Integration**: Use OpenRouter's web plugin or external API (SerpAPI/Brave)?
   - **Recommendation**: Start with OpenRouter web plugin, fallback to Brave Search API

2. **PDF Handling**: Which library for PDF text extraction?
   - **Recommendation**: pypdf (lightweight, sufficient for text)

3. **File Operations Sandboxing**: How to restrict file tools to project?
   - **Recommendation**: Validate all paths against project_root from vlt.toml

4. **Streaming Format**: SSE or WebSocket?
   - **Recommendation**: Keep SSE (existing pattern, simpler)
