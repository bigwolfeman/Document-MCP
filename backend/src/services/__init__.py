"""Service layer for business logic and external integrations."""

from .auth import AuthError, AuthService
from .config import AppConfig, get_config, reload_config
from .database import DatabaseService, init_database
from .indexer import IndexerService, normalize_slug, normalize_tag
from .oracle_bridge import OracleBridge, OracleBridgeError
from .oracle_context_service import (
    OracleContextService,
    OracleContextServiceError,
    get_context_service,
)
from .prompt_loader import PromptLoader, PromptLoaderError
from .thread_retriever import ThreadRetriever, get_thread_retriever
from .thread_service import ThreadService, get_thread_service
from .tool_executor import ToolExecutor, get_tool_executor
from .vault import VaultNote, VaultService, sanitize_path, validate_note_path

__all__ = [
    "AppConfig",
    "get_config",
    "reload_config",
    "DatabaseService",
    "init_database",
    "AuthService",
    "AuthError",
    "VaultService",
    "VaultNote",
    "sanitize_path",
    "validate_note_path",
    "IndexerService",
    "normalize_slug",
    "normalize_tag",
    "OracleBridge",
    "OracleBridgeError",
    "OracleContextService",
    "OracleContextServiceError",
    "get_context_service",
    "PromptLoader",
    "PromptLoaderError",
    "ThreadRetriever",
    "get_thread_retriever",
    "ThreadService",
    "get_thread_service",
    "ToolExecutor",
    "get_tool_executor",
]
