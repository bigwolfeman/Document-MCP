"""Unit tests for ToolExecutor service (009-oracle-agent T015)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.services.tool_executor import ToolExecutor, get_tool_executor


@pytest.fixture
def mock_services():
    """Create mock services for ToolExecutor."""
    vault = MagicMock()
    indexer = MagicMock()
    threads = MagicMock()
    oracle_bridge = MagicMock()
    db = MagicMock()

    return {
        "vault_service": vault,
        "indexer_service": indexer,
        "thread_service": threads,
        "oracle_bridge": oracle_bridge,
        "db_service": db,
    }


@pytest.fixture
def executor(mock_services) -> ToolExecutor:
    """Create a ToolExecutor with mocked dependencies."""
    return ToolExecutor(**mock_services)


class TestToolExecutorInit:
    """Tests for ToolExecutor initialization."""

    def test_init_with_provided_services(self, mock_services) -> None:
        """Executor uses provided service instances."""
        executor = ToolExecutor(**mock_services)

        assert executor.vault is mock_services["vault_service"]
        assert executor.indexer is mock_services["indexer_service"]
        assert executor.threads is mock_services["thread_service"]

    def test_init_creates_default_services_when_none_provided(self) -> None:
        """Executor creates default services when none provided."""
        # This will create real service instances
        executor = ToolExecutor()

        assert executor.vault is not None
        assert executor.indexer is not None
        assert executor.threads is not None


class TestToolExecutorGetToolSchemas:
    """Tests for get_tool_schemas() method."""

    def test_get_oracle_tools(self, executor: ToolExecutor) -> None:
        """get_tool_schemas('oracle') returns Oracle-scoped tools."""
        tools = executor.get_tool_schemas(agent="oracle")

        # Should have multiple tools
        assert len(tools) > 0

        # All should be function type
        for tool in tools:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name" in tool["function"]

        # Check for expected Oracle tools
        tool_names = [t["function"]["name"] for t in tools]
        assert "search_code" in tool_names
        assert "vault_read" in tool_names
        assert "thread_push" in tool_names

    def test_get_librarian_tools(self, executor: ToolExecutor) -> None:
        """get_tool_schemas('librarian') returns Librarian-scoped tools."""
        tools = executor.get_tool_schemas(agent="librarian")

        tool_names = [t["function"]["name"] for t in tools]

        # Librarian should have fewer tools
        assert len(tools) < len(executor.get_tool_schemas(agent="oracle"))

        # Librarian-only tools
        assert "vault_move" in tool_names
        assert "vault_create_index" in tool_names

        # Both agents have these
        assert "vault_read" in tool_names
        assert "vault_search" in tool_names

        # Oracle-only tools should not be present
        assert "thread_push" not in tool_names
        assert "web_search" not in tool_names

    def test_schemas_are_cached(self, executor: ToolExecutor) -> None:
        """Tool schemas are cached after first load."""
        tools1 = executor.get_tool_schemas(agent="oracle")
        tools2 = executor.get_tool_schemas(agent="oracle")

        # Same cache, filtered each time
        assert executor._schema_cache is not None


class TestToolExecutorExecute:
    """Tests for execute() method."""

    @pytest.mark.asyncio
    async def test_execute_unknown_tool_returns_error(
        self, executor: ToolExecutor
    ) -> None:
        """execute() returns error JSON for unknown tool."""
        result = await executor.execute("unknown_tool", {}, "user-123")

        data = json.loads(result)
        assert "error" in data
        assert "Unknown tool" in data["error"]

    @pytest.mark.asyncio
    async def test_execute_vault_read_calls_service(
        self, executor: ToolExecutor, mock_services
    ) -> None:
        """execute('vault_read') calls VaultService.read_note()."""
        mock_services["vault_service"].read_note.return_value = {
            "title": "Test Note",
            "body": "Content here",
            "metadata": {},
        }

        result = await executor.execute(
            "vault_read",
            {"path": "test/note.md"},
            "user-123",
        )

        data = json.loads(result)
        assert data["path"] == "test/note.md"
        assert data["title"] == "Test Note"
        assert data["content"] == "Content here"

        mock_services["vault_service"].read_note.assert_called_once_with(
            "user-123", "test/note.md"
        )

    @pytest.mark.asyncio
    async def test_execute_vault_search_calls_indexer(
        self, executor: ToolExecutor, mock_services
    ) -> None:
        """execute('vault_search') calls IndexerService.search_notes()."""
        mock_services["indexer_service"].search_notes.return_value = [
            {"path": "result1.md", "score": 0.9},
            {"path": "result2.md", "score": 0.8},
        ]

        result = await executor.execute(
            "vault_search",
            {"query": "test query", "limit": 5},
            "user-123",
        )

        data = json.loads(result)
        assert data["query"] == "test query"
        assert data["count"] == 2
        assert len(data["results"]) == 2

    @pytest.mark.asyncio
    async def test_execute_search_code_calls_oracle_bridge(
        self, executor: ToolExecutor, mock_services
    ) -> None:
        """execute('search_code') calls OracleBridge.search_code()."""
        mock_services["oracle_bridge"].search_code = AsyncMock(
            return_value={"results": [{"file": "test.py"}]}
        )

        result = await executor.execute(
            "search_code",
            {"query": "function definition", "limit": 5},
            "user-123",
        )

        data = json.loads(result)
        assert "results" in data

        mock_services["oracle_bridge"].search_code.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_handles_file_not_found(
        self, executor: ToolExecutor, mock_services
    ) -> None:
        """execute() returns error for FileNotFoundError."""
        mock_services["vault_service"].read_note.side_effect = FileNotFoundError(
            "Note not found"
        )

        result = await executor.execute(
            "vault_read",
            {"path": "missing.md"},
            "user-123",
        )

        data = json.loads(result)
        assert "error" in data
        assert "File not found" in data["error"]

    @pytest.mark.asyncio
    async def test_execute_handles_generic_exception(
        self, executor: ToolExecutor, mock_services
    ) -> None:
        """execute() returns error for generic exceptions."""
        mock_services["vault_service"].read_note.side_effect = Exception(
            "Something went wrong"
        )

        result = await executor.execute(
            "vault_read",
            {"path": "test.md"},
            "user-123",
        )

        data = json.loads(result)
        assert "error" in data
        assert "execution failed" in data["error"]


class TestToolExecutorUnimplementedTools:
    """Tests for placeholder tool implementations."""

    @pytest.mark.asyncio
    async def test_find_definition_returns_not_implemented(
        self, executor: ToolExecutor
    ) -> None:
        """find_definition returns placeholder error."""
        result = await executor.execute(
            "find_definition",
            {"symbol": "TestClass"},
            "user-123",
        )

        data = json.loads(result)
        assert "error" in data
        assert "not yet implemented" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_web_search_returns_not_implemented(
        self, executor: ToolExecutor
    ) -> None:
        """web_search returns placeholder error."""
        result = await executor.execute(
            "web_search",
            {"query": "python docs"},
            "user-123",
        )

        data = json.loads(result)
        assert "error" in data
        assert "not yet implemented" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_delegate_librarian_returns_not_implemented(
        self, executor: ToolExecutor
    ) -> None:
        """delegate_librarian returns placeholder error."""
        result = await executor.execute(
            "delegate_librarian",
            {"task": "organize docs"},
            "user-123",
        )

        data = json.loads(result)
        assert "error" in data
        assert "not yet implemented" in data["error"].lower()


class TestToolExecutorSingleton:
    """Tests for singleton pattern."""

    def test_get_tool_executor_returns_singleton(self) -> None:
        """get_tool_executor() returns the same instance."""
        # Clear any existing singleton
        import backend.src.services.tool_executor as te_module

        te_module._tool_executor = None

        executor1 = get_tool_executor()
        executor2 = get_tool_executor()

        assert executor1 is executor2

        # Clean up
        te_module._tool_executor = None
