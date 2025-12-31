#!/usr/bin/env python3
"""Demo script for CodeRAG parser and chunker functionality.

This script demonstrates the parser and chunker modules with example code.
It works even without tree-sitter/llama-index installed, showing graceful degradation.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vlt.core.coderag.parser import (
    detect_language,
    is_available as parser_available,
    SUPPORTED_LANGUAGES
)
from vlt.core.coderag.chunker import (
    is_available as chunker_available,
    DEFAULT_CHUNK_LINES,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_MAX_CHARS,
)

# Example code to parse
EXAMPLE_PYTHON = '''
import os
from pathlib import Path
from typing import List, Optional

class FileProcessor:
    """Process files with various operations."""

    def __init__(self, base_path: Path):
        """Initialize processor with base path."""
        self.base_path = base_path

    def list_files(self, pattern: str = "*.py") -> List[Path]:
        """List files matching pattern.

        Args:
            pattern: Glob pattern for file matching

        Returns:
            List of matching file paths
        """
        return list(self.base_path.glob(pattern))

    @staticmethod
    def validate_path(path: str) -> bool:
        """Validate that path exists and is readable."""
        return Path(path).exists()

def main():
    """Main entry point."""
    processor = FileProcessor(Path.cwd())
    files = processor.list_files()
    print(f"Found {len(files)} files")

if __name__ == "__main__":
    main()
'''


def demo_parser():
    """Demonstrate parser functionality."""
    print("=" * 70)
    print("PARSER DEMO")
    print("=" * 70)

    # Check availability
    print(f"\nParser available: {parser_available()}")
    print(f"Supported languages: {', '.join(sorted(SUPPORTED_LANGUAGES))}")

    # Language detection
    print("\n--- Language Detection ---")
    test_files = [
        "main.py",
        "app.ts",
        "component.tsx",
        "script.js",
        "server.go",
        "lib.rs",
        "unknown.txt",
    ]

    for file in test_files:
        lang = detect_language(file)
        print(f"{file:20s} -> {lang or 'Unknown'}")

    # Parsing (only if available)
    if parser_available():
        print("\n--- Parsing Python Code ---")
        try:
            from vlt.core.coderag.parser import parse_file

            tree = parse_file(EXAMPLE_PYTHON, "python")
            if tree:
                print(f"Root node type: {tree.root_node.type}")
                print(f"Has errors: {tree.root_node.has_error}")
                print(f"Children count: {len(tree.root_node.children)}")
                print("Parse successful!")
            else:
                print("Parse returned None")
        except Exception as e:
            print(f"Parse error: {e}")
    else:
        print("\n[Parsing skipped - tree-sitter not installed]")


def demo_chunker():
    """Demonstrate chunker functionality."""
    print("\n" + "=" * 70)
    print("CHUNKER DEMO")
    print("=" * 70)

    # Check availability
    print(f"\nChunker available: {chunker_available()}")

    # Configuration
    print("\n--- Chunker Configuration ---")
    print(f"Default chunk lines: {DEFAULT_CHUNK_LINES}")
    print(f"Default overlap: {DEFAULT_CHUNK_OVERLAP}")
    print(f"Max characters: {DEFAULT_MAX_CHARS}")

    # Chunking (only if available)
    if chunker_available():
        print("\n--- Chunking Python Code ---")
        try:
            from vlt.core.coderag.chunker import chunk_file

            chunks = chunk_file(EXAMPLE_PYTHON, "python", "example.py")

            print(f"\nCreated {len(chunks)} chunk(s)")
            print()

            for i, chunk in enumerate(chunks, 1):
                print(f"Chunk {i}:")
                print(f"  Type: {chunk['chunk_type']}")
                print(f"  Name: {chunk['qualified_name']}")
                print(f"  Lines: {chunk['lineno']}-{chunk['end_lineno']}")
                print(f"  Language: {chunk['language']}")

                if chunk['imports']:
                    print(f"  Imports: {len(chunk['imports'].split(chr(10)))} lines")

                if chunk['class_context']:
                    print(f"  Class context: Yes")

                if chunk['signature']:
                    print(f"  Signature: {chunk['signature'][:50]}...")

                if chunk['decorators']:
                    print(f"  Decorators: {len(chunk['decorators'])}")

                if chunk['docstring']:
                    print(f"  Docstring: {chunk['docstring'][:50]}...")

                print(f"  Chunk text length: {len(chunk['chunk_text'])} chars")
                print()

        except Exception as e:
            print(f"Chunking error: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("\n[Chunking skipped - dependencies not installed]")
        print("Install with: pip install tree-sitter tree-sitter-languages llama-index-core")


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print("CodeRAG Parser and Chunker Demo")
    print("=" * 70)

    demo_parser()
    demo_chunker()

    print("\n" + "=" * 70)
    print("Demo complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
