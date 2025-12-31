# Implementation Tasks: Vault CLI (vlt)

**Total Tasks**: 35
**Scope**: MVP implementation of `vlt` CLI for agent thought management, including asynchronous summarization and search.

## Dependencies

- **Phase 1 (Setup)**: Blocks everything.
- **Phase 2 (Foundational)**: Blocks US1, US2, US3, US4.
- **Phase 3 (US1)**: Blocks US2, US3. (Core data ingestion).
- **Phase 4 (US2)**: Dependent on US1. Blocks nothing critical (can run parallel with US3).
- **Phase 5 (US3)**: Dependent on US1. Core value add (Librarian). Blocks US4.
- **Phase 6 (US4)**: Dependent on US3 (needs embeddings).

## Phase 1: Setup

**Goal**: Initialize project structure and configuration.

- [x] T001 Create project directories (`src/vlt`, `tests`, `src/vlt/core`, `src/vlt/cli`, `src/vlt/lib`)
- [x] T002 Initialize `pyproject.toml` with dependencies (`typer`, `pydantic`, `sqlalchemy`, `rich`, `numpy`, `openai` or `httpx` for OpenRouter)
- [x] T003 Create `src/vlt/config.py` for loading environment variables (LLM keys, DB path) using `pydantic-settings`
- [x] T004 Create `src/vlt/db.py` to handle SQLite connection and session management

## Phase 2: Foundational

**Goal**: Define core data models and abstract interfaces.

- [x] T005 Implement `Project` model in `src/vlt/core/models.py`
- [x] T006 Implement `Thread` model in `src/vlt/core/models.py`
- [x] T007 Implement `Node` model in `src/vlt/core/models.py`
- [x] T008 Implement `State` model in `src/vlt/core/models.py` with polymorphic targeting
- [x] T009 Create `src/vlt/core/interfaces.py` defining `IVaultService`, `ILibrarian`, `ILLMProvider`
- [x] T010 Implement database migration/initialization script in `src/vlt/core/migrations.py` (using `alembic` or simple `Base.metadata.create_all`)

## Phase 3: User Story 1 - Initialize and Log Thoughts

**Goal**: Enable synchronous, low-latency logging of thoughts via CLI.
**Priority**: P1
**Independent Test**: Create project, thread, and push thoughts; verify in DB.

- [x] T011 [US1] Implement `SqliteVaultService` in `src/vlt/core/service.py` (create_project, create_thread)
- [x] T012 [US1] Implement `add_thought` logic in `SqliteVaultService` ensuring <50ms write time
- [x] T013 [US1] Create CLI entry point `src/vlt/main.py` using `Typer`
- [x] T014 [US1] Implement `vlt init` command to setup local DB
- [x] T015 [US1] Implement `vlt thread new` command
- [x] T016 [US1] Implement `vlt thread push` command

## Phase 4: User Story 2 - Retrieve Context and Overview

**Goal**: Display high-level summaries and thread details.
**Priority**: P1
**Independent Test**: Populate DB with mock data, run `vlt overview`, verify output format.

- [x] T017 [US2] Implement `get_project_overview` in `SqliteVaultService` (fetching Project + latest State)
- [x] T018 [US2] Implement `get_thread_state` in `SqliteVaultService` (fetching Thread + State + recent Nodes)
- [x] T019 [US2] Implement `vlt overview` command using `Rich` tables/tree
- [x] T020 [US2] Implement `vlt thread read` command using `Rich` markdown rendering

## Phase 5: User Story 3 - Asynchronous Summarization

**Goal**: Background processing of nodes into summaries.
**Priority**: P2
**Independent Test**: Add nodes, run `Librarian.process_pending_nodes`, verify State table updates.

- [x] T021 [US3] Implement `OpenRouterLLMProvider` in `src/vlt/lib/llm.py` (generate_summary, get_embedding)
- [x] T022 [US3] Implement `Librarian` logic in `src/vlt/core/librarian.py` (fetching unsummarized nodes)
- [x] T023 [US3] Implement `process_pending_nodes` logic (calling LLM, creating/updating State, marking Nodes processed)
- [x] T024 [US3] Implement `update_project_overviews` logic (aggregating Thread summaries)
- [x] T025 [US3] Add `vlt librarian run` command to `src/vlt/main.py`
- [x] T026 [US3] Add daemon mode flag to `vlt librarian run` (simple loop with sleep)

## Phase 6: User Story 4 - Semantic Search

**Goal**: Retrieve nodes via vector search.
**Priority**: P3
**Independent Test**: Seed DB with embeddings, run `search`, verify semantic matches.

- [x] T027 [US4] Implement `VectorService` in `src/vlt/core/vector.py` using `numpy` for in-memory cosine similarity
- [x] T028 [US4] Integrate embedding generation into `Librarian` (during processing loop)
- [x] T029 [US4] Implement `search` method in `SqliteVaultService` (combining VectorService + DB fetch)
- [x] T030 [US4] Implement `vlt thread seek` command
- [x] T031 [US4] Add `--project` flag to `vlt thread seek` for global search

## Phase 7: Polish & Cross-Cutting

**Goal**: Refine UX and handle edge cases.

- [x] T032 Implement configuration wizard for `vlt init` (asking for API keys)
- [x] T033 Add error handling for network failures in Librarian (retry logic)
- [x] T034 Optimize `vlt thread push` latency (ensure minimal imports on startup)
- [x] T035 Add `--json` output flag to all read commands for machine consumption

## Phase 8: The Knowledge Graph

**Goal**: Transform the flat log into a connected semantic graph.

- [x] T036 Add `Tag` model and `Node.tags` relationship.
- [x] T037 Add `Reference` model for cross-thread linking.
- [x] T038 Implement `vlt tag` and `vlt link` commands.
- [ ] T039 Update `vlt thread seek` to support tag filtering.

## Phase 9: Project Manager Scaffolding

**Goal**: Integrate `vlt` with the `Document-MCP` RAG harness via Markdown Sync.

- [ ] T040 Implement `vlt export` command (Markdown format).
- [ ] T041 Add `VLT_SYNC_PATH` config to `vlt` (pointing to `Document-MCP/data/vaults/default/vlt`).
- [ ] T042 Update `Librarian` to auto-export changed threads to `VLT_SYNC_PATH`.

## Implementation Strategy

1.  **MVP (Phase 1-3)**: You will have a working logging tool. Summaries will be empty/static.
2.  **Alpha (Phase 4-5)**: You add the "Brain" (summarization).
3.  **Beta (Phase 6-7)**: You add "Memory" (search) and polish.

## Parallel Execution

- **Phase 4 & 5** can be developed in parallel after Phase 3 is stable.
- **Frontend (CLI)** tasks (T015, T016, T019, T020) can be implemented independently if Service Interfaces (T009) are mocked.
