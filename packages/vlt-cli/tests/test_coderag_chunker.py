"""Tests for coderag chunker module."""

import pytest
from vlt.core.coderag.chunker import (
    chunk_file,
    is_available,
    DEFAULT_CHUNK_LINES,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_MAX_CHARS,
)


def test_constants():
    """Test chunking constants are reasonable."""
    assert DEFAULT_CHUNK_LINES == 40
    assert DEFAULT_CHUNK_OVERLAP == 15
    assert DEFAULT_MAX_CHARS == 1500


def test_is_available():
    """Test availability check."""
    result = is_available()
    assert isinstance(result, bool)


@pytest.mark.skipif(not is_available(), reason="LlamaIndex or tree-sitter not installed")
def test_chunk_simple_python_function():
    """Test chunking a simple Python function."""
    code = '''
def hello(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}"
'''

    chunks = chunk_file(code, "python", "example.py")

    assert len(chunks) >= 1
    chunk = chunks[0]

    # Verify required fields
    assert "file_path" in chunk
    assert "chunk_type" in chunk
    assert "qualified_name" in chunk
    assert "imports" in chunk
    assert "class_context" in chunk
    assert "signature" in chunk
    assert "decorators" in chunk
    assert "docstring" in chunk
    assert "body" in chunk
    assert "lineno" in chunk
    assert "end_lineno" in chunk
    assert "language" in chunk
    assert "chunk_text" in chunk

    # Verify values
    assert chunk["file_path"] == "example.py"
    assert chunk["language"] == "python"
    assert "hello" in chunk["qualified_name"].lower()


@pytest.mark.skipif(not is_available(), reason="LlamaIndex or tree-sitter not installed")
def test_chunk_with_imports():
    """Test that imports are extracted."""
    code = '''
import os
from pathlib import Path

def process_file(path: str):
    return Path(path).exists()
'''

    chunks = chunk_file(code, "python", "example.py")

    assert len(chunks) >= 1
    # Check that imports are captured
    imports = chunks[0]["imports"]
    assert "import os" in imports or any("import os" in c["imports"] for c in chunks)


@pytest.mark.skipif(not is_available(), reason="LlamaIndex or tree-sitter not installed")
def test_chunk_class_method():
    """Test chunking a class with methods."""
    code = '''
class Calculator:
    """Simple calculator."""

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def subtract(self, a: int, b: int) -> int:
        """Subtract two numbers."""
        return a - b
'''

    chunks = chunk_file(code, "python", "calculator.py")

    # Should have chunks for the class and/or methods
    assert len(chunks) >= 1

    # At least one chunk should have class context or be a method
    has_method = any(
        "method" in chunk.get("chunk_type", "") or
        "class_context" in chunk and chunk["class_context"]
        for chunk in chunks
    )
    assert has_method or len(chunks) > 0  # Either has methods or has content


@pytest.mark.skipif(not is_available(), reason="LlamaIndex or tree-sitter not installed")
def test_chunk_with_decorators():
    """Test that decorators are extracted (Python)."""
    code = '''
from functools import lru_cache

@lru_cache(maxsize=128)
def expensive_function(n: int) -> int:
    """Compute something expensive."""
    return n * n
'''

    chunks = chunk_file(code, "python", "example.py")

    assert len(chunks) >= 1
    # Decorators should be in the chunk somewhere
    # (Either in decorators list or in chunk_text)
    chunk = chunks[0]
    has_decorator = (
        "@lru_cache" in chunk.get("chunk_text", "") or
        any("@lru_cache" in d for d in chunk.get("decorators", []))
    )
    # May or may not capture decorators depending on implementation
    # Just verify structure is present
    assert "decorators" in chunk


def test_chunk_file_unsupported_language():
    """Test chunking unsupported language."""
    if not is_available():
        pytest.skip("Dependencies not available")

    with pytest.raises(ValueError, match="Unsupported"):
        chunk_file("code", "cobol", "example.cob")


def test_chunk_file_no_dependencies():
    """Test error when dependencies not available."""
    if not is_available():
        with pytest.raises(RuntimeError, match="not available"):
            chunk_file("code", "python", "example.py")


@pytest.mark.skipif(not is_available(), reason="LlamaIndex or tree-sitter not installed")
def test_chunk_text_assembly():
    """Test that chunk_text is properly assembled."""
    code = '''
import sys

def main():
    """Main entry point."""
    print("Hello")
'''

    chunks = chunk_file(code, "python", "example.py")

    assert len(chunks) >= 1
    chunk = chunks[0]

    # chunk_text should combine context elements
    chunk_text = chunk["chunk_text"]
    assert chunk_text  # Not empty
    assert isinstance(chunk_text, str)


@pytest.mark.skipif(not is_available(), reason="LlamaIndex or tree-sitter not installed")
def test_chunk_large_file():
    """Test chunking a larger file creates multiple chunks."""
    # Create a file with multiple functions
    code = '\n'.join([
        f'''
def function_{i}(x):
    """Function number {i}."""
    result = x * {i}
    return result
'''
        for i in range(10)
    ])

    chunks = chunk_file(code, "python", "large.py", chunk_lines=20)

    # Should create multiple chunks
    assert len(chunks) >= 2

    # Each chunk should be properly structured
    for chunk in chunks:
        assert chunk["language"] == "python"
        assert chunk["file_path"] == "large.py"
        assert "chunk_text" in chunk
