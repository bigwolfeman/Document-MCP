"""CodeRAG database store for chunks, graph, and symbols.

T025: Database interface for CodeChunk, CodeNode, CodeEdge, SymbolDefinition, RepoMap.
Provides CRUD operations following existing vlt-cli database patterns.
"""

import uuid
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from vlt.core.models import (
    CodeChunk, CodeNode, CodeEdge, SymbolDefinition, RepoMap,
    ChunkType, NodeType, EdgeType
)
from vlt.db import SessionLocal
import logging

logger = logging.getLogger(__name__)


class CodeRAGStoreError(Exception):
    """Raised when database operations fail."""
    pass


class CodeRAGStore:
    """Database interface for CodeRAG entities.

    Handles persistence of code chunks, graph nodes/edges, symbols, and repo maps.
    Uses SQLAlchemy session patterns consistent with vlt-cli.
    """

    def __init__(self, db: Optional[Session] = None):
        """Initialize store with optional database session.

        Args:
            db: Optional SQLAlchemy session (creates new if None)
        """
        self._db = db
        self._owns_db = db is None

    def __enter__(self):
        if self._owns_db:
            self._db = SessionLocal()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._owns_db and self._db:
            self._db.close()

    @property
    def db(self) -> Session:
        """Get database session, creating if needed."""
        if self._db is None:
            self._db = SessionLocal()
            self._owns_db = True
        return self._db

    # ========================================================================
    # Code Chunks
    # ========================================================================

    def save_chunks(self, chunks: List[Dict[str, Any]], project_id: str) -> int:
        """Save code chunks with embeddings to database.

        Args:
            chunks: List of chunk dictionaries from chunker.chunk_file()
            project_id: Project identifier

        Returns:
            Number of chunks saved

        Raises:
            CodeRAGStoreError: If database operation fails

        Note:
            Each chunk dict should contain:
            - file_path, chunk_type, qualified_name, language
            - imports, class_context, signature, decorators, docstring, body
            - lineno, end_lineno, chunk_text
            - embedding (optional bytes), embedding_text (optional str)
        """
        try:
            saved_count = 0

            for chunk_dict in chunks:
                # Generate file hash for change tracking
                file_hash = self._compute_file_hash(chunk_dict.get('body', ''))

                # Map chunk_type string to enum
                chunk_type_str = chunk_dict.get('chunk_type', 'code')
                try:
                    chunk_type = ChunkType(chunk_type_str)
                except ValueError:
                    # Fallback for unknown types
                    chunk_type = ChunkType.FUNCTION

                # Create CodeChunk entity
                chunk = CodeChunk(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    file_path=chunk_dict['file_path'],
                    file_hash=file_hash,
                    chunk_type=chunk_type,
                    name=chunk_dict.get('qualified_name', '').split('.')[-1],  # Last part
                    qualified_name=chunk_dict.get('qualified_name', ''),
                    language=chunk_dict['language'],
                    lineno=chunk_dict.get('lineno', 0),
                    end_lineno=chunk_dict.get('end_lineno', 0),
                    imports=chunk_dict.get('imports'),
                    class_context=chunk_dict.get('class_context'),
                    signature=chunk_dict.get('signature'),
                    decorators='\n'.join(chunk_dict.get('decorators', [])) if chunk_dict.get('decorators') else None,
                    docstring=chunk_dict.get('docstring'),
                    body=chunk_dict.get('body', ''),
                    embedding=chunk_dict.get('embedding'),  # bytes or None
                    embedding_text=chunk_dict.get('embedding_text') or chunk_dict.get('chunk_text'),
                    token_count=chunk_dict.get('token_count'),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )

                self.db.add(chunk)
                saved_count += 1

            self.db.commit()
            logger.info(f"Saved {saved_count} code chunks for project {project_id}")
            return saved_count

        except SQLAlchemyError as e:
            self.db.rollback()
            raise CodeRAGStoreError(f"Failed to save chunks: {e}")

    def get_chunks_by_file(self, file_path: str, project_id: str) -> List[CodeChunk]:
        """Get all chunks for a specific file.

        Args:
            file_path: Path to the source file
            project_id: Project identifier

        Returns:
            List of CodeChunk entities
        """
        try:
            stmt = select(CodeChunk).where(
                CodeChunk.project_id == project_id,
                CodeChunk.file_path == file_path
            ).order_by(CodeChunk.lineno)

            result = self.db.scalars(stmt).all()
            return list(result)

        except SQLAlchemyError as e:
            raise CodeRAGStoreError(f"Failed to get chunks by file: {e}")

    def get_chunk_by_id(self, chunk_id: str) -> Optional[CodeChunk]:
        """Get a single chunk by ID.

        Args:
            chunk_id: Chunk identifier

        Returns:
            CodeChunk entity or None if not found
        """
        try:
            return self.db.get(CodeChunk, chunk_id)
        except SQLAlchemyError as e:
            raise CodeRAGStoreError(f"Failed to get chunk: {e}")

    def delete_file_data(self, file_path: str, project_id: str) -> int:
        """Delete all data for a specific file (for re-indexing).

        This removes chunks, graph nodes, and symbols for the file.

        Args:
            file_path: Path to the source file
            project_id: Project identifier

        Returns:
            Total number of entities deleted

        Raises:
            CodeRAGStoreError: If deletion fails
        """
        try:
            deleted_count = 0

            # Delete code chunks
            stmt = delete(CodeChunk).where(
                CodeChunk.project_id == project_id,
                CodeChunk.file_path == file_path
            )
            result = self.db.execute(stmt)
            deleted_count += result.rowcount

            # Delete code nodes
            stmt = delete(CodeNode).where(
                CodeNode.project_id == project_id,
                CodeNode.file_path == file_path
            )
            result = self.db.execute(stmt)
            deleted_count += result.rowcount

            # Delete code edges (those referencing deleted nodes)
            # This is tricky - need to delete edges where source or target is in this file
            # For simplicity, we'll delete edges where source is from this file
            # (caller relationships are less critical)
            nodes_to_delete = select(CodeNode.id).where(
                CodeNode.project_id == project_id,
                CodeNode.file_path == file_path
            )
            stmt = delete(CodeEdge).where(
                CodeEdge.source_id.in_(nodes_to_delete)
            )
            result = self.db.execute(stmt)
            deleted_count += result.rowcount

            # Delete symbol definitions
            stmt = delete(SymbolDefinition).where(
                SymbolDefinition.project_id == project_id,
                SymbolDefinition.file_path == file_path
            )
            result = self.db.execute(stmt)
            deleted_count += result.rowcount

            self.db.commit()
            logger.info(f"Deleted {deleted_count} entities for file {file_path}")
            return deleted_count

        except SQLAlchemyError as e:
            self.db.rollback()
            raise CodeRAGStoreError(f"Failed to delete file data: {e}")

    # ========================================================================
    # Code Graph
    # ========================================================================

    def save_graph(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], project_id: str) -> tuple[int, int]:
        """Save code graph nodes and edges to database.

        Args:
            nodes: List of CodeNode dicts from graph.build_graph()
            edges: List of CodeEdge dicts from graph.build_graph()
            project_id: Project identifier

        Returns:
            Tuple of (nodes_saved, edges_saved)

        Raises:
            CodeRAGStoreError: If database operation fails

        Note:
            Node dicts should have: id, file_path, node_type, name, signature, lineno, docstring
            Edge dicts should have: source_id, target_id, edge_type, lineno
        """
        try:
            nodes_saved = 0
            edges_saved = 0

            # Save nodes
            for node_dict in nodes:
                # Map node_type string to enum
                node_type_str = node_dict.get('node_type', 'function')
                try:
                    node_type = NodeType(node_type_str)
                except ValueError:
                    node_type = NodeType.FUNCTION

                node = CodeNode(
                    id=node_dict['id'],  # Qualified name
                    project_id=project_id,
                    file_path=node_dict['file_path'],
                    node_type=node_type,
                    name=node_dict['name'],
                    signature=node_dict.get('signature'),
                    lineno=node_dict.get('lineno'),
                    docstring=node_dict.get('docstring'),
                    centrality_score=None  # Will be computed later for repo map
                )

                self.db.add(node)
                nodes_saved += 1

            # Save edges
            for edge_dict in edges:
                # Map edge_type string to enum
                edge_type_str = edge_dict.get('edge_type', 'calls')
                try:
                    edge_type = EdgeType(edge_type_str)
                except ValueError:
                    edge_type = EdgeType.CALLS

                edge = CodeEdge(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    source_id=edge_dict['source_id'],
                    target_id=edge_dict['target_id'],
                    edge_type=edge_type,
                    lineno=edge_dict.get('lineno'),
                    count=1  # Default count
                )

                self.db.add(edge)
                edges_saved += 1

            self.db.commit()
            logger.info(f"Saved graph: {nodes_saved} nodes, {edges_saved} edges for project {project_id}")
            return (nodes_saved, edges_saved)

        except SQLAlchemyError as e:
            self.db.rollback()
            raise CodeRAGStoreError(f"Failed to save graph: {e}")

    def get_nodes_by_project(self, project_id: str) -> List[CodeNode]:
        """Get all graph nodes for a project.

        Args:
            project_id: Project identifier

        Returns:
            List of CodeNode entities
        """
        try:
            stmt = select(CodeNode).where(CodeNode.project_id == project_id)
            result = self.db.scalars(stmt).all()
            return list(result)
        except SQLAlchemyError as e:
            raise CodeRAGStoreError(f"Failed to get nodes: {e}")

    def get_edges_by_project(self, project_id: str) -> List[CodeEdge]:
        """Get all graph edges for a project.

        Args:
            project_id: Project identifier

        Returns:
            List of CodeEdge entities
        """
        try:
            stmt = select(CodeEdge).where(CodeEdge.project_id == project_id)
            result = self.db.scalars(stmt).all()
            return list(result)
        except SQLAlchemyError as e:
            raise CodeRAGStoreError(f"Failed to get edges: {e}")

    # ========================================================================
    # Symbol Definitions (ctags)
    # ========================================================================

    def save_symbols(self, symbols: List[Dict[str, Any]], project_id: str) -> int:
        """Save ctags symbol definitions to database.

        Args:
            symbols: List of SymbolDefinition dicts from ctags.parse_ctags()
            project_id: Project identifier

        Returns:
            Number of symbols saved

        Raises:
            CodeRAGStoreError: If database operation fails

        Note:
            Symbol dicts should have: name, file_path, lineno, kind, scope, signature, language
        """
        try:
            saved_count = 0

            for sym_dict in symbols:
                symbol = SymbolDefinition(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    name=sym_dict['name'],
                    file_path=sym_dict['file_path'],
                    lineno=sym_dict['lineno'],
                    kind=sym_dict['kind'],
                    scope=sym_dict.get('scope'),
                    signature=sym_dict.get('signature'),
                    language=sym_dict.get('language', 'unknown')
                )

                self.db.add(symbol)
                saved_count += 1

            self.db.commit()
            logger.info(f"Saved {saved_count} symbol definitions for project {project_id}")
            return saved_count

        except SQLAlchemyError as e:
            self.db.rollback()
            raise CodeRAGStoreError(f"Failed to save symbols: {e}")

    def get_symbols_by_name(self, name: str, project_id: str) -> List[SymbolDefinition]:
        """Find symbol definitions by name.

        Args:
            name: Symbol name to search for
            project_id: Project identifier

        Returns:
            List of matching SymbolDefinition entities
        """
        try:
            stmt = select(SymbolDefinition).where(
                SymbolDefinition.project_id == project_id,
                SymbolDefinition.name == name
            )
            result = self.db.scalars(stmt).all()
            return list(result)
        except SQLAlchemyError as e:
            raise CodeRAGStoreError(f"Failed to get symbols: {e}")

    # ========================================================================
    # Repository Map
    # ========================================================================

    def save_repo_map(self, repo_map: Dict[str, Any], project_id: str) -> RepoMap:
        """Save repository map to database.

        Args:
            repo_map: Repository map dict with structure:
                - scope: Optional subdirectory scope
                - map_text: The generated map text
                - token_count: Token count of map_text
                - max_tokens: Budget used
                - files_included: Number of files in map
                - symbols_included: Number of symbols in map
                - symbols_total: Total symbols before pruning
            project_id: Project identifier

        Returns:
            Saved RepoMap entity

        Raises:
            CodeRAGStoreError: If database operation fails
        """
        try:
            repo_map_entity = RepoMap(
                id=str(uuid.uuid4()),
                project_id=project_id,
                scope=repo_map.get('scope'),
                map_text=repo_map['map_text'],
                token_count=repo_map['token_count'],
                max_tokens=repo_map['max_tokens'],
                files_included=repo_map['files_included'],
                symbols_included=repo_map['symbols_included'],
                symbols_total=repo_map['symbols_total'],
                created_at=datetime.now(timezone.utc)
            )

            self.db.add(repo_map_entity)
            self.db.commit()
            self.db.refresh(repo_map_entity)

            logger.info(f"Saved repo map for project {project_id} (scope: {repo_map.get('scope', 'all')})")
            return repo_map_entity

        except SQLAlchemyError as e:
            self.db.rollback()
            raise CodeRAGStoreError(f"Failed to save repo map: {e}")

    def get_repo_map(self, project_id: str, scope: Optional[str] = None) -> Optional[RepoMap]:
        """Get most recent repository map for project.

        Args:
            project_id: Project identifier
            scope: Optional subdirectory scope

        Returns:
            RepoMap entity or None if not found
        """
        try:
            stmt = select(RepoMap).where(
                RepoMap.project_id == project_id
            )

            if scope:
                stmt = stmt.where(RepoMap.scope == scope)
            else:
                stmt = stmt.where(RepoMap.scope.is_(None))

            stmt = stmt.order_by(RepoMap.created_at.desc()).limit(1)

            return self.db.scalars(stmt).first()

        except SQLAlchemyError as e:
            raise CodeRAGStoreError(f"Failed to get repo map: {e}")

    # ========================================================================
    # Utility
    # ========================================================================

    def get_project_stats(self, project_id: str) -> Dict[str, int]:
        """Get indexing statistics for a project.

        Args:
            project_id: Project identifier

        Returns:
            Dict with counts: chunks, nodes, edges, symbols
        """
        try:
            stats = {}

            # Count chunks
            stmt = select(CodeChunk).where(CodeChunk.project_id == project_id)
            stats['chunks'] = len(self.db.scalars(stmt).all())

            # Count nodes
            stmt = select(CodeNode).where(CodeNode.project_id == project_id)
            stats['nodes'] = len(self.db.scalars(stmt).all())

            # Count edges
            stmt = select(CodeEdge).where(CodeEdge.project_id == project_id)
            stats['edges'] = len(self.db.scalars(stmt).all())

            # Count symbols
            stmt = select(SymbolDefinition).where(SymbolDefinition.project_id == project_id)
            stats['symbols'] = len(self.db.scalars(stmt).all())

            return stats

        except SQLAlchemyError as e:
            raise CodeRAGStoreError(f"Failed to get stats: {e}")

    def _compute_file_hash(self, content: str) -> str:
        """Compute MD5 hash of file content for change detection.

        Args:
            content: File content string

        Returns:
            32-character hex MD5 hash
        """
        return hashlib.md5(content.encode('utf-8')).hexdigest()


# ============================================================================
# Convenience Functions
# ============================================================================

def save_chunks(chunks: List[Dict[str, Any]], project_id: str, db: Optional[Session] = None) -> int:
    """Standalone function to save code chunks."""
    with CodeRAGStore(db) as store:
        return store.save_chunks(chunks, project_id)


def save_graph(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], project_id: str, db: Optional[Session] = None) -> tuple[int, int]:
    """Standalone function to save code graph."""
    with CodeRAGStore(db) as store:
        return store.save_graph(nodes, edges, project_id)


def save_symbols(symbols: List[Dict[str, Any]], project_id: str, db: Optional[Session] = None) -> int:
    """Standalone function to save symbol definitions."""
    with CodeRAGStore(db) as store:
        return store.save_symbols(symbols, project_id)


def get_chunks_by_file(file_path: str, project_id: str, db: Optional[Session] = None) -> List[CodeChunk]:
    """Standalone function to get chunks by file."""
    with CodeRAGStore(db) as store:
        return store.get_chunks_by_file(file_path, project_id)


def delete_file_data(file_path: str, project_id: str, db: Optional[Session] = None) -> int:
    """Standalone function to delete file data."""
    with CodeRAGStore(db) as store:
        return store.delete_file_data(file_path, project_id)
