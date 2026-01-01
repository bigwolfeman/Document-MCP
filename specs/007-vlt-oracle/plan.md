# Implementation Plan: Vlt Oracle

**Branch**: `007-vlt-oracle` | **Date**: 2025-12-30 | **Spec**: [spec.md](./spec.md)
**Updated**: 2025-12-30 (v3 - Shared context, lazy LLM, delta indexing)
**Input**: Feature specification from `/specs/007-vlt-oracle/spec.md`

## Summary

Implement a production-grade multi-source intelligent context retrieval system that integrates:
- **vlt-cli threads** for development history and memory
- **Document-MCP markdown vault** for documentation
- **CodeRAG** with hybrid retrieval (vector + BM25 + graph + code intelligence)

The system provides AI coding agents with comprehensive codebase understanding through:
- **Hybrid retrieval pipeline**: Vector search (semantic) + BM25 (exact match) + Graph traversal (structural) + Code intelligence (definitions/references)
- **Repository map**: Aider-style condensed codebase overview for LLM navigation
- **Reranking stage**: Cross-encoder or LLM-based result scoring
- **MCP tools**: Full toolset for coding agents (ask_oracle, search_code, find_definition, find_references, get_repo_map)
- **Shared conversation context**: All tools share one context window with compression
- **Lazy LLM evaluation**: Summaries/embeddings generated on-read, not on-write
- **Delta-based indexing**: Batch changes, commit when threshold reached

**Key Technical Decisions**:
- Use **LlamaIndex CodeSplitter** (Sweep's chunker) for semantic chunking
- Use **tree-sitter** for language-agnostic parsing (not Python `ast`)
- Use **qwen/qwen3-embedding-8b** for code-aware embeddings
- Use **ctags** (Universal Ctags) for symbol definition index
- Use **SQLite FTS5** for BM25 keyword search
- Build **Aider-style repo map** with graph centrality ranking
- **Rerank** results before synthesis
- **Lazy LLM calls**: No API calls on write operations
- **Shared context window**: Single conversation across all MCP tools with auto-compression
- **Delta-based commits**: Queue changes, batch commit when threshold reached

## Technical Context

**Language/Version**: Python 3.11+ (vlt-cli, CodeRAG), TypeScript 5.x (frontend)
**Primary Dependencies**:
- vlt-cli: Typer, SQLAlchemy, httpx, numpy
- CodeRAG: LlamaIndex, tree-sitter, tree-sitter-languages
- Document-MCP: FastAPI, React 19, Vite 7
- New: Universal Ctags (external binary), cross-encoder models
**Storage**: SQLite (vlt-cli ~/.vlt/vault.db) + SQLite FTS5 (BM25) + ctags files
**Testing**: pytest (backend), manual E2E (frontend)
**Target Platform**: Linux/macOS CLI, Web browser
**Project Type**: Multi-repo (vlt-cli extension + Document-MCP integration)
**Performance Goals**:
- <15s oracle response
- <5min coderag init for 10K files
- <30s repo map generation
- <$0.03/query
**Constraints**:
- <30s per retrieval path
- Graceful degradation when sources unavailable
- Context window budget for synthesis (~16K tokens)
**Scale/Scope**: 1-10K code files, 1-5K vault notes, 1-1K vlt threads

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Brownfield Integration** | PASS | Extends vlt-cli with new modules. Uses LlamaIndex (already in Document-MCP). Reuses SQLite FTS5 pattern from vault. |
| **II. Test-Backed Development** | PASS | pytest for chunker, retrievers, reranker, orchestrator. Integration tests for full pipeline. |
| **III. Incremental Delivery** | PASS | Phase 1: Indexing. Phase 2: Retrieval. Phase 3: Repo map. Phase 4: Reranking. Phase 5: MCP tools. Phase 6: Web UI. |
| **IV. Specification-Driven** | PASS | 40 functional requirements traced from spec. Data model derived from Key Entities. |

**Technology Standards**:
- Backend: Python 3.11+, Pydantic, SQLite ✓
- Frontend: React 19, TypeScript, Tailwind CSS, Shadcn/UI ✓
- No Magic: Explicit retriever interface, configurable pipeline stages ✓
- Single Source of Truth: All indexes derived from source files ✓
- Error Handling: Graceful degradation per retrieval path ✓

## Architecture

### High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              INDEXING PIPELINE                               │
│                           (vlt coderag init)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
     Source Files (*.py, *.ts, etc.) │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            TREE-SITTER PARSE                                 │
│                    Language-agnostic AST extraction                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
        ┌───────────────┐  ┌─────────────────┐  ┌──────────────┐
        │ LLAMAINDEX    │  │ GRAPH BUILDER   │  │ CTAGS        │
        │ CodeSplitter  │  │                 │  │              │
        │               │  │ - Import edges  │  │ Symbol →     │
        │ Context-      │  │ - Call edges    │  │ file:line    │
        │ enriched      │  │ - Inherit edges │  │ definitions  │
        │ chunks        │  │                 │  │              │
        └───────┬───────┘  └────────┬────────┘  └──────┬───────┘
                │                   │                  │
                ▼                   ▼                  ▼
        ┌───────────────┐  ┌─────────────────┐  ┌──────────────┐
        │ EMBED         │  │ GRAPH DB        │  │ CTAGS INDEX  │
        │ qwen3-8b      │  │ (SQLite)        │  │ (tags file)  │
        │               │  │                 │  │              │
        │ + BM25 INDEX  │  │ CodeNode        │  │              │
        │ (FTS5)        │  │ CodeEdge        │  │              │
        └───────────────┘  └─────────────────┘  └──────────────┘
                │                   │                  │
                └───────────────────┼──────────────────┘
                                    │
                                    ▼
                        ┌───────────────────┐
                        │ REPO MAP          │
                        │ GENERATOR         │
                        │                   │
                        │ Graph centrality  │
                        │ → pruned outline  │
                        └───────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              QUERY PIPELINE                                  │
│                           (vlt oracle "...")                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                              User Question
                                     │
                                     ▼
                        ┌───────────────────┐
                        │ QUERY ANALYZER    │
                        │                   │
                        │ Detect query type:│
                        │ - definition?     │
                        │ - references?     │
                        │ - conceptual?     │
                        │ - behavioral?     │
                        └─────────┬─────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ IF DEFINITION   │    │ IF REFERENCES   │    │ OTHERWISE       │
│                 │    │                 │    │                 │
│ → ctags lookup  │    │ → graph query   │    │ → hybrid search │
│ → exact file:ln │    │ → call sites    │    │                 │
└────────┬────────┘    └────────┬────────┘    └────────┬────────┘
         │                      │                      │
         │                      │         ┌────────────┴────────────┐
         │                      │         │                         │
         │                      │         ▼                         ▼
         │                      │  ┌─────────────┐          ┌─────────────┐
         │                      │  │ VECTOR      │          │ BM25        │
         │                      │  │ SEARCH      │          │ SEARCH      │
         │                      │  │             │          │             │
         │                      │  │ Semantic    │          │ Exact match │
         │                      │  │ similarity  │          │ keywords    │
         │                      │  └──────┬──────┘          └──────┬──────┘
         │                      │         │                        │
         │                      │         └───────────┬────────────┘
         │                      │                     │
         │                      │                     ▼
         │                      │           ┌─────────────────┐
         │                      │           │ GRAPH EXPANSION │
         │                      │           │                 │
         │                      │           │ For each result:│
         │                      │           │ - get callers   │
         │                      │           │ - get callees   │
         │                      │           │ - get imports   │
         │                      │           └────────┬────────┘
         │                      │                    │
         └──────────────────────┴────────────────────┘
                                     │
                                     ▼
                        ┌───────────────────┐
                        │ MERGE & DEDUPE    │
                        │                   │
                        │ Combine results   │
                        │ from all paths    │
                        │ Tag with source   │
                        └─────────┬─────────┘
                                  │
                                  ▼
                        ┌───────────────────┐
                        │ RERANKER          │
                        │                   │
                        │ Cross-encoder or  │
                        │ LLM-based scoring │
                        │ → top-k selection │
                        └─────────┬─────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                    ▼                           ▼
        ┌───────────────────┐      ┌───────────────────┐
        │ VAULT SEARCH      │      │ THREAD SEARCH     │
        │ (Document-MCP)    │      │ (vlt seek)        │
        │                   │      │                   │
        │ Markdown notes    │      │ Dev history       │
        └─────────┬─────────┘      └─────────┬─────────┘
                  │                          │
                  └────────────┬─────────────┘
                               │
                               ▼
                  ┌───────────────────────┐
                  │ CONTEXT ASSEMBLY      │
                  │                       │
                  │ - Top-k code chunks   │
                  │ - Relevant vault notes│
                  │ - Thread context      │
                  │ - Repo map slice      │
                  │ - Test files (if rel) │
                  └───────────┬───────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │ SYNTHESIS             │
                  │                       │
                  │ Claude/GPT-4 with     │
                  │ assembled context     │
                  │ → answer + citations  │
                  └───────────────────────┘
```

### Repo Map Generation (Aider Pattern)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           REPO MAP GENERATOR                                 │
└─────────────────────────────────────────────────────────────────────────────┘

1. Parse all files → extract symbols (classes, functions, methods)
2. Build reference graph (who calls/imports what)
3. Calculate PageRank/centrality scores for each symbol
4. Generate map with budget:
   - Always include: file names, class names, top functions
   - Include signatures for high-centrality symbols
   - Prune low-centrality symbols to fit token budget

OUTPUT FORMAT:
```
src/
├── api/
│   └── routes/
│       ├── auth.py
│       │   ├── class AuthRouter
│       │   │   ├── login(username: str, password: str) → Token
│       │   │   ├── logout(token: str) → None
│       │   │   └── refresh(token: str) → Token
│       │   └── verify_jwt(token: str) → Payload
│       └── notes.py
│           ├── class NotesRouter
│           │   ├── list_notes(user_id: str) → List[Note]
│           │   ├── read_note(path: str) → Note
│           │   └── write_note(path: str, content: str) → Note
│           └── validate_path(path: str) → bool
├── services/
│   └── vault.py
│       ├── class VaultService
│       │   ├── read_note(...)
│       │   ├── write_note(...)
│       │   └── search_notes(...)
│       └── sanitize_path(...)
```

### Context-Enriched Chunks (Critical for Quality)

Each chunk includes:
```python
CodeChunk:
  file_path: "src/services/vault.py"
  chunk_type: "method"
  qualified_name: "VaultService.search_notes"

  # CONTEXT (what makes it self-contained)
  imports: |
    from pathlib import Path
    from typing import List, Optional
    import sqlite3

  class_context: |
    class VaultService:
        """Service for vault filesystem operations."""
        def __init__(self, base_path: Path):
            self.base_path = base_path

  signature: "def search_notes(self, user_id: str, query: str, limit: int = 50) -> List[Dict]:"

  decorators: []

  docstring: "Full-text search across all notes in user's vault."

  body: |
    results = []
    conn = sqlite3.connect(self.db_path)
    # ... actual implementation
    return results

  # METADATA
  lineno: 145
  end_lineno: 178
  language: "python"

  # VECTOR
  embedding: bytes  # qwen3-8b embedding of full chunk text
```

### Shared Conversation Context (Cross-Tool Memory)

All MCP tools share a single conversation context that persists across tool calls:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ORACLE CONVERSATION CONTEXT                           │
│                    (Shared across all tool calls)                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ CONVERSATION HISTORY                                                         │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ [Compressed Summary]                                                     │ │
│ │ "Earlier: User asked about auth, found UserService in auth.py:45,       │ │
│ │  then explored its callers in login.py and middleware.py..."            │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ [Recent Exchanges - Uncompressed]                                        │ │
│ │ Tool: find_definition("UserService")                                     │ │
│ │ Result: src/services/auth.py:45 - class UserService                      │ │
│ │                                                                          │ │
│ │ Tool: find_references("UserService")                                     │ │
│ │ Result: 12 usages across login.py, middleware.py, tests/...              │ │
│ │                                                                          │ │
│ │ Tool: ask_oracle("How does UserService interact with database?")         │ │
│ │ [CURRENT]                                                                │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Token Budget: 16000 | Used: 12500 | Threshold (80%): 12800                  │
│ Compression triggered at: 12800 tokens                                       │
└─────────────────────────────────────────────────────────────────────────────┘

COMPRESSION STRATEGY:
1. When tokens > 80% budget → compress oldest exchanges
2. Keep last N exchanges (default: 5) uncompressed
3. Compress to summary preserving: symbols mentioned, file paths, key insights
4. Store compressed summaries for potential retrieval
```

### Lazy LLM Evaluation (Cost Optimization)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LAZY EVALUATION PHILOSOPHY                           │
│              "Generate on read, not on write"                                │
└─────────────────────────────────────────────────────────────────────────────┘

WRITE PATH (No LLM calls):
┌────────────────┐     ┌────────────────┐     ┌────────────────┐
│ vlt thread     │     │ Store raw      │     │ Mark as        │
│ push "thought" │ ──▶ │ content only   │ ──▶ │ "needs_summary"│
└────────────────┘     └────────────────┘     └────────────────┘
                       Time: <50ms, Cost: $0

READ PATH (LLM calls on-demand):
┌────────────────┐     ┌────────────────┐     ┌────────────────┐
│ vlt thread     │     │ Check: stale?  │     │ If stale:      │
│ read <thread>  │ ──▶ │ last_node_id   │ ──▶ │ regenerate     │
└────────────────┘     │ > summarized?  │     │ incrementally  │
                       └────────────────┘     └────────────────┘
                                              Time: ~2s, Cost: ~$0.001

ORACLE QUERY PATH (Selective generation):
┌────────────────┐     ┌────────────────┐     ┌────────────────┐
│ Oracle query   │     │ Retrieve       │     │ Only generate  │
│ matches        │ ──▶ │ matching       │ ──▶ │ summaries for  │
│ 3 threads      │     │ threads        │     │ those 3        │
└────────────────┘     └────────────────┘     └────────────────┘
                       (Skip 97 unrelated threads)

STALENESS DETECTION:
┌─────────────────────────────────────────────────────────────────┐
│ Thread: "auth-design"                                           │
│ ├── nodes: [1, 2, 3, 4, 5, 6, 7, 8]  (8 nodes total)           │
│ ├── last_summarized_node_id: 5                                  │
│ └── status: STALE (3 new nodes since summary)                   │
│                                                                 │
│ On read: Summarize nodes 6, 7, 8 only (incremental)             │
│ Update: last_summarized_node_id = 8                             │
└─────────────────────────────────────────────────────────────────┘
```

### Delta-Based Index Commits

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DELTA-BASED INDEXING                                  │
│              "Batch changes, commit when meaningful"                         │
└─────────────────────────────────────────────────────────────────────────────┘

FILE CHANGE FLOW:
┌────────────┐    ┌────────────────┐    ┌────────────────┐    ┌────────────┐
│ File save  │    │ Detect change  │    │ Add to delta   │    │ Check      │
│ (editor)   │ ─▶ │ (hash compare) │ ─▶ │ queue          │ ─▶ │ thresholds │
└────────────┘    └────────────────┘    └────────────────┘    └─────┬──────┘
                                                                    │
                  ┌─────────────────────────────────────────────────┘
                  │
                  ▼
    ┌─────────────────────────────────────────────────────────────────────┐
    │ THRESHOLD CHECK                                                      │
    │                                                                      │
    │ IF (queued_files >= 5) OR (queued_lines >= 1000):                   │
    │   → BATCH COMMIT: Reindex all queued files in one operation          │
    │                                                                      │
    │ ELSE IF (time_since_last_change > 5 minutes):                       │
    │   → TIMEOUT COMMIT: Commit whatever is queued                        │
    │                                                                      │
    │ ELSE:                                                                │
    │   → QUEUE: Keep waiting for more changes                             │
    └─────────────────────────────────────────────────────────────────────┘

JUST-IN-TIME INDEXING (Query-triggered):
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│ Oracle query   │    │ Check: query   │    │ Index those    │
│ "auth logic"   │ ─▶ │ matches queued │ ─▶ │ files first,   │
│                │    │ files?         │    │ then query     │
└────────────────┘    └────────────────┘    └────────────────┘

DELTA QUEUE STATE:
┌─────────────────────────────────────────────────────────────────┐
│ Delta Queue Status (vlt coderag status)                         │
│ ├── Queued files: 3                                             │
│ │   ├── src/auth.py (modified 2 min ago, +45 lines)            │
│ │   ├── src/login.py (modified 1 min ago, +12 lines)           │
│ │   └── tests/test_auth.py (modified 30 sec ago, +28 lines)    │
│ ├── Total delta: 85 lines (threshold: 1000)                     │
│ ├── Files threshold: 3/5                                        │
│ └── Auto-commit in: 3 minutes                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

### Documentation (this feature)

```text
specs/007-vlt-oracle/
├── spec.md              # Feature specification (40 FRs)
├── plan.md              # This file
├── research.md          # Technical research (updated with LSP/SCIP)
├── data-model.md        # Entity definitions (updated)
├── quickstart.md        # Developer onboarding
├── contracts/
│   ├── oracle-api.yaml  # OpenAPI for Document-MCP endpoints
│   └── mcp-tools.json   # MCP tool schemas (5 tools)
└── tasks.md             # Implementation tasks (via /speckit.tasks)
```

### Source Code (vlt-cli Extensions)

**Location**: `/home/wolfe/Projects/vlt-cli/`

```text
src/vlt/
├── main.py                         # Add oracle_app, coderag_app command groups
│
├── core/
│   ├── oracle.py                   # OracleOrchestrator - main entry point
│   │
│   ├── coderag/                    # CodeRAG subsystem
│   │   ├── __init__.py
│   │   ├── indexer.py              # Orchestrates full indexing pipeline
│   │   ├── chunker.py              # LlamaIndex CodeSplitter wrapper
│   │   ├── embedder.py             # qwen3-8b embedding via OpenRouter
│   │   ├── graph.py                # Import/call graph builder (tree-sitter)
│   │   ├── repomap.py              # Aider-style repo map generator
│   │   ├── ctags.py                # Universal Ctags wrapper
│   │   ├── bm25.py                 # SQLite FTS5 keyword index
│   │   └── store.py                # SQLAlchemy models for code data
│   │
│   ├── retrievers/                 # Retrieval implementations
│   │   ├── __init__.py
│   │   ├── base.py                 # IRetriever protocol
│   │   ├── vector.py               # Vector similarity search
│   │   ├── bm25.py                 # BM25 keyword search
│   │   ├── graph.py                # Graph traversal (definitions, references)
│   │   ├── vault.py                # Document-MCP HTTP client
│   │   └── threads.py              # vlt seek wrapper
│   │
│   ├── reranker.py                 # Cross-encoder or LLM-based reranking
│   ├── query_analyzer.py           # Detect query type (definition, refs, etc.)
│   ├── context_assembler.py        # Build final context for synthesis
│   │
│   └── models.py                   # Add CodeChunk, CodeNode, CodeEdge, RepoMap
│
├── lib/
│   └── llm.py                      # Add qwen3-8b embedding support
│
└── tests/
    ├── unit/
    │   ├── test_chunker.py         # LlamaIndex CodeSplitter tests
    │   ├── test_graph.py           # Graph builder tests
    │   ├── test_repomap.py         # Repo map generation tests
    │   ├── test_retrievers.py      # Each retriever
    │   ├── test_reranker.py        # Reranking logic
    │   └── test_query_analyzer.py  # Query type detection
    └── integration/
        ├── test_indexing.py        # Full indexing pipeline
        └── test_oracle_flow.py     # End-to-end query
```

### Source Code (Document-MCP Extensions)

**Location**: This repo (`/mnt/BigAssDrive/00projects/11UnifiedTolling/Vlt-Bridge/`)

```text
backend/
├── src/
│   ├── api/routes/
│   │   └── oracle.py               # /api/oracle, /api/oracle/stream endpoints
│   ├── services/
│   │   └── oracle_bridge.py        # Calls vlt oracle or imports module
│   └── mcp/
│       └── server.py               # ADD: 5 MCP tools
└── tests/
    └── unit/
        └── test_oracle_route.py

frontend/
└── src/
    ├── components/
    │   └── OracleChat.tsx          # Chat panel for oracle
    ├── services/
    │   └── oracle.ts               # API client
    └── types/
        └── oracle.ts               # TypeScript types
```

## MCP Tools Schema

```json
{
  "tools": [
    {
      "name": "ask_oracle",
      "description": "Ask a question about the codebase. Returns synthesized answer with citations.",
      "parameters": {
        "question": "string (required)",
        "sources": "array of 'vault'|'code'|'threads' (optional)",
        "explain": "boolean (optional)"
      }
    },
    {
      "name": "search_code",
      "description": "Search code using hybrid retrieval (semantic + keyword).",
      "parameters": {
        "query": "string (required)",
        "limit": "integer (default: 10)",
        "language": "string (optional filter)"
      }
    },
    {
      "name": "find_definition",
      "description": "Find where a symbol is defined. Uses code intelligence for exact lookup.",
      "parameters": {
        "symbol": "string (required)",
        "scope": "string (optional, file path to narrow search)"
      }
    },
    {
      "name": "find_references",
      "description": "Find all usages of a symbol. Uses call graph and code intelligence.",
      "parameters": {
        "symbol": "string (required)",
        "limit": "integer (default: 20)"
      }
    },
    {
      "name": "get_repo_map",
      "description": "Get codebase structure overview. Returns Aider-style repo map.",
      "parameters": {
        "scope": "string (optional, subdirectory to focus on)",
        "max_tokens": "integer (default: 4000)"
      }
    }
  ]
}
```

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Hybrid retrieval (3 paths) | Pure vector fails for code; research unanimous | Single retrieval misses exact matches OR semantic relationships |
| Reranking stage | Top-k from hybrid needs scoring | Without reranking, irrelevant results pollute context |
| Repo map generation | Critical for "big picture" queries | Aider's success validates; LLM can't navigate without overview |
| 5 MCP tools (not 1) | Coding agents need granular control | Single tool can't expose definition lookup, references, map |
| ctags + graph + FTS5 | Different query types need different indexes | Embedding-only misses structural queries entirely |

## Implementation Phases

### Phase 1: CodeRAG Indexing Foundation
**Goal**: Parse code, extract chunks, build basic indexes

- [ ] tree-sitter integration for multi-language parsing
- [ ] LlamaIndex CodeSplitter integration (Sweep's chunker)
- [ ] Context enrichment (imports, class def, signature, docstring)
- [ ] qwen/qwen3-embedding-8b embedding via OpenRouter
- [ ] SQLite storage for CodeChunk entities
- [ ] `vlt coderag init` and `vlt coderag status` commands
- [ ] Unit tests for chunker, embedder

### Phase 2: Hybrid Retrieval Pipeline
**Goal**: Vector + BM25 + Graph retrieval

- [ ] SQLite FTS5 BM25 index for code chunks
- [ ] Vector search retriever
- [ ] BM25 search retriever
- [ ] Import/call graph builder (tree-sitter based)
- [ ] Graph traversal retriever (definitions, references)
- [ ] Parallel retrieval orchestration
- [ ] Result merging and deduplication
- [ ] Unit tests for each retriever

### Phase 3: Code Intelligence
**Goal**: Exact definition/reference lookup

- [ ] Universal Ctags integration
- [ ] ctags index generation during `coderag init`
- [ ] Definition lookup from ctags
- [ ] Query analyzer (detect definition vs reference vs conceptual)
- [ ] Fallback chain: ctags → graph → semantic search
- [ ] Unit tests for ctags, query analyzer

### Phase 4: Repository Map
**Goal**: Aider-style codebase overview

- [ ] Symbol extraction from tree-sitter AST
- [ ] Reference graph construction
- [ ] PageRank/centrality calculation
- [ ] Token-budgeted map generation with pruning
- [ ] `vlt coderag map` command
- [ ] Map slice selection for query context
- [ ] Unit tests for repo map generator

### Phase 5: Reranking and Synthesis
**Goal**: Quality scoring and answer generation

- [ ] Reranker interface
- [ ] LLM-based reranking implementation (cheap model)
- [ ] Context assembler (code + vault + threads + map)
- [ ] Token budget management
- [ ] Synthesis prompt engineering
- [ ] `vlt oracle "question"` command
- [ ] Integration tests for full pipeline

### Phase 6: MCP Tools
**Goal**: Full toolset for coding agents

- [ ] `ask_oracle` MCP tool
- [ ] `search_code` MCP tool
- [ ] `find_definition` MCP tool
- [ ] `find_references` MCP tool
- [ ] `get_repo_map` MCP tool
- [ ] JSON output formatting
- [ ] MCP tool tests

### Phase 7: Web UI
**Goal**: Browser-based oracle access

- [ ] `/api/oracle` endpoint
- [ ] `/api/oracle/stream` streaming endpoint
- [ ] OracleChat React component
- [ ] Citation linking in UI
- [ ] Integration with existing ChatPanel

### Phase 8: Polish
**Goal**: Session logging, tests as context, git signals

- [ ] Session logging to vlt threads
- [ ] Test file boosting in retrieval
- [ ] Git blame/history integration (optional)
- [ ] `--explain` mode for debugging
- [ ] `--source` filtering
- [ ] Incremental indexing optimization

## Artifacts Generated

- [spec.md](./spec.md) - Updated specification (40 FRs, 10 user stories)
- [plan.md](./plan.md) - This file (production architecture)
- [research.md](./research.md) - Technical research (to be updated with LSP/SCIP)
- [data-model.md](./data-model.md) - Entity definitions (to be updated)
- [quickstart.md](./quickstart.md) - Developer onboarding guide
- [contracts/oracle-api.yaml](./contracts/oracle-api.yaml) - OpenAPI spec (to be updated)
- [contracts/mcp-tools.json](./contracts/mcp-tools.json) - MCP tool schemas (to be updated)

## Key Dependencies to Install

**vlt-cli (Python)**:
```toml
[project.optional-dependencies]
oracle = [
    "llama-index>=0.10.0",
    "llama-index-core>=0.10.0",
    "tree-sitter>=0.21.0",
    "tree-sitter-languages>=1.10.0",
    "httpx>=0.28.0",
]
```

**System**:
- Universal Ctags: `apt install universal-ctags` or `brew install universal-ctags`

## Next Steps

Run `/speckit.tasks` to generate the implementation task list with all phases.
