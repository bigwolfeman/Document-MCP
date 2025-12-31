# CodeRAG Subsystem

This directory contains the CodeRAG (Code Retrieval-Augmented Generation) indexing and retrieval system for the Vlt Oracle feature (007-vlt-oracle).

## Architecture Overview

The CodeRAG system provides production-grade code intelligence with hybrid retrieval:
- **Vector search** (semantic similarity using embeddings)
- **BM25 keyword search** (exact keyword matching)
- **Code graph** (import/call relationships)
- **Symbol index** (ctags-based definition lookup)
- **Repository map** (Aider-style codebase overview)

## Components

### Core Indexing Components

#### 1. **parser.py** - Tree-sitter Parser Wrapper (T020)
Language-agnostic code parsing using tree-sitter.

**Supported Languages:** Python, TypeScript, JavaScript, Go, Rust

**Key Functions:**
```python
detect_language(file_path: str) -> Optional[str]
parse_file(content: str, language: str) -> Optional[Tree]
get_node_text(node: Node, source: bytes) -> str
```

#### 2. **chunker.py** - LlamaIndex CodeSplitter (T023)
Semantic code chunking with context enrichment.

**Features:**
- Uses LlamaIndex's CodeSplitter (Sweep's chunker)
- Enriches chunks with: imports, class context, signatures, decorators, docstrings
- Makes chunks self-contained for better embedding quality

**Key Functions:**
```python
chunk_file(content: str, language: str, file_path: str) -> List[Dict[str, Any]]
```

**Chunk Structure:**
- `file_path`, `chunk_type`, `qualified_name`, `language`
- `imports`, `class_context`, `signature`, `decorators`, `docstring`, `body`
- `lineno`, `end_lineno`, `chunk_text`

#### 3. **embedder.py** - Embedding Client (T021)
Generates embeddings using qwen/qwen3-embedding-8b via OpenRouter.

**Features:**
- Async batch processing
- Rate limit handling
- Graceful degradation

**Key Functions:**
```python
async get_embedding(text: str) -> Optional[List[float]]
async get_embeddings_batch(texts: List[str], batch_size: int = 10) -> List[Optional[List[float]]]
```

#### 4. **bm25.py** - BM25 Keyword Indexer (T022)
SQLite FTS5 for keyword-based retrieval.

**Features:**
- BM25 ranking
- Porter stemming
- Query sanitization
- Project-scoped search

**Key Classes:**
```python
class BM25Indexer:
    def index_chunk(chunk_id, name, qualified_name, signature, docstring, body)
    def search_bm25(query: str, limit: int = 20) -> List[Tuple[str, float]]
    def delete_chunk(chunk_id: str)
```

#### 5. **graph.py** - Code Graph Builder (T023)
Extracts code relationships using tree-sitter.

**Node Types:** MODULE, CLASS, FUNCTION, METHOD, VARIABLE
**Edge Types:** CALLS, IMPORTS, INHERITS, USES, DECORATES

**Key Functions:**
```python
build_graph(parsed_files: Dict, project_id: str) -> Tuple[List[CodeNode], List[CodeEdge]]
```

#### 6. **ctags.py** - Universal Ctags Wrapper (T024)
Symbol definition indexing.

**Key Functions:**
```python
generate_ctags(project_path: str) -> Optional[str]
parse_ctags(tags_path: str) -> List[SymbolDefinition]
lookup_definition(name: str, tags: List[SymbolDefinition]) -> Optional[SymbolDefinition]
```

### Orchestration & Storage

#### 7. **store.py** - Database Interface (T025)
CRUD operations for all CodeRAG entities.

**Key Classes:**
```python
class CodeRAGStore:
    def save_chunks(chunks: List[Dict], project_id: str) -> int
    def save_graph(nodes: List[Dict], edges: List[Dict], project_id: str) -> tuple[int, int]
    def save_symbols(symbols: List[Dict], project_id: str) -> int
    def get_chunks_by_file(file_path: str, project_id: str) -> List[CodeChunk]
    def delete_file_data(file_path: str, project_id: str) -> int
```

**Managed Entities:**
- `CodeChunk` - Context-enriched code chunks with embeddings
- `CodeNode` - Graph nodes (symbols)
- `CodeEdge` - Graph edges (relationships)
- `SymbolDefinition` - ctags symbol definitions
- `RepoMap` - Cached repository structure maps

#### 8. **indexer.py** - Main Indexer Orchestrator (T026)
High-level indexing coordinator.

**Key Classes:**
```python
class CodeRAGIndexer:
    def __init__(project_path: Path, project_id: str)
    def index_full(force: bool = False) -> IndexerStats
    def index_changed_files() -> IndexerStats
    def get_index_status() -> Dict[str, Any]
```

**Indexing Workflow:**
1. Discover files (include/exclude patterns)
2. Filter unchanged files (content hash)
3. Parse and chunk files
4. Generate embeddings (async batch)
5. Store chunks
6. Build code graph
7. Generate ctags
8. Generate repository map
9. Index into BM25

## Usage Examples

### Full Project Indexing

```python
from pathlib import Path
from vlt.core.coderag.indexer import CodeRAGIndexer

indexer = CodeRAGIndexer(
    project_path=Path("/path/to/project"),
    project_id="my-project"
)

stats = indexer.index_full(force=False)  # Incremental
print(f"Indexed {stats.files_indexed} files")
print(f"Created {stats.chunks_created} chunks")
```

### Using the Store

```python
from vlt.core.coderag.store import CodeRAGStore

with CodeRAGStore() as store:
    chunks = store.get_chunks_by_file("src/main.py", "my-project")
    stats = store.get_project_stats("my-project")
```

### BM25 Search

```python
from vlt.core.coderag.bm25 import BM25Indexer

with BM25Indexer() as bm25:
    results = bm25.search_bm25("authenticate user", limit=10)
    for chunk_id, score in results:
        print(f"Chunk {chunk_id}: score={score}")
```

## Configuration

Via `vlt.toml`:

```toml
[coderag]
include = ["src/**/*.py", "tests/**/*.py"]
exclude = ["**/node_modules/**", "**/.git/**"]
languages = ["python", "typescript", "javascript"]

[coderag.embedding]
model = "qwen/qwen3-embedding-8b"
batch_size = 10

[coderag.repomap]
max_tokens = 4000
include_signatures = true
```

## Dependencies

**Required:**
- sqlalchemy
- httpx
- pydantic-settings

**Optional:**
- tree-sitter, tree-sitter-languages
- llama-index-core
- Universal Ctags (system binary)

Install:
```bash
pip install tree-sitter tree-sitter-languages llama-index-core
sudo apt install universal-ctags  # or: brew install universal-ctags
```

## Performance

- Indexing: ~5 min for 10K files
- Incremental: <30s for changed files
- BM25 search: <1s for 5K notes
- Embedding: Batched at 10/batch with rate limiting

## Related Files

- Spec: `/specs/007-vlt-oracle/spec.md`
- Plan: `/specs/007-vlt-oracle/plan.md`
- Models: `vlt/core/models.py`
- Config: `vlt/core/identity.py`
