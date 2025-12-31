"""Context assembler for Oracle synthesis.

T071-T072: Assembles final context from multiple retrieval sources with
token budget management. Prioritizes content by relevance and type.

Priority order (research.md Section 7):
1. Exact matches (definitions)
2. Direct call sites (references)
3. Top-k code chunks (from reranking)
4. Relevant vault notes
5. Thread context
6. Repo map slice
"""

import logging
from typing import List, Optional, Dict, Any
from vlt.core.retrievers.base import RetrievalResult, SourceType


logger = logging.getLogger(__name__)


# Token estimation factor (conservative: 1 token ≈ 4 characters for code)
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    Uses conservative heuristic: 1 token ≈ 4 characters.
    This is conservative for code (which typically has more tokens per char).

    Args:
        text: Text content

    Returns:
        Estimated token count
    """
    return len(text) // CHARS_PER_TOKEN


def assemble_context(
    code_results: List[RetrievalResult],
    vault_results: List[RetrievalResult],
    thread_results: List[RetrievalResult],
    repo_map: Optional[str] = None,
    max_tokens: int = 16000,
    query_type: str = "conceptual"
) -> Dict[str, Any]:
    """Assemble final context from multiple sources with token budget.

    Follows priority order from research.md Section 7:
    1. Exact matches (definitions) - highest priority for navigation queries
    2. Direct call sites (references) - high priority for "what calls this"
    3. Top-k code chunks - core content from reranking
    4. Relevant vault notes - documentation context
    5. Thread context - development history
    6. Repo map slice - structural overview (always include some)

    Args:
        code_results: Results from code retrieval (vector, BM25, graph)
        vault_results: Results from vault search
        thread_results: Results from thread search
        repo_map: Repository map text (optional)
        max_tokens: Maximum tokens for assembled context (default: 16000)
        query_type: Type of query (affects prioritization)

    Returns:
        Dict with:
            - context: Assembled context string
            - sections: Dict of section names to content
            - token_count: Actual token count
            - max_tokens: Budget used
            - sources_included: Number of sources included
            - sources_excluded: Number of sources excluded due to budget
    """
    logger.info(
        f"Assembling context with {len(code_results)} code, {len(vault_results)} vault, "
        f"{len(thread_results)} thread results (budget: {max_tokens} tokens, type: {query_type})"
    )

    sections = {}
    token_count = 0
    sources_included = 0
    sources_excluded = 0

    # Track what we've added to avoid redundant content
    added_paths = set()

    # Reserve tokens for repo map (always include 10% for structure)
    repo_map_budget = int(max_tokens * 0.1)
    remaining_budget = max_tokens - repo_map_budget

    # Priority 1: Exact matches for definition/reference queries (15% of budget)
    if query_type in ("definition", "references"):
        definition_budget = int(remaining_budget * 0.15)
        definition_results = [r for r in code_results if r.source_type in (SourceType.DEFINITION, SourceType.REFERENCE)]

        if definition_results:
            section_text, added, excluded, tokens = _add_results_to_budget(
                results=definition_results,
                budget=definition_budget,
                section_title="## Definitions and References",
                added_paths=added_paths
            )

            if section_text:
                sections["definitions"] = section_text
                token_count += tokens
                sources_included += added
                sources_excluded += excluded
                remaining_budget -= tokens

    # Priority 2: Top-k code chunks (60% of remaining budget)
    code_budget = int(remaining_budget * 0.6)
    code_only = [r for r in code_results if r.source_type == SourceType.CODE]

    if code_only:
        section_text, added, excluded, tokens = _add_results_to_budget(
            results=code_only,
            budget=code_budget,
            section_title="## Code Context",
            added_paths=added_paths
        )

        if section_text:
            sections["code"] = section_text
            token_count += tokens
            sources_included += added
            sources_excluded += excluded
            remaining_budget -= tokens

    # Priority 3: Vault notes (20% of remaining budget)
    vault_budget = int(remaining_budget * 0.2)

    if vault_results:
        section_text, added, excluded, tokens = _add_results_to_budget(
            results=vault_results,
            budget=vault_budget,
            section_title="## Documentation",
            added_paths=added_paths
        )

        if section_text:
            sections["vault"] = section_text
            token_count += tokens
            sources_included += added
            sources_excluded += excluded
            remaining_budget -= tokens

    # Priority 4: Thread context (use remaining budget)
    if thread_results and remaining_budget > 500:  # Only if we have meaningful space
        section_text, added, excluded, tokens = _add_results_to_budget(
            results=thread_results,
            budget=remaining_budget,
            section_title="## Development History",
            added_paths=added_paths
        )

        if section_text:
            sections["threads"] = section_text
            token_count += tokens
            sources_included += added
            sources_excluded += excluded

    # Priority 5: Repo map slice (always include for structure)
    if repo_map:
        # Truncate repo map to fit budget
        truncated_map = _truncate_to_tokens(repo_map, repo_map_budget)
        map_tokens = estimate_tokens(truncated_map)

        sections["repo_map"] = f"## Codebase Structure\n\n{truncated_map}"
        token_count += map_tokens

    # Assemble final context from sections
    context_parts = []

    # Order sections by priority
    priority_order = ["definitions", "code", "vault", "threads", "repo_map"]

    for section_name in priority_order:
        if section_name in sections:
            context_parts.append(sections[section_name])

    final_context = "\n\n".join(context_parts)

    logger.info(
        f"Context assembly complete: {token_count}/{max_tokens} tokens, "
        f"{sources_included} sources included, {sources_excluded} excluded"
    )

    return {
        "context": final_context,
        "sections": sections,
        "token_count": token_count,
        "max_tokens": max_tokens,
        "sources_included": sources_included,
        "sources_excluded": sources_excluded
    }


def _add_results_to_budget(
    results: List[RetrievalResult],
    budget: int,
    section_title: str,
    added_paths: set
) -> tuple[str, int, int, int]:
    """Add results to a section within token budget.

    Args:
        results: List of retrieval results to add
        budget: Token budget for this section
        section_title: Markdown section title
        added_paths: Set of already-added source paths (mutated)

    Returns:
        Tuple of (section_text, sources_added, sources_excluded, tokens_used)
    """
    if not results:
        return "", 0, 0, 0

    section_lines = [section_title, ""]
    section_tokens = estimate_tokens(section_title) + 2  # +2 for newlines
    sources_added = 0
    sources_excluded = 0

    for result in results:
        # Skip duplicates
        if result.source_path in added_paths:
            sources_excluded += 1
            continue

        # Format result with citation
        result_text = _format_result(result)
        result_tokens = estimate_tokens(result_text)

        # Check budget
        if section_tokens + result_tokens > budget:
            logger.debug(f"Budget exhausted for section '{section_title}' at {sources_added} sources")
            sources_excluded += 1
            continue

        # Add to section
        section_lines.append(result_text)
        section_lines.append("")  # Blank line between results
        section_tokens += result_tokens + 1  # +1 for blank line

        added_paths.add(result.source_path)
        sources_added += 1

    if sources_added == 0:
        return "", 0, sources_excluded, 0

    section_text = "\n".join(section_lines)
    return section_text, sources_added, sources_excluded, section_tokens


def _format_result(result: RetrievalResult) -> str:
    """Format a retrieval result for inclusion in context.

    Args:
        result: Retrieval result to format

    Returns:
        Formatted text with citation
    """
    # Build citation
    citation = f"[{result.source_path}]"

    # Add score if high confidence
    if result.score >= 0.8:
        citation += f" (score: {result.score:.2f})"

    # Format based on source type
    if result.source_type == SourceType.CODE:
        # Code chunk format
        language = result.metadata.get("language", "")
        qualified_name = result.metadata.get("qualified_name", "")

        header = f"### {citation}"
        if qualified_name:
            header += f" - {qualified_name}"

        # Wrap content in code fence if it's not already
        content = result.content.strip()
        if not content.startswith("```"):
            content = f"```{language}\n{content}\n```"

        return f"{header}\n\n{content}"

    elif result.source_type == SourceType.VAULT:
        # Vault note format
        title = result.metadata.get("title", "")
        header = f"### {citation}"
        if title:
            header += f" - {title}"

        return f"{header}\n\n{result.content}"

    elif result.source_type == SourceType.THREAD:
        # Thread node format
        thread_id = result.metadata.get("thread_id", "")
        author = result.metadata.get("author", "")
        timestamp = result.metadata.get("timestamp", "")

        header = f"### {citation}"
        if author:
            header += f" (by {author}"
            if timestamp:
                header += f", {timestamp[:10]}"  # Just date
            header += ")"

        return f"{header}\n\n{result.content}"

    else:
        # Generic format for definitions, references
        return f"### {citation}\n\n{result.content}"


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to fit within token budget.

    Args:
        text: Text to truncate
        max_tokens: Maximum tokens allowed

    Returns:
        Truncated text (may be shorter than original)
    """
    current_tokens = estimate_tokens(text)

    if current_tokens <= max_tokens:
        return text

    # Truncate by characters (conservative)
    max_chars = max_tokens * CHARS_PER_TOKEN
    truncated = text[:max_chars]

    # Try to end at a line break for cleaner truncation
    last_newline = truncated.rfind('\n')
    if last_newline > max_chars * 0.8:  # At least 80% of budget
        truncated = truncated[:last_newline]

    return truncated + "\n\n[... truncated for token budget]"
