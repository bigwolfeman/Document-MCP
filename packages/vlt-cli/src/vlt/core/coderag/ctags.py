"""Ctags wrapper for symbol definition indexing.

Uses Universal Ctags to generate symbol indexes for fast definition lookup.
Falls back gracefully when ctags is not installed.
"""

import subprocess
import logging
import shutil
import os
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SymbolDefinition:
    """Symbol definition from ctags (dict form, not SQLAlchemy)."""
    name: str
    file_path: str
    lineno: int
    kind: str  # function, class, method, variable, etc.
    scope: Optional[str] = None  # Enclosing scope (e.g., "class:MyClass")
    signature: Optional[str] = None
    language: str = "unknown"


def generate_ctags(project_path: str, languages: Optional[List[str]] = None) -> Optional[str]:
    """Generate ctags file for a project.

    Args:
        project_path: Root directory of the project
        languages: List of languages to index (default: Python, TypeScript, JavaScript)

    Returns:
        Path to generated tags file, or None if ctags not available
    """
    # Check if ctags is available
    ctags_bin = shutil.which("ctags")
    if not ctags_bin:
        logger.warning(
            "ctags binary not found. Symbol indexing will be unavailable. "
            "Install Universal Ctags for better code intelligence: "
            "https://github.com/universal-ctags/ctags"
        )
        return None

    # Default languages
    if languages is None:
        languages = ["Python", "TypeScript", "JavaScript"]

    # Tags file path
    tags_path = os.path.join(project_path, "tags")

    # Build ctags command
    lang_str = ",".join(languages)
    cmd = [
        ctags_bin,
        "--recurse",
        f"--languages={lang_str}",
        "--extras=+q",  # Include qualified names
        "--fields=+nKS",  # Include line number, kind, signature
        "-f", tags_path,
        "."
    ]

    try:
        # Run ctags
        result = subprocess.run(
            cmd,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120  # 2 minute timeout
        )

        if result.returncode != 0:
            logger.error(f"ctags failed with exit code {result.returncode}: {result.stderr}")
            return None

        # Verify tags file was created
        if not os.path.exists(tags_path):
            logger.error(f"ctags did not create tags file at {tags_path}")
            return None

        logger.info(f"Generated ctags index at {tags_path}")
        return tags_path

    except subprocess.TimeoutExpired:
        logger.error("ctags command timed out after 120 seconds")
        return None
    except Exception as e:
        logger.error(f"Failed to run ctags: {e}")
        return None


def parse_ctags(tags_path: str) -> List[SymbolDefinition]:
    """Parse ctags file into symbol definitions.

    Args:
        tags_path: Path to ctags tags file

    Returns:
        List of SymbolDefinition objects
    """
    if not os.path.exists(tags_path):
        logger.error(f"Tags file not found: {tags_path}")
        return []

    symbols: List[SymbolDefinition] = []

    try:
        with open(tags_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                # Skip comment lines
                if line.startswith("!_TAG_"):
                    continue

                # Parse tag line
                symbol = _parse_tag_line(line)
                if symbol:
                    symbols.append(symbol)

        logger.info(f"Parsed {len(symbols)} symbols from {tags_path}")
        return symbols

    except Exception as e:
        logger.error(f"Failed to parse ctags file {tags_path}: {e}")
        return []


def lookup_definition(name: str, tags: List[SymbolDefinition]) -> Optional[SymbolDefinition]:
    """Look up symbol definition by name.

    Args:
        name: Symbol name to look up
        tags: List of symbol definitions from parse_ctags

    Returns:
        First matching SymbolDefinition, or None if not found
    """
    # Exact match
    for tag in tags:
        if tag.name == name:
            return tag

    # Try suffix match for qualified names (e.g., "method" matches "Class.method")
    for tag in tags:
        if tag.name.endswith(f".{name}") or tag.name.endswith(f"::{name}"):
            return tag

    return None


def lookup_all_definitions(name: str, tags: List[SymbolDefinition]) -> List[SymbolDefinition]:
    """Look up all symbol definitions matching a name.

    Useful when a symbol is defined in multiple places.

    Args:
        name: Symbol name to look up
        tags: List of symbol definitions from parse_ctags

    Returns:
        List of matching SymbolDefinition objects
    """
    matches = []

    # Exact matches
    for tag in tags:
        if tag.name == name:
            matches.append(tag)

    # Suffix matches for qualified names
    if not matches:
        for tag in tags:
            if tag.name.endswith(f".{name}") or tag.name.endswith(f"::{name}"):
                matches.append(tag)

    return matches


def lookup_by_kind(kind: str, tags: List[SymbolDefinition]) -> List[SymbolDefinition]:
    """Look up symbols by kind (function, class, method, etc.).

    Args:
        kind: Symbol kind (function, class, method, variable, etc.)
        tags: List of symbol definitions

    Returns:
        List of matching symbols
    """
    return [tag for tag in tags if tag.kind == kind]


def lookup_in_file(file_path: str, tags: List[SymbolDefinition]) -> List[SymbolDefinition]:
    """Look up all symbols defined in a file.

    Args:
        file_path: Path to source file
        tags: List of symbol definitions

    Returns:
        List of symbols defined in the file
    """
    # Normalize path for comparison
    normalized = os.path.normpath(file_path)
    return [tag for tag in tags if os.path.normpath(tag.file_path) == normalized]


# ============================================================================
# Internal Parsing
# ============================================================================

def _parse_tag_line(line: str) -> Optional[SymbolDefinition]:
    """Parse a single line from ctags file.

    Ctags format (tab-separated):
    <tag_name>\t<file_path>\t<ex_command>;\t<extension_fields>

    Example:
    authenticate_user\tsrc/auth.py\t/^def authenticate_user(username, password):$/;"\tf\tline:42\tsignature:(username, password)

    Extension fields format:
    <kind>  line:<lineno>  signature:<sig>  class:<scope>  etc.
    """
    try:
        # Split by tabs
        parts = line.strip().split("\t")
        if len(parts) < 3:
            return None

        tag_name = parts[0]
        file_path = parts[1]

        # Parse extension fields (everything after first ;")
        extensions = {}
        for part in parts[3:]:
            if ":" in part:
                key, value = part.split(":", 1)
                extensions[key] = value
            elif len(part) == 1:  # Single letter is the kind
                extensions["kind"] = part

        # Extract fields
        kind = extensions.get("kind", "unknown")
        lineno_str = extensions.get("line", "0")
        signature = extensions.get("signature")
        scope = extensions.get("class") or extensions.get("namespace") or extensions.get("struct")
        language = extensions.get("language", "unknown")

        # Parse line number
        try:
            lineno = int(lineno_str)
        except ValueError:
            lineno = 0

        # Expand kind abbreviations
        kind = _expand_kind(kind)

        return SymbolDefinition(
            name=tag_name,
            file_path=file_path,
            lineno=lineno,
            kind=kind,
            scope=scope,
            signature=signature,
            language=language
        )

    except Exception as e:
        logger.debug(f"Failed to parse ctags line: {line.strip()} - {e}")
        return None


def _expand_kind(kind: str) -> str:
    """Expand ctags kind abbreviations to full names."""
    kind_map = {
        "c": "class",
        "f": "function",
        "m": "method",
        "v": "variable",
        "i": "interface",
        "s": "struct",
        "t": "type",
        "n": "namespace",
        "e": "enum",
        "p": "property",
    }
    return kind_map.get(kind, kind)


def get_ctags_status(project_path: str) -> dict:
    """Get status of ctags index for a project.

    Args:
        project_path: Root directory of the project

    Returns:
        Dict with status information
    """
    tags_path = os.path.join(project_path, "tags")

    if not os.path.exists(tags_path):
        return {
            "available": False,
            "indexed": False,
            "tags_path": tags_path,
        }

    # Parse to get symbol count
    symbols = parse_ctags(tags_path)

    # Get file modification time
    mtime = os.path.getmtime(tags_path)
    from datetime import datetime
    last_updated = datetime.fromtimestamp(mtime)

    # Group by kind
    by_kind = {}
    for sym in symbols:
        by_kind[sym.kind] = by_kind.get(sym.kind, 0) + 1

    return {
        "available": True,
        "indexed": True,
        "tags_path": tags_path,
        "total_symbols": len(symbols),
        "by_kind": by_kind,
        "last_updated": last_updated.isoformat(),
    }


def regenerate_ctags_if_stale(
    project_path: str,
    max_age_seconds: int = 3600,
    languages: Optional[List[str]] = None
) -> Optional[str]:
    """Regenerate ctags index if it's stale or missing.

    Args:
        project_path: Root directory of the project
        max_age_seconds: Maximum age of tags file before regeneration (default: 1 hour)
        languages: Languages to index

    Returns:
        Path to tags file, or None if generation failed
    """
    tags_path = os.path.join(project_path, "tags")

    # Check if regeneration is needed
    should_regenerate = False

    if not os.path.exists(tags_path):
        should_regenerate = True
        logger.info("Tags file missing, generating...")
    else:
        # Check age
        import time
        mtime = os.path.getmtime(tags_path)
        age = time.time() - mtime

        if age > max_age_seconds:
            should_regenerate = True
            logger.info(f"Tags file is {age:.0f}s old (max {max_age_seconds}s), regenerating...")

    if should_regenerate:
        return generate_ctags(project_path, languages)
    else:
        logger.debug(f"Tags file is fresh: {tags_path}")
        return tags_path


# ============================================================================
# T038 - Index Loading and Querying
# ============================================================================

def load_ctags_index(project_id: str, project_path: str) -> List[SymbolDefinition]:
    """Load ctags index for a project from tags file.

    Args:
        project_id: Project identifier (for logging/context)
        project_path: Root directory of the project

    Returns:
        List of SymbolDefinition objects from the tags file
    """
    tags_path = os.path.join(project_path, "tags")

    if not os.path.exists(tags_path):
        logger.warning(f"No ctags index found for project {project_id} at {tags_path}")
        return []

    symbols = parse_ctags(tags_path)
    logger.info(f"Loaded {len(symbols)} symbols from ctags index for project {project_id}")
    return symbols


def query_ctags(
    name: str,
    tags: List[SymbolDefinition],
    kind: Optional[str] = None,
    exact: bool = False
) -> List[SymbolDefinition]:
    """Query ctags index for symbols matching name and kind.

    Supports both exact and prefix matching.

    Args:
        name: Symbol name to search for
        tags: List of symbol definitions from load_ctags_index
        kind: Optional filter by symbol kind (function, class, method, etc.)
        exact: If True, only exact matches; if False, include prefix matches

    Returns:
        List of matching SymbolDefinition objects, ordered by relevance
    """
    if not name:
        return []

    matches = []
    name_lower = name.lower()

    # First pass: exact matches
    for tag in tags:
        # Check kind filter if provided
        if kind and tag.kind != kind:
            continue

        # Exact match (case-insensitive)
        if tag.name.lower() == name_lower:
            matches.append(tag)

    # If exact mode or we have exact matches, return them
    if exact or matches:
        return matches

    # Second pass: suffix matches for qualified names
    # e.g., "method" matches "Class.method"
    for tag in tags:
        if kind and tag.kind != kind:
            continue

        if tag.name.lower().endswith(f".{name_lower}") or tag.name.lower().endswith(f"::{name_lower}"):
            matches.append(tag)

    if matches:
        return matches

    # Third pass: prefix matches (only if no exact or suffix matches)
    # e.g., "auth" matches "authenticate_user"
    for tag in tags:
        if kind and tag.kind != kind:
            continue

        if tag.name.lower().startswith(name_lower):
            matches.append(tag)

    return matches
