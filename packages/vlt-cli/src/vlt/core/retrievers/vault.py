"""Vault retriever for Document-MCP markdown notes.

T069: Retrieves context from Document-MCP vault using HTTP API.
Implements IRetriever interface for integration with hybrid retrieval.
"""

import logging
import os
import httpx
from typing import List, Optional
from vlt.core.retrievers.base import BaseRetriever, RetrievalResult, SourceType, RetrievalMethod
from vlt.config import Settings


logger = logging.getLogger(__name__)


class VaultRetriever(BaseRetriever):
    """Retrieves relevant markdown notes from Document-MCP vault.

    Uses the Document-MCP search API (GET /api/search?q=...) to find
    relevant markdown notes that might contain documentation or context
    related to the user's question.

    Attributes:
        vault_url: Base URL for Document-MCP instance
        settings: Settings instance with configuration
        timeout: HTTP request timeout in seconds
    """

    def __init__(
        self,
        vault_url: Optional[str] = None,
        settings: Optional[Settings] = None,
        timeout: float = 10.0
    ):
        """Initialize vault retriever.

        Args:
            vault_url: Base URL for Document-MCP (e.g., "http://localhost:8000")
            settings: Optional settings instance (uses default if None)
            timeout: HTTP request timeout in seconds (default: 10.0)
        """
        super().__init__()

        if settings is None:
            settings = Settings()

        self.settings = settings
        self.timeout = timeout

        # Load vault URL from settings or use provided value
        # Priority: argument > env var > default
        self.vault_url = vault_url or os.environ.get("VLT_VAULT_URL", "http://localhost:8000")

        self.logger.info(f"Initialized VaultRetriever with URL: {self.vault_url}")

    @property
    def name(self) -> str:
        """Get retriever name."""
        return "vault"

    @property
    def available(self) -> bool:
        """Check if vault is reachable.

        Returns:
            True if vault URL is configured (doesn't verify connectivity)
        """
        # Simple availability check - just verify URL is configured
        # Could optionally ping /api/health endpoint, but that adds latency
        return bool(self.vault_url)

    async def retrieve(self, query: str, limit: int = 20) -> List[RetrievalResult]:
        """Retrieve relevant markdown notes from vault.

        Args:
            query: Natural language question or search query
            limit: Maximum number of results to return (default: 20)

        Returns:
            List of retrieval results from vault search

        Raises:
            httpx.HTTPError: If vault API call fails
        """
        if not query.strip():
            self.logger.warning("Empty query provided to vault retriever")
            return []

        self.logger.debug(f"Searching vault for: '{query[:50]}...' (limit={limit})")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Call Document-MCP search API
                response = await client.get(
                    f"{self.vault_url}/api/search",
                    params={
                        "q": query,
                        "limit": limit
                    }
                )

                if response.status_code == 404:
                    self.logger.warning("Vault search endpoint not found (404). Is Document-MCP running?")
                    return []

                if response.status_code != 200:
                    self.logger.error(f"Vault search failed with status {response.status_code}: {response.text}")
                    return []

                data = response.json()

                # Expected response format from Document-MCP:
                # {
                #   "results": [
                #     {
                #       "path": "folder/note.md",
                #       "title": "Note Title",
                #       "snippet": "...matching text...",
                #       "score": 0.85,
                #       "updated": "2025-01-15T10:30:00Z"
                #     },
                #     ...
                #   ]
                # }

                results_list = data.get("results", [])
                self.logger.info(f"Vault search returned {len(results_list)} results")

                # Convert to RetrievalResult objects
                retrieval_results = []

                for item in results_list[:limit]:
                    # Extract fields with safe defaults
                    note_path = item.get("path", "unknown.md")
                    title = item.get("title", note_path)
                    snippet = item.get("snippet", "")
                    score = item.get("score", 0.5)  # Normalize to 0-1
                    updated = item.get("updated", "")

                    # Build full content for context
                    # Format: Title + snippet
                    content = f"# {title}\n\n{snippet}"

                    # Estimate token count (rough: 1 token ≈ 4 characters)
                    token_count = len(content) // 4

                    result = RetrievalResult(
                        content=content,
                        source_type=SourceType.VAULT,
                        source_path=note_path,
                        retrieval_method=RetrievalMethod.BM25,  # Document-MCP uses FTS5 (BM25-like)
                        score=float(score),
                        token_count=token_count,
                        metadata={
                            "note_path": note_path,
                            "title": title,
                            "snippet": snippet,
                            "updated": updated,
                            "vault_url": self.vault_url
                        }
                    )

                    retrieval_results.append(result)

                self.logger.info(f"Converted {len(retrieval_results)} vault results to RetrievalResult")
                return retrieval_results

        except httpx.TimeoutException:
            self.logger.error(f"Vault search timed out after {self.timeout}s")
            return []
        except httpx.RequestError as e:
            self.logger.error(f"Network error calling vault API: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error in vault retrieval: {e}", exc_info=True)
            return []


# Convenience function for standalone usage
async def search_vault(
    query: str,
    vault_url: Optional[str] = None,
    limit: int = 20,
    settings: Optional[Settings] = None
) -> List[RetrievalResult]:
    """Search Document-MCP vault for relevant markdown notes.

    Convenience function for standalone vault search without creating
    a retriever instance.

    Args:
        query: Natural language question or search query
        vault_url: Base URL for Document-MCP (optional)
        limit: Maximum number of results to return (default: 20)
        settings: Optional settings instance

    Returns:
        List of retrieval results from vault
    """
    retriever = VaultRetriever(vault_url=vault_url, settings=settings)
    return await retriever.retrieve(query, limit)
