# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]
**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

**Language**: Python 3.11+ (chosen for modularity and ease of NLP integration)
**Frameworks**:
- `Typer`: For CLI interface
- `Pydantic`: For data validation and schema definition
- `SQLAlchemy`: For ORM/database interactions
- `Rich`: For TUI output

**External Services**:
- OpenRouter API: For LLM access (Librarian service)

**Data Storage**:
- SQLite: Single local file database
- Vector Search: Standard SQLite (BLOB storage) + Numpy for in-memory brute-force search (per Research decision)

**Design Patterns**:
- Repository Pattern: To decouple data access
- Command Pattern: For CLI operations
- Observer Pattern: Librarian monitoring database changes

## Constitution Check

**Principles**:
- **Library-First**: The core logic (thought management, summarization) will be implemented as a library (`vlt-core`) separate from the CLI and Daemon entry points.
- **CLI Interface**: The primary interface is `vlt`, adhering to stdin/args → stdout.
- **Test-First**: TDD will be enforced.
- **Simplicity**: Starting with SQLite avoids complex infrastructure dependencies.

**Violations**: None identified. All design choices align with the Library-First and Simplicity principles.

## Plan Status
**Phase 1 Complete**: Design artifacts generated (`data-model.md`, `contracts/interfaces.md`, `quickstart.md`).
**Ready for**: Task Generation.



## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |

## Phase 7: Polish & Cross-Cutting

**Goal**: Refine UX and handle edge cases.

- [x] T032 Implement configuration wizard for `vlt init` (asking for API keys)
- [x] T033 Add error handling for network failures in Librarian (retry logic)
- [x] T034 Optimize `vlt thread push` latency (ensure minimal imports on startup)
- [x] T035 Add `--json` output flag to all read commands for machine consumption

## Phase 8: The Knowledge Graph (Current Focus)

**Goal**: Transform the flat log into a connected semantic graph.

- [ ] T036 Add `Tag` model and `Node.tags` relationship.
- [ ] T037 Add `Reference` model for cross-thread linking.
- [ ] T038 Implement `vlt tag` and `vlt link` commands.
- [ ] T039 Update `vlt thread seek` to support tag filtering.

## Phase 9: Project Manager Scaffolding (Future)

**Goal**: Integrate `vlt` with the `Document-MCP` RAG harness.
- **Discovery**: `Document-MCP` uses a filesystem-based Vault (`data/vaults/<user>/*.md`).
- **Strategy**: **Markdown Sync**.
    - `vlt` will export Thread Summaries + Recent Nodes as formatted Markdown files.
    - `Document-MCP` will ingest these files automatically via its existing RAG indexer (`backend/src/services/rag_index.py`).
- **Tasks**:
    - [ ] T040 Implement `vlt export` command (Markdown format).
    - [ ] T041 Add `VLT_SYNC_PATH` config to `vlt` (pointing to `Document-MCP/data/vaults/default/vlt`).
    - [ ] T042 Update `Librarian` to auto-export changed threads to `VLT_SYNC_PATH`.

## Implementation Strategy
# ...
