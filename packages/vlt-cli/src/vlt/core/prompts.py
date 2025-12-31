"""Prompt templates for Oracle synthesis.

T073-T074: Synthesis prompt engineering with source citation formatting.
"""

from typing import Optional


def build_synthesis_prompt(
    question: str,
    context: str,
    query_type: str = "conceptual",
    include_citations: bool = True
) -> str:
    """Build synthesis prompt for LLM.

    Args:
        question: User's natural language question
        context: Assembled context from retrievers
        query_type: Type of query (definition, references, conceptual, behavioral)
        include_citations: Whether to request source citations (default: True)

    Returns:
        Formatted prompt string for synthesis
    """
    # System instructions for different query types
    type_instructions = {
        "definition": """You are answering a code navigation query about where a symbol is defined.
Focus on providing the exact location and surrounding context. Be precise and concise.""",

        "references": """You are answering a code navigation query about where/how a symbol is used.
List all usage locations and explain the calling context. Show the relationships between components.""",

        "conceptual": """You are answering a conceptual question about how code works.
Explain the implementation, design patterns, and key concepts. Make it clear and educational.""",

        "behavioral": """You are answering a question about why code behaves a certain way.
Explain the purpose, reasoning, and historical context. Connect implementation to intent.""",

        "unknown": """You are answering a technical question about a codebase.
Provide a clear, well-structured answer based on the available context."""
    }

    system_instruction = type_instructions.get(query_type, type_instructions["unknown"])

    # Citation instructions
    citation_instruction = ""
    if include_citations:
        citation_instruction = """
CRITICAL: You MUST cite your sources for every claim. Use these citation formats:
- Code: [src/api/routes.py:42]
- Documentation: [docs/architecture.md]
- Thread history: [thread:auth-design#15]

Example:
"The authentication system uses JWT tokens [src/services/auth.py:145]. According to the design docs [docs/auth-strategy.md], we chose JWTs for their stateless nature [thread:auth-design#8]."

If you cannot find relevant information in the context for a specific part of the question, say so explicitly rather than guessing.
"""

    prompt = f"""{system_instruction}

{citation_instruction}

## Question
{question}

## Context
{context}

## Instructions
Based on the context above, answer the question thoroughly. Structure your response with:
1. A clear, direct answer to the question
2. Supporting details and explanation
3. Relevant code examples (if applicable)
4. Source citations for every claim
5. Any caveats or limitations based on available context

If the context does not contain sufficient information to answer the question completely, state what is missing and provide the best answer you can from what's available.

## Answer
"""

    return prompt


def build_no_context_response(question: str) -> str:
    """Build response when no relevant context is found.

    T077: Honest response when no context found (don't hallucinate).

    Args:
        question: User's original question

    Returns:
        Formatted response explaining no context was found
    """
    return f"""I searched for relevant context to answer your question:

**"{question}"**

However, I could not find any relevant information in:
- Code index (no matching code chunks)
- Documentation vault (no matching notes)
- Development threads (no matching history)

This could mean:
1. The code/documentation hasn't been indexed yet (run `vlt coderag init`)
2. The question uses different terminology than the codebase
3. This information genuinely doesn't exist in the indexed sources

**Suggestions:**
- Try rephrasing the question with different keywords
- Check if the relevant files have been indexed
- Search manually in the codebase with file paths or function names you know exist

I cannot provide an answer without relevant context, as I don't want to hallucinate or guess.
"""


def build_explain_trace_section(
    query_analysis: dict,
    retrieval_stats: dict,
    reranking_stats: Optional[dict] = None
) -> str:
    """Build debug trace section for --explain mode.

    Args:
        query_analysis: Dict with query type detection results
        retrieval_stats: Dict with retrieval statistics by source
        reranking_stats: Optional dict with reranking statistics

    Returns:
        Formatted trace section for debugging
    """
    trace_lines = [
        "## Debug Trace (--explain mode)",
        "",
        "### Query Analysis",
        f"- Type: {query_analysis.get('query_type', 'unknown')}",
        f"- Confidence: {query_analysis.get('confidence', 0.0):.2f}",
        f"- Extracted symbols: {', '.join(query_analysis.get('extracted_symbols', [])) or 'none'}",
        f"- Reasoning: {query_analysis.get('reasoning', 'N/A')}",
        "",
        "### Retrieval Statistics",
    ]

    # Add stats for each retrieval source
    for source_name, stats in retrieval_stats.items():
        trace_lines.append(f"- **{source_name}**: {stats.get('count', 0)} results "
                          f"(avg score: {stats.get('avg_score', 0.0):.2f})")

    # Add reranking stats if available
    if reranking_stats:
        trace_lines.extend([
            "",
            "### Reranking Statistics",
            f"- Candidates: {reranking_stats.get('candidates', 0)}",
            f"- Top-k selected: {reranking_stats.get('top_k', 0)}",
            f"- Model used: {reranking_stats.get('model', 'N/A')}",
        ])

    return "\n".join(trace_lines)


def format_citations(text: str) -> str:
    """Format citations in response text for CLI display.

    Converts citation markers like [file.py:42] to rich-formatted clickable text.

    Args:
        text: Response text with citation markers

    Returns:
        Text with formatted citations
    """
    # This is a simple implementation - could be enhanced with rich markup
    # for actual clickable links in supported terminals
    return text


def extract_citations_from_response(response_text: str) -> list[str]:
    """Extract all citations from a synthesized response.

    Args:
        response_text: Synthesized response with citation markers

    Returns:
        List of unique citations found in response
    """
    import re

    # Pattern: [file.py:123], [note/path.md], [thread:id#node]
    citation_pattern = r'\[([^\]]+)\]'

    matches = re.findall(citation_pattern, response_text)

    # Filter to only actual citations (not markdown links)
    # Citations contain : or / or #
    citations = [
        m for m in matches
        if ':' in m or '/' in m or '#' in m
    ]

    # Deduplicate while preserving order
    seen = set()
    unique_citations = []
    for citation in citations:
        if citation not in seen:
            seen.add(citation)
            unique_citations.append(citation)

    return unique_citations
