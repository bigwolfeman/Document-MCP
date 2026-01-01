# Research: SQLite Vector Search Strategy

## Decision
**Use `sqlite-vec` (successor to `sqlite-vss`) or standard SQLite with separate vector handling via `numpy` if extension support is complex.**

**Selected Approach: `sqlite-vec`**
We will prioritize using `sqlite-vec` if a pre-compiled Python wheel is available and reliable for the target environment (Linux). If not, we will fall back to a "Hybrid" approach where vectors are stored as BLOBs in SQLite, and a simple in-memory index (using `numpy` or `scikit-learn`) is built at startup or query time for the specific thread/project context.

Given the scale of "Thoughts" (likely thousands, not millions per project), an exact brute-force search using `numpy` is extremely fast and avoids complex extension dependencies.

**Refined Decision**: **Standard SQLite + Numpy (Brute Force) for v1.**
Rationale:
1.  **Zero Dependency Hell**: No need to worry about compiling C extensions for SQLite on the user's machine.
2.  **Performance**: For <100k vectors, `numpy.dot` is sub-millisecond.
3.  **Portability**: Works everywhere Python works.
4.  **Complexity**: Much lower than managing `sqlite-vec` loading.

## Rationale
- **Simplicity**: The constitution values simplicity. Adding a compiled extension adds deployment friction.
- **Scale**: Agents work in projects. A project having >100k active thought nodes is a "good problem to have" but unlikely for v1.
- **Maintenance**: Pure Python + Standard SQL is easier to maintain.

## Alternatives Considered
- **sqlite-vss/sqlite-vec**: Powerful, but installation can be tricky across platforms without Docker.
- **ChromaDB/Qdrant**: Too heavy. Introduces a separate server process or complex dependency chain.
- **PGVector**: Requires Postgres, violates "Local First" / "Simplicity" for a CLI tool.

## Conclusion
We will implement a `VectorService` in `vlt-core` that:
1.  Stores embeddings as `BLOB` (serialized bytes) in the `nodes` table.
2.  Performs search by loading relevant vectors (filtered by project/thread) into memory and calculating Cosine Similarity using `numpy`.
