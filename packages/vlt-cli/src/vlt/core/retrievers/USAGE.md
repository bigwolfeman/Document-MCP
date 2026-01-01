# Hybrid Retrieval Usage Guide

This document explains how to use the hybrid retrieval system for the Vlt Oracle feature.

## Quick Start

### Basic Hybrid Retrieval

```python
from vlt.core.retrievers import hybrid_retrieve

# Perform hybrid retrieval with all methods (vector, BM25, graph)
results = await hybrid_retrieve(
    query="How does authentication work in this project?",
    project_id="my-project",
    project_path="/path/to/project",
    top_k=10,
    use_reranking=True
)

# Process results
for result in results:
    print(f"Source: {result.source_path}")
    print(f"Score: {result.score}")
    print(f"Method: {result.retrieval_method.value}")
    print(f"Content: {result.content[:200]}...")
    print("---")
```

### Synchronous Version

```python
from vlt.core.retrievers import hybrid_retrieve_sync

# Same as above but synchronous
results = hybrid_retrieve_sync(
    query="Where is UserService defined?",
    project_id="my-project",
    project_path="/path/to/project",
    top_k=5
)
```

## Individual Retrieval Methods

### Vector Search Only

```python
from vlt.core.retrievers import retrieve_vector_only

# Semantic similarity search
results = await retrieve_vector_only(
    query="retry logic with exponential backoff",
    project_id="my-project",
    limit=20
)
```

### BM25 Keyword Search Only

```python
from vlt.core.retrievers import retrieve_bm25_only

# Exact keyword matching
results = await retrieve_bm25_only(
    query="authenticate_user",
    project_id="my-project",
    limit=20
)
```

### Graph Traversal Only

```python
from vlt.core.retrievers import retrieve_graph_only

# Structural queries (definitions, references)
results = await retrieve_graph_only(
    query="where is authenticate_user defined?",
    project_id="my-project",
    project_path="/path/to/project",
    limit=20
)
```

## Using Individual Retrievers

### Vector Retriever

```python
from vlt.core.retrievers import VectorRetriever
from vlt.config import Settings

settings = Settings()
retriever = VectorRetriever(
    project_id="my-project",
    settings=settings
)

results = await retriever.retrieve(
    query="database connection pooling",
    limit=10
)
```

### BM25 Retriever

```python
from vlt.core.retrievers import BM25Retriever

retriever = BM25Retriever(project_id="my-project")

results = await retriever.retrieve(
    query="login validation",
    limit=10
)
```

### Graph Retriever

```python
from vlt.core.retrievers import GraphRetriever

retriever = GraphRetriever(
    project_id="my-project",
    project_path="/path/to/project"
)

# Detects query type automatically
results = await retriever.retrieve(
    query="what calls process_payment?",
    limit=10
)
```

## Custom Retriever Combinations

```python
from vlt.core.retrievers import (
    VectorRetriever,
    BM25Retriever,
    hybrid_retrieve
)

# Use only vector and BM25 (skip graph)
custom_retrievers = [
    VectorRetriever(project_id="my-project"),
    BM25Retriever(project_id="my-project"),
]

results = await hybrid_retrieve(
    query="error handling patterns",
    project_id="my-project",
    project_path="/path/to/project",
    retrievers=custom_retrievers,
    top_k=15
)
```

## Reranking

### With Reranking (Default)

```python
# Reranking is enabled by default
results = await hybrid_retrieve(
    query="user authentication flow",
    project_id="my-project",
    project_path="/path/to/project",
    use_reranking=True  # Default
)
```

### Without Reranking

```python
# Skip LLM reranking, use score-based sorting
results = await hybrid_retrieve(
    query="user authentication flow",
    project_id="my-project",
    project_path="/path/to/project",
    use_reranking=False
)
```

### Direct Reranking

```python
from vlt.core.reranker import rerank

# Get results from any source
results = await retrieve_bm25_only(
    query="api endpoints",
    project_id="my-project"
)

# Rerank them
reranked = await rerank(
    query="api endpoints",
    candidates=results,
    top_k=5
)
```

## Working with Results

### Accessing Result Data

```python
for result in results:
    # Basic info
    print(f"Source: {result.source_path}")  # "path/to/file.py:42"
    print(f"Type: {result.source_type.value}")  # "code", "definition", "reference"
    print(f"Method: {result.retrieval_method.value}")  # "vector", "bm25", "graph", "hybrid"
    print(f"Score: {result.score}")  # 0.0-1.0
    print(f"Tokens: {result.token_count}")

    # Content
    print(f"Content:\n{result.content}")

    # Metadata (varies by source type)
    if result.source_type == SourceType.CODE:
        print(f"File: {result.metadata['file_path']}")
        print(f"Line: {result.metadata['lineno']}")
        print(f"Function: {result.metadata['qualified_name']}")
        print(f"Language: {result.metadata['language']}")
```

### Filtering Results by Source Type

```python
from vlt.core.retrievers import SourceType

# Get only code chunk results
code_results = [
    r for r in results
    if r.source_type == SourceType.CODE
]

# Get only definition results
definition_results = [
    r for r in results
    if r.source_type == SourceType.DEFINITION
]
```

### Filtering by Retrieval Method

```python
from vlt.core.retrievers import RetrievalMethod

# Get only vector search results
vector_results = [
    r for r in results
    if r.retrieval_method == RetrievalMethod.VECTOR
]

# Get hybrid results (found by multiple methods)
hybrid_results = [
    r for r in results
    if r.retrieval_method == RetrievalMethod.HYBRID
]
```

## Merging Results

```python
from vlt.core.retrievers import (
    VectorRetriever,
    BM25Retriever,
    merge_results
)

# Get results from multiple retrievers
vector = VectorRetriever(project_id="my-project")
bm25 = BM25Retriever(project_id="my-project")

vector_results = await vector.retrieve("authentication")
bm25_results = await bm25.retrieve("authentication")

# Merge and deduplicate
merged = merge_results([vector_results, bm25_results])

# Results are now:
# 1. Deduplicated by (file_path, lineno)
# 2. Scores averaged for duplicates
# 3. Sorted by combined score
# 4. Tagged with HYBRID method if from multiple sources
```

## Error Handling

### Graceful Degradation

```python
from vlt.core.retrievers import hybrid_retrieve

# If vector retriever is unavailable (no API key),
# hybrid_retrieve will still use BM25 and graph
results = await hybrid_retrieve(
    query="database migrations",
    project_id="my-project",
    project_path="/path/to/project"
)
# Only available retrievers will run
```

### Safe Retrieval

```python
from vlt.core.retrievers import VectorRetriever

retriever = VectorRetriever(project_id="my-project")

# retrieve_safe() catches exceptions and returns []
results = await retriever.retrieve_safe("query")

# vs retrieve() which raises exceptions
try:
    results = await retriever.retrieve("query")
except RetrieverError as e:
    print(f"Retrieval failed: {e}")
```

## Configuration

### Using Custom Settings

```python
from vlt.config import Settings
from vlt.core.retrievers import VectorRetriever

# Custom settings
settings = Settings(
    openrouter_api_key="your-key",
    openrouter_embedding_model="qwen/qwen3-embedding-8b"
)

retriever = VectorRetriever(
    project_id="my-project",
    settings=settings
)
```

### Database Sessions

```python
from vlt.db import SessionLocal
from vlt.core.retrievers import BM25Retriever

# Share database session across retrievers
with SessionLocal() as db:
    retriever = BM25Retriever(project_id="my-project", db=db)
    results = await retriever.retrieve("query")
```

## Performance Tips

1. **Use reranking judiciously**: Reranking adds latency and cost. Disable for simple queries.

2. **Adjust top_k**: Request more results than needed (e.g., 40) before reranking down to top 10.

3. **Skip unavailable retrievers**: Vector search requires API key. BM25 and graph work offline.

4. **Cache results**: Store results for repeated queries to avoid re-retrieval.

5. **Use appropriate retrieval methods**:
   - Definitions/references → Graph retriever
   - Exact terms → BM25
   - Conceptual queries → Vector
   - Unsure → Hybrid (all methods)

## Integration with Oracle

The hybrid retrieval system is designed to be used by the Oracle orchestrator:

```python
from vlt.core.retrievers import hybrid_retrieve

async def oracle_query(question: str, project_id: str, project_path: str):
    # Step 1: Retrieve relevant code
    code_results = await hybrid_retrieve(
        query=question,
        project_id=project_id,
        project_path=project_path,
        top_k=20,
        use_reranking=True
    )

    # Step 2: Assemble context from results
    context = "\n\n".join([r.content for r in code_results[:10]])

    # Step 3: Generate answer with LLM
    # (implementation in oracle orchestrator)
    ...
```
