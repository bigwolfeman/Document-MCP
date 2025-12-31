"""Tool Executor - Dispatches tool calls to service implementations.

This service routes tool calls from the Oracle Agent to the appropriate
backend services (VaultService, IndexerService, ThreadService, OracleBridge).
It also handles schema loading and filtering by agent scope.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.thread import ThreadEntry
from .database import DatabaseService
from .indexer import IndexerService
from .oracle_bridge import OracleBridge
from .thread_service import ThreadService
from .vault import VaultService

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    Executes tool calls by routing to appropriate backend services.

    Supports both Oracle and Librarian agent scopes with different tool sets.
    Tool schemas are loaded from backend/prompts/tools.json with fallback
    to specs/009-oracle-agent/contracts/tools.json.
    """

    def __init__(
        self,
        vault_service: Optional[VaultService] = None,
        indexer_service: Optional[IndexerService] = None,
        thread_service: Optional[ThreadService] = None,
        oracle_bridge: Optional[OracleBridge] = None,
        db_service: Optional[DatabaseService] = None,
    ) -> None:
        """
        Initialize the tool executor with service dependencies.

        Args:
            vault_service: VaultService instance (created if None)
            indexer_service: IndexerService instance (created if None)
            thread_service: ThreadService instance (created if None)
            oracle_bridge: OracleBridge instance (created if None)
            db_service: DatabaseService instance for indexer (created if None)
        """
        self._db = db_service or DatabaseService()
        self.vault = vault_service or VaultService()
        self.indexer = indexer_service or IndexerService(self._db)
        self.threads = thread_service or ThreadService(self._db)
        self.oracle_bridge = oracle_bridge or OracleBridge()

        # Tool registry mapping tool names to handler methods
        self._tools: Dict[str, Any] = {
            # Code tools
            "search_code": self._search_code,
            "find_definition": self._find_definition,
            "find_references": self._find_references,
            "get_repo_map": self._get_repo_map,
            # Vault tools
            "vault_read": self._vault_read,
            "vault_write": self._vault_write,
            "vault_search": self._vault_search,
            "vault_list": self._vault_list,
            "vault_move": self._vault_move,
            "vault_create_index": self._vault_create_index,
            # Thread tools
            "thread_push": self._thread_push,
            "thread_read": self._thread_read,
            "thread_seek": self._thread_seek,
            "thread_list": self._thread_list,
            # Web tools
            "web_search": self._web_search,
            "web_fetch": self._web_fetch,
            # Meta tools
            "delegate_librarian": self._delegate_librarian,
        }

        # Cache for tool schemas
        self._schema_cache: Optional[Dict[str, Any]] = None

    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        user_id: str,
    ) -> str:
        """
        Execute a tool call and return the result as a JSON string.

        Args:
            name: Tool name to execute
            arguments: Tool arguments dictionary
            user_id: User ID for scoped operations

        Returns:
            JSON string containing the tool result or error
        """
        if name not in self._tools:
            logger.warning(f"Unknown tool requested: {name}")
            return json.dumps({"error": f"Unknown tool: {name}"})

        handler = self._tools[name]

        try:
            logger.info(
                f"Executing tool: {name}",
                extra={"user_id": user_id, "tool": name, "args_keys": list(arguments.keys())},
            )
            result = await handler(user_id, **arguments)
            return json.dumps(result, default=str)
        except FileNotFoundError as e:
            logger.warning(f"Tool {name} file not found: {e}")
            return json.dumps({"error": f"File not found: {str(e)}"})
        except ValueError as e:
            logger.warning(f"Tool {name} validation error: {e}")
            return json.dumps({"error": f"Invalid arguments: {str(e)}"})
        except Exception as e:
            logger.exception(f"Tool {name} execution failed: {e}")
            return json.dumps({"error": f"Tool execution failed: {str(e)}"})

    def get_tool_schemas(self, agent: str = "oracle") -> List[Dict[str, Any]]:
        """
        Get OpenRouter-compatible tool schemas filtered by agent scope.

        Args:
            agent: Agent type ("oracle" or "librarian")

        Returns:
            List of tool definitions in OpenRouter function calling format
        """
        if self._schema_cache is None:
            self._schema_cache = self._load_tool_schemas()

        tools_data = self._schema_cache.get("tools", [])

        # Filter tools by agent scope and format for OpenRouter
        filtered_tools = []
        for tool in tools_data:
            agent_scope = tool.get("agent_scope", ["oracle"])
            if agent in agent_scope:
                # Return only type and function fields (OpenRouter format)
                filtered_tools.append({
                    "type": tool.get("type", "function"),
                    "function": tool.get("function", {}),
                })

        logger.debug(f"Loaded {len(filtered_tools)} tools for agent '{agent}'")
        return filtered_tools

    def _load_tool_schemas(self) -> Dict[str, Any]:
        """
        Load tool schemas from JSON file.

        Tries backend/prompts/tools.json first, falls back to
        specs/009-oracle-agent/contracts/tools.json.

        Returns:
            Parsed JSON data containing tool definitions
        """
        # Primary location: backend/prompts/tools.json
        prompts_tools = Path(__file__).parent.parent.parent / "prompts" / "tools.json"

        # Fallback location: specs/009-oracle-agent/contracts/tools.json
        specs_tools = (
            Path(__file__).parent.parent.parent.parent
            / "specs"
            / "009-oracle-agent"
            / "contracts"
            / "tools.json"
        )

        tools_file = prompts_tools if prompts_tools.exists() else specs_tools

        if not tools_file.exists():
            logger.error(f"Tool schemas not found at {prompts_tools} or {specs_tools}")
            return {"tools": []}

        try:
            with open(tools_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"Loaded tool schemas from {tools_file}")
                return data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse tool schemas: {e}")
            return {"tools": []}

    # =========================================================================
    # Code Tool Implementations
    # =========================================================================

    async def _search_code(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        language: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Search the codebase using hybrid retrieval."""
        result = await self.oracle_bridge.search_code(
            query=query,
            limit=limit,
            language=language,
        )
        return result

    async def _find_definition(
        self,
        user_id: str,
        symbol: str,
        scope: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Find where a symbol is defined."""
        # Not yet fully implemented in OracleBridge
        return {"error": f"Tool not yet implemented: find_definition"}

    async def _find_references(
        self,
        user_id: str,
        symbol: str,
        limit: int = 20,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Find all usages of a symbol."""
        # Not yet fully implemented in OracleBridge
        return {"error": f"Tool not yet implemented: find_references"}

    async def _get_repo_map(
        self,
        user_id: str,
        scope: Optional[str] = None,
        max_tokens: int = 2000,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Get repository structure map."""
        # Not yet fully implemented in OracleBridge
        return {"error": f"Tool not yet implemented: get_repo_map"}

    # =========================================================================
    # Vault Tool Implementations
    # =========================================================================

    async def _vault_read(
        self,
        user_id: str,
        path: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Read a markdown note from the vault."""
        note = self.vault.read_note(user_id, path)
        return {
            "path": path,
            "title": note.get("title", ""),
            "content": note.get("body", ""),
            "metadata": note.get("metadata", {}),
        }

    async def _vault_write(
        self,
        user_id: str,
        path: str,
        body: str,
        title: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Create or update a markdown note in the vault."""
        note = self.vault.write_note(
            user_id,
            path,
            title=title,
            body=body,
        )
        # Index the note after writing
        self.indexer.index_note(user_id, note)
        return {
            "status": "ok",
            "path": path,
            "title": note.get("title", ""),
        }

    async def _vault_search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Search the documentation vault using full-text search."""
        results = self.indexer.search_notes(user_id, query, limit=limit)
        return {
            "query": query,
            "results": results,
            "count": len(results),
        }

    async def _vault_list(
        self,
        user_id: str,
        folder: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """List notes in a vault folder."""
        notes = self.vault.list_notes(user_id, folder=folder)
        return {
            "folder": folder or "/",
            "notes": notes,
            "count": len(notes),
        }

    async def _vault_move(
        self,
        user_id: str,
        old_path: str,
        new_path: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Move or rename a note (Librarian tool)."""
        # Not yet implemented - would need to update wikilinks
        return {"error": f"Tool not yet implemented: vault_move"}

    async def _vault_create_index(
        self,
        user_id: str,
        folder: str,
        title: Optional[str] = None,
        include_summaries: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Create an index.md file for a folder (Librarian tool)."""
        # Not yet implemented
        return {"error": f"Tool not yet implemented: vault_create_index"}

    # =========================================================================
    # Thread Tool Implementations
    # =========================================================================

    async def _thread_push(
        self,
        user_id: str,
        thread_id: str,
        content: str,
        entry_type: str = "thought",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Record a thought, decision, or finding to long-term memory."""
        # Create entry with unique ID
        entry_id = str(uuid.uuid4())
        timestamp = datetime.utcnow()

        # Get current max sequence for the thread
        thread = self.threads.get_thread(user_id, thread_id, include_entries=False)
        if thread is None:
            # Create the thread first with a project_id derived from user context
            # For now, use a placeholder project
            project_id = kwargs.get("project_id", "default")
            self.threads.create_or_update_thread(
                user_id=user_id,
                thread_id=thread_id,
                project_id=project_id,
                name=thread_id,
                status="active",
            )
            next_sequence = 0
        else:
            # Get highest sequence from existing entries
            sync_status = self.threads.get_sync_status(user_id, thread_id)
            next_sequence = (sync_status.last_synced_sequence + 1) if sync_status else 0

        # Create thread entry
        entry = ThreadEntry(
            entry_id=entry_id,
            sequence_id=next_sequence,
            content=f"[{entry_type}] {content}",
            author="oracle",
            timestamp=timestamp,
        )

        # Add entry to thread
        synced_count, last_seq = self.threads.add_entries(user_id, thread_id, [entry])

        return {
            "status": "ok",
            "thread_id": thread_id,
            "entry_id": entry_id,
            "sequence_id": next_sequence,
        }

    async def _thread_read(
        self,
        user_id: str,
        thread_id: str,
        limit: int = 10,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Read a thread to get context and summary of past work."""
        thread = self.threads.get_thread(
            user_id,
            thread_id,
            include_entries=True,
            entries_limit=limit,
        )

        if thread is None:
            return {
                "error": f"Thread not found: {thread_id}",
                "thread_id": thread_id,
            }

        # Convert entries to serializable format
        entries = []
        if thread.entries:
            entries = [
                {
                    "entry_id": e.entry_id,
                    "content": e.content,
                    "author": e.author,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in thread.entries
            ]

        return {
            "thread_id": thread.thread_id,
            "project_id": thread.project_id,
            "name": thread.name,
            "status": thread.status,
            "entries": entries,
            "entry_count": len(entries),
        }

    async def _thread_seek(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Search across all threads for relevant past context."""
        response = self.threads.search_threads(
            user_id,
            query,
            project_id=kwargs.get("project_id"),
            limit=limit,
        )

        # Convert results to serializable format
        results = [
            {
                "thread_id": r.thread_id,
                "entry_id": r.entry_id,
                "content": r.content,
                "author": r.author,
                "timestamp": r.timestamp.isoformat(),
                "score": r.score,
            }
            for r in response.results
        ]

        return {
            "query": query,
            "results": results,
            "total": response.total,
        }

    async def _thread_list(
        self,
        user_id: str,
        status: str = "active",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """List all threads for the current project."""
        # Map status filter
        status_filter = None if status == "all" else status

        response = self.threads.list_threads(
            user_id,
            project_id=kwargs.get("project_id"),
            status=status_filter,
            limit=kwargs.get("limit", 50),
            offset=kwargs.get("offset", 0),
        )

        # Convert threads to serializable format
        threads = [
            {
                "thread_id": t.thread_id,
                "project_id": t.project_id,
                "name": t.name,
                "status": t.status,
                "created_at": t.created_at.isoformat(),
                "updated_at": t.updated_at.isoformat(),
            }
            for t in response.threads
        ]

        return {
            "threads": threads,
            "total": response.total,
        }

    # =========================================================================
    # Web Tool Implementations
    # =========================================================================

    async def _web_search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Search the web for information."""
        # Not yet implemented
        return {"error": f"Tool not yet implemented: web_search"}

    async def _web_fetch(
        self,
        user_id: str,
        url: str,
        max_tokens: int = 1000,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Fetch and extract content from a URL."""
        # Not yet implemented
        return {"error": f"Tool not yet implemented: web_fetch"}

    # =========================================================================
    # Meta Tool Implementations
    # =========================================================================

    async def _delegate_librarian(
        self,
        user_id: str,
        task: str,
        files: Optional[List[str]] = None,
        folder: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Delegate a vault organization task to the Librarian subagent."""
        # Not yet implemented - would spawn Librarian agent
        return {"error": f"Tool not yet implemented: delegate_librarian"}


# Singleton instance for dependency injection
_tool_executor: Optional[ToolExecutor] = None


def get_tool_executor() -> ToolExecutor:
    """Get or create the tool executor singleton."""
    global _tool_executor
    if _tool_executor is None:
        _tool_executor = ToolExecutor()
    return _tool_executor


__all__ = ["ToolExecutor", "get_tool_executor"]
