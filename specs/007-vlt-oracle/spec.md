# Feature Specification: Vlt Oracle - Multi-Source Intelligent Context Retrieval

**Feature Branch**: `007-vlt-oracle`
**Created**: 2025-12-30
**Updated**: 2025-12-30 (v3 - Shared context, lazy LLM, delta indexing)
**Status**: Draft
**Input**: User description: "A powerful tool extending Claude Code's harness with multi-source knowledge retrieval. Integrates vlt-cli threads, Document-MCP markdown vault, and a production-grade CodeRAG system with hybrid retrieval, LSP-driven context expansion, and repo map generation. Exposes tools via CLI and MCP for AI coding agents."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask Oracle via CLI (Priority: P1)

An AI agent (Claude Code) needs to understand how authentication works in a project it's unfamiliar with. Instead of exhausting its context window reading every file, it runs `vlt oracle "How does authentication work in this project?"` and receives a synthesized answer drawing from code, documentation, and historical development context.

**Why this priority**: This is the core value proposition - enabling AI agents to query a unified knowledge base without context window bloat. Without this, the entire feature has no purpose.

**Independent Test**: Can be fully tested by running the oracle command against a project with indexed code, documentation, and vlt threads. Delivers immediate value by answering complex project questions.

**Acceptance Scenarios**:

1. **Given** a project with indexed code, markdown notes, and vlt threads, **When** an AI agent runs `vlt oracle "How does authentication work?"`, **Then** the system returns a markdown-formatted answer with relevant code snippets, documentation excerpts, and historical context, including source citations.

2. **Given** a question with no relevant context in any knowledge source, **When** an AI agent runs `vlt oracle "What is the meaning of life?"`, **Then** the system responds honestly that no relevant project context was found rather than hallucinating.

3. **Given** a valid question, **When** the oracle command is run, **Then** the response includes clickable/copyable source citations (file paths, note paths, thread IDs) for each piece of evidence used.

4. **Given** a query like "Where is UserService used?", **When** the oracle runs, **Then** the system uses LSP/code intelligence to find all references (not just embedding similarity) and includes call sites in the response.

---

### User Story 2 - CodeRAG Indexing with Hybrid Pipeline (Priority: P1)

A project maintainer wants the oracle to answer code-specific questions. They run `vlt coderag init` to index their codebase, which creates:
- Vector embeddings for semantic search (using qwen/qwen3-embedding-8b)
- BM25/keyword index for exact matches
- Import/call graph for structural queries
- Repository map (Aider-style) for codebase overview
- ctags index for fast symbol lookup

**Why this priority**: Without robust code indexing, the oracle cannot answer code-related questions effectively. The hybrid approach is essential - production systems confirm pure vector search fails for code.

**Independent Test**: Can be tested by running coderag init, then directly querying with `vlt coderag search "function that handles user login"`. Should return results from both semantic and keyword search.

**Acceptance Scenarios**:

1. **Given** a project with a `vlt.toml` file specifying include/exclude patterns, **When** the maintainer runs `vlt coderag init`, **Then** the system:
   - Parses all matching files using tree-sitter (language-agnostic)
   - Extracts context-enriched chunks (imports, class definition, signature, body, docstring)
   - Generates embeddings using qwen/qwen3-embedding-8b
   - Builds BM25 index for keyword search
   - Constructs import/call graph
   - Generates repository map
   - Runs ctags for symbol index

2. **Given** an indexed codebase, **When** the maintainer runs `vlt coderag status`, **Then** the system displays: files indexed, chunks created, vector index size, BM25 index size, graph nodes/edges, repo map token count, last update time.

3. **Given** a source file that has been modified since last indexing, **When** incremental indexing runs, **Then** only the changed file is re-processed (using content hash comparison).

---

### User Story 3 - Repository Map for Codebase Overview (Priority: P1)

An AI agent needs to understand the overall structure of a codebase before diving into specific questions. The system generates an Aider-style repository map - a condensed view of all files, classes, and functions with their signatures.

**Why this priority**: The repo map is critical for "big picture" questions and helps the LLM navigate the codebase efficiently. Aider's success validates this pattern.

**Independent Test**: Run `vlt coderag map` and verify it produces a navigable outline of the codebase that fits within reasonable token limits.

**Acceptance Scenarios**:

1. **Given** an indexed codebase, **When** `vlt coderag map` is run, **Then** the system outputs a structured map showing: file paths, top-level classes/functions, their signatures, and key relationships.

2. **Given** a repo map that would exceed token limits, **When** generating the map, **Then** the system uses graph centrality analysis to prioritize the most important/referenced symbols and prunes less important ones.

3. **Given** a query context, **When** assembling oracle context, **Then** a relevant slice of the repo map is included to help the LLM understand where retrieved chunks fit in the larger codebase.

---

### User Story 4 - LSP-Driven Context Expansion (Priority: P1)

When answering queries like "Where is X defined?" or "What calls this function?", the system uses Language Server Protocol (LSP) or persisted code intelligence (SCIP/ctags) to provide exact answers rather than relying solely on embedding similarity.

**Why this priority**: Embeddings are fuzzy; LSP is exact. For navigation queries (definition, references, usages), code intelligence provides dramatically better results than semantic search alone.

**Independent Test**: Query "Where is UserService defined?" and verify the system returns the exact file:line, not just semantically similar chunks.

**Acceptance Scenarios**:

1. **Given** a query containing "where is X defined", **When** the oracle processes it, **Then** the system:
   - Identifies this as a definition query
   - Uses ctags/SCIP index to find the exact definition location
   - Returns the precise file:line with surrounding context

2. **Given** a query containing "where is X used" or "what calls X", **When** the oracle processes it, **Then** the system:
   - Uses the call graph or LSP references to find all usages
   - Returns call sites with surrounding context

3. **Given** a query about a type error or diagnostic, **When** the oracle processes it, **Then** the system can retrieve relevant LSP diagnostics and type information to explain the issue.

---

### User Story 5 - Hybrid Retrieval with Reranking (Priority: P1)

The oracle uses three parallel retrieval paths (vector, BM25, graph) and then reranks results before synthesis. This ensures both semantic matches and exact keyword matches are captured.

**Why this priority**: Production systems (Sourcegraph, Cursor, Bloop) all use hybrid retrieval. Pure vector search misses exact matches; pure keyword misses semantic relationships.

**Independent Test**: Query for a specific function name and verify it appears in results (keyword), then query for a concept and verify semantically related code appears (vector).

**Acceptance Scenarios**:

1. **Given** a query with an exact function name like "authenticate_user", **When** retrieval runs, **Then** the BM25/keyword path finds exact matches even if embedding similarity is low.

2. **Given** a conceptual query like "retry logic with backoff", **When** retrieval runs, **Then** the vector path finds semantically related code like `attempt_with_exponential_delay()` even without keyword overlap.

3. **Given** results from all retrieval paths, **When** reranking runs, **Then** a cross-encoder or LLM-based reranker scores each candidate and selects the top-k most relevant for synthesis.

---

### User Story 6 - MCP Tools for Coding Agents (Priority: P1)

Claude Code and other AI coding agents need MCP tools to interact with the oracle and code intelligence. The MCP server exposes tools for asking questions, searching code, finding definitions/references, and viewing the repo map.

**Why this priority**: The primary use case is AI agents using these tools during coding sessions. MCP is the integration point.

**Independent Test**: Configure Claude Code with the MCP server and verify all tools work from within the agent.

**Acceptance Scenarios**:

1. **Given** an MCP-connected agent, **When** it calls `ask_oracle(question)`, **Then** it receives a synthesized answer with source citations.

2. **Given** an MCP-connected agent, **When** it calls `search_code(query)`, **Then** it receives ranked code chunks from hybrid search.

3. **Given** an MCP-connected agent, **When** it calls `find_definition(symbol)`, **Then** it receives the exact definition location from code intelligence.

4. **Given** an MCP-connected agent, **When** it calls `find_references(symbol)`, **Then** it receives all usage locations from the call graph or LSP.

5. **Given** an MCP-connected agent, **When** it calls `get_repo_map(scope?)`, **Then** it receives the repository structure map (optionally scoped to a subdirectory).

---

### User Story 7 - Ask Oracle via Web UI (Priority: P2)

A human developer working in the Document-MCP web interface wants to ask questions about the project without leaving the browser. They type a question in a chat panel and receive a streaming response with clickable source citations.

**Why this priority**: Extends oracle access to the web UI for human users. Important for adoption but depends on the core oracle functionality (P1) being complete.

**Independent Test**: Can be tested by opening the web UI, typing a question in the oracle chat panel, and verifying the response streams in with working citation links.

**Acceptance Scenarios**:

1. **Given** an authenticated user on the Document-MCP web UI, **When** they type a question in the oracle chat panel and press enter, **Then** the response streams in with visible progress indicators ("Searching vault...", "Searching code...", etc.).

2. **Given** an oracle response with source citations, **When** the user clicks a citation link, **Then** the UI navigates to the source (opens note in viewer, shows code file, or displays thread).

3. **Given** an ongoing oracle conversation, **When** the user asks follow-up questions, **Then** the conversation context is maintained for more relevant answers.

---

### User Story 8 - Oracle Session Logging (Priority: P3)

An AI agent wants its oracle conversations logged for future reference. Each oracle invocation automatically creates or appends to a dated vlt thread, enabling future sessions to reference past Q&A and decisions.

**Why this priority**: Enables long-term memory and audit trail. Valuable but not required for core oracle functionality.

**Independent Test**: Can be tested by running multiple oracle queries, then reading the `oracle-session-YYYY-MM-DD` thread to verify Q&A pairs are logged.

**Acceptance Scenarios**:

1. **Given** an oracle query, **When** the query completes, **Then** both the question and answer are logged to an `oracle-session-YYYY-MM-DD` thread with proper author attribution.

2. **Given** existing oracle session threads, **When** the Librarian runs, **Then** oracle threads are summarized like any other vlt thread.

---

### User Story 9 - Source Filtering and Explain Mode (Priority: P3)

An AI agent wants to restrict oracle search to specific knowledge sources or see detailed retrieval traces for debugging.

**Why this priority**: Power-user features for targeted queries and debugging.

**Acceptance Scenarios**:

1. **Given** the oracle command with `--source=code`, **When** the query runs, **Then** only code index results are included.

2. **Given** the oracle command with `--explain`, **When** the query runs, **Then** the output shows: all retrieval paths used, raw results with scores, reranking decisions, and final context assembly.

---

### User Story 10 - Tests and Git Context (Priority: P3)

For queries about behavior or recent changes, the oracle includes relevant tests and git history as high-signal context.

**Why this priority**: Tests often explain expected behavior better than implementation code. Git blame/history helps with "why was this changed?" questions.

**Acceptance Scenarios**:

1. **Given** a query about expected behavior of a function, **When** retrieval runs, **Then** the system boosts relevant test files (`test_*.py`, `*.spec.ts`) in ranking.

2. **Given** a query about recent changes or regressions, **When** retrieval runs, **Then** the system can include `git blame` output and recent commit messages for relevant files.

---

### User Story 11 - Shared Conversation Context (Priority: P1)

All oracle tools (ask_oracle, search_code, find_definition, find_references, get_repo_map) share a single running conversation context. This enables the LLM to build understanding across multiple tool calls without redundant context fetching.

**Why this priority**: Without shared context, each tool call starts fresh, losing valuable conversation history and forcing repetitive explanations. This is the foundation for efficient multi-turn interactions.

**Independent Test**: Call `find_definition("UserService")`, then `find_references("UserService")`, then `ask_oracle("How does UserService interact with the database?")` - verify the conversation builds on previous context.

**Acceptance Scenarios**:

1. **Given** an oracle session with prior tool calls, **When** a new tool is invoked, **Then** the new tool has access to the conversation history and can reference prior results.

2. **Given** a conversation context approaching token limits, **When** the context exceeds a threshold (e.g., 80% of budget), **Then** the system compresses older exchanges while preserving key insights and recent context.

3. **Given** a compressed conversation, **When** the user asks about something from compressed history, **Then** the system can still provide accurate information (key facts were preserved during compression).

4. **Given** multiple MCP tool calls in sequence, **When** any tool returns results, **Then** those results are added to the shared conversation context for subsequent tools to reference.

---

### User Story 12 - Lazy LLM Evaluation (Priority: P1)

The system follows a "lazy evaluation" philosophy for LLM calls - computations happen when results are needed, not when data changes. This applies to summaries, embeddings, and other LLM-generated artifacts.

**Why this priority**: Eager LLM calls (e.g., regenerating summaries on every push) waste API costs and add latency. Most writes are never read; lazy evaluation ensures we only pay for what we use.

**Independent Test**: Push 10 thoughts to a vlt thread, verify no LLM calls are made. Then read the thread, verify summary is generated on-demand.

**Acceptance Scenarios**:

1. **Given** a `vlt thread push` operation, **When** the push completes, **Then** NO summary regeneration or embedding generation occurs (data is stored raw).

2. **Given** a thread with un-summarized nodes, **When** `vlt thread read` or oracle references the thread, **Then** summaries are generated on-demand and cached for future reads.

3. **Given** stale summaries (new nodes since last summary), **When** the thread is read, **Then** the system detects staleness and regenerates incrementally (only processing new nodes).

4. **Given** an oracle query, **When** vlt threads are retrieved, **Then** only threads that match the query have their summaries generated/refreshed.

---

### User Story 13 - Delta-Based Index Commits (Priority: P1)

CodeRAG indexing batches changes and only commits to indexes when a meaningful delta is reached. This prevents excessive reindexing from frequent small changes.

**Why this priority**: Reindexing on every file save is wasteful. Developers often save frequently during editing. Delta-based commits amortize indexing cost across multiple changes.

**Independent Test**: Modify 3 files in quick succession, verify only 1 batch index operation occurs.

**Acceptance Scenarios**:

1. **Given** file changes detected, **When** the total delta is below threshold (e.g., <5 files or <1000 lines), **Then** changes are queued but NOT committed to indexes.

2. **Given** queued changes that reach the delta threshold, **When** threshold is crossed, **Then** all queued changes are batch-committed to indexes in one operation.

3. **Given** queued changes that haven't reached threshold, **When** a configurable timeout expires (e.g., 5 minutes), **Then** queued changes are committed regardless of size.

4. **Given** an explicit `vlt coderag sync --force` command, **When** executed, **Then** all queued changes are immediately committed regardless of delta.

5. **Given** an oracle query, **When** there are uncommitted changes to relevant files, **Then** those specific files are indexed on-demand before the query (just-in-time indexing).

---

### Edge Cases

- What happens when one knowledge source is unavailable (e.g., CodeRAG not initialized)? System should degrade gracefully, querying available sources and noting which sources were skipped.
- What happens when LSP/code intelligence is not available for a language? Fall back to ctags for definitions, AST-based call graph for references, and semantic search for the rest.
- How does the system handle very large codebases (>10K files)? Use metadata filtering (file path, language) to scope searches before running full retrieval.
- What happens when the embedding model API is unreachable? Fall back to BM25-only search with a warning.
- How does the system handle monorepos with multiple languages? Index each language with tree-sitter, use language metadata for filtering, unified search across all.

## Requirements *(mandatory)*

### Functional Requirements

**Oracle Core**
- **FR-001**: System MUST accept natural language questions and return synthesized answers from multiple knowledge sources.
- **FR-002**: System MUST query four knowledge sources in parallel: markdown vault (Document-MCP), code index (CodeRAG vector+BM25), code graph, and development threads (vlt).
- **FR-003**: System MUST deduplicate, merge, and rerank results from all sources before synthesis.
- **FR-004**: System MUST include source citations in every response (file paths with line numbers, note paths, thread IDs).
- **FR-005**: System MUST respond honestly when no relevant context is found rather than generating hallucinated answers.
- **FR-006**: System MUST include a relevant slice of the repository map in context for structural understanding.

**CodeRAG Indexing - Hybrid Pipeline**
- **FR-007**: System MUST parse source code files using tree-sitter for language-agnostic AST extraction.
- **FR-008**: System MUST use LlamaIndex's CodeSplitter (Sweep's chunker) for semantic chunk extraction.
- **FR-009**: System MUST enrich each chunk with context: imports, class definition, function signature, decorators, docstring, and body.
- **FR-010**: System MUST generate vector embeddings using qwen/qwen3-embedding-8b model.
- **FR-011**: System MUST build a BM25/keyword index (SQLite FTS5) for exact match retrieval.
- **FR-012**: System MUST build an import/call graph to capture code relationships.
- **FR-013**: System MUST generate a repository map (Aider-style) showing files, classes, functions, and signatures.
- **FR-014**: System MUST run ctags (Universal Ctags) to build a symbol definition index.
- **FR-015**: System MUST respect include/exclude patterns from project configuration.
- **FR-016**: System MUST support incremental indexing using content hash comparison.

**Code Intelligence (LSP/SCIP)**
- **FR-017**: System MUST detect "definition" queries and use ctags/SCIP for exact lookup.
- **FR-018**: System MUST detect "references/usages" queries and use call graph or LSP for exact lookup.
- **FR-019**: System SHOULD support persisted SCIP indexes for fast, deterministic code navigation.
- **FR-020**: System MUST fall back gracefully when code intelligence is unavailable for a language.

**Retrieval Architecture**
- **FR-021**: System MUST perform parallel retrieval: vector search, BM25 search, graph traversal.
- **FR-022**: System MUST merge results from all retrieval paths with source attribution.
- **FR-023**: System MUST apply a reranking stage (cross-encoder or LLM-based) to select top-k results.
- **FR-024**: System MUST support metadata filtering by file path, language, and file type.

**CLI Interface**
- **FR-025**: System MUST expose `vlt oracle "question"` command for CLI access.
- **FR-026**: System MUST expose `vlt coderag init` command to initialize all indexes.
- **FR-027**: System MUST expose `vlt coderag status` command to display index health.
- **FR-028**: System MUST expose `vlt coderag map` command to view/regenerate the repository map.
- **FR-029**: System MUST expose `vlt coderag search "query"` for direct code search.
- **FR-030**: System MUST support `--source`, `--explain`, and `--json` flags.

**MCP Tools for Coding Agents**
- **FR-031**: System MUST expose `ask_oracle` MCP tool for synthesized Q&A.
- **FR-032**: System MUST expose `search_code` MCP tool for hybrid code search.
- **FR-033**: System MUST expose `find_definition` MCP tool for symbol definition lookup.
- **FR-034**: System MUST expose `find_references` MCP tool for symbol usage lookup.
- **FR-035**: System MUST expose `get_repo_map` MCP tool for codebase structure overview.

**Web UI**
- **FR-036**: System MUST provide a chat panel in the web UI for oracle queries.
- **FR-037**: System MUST stream oracle responses for perceived responsiveness.
- **FR-038**: System MUST render source citations as clickable links that navigate to the source.

**Session Logging**
- **FR-039**: System MUST log oracle Q&A pairs to dated vlt threads (`oracle-session-YYYY-MM-DD`).
- **FR-040**: System MUST attribute logged entries with appropriate author (agent ID or "user").

**Shared Conversation Context**
- **FR-041**: System MUST maintain a shared conversation context across all MCP tool calls within a session.
- **FR-042**: System MUST allow tool results to reference and build upon prior tool results in the same session.
- **FR-043**: System MUST compress conversation context when it exceeds 80% of the token budget, preserving key insights.
- **FR-044**: System MUST preserve recent context (last N exchanges) uncompressed during compression.
- **FR-045**: System MUST store compressed conversation summaries for retrieval of historical context.

**Lazy LLM Evaluation**
- **FR-046**: System MUST NOT call LLM APIs during write operations (`vlt thread push`, file saves).
- **FR-047**: System MUST generate summaries on-demand when threads are read or queried.
- **FR-048**: System MUST cache generated summaries and embeddings for reuse.
- **FR-049**: System MUST detect stale cached artifacts (new data since generation) and regenerate incrementally.
- **FR-050**: System MUST track "last_summarized_node_id" to enable incremental summarization.

**Delta-Based Indexing**
- **FR-051**: System MUST queue file changes instead of immediately reindexing.
- **FR-052**: System MUST batch-commit queued changes when delta threshold is reached (configurable: default 5 files or 1000 lines).
- **FR-053**: System MUST auto-commit queued changes after timeout (configurable: default 5 minutes).
- **FR-054**: System MUST support force-commit via `vlt coderag sync --force`.
- **FR-055**: System MUST perform just-in-time indexing for uncommitted files when they match an oracle query.
- **FR-056**: System MUST expose delta queue status in `vlt coderag status`.

### Key Entities

- **OracleQuery**: A natural language question with optional source filters, explain flag, and scope.
- **RetrievalResult**: A single piece of evidence from any retrieval path, including content, source type, source path, relevance score, retrieval method, and metadata.
- **OracleResponse**: The synthesized answer plus a list of source citations, repo map slice, and optional retrieval traces.
- **OracleConversation**: Shared context window across all tool calls in a session, with conversation history, compressed summaries, and token tracking.
- **CodeChunk**: A context-enriched semantic unit extracted from source code (imports, class context, signature, body, docstring) with its embedding vector.
- **CodeGraph**: Nodes (symbols) and edges (calls, imports, inherits) representing code relationships.
- **RepoMap**: A condensed structural view of the codebase (files → symbols → signatures) with importance ranking.
- **SymbolIndex**: ctags-based index mapping symbol names to definition locations.
- **SCIPIndex**: Persisted code intelligence data for definitions, references, and hovers (optional).
- **IndexDeltaQueue**: Pending file changes awaiting batch commit to indexes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can receive an oracle response within 15 seconds for typical questions against a 1,000-file codebase.
- **SC-002**: Oracle responses include relevant context from all available sources at least 85% of the time (improved from 80% due to hybrid retrieval).
- **SC-003**: CodeRAG initialization completes within 5 minutes for a 10,000-file codebase.
- **SC-004**: Incremental code indexing processes changed files within 30 seconds of detection.
- **SC-005**: Cost per oracle query remains below $0.03 using tiered model strategy (adjusted for reranking).
- **SC-006**: AI agents using the oracle can complete context-gathering tasks with 60% fewer tool calls compared to manual file reading (improved from 50% due to MCP tools).
- **SC-007**: 95% of "where is X defined?" queries return the correct file:line (code intelligence precision).
- **SC-008**: 90% of source citations in oracle responses link to genuinely relevant content.
- **SC-009**: System handles 10 concurrent oracle queries without degradation.
- **SC-010**: Repository map generation completes within 30 seconds for a 5,000-file codebase.
- **SC-011**: Lazy evaluation reduces LLM API calls by 70% compared to eager evaluation (write-time summarization).
- **SC-012**: Delta-based indexing reduces embedding API calls by 50% compared to immediate reindexing.
- **SC-013**: Conversation context compression preserves 90% of relevant information (measured by answer quality on compressed vs full context).
- **SC-014**: Multi-turn oracle sessions (5+ tool calls) complete within 60 seconds total.

## Assumptions

- The vlt-cli tool is installed and configured with an OpenRouter API key.
- Document-MCP backend is running and accessible for vault search API calls.
- Users have appropriate permissions to read codebase files being indexed.
- Tree-sitter parsers are available for project languages (Python, TypeScript, JavaScript, Go, Rust covered).
- Universal Ctags is installed for symbol indexing.
- Network connectivity is available for embedding and LLM API calls.

## Dependencies

- **vlt-cli**: Existing thread storage, semantic search, and Librarian infrastructure.
- **Document-MCP**: Existing vault search API (`/api/search`) and web UI components.
- **LlamaIndex**: CodeSplitter for chunking, vector store abstractions.
- **tree-sitter**: Language-agnostic parsing (via tree-sitter Python bindings).
- **Universal Ctags**: Symbol definition indexing.
- **OpenRouter API**: For qwen/qwen3-embedding-8b embeddings and LLM synthesis.
- **SQLite FTS5**: For BM25 keyword search (already in Document-MCP).

## Out of Scope

- Real-time code indexing via filesystem watchers (manual/scheduled refresh only for MVP).
- Full LSP server integration (use persisted indexes instead; LSP is optional enhancement).
- SCIP index generation (can use pre-generated indexes if available, but not required).
- Multi-project oracle queries (one project context at a time).
- Voice input for oracle queries.
- Oracle query suggestions/autocomplete.
