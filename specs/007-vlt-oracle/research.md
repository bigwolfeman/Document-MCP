# Research: Vlt Oracle Implementation

**Feature**: 007-vlt-oracle
**Date**: 2025-12-30
**Updated**: 2025-12-30 (v3 - Cost optimization patterns)
**Status**: Complete

## Summary

This document consolidates technical research for implementing the Vlt Oracle feature - a production-grade multi-source intelligent context retrieval system. The research draws from:
1. Analysis of production systems (Sourcegraph Cody, Cursor, Aider, Sweep, Bloop)
2. Best practices documentation from Qdrant, LanceDB, Qodo
3. Code intelligence protocols (LSP, SCIP, ctags)
4. **Cost optimization strategies** (lazy evaluation, delta indexing, shared context) - NEW v3

---

## 1. Code Chunking: LlamaIndex CodeSplitter (Sweep's Chunker)

### Decision: Use LlamaIndex's CodeSplitter with tree-sitter

**Rationale**: Sweep's chunker is proven at scale (2M+ lines/day) and already integrated into LlamaIndex. Tree-sitter provides language-agnostic parsing for 100+ languages.

**What Makes It Work**:
- **AST-based splitting**: Chunks at function/class boundaries, never mid-statement
- **Context enrichment**: Includes imports, class definition, signature with each chunk
- **Safe splitting**: If a function is too large, splits at logical boundaries (not mid-if/else)
- **Recursive handling**: Large files are broken into subtrees while preserving logical groupings

**Implementation**:
```python
from llama_index.core.node_parser import CodeSplitter
from tree_sitter_languages import get_parser

# Initialize with tree-sitter
parser = get_parser("python")
splitter = CodeSplitter(
    language="python",
    chunk_lines=40,  # Target lines per chunk
    chunk_lines_overlap=15,  # Overlap for context
    max_chars=1500,  # Hard limit
)

# Split code
chunks = splitter.get_nodes_from_documents([document])
```

**Context Enrichment Pattern** (Qodo's approach):
```python
def enrich_chunk(chunk, file_content, ast):
    # Include imports at top of file
    chunk.imports = extract_imports(ast)

    # Include enclosing class definition
    if chunk.is_method:
        chunk.class_context = get_class_header(chunk.enclosing_class)

    # Include full signature with types
    chunk.signature = get_full_signature(chunk.node)

    # Include docstring
    chunk.docstring = ast.get_docstring(chunk.node)

    return chunk
```

**Sources**: Qodo Blog, LanceDB CodeQA, Sweep GitHub

---

## 2. Embedding Model: qwen/qwen3-embedding-8b

### Decision: Use qwen/qwen3-embedding-8b via OpenRouter

**Rationale**:
- Code-specific embeddings outperform general models for semantic code search
- User-specified choice
- Available via OpenRouter (no self-hosting required)

**Alternatives Considered**:
- OpenAI text-embedding-3-small: Good but general-purpose
- VoyageCode-3: Excellent but expensive
- Nomic Embed Code 7B: State-of-art but requires self-hosting

**Implementation**:
```python
async def get_code_embedding(text: str) -> List[float]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            json={
                "model": "qwen/qwen3-embedding-8b",
                "input": text
            }
        )
        return response.json()["data"][0]["embedding"]
```

---

## 3. Hybrid Retrieval Architecture

### Decision: Vector + BM25 + Graph + Code Intelligence

**Rationale**: Research is unanimous - pure vector search fails for code. Production systems all use hybrid.

**Why Each Path Matters**:

| Retrieval Path | Query Type | Example |
|---------------|-----------|---------|
| **Vector** | Conceptual | "retry logic with backoff" → finds `attempt_with_delay()` |
| **BM25** | Exact match | "authenticate_user" → finds function by name |
| **Graph** | Structural | "what calls this?" → finds all call sites |
| **Code Intel** | Navigation | "where defined?" → exact file:line |

**Production Evidence**:
- Sourcegraph Cody: Keyword (Zoekt) + Embedding + Graph (SCIP)
- Cursor: Custom embedding + Turbopuffer vector DB + local context
- Bloop: Neural semantic + traditional code parsing

**Implementation Pattern**:
```python
async def hybrid_retrieve(query: str, top_k: int = 20) -> List[Result]:
    # Parallel retrieval
    results = await asyncio.gather(
        vector_search(query, top_k),
        bm25_search(query, top_k),
        graph_search(query, top_k) if is_structural_query(query) else [],
    )

    # Merge with source attribution
    merged = merge_results(results, sources=["vector", "bm25", "graph"])

    # Deduplicate by file+range
    deduped = deduplicate(merged)

    return deduped
```

**Sources**: Sourcegraph Blog, Modal Blog, Qdrant Tutorial

---

## 4. Code Intelligence: LSP/SCIP/ctags

### Decision: ctags (always-on) + Optional LSP expansion

**Rationale**:
- ctags is cheap and reliable for definitions
- LSP provides exact references but requires running language servers
- SCIP indexes can be pre-generated in CI for faster queries

### What Each Provides:

**ctags (Universal Ctags)**:
- Symbol → file:line mappings for definitions
- Fast, language-agnostic
- Aider uses this for repo map

```bash
# Generate ctags
ctags --recurse --languages=Python,TypeScript --extras=+q -f tags .
```

**LSP Protocol Methods**:
- `textDocument/definition`: Jump to symbol definition
- `textDocument/references`: Find all usages
- `textDocument/hover`: Get type info and docs
- `textDocument/documentSymbol`: Get file outline

**SCIP (Sourcegraph Code Intelligence Protocol)**:
- Persisted code intelligence (no live server needed)
- Pre-indexed definitions, references, hovers
- Supports cross-repo navigation

### Implementation Pattern:
```python
class CodeIntelligence:
    def find_definition(self, symbol: str) -> Optional[Location]:
        # 1. Try ctags (fastest)
        if location := self.ctags_index.lookup(symbol):
            return location

        # 2. Try SCIP index if available
        if self.scip_index and (location := self.scip_index.definition(symbol)):
            return location

        # 3. Fall back to graph search
        if node := self.code_graph.find_node(symbol):
            return node.location

        # 4. Last resort: semantic search
        return self.vector_search(f"definition of {symbol}")[0]

    def find_references(self, symbol: str) -> List[Location]:
        # 1. Graph edges (call sites)
        references = self.code_graph.get_callers(symbol)

        # 2. Supplement with SCIP if available
        if self.scip_index:
            references.extend(self.scip_index.references(symbol))

        return deduplicate(references)
```

**Sources**: Microsoft LSP Spec, Sourcegraph SCIP Blog, Aider ctags docs

---

## 5. Repository Map (Aider Pattern)

### Decision: Generate Aider-style repo map with graph centrality

**Rationale**:
- Aider's success validates the pattern
- LLMs need structural overview to navigate code
- Token-budgeted map fits in context

**How Aider Does It**:
1. Parse all files with tree-sitter
2. Extract top-level symbols (classes, functions)
3. Build reference graph (who calls/imports what)
4. Calculate PageRank to find most important symbols
5. Generate text map prioritizing high-centrality symbols
6. Prune to fit token budget

**Implementation**:
```python
def generate_repo_map(project_path: str, max_tokens: int = 4000) -> str:
    # 1. Parse all files
    symbols = []
    for file in glob(f"{project_path}/**/*.py"):
        ast = tree_sitter_parse(file)
        symbols.extend(extract_symbols(ast, file))

    # 2. Build reference graph
    graph = build_reference_graph(symbols)

    # 3. Calculate centrality (who is most referenced)
    centrality = nx.pagerank(graph)

    # 4. Generate map text
    lines = []
    for file, file_symbols in group_by_file(symbols):
        lines.append(f"├── {file}")
        for sym in sorted(file_symbols, key=lambda s: -centrality.get(s.name, 0)):
            if within_token_budget(lines, max_tokens):
                lines.append(f"│   ├── {sym.signature}")

    return "\n".join(lines)
```

**Output Format**:
```
src/
├── api/routes/auth.py
│   ├── class AuthRouter
│   │   ├── login(username, password) → Token
│   │   └── logout(token) → None
├── services/vault.py
│   ├── class VaultService
│   │   ├── search_notes(user_id, query) → List[Note]
│   │   └── write_note(path, content) → Note
```

**Sources**: Aider Documentation, Aider GitHub

---

## 6. Reranking Stage

### Decision: LLM-based reranking (cheap model)

**Rationale**:
- Raw hybrid results need scoring
- Cross-encoders are precise but need fine-tuning
- LLM reranking is flexible and accurate

**Options Considered**:
- Cross-encoder (ms-marco): Fast, needs training data
- LLM reranking: Flexible, uses cheap model (gpt-4o-mini)
- Cohere Rerank: Good but external API

**Implementation**:
```python
async def rerank(query: str, candidates: List[Result], top_k: int = 10) -> List[Result]:
    # Build reranking prompt
    prompt = f"""Score these code snippets for relevance to the query.
Query: {query}

Snippets:
{format_snippets(candidates)}

Return JSON array of {{index, score}} sorted by relevance (0-10 scale).
"""

    # Use cheap model
    response = await llm.complete(
        model="gpt-4o-mini",
        prompt=prompt,
        response_format={"type": "json_object"}
    )

    # Parse scores and reorder
    scores = json.loads(response)
    ranked = sort_by_scores(candidates, scores)

    return ranked[:top_k]
```

**Sources**: Sourcegraph RecSys'24 Paper, LanceDB Tutorial

---

## 7. Context Assembly

### Decision: Token-budgeted assembly with priority ordering

**Rationale**: LLM context is precious. Irrelevant content hurts more than missing content.

**Assembly Order** (highest to lowest priority):
1. **Exact matches** (definition queries)
2. **Direct call sites** (reference queries)
3. **Top-k code chunks** (from reranking)
4. **Relevant vault notes**
5. **Thread context** (dev history)
6. **Repo map slice** (structural overview)
7. **Relevant tests** (behavior explanation)

**Implementation**:
```python
def assemble_context(
    code_results: List[Result],
    vault_results: List[Result],
    thread_results: List[Result],
    repo_map: str,
    max_tokens: int = 16000
) -> str:
    sections = []
    token_count = 0

    # Priority 1: Code (most important)
    for result in code_results[:10]:
        if token_count + result.tokens < max_tokens * 0.6:
            sections.append(format_code_result(result))
            token_count += result.tokens

    # Priority 2: Vault notes
    for result in vault_results[:5]:
        if token_count + result.tokens < max_tokens * 0.8:
            sections.append(format_vault_result(result))
            token_count += result.tokens

    # Priority 3: Repo map (always include some)
    map_slice = truncate_to_tokens(repo_map, max_tokens * 0.1)
    sections.append(f"## Codebase Structure\n{map_slice}")

    # Priority 4: Thread context (if room)
    for result in thread_results[:3]:
        if token_count + result.tokens < max_tokens:
            sections.append(format_thread_result(result))
            token_count += result.tokens

    return "\n\n".join(sections)
```

**Sources**: Sourcegraph Blog, Qodo Blog

---

## 8. Production Systems Summary

| System | Chunking | Embedding | Retrieval | Code Intel | Key Insight |
|--------|----------|-----------|-----------|------------|-------------|
| **Sourcegraph Cody** | AST-based | OpenAI → own | Zoekt + Vector + SCIP | SCIP/LSIF | Pivoted away from embeddings at scale |
| **Cursor** | Custom | Custom model | Turbopuffer | Local context | 12.5% accuracy gain from custom model |
| **Aider** | tree-sitter | Minimal | Repo map + grep | ctags | LLM navigates via map, not retrieval |
| **Sweep** | CST (tree-sitter) | OpenAI | Vector | Graph | Chunker adopted by LlamaIndex |
| **Bloop** | Rust parser | OpenAI | Neural + keyword | - | GPT-4 synthesis |

**Key Takeaways**:
1. **Hybrid retrieval is non-negotiable** - every production system uses it
2. **Code intelligence beats embeddings** for navigation queries
3. **Repo map is critical** for big-picture understanding
4. **Reranking improves precision** significantly
5. **Context enrichment** prevents hallucination

---

## 9. Anti-Patterns to Avoid

### What Fails in Practice:

1. **Embedding entire files**: Too coarse, embeddings become generic
2. **Line-level chunking**: Too fine, loses context
3. **Missing context in chunks**: LLM hallucinates missing imports/classes
4. **Pure vector search**: Misses exact keyword matches
5. **Pure keyword search**: Misses semantic relationships
6. **No reranking**: Irrelevant results pollute context
7. **Large context windows as substitute**: "Lost in the middle" problem

### What to Do Instead:

1. **Function/class-level chunks** with context enrichment
2. **Hybrid retrieval** with multiple paths
3. **Rerank before synthesis**
4. **Include repo map** for structure
5. **Graceful degradation** when sources unavailable

---

## 10. Minimum Viable Implementation

For our constraints (CLI tool, SQLite, 1-10K files):

### Always-On (Cheap):
1. **ctags repo map** - Fast symbol index
2. **tree-sitter chunking** - Language-agnostic
3. **SQLite FTS5** - BM25 keyword search
4. **SQLite + numpy** - Vector storage

### On-Demand:
1. **qwen3-8b embeddings** - When indexing
2. **LLM reranking** - When querying
3. **Graph expansion** - For structural queries

### Optional Enhancement:
1. **SCIP indexes** - Pre-generated in CI
2. **LSP live** - If language server available

---

## 11. Configuration Recommendations

### vlt.toml Example:
```toml
[project]
name = "my-project"
id = "my-project"

[coderag]
include = ["src/**/*.py", "lib/**/*.py", "tests/**/*.py"]
exclude = ["**/node_modules/**", "**/__pycache__/**", "**/.git/**"]
languages = ["python", "typescript", "javascript"]

[coderag.embedding]
model = "qwen/qwen3-embedding-8b"
batch_size = 10

[coderag.repomap]
max_tokens = 4000
include_signatures = true
include_docstrings = false

[oracle]
vault_url = "http://localhost:8000"
synthesis_model = "anthropic/claude-sonnet-4"
rerank_model = "openai/gpt-4o-mini"
max_context_tokens = 16000
```

---

## 12. Cost Optimization Patterns (NEW v3)

### Decision: Lazy LLM Evaluation + Delta-Based Indexing + Shared Context

**Rationale**: LLM API costs scale with usage. Intelligent deferral and batching reduces costs by 70-90% while maintaining quality.

### 12.1 Lazy LLM Evaluation

**Problem**: Calling LLM on every write operation (thread push, file save) is wasteful when most content is never queried.

**Solution**: Generate on read, not on write.

| Operation | Old Pattern | New Pattern (Lazy) |
|-----------|-------------|-------------------|
| `vlt thread push` | Generate summary (LLM call) | Store raw content only |
| `vlt thread read` | Return cached summary | Check staleness → generate if needed |
| Oracle query | Query all threads | Query only matching threads, generate lazily |
| Embedding generation | On file save | On first query or batch commit |

**Staleness Detection Pattern**:
```python
def is_stale(thread_id: str) -> bool:
    cache = get_summary_cache(thread_id)
    if not cache:
        return True  # No cache = stale

    current_last_node = get_max_node_id(thread_id)
    return cache.last_node_id < current_last_node

def get_thread_summary(thread_id: str) -> str:
    if is_stale(thread_id):
        # Incremental: only summarize new nodes
        new_nodes = get_nodes_after(thread_id, cache.last_node_id)
        summary = generate_summary(existing_summary, new_nodes)
        update_cache(thread_id, summary, current_last_node)
    return get_cached_summary(thread_id)
```

**Cost Savings**:
- Typical project: 100 thread pushes/day, 5 reads/day
- Old: 100 LLM calls/day
- New: 5 LLM calls/day (95% reduction)

### 12.2 Delta-Based Indexing

**Problem**: Re-indexing on every file save causes:
- Excessive embedding API calls
- Database churn
- User-perceived latency

**Solution**: Queue changes, batch commit when thresholds exceeded.

**Threshold Configuration**:
```toml
[coderag.delta]
file_threshold = 5       # Commit after N files changed
line_threshold = 1000    # Commit after N total lines changed
timeout_seconds = 300    # Commit after N seconds of inactivity
jit_indexing = true      # Index queued files on-demand if they match query
```

**Just-In-Time Indexing Pattern**:
```python
async def oracle_query(question: str, project_id: str) -> OracleResponse:
    # 1. Check if query might match queued files
    queued = get_queued_files(project_id)
    matching = [f for f in queued if likely_matches(question, f.file_path)]

    # 2. JIT index matching files before query
    if matching:
        await index_files_immediately(matching)
        mark_as_indexed(matching)

    # 3. Proceed with normal retrieval
    return await standard_retrieval(question, project_id)

def likely_matches(question: str, file_path: str) -> bool:
    """Quick heuristic: does question mention anything in the file path?"""
    keywords = extract_keywords(question)
    path_parts = file_path.lower().split('/')
    return any(kw in path_parts for kw in keywords)
```

**Cost Savings**:
- Typical coding session: 50 file saves, 10 meaningful chunks
- Old: 50 embedding API calls
- New: ~3 batch commits (~15 calls) + occasional JIT (90% reduction)

### 12.3 Shared Conversation Context

**Problem**: Each MCP tool call starts fresh, losing context from prior tool calls. Agents repeat similar queries, wasting tokens.

**Solution**: Persistent conversation context across tool calls with compression.

**Context Management Pattern**:
```python
class ConversationContext:
    def __init__(self, token_budget: int = 16000, compression_threshold: float = 0.8):
        self.token_budget = token_budget
        self.compression_threshold = compression_threshold
        self.compressed_history = ""
        self.recent_exchanges = []  # Keep last N uncompressed
        self.mentioned_symbols = set()
        self.mentioned_files = set()

    def add_exchange(self, tool_name: str, input: dict, output: dict, tokens: int):
        exchange = {
            "tool": tool_name,
            "input": input,
            "output_summary": summarize_output(output),
            "tokens": tokens,
            "key_insights": extract_insights(output)
        }
        self.recent_exchanges.append(exchange)
        self.mentioned_symbols.update(extract_symbols(input, output))
        self.mentioned_files.update(extract_files(input, output))

        if self.tokens_used > self.token_budget * self.compression_threshold:
            self.compress()

    def compress(self):
        """Compress older exchanges to summary, keep recent uncompressed."""
        to_compress = self.recent_exchanges[:-5]  # Keep last 5
        self.recent_exchanges = self.recent_exchanges[-5:]

        # LLM call to compress
        summary = llm_compress(
            existing=self.compressed_history,
            new_exchanges=to_compress,
            preserve=["symbols", "files", "key insights"]
        )
        self.compressed_history = summary

    def get_context_for_tool(self) -> str:
        """Return context to prepend to tool calls."""
        return f"""## Conversation Context
{self.compressed_history}

## Recent Activity
{format_recent_exchanges(self.recent_exchanges)}

## Key Symbols Discussed: {', '.join(self.mentioned_symbols)}
## Files Referenced: {', '.join(self.mentioned_files)}
"""
```

**Cost Savings**:
- 10-tool conversation: Without context → 10 independent calls, redundant retrieval
- With shared context: Symbols/files tracked, retrieval prioritizes known context
- Compression at 80%: Long conversations stay within budget
- Estimated: 30-50% token reduction for multi-tool sessions

### 12.4 Cost Projection

**Per-Query Cost Breakdown** (optimized):

| Component | Old | Optimized | Savings |
|-----------|-----|-----------|---------|
| Embedding (query) | $0.0001 | $0.0001 | - |
| Embedding (indexing) | $0.01/save | $0.003/batch | 70% |
| Reranking (gpt-4o-mini) | $0.002 | $0.002 | - |
| Thread summaries | $0.005/push | $0.001/read | 80% |
| Synthesis | $0.015 | $0.010 (context reuse) | 33% |
| **Total per query** | ~$0.032 | ~$0.016 | **50%** |

**Target**: <$0.03/query (achieved with optimization)

### 12.5 Implementation Priority

1. **Lazy thread summaries** (highest impact, easiest)
2. **Delta-based indexing** (second highest impact)
3. **Shared conversation context** (complex, but valuable for agent use)

---

## Conclusion

All technical unknowns have been resolved. The implementation should:

1. **Use LlamaIndex CodeSplitter** with tree-sitter for chunking
2. **Embed with qwen/qwen3-embedding-8b** via OpenRouter
3. **Build hybrid indexes**: Vector + FTS5 + Graph + ctags
4. **Generate Aider-style repo map** with centrality ranking
5. **Rerank with cheap LLM** before synthesis
6. **Expose 5 MCP tools** for coding agents
7. **Fall back gracefully** when components unavailable
8. **Lazy LLM evaluation**: Generate summaries on-read, not on-write
9. **Delta-based indexing**: Batch changes, commit when threshold reached
10. **Shared conversation context**: Persistent cross-tool context with compression
