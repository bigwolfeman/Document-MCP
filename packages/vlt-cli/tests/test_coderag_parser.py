"""Tests for coderag parser module."""

import pytest
from vlt.core.coderag.parser import (
    detect_language,
    parse_file,
    get_node_text,
    is_available,
    SUPPORTED_LANGUAGES,
)


def test_detect_language():
    """Test language detection from file extensions."""
    assert detect_language("main.py") == "python"
    assert detect_language("app.ts") == "typescript"
    assert detect_language("component.tsx") == "tsx"
    assert detect_language("script.js") == "javascript"
    assert detect_language("main.go") == "go"
    assert detect_language("lib.rs") == "rust"
    assert detect_language("unknown.txt") is None
    assert detect_language("file") is None


def test_detect_language_case_insensitive():
    """Test language detection is case-insensitive."""
    assert detect_language("Main.PY") == "python"
    assert detect_language("App.TS") == "typescript"


def test_supported_languages():
    """Test supported languages constant."""
    assert "python" in SUPPORTED_LANGUAGES
    assert "typescript" in SUPPORTED_LANGUAGES
    assert "javascript" in SUPPORTED_LANGUAGES
    assert "go" in SUPPORTED_LANGUAGES
    assert "rust" in SUPPORTED_LANGUAGES
    assert len(SUPPORTED_LANGUAGES) >= 5


def test_is_available():
    """Test availability check."""
    # Should return bool
    result = is_available()
    assert isinstance(result, bool)


@pytest.mark.skipif(not is_available(), reason="tree-sitter not installed")
def test_parse_file_python():
    """Test parsing Python code."""
    code = """
def hello(name: str) -> str:
    '''Greet someone.'''
    return f"Hello, {name}"
"""
    tree = parse_file(code, "python")
    assert tree is not None
    assert tree.root_node.type == "module"
    assert not tree.root_node.has_error


@pytest.mark.skipif(not is_available(), reason="tree-sitter not installed")
def test_parse_file_with_syntax_error():
    """Test parsing code with syntax errors."""
    code = "def hello(\n    # incomplete"
    tree = parse_file(code, "python")
    # Should still return a tree, but with errors
    assert tree is not None
    # May or may not have errors depending on recovery


@pytest.mark.skipif(not is_available(), reason="tree-sitter not installed")
def test_parse_file_unsupported_language():
    """Test parsing unsupported language raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported language"):
        parse_file("code", "cobol")


def test_parse_file_no_tree_sitter():
    """Test error when tree-sitter not available."""
    if not is_available():
        with pytest.raises(RuntimeError, match="tree-sitter not available"):
            parse_file("code", "python")


@pytest.mark.skipif(not is_available(), reason="tree-sitter not installed")
def test_get_node_text():
    """Test extracting text from a node."""
    code = "def hello():\n    pass"
    tree = parse_file(code, "python")
    assert tree is not None

    # Get function definition node
    func_node = tree.root_node.children[0]
    text = get_node_text(func_node, code.encode('utf-8'))
    assert "def hello" in text
    assert "pass" in text
