"""Query type detection for Oracle feature.

T042: Detects query intent to route to appropriate code intelligence path.
Uses simple keyword matching (no LLM needed) for fast classification.
"""

import re
import logging
from enum import Enum
from typing import Optional, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ============================================================================
# Query Types
# ============================================================================

class QueryType(Enum):
    """Type of query for routing to appropriate handler."""
    DEFINITION = "definition"          # "Where is X defined?"
    REFERENCES = "references"          # "What calls X?", "Where is X used?"
    CONCEPTUAL = "conceptual"          # "How does X work?", "What does X do?"
    BEHAVIORAL = "behavioral"          # "Why does X happen?", "What's the purpose of X?"
    UNKNOWN = "unknown"                # Unclassified query


@dataclass
class QueryAnalysis:
    """Result of query analysis."""
    query_type: QueryType
    confidence: float  # 0.0 to 1.0
    extracted_symbols: List[str]  # Symbol names extracted from query
    reasoning: str  # Why this classification


# ============================================================================
# T042 - Query Type Detector
# ============================================================================

def analyze_query(question: str) -> QueryAnalysis:
    """Analyze query to determine type and extract symbols.

    Uses keyword pattern matching for fast, deterministic classification.
    No LLM calls - optimized for speed.

    Args:
        question: Natural language question

    Returns:
        QueryAnalysis with type, confidence, and extracted symbols
    """
    if not question or not question.strip():
        return QueryAnalysis(
            query_type=QueryType.UNKNOWN,
            confidence=0.0,
            extracted_symbols=[],
            reasoning="Empty query"
        )

    question_lower = question.lower().strip()

    # Try each classification pattern in priority order
    # Definition queries (highest priority for code navigation)
    definition_result = _detect_definition_query(question_lower)
    if definition_result:
        return definition_result

    # Reference queries (high priority for code navigation)
    reference_result = _detect_reference_query(question_lower)
    if reference_result:
        return reference_result

    # Behavioral queries (medium priority)
    behavioral_result = _detect_behavioral_query(question_lower)
    if behavioral_result:
        return behavioral_result

    # Conceptual queries (default for most questions)
    conceptual_result = _detect_conceptual_query(question_lower)
    if conceptual_result:
        return conceptual_result

    # Fallback to unknown
    return QueryAnalysis(
        query_type=QueryType.UNKNOWN,
        confidence=0.3,
        extracted_symbols=_extract_symbols(question),
        reasoning="No clear pattern match"
    )


# ============================================================================
# Pattern Detectors
# ============================================================================

def _detect_definition_query(question: str) -> Optional[QueryAnalysis]:
    """Detect queries asking for symbol definitions.

    Patterns:
    - "where is X defined"
    - "where can I find X"
    - "show me the definition of X"
    - "what file contains X"
    - "locate X"
    """
    # Definition patterns (exact phrases)
    definition_patterns = [
        r"where\s+is\s+(\w+)\s+defined",
        r"where\s+(?:can|do)\s+(?:i|we)\s+find\s+(\w+)",
        r"(?:show|find|locate)\s+(?:me\s+)?(?:the\s+)?definition\s+of\s+(\w+)",
        r"what\s+file\s+contains\s+(?:the\s+)?(?:definition\s+of\s+)?(\w+)",
        r"locate\s+(?:the\s+)?(?:definition\s+of\s+)?(\w+)",
        r"find\s+(?:the\s+)?(?:class|function|method)\s+(\w+)",
        r"where\s+(?:is|can\s+i\s+find)\s+(?:the\s+)?(?:class|function|method)\s+(\w+)",
    ]

    for pattern in definition_patterns:
        match = re.search(pattern, question)
        if match:
            symbol = match.group(1) if match.groups() else None
            symbols = [symbol] if symbol else _extract_symbols(question)

            return QueryAnalysis(
                query_type=QueryType.DEFINITION,
                confidence=0.9,
                extracted_symbols=symbols,
                reasoning=f"Matched definition pattern: '{pattern}'"
            )

    # Weaker definition patterns
    if any(phrase in question for phrase in ["where is", "where's", "find the"]):
        symbols = _extract_symbols(question)
        if symbols:
            return QueryAnalysis(
                query_type=QueryType.DEFINITION,
                confidence=0.6,
                extracted_symbols=symbols,
                reasoning="Matched weak definition pattern"
            )

    return None


def _detect_reference_query(question: str) -> Optional[QueryAnalysis]:
    """Detect queries asking for symbol references/usages.

    Patterns:
    - "what calls X"
    - "where is X used"
    - "who uses X"
    - "find usages of X"
    - "show references to X"
    """
    reference_patterns = [
        r"what\s+calls\s+(\w+)",
        r"(?:where|who)\s+(?:is|does)\s+(\w+)\s+(?:used|called)",
        r"find\s+(?:all\s+)?(?:usages|uses|references|calls)\s+of\s+(\w+)",
        r"show\s+(?:me\s+)?(?:all\s+)?references\s+to\s+(\w+)",
        r"(?:who|what)\s+uses\s+(\w+)",
        r"(?:list|show)\s+(?:all\s+)?(?:the\s+)?callers?\s+of\s+(\w+)",
        r"where\s+(?:do|does)\s+(?:we|i)\s+(?:use|call)\s+(\w+)",
    ]

    for pattern in reference_patterns:
        match = re.search(pattern, question)
        if match:
            symbol = match.group(1) if match.groups() else None
            symbols = [symbol] if symbol else _extract_symbols(question)

            return QueryAnalysis(
                query_type=QueryType.REFERENCES,
                confidence=0.9,
                extracted_symbols=symbols,
                reasoning=f"Matched reference pattern: '{pattern}'"
            )

    # Weaker reference patterns
    if any(phrase in question for phrase in ["calls", "uses", "references to", "usages"]):
        symbols = _extract_symbols(question)
        if symbols:
            return QueryAnalysis(
                query_type=QueryType.REFERENCES,
                confidence=0.6,
                extracted_symbols=symbols,
                reasoning="Matched weak reference pattern"
            )

    return None


def _detect_behavioral_query(question: str) -> Optional[QueryAnalysis]:
    """Detect queries asking about behavior/purpose.

    Patterns:
    - "why does X happen"
    - "what is the purpose of X"
    - "why do we need X"
    - "what's the reason for X"
    """
    behavioral_patterns = [
        r"why\s+(?:does|is|do)\s+(\w+)",
        r"what\s+(?:is|was)\s+the\s+(?:purpose|reason)\s+(?:of|for)\s+(\w+)",
        r"why\s+(?:do|did)\s+(?:we|i)\s+(?:need|use|have)\s+(\w+)",
        r"what'?s\s+the\s+(?:purpose|reason|point)\s+of\s+(\w+)",
    ]

    for pattern in behavioral_patterns:
        match = re.search(pattern, question)
        if match:
            symbol = match.group(1) if match.groups() else None
            symbols = [symbol] if symbol else _extract_symbols(question)

            return QueryAnalysis(
                query_type=QueryType.BEHAVIORAL,
                confidence=0.8,
                extracted_symbols=symbols,
                reasoning=f"Matched behavioral pattern: '{pattern}'"
            )

    # Weaker behavioral patterns
    if any(phrase in question for phrase in ["why does", "why is", "purpose of", "reason for"]):
        return QueryAnalysis(
            query_type=QueryType.BEHAVIORAL,
            confidence=0.5,
            extracted_symbols=_extract_symbols(question),
            reasoning="Matched weak behavioral pattern"
        )

    return None


def _detect_conceptual_query(question: str) -> Optional[QueryAnalysis]:
    """Detect queries asking about concepts/implementation.

    Patterns:
    - "how does X work"
    - "what does X do"
    - "explain X"
    - "how is X implemented"
    """
    conceptual_patterns = [
        r"how\s+(?:does|do|is)\s+(\w+)\s+(?:work|implemented)",
        r"what\s+(?:does|do|is)\s+(\w+)\s+(?:do|for)",
        r"explain\s+(?:the\s+)?(\w+)",
        r"how\s+(?:to|do\s+(?:i|we))\s+(?:use|implement)\s+(\w+)",
        r"what\s+is\s+(\w+)",
    ]

    for pattern in conceptual_patterns:
        match = re.search(pattern, question)
        if match:
            symbol = match.group(1) if match.groups() else None
            symbols = [symbol] if symbol else _extract_symbols(question)

            return QueryAnalysis(
                query_type=QueryType.CONCEPTUAL,
                confidence=0.8,
                extracted_symbols=symbols,
                reasoning=f"Matched conceptual pattern: '{pattern}'"
            )

    # Default to conceptual for most "how/what" questions
    if any(question.startswith(word) for word in ["how ", "what ", "explain ", "describe "]):
        return QueryAnalysis(
            query_type=QueryType.CONCEPTUAL,
            confidence=0.6,
            extracted_symbols=_extract_symbols(question),
            reasoning="Default conceptual query"
        )

    return None


# ============================================================================
# Symbol Extraction
# ============================================================================

def _extract_symbols(question: str) -> List[str]:
    """Extract potential symbol names from question.

    Looks for:
    - PascalCase (classes)
    - snake_case (functions, variables)
    - camelCase (methods)
    - Capitalized words that look like names

    Args:
        question: Natural language question

    Returns:
        List of extracted symbol names
    """
    symbols = []

    # Pattern 1: CamelCase or PascalCase (e.g., UserService, getElementById)
    camel_pattern = r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b'
    symbols.extend(re.findall(camel_pattern, question))

    # Pattern 2: snake_case (e.g., authenticate_user, get_user_id)
    snake_pattern = r'\b[a-z]+(?:_[a-z]+)+\b'
    symbols.extend(re.findall(snake_pattern, question))

    # Pattern 3: ALL_CAPS (constants)
    caps_pattern = r'\b[A-Z][A-Z_]+\b'
    caps_matches = re.findall(caps_pattern, question)
    # Filter out common words
    symbols.extend([m for m in caps_matches if len(m) > 2])

    # Pattern 4: Single capitalized words (potential class names)
    # But exclude common words
    exclude_words = {
        "The", "This", "That", "What", "Where", "When", "Why", "How",
        "Is", "Are", "Do", "Does", "Can", "Could", "Should", "Would",
        "In", "On", "At", "To", "For", "From", "With", "By"
    }
    capital_pattern = r'\b[A-Z][a-z]{2,}\b'
    capital_matches = re.findall(capital_pattern, question)
    symbols.extend([m for m in capital_matches if m not in exclude_words])

    # Deduplicate while preserving order
    seen = set()
    unique_symbols = []
    for symbol in symbols:
        if symbol not in seen:
            seen.add(symbol)
            unique_symbols.append(symbol)

    logger.debug(f"Extracted symbols from query: {unique_symbols}")
    return unique_symbols


# ============================================================================
# Utility Functions
# ============================================================================

def get_primary_symbol(analysis: QueryAnalysis) -> Optional[str]:
    """Get the primary symbol from query analysis.

    Args:
        analysis: QueryAnalysis result

    Returns:
        First extracted symbol, or None if no symbols found
    """
    if analysis.extracted_symbols:
        return analysis.extracted_symbols[0]
    return None


def is_navigation_query(analysis: QueryAnalysis) -> bool:
    """Check if query is a code navigation query (definition/references).

    Args:
        analysis: QueryAnalysis result

    Returns:
        True if query is DEFINITION or REFERENCES type
    """
    return analysis.query_type in (QueryType.DEFINITION, QueryType.REFERENCES)


def format_analysis(analysis: QueryAnalysis) -> str:
    """Format query analysis for logging/display.

    Args:
        analysis: QueryAnalysis result

    Returns:
        Human-readable string
    """
    symbols_str = ", ".join(analysis.extracted_symbols) if analysis.extracted_symbols else "none"
    return (
        f"Query Type: {analysis.query_type.value}\n"
        f"Confidence: {analysis.confidence:.2f}\n"
        f"Symbols: {symbols_str}\n"
        f"Reasoning: {analysis.reasoning}"
    )
