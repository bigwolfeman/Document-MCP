#!/usr/bin/env python3
"""
Demo script showing how to use vlt.toml configuration.

This demonstrates:
1. Creating a vlt.toml file
2. Loading configuration sections
3. Using configuration values
4. Handling defaults
"""

from pathlib import Path
import tempfile

from vlt.core.identity import (
    create_vlt_toml,
    load_vlt_config,
    load_project_identity,
    load_coderag_config,
    load_oracle_config,
)


def demo_create_config():
    """Demo: Create a vlt.toml file."""
    print("=" * 70)
    print("DEMO 1: Creating vlt.toml")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)

        # Create vlt.toml
        create_vlt_toml(
            path=path,
            name="demo-project",
            id="demo-project",
            description="A demonstration project"
        )

        # Show the generated file
        toml_file = path / "vlt.toml"
        print(f"\nCreated: {toml_file}")
        print("\nContents:")
        print("-" * 70)
        print(toml_file.read_text())
        print("-" * 70)


def demo_load_config():
    """Demo: Load complete configuration."""
    print("\n" + "=" * 70)
    print("DEMO 2: Loading Complete Configuration")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        create_vlt_toml(path, "load-demo", "load-demo", "Load demo project")

        # Load complete config
        config = load_vlt_config(path)

        print(f"\nProject Name: {config.project.name}")
        print(f"Project ID: {config.project.id}")
        print(f"Description: {config.project.description}")

        print(f"\nCodeRAG Enabled: {config.coderag is not None}")
        if config.coderag:
            print(f"  Include Patterns: {config.coderag.include}")
            print(f"  Languages: {config.coderag.languages}")
            print(f"  Embedding Model: {config.coderag.embedding.model}")
            print(f"  Batch Size: {config.coderag.embedding.batch_size}")

        print(f"\nOracle Enabled: {config.oracle is not None}")
        if config.oracle:
            print(f"  Vault URL: {config.oracle.vault_url}")
            print(f"  Synthesis Model: {config.oracle.synthesis_model}")
            print(f"  Max Context Tokens: {config.oracle.max_context_tokens}")


def demo_section_loading():
    """Demo: Load individual sections."""
    print("\n" + "=" * 70)
    print("DEMO 3: Loading Individual Sections")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        create_vlt_toml(path, "section-demo", "section-demo")

        # Load project only
        project = load_project_identity(path)
        print(f"\n[Project Section]")
        print(f"  Name: {project.name}")
        print(f"  ID: {project.id}")

        # Load CodeRAG config
        coderag = load_coderag_config(path)
        print(f"\n[CodeRAG Section]")
        print(f"  Include: {coderag.include}")
        print(f"  Exclude: {coderag.exclude[:2]}...")  # Show first 2
        print(f"  Embedding Model: {coderag.embedding.model}")
        print(f"  Repo Map Tokens: {coderag.repomap.max_tokens}")
        print(f"  Delta File Threshold: {coderag.delta.file_threshold}")

        # Load Oracle config
        oracle = load_oracle_config(path)
        print(f"\n[Oracle Section]")
        print(f"  Vault URL: {oracle.vault_url}")
        print(f"  Synthesis Model: {oracle.synthesis_model}")
        print(f"  Rerank Model: {oracle.rerank_model}")


def demo_defaults():
    """Demo: Using defaults when sections are missing."""
    print("\n" + "=" * 70)
    print("DEMO 4: Defaults When Sections Missing")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)

        # Create minimal vlt.toml (only [project])
        minimal_toml = path / "vlt.toml"
        minimal_toml.write_text("""[project]
name = "minimal-project"
id = "minimal-project"
""")

        print("\nCreated minimal vlt.toml (only [project] section)")

        # Load sections - should get defaults
        coderag = load_coderag_config(path)
        oracle = load_oracle_config(path)

        print("\nLoading CodeRAG config...")
        print(f"  Got defaults? {coderag is not None}")
        print(f"  Embedding Model: {coderag.embedding.model}")
        print(f"  Languages: {coderag.languages}")

        print("\nLoading Oracle config...")
        print(f"  Got defaults? {oracle is not None}")
        print(f"  Synthesis Model: {oracle.synthesis_model}")
        print(f"  Max Context Tokens: {oracle.max_context_tokens}")


def demo_custom_config():
    """Demo: Using custom configuration values."""
    print("\n" + "=" * 70)
    print("DEMO 5: Custom Configuration Values")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)

        # Create custom vlt.toml
        custom_toml = path / "vlt.toml"
        custom_toml.write_text("""[project]
name = "custom-rust-project"
id = "custom-rust-project"
description = "A Rust project with custom settings"

[coderag]
include = ["src/**/*.rs", "lib/**/*.rs"]
exclude = ["**/target/**", "**/.git/**"]
languages = ["rust"]

[coderag.embedding]
model = "openai/text-embedding-3-large"
batch_size = 25

[coderag.repomap]
max_tokens = 8000
include_signatures = true
include_docstrings = true

[coderag.delta]
file_threshold = 10
line_threshold = 2000
timeout_seconds = 600
jit_indexing = false

[oracle]
vault_url = "https://my-vault.example.com"
synthesis_model = "openai/gpt-4o"
rerank_model = "anthropic/claude-haiku-4"
max_context_tokens = 32000
""")

        print("\nCreated custom vlt.toml for Rust project")

        config = load_vlt_config(path)

        print(f"\n[Project]")
        print(f"  Name: {config.project.name}")
        print(f"  Language: Rust")

        print(f"\n[CodeRAG - Custom]")
        print(f"  Include: {config.coderag.include}")
        print(f"  Languages: {config.coderag.languages}")
        print(f"  Embedding Model: {config.coderag.embedding.model}")
        print(f"  Batch Size: {config.coderag.embedding.batch_size}")
        print(f"  Repo Map Tokens: {config.coderag.repomap.max_tokens}")
        print(f"  Include Docstrings: {config.coderag.repomap.include_docstrings}")
        print(f"  Delta File Threshold: {config.coderag.delta.file_threshold}")
        print(f"  JIT Indexing: {config.coderag.delta.jit_indexing}")

        print(f"\n[Oracle - Custom]")
        print(f"  Vault URL: {config.oracle.vault_url}")
        print(f"  Synthesis Model: {config.oracle.synthesis_model}")
        print(f"  Rerank Model: {config.oracle.rerank_model}")
        print(f"  Max Tokens: {config.oracle.max_context_tokens}")


def demo_nested_search():
    """Demo: Finding vlt.toml from nested directories."""
    print("\n" + "=" * 70)
    print("DEMO 6: Nested Directory Search")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        create_vlt_toml(root, "root-project", "root-project")

        # Create deep nested structure
        deep_path = root / "src" / "core" / "modules" / "handlers"
        deep_path.mkdir(parents=True)

        print(f"\nProject root: {root}")
        print(f"Working directory: {deep_path}")
        print(f"Relative depth: 4 levels deep")

        # Load config from deep path
        project = load_project_identity(deep_path)
        coderag = load_coderag_config(deep_path)

        print(f"\nFound vlt.toml? {project is not None}")
        print(f"Project Name: {project.name}")
        print(f"CodeRAG Model: {coderag.embedding.model}")
        print("\n✓ Successfully found vlt.toml in parent directory!")


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print("VLT.TOML CONFIGURATION DEMO")
    print("=" * 70)

    demo_create_config()
    demo_load_config()
    demo_section_loading()
    demo_defaults()
    demo_custom_config()
    demo_nested_search()

    print("\n" + "=" * 70)
    print("All demos completed!")
    print("=" * 70)
    print("\nSee examples/vlt.toml.example for a complete template")
    print("See docs/configuration.md for full documentation")
    print()


if __name__ == "__main__":
    main()
