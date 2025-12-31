"""Unit tests for PromptLoader service (009-oracle-agent T014)."""

from pathlib import Path

import pytest

from backend.src.services.prompt_loader import (
    PromptLoader,
    PromptLoaderError,
    DEFAULT_PROMPTS_DIR,
)


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """Create a temporary prompts directory with test templates."""
    prompts = tmp_path / "prompts"
    prompts.mkdir()

    # Create oracle subdirectory
    oracle_dir = prompts / "oracle"
    oracle_dir.mkdir()

    # Create test template with Jinja2 variables
    system_template = oracle_dir / "system.md"
    system_template.write_text(
        "# Oracle System\n\nProject: {{ project_id }}\nUser: {{ user_id }}"
    )

    # Create librarian subdirectory
    librarian_dir = prompts / "librarian"
    librarian_dir.mkdir()

    librarian_template = librarian_dir / "system.md"
    librarian_template.write_text(
        "# Librarian\n\nProject: {{ project_id or 'default' }}"
    )

    return prompts


@pytest.fixture
def loader(prompts_dir: Path) -> PromptLoader:
    """Create a PromptLoader with the test prompts directory."""
    return PromptLoader(prompts_dir=prompts_dir)


class TestPromptLoaderInit:
    """Tests for PromptLoader initialization."""

    def test_init_with_existing_directory(self, prompts_dir: Path) -> None:
        """Loader initializes with Jinja2 environment when directory exists."""
        loader = PromptLoader(prompts_dir=prompts_dir)

        assert loader.prompts_dir == prompts_dir
        assert loader.env is not None

    def test_init_with_nonexistent_directory(self, tmp_path: Path) -> None:
        """Loader falls back to inline prompts when directory doesn't exist."""
        nonexistent = tmp_path / "nonexistent"
        loader = PromptLoader(prompts_dir=nonexistent)

        assert loader.prompts_dir == nonexistent
        assert loader.env is None

    def test_default_prompts_dir_is_backend_prompts(self) -> None:
        """DEFAULT_PROMPTS_DIR points to backend/prompts/."""
        assert DEFAULT_PROMPTS_DIR.name == "prompts"
        assert DEFAULT_PROMPTS_DIR.parent.name == "backend"


class TestPromptLoaderLoad:
    """Tests for PromptLoader.load() method."""

    def test_load_template_from_filesystem(self, loader: PromptLoader) -> None:
        """load() renders template from filesystem with context variables."""
        result = loader.load(
            "oracle/system.md",
            {"project_id": "test-project", "user_id": "test-user"},
        )

        assert "Project: test-project" in result
        assert "User: test-user" in result

    def test_load_template_with_default_values(self, loader: PromptLoader) -> None:
        """load() handles Jinja2 default value syntax."""
        result = loader.load("librarian/system.md", {"project_id": None})

        assert "Project: default" in result

    def test_load_template_with_empty_context(self, loader: PromptLoader) -> None:
        """load() works with empty context dict."""
        result = loader.load("librarian/system.md", {})

        assert "# Librarian" in result
        assert "Project: default" in result

    def test_load_nonexistent_template_uses_fallback(
        self, prompts_dir: Path
    ) -> None:
        """load() falls back to inline prompt if template not found."""
        loader = PromptLoader(prompts_dir=prompts_dir)

        # oracle/synthesis.md doesn't exist in test fixtures but is in inline
        result = loader.load("oracle/synthesis.md", {"context_summary": "Test"})

        assert "Synthesis" in result or "context" in result.lower()


class TestPromptLoaderInlineFallback:
    """Tests for inline prompt fallback behavior."""

    def test_inline_fallback_oracle_system(self, tmp_path: Path) -> None:
        """Inline fallback provides oracle/system.md."""
        loader = PromptLoader(prompts_dir=tmp_path / "nonexistent")

        result = loader.load(
            "oracle/system.md",
            {"project_id": "fallback-test", "user_id": "test-user"},
        )

        assert "Oracle" in result
        assert "fallback-test" in result

    def test_inline_fallback_librarian_system(self, tmp_path: Path) -> None:
        """Inline fallback provides librarian/system.md."""
        loader = PromptLoader(prompts_dir=tmp_path / "nonexistent")

        result = loader.load(
            "librarian/system.md",
            {"project_id": "lib-test"},
        )

        assert "Librarian" in result
        assert "lib-test" in result

    def test_inline_fallback_raises_for_unknown_path(self, tmp_path: Path) -> None:
        """load() raises PromptLoaderError for unknown template path."""
        loader = PromptLoader(prompts_dir=tmp_path / "nonexistent")

        with pytest.raises(PromptLoaderError) as exc_info:
            loader.load("unknown/prompt.md", {})

        assert "Prompt not found" in str(exc_info.value)
        assert "unknown/prompt.md" in str(exc_info.value)


class TestPromptLoaderListAvailable:
    """Tests for PromptLoader.list_available() method."""

    def test_list_available_includes_filesystem_templates(
        self, loader: PromptLoader
    ) -> None:
        """list_available() returns templates found on filesystem."""
        available = loader.list_available()

        assert "oracle/system.md" in available["filesystem"]
        assert "librarian/system.md" in available["filesystem"]

    def test_list_available_includes_inline_templates(
        self, loader: PromptLoader
    ) -> None:
        """list_available() returns all inline fallback templates."""
        available = loader.list_available()

        assert "oracle/system.md" in available["inline"]
        assert "oracle/synthesis.md" in available["inline"]
        assert "oracle/compression.md" in available["inline"]
        assert "librarian/system.md" in available["inline"]

    def test_list_available_with_nonexistent_dir(self, tmp_path: Path) -> None:
        """list_available() returns empty filesystem list when dir doesn't exist."""
        loader = PromptLoader(prompts_dir=tmp_path / "nonexistent")
        available = loader.list_available()

        assert available["filesystem"] == []
        assert len(available["inline"]) > 0


class TestPromptLoaderHotReload:
    """Tests for hot-reload behavior."""

    def test_template_changes_are_reflected_with_new_loader(
        self, prompts_dir: Path
    ) -> None:
        """Creating a new loader picks up template changes."""
        # First loader
        loader1 = PromptLoader(prompts_dir=prompts_dir)
        result1 = loader1.load("oracle/system.md", {"project_id": "v1"})
        assert "Project: v1" in result1

        # Modify the template
        template_file = prompts_dir / "oracle" / "system.md"
        template_file.write_text("# Updated\n\nVersion: {{ project_id }}")

        # New loader sees the changes
        loader2 = PromptLoader(prompts_dir=prompts_dir)
        result2 = loader2.load("oracle/system.md", {"project_id": "v2"})
        assert "Version: v2" in result2
        assert "Updated" in result2
