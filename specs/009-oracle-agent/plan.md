# Implementation Plan: Oracle Agent Architecture

**Branch**: `009-oracle-agent` | **Date**: 2025-12-31 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/009-oracle-agent/spec.md`

## Summary

Transform the Oracle from a subprocess-based CLI wrapper into a proper AI agent running in the backend. The agent uses OpenRouter function calling for tool execution, delegates vault organization to a Librarian subagent, and persists conversation context across sessions. Migrate the existing OracleOrchestrator 5-stage pipeline from vlt-cli to the backend, extending it with proper tool calling and context management.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI, Pydantic, httpx, Jinja2, FastMCP (existing)
**Storage**: SQLite (data/index.db for backend, ~/.vlt/vault.db for CLI)
**Testing**: pytest (backend unit/integration), manual verification (UI)
**Target Platform**: Linux server (self-hosted), Hugging Face Spaces
**Project Type**: Web application (monorepo with backend + frontend + vlt-cli)
**Performance Goals**: <10s for typical queries, <5s for tool-less responses
**Constraints**: 16k token context budget, streaming responses, graceful degradation
**Scale/Scope**: 100 concurrent users, multi-project support

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Check

### I. Brownfield Integration ✅ PASS
- Extends existing `backend/src/services/` with new `oracle_agent.py`
- Reuses existing FastMCP tool patterns from `mcp/server.py`
- Follows existing API route patterns in `api/routes/`
- Matches existing Pydantic model patterns

### II. Test-Backed Development ✅ PASS
- New services will have pytest unit tests
- API endpoints will have integration tests
- Frontend relies on existing manual/E2E verification

### III. Incremental Delivery ✅ PASS
- Phase 1: Core agent loop with existing tools
- Phase 2: New tools (thread_push, web_search)
- Phase 3: Librarian subagent
- Phase 4: Context persistence
- Old oracle_bridge.py kept as fallback initially

### IV. Specification-Driven ✅ PASS
- All work traced to spec.md requirements
- FR-001 through FR-027 mapped to implementation tasks

---

### Post-Design Check (After Phase 1)

### I. Brownfield Integration ✅ PASS (Verified)
- `OracleAgent` follows existing service patterns in `backend/src/services/`
- `ToolExecutor` reuses existing `VaultService`, `IndexerService`, `ThreadService`
- `PromptLoader` uses Jinja2 which is standard Python
- New table `oracle_contexts` follows existing SQLite schema patterns
- API contracts follow existing OpenAPI patterns

### II. Test-Backed Development ✅ PASS (Planned)
- Unit tests specified: `test_oracle_agent.py`, `test_prompt_loader.py`, `test_tool_executor.py`
- Integration tests specified: `test_oracle_api.py`
- Test patterns match existing `backend/tests/` structure

### III. Incremental Delivery ✅ PASS (Verified)
- Quickstart shows minimal viable implementation in 30 minutes
- Each phase builds on previous without breaking existing functionality
- Fallback to inline prompts if `prompts/` directory not created yet
- `oracle_bridge.py` preserved as fallback during transition

### IV. Specification-Driven ✅ PASS (Verified)
- Data model entities map directly to spec.md Key Entities
- API contracts implement all FR-001 through FR-027
- Tool definitions cover all required capabilities

## Project Structure

### Documentation (this feature)

```text
specs/009-oracle-agent/
├── plan.md              # This file
├── research.md          # Phase 0 output (COMPLETE)
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── oracle-api.yaml  # OpenAPI for Oracle endpoints
│   └── tools.json       # Tool schemas for OpenRouter
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── models/
│   │   ├── oracle.py              # Existing - extend
│   │   └── oracle_context.py      # NEW - context persistence
│   ├── services/
│   │   ├── oracle_agent.py        # NEW - main agent class
│   │   ├── librarian_agent.py     # NEW - subagent for vault
│   │   ├── prompt_loader.py       # NEW - Jinja2 template loader
│   │   ├── tool_executor.py       # NEW - tool dispatch
│   │   ├── oracle_bridge.py       # Existing - deprecate
│   │   ├── thread_service.py      # Existing - extend
│   │   └── librarian_service.py   # Existing - keep for summarization
│   ├── api/routes/
│   │   ├── oracle.py              # Existing - update
│   │   └── threads.py             # Existing - extend
│   └── mcp/
│       └── server.py              # Existing - add new tools
├── prompts/                       # NEW - external prompts
│   ├── oracle/
│   │   ├── system.md
│   │   ├── synthesis.md
│   │   ├── compression.md
│   │   └── no_context.md
│   ├── librarian/
│   │   ├── system.md
│   │   └── organize.md
│   └── tools/
│       └── {tool_name}.md
└── tests/
    ├── unit/
    │   ├── test_oracle_agent.py   # NEW
    │   ├── test_prompt_loader.py  # NEW
    │   └── test_tool_executor.py  # NEW
    └── integration/
        └── test_oracle_api.py     # NEW

packages/vlt-cli/
├── src/vlt/
│   ├── commands/
│   │   └── oracle.py              # Existing - convert to thin client
│   └── core/
│       ├── oracle.py              # Existing - reference for migration
│       └── conversation.py        # Existing - reference for context patterns
```

**Structure Decision**: Web application structure (Option 2). Primary changes in `backend/src/services/` and new `backend/prompts/` directory. Frontend changes minimal (already has AI Chat). vlt-cli oracle command becomes thin HTTP client.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Subagent pattern | Specialized prompts for vault organization | Single agent tool list becomes unwieldy (20+ tools) |
| External prompts (Jinja2) | Constitution: "No Magic", hot-reloadable | Hardcoded strings violate explicit > implicit |
| Context persistence (new table) | Multi-day sessions, model switches | In-memory loses context on restart |

## Key Decisions from Research

1. **Migrate OracleOrchestrator** from vlt-cli to backend (not rewrite)
2. **Extend FastMCP** tool patterns (not LangChain/custom framework)
3. **OpenRouter function calling** for tool execution
4. **SQLite oracle_contexts table** for session persistence
5. **Librarian as first subagent** with scoped tools
6. **Jinja2 prompts** in `backend/prompts/` directory
7. **SSE streaming** (existing pattern, keep)

## Implementation Phases

### Phase 1: Core Agent (P1 Stories)
- Create OracleAgent class with agent loop
- Implement tool executor with existing tools
- Update API routes to use OracleAgent
- Add basic context tracking (in-memory first)

### Phase 2: Memory & Tools (P2 Stories)
- Add thread_push, thread_read, thread_seek tools
- Implement oracle_contexts table
- Add context compression
- Convert vlt-cli oracle to thin client

### Phase 3: Subagent & Web (P2-P3 Stories)
- Implement LibrarianAgent
- Add delegate_librarian tool
- Add web_search, web_fetch tools
- Add vault_move, vault_create_index for Librarian

### Phase 4: Polish (P3 Stories)
- Model change handling
- Prompt hot-reload
- Tool visibility in UI
- Context usage indicators
