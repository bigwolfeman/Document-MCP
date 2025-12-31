# Feature Specification: Vault CLI (vlt) - Agent Thought Management

**Feature Branch**: `001-vault-cli`  
**Created**: 2025-12-13  
**Status**: Draft  
**Input**: User description: "Implement vlt CLI for agent thought management"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Initialize and Log Thoughts (Priority: P1)

An AI agent or human user initializes a new project/thread and logs thoughts incrementally to maintain a persistent stream of consciousness without context bloat.

**Why this priority**: Core functionality for data ingestion and structure creation. Without this, there is no data to manage.

**Independent Test**: Can be tested by running the CLI to create a thread and push messages, verifying the database contains the raw entries.

**Acceptance Scenarios**:

1. **Given** no existing project, **When** user runs `vlt thread new <project> <thread> "<initial>"`, **Then** a new project and thread are created, and the initial thought is recorded.
2. **Given** an active thread, **When** user runs `vlt thread push <id> "<thought>"`, **Then** the thought is appended to the thread history immediately (low latency).
3. **Given** a thread, **When** user runs `vlt thread push`, **Then** the command returns a success confirmation with the new Node ID.

---

### User Story 2 - Retrieve Context and Overview (Priority: P1)

An AI agent "wakes up" (starts a new session) or needs to refresh its memory and requests a high-level overview of the project or a deep dive into a specific thread.

**Why this priority**: Solves the "Cold Start Problem" and enables agents to resume work effectively across sessions.

**Independent Test**: Can be tested by running the CLI read/overview commands on a populated database and verifying the output matches the expected summaries.

**Acceptance Scenarios**:

1. **Given** a project with multiple threads, **When** user runs `vlt overview`, **Then** the system displays a project-level summary and a list of active threads with their statuses.
2. **Given** a specific thread ID, **When** user runs `vlt thread read <id>`, **Then** the system displays the thread's executive summary, narrative chain, and active constraints.

---

### User Story 3 - Asynchronous Summarization (Priority: P2)

A background service ("Librarian") automatically processes new thoughts, updates thread summaries, and generates embeddings to keep the "State" up-to-date without blocking the CLI.

**Why this priority**: Enables the "lossy compression" of the thought stream, keeping context windows manageable while preserving meaning.

**Independent Test**: Can be tested by pushing thoughts via CLI, then running the daemon and verifying that `State` records are updated and embeddings are generated.

**Acceptance Scenarios**:

1. **Given** new un-summarized nodes, **When** the daemon runs, **Then** it generates an updated natural language summary using an LLM.
2. **Given** multiple updated threads, **When** the daemon runs, **Then** it updates the global project overview/state.
3. **Given** a thread with new nodes, **When** the daemon processes them, **Then** the thread's "Head" pointer in the State object is updated to the latest node.

---

### User Story 4 - Semantic Search (Priority: P3)

An agent searches for specific past information using natural language queries to recall details buried in long threads.

**Why this priority**: Enhances long-term memory retrieval beyond immediate summaries.

**Independent Test**: Can be tested by populating the DB with diverse topics and running search queries to verify relevant results are returned.

**Acceptance Scenarios**:

1. **Given** a specific thread, **When** user runs `vlt thread seek <id> "<query>"`, **Then** the system returns relevant nodes from that thread based on semantic similarity.
2. **Given** a project, **When** user runs `vlt thread seek -a "<query>" --project <project>`, **Then** the system returns relevant nodes from *all* threads in the project.

### Edge Cases

- **Concurrent Writes**: What happens if multiple agent instances push to the same thread simultaneously? (Database locking/concurrency handling).
- **Network Failure**: What happens if the Librarian cannot reach the LLM provider? (Retry logic, error logging, stale state indication).
- **Empty State**: What happens if `read` or `overview` is called before the Librarian has processed the first nodes? (Should show raw nodes or a "Pending" status).
- **Large Inputs**: What happens if a thought exceeds the context limit of the embedding model? (Truncation or rejection).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a CLI tool (`vlt`) for synchronous, low-latency (<50ms) logging of text data ("thoughts").
- **FR-002**: System MUST support hierarchical organization: Projects contain Threads; Threads contain Nodes.
- **FR-003**: System MUST provide a background service ("Librarian") that monitors for new Nodes and triggers summarization.
- **FR-004**: The Librarian MUST use an external LLM API to generate summaries of Threads and Projects.
- **FR-005**: System MUST store both raw text (Nodes) and synthesized summaries (State) in a local relational database.
- **FR-006**: System MUST support semantic search over Node content using vector embeddings.
- **FR-007**: `vlt overview` MUST display the most recent project-level summary and a list of active threads.
- **FR-008**: `vlt thread read` MUST display the current thread summary (State) and recent raw nodes.
- **FR-009**: System MUST allow configuration of LLM provider settings (API keys, model endpoints).

### Assumptions & Dependencies

- **User Environment**: The user has a valid API key for the selected LLM provider.
- **System Capabilities**: The host system supports background processes (daemons) and has local write access for the database.
- **Connectivity**: Internet connection is required for the Librarian to access the LLM API (unless a local model is configured).

### Key Entities *(include if feature involves data)*

- **Project**: A logical grouping of threads (e.g., "crypto-bot").
- **Thread**: A distinct stream of thought (e.g., "optim-strategy") consisting of a linked list of Nodes.
- **Node**: An immutable record containing content, timestamp, and a link to the previous node.
- **State**: A mutable record containing the current summary ("Head State") of a Thread or Project.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `vlt thread push` command returns control to the user in under 50 milliseconds (p95).
- **SC-002**: `vlt thread read` returns a summary that includes information from nodes added within the last processing cycle.
- **SC-003**: System successfully summarizes a thread with >50 nodes into a concise "State" description.
- **SC-004**: Search queries return relevant results (top 3 matches contain the target concept) for known data.
- **SC-005**: Project overview is generated and available for agents starting a new session.