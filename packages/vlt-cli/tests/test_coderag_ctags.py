"""Tests for coderag ctags module."""

import pytest
import os
import tempfile
import shutil
from pathlib import Path

from vlt.core.coderag.ctags import (
    generate_ctags,
    parse_ctags,
    lookup_definition,
    lookup_all_definitions,
    lookup_by_kind,
    lookup_in_file,
    get_ctags_status,
    _parse_tag_line,
    _expand_kind,
    SymbolDefinition,
)


def test_expand_kind():
    """Test ctags kind abbreviation expansion."""
    assert _expand_kind("c") == "class"
    assert _expand_kind("f") == "function"
    assert _expand_kind("m") == "method"
    assert _expand_kind("v") == "variable"
    assert _expand_kind("i") == "interface"
    assert _expand_kind("unknown") == "unknown"


def test_parse_tag_line_basic():
    """Test parsing a basic ctags tag line."""
    line = 'authenticate_user\tsrc/auth.py\t/^def authenticate_user(username, password):$/;"\tf\tline:42\tsignature:(username, password)'

    symbol = _parse_tag_line(line)

    assert symbol is not None
    assert symbol.name == "authenticate_user"
    assert symbol.file_path == "src/auth.py"
    assert symbol.lineno == 42
    assert symbol.kind == "function"
    assert symbol.signature == "(username, password)"


def test_parse_tag_line_with_class():
    """Test parsing a tag line with class scope."""
    line = 'method_name\tsrc/models.py\t/^    def method_name(self):$/;"\tm\tline:100\tclass:MyClass'

    symbol = _parse_tag_line(line)

    assert symbol is not None
    assert symbol.name == "method_name"
    assert symbol.kind == "method"
    assert symbol.scope == "MyClass"
    assert symbol.lineno == 100


def test_parse_tag_line_invalid():
    """Test parsing invalid tag lines."""
    # Too few fields
    assert _parse_tag_line("invalid") is None

    # Comment line
    assert _parse_tag_line("!_TAG_FILE_FORMAT\t2") is None


def test_lookup_definition():
    """Test looking up symbol definitions."""
    symbols = [
        SymbolDefinition("UserService", "src/user.py", 10, "class"),
        SymbolDefinition("authenticate", "src/auth.py", 20, "function"),
        SymbolDefinition("helper", "src/utils.py", 30, "function"),
    ]

    # Exact match
    result = lookup_definition("UserService", symbols)
    assert result is not None
    assert result.name == "UserService"
    assert result.file_path == "src/user.py"

    # Not found
    result = lookup_definition("NonExistent", symbols)
    assert result is None


def test_lookup_definition_qualified():
    """Test looking up qualified symbol names."""
    symbols = [
        SymbolDefinition("UserService.create", "src/user.py", 20, "method", scope="UserService"),
    ]

    # Exact match
    result = lookup_definition("UserService.create", symbols)
    assert result is not None

    # Suffix match
    result = lookup_definition("create", symbols)
    assert result is not None


def test_lookup_all_definitions():
    """Test looking up all matching definitions."""
    symbols = [
        SymbolDefinition("helper", "src/utils.py", 10, "function"),
        SymbolDefinition("helper", "src/common.py", 20, "function"),
        SymbolDefinition("other", "src/other.py", 30, "function"),
    ]

    results = lookup_all_definitions("helper", symbols)
    assert len(results) == 2
    assert all(s.name == "helper" for s in results)


def test_lookup_by_kind():
    """Test looking up symbols by kind."""
    symbols = [
        SymbolDefinition("UserService", "src/user.py", 10, "class"),
        SymbolDefinition("ProductService", "src/product.py", 20, "class"),
        SymbolDefinition("authenticate", "src/auth.py", 30, "function"),
    ]

    classes = lookup_by_kind("class", symbols)
    assert len(classes) == 2
    assert all(s.kind == "class" for s in classes)

    functions = lookup_by_kind("function", symbols)
    assert len(functions) == 1


def test_lookup_in_file():
    """Test looking up symbols in a specific file."""
    symbols = [
        SymbolDefinition("UserService", "src/user.py", 10, "class"),
        SymbolDefinition("create_user", "src/user.py", 20, "function"),
        SymbolDefinition("authenticate", "src/auth.py", 30, "function"),
    ]

    user_symbols = lookup_in_file("src/user.py", symbols)
    assert len(user_symbols) == 2
    assert all(s.file_path == "src/user.py" for s in user_symbols)


@pytest.mark.skipif(not shutil.which("ctags"), reason="ctags not installed")
def test_generate_ctags_integration():
    """Integration test for ctags generation (requires ctags binary)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test Python file
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("""
class TestClass:
    def method_one(self):
        pass

def test_function():
    pass
""")

        # Generate ctags
        tags_path = generate_ctags(tmpdir, languages=["Python"])

        assert tags_path is not None
        assert os.path.exists(tags_path)

        # Parse tags
        symbols = parse_ctags(tags_path)

        # Should find class and functions
        assert len(symbols) > 0

        # Find specific symbols
        test_class = lookup_definition("TestClass", symbols)
        assert test_class is not None
        assert test_class.kind == "class"

        test_func = lookup_definition("test_function", symbols)
        assert test_func is not None
        assert test_func.kind == "function"


@pytest.mark.skipif(not shutil.which("ctags"), reason="ctags not installed")
def test_get_ctags_status():
    """Test getting ctags status for a project."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initially no tags
        status = get_ctags_status(tmpdir)
        assert status["available"] is False
        assert status["indexed"] is False

        # Create test file and generate tags
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("def foo(): pass")

        tags_path = generate_ctags(tmpdir)

        # Now should have tags
        status = get_ctags_status(tmpdir)
        assert status["available"] is True
        assert status["indexed"] is True
        assert status["total_symbols"] > 0
        assert "last_updated" in status


def test_generate_ctags_not_installed():
    """Test graceful failure when ctags is not installed."""
    # Temporarily override shutil.which to simulate missing ctags
    original_which = shutil.which

    def mock_which(cmd):
        if cmd == "ctags":
            return None
        return original_which(cmd)

    shutil.which = mock_which

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_ctags(tmpdir)
            assert result is None  # Should return None gracefully
    finally:
        shutil.which = original_which


def test_parse_ctags_missing_file():
    """Test parsing non-existent tags file."""
    symbols = parse_ctags("/nonexistent/tags")
    assert symbols == []


def test_symbol_definition_dataclass():
    """Test SymbolDefinition dataclass."""
    symbol = SymbolDefinition(
        name="test_func",
        file_path="test.py",
        lineno=42,
        kind="function",
        scope="TestClass",
        signature="(arg1, arg2)",
        language="python"
    )

    assert symbol.name == "test_func"
    assert symbol.file_path == "test.py"
    assert symbol.lineno == 42
    assert symbol.kind == "function"
    assert symbol.scope == "TestClass"
    assert symbol.signature == "(arg1, arg2)"
    assert symbol.language == "python"
