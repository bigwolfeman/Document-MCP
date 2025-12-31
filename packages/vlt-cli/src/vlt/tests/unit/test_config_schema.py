"""Tests for vlt.toml configuration schema."""

import tempfile
import tomllib
from pathlib import Path

import pytest

from vlt.core.identity import (
    CodeRAGConfig,
    CodeRAGDeltaConfig,
    CodeRAGEmbeddingConfig,
    CodeRAGRepoMapConfig,
    OracleConfig,
    ProjectConfig,
    VltConfig,
    create_vlt_toml,
    find_vlt_toml,
    load_coderag_config,
    load_oracle_config,
    load_project_identity,
    load_vlt_config,
)


class TestConfigModels:
    """Test Pydantic configuration models."""

    def test_project_config_minimal(self):
        """Test minimal project config."""
        config = ProjectConfig(name="test-project", id="test-project")
        assert config.name == "test-project"
        assert config.id == "test-project"
        assert config.description is None

    def test_project_config_full(self):
        """Test full project config."""
        config = ProjectConfig(
            name="test-project",
            id="test-project",
            description="A test project"
        )
        assert config.description == "A test project"

    def test_coderag_config_defaults(self):
        """Test CodeRAG config with defaults."""
        config = CodeRAGConfig()
        assert config.include == ["src/**/*.py", "lib/**/*.py", "tests/**/*.py"]
        assert config.exclude == ["**/node_modules/**", "**/__pycache__/**", "**/.git/**"]
        assert config.languages == ["python", "typescript", "javascript"]
        assert config.embedding.model == "qwen/qwen3-embedding-8b"
        assert config.embedding.batch_size == 10
        assert config.repomap.max_tokens == 4000
        assert config.repomap.include_signatures is True
        assert config.repomap.include_docstrings is False
        assert config.delta.file_threshold == 5
        assert config.delta.line_threshold == 1000
        assert config.delta.timeout_seconds == 300
        assert config.delta.jit_indexing is True

    def test_coderag_config_custom(self):
        """Test CodeRAG config with custom values."""
        config = CodeRAGConfig(
            include=["custom/**/*.py"],
            exclude=["custom_exclude/**"],
            languages=["rust"],
            embedding=CodeRAGEmbeddingConfig(
                model="custom/model",
                batch_size=20
            ),
            repomap=CodeRAGRepoMapConfig(
                max_tokens=8000,
                include_signatures=False,
                include_docstrings=True
            ),
            delta=CodeRAGDeltaConfig(
                file_threshold=10,
                line_threshold=2000,
                timeout_seconds=600,
                jit_indexing=False
            )
        )
        assert config.include == ["custom/**/*.py"]
        assert config.embedding.model == "custom/model"
        assert config.embedding.batch_size == 20
        assert config.repomap.max_tokens == 8000
        assert config.delta.file_threshold == 10

    def test_oracle_config_defaults(self):
        """Test Oracle config with defaults."""
        config = OracleConfig()
        assert config.vault_url == "http://localhost:8000"
        assert config.synthesis_model == "anthropic/claude-sonnet-4"
        assert config.rerank_model == "openai/gpt-4o-mini"
        assert config.max_context_tokens == 16000

    def test_oracle_config_custom(self):
        """Test Oracle config with custom values."""
        config = OracleConfig(
            vault_url="https://custom.vault.url",
            synthesis_model="custom/model",
            rerank_model="custom/rerank",
            max_context_tokens=32000
        )
        assert config.vault_url == "https://custom.vault.url"
        assert config.synthesis_model == "custom/model"
        assert config.max_context_tokens == 32000

    def test_vlt_config_minimal(self):
        """Test minimal VltConfig (only project section)."""
        config = VltConfig(
            project=ProjectConfig(name="test", id="test")
        )
        assert config.project.name == "test"
        assert config.coderag is None
        assert config.oracle is None

    def test_vlt_config_full(self):
        """Test full VltConfig with all sections."""
        config = VltConfig(
            project=ProjectConfig(name="test", id="test"),
            coderag=CodeRAGConfig(),
            oracle=OracleConfig()
        )
        assert config.project.name == "test"
        assert config.coderag is not None
        assert config.oracle is not None


class TestTOMLParsing:
    """Test TOML file parsing."""

    def test_parse_minimal_toml(self):
        """Test parsing minimal vlt.toml (only project)."""
        toml_content = """
[project]
name = "minimal-project"
id = "minimal-project"
"""
        data = tomllib.loads(toml_content)
        config = VltConfig(**data)
        assert config.project.name == "minimal-project"
        assert config.coderag is None
        assert config.oracle is None

    def test_parse_full_toml(self):
        """Test parsing complete vlt.toml with all sections."""
        toml_content = """
[project]
name = "full-project"
id = "full-project"
description = "A full configuration"

[coderag]
include = ["src/**/*.py", "lib/**/*.py"]
exclude = ["**/node_modules/**", "**/__pycache__/**"]
languages = ["python", "typescript"]

[coderag.embedding]
model = "qwen/qwen3-embedding-8b"
batch_size = 10

[coderag.repomap]
max_tokens = 4000
include_signatures = true
include_docstrings = false

[coderag.delta]
file_threshold = 5
line_threshold = 1000
timeout_seconds = 300
jit_indexing = true

[oracle]
vault_url = "http://localhost:8000"
synthesis_model = "anthropic/claude-sonnet-4"
rerank_model = "openai/gpt-4o-mini"
max_context_tokens = 16000
"""
        data = tomllib.loads(toml_content)
        config = VltConfig(**data)

        assert config.project.name == "full-project"
        assert config.project.description == "A full configuration"

        assert config.coderag is not None
        assert config.coderag.include == ["src/**/*.py", "lib/**/*.py"]
        assert config.coderag.embedding.model == "qwen/qwen3-embedding-8b"
        assert config.coderag.repomap.max_tokens == 4000
        assert config.coderag.delta.file_threshold == 5

        assert config.oracle is not None
        assert config.oracle.vault_url == "http://localhost:8000"
        assert config.oracle.synthesis_model == "anthropic/claude-sonnet-4"

    def test_parse_partial_coderag(self):
        """Test parsing with only some coderag subsections."""
        toml_content = """
[project]
name = "partial-project"
id = "partial-project"

[coderag]
include = ["custom/**/*.py"]

[coderag.embedding]
model = "custom/model"
"""
        data = tomllib.loads(toml_content)
        config = VltConfig(**data)

        assert config.coderag is not None
        assert config.coderag.include == ["custom/**/*.py"]
        # Check that defaults are applied for missing fields
        assert config.coderag.exclude == ["**/node_modules/**", "**/__pycache__/**", "**/.git/**"]
        assert config.coderag.embedding.model == "custom/model"
        assert config.coderag.embedding.batch_size == 10  # Default
        # Check nested defaults
        assert config.coderag.repomap.max_tokens == 4000


class TestConfigFileOperations:
    """Test file-based configuration operations."""

    def test_create_vlt_toml(self):
        """Test creating vlt.toml file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            create_vlt_toml(path, "test-project", "test-project", "A test")

            toml_file = path / "vlt.toml"
            assert toml_file.exists()

            # Parse and validate
            with open(toml_file, "rb") as f:
                data = tomllib.load(f)

            config = VltConfig(**data)
            assert config.project.name == "test-project"
            assert config.project.id == "test-project"
            assert config.project.description == "A test"
            assert config.coderag is not None
            assert config.oracle is not None

    def test_find_vlt_toml_current_dir(self):
        """Test finding vlt.toml in current directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            create_vlt_toml(path, "test", "test")

            found = find_vlt_toml(path)
            assert found is not None
            assert found == path / "vlt.toml"

    def test_find_vlt_toml_parent_dir(self):
        """Test finding vlt.toml in parent directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            create_vlt_toml(root, "test", "test")

            # Create subdirectory
            subdir = root / "nested" / "deep"
            subdir.mkdir(parents=True)

            # Search from subdirectory
            found = find_vlt_toml(subdir)
            assert found is not None
            assert found == root / "vlt.toml"

    def test_find_vlt_toml_not_found(self):
        """Test when vlt.toml is not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            found = find_vlt_toml(path)
            assert found is None

    def test_load_vlt_config(self):
        """Test loading complete configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            create_vlt_toml(path, "test-load", "test-load", "Test loading")

            config = load_vlt_config(path)
            assert config is not None
            assert config.project.name == "test-load"
            assert config.coderag is not None
            assert config.oracle is not None

    def test_load_project_identity(self):
        """Test loading only project section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            create_vlt_toml(path, "test-project", "test-project")

            project = load_project_identity(path)
            assert project is not None
            assert project.name == "test-project"
            assert project.id == "test-project"

    def test_load_coderag_config(self):
        """Test loading CodeRAG configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            create_vlt_toml(path, "test", "test")

            config = load_coderag_config(path)
            assert config is not None
            assert config.include == ["src/**/*.py", "lib/**/*.py", "tests/**/*.py"]
            assert config.embedding.model == "qwen/qwen3-embedding-8b"

    def test_load_coderag_config_defaults_when_missing(self):
        """Test loading CodeRAG config returns defaults when section missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)

            # Create minimal toml without coderag section
            toml_content = """[project]
name = "minimal"
id = "minimal"
"""
            toml_file = path / "vlt.toml"
            with open(toml_file, "w") as f:
                f.write(toml_content)

            config = load_coderag_config(path)
            assert config is not None
            # Should return defaults
            assert config.include == ["src/**/*.py", "lib/**/*.py", "tests/**/*.py"]

    def test_load_oracle_config(self):
        """Test loading Oracle configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            create_vlt_toml(path, "test", "test")

            config = load_oracle_config(path)
            assert config is not None
            assert config.vault_url == "http://localhost:8000"
            assert config.synthesis_model == "anthropic/claude-sonnet-4"

    def test_load_oracle_config_defaults_when_missing(self):
        """Test loading Oracle config returns defaults when section missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)

            # Create minimal toml without oracle section
            toml_content = """[project]
name = "minimal"
id = "minimal"
"""
            toml_file = path / "vlt.toml"
            with open(toml_file, "w") as f:
                f.write(toml_content)

            config = load_oracle_config(path)
            assert config is not None
            # Should return defaults
            assert config.vault_url == "http://localhost:8000"

    def test_load_malformed_toml(self):
        """Test handling of malformed TOML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)

            # Create invalid TOML
            toml_file = path / "vlt.toml"
            with open(toml_file, "w") as f:
                f.write("this is not valid toml [[[")

            config = load_vlt_config(path)
            assert config is None  # Should gracefully handle error

    def test_load_missing_required_fields(self):
        """Test handling of missing required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)

            # Create TOML missing required project fields
            toml_file = path / "vlt.toml"
            with open(toml_file, "w") as f:
                f.write("[project]\n")  # Missing name and id

            config = load_vlt_config(path)
            assert config is None  # Should fail validation


class TestConfigIntegration:
    """Integration tests for configuration usage."""

    def test_typical_workflow(self):
        """Test typical configuration workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)

            # 1. Create vlt.toml
            create_vlt_toml(path, "my-project", "my-project", "My awesome project")

            # 2. Load project identity
            project = load_project_identity(path)
            assert project.name == "my-project"

            # 3. Load CodeRAG config
            coderag = load_coderag_config(path)
            assert coderag.embedding.model == "qwen/qwen3-embedding-8b"

            # 4. Load Oracle config
            oracle = load_oracle_config(path)
            assert oracle.max_context_tokens == 16000

    def test_config_from_subdirectory(self):
        """Test loading config from nested subdirectory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            create_vlt_toml(root, "root-project", "root-project")

            # Create deep nested structure
            deep_path = root / "src" / "core" / "modules"
            deep_path.mkdir(parents=True)

            # All loads should find the root vlt.toml
            project = load_project_identity(deep_path)
            assert project.name == "root-project"

            coderag = load_coderag_config(deep_path)
            assert coderag is not None

            oracle = load_oracle_config(deep_path)
            assert oracle is not None
