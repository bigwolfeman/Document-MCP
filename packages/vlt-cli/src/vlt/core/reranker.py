"""LLM-based reranker for hybrid retrieval results.

T047: LLM-based reranking using cheap models (gpt-4o-mini via OpenRouter).
Provides optional reranking - falls back to score-based sorting if no API key.
"""

import logging
import json
from typing import List, Optional
import httpx

from vlt.core.retrievers.base import RetrievalResult
from vlt.config import Settings


logger = logging.getLogger(__name__)


class RerankerError(Exception):
    """Raised when reranking fails."""
    pass


async def rerank(
    query: str,
    candidates: List[RetrievalResult],
    top_k: int = 10,
    settings: Optional[Settings] = None
) -> List[RetrievalResult]:
    """Rerank retrieval results using LLM scoring.

    This function:
    1. Uses a cheap LLM (gpt-4o-mini) to score each candidate's relevance
    2. Prompts the LLM to rate each snippet 0-10 for the given query
    3. Reorders candidates by LLM scores
    4. Returns top-k results

    Args:
        query: Original user query
        candidates: List of retrieval results to rerank
        top_k: Number of top results to return (default: 10)
        settings: Optional settings instance (uses default if None)

    Returns:
        Reordered top-k results by LLM relevance score

    Behavior:
        - If no API key configured: falls back to score-based sort (no LLM call)
        - If LLM call fails: logs warning and falls back to score-based sort
        - Otherwise: returns LLM-reranked results
    """
    if settings is None:
        settings = Settings()

    # Fallback if no API key
    if not settings.openrouter_api_key:
        logger.info("No OpenRouter API key - falling back to score-based ranking")
        return _fallback_rerank(candidates, top_k)

    # Don't call LLM if candidates list is empty or already small
    if not candidates:
        return []

    if len(candidates) <= top_k:
        logger.debug(f"Candidates ({len(candidates)}) <= top_k ({top_k}), skipping rerank")
        return sorted(candidates, key=lambda r: r.score, reverse=True)[:top_k]

    try:
        logger.info(f"Reranking {len(candidates)} candidates with LLM for query: {query[:50]}...")

        # Build reranking prompt
        prompt = _build_rerank_prompt(query, candidates)

        # Call LLM for scoring
        response_text = await _call_llm_for_scores(prompt, settings)

        # Parse scores from response
        scores = _parse_llm_scores(response_text, len(candidates))

        # Apply scores to candidates
        for i, candidate in enumerate(candidates):
            if i < len(scores):
                # Normalize LLM score (0-10) to [0, 1] range
                candidate.score = scores[i] / 10.0

        # Sort by new scores and return top-k
        reranked = sorted(candidates, key=lambda r: r.score, reverse=True)
        logger.info(f"Reranking complete, returning top {top_k} results")
        return reranked[:top_k]

    except Exception as e:
        logger.warning(f"Reranking failed: {e}, falling back to score-based ranking")
        return _fallback_rerank(candidates, top_k)


def _fallback_rerank(
    candidates: List[RetrievalResult],
    top_k: int
) -> List[RetrievalResult]:
    """Fallback reranking using existing scores.

    Args:
        candidates: List of retrieval results
        top_k: Number of top results to return

    Returns:
        Top-k results sorted by existing score
    """
    sorted_candidates = sorted(candidates, key=lambda r: r.score, reverse=True)
    return sorted_candidates[:top_k]


def _build_rerank_prompt(query: str, candidates: List[RetrievalResult]) -> str:
    """Build LLM prompt for reranking.

    Args:
        query: User query
        candidates: List of retrieval results

    Returns:
        Formatted prompt string
    """
    snippets_text = []
    for i, candidate in enumerate(candidates):
        # Truncate content to first 300 chars to save tokens
        content_preview = candidate.content[:300]
        if len(candidate.content) > 300:
            content_preview += "..."

        snippets_text.append(f"""
{i}. Source: {candidate.source_path}
   Type: {candidate.source_type.value}
   Content:
   {content_preview}
""")

    snippets_str = "\n".join(snippets_text)

    prompt = f"""You are a code search relevance evaluator. Given a user query and code snippets, score each snippet's relevance.

Query: {query}

Snippets:
{snippets_str}

Instructions:
1. For each snippet, assign a relevance score from 0-10:
   - 10: Directly answers the query
   - 7-9: Highly relevant, contains key information
   - 4-6: Somewhat relevant, provides context
   - 1-3: Tangentially related
   - 0: Not relevant

2. Return ONLY a JSON array of scores in order (no explanation):
[score0, score1, score2, ...]

Example response: [8, 3, 9, 5, 7]
"""

    return prompt


async def _call_llm_for_scores(prompt: str, settings: Settings) -> str:
    """Call LLM API to get relevance scores.

    Args:
        prompt: Reranking prompt
        settings: Settings instance with API key

    Returns:
        Raw LLM response text

    Raises:
        RerankerError: If API call fails
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.openrouter_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "openai/gpt-4o-mini",  # Cheap model for reranking
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.0,  # Deterministic
                    "max_tokens": 500,
                }
            )

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "60"))
                raise RerankerError(f"Rate limited. Retry after {retry_after} seconds.")

            if response.status_code != 200:
                error_detail = response.text
                raise RerankerError(
                    f"LLM API returned {response.status_code}: {error_detail}"
                )

            data = response.json()

            if "choices" not in data or len(data["choices"]) == 0:
                raise RerankerError("No response from LLM")

            return data["choices"][0]["message"]["content"]

    except httpx.TimeoutException:
        raise RerankerError("LLM API request timed out")
    except httpx.RequestError as e:
        raise RerankerError(f"Network error calling LLM API: {str(e)}")


def _parse_llm_scores(response_text: str, expected_count: int) -> List[float]:
    """Parse scores from LLM response.

    Args:
        response_text: Raw LLM response
        expected_count: Expected number of scores

    Returns:
        List of parsed scores (0.0-10.0)

    Raises:
        RerankerError: If parsing fails
    """
    try:
        # Try to extract JSON array from response
        # The response might have extra text, so we look for [...]
        import re
        json_match = re.search(r'\[[\d,\s]+\]', response_text)

        if not json_match:
            raise RerankerError(f"No JSON array found in LLM response: {response_text[:100]}")

        json_str = json_match.group(0)
        scores = json.loads(json_str)

        if not isinstance(scores, list):
            raise RerankerError(f"LLM response is not a list: {type(scores)}")

        # Validate scores
        validated_scores = []
        for score in scores:
            if not isinstance(score, (int, float)):
                logger.warning(f"Invalid score type: {type(score)}, defaulting to 0")
                validated_scores.append(0.0)
            else:
                # Clamp to [0, 10] range
                clamped = max(0.0, min(10.0, float(score)))
                validated_scores.append(clamped)

        # Pad with zeros if not enough scores
        while len(validated_scores) < expected_count:
            validated_scores.append(0.0)

        # Truncate if too many scores
        if len(validated_scores) > expected_count:
            validated_scores = validated_scores[:expected_count]

        return validated_scores

    except json.JSONDecodeError as e:
        raise RerankerError(f"Failed to parse JSON from LLM response: {e}")
    except Exception as e:
        raise RerankerError(f"Error parsing LLM scores: {e}")


# Synchronous wrapper for convenience
def rerank_sync(
    query: str,
    candidates: List[RetrievalResult],
    top_k: int = 10,
    settings: Optional[Settings] = None
) -> List[RetrievalResult]:
    """Synchronous wrapper for rerank.

    Args:
        query: Original user query
        candidates: List of retrieval results to rerank
        top_k: Number of top results to return
        settings: Optional settings instance

    Returns:
        Reordered top-k results
    """
    import asyncio
    return asyncio.run(rerank(query, candidates, top_k, settings))
