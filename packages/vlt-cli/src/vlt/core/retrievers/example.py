"""Example retriever implementation demonstrating the IRetriever protocol.

This is a reference implementation showing how to create a concrete retriever
that conforms to the IRetriever protocol and inherits from BaseRetriever.
"""

from typing import List
from .base import BaseRetriever, RetrievalResult, SourceType, RetrievalMethod


class ExampleRetriever(BaseRetriever):
    """Example retriever that returns mock results.

    This demonstrates the minimal implementation required for a retriever:
    1. Inherit from BaseRetriever
    2. Implement async retrieve() method
    3. Implement name property
    4. Optionally override available property and _initialize() method

    Usage:
        retriever = ExampleRetriever()
        results = await retriever.retrieve("How does auth work?", limit=10)
    """

    def _initialize(self) -> None:
        """Initialize the retriever.

        This is called automatically by BaseRetriever.__init__().
        Use it to load indexes, check dependencies, etc.
        """
        self.logger.info("Initializing example retriever")
        # In a real implementation, you might:
        # - Check if required indexes exist
        # - Load configuration
        # - Verify API keys
        # - Connect to databases

    @property
    def name(self) -> str:
        """Return the retriever name."""
        return "example"

    @property
    def available(self) -> bool:
        """Check if this retriever is ready to use.

        In a real implementation, you might check:
        - Does the index file exist?
        - Are API credentials configured?
        - Are required dependencies installed?
        """
        return True

    async def retrieve(self, query: str, limit: int = 20) -> List[RetrievalResult]:
        """Retrieve mock results for demonstration.

        Args:
            query: Natural language question or search query
            limit: Maximum number of results to return

        Returns:
            List of mock retrieval results
        """
        self.logger.debug(f"Retrieving results for query: {query}")

        # In a real implementation, you would:
        # 1. Parse/embed the query
        # 2. Search your index (vector, BM25, graph, etc.)
        # 3. Score and rank results
        # 4. Return top-k results

        # For this example, just return mock data
        mock_results = [
            RetrievalResult(
                content="def authenticate(username: str, password: str) -> Token:\n    \"\"\"Authenticate user and return JWT token.\"\"\"\n    ...",
                source_type=SourceType.CODE,
                source_path="src/auth.py:15",
                retrieval_method=RetrievalMethod.VECTOR,
                score=0.95,
                token_count=50,
                metadata={
                    "file_path": "src/auth.py",
                    "chunk_type": "function",
                    "qualified_name": "authenticate",
                    "lineno": 15,
                    "language": "python",
                    "signature": "def authenticate(username: str, password: str) -> Token"
                }
            ),
            RetrievalResult(
                content="# Authentication Flow\n\nThe system uses JWT tokens for authentication...",
                source_type=SourceType.VAULT,
                source_path="docs/authentication.md",
                retrieval_method=RetrievalMethod.BM25,
                score=0.87,
                token_count=120,
                metadata={
                    "note_path": "docs/authentication.md",
                    "title": "Authentication Flow",
                    "snippet": "The system uses JWT tokens...",
                    "updated": "2025-12-30T10:00:00Z"
                }
            )
        ]

        # Respect the limit parameter
        return mock_results[:limit]
