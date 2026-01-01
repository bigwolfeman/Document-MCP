# Feature Specification: Oracle Agent Architecture

**Feature Branch**: `009-oracle-agent`
**Created**: 2025-12-31
**Status**: Draft
**Input**: User description: "Oracle Agent with proper tool calling, subagent orchestration, context window management, and prompts architecture"

## Overview

The Oracle is an AI project manager that helps developers understand and navigate their codebase. It currently has a critical architectural flaw: the backend shells out to the `vlt oracle` CLI as a subprocess. The backend should BE the Oracle, with both the Web UI and CLI acting as thin clients.

This feature transforms the Oracle into a proper AI agent with:
- Tool calling capabilities (document management, memory, code search, web research)
- Subagent orchestration (Librarian for vault organization)
- Persistent context windows that survive sessions and model changes
- Externalized prompts for maintainability

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask Oracle a Question via Web UI (Priority: P1)

A developer opens the Web UI AI Chat and asks the Oracle a question about their project. The Oracle searches available sources (documentation, code, development threads), synthesizes an answer, and cites its sources. The conversation persists across browser refreshes.

**Why this priority**: This is the primary interaction mode. Without this working, the Oracle provides no value.

**Independent Test**: Can be fully tested by opening the AI Chat panel, typing a question, and verifying the Oracle responds with cited sources from the project.

**Acceptance Scenarios**:

1. **Given** a user is logged in and has a project with indexed code and documentation, **When** they ask "How does authentication work?", **Then** the Oracle searches all sources, provides an answer, and shows clickable citations to specific files/notes.

2. **Given** a user asks a follow-up question in the same session, **When** they reference "the code you just showed me", **Then** the Oracle maintains context and understands the reference.

3. **Given** a user closes their browser and returns the next day, **When** they open the same project chat, **Then** their previous conversation is restored and the Oracle remembers the context.

---

### User Story 2 - Oracle Uses Tools to Complete Research (Priority: P1)

A developer asks the Oracle to research something that requires multiple steps - searching code, reading files, and searching the web. The Oracle autonomously uses its tools to gather information, then synthesizes a response.

**Why this priority**: Tool calling is the core capability that makes the Oracle an agent rather than just a chatbot. Without tools, the Oracle cannot access project context.

**Independent Test**: Can be tested by asking a question that requires code search plus documentation lookup, and verifying the Oracle uses both tools before answering.

**Acceptance Scenarios**:

1. **Given** a user asks "Where is user authentication implemented and what documentation exists for it?", **When** the Oracle processes the request, **Then** it uses code search tool, reads relevant files, searches the vault, and combines findings into a coherent answer.

2. **Given** a user asks about something requiring web search, **When** the Oracle determines external information is needed, **Then** it uses web search, fetches relevant pages, and incorporates findings with proper attribution.

3. **Given** a tool call fails (e.g., file not found), **When** the error occurs, **Then** the Oracle handles it gracefully, informs the user, and tries alternative approaches.

---

### User Story 3 - Oracle Saves Research to Memory (Priority: P2)

After completing research, the Oracle can save important findings, decisions, or context to its long-term memory (vlt threads) and to the documentation vault for future reference.

**Why this priority**: Memory persistence enables the Oracle to learn and improve over time. It's essential for project continuity but not required for basic Q&A functionality.

**Independent Test**: Can be tested by asking the Oracle to save a research finding, then verifying it appears in the appropriate thread or vault note.

**Acceptance Scenarios**:

1. **Given** the Oracle completes research about an architecture decision, **When** the user says "Save this decision to memory", **Then** the Oracle creates a thread entry with the decision rationale and key details.

2. **Given** the Oracle gathers important project context, **When** the user says "Create a note about this", **Then** the Oracle creates a markdown note in the vault with proper structure and wikilinks.

3. **Given** the Oracle has previously saved information, **When** a relevant question is asked later, **Then** the Oracle retrieves and references that saved information.

---

### User Story 4 - Ask Oracle via CLI (Priority: P2)

A developer uses `vlt oracle "question"` from the command line within their project directory. The CLI acts as a thin client, sending the request to the backend Oracle, which processes it and streams back the response.

**Why this priority**: CLI access enables AI coding agents (like Claude Code) to query the Oracle programmatically. Important for automation but Web UI is the primary interface.

**Independent Test**: Can be tested by running `vlt oracle "How does X work?"` from terminal and verifying a streamed response appears.

**Acceptance Scenarios**:

1. **Given** a developer is in a project directory with `vlt.toml`, **When** they run `vlt oracle "What is the project structure?"`, **Then** the CLI sends the request to the backend and streams the response with citations.

2. **Given** the backend is unavailable, **When** the CLI tries to connect, **Then** it displays a helpful error message about server connectivity.

3. **Given** JSON output is requested (`--json`), **When** the query completes, **Then** the CLI outputs valid JSON with answer, sources, and metadata.

---

### User Story 5 - Oracle Delegates to Librarian Subagent (Priority: P3)

When the Oracle needs to reorganize documentation, move files, or create index pages, it delegates these tasks to the Librarian subagent. The Librarian specializes in vault organization while the Oracle focuses on answering questions.

**Why this priority**: Subagent delegation improves quality by using specialized prompts for specific tasks. However, core functionality works without it.

**Independent Test**: Can be tested by asking the Oracle to organize files in a folder, and verifying the Librarian is invoked and completes the task.

**Acceptance Scenarios**:

1. **Given** a user asks the Oracle to "organize the notes in the architecture folder", **When** the Oracle processes this request, **Then** it delegates to the Librarian, which reads notes, creates an index, and moves files as appropriate.

2. **Given** the Librarian completes a task, **When** control returns to the Oracle, **Then** the Oracle summarizes what was done and notifies the user.

3. **Given** the Librarian encounters an issue (e.g., conflicting wikilinks), **When** it cannot proceed, **Then** it reports the issue to the Oracle, which explains the problem to the user.

---

### User Story 6 - Context Survives Model Changes (Priority: P3)

A developer has an ongoing conversation with the Oracle using one model. The next day, the system administrator changes the default model. When the developer returns, their context is preserved and the Oracle continues the conversation seamlessly.

**Why this priority**: Model flexibility is important for cost optimization and capability improvements, but most users will use a consistent model.

**Independent Test**: Can be tested by starting a conversation, changing the model in settings, and verifying the Oracle still has relevant context.

**Acceptance Scenarios**:

1. **Given** a user had a conversation yesterday with Model A, **When** they return today and Model B is now configured, **Then** the Oracle loads compressed context and continues coherently.

2. **Given** context needs to be re-tokenized for a new model, **When** the session resumes, **Then** the compression happens transparently without user-visible delay.

3. **Given** context has grown very large (near token limits), **When** compression occurs, **Then** key decisions and recent exchanges are preserved while older details are summarized.

---

### Edge Cases

- What happens when the Oracle's context window fills up mid-conversation?
  - System compresses older exchanges while preserving recent ones and key decisions
- How does the system handle concurrent requests from the same user?
  - Requests are queued per-project to maintain conversation coherence
- What happens when a tool call takes too long?
  - Timeout after reasonable period with user notification; partial results shown if available
- How does the system handle malformed or malicious questions?
  - Input validation and rate limiting; harmful content is refused with explanation
- What if the external LLM API is unavailable?
  - Graceful degradation with cached information where possible; clear error messaging

## Requirements *(mandatory)*

### Functional Requirements

**Core Oracle Capabilities**

- **FR-001**: System MUST process natural language questions and return synthesized answers with source citations
- **FR-002**: System MUST search across code, documentation vault, and development threads to gather context
- **FR-003**: System MUST stream responses to users in real-time during generation
- **FR-004**: System MUST maintain conversation history within a session
- **FR-005**: System MUST persist conversation context across sessions (browser refreshes, reconnections)

**Tool Calling**

- **FR-006**: System MUST support tool calling for autonomous information gathering
- **FR-007**: System MUST provide tools for reading, writing, searching, and listing vault documents
- **FR-008**: System MUST provide tools for reading, writing, and searching development threads
- **FR-009**: System MUST provide tools for searching code and finding definitions/references
- **FR-010**: System MUST provide tools for web search and URL fetching
- **FR-011**: System MUST handle tool call failures gracefully with fallback strategies
- **FR-012**: System MUST support parallel tool calls when operations are independent

**Subagent Orchestration**

- **FR-013**: System MUST support delegation of specialized tasks to subagents
- **FR-014**: System MUST provide a Librarian subagent for vault organization tasks
- **FR-015**: Subagents MUST have access to a scoped subset of tools appropriate to their role
- **FR-016**: Subagent results MUST be integrated back into the main Oracle response

**Context Management**

- **FR-017**: System MUST track context window token usage per conversation
- **FR-018**: System MUST compress older exchanges when approaching token limits
- **FR-019**: System MUST preserve key decisions and recent exchanges during compression
- **FR-020**: System MUST support resuming context after model changes
- **FR-021**: System MUST scope conversations to projects (each project has its own context)

**Prompt Management**

- **FR-022**: System prompts MUST be stored as external files, not hardcoded in source
- **FR-023**: System MUST support template variables in prompts for context injection
- **FR-024**: Tool descriptions MUST be externally configurable

**Multi-Client Access**

- **FR-025**: System MUST serve requests from both Web UI and CLI clients
- **FR-026**: CLI MUST act as a thin client, delegating processing to the backend
- **FR-027**: System MUST support both streaming and non-streaming response modes

### Key Entities

- **OracleContext**: Persistent conversation state for a user+project pair. Includes compressed summary, recent exchanges, key decisions, token usage, and last model used.

- **Tool**: A capability the Oracle can invoke. Has a name, description, parameter schema, and execution function. Scoped to specific agents (Oracle vs Librarian).

- **Subagent**: A specialized agent with its own system prompt and tool subset. Receives delegated tasks and returns results to the parent agent.

- **Prompt**: An external template file with variables for context injection. Organized by agent type and purpose.

- **Thread**: Long-term memory storage for decisions, findings, and context. Linked to projects.

- **VaultNote**: Markdown document in the user's documentation vault. Supports wikilinks, tags, and full-text search.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can ask questions and receive relevant, cited answers within 10 seconds for typical queries
- **SC-002**: Oracle successfully uses tools to gather context in 90% of queries requiring external information
- **SC-003**: Conversation context persists correctly across sessions in 100% of normal use cases
- **SC-004**: Context compression preserves key decisions and maintains conversation coherence
- **SC-005**: CLI and Web UI provide equivalent functionality for question-answering
- **SC-006**: Tool call failures are handled gracefully without crashing or hanging
- **SC-007**: System supports at least 100 concurrent users across all projects
- **SC-008**: Prompt changes can be deployed without code changes or service restarts
- **SC-009**: Subagent delegation completes successfully in 85% of applicable tasks
- **SC-010**: Users report that Oracle answers are helpful and well-sourced in 80%+ of feedback

## Assumptions

- Users have an active internet connection for LLM API calls
- External LLM APIs (OpenRouter, Google) are generally available with reasonable latency
- Projects have been indexed (CodeRAG, vault) before Oracle queries
- Users authenticate via existing HF OAuth or local mode
- Token limits and pricing follow standard LLM API conventions
- File operations are scoped to the user's project directory for security

## Dependencies

- Existing CodeRAG indexing and search functionality
- Existing vault document storage and search
- Existing thread sync infrastructure
- External LLM API access (OpenRouter or Google Gemini)
- Existing authentication system

## Out of Scope

- Training or fine-tuning custom models
- On-device/offline LLM inference
- Multi-user collaboration within the same conversation
- Voice input/output
- Mobile-native applications
- Code execution or shell command tools (security concern - may be added later with sandboxing)
