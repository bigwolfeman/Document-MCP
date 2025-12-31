"""Code intelligence layer for Oracle feature.

T039-T041: Unified interface for code navigation queries.
Implements fallback chain: ctags → graph → semantic search.
"""

import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from vlt.core.models import CodeNode, CodeEdge, SymbolDefinition as SymbolDefinitionModel, EdgeType
from vlt.core.coderag.ctags import SymbolDefinition, load_ctags_index, query_ctags
from vlt.db import SessionLocal

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Location:
    """Code location with context."""
    file_path: str
    lineno: int
    end_lineno: Optional[int]
    context: str  # Surrounding code lines
    kind: Optional[str]  # function, class, method, etc.
    signature: Optional[str] = None  # Function/method signature
    qualified_name: Optional[str] = None  # Full qualified name


# ============================================================================
# T039 - Definition Lookup with Fallback Chain
# ============================================================================

def find_definition(
    symbol: str,
    project_id: str,
    project_path: str,
    db: Optional[Session] = None
) -> Optional[Location]:
    """Find symbol definition using fallback chain.

    Fallback order:
    1. ctags (fastest, most reliable for definitions)
    2. Code graph (database lookup)
    3. Semantic search (TODO: not implemented yet)

    Args:
        symbol: Symbol name to look up
        project_id: Project identifier
        project_path: Root directory of the project
        db: Optional database session

    Returns:
        Location of the definition, or None if not found
    """
    if not symbol:
        logger.warning("Empty symbol name provided to find_definition")
        return None

    logger.debug(f"Finding definition for symbol: {symbol}")

    # Fallback 1: Try ctags (fastest)
    ctags_result = _find_definition_ctags(symbol, project_id, project_path)
    if ctags_result:
        logger.debug(f"Found definition in ctags: {ctags_result.file_path}:{ctags_result.lineno}")
        return ctags_result

    # Fallback 2: Try code graph (database)
    graph_result = _find_definition_graph(symbol, project_id, db)
    if graph_result:
        logger.debug(f"Found definition in graph: {graph_result.file_path}:{graph_result.lineno}")
        return graph_result

    # Fallback 3: Semantic search (not implemented yet)
    # This would query the vector store for semantically similar chunks
    logger.debug(f"No definition found for symbol: {symbol}")
    return None


def _find_definition_ctags(
    symbol: str,
    project_id: str,
    project_path: str
) -> Optional[Location]:
    """Find definition using ctags index.

    Args:
        symbol: Symbol name to look up
        project_id: Project identifier
        project_path: Root directory of the project

    Returns:
        Location of the definition, or None if not found
    """
    try:
        # Load ctags index
        tags = load_ctags_index(project_id, project_path)
        if not tags:
            logger.debug("No ctags index available")
            return None

        # Query for the symbol
        matches = query_ctags(symbol, tags, exact=False)
        if not matches:
            logger.debug(f"No ctags matches for symbol: {symbol}")
            return None

        # Use the first match (most relevant)
        match = matches[0]

        # Read surrounding context from file
        context = _read_file_context(
            match.file_path,
            match.lineno,
            context_lines=5,
            project_path=project_path
        )

        return Location(
            file_path=match.file_path,
            lineno=match.lineno,
            end_lineno=None,  # ctags doesn't provide end line
            context=context,
            kind=match.kind,
            signature=match.signature,
            qualified_name=match.name
        )

    except Exception as e:
        logger.error(f"Error finding definition in ctags: {e}")
        return None


def _find_definition_graph(
    symbol: str,
    project_id: str,
    db: Optional[Session] = None
) -> Optional[Location]:
    """Find definition using code graph.

    Args:
        symbol: Symbol name to look up
        project_id: Project identifier
        db: Optional database session

    Returns:
        Location of the definition, or None if not found
    """
    owns_db = db is None
    if owns_db:
        db = SessionLocal()

    try:
        # Query CodeNode table for matching symbols
        # Try exact match first
        stmt = select(CodeNode).where(
            CodeNode.project_id == project_id,
            CodeNode.name == symbol
        )
        result = db.scalars(stmt).first()

        # If no exact match, try qualified name match
        if not result:
            stmt = select(CodeNode).where(
                CodeNode.project_id == project_id,
                CodeNode.id.like(f"%{symbol}")  # Suffix match
            )
            result = db.scalars(stmt).first()

        if not result:
            logger.debug(f"No graph node found for symbol: {symbol}")
            return None

        # Read surrounding context from file
        context = _read_file_context(
            result.file_path,
            result.lineno or 0,
            context_lines=5
        )

        return Location(
            file_path=result.file_path,
            lineno=result.lineno or 0,
            end_lineno=None,
            context=context,
            kind=result.node_type.value,
            signature=result.signature,
            qualified_name=result.id
        )

    except Exception as e:
        logger.error(f"Error finding definition in graph: {e}")
        return None

    finally:
        if owns_db and db:
            db.close()


# ============================================================================
# T040 - Reference Lookup Using Graph
# ============================================================================

def find_references(
    symbol: str,
    project_id: str,
    limit: int = 20,
    db: Optional[Session] = None
) -> List[Location]:
    """Find all references to a symbol using code graph.

    Uses CodeEdge table to find all call sites and usages.

    Args:
        symbol: Symbol name to look up
        project_id: Project identifier
        limit: Maximum number of references to return
        db: Optional database session

    Returns:
        List of Locations where the symbol is referenced
    """
    if not symbol:
        logger.warning("Empty symbol name provided to find_references")
        return []

    logger.debug(f"Finding references for symbol: {symbol}")

    owns_db = db is None
    if owns_db:
        db = SessionLocal()

    try:
        # First, find the node(s) matching the symbol
        stmt = select(CodeNode).where(
            CodeNode.project_id == project_id,
            CodeNode.name == symbol
        )
        nodes = db.scalars(stmt).all()

        # Also try qualified name match
        if not nodes:
            stmt = select(CodeNode).where(
                CodeNode.project_id == project_id,
                CodeNode.id.like(f"%{symbol}")
            )
            nodes = db.scalars(stmt).all()

        if not nodes:
            logger.debug(f"No nodes found for symbol: {symbol}")
            return []

        # Collect all qualified names
        target_ids = [node.id for node in nodes]

        # Find all edges pointing to these nodes (incoming edges = references)
        stmt = select(CodeEdge).where(
            CodeEdge.project_id == project_id,
            CodeEdge.target_id.in_(target_ids),
            CodeEdge.edge_type.in_([EdgeType.CALLS, EdgeType.USES])
        ).limit(limit)

        edges = db.scalars(stmt).all()

        if not edges:
            logger.debug(f"No references found for symbol: {symbol}")
            return []

        # Convert edges to locations
        locations = []
        for edge in edges:
            # Get the source node (caller)
            source_node = db.get(CodeNode, edge.source_id)
            if not source_node:
                continue

            # Read context around the call site
            context = _read_file_context(
                source_node.file_path,
                edge.lineno or source_node.lineno or 0,
                context_lines=3
            )

            locations.append(Location(
                file_path=source_node.file_path,
                lineno=edge.lineno or source_node.lineno or 0,
                end_lineno=None,
                context=context,
                kind="reference",
                signature=None,
                qualified_name=source_node.id
            ))

        logger.info(f"Found {len(locations)} references for symbol: {symbol}")
        return locations

    except Exception as e:
        logger.error(f"Error finding references: {e}")
        return []

    finally:
        if owns_db and db:
            db.close()


# ============================================================================
# T041 - Unified Code Intelligence Interface
# ============================================================================

class CodeIntelligence:
    """Unified interface for code intelligence queries.

    Encapsulates ctags, graph, and semantic fallback for:
    - Definition lookup
    - Reference lookup
    - Type information (optional)
    """

    def __init__(self, project_id: str, project_path: str, db: Optional[Session] = None):
        """Initialize code intelligence for a project.

        Args:
            project_id: Project identifier
            project_path: Root directory of the project
            db: Optional database session (will create if None)
        """
        self.project_id = project_id
        self.project_path = project_path
        self._db = db
        self._owns_db = db is None

        # Lazy-load ctags cache
        self._ctags_cache: Optional[List[SymbolDefinition]] = None

    def __enter__(self):
        if self._owns_db:
            self._db = SessionLocal()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._owns_db and self._db:
            self._db.close()

    @property
    def db(self) -> Session:
        """Get database session."""
        if self._db is None:
            self._db = SessionLocal()
            self._owns_db = True
        return self._db

    def find_definition(self, symbol: str) -> Optional[Location]:
        """Find symbol definition using fallback chain.

        Args:
            symbol: Symbol name to look up

        Returns:
            Location of the definition, or None if not found
        """
        return find_definition(symbol, self.project_id, self.project_path, self.db)

    def find_references(self, symbol: str, limit: int = 20) -> List[Location]:
        """Find all references to a symbol.

        Args:
            symbol: Symbol name to look up
            limit: Maximum number of references to return

        Returns:
            List of Locations where the symbol is referenced
        """
        return find_references(symbol, self.project_id, limit, self.db)

    def get_type_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get type information for a symbol (optional enhancement).

        This is a placeholder for future LSP integration.

        Args:
            symbol: Symbol name to look up

        Returns:
            Dict with type information, or None if not available
        """
        # TODO: Implement LSP-based type lookup
        logger.debug("get_type_info not yet implemented")
        return None

    def _load_ctags_cache(self) -> List[SymbolDefinition]:
        """Lazy-load ctags index into cache.

        Returns:
            List of symbol definitions
        """
        if self._ctags_cache is None:
            self._ctags_cache = load_ctags_index(self.project_id, self.project_path)
        return self._ctags_cache


# ============================================================================
# Helper Functions
# ============================================================================

def _read_file_context(
    file_path: str,
    lineno: int,
    context_lines: int = 5,
    project_path: Optional[str] = None
) -> str:
    """Read surrounding context from a file.

    Args:
        file_path: Path to the file (relative or absolute)
        lineno: Line number (1-indexed)
        context_lines: Number of lines before/after to include
        project_path: Optional project root for resolving relative paths

    Returns:
        String containing the context lines
    """
    try:
        # Resolve path
        if project_path and not Path(file_path).is_absolute():
            full_path = Path(project_path) / file_path
        else:
            full_path = Path(file_path)

        if not full_path.exists():
            logger.warning(f"File not found for context: {full_path}")
            return ""

        # Read file lines
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        # Calculate range
        start_line = max(0, lineno - context_lines - 1)
        end_line = min(len(lines), lineno + context_lines)

        # Extract context
        context_lines_text = lines[start_line:end_line]

        # Format with line numbers
        formatted_lines = []
        for i, line in enumerate(context_lines_text, start=start_line + 1):
            marker = ">>>" if i == lineno else "   "
            formatted_lines.append(f"{marker} {i:4d} | {line.rstrip()}")

        return "\n".join(formatted_lines)

    except Exception as e:
        logger.error(f"Error reading file context from {file_path}:{lineno}: {e}")
        return ""
