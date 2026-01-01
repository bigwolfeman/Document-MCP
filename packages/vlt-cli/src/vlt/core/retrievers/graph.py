"""Graph traversal retriever for code navigation queries.

T045: Graph traversal retriever that implements IRetriever interface.
Uses code intelligence (ctags + code graph) to handle structural queries
like "where is X defined?" and "what calls Y?".
"""

import logging
import re
from typing import List, Optional
from sqlalchemy.orm import Session

from vlt.core.retrievers.base import (
    BaseRetriever,
    RetrievalResult,
    SourceType,
    RetrievalMethod,
    RetrieverError
)
from vlt.core.coderag.code_intel import CodeIntelligence, Location
from vlt.db import SessionLocal


logger = logging.getLogger(__name__)


# Query type detection patterns
DEFINITION_PATTERNS = [
    r'\bwhere\s+is\s+(\w+)\s+defined\b',
    r'\bdefinition\s+of\s+(\w+)\b',
    r'\bfind\s+(\w+)\s+definition\b',
    r'\bshow\s+me\s+(\w+)\s+definition\b',
    r'\bwhat\s+is\s+(\w+)\b',
]

REFERENCE_PATTERNS = [
    r'\bwhere\s+is\s+(\w+)\s+used\b',
    r'\bwhat\s+calls\s+(\w+)\b',
    r'\bwho\s+calls\s+(\w+)\b',
    r'\breferences\s+to\s+(\w+)\b',
    r'\busages\s+of\s+(\w+)\b',
    r'\bfind\s+(\w+)\s+references\b',
]


class GraphRetriever(BaseRetriever):
    """Graph traversal retriever for structural code queries.

    This retriever:
    1. Detects query type (definition vs reference)
    2. Uses code intelligence to find exact locations
    3. Returns precise results for navigation queries

    Attributes:
        project_id: Project identifier to scope search
        project_path: Path to project root (for ctags)
        db: Database session
        code_intel: Code intelligence interface
    """

    def __init__(
        self,
        project_id: str,
        project_path: str,
        db: Optional[Session] = None
    ):
        """Initialize graph retriever.

        Args:
            project_id: Project identifier to scope search
            project_path: Path to project root directory
            db: Optional database session (creates new if None)
        """
        self.project_id = project_id
        self.project_path = project_path
        self._db = db
        self._owns_db = db is None
        self.code_intel: Optional[CodeIntelligence] = None
        super().__init__()

    def _initialize(self) -> None:
        """Initialize code intelligence interface."""
        self.code_intel = CodeIntelligence(
            project_id=self.project_id,
            project_path=self.project_path,
            db=self.db
        )

    @property
    def name(self) -> str:
        """Get retriever name."""
        return "graph"

    @property
    def available(self) -> bool:
        """Check if retriever is available.

        Returns:
            True (code graph is always available)
        """
        return True

    @property
    def db(self) -> Session:
        """Get database session, creating if needed."""
        if self._db is None:
            self._db = SessionLocal()
            self._owns_db = True
        return self._db

    def __enter__(self):
        """Context manager entry."""
        if self._owns_db:
            self._db = SessionLocal()
        if self.code_intel is None:
            self.code_intel = CodeIntelligence(
                project_id=self.project_id,
                project_path=self.project_path,
                db=self._db
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._owns_db and self._db:
            self._db.close()

    async def retrieve(self, query: str, limit: int = 20) -> List[RetrievalResult]:
        """Retrieve results using graph traversal for structural queries.

        Args:
            query: Natural language question or search query
            limit: Maximum number of results to return (default: 20)

        Returns:
            List of retrieval results for definition/reference queries

        Raises:
            RetrieverError: If retrieval fails
        """
        if self.code_intel is None:
            self.code_intel = CodeIntelligence(
                project_id=self.project_id,
                project_path=self.project_path,
                db=self.db
            )

        try:
            # Detect query type and extract symbol
            query_type, symbol = self._detect_query_type(query)

            if query_type is None or symbol is None:
                logger.debug(f"Query not recognized as structural: {query}")
                return []

            logger.debug(f"Detected {query_type} query for symbol: {symbol}")

            # Route to appropriate handler
            if query_type == "definition":
                return await self._retrieve_definition(symbol)
            elif query_type == "reference":
                return await self._retrieve_references(symbol, limit)
            else:
                return []

        except Exception as e:
            logger.error(f"Error in graph retrieval: {e}", exc_info=True)
            raise RetrieverError(
                f"Graph retrieval failed: {str(e)}",
                retriever_name=self.name
            ) from e

    def _detect_query_type(self, query: str) -> tuple[Optional[str], Optional[str]]:
        """Detect query type and extract symbol name.

        Args:
            query: Natural language query

        Returns:
            Tuple of (query_type, symbol_name) or (None, None) if not detected
        """
        query_lower = query.lower()

        # Try definition patterns
        for pattern in DEFINITION_PATTERNS:
            match = re.search(pattern, query_lower)
            if match:
                symbol = match.group(1)
                return ("definition", symbol)

        # Try reference patterns
        for pattern in REFERENCE_PATTERNS:
            match = re.search(pattern, query_lower)
            if match:
                symbol = match.group(1)
                return ("reference", symbol)

        return (None, None)

    async def _retrieve_definition(self, symbol: str) -> List[RetrievalResult]:
        """Retrieve definition location for a symbol.

        Args:
            symbol: Symbol name to look up

        Returns:
            List containing single RetrievalResult for the definition
        """
        location = self.code_intel.find_definition(symbol)

        if location is None:
            logger.info(f"No definition found for symbol: {symbol}")
            return []

        # Convert Location to RetrievalResult
        result = self._location_to_result(
            location,
            symbol,
            source_type=SourceType.DEFINITION,
            retrieval_method=RetrievalMethod.GRAPH
        )

        return [result] if result else []

    async def _retrieve_references(
        self,
        symbol: str,
        limit: int
    ) -> List[RetrievalResult]:
        """Retrieve reference locations for a symbol.

        Args:
            symbol: Symbol name to look up
            limit: Maximum number of references to return

        Returns:
            List of RetrievalResult objects for each reference
        """
        locations = self.code_intel.find_references(symbol, limit=limit)

        if not locations:
            logger.info(f"No references found for symbol: {symbol}")
            return []

        # Convert Locations to RetrievalResults
        results = []
        for location in locations:
            result = self._location_to_result(
                location,
                symbol,
                source_type=SourceType.REFERENCE,
                retrieval_method=RetrievalMethod.GRAPH
            )
            if result:
                results.append(result)

        return results

    def _location_to_result(
        self,
        location: Location,
        symbol: str,
        source_type: SourceType,
        retrieval_method: RetrievalMethod
    ) -> Optional[RetrievalResult]:
        """Convert a Location to a RetrievalResult.

        Args:
            location: Code location
            symbol: Symbol name
            source_type: Type of source (DEFINITION or REFERENCE)
            retrieval_method: Retrieval method used

        Returns:
            RetrievalResult object or None on error
        """
        try:
            # Build content with context
            content_parts = []

            # Add header
            if source_type == SourceType.DEFINITION:
                content_parts.append(f"# Definition of {symbol}")
            else:
                content_parts.append(f"# Reference to {symbol}")

            # Add location info
            content_parts.append(f"**File**: {location.file_path}")
            content_parts.append(f"**Line**: {location.lineno}")

            if location.qualified_name:
                content_parts.append(f"**Qualified Name**: {location.qualified_name}")

            if location.kind:
                content_parts.append(f"**Kind**: {location.kind}")

            if location.signature:
                content_parts.append(f"**Signature**: {location.signature}")

            # Add code context
            if location.context:
                content_parts.append(f"\n```\n{location.context}\n```")

            content = "\n".join(content_parts)

            # Build source path
            source_path = f"{location.file_path}:{location.lineno}"

            # Metadata
            metadata = {
                "file_path": location.file_path,
                "lineno": location.lineno,
                "end_lineno": location.end_lineno,
                "kind": location.kind,
                "signature": location.signature,
                "qualified_name": location.qualified_name,
            }

            # Score: Graph results get perfect score (exact matches)
            score = 1.0

            return RetrievalResult(
                content=content,
                source_type=source_type,
                source_path=source_path,
                retrieval_method=retrieval_method,
                score=score,
                token_count=len(content.split()),
                metadata=metadata
            )

        except Exception as e:
            logger.error(f"Error converting location to result: {e}")
            return None


# Convenience functions for standalone use
async def search_definition(
    symbol: str,
    project_id: str,
    project_path: str,
    db: Optional[Session] = None
) -> List[RetrievalResult]:
    """Standalone function to find symbol definition.

    Args:
        symbol: Symbol name to look up
        project_id: Project identifier
        project_path: Path to project root
        db: Optional database session

    Returns:
        List containing single RetrievalResult for the definition
    """
    async with GraphRetriever(project_id, project_path, db) as retriever:
        return await retriever._retrieve_definition(symbol)


async def search_references(
    symbol: str,
    project_id: str,
    project_path: str,
    limit: int = 20,
    db: Optional[Session] = None
) -> List[RetrievalResult]:
    """Standalone function to find symbol references.

    Args:
        symbol: Symbol name to look up
        project_id: Project identifier
        project_path: Path to project root
        limit: Maximum number of references to return
        db: Optional database session

    Returns:
        List of RetrievalResult objects for each reference
    """
    async with GraphRetriever(project_id, project_path, db) as retriever:
        return await retriever._retrieve_references(symbol, limit)
