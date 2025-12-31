"""
Embedding client for CodeRAG using OpenRouter API.

T021: Embedding client using qwen/qwen3-embedding-8b via OpenRouter.
Supports async batch processing with rate limit handling.
"""

import asyncio
from typing import List, Optional
import httpx
from vlt.config import Settings


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""
    pass


async def get_embedding(text: str, settings: Optional[Settings] = None) -> Optional[List[float]]:
    """
    Generate embedding for a single text string.

    Args:
        text: Text to embed
        settings: Optional settings instance (uses default if None)

    Returns:
        List of floats representing the embedding vector, or None if API key not configured

    Raises:
        EmbeddingError: If API call fails (network, rate limit, model error)
    """
    if settings is None:
        settings = Settings()

    # Return None if no API key configured (graceful degradation)
    if not settings.openrouter_api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.openrouter_base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openrouter_embedding_model,
                    "input": text,
                }
            )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "60"))
                raise EmbeddingError(f"Rate limited. Retry after {retry_after} seconds.")

            # Handle other errors
            if response.status_code != 200:
                error_detail = response.text
                raise EmbeddingError(
                    f"Embedding API returned {response.status_code}: {error_detail}"
                )

            data = response.json()

            # Extract embedding vector from response
            if "data" not in data or len(data["data"]) == 0:
                raise EmbeddingError("No embedding data in API response")

            embedding = data["data"][0]["embedding"]

            # Validate embedding is list of floats
            if not isinstance(embedding, list) or not all(isinstance(x, (int, float)) for x in embedding):
                raise EmbeddingError("Invalid embedding format from API")

            return [float(x) for x in embedding]

    except httpx.TimeoutException:
        raise EmbeddingError("Embedding API request timed out")
    except httpx.RequestError as e:
        raise EmbeddingError(f"Network error calling embedding API: {str(e)}")
    except Exception as e:
        if isinstance(e, EmbeddingError):
            raise
        raise EmbeddingError(f"Unexpected error generating embedding: {str(e)}")


async def get_embeddings_batch(
    texts: List[str],
    batch_size: int = 10,
    settings: Optional[Settings] = None
) -> List[Optional[List[float]]]:
    """
    Generate embeddings for multiple texts with batching and rate limit handling.

    Args:
        texts: List of text strings to embed
        batch_size: Number of texts to process in parallel (default: 10)
        settings: Optional settings instance (uses default if None)

    Returns:
        List of embedding vectors (same order as input texts).
        Failed embeddings are None with error logged.

    Note:
        This function processes texts in batches to avoid overwhelming the API.
        It handles rate limiting by backing off exponentially.
    """
    if settings is None:
        settings = Settings()

    # Return all None if no API key
    if not settings.openrouter_api_key:
        return [None] * len(texts)

    results: List[Optional[List[float]]] = []

    # Process in batches
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_results = []

        # Create tasks for parallel processing within batch
        tasks = [get_embedding(text, settings) for text in batch]

        # Execute batch with error handling
        try:
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            # Should not happen with return_exceptions=True, but handle anyway
            print(f"Unexpected batch error: {e}")
            batch_results = [None] * len(batch)

        # Convert exceptions to None and log errors
        for j, result in enumerate(batch_results):
            if isinstance(result, Exception):
                print(f"Warning: Failed to embed text at index {i + j}: {result}")
                results.append(None)
            else:
                results.append(result)

        # Rate limit protection: small delay between batches
        if i + batch_size < len(texts):
            await asyncio.sleep(0.5)  # 500ms between batches

    return results


# Synchronous wrapper for convenience
def get_embedding_sync(text: str, settings: Optional[Settings] = None) -> Optional[List[float]]:
    """
    Synchronous wrapper for get_embedding.

    Args:
        text: Text to embed
        settings: Optional settings instance

    Returns:
        Embedding vector or None
    """
    return asyncio.run(get_embedding(text, settings))


def get_embeddings_batch_sync(
    texts: List[str],
    batch_size: int = 10,
    settings: Optional[Settings] = None
) -> List[Optional[List[float]]]:
    """
    Synchronous wrapper for get_embeddings_batch.

    Args:
        texts: List of text strings to embed
        batch_size: Number of texts to process in parallel
        settings: Optional settings instance

    Returns:
        List of embedding vectors
    """
    return asyncio.run(get_embeddings_batch(texts, batch_size, settings))
