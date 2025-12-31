# Tasks: Vlt Oracle - Multi-Source Intelligent Context Retrieval

**Input**: Design documents from `/specs/007-vlt-oracle/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/
**Generated**: 2025-12-30

**Project Type**: Multi-repo (vlt-cli extension + Document-MCP integration)
- **vlt-cli**: `/home/wolfe/Projects/vlt-cli/`
- **Document-MCP**: This repo (`/mnt/BigAssDrive/00projects/11UnifiedTolling/Vlt-Bridge/`)

**Tests**: No explicit test tasks generated (not requested in spec). Tests can be added following Phase structure.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story (US2, US3, etc.)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and dependencies for vlt-cli extensions

- [x] T001 Create vlt-cli module structure: `src/vlt/core/coderag/`, `src/vlt/core/retrievers/`
- [x] T002 [P] Add CodeRAG dependencies to vlt-cli pyproject.toml: llama-index, tree-sitter, tree-sitter-languages
- [x] T003 [P] Verify Universal Ctags is installed, add to README prerequisites
- [x] T004 [P] Add OpenRouter API configuration for qwen/qwen3-embedding-8b in vlt-cli config

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database schema, core models, and base infrastructure that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Create SQLAlchemy models for CodeChunk in `src/vlt/core/models.py`
- [x] T006 [P] Create SQLAlchemy models for CodeNode and CodeEdge in `src/vlt/core/models.py`
- [x] T007 [P] Create SQLAlchemy models for SymbolDefinition in `src/vlt/core/models.py`
- [x] T008 [P] Create SQLAlchemy models for RepoMap in `src/vlt/core/models.py`
- [x] T009 [P] Create SQLAlchemy models for OracleSession in `src/vlt/core/models.py`
- [x] T010 [P] Create SQLAlchemy models for OracleConversation in `src/vlt/core/models.py`
- [x] T011 [P] Create SQLAlchemy models for IndexDeltaQueue in `src/vlt/core/models.py`
- [x] T012 [P] Create SQLAlchemy models for ThreadSummaryCache in `src/vlt/core/models.py`
- [x] T013 Create database migrations for all new tables in vlt-cli vault.db
- [x] T014 [P] Create FTS5 virtual table for code_chunk_fts (BM25 index)
- [x] T015 [P] Create Pydantic schemas for RetrievalResult, OracleQuery, OracleResponse in `src/vlt/core/schemas.py`
- [x] T016 [P] Create IRetriever protocol interface in `src/vlt/core/retrievers/base.py`
- [x] T017 Add [coderag] and [oracle] configuration sections to vlt.toml schema

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 2 - CodeRAG Indexing with Hybrid Pipeline (Priority: P1) 🎯 MVP

**Goal**: Parse code, extract context-enriched chunks, build vector/BM25/graph indexes

**Independent Test**: Run `vlt coderag init`, then `vlt coderag search "function that handles login"` - should return hybrid results

### Implementation for User Story 2

- [x] T018 [US2] Implement tree-sitter parser wrapper in `src/vlt/core/coderag/parser.py`
- [x] T019 [US2] Implement LlamaIndex CodeSplitter integration in `src/vlt/core/coderag/chunker.py`
- [x] T020 [US2] Add context enrichment (imports, class_context, signature, decorators, docstring) to chunker
- [x] T021 [US2] Implement qwen3-8b embedding client in `src/vlt/core/coderag/embedder.py`
- [x] T022 [US2] Implement SQLite FTS5 BM25 indexer in `src/vlt/core/coderag/bm25.py`
- [x] T023 [US2] Implement import/call graph builder in `src/vlt/core/coderag/graph.py`
- [x] T024 [US2] Implement Universal Ctags wrapper in `src/vlt/core/coderag/ctags.py`
- [x] T025 [US2] Implement CodeRAG store (chunk storage, retrieval) in `src/vlt/core/coderag/store.py`
- [x] T026 [US2] Create CodeRAG indexer orchestrator in `src/vlt/core/coderag/indexer.py`
- [x] T027 [US2] Implement `vlt coderag init` CLI command in `src/vlt/main.py`
- [x] T028 [US2] Implement `vlt coderag status` CLI command in `src/vlt/main.py`
- [x] T029 [US2] Implement `vlt coderag search` CLI command in `src/vlt/main.py`
- [x] T030 [US2] Add incremental indexing using content hash comparison in indexer.py

**Checkpoint**: CodeRAG indexing complete - can search code via hybrid retrieval

---

## Phase 4: User Story 3 - Repository Map (Priority: P1)

**Goal**: Generate Aider-style codebase overview with centrality-based pruning

**Independent Test**: Run `vlt coderag map` - should produce navigable outline fitting token budget

### Implementation for User Story 3

- [x] T031 [US3] Implement symbol extraction from tree-sitter AST in `src/vlt/core/coderag/repomap.py`
- [x] T032 [US3] Implement reference graph construction using CodeNode/CodeEdge
- [x] T033 [US3] Implement PageRank/centrality calculation for symbols
- [x] T034 [US3] Implement token-budgeted map generation with pruning
- [x] T035 [US3] Implement map scope filtering (subdirectory focus)
- [x] T036 [US3] Implement `vlt coderag map` CLI command in `src/vlt/main.py`
- [x] T037 [US3] Store generated RepoMap in database for caching

**Checkpoint**: Repo map generation complete

---

## Phase 5: User Story 4 - LSP-Driven Context Expansion (Priority: P1)

**Goal**: Exact definition/reference lookup using ctags/graph (not just embeddings)

**Independent Test**: Query "Where is UserService defined?" - should return exact file:line

### Implementation for User Story 4

- [x] T038 [US4] Implement ctags index loader/querier in `src/vlt/core/coderag/ctags.py`
- [x] T039 [US4] Implement definition lookup: ctags → graph → semantic fallback chain
- [x] T040 [US4] Implement reference lookup using call graph edges
- [x] T041 [US4] Create code intelligence interface in `src/vlt/core/coderag/code_intel.py`
- [x] T042 [US4] Implement query type detector (definition vs references vs conceptual) in `src/vlt/core/query_analyzer.py`

**Checkpoint**: Code intelligence queries return exact locations

---

## Phase 6: User Story 5 - Hybrid Retrieval with Reranking (Priority: P1)

**Goal**: Parallel retrieval (vector + BM25 + graph) with reranking before synthesis

**Independent Test**: Search exact function name (BM25 hit) AND conceptual query (vector hit) - both succeed

### Implementation for User Story 5

- [x] T043 [US5] Implement vector search retriever in `src/vlt/core/retrievers/vector.py`
- [x] T044 [P] [US5] Implement BM25 search retriever in `src/vlt/core/retrievers/bm25.py`
- [x] T045 [P] [US5] Implement graph traversal retriever in `src/vlt/core/retrievers/graph.py`
- [x] T046 [US5] Implement result merger and deduplicator
- [x] T047 [US5] Implement LLM-based reranker in `src/vlt/core/reranker.py`
- [x] T048 [US5] Implement parallel retrieval orchestration (asyncio.gather)
- [x] T049 [US5] Add retrieval method attribution to results (vector/bm25/graph)

**Checkpoint**: Hybrid retrieval with reranking complete

---

## Phase 7: User Story 13 - Delta-Based Index Commits (Priority: P1)

**Goal**: Queue file changes, batch commit when threshold reached

**Independent Test**: Modify 3 files rapidly - verify single batch index operation

### Implementation for User Story 13

- [ ] T050 [US13] Implement file change detection (hash comparison) in `src/vlt/core/coderag/delta.py`
- [ ] T051 [US13] Implement delta queue manager with threshold checking
- [ ] T052 [US13] Implement batch commit logic (files/lines/timeout thresholds)
- [ ] T053 [US13] Implement just-in-time indexing for query-matched queued files
- [ ] T054 [US13] Add delta queue status to `vlt coderag status` output
- [ ] T055 [US13] Implement `vlt coderag sync --force` command

**Checkpoint**: Delta-based indexing reduces API calls

---

## Phase 8: User Story 12 - Lazy LLM Evaluation (Priority: P1)

**Goal**: Generate summaries/embeddings on-read, not on-write

**Independent Test**: Push 10 thread entries - verify no LLM calls; read thread - verify summary generated

### Implementation for User Story 12

- [ ] T056 [US12] Modify vlt thread push to skip summary generation
- [ ] T057 [US12] Implement ThreadSummaryCache manager in `src/vlt/core/lazy_eval.py`
- [ ] T058 [US12] Implement staleness detection (last_summarized_node_id check)
- [ ] T059 [US12] Implement incremental summary regeneration (new nodes only)
- [ ] T060 [US12] Modify vlt thread read to trigger lazy summary generation
- [ ] T061 [US12] Integrate lazy evaluation with oracle thread retrieval

**Checkpoint**: Lazy LLM evaluation reduces costs by 70%+

---

## Phase 9: User Story 11 - Shared Conversation Context (Priority: P1)

**Goal**: All MCP tools share single conversation context with compression

**Independent Test**: Call find_definition → find_references → ask_oracle - verify context builds across calls

### Implementation for User Story 11

- [ ] T062 [US11] Implement OracleConversation manager in `src/vlt/core/conversation.py`
- [ ] T063 [US11] Implement exchange logging (tool_name, input, output_summary, key_insights)
- [ ] T064 [US11] Implement token counting for conversation context
- [ ] T065 [US11] Implement compression trigger at 80% token budget
- [ ] T066 [US11] Implement LLM-based context compression preserving symbols/files/insights
- [ ] T067 [US11] Implement mentioned_symbols and mentioned_files tracking
- [ ] T068 [US11] Add conversation context injection to all oracle tools

**Checkpoint**: Shared context enables multi-turn oracle sessions

---

## Phase 10: User Story 1 - Ask Oracle via CLI (Priority: P1) 🎯 CORE FEATURE

**Goal**: Natural language questions answered from all knowledge sources

**Independent Test**: Run `vlt oracle "How does authentication work?"` - get synthesized answer with citations

### Implementation for User Story 1

- [x] T069 [US1] Implement vault retriever (Document-MCP API client) in `src/vlt/core/retrievers/vault.py`
- [x] T070 [P] [US1] Implement thread retriever (vlt seek wrapper) in `src/vlt/core/retrievers/threads.py`
- [x] T071 [US1] Implement context assembler in `src/vlt/core/context_assembler.py`
- [x] T072 [US1] Implement token budget management for context assembly
- [x] T073 [US1] Implement synthesis prompt engineering for oracle answers
- [x] T074 [US1] Implement source citation formatting (file:line, note paths, thread IDs)
- [x] T075 [US1] Create OracleOrchestrator in `src/vlt/core/oracle.py`
- [x] T076 [US1] Implement `vlt oracle "question"` CLI command in `src/vlt/main.py`
- [x] T077 [US1] Handle "no relevant context found" gracefully (FR-005)
- [x] T078 [US1] Include repo map slice in oracle context (FR-006)

**Checkpoint**: Core oracle CLI complete - can ask questions about codebase

---

## Phase 11: User Story 6 - MCP Tools for Coding Agents (Priority: P1)

**Goal**: Expose oracle functionality via MCP tools for Claude Code and other agents

**Independent Test**: Configure Claude Code with MCP server - all 5 tools work

### Implementation for User Story 6

- [x] T079 [US6] Implement `ask_oracle` MCP tool in `backend/src/mcp/server.py`
- [x] T080 [P] [US6] Implement `search_code` MCP tool in `backend/src/mcp/server.py`
- [x] T081 [P] [US6] Implement `find_definition` MCP tool in `backend/src/mcp/server.py`
- [x] T082 [P] [US6] Implement `find_references` MCP tool in `backend/src/mcp/server.py`
- [x] T083 [P] [US6] Implement `get_repo_map` MCP tool in `backend/src/mcp/server.py`
- [x] T084 [US6] Create oracle bridge service in `backend/src/services/oracle_bridge.py`
- [x] T085 [US6] Add MCP tool JSON schemas per contracts/mcp-tools.json
- [x] T086 [US6] Integrate shared conversation context with MCP tool calls
- [x] T087 [US6] Add JSON output formatting for MCP responses

**Checkpoint**: All 5 MCP tools exposed - AI agents can use oracle

---

## Phase 12: User Story 7 - Ask Oracle via Web UI (Priority: P2)

**Goal**: Browser-based oracle chat with streaming responses

**Independent Test**: Open web UI, ask question, see streaming response with clickable citations

### Implementation for User Story 7

- [ ] T088 [US7] Create `/api/oracle` endpoint in `backend/src/api/routes/oracle.py`
- [ ] T089 [US7] Create `/api/oracle/stream` streaming endpoint in `backend/src/api/routes/oracle.py`
- [ ] T090 [US7] Implement OracleChat React component in `frontend/src/components/OracleChat.tsx`
- [ ] T091 [US7] Implement streaming response rendering in OracleChat
- [ ] T092 [US7] Implement citation linking (click → navigate to source)
- [ ] T093 [US7] Create oracle TypeScript types in `frontend/src/types/oracle.ts`
- [ ] T094 [US7] Create oracle API client in `frontend/src/services/oracle.ts`
- [ ] T095 [US7] Integrate OracleChat with existing ChatPanel

**Checkpoint**: Web UI oracle chat complete

---

## Phase 13: User Stories 8-10 - Polish Features (Priority: P3)

**Goal**: Session logging, source filtering, explain mode, test boosting

### User Story 8 - Oracle Session Logging

- [ ] T096 [US8] Implement oracle session logging to vlt threads
- [ ] T097 [US8] Create `oracle-session-YYYY-MM-DD` thread naming convention
- [ ] T098 [US8] Add author attribution (agent ID or "user") to logged entries

### User Story 9 - Source Filtering and Explain Mode

- [ ] T099 [US9] Implement `--source=vault|code|threads` filter in oracle CLI
- [ ] T100 [US9] Implement `--explain` mode showing retrieval traces
- [ ] T101 [US9] Add explain output formatting (scores, paths, reranking decisions)

### User Story 10 - Tests and Git Context

- [ ] T102 [US10] Implement test file boosting in retrieval ranking
- [ ] T103 [US10] Implement git blame integration for "why was this changed?" queries
- [ ] T104 [US10] Add recent commit context for relevant files

**Checkpoint**: All P3 polish features complete

---

## Phase 14: Final Polish & Cross-Cutting Concerns

**Purpose**: Integration testing, documentation, performance validation

- [ ] T105 [P] Update CLAUDE.md with oracle/coderag commands and MCP tools
- [ ] T106 [P] Update vlt-cli README with oracle feature documentation
- [ ] T107 Run end-to-end integration test: init → index → query → web UI
- [ ] T108 Performance validation: <15s oracle response, <5min coderag init (10K files)
- [ ] T109 [P] Validate quickstart.md scenarios work
- [ ] T110 Graceful degradation testing (missing sources, API errors)

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3+ (User Stories)
                                         ↓
                              ┌──────────┴──────────┐
                              ↓                     ↓
                         Phase 3 (US2)          Phase 7 (US13)
                         CodeRAG Indexing       Delta Indexing
                              ↓                     ↓
                    ┌─────────┼─────────┐          │
                    ↓         ↓         ↓          │
               Phase 4    Phase 5    Phase 8       │
               (US3)      (US4)      (US12)        │
               RepoMap    Code Intel  Lazy LLM     │
                    ↓         ↓         ↓          │
                    └────┬────┘         │          │
                         ↓              │          │
                    Phase 6 (US5)       │          │
                    Hybrid Retrieval    │          │
                         ↓              │          │
                         └──────┬───────┘          │
                                ↓                  │
                           Phase 9 (US11)          │
                           Shared Context ←────────┘
                                ↓
                           Phase 10 (US1)
                           Oracle CLI
                                ↓
                           Phase 11 (US6)
                           MCP Tools
                                ↓
                           Phase 12 (US7)
                           Web UI
                                ↓
                           Phase 13 (US8-10)
                           Polish
                                ↓
                           Phase 14
                           Final Polish
```

### User Story Dependencies

| Story | Depends On | Can Start After |
|-------|------------|-----------------|
| US2 (CodeRAG) | Foundational | Phase 2 |
| US3 (RepoMap) | US2 | Phase 3 |
| US4 (Code Intel) | US2 | Phase 3 |
| US5 (Hybrid Retrieval) | US2, US3, US4 | Phase 4+5 |
| US13 (Delta Indexing) | Foundational | Phase 2 |
| US12 (Lazy LLM) | Foundational | Phase 2 |
| US11 (Shared Context) | US5, US12, US13 | Phase 6+7+8 |
| US1 (Oracle CLI) | US5, US11 | Phase 9 |
| US6 (MCP Tools) | US1 | Phase 10 |
| US7 (Web UI) | US1 | Phase 10 |
| US8-10 (Polish) | US1 | Phase 10 |

### Parallel Opportunities

**Within Phase 2 (Foundational)**:
```
T005 (CodeChunk model) → T013 (migrations)
T006-T012 (other models) [P] → T013 (migrations)
T014 (FTS5) [P]
T015-T017 (schemas, interfaces, config) [P]
```

**Within Phase 6 (Hybrid Retrieval)**:
```
T043 (vector) → T046 (merger)
T044 (BM25) [P] → T046 (merger)
T045 (graph) [P] → T046 (merger)
```

**Within Phase 11 (MCP Tools)**:
```
T080-T083 (search_code, find_definition, find_references, get_repo_map) [P]
```

---

## Implementation Strategy

### MVP First (Phases 1-6 + Phase 10)

1. **Phase 1**: Setup project structure
2. **Phase 2**: Database models and schema
3. **Phase 3**: CodeRAG indexing (US2)
4. **Phase 4**: Repository map (US3)
5. **Phase 5**: Code intelligence (US4)
6. **Phase 6**: Hybrid retrieval (US5)
7. **Phase 10**: Oracle CLI (US1) - **STOP HERE FOR MVP**

At this point: `vlt coderag init` and `vlt oracle "question"` work end-to-end

### Full P1 Delivery (Add Phases 7-11)

8. **Phase 7**: Delta indexing (US13)
9. **Phase 8**: Lazy LLM (US12)
10. **Phase 9**: Shared context (US11)
11. **Phase 11**: MCP tools (US6)

At this point: All P1 stories complete, AI agents can use oracle via MCP

### Complete Feature (Add Phases 12-14)

12. **Phase 12**: Web UI (US7 - P2)
13. **Phase 13**: Polish features (US8-10 - P3)
14. **Phase 14**: Final validation

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Tasks** | 110 |
| **Phase 1 (Setup)** | 4 tasks |
| **Phase 2 (Foundational)** | 13 tasks |
| **Phase 3 (US2 - CodeRAG)** | 13 tasks |
| **Phase 4 (US3 - RepoMap)** | 7 tasks |
| **Phase 5 (US4 - Code Intel)** | 5 tasks |
| **Phase 6 (US5 - Retrieval)** | 7 tasks |
| **Phase 7 (US13 - Delta)** | 6 tasks |
| **Phase 8 (US12 - Lazy)** | 6 tasks |
| **Phase 9 (US11 - Context)** | 7 tasks |
| **Phase 10 (US1 - Oracle CLI)** | 10 tasks |
| **Phase 11 (US6 - MCP)** | 9 tasks |
| **Phase 12 (US7 - Web UI)** | 8 tasks |
| **Phase 13 (US8-10 - Polish)** | 9 tasks |
| **Phase 14 (Final)** | 6 tasks |
| **MVP Scope** | Phases 1-6 + 10 (59 tasks) |
| **Parallel [P] Tasks** | 32 tasks |

---

## Notes

- Tasks touch two repos: vlt-cli (`/home/wolfe/Projects/vlt-cli/`) and Document-MCP (this repo)
- Most vlt-cli work is in `src/vlt/core/` - new modules for coderag, retrievers, oracle
- Document-MCP work is backend (MCP tools, API routes) and frontend (OracleChat)
- Delta indexing and lazy LLM can be developed in parallel with main pipeline
- Shared context (US11) should be done AFTER retrieval pipeline is stable
