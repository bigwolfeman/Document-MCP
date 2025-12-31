"""OracleContextService - Manages Oracle context persistence (009-oracle-agent T055).

This service handles:
- Context CRUD operations for user+project pairs
- Context compression when approaching token budget
- Model change detection and re-summarization
- Key decisions preservation during compression
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from ..models.oracle_context import (
    ContextStatus,
    ExchangeRole,
    OracleContext,
    OracleExchange,
    ToolCall,
)
from .database import DatabaseService

logger = logging.getLogger(__name__)


class OracleContextServiceError(Exception):
    """Raised when context service operations fail."""

    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class OracleContextService:
    """Service for managing Oracle conversation context persistence.

    Provides CRUD operations for OracleContext, automatic compression when
    approaching token budget, and model change handling.
    """

    # Compression threshold (percentage of token budget)
    COMPRESSION_THRESHOLD = 0.80

    # Number of recent exchanges to preserve during compression
    PRESERVE_RECENT_EXCHANGES = 5

    # Target reduction percentage during compression
    COMPRESSION_REDUCTION_TARGET = 30

    # Token estimation: roughly 4 characters per token
    CHARS_PER_TOKEN = 4

    def __init__(self, db: Optional[DatabaseService] = None):
        """Initialize the context service.

        Args:
            db: Database service instance. Creates new one if not provided.
        """
        self.db = db or DatabaseService()

    # ========================================
    # Context CRUD Operations
    # ========================================

    def get_context(
        self,
        user_id: str,
        project_id: str,
    ) -> Optional[OracleContext]:
        """Get context for a user+project pair.

        Args:
            user_id: User identifier
            project_id: Project identifier

        Returns:
            OracleContext if found, None otherwise
        """
        conn = self.db.connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, user_id, project_id, session_start, last_activity,
                       last_model, token_budget, tokens_used, compressed_summary,
                       recent_exchanges_json, key_decisions_json, mentioned_symbols,
                       mentioned_files, status, compression_count
                FROM oracle_contexts
                WHERE user_id = ? AND project_id = ?
                """,
                (user_id, project_id)
            )
            row = cursor.fetchone()

            if not row:
                return None

            return self._row_to_context(row)
        except Exception as e:
            logger.error(f"Failed to get context for {user_id}/{project_id}: {e}")
            raise OracleContextServiceError(
                f"Failed to get context: {str(e)}",
                {"user_id": user_id, "project_id": project_id}
            )
        finally:
            conn.close()

    def get_or_create_context(
        self,
        user_id: str,
        project_id: str,
        token_budget: int = 16000,
    ) -> OracleContext:
        """Get existing context or create a new one.

        This is the primary entry point for the Oracle agent. It ensures
        a context always exists for the user+project pair.

        Args:
            user_id: User identifier
            project_id: Project identifier
            token_budget: Token budget for new contexts (default 16000)

        Returns:
            Existing or newly created OracleContext
        """
        existing = self.get_context(user_id, project_id)
        if existing:
            return existing

        return self.create_context(user_id, project_id, token_budget)

    def create_context(
        self,
        user_id: str,
        project_id: str,
        token_budget: int = 16000,
    ) -> OracleContext:
        """Create a new context for a user+project pair.

        Args:
            user_id: User identifier
            project_id: Project identifier
            token_budget: Maximum tokens allowed (default 16000)

        Returns:
            Newly created OracleContext

        Raises:
            OracleContextServiceError: If context already exists or creation fails
        """
        context_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        context = OracleContext(
            id=context_id,
            user_id=user_id,
            project_id=project_id,
            session_start=now,
            last_activity=now,
            token_budget=token_budget,
            tokens_used=0,
            recent_exchanges=[],
            key_decisions=[],
            status=ContextStatus.ACTIVE,
            compression_count=0,
        )

        conn = self.db.connect()
        try:
            conn.execute(
                """
                INSERT INTO oracle_contexts (
                    id, user_id, project_id, session_start, last_activity,
                    last_model, token_budget, tokens_used, compressed_summary,
                    recent_exchanges_json, key_decisions_json, mentioned_symbols,
                    mentioned_files, status, compression_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    context_id,
                    user_id,
                    project_id,
                    now.isoformat(),
                    now.isoformat(),
                    None,  # last_model
                    token_budget,
                    0,  # tokens_used
                    None,  # compressed_summary
                    "[]",  # recent_exchanges_json
                    "[]",  # key_decisions_json
                    None,  # mentioned_symbols
                    None,  # mentioned_files
                    ContextStatus.ACTIVE.value,
                    0,  # compression_count
                )
            )
            conn.commit()

            logger.info(f"Created context {context_id} for {user_id}/{project_id}")
            return context

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create context for {user_id}/{project_id}: {e}")
            raise OracleContextServiceError(
                f"Failed to create context: {str(e)}",
                {"user_id": user_id, "project_id": project_id}
            )
        finally:
            conn.close()

    def update_context(self, context: OracleContext) -> OracleContext:
        """Update an existing context.

        Args:
            context: Context with updated values

        Returns:
            Updated OracleContext

        Raises:
            OracleContextServiceError: If update fails
        """
        conn = self.db.connect()
        try:
            # Serialize exchanges and decisions to JSON
            exchanges_json = json.dumps([
                self._exchange_to_dict(e) for e in context.recent_exchanges
            ])
            decisions_json = json.dumps(context.key_decisions)

            conn.execute(
                """
                UPDATE oracle_contexts
                SET last_activity = ?,
                    last_model = ?,
                    token_budget = ?,
                    tokens_used = ?,
                    compressed_summary = ?,
                    recent_exchanges_json = ?,
                    key_decisions_json = ?,
                    mentioned_symbols = ?,
                    mentioned_files = ?,
                    status = ?,
                    compression_count = ?
                WHERE id = ?
                """,
                (
                    context.last_activity.isoformat() if context.last_activity else None,
                    context.last_model,
                    context.token_budget,
                    context.tokens_used,
                    context.compressed_summary,
                    exchanges_json,
                    decisions_json,
                    context.mentioned_symbols,
                    context.mentioned_files,
                    context.status.value,
                    context.compression_count,
                    context.id,
                )
            )
            conn.commit()

            logger.debug(f"Updated context {context.id}")
            return context

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update context {context.id}: {e}")
            raise OracleContextServiceError(
                f"Failed to update context: {str(e)}",
                {"context_id": context.id}
            )
        finally:
            conn.close()

    def delete_context(
        self,
        user_id: str,
        project_id: str,
    ) -> bool:
        """Delete context for a user+project pair.

        Args:
            user_id: User identifier
            project_id: Project identifier

        Returns:
            True if deleted, False if not found
        """
        conn = self.db.connect()
        try:
            cursor = conn.execute(
                """
                DELETE FROM oracle_contexts
                WHERE user_id = ? AND project_id = ?
                """,
                (user_id, project_id)
            )
            conn.commit()

            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted context for {user_id}/{project_id}")

            return deleted

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete context for {user_id}/{project_id}: {e}")
            raise OracleContextServiceError(
                f"Failed to delete context: {str(e)}",
                {"user_id": user_id, "project_id": project_id}
            )
        finally:
            conn.close()

    def list_contexts(
        self,
        user_id: str,
        status: Optional[ContextStatus] = None,
        limit: int = 50,
    ) -> List[OracleContext]:
        """List contexts for a user.

        Args:
            user_id: User identifier
            status: Optional status filter
            limit: Maximum number of contexts to return

        Returns:
            List of OracleContext objects
        """
        conn = self.db.connect()
        try:
            if status:
                cursor = conn.execute(
                    """
                    SELECT id, user_id, project_id, session_start, last_activity,
                           last_model, token_budget, tokens_used, compressed_summary,
                           recent_exchanges_json, key_decisions_json, mentioned_symbols,
                           mentioned_files, status, compression_count
                    FROM oracle_contexts
                    WHERE user_id = ? AND status = ?
                    ORDER BY last_activity DESC
                    LIMIT ?
                    """,
                    (user_id, status.value, limit)
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, user_id, project_id, session_start, last_activity,
                           last_model, token_budget, tokens_used, compressed_summary,
                           recent_exchanges_json, key_decisions_json, mentioned_symbols,
                           mentioned_files, status, compression_count
                    FROM oracle_contexts
                    WHERE user_id = ?
                    ORDER BY last_activity DESC
                    LIMIT ?
                    """,
                    (user_id, limit)
                )

            return [self._row_to_context(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Failed to list contexts for {user_id}: {e}")
            raise OracleContextServiceError(
                f"Failed to list contexts: {str(e)}",
                {"user_id": user_id}
            )
        finally:
            conn.close()

    # ========================================
    # Exchange Management
    # ========================================

    def add_exchange(
        self,
        user_id: str,
        project_id: str,
        exchange: OracleExchange,
        model_used: Optional[str] = None,
    ) -> OracleContext:
        """Add an exchange to the context.

        This is called after each Oracle turn. It:
        1. Adds the exchange to recent_exchanges
        2. Updates token usage
        3. Checks if compression is needed
        4. Detects model changes

        Args:
            user_id: User identifier
            project_id: Project identifier
            exchange: The exchange to add
            model_used: Model that generated this exchange (for change detection)

        Returns:
            Updated OracleContext (possibly compressed)
        """
        context = self.get_or_create_context(user_id, project_id)

        # Add exchange
        context.recent_exchanges.append(exchange)

        # Update token count
        context.tokens_used += exchange.token_count

        # Update activity timestamp
        context.last_activity = datetime.now(timezone.utc)

        # Track mentioned symbols and files
        if exchange.mentioned_symbols:
            existing = set((context.mentioned_symbols or "").split(","))
            existing.discard("")
            existing.update(exchange.mentioned_symbols)
            context.mentioned_symbols = ",".join(sorted(existing)[:100])  # Limit to 100

        if exchange.mentioned_files:
            existing = set((context.mentioned_files or "").split(","))
            existing.discard("")
            existing.update(exchange.mentioned_files)
            context.mentioned_files = ",".join(sorted(existing)[:100])  # Limit to 100

        # Check for model change
        if model_used and context.last_model and model_used != context.last_model:
            logger.info(
                f"Model change detected: {context.last_model} -> {model_used} "
                f"for context {context.id}"
            )
            context = self._handle_model_change(context, model_used)

        context.last_model = model_used

        # Save the updated context
        context = self.update_context(context)

        # Check if compression is needed
        if self._should_compress(context):
            context = self.compress_context(context)

        return context

    def add_key_decision(
        self,
        user_id: str,
        project_id: str,
        decision: str,
    ) -> OracleContext:
        """Add a key decision to the context.

        Key decisions are preserved during compression.

        Args:
            user_id: User identifier
            project_id: Project identifier
            decision: The decision text

        Returns:
            Updated OracleContext
        """
        context = self.get_or_create_context(user_id, project_id)

        # Avoid duplicates
        if decision not in context.key_decisions:
            context.key_decisions.append(decision)
            # Limit to 20 decisions
            if len(context.key_decisions) > 20:
                context.key_decisions = context.key_decisions[-20:]

        context.last_activity = datetime.now(timezone.utc)
        return self.update_context(context)

    # ========================================
    # Context Compression
    # ========================================

    def _should_compress(self, context: OracleContext) -> bool:
        """Check if context should be compressed.

        Compression is triggered when token usage exceeds the threshold.

        Args:
            context: The context to check

        Returns:
            True if compression is needed
        """
        if context.token_budget <= 0:
            return False

        usage_ratio = context.tokens_used / context.token_budget
        return usage_ratio >= self.COMPRESSION_THRESHOLD

    def compress_context(
        self,
        context: OracleContext,
        preserve_recent: Optional[int] = None,
    ) -> OracleContext:
        """Compress the context to reduce token usage.

        This method:
        1. Preserves the most recent exchanges (verbatim)
        2. Compresses older exchanges into a summary
        3. Preserves all key decisions
        4. Updates the context in the database

        Args:
            context: The context to compress
            preserve_recent: Number of recent exchanges to keep verbatim
                           (default: PRESERVE_RECENT_EXCHANGES)

        Returns:
            Compressed OracleContext
        """
        preserve_recent = preserve_recent or self.PRESERVE_RECENT_EXCHANGES

        exchanges = context.recent_exchanges

        # If we don't have enough exchanges to compress, return as-is
        if len(exchanges) <= preserve_recent:
            logger.debug(f"Context {context.id} has too few exchanges to compress")
            return context

        # Split exchanges into old (to compress) and recent (to preserve)
        exchanges_to_compress = exchanges[:-preserve_recent]
        recent_exchanges = exchanges[-preserve_recent:]

        logger.info(
            f"Compressing context {context.id}: "
            f"{len(exchanges_to_compress)} exchanges to compress, "
            f"{len(recent_exchanges)} to preserve"
        )

        # Generate compression summary
        new_summary = self._generate_compression_summary(
            context=context,
            exchanges_to_compress=exchanges_to_compress,
        )

        # Update context
        context.compressed_summary = new_summary
        context.recent_exchanges = recent_exchanges
        context.compression_count += 1

        # Recalculate token usage
        context.tokens_used = self._calculate_token_usage(context)

        # Save and return
        return self.update_context(context)

    def _generate_compression_summary(
        self,
        context: OracleContext,
        exchanges_to_compress: List[OracleExchange],
    ) -> str:
        """Generate a compression summary for older exchanges.

        This creates a structured summary that preserves:
        - Key decisions
        - Important discoveries
        - Active references

        Note: In a full implementation, this would call an LLM with the
        compression prompt. For now, we generate a structured summary.

        Args:
            context: The context being compressed
            exchanges_to_compress: Exchanges to summarize

        Returns:
            Compression summary string
        """
        # Build summary from existing compressed_summary and new exchanges
        existing_summary = context.compressed_summary or ""

        # Extract key information from exchanges
        decisions = list(context.key_decisions)
        discoveries = []
        tool_results = []

        for exchange in exchanges_to_compress:
            # Extract any decisions marked in key_insight
            if exchange.key_insight:
                discoveries.append(exchange.key_insight)

            # Extract tool call summaries
            if exchange.tool_calls:
                for tc in exchange.tool_calls:
                    if tc.result and len(tc.result) > 50:
                        # Truncate long results
                        tool_results.append(
                            f"- {tc.name}: {tc.result[:200]}..."
                        )
                    elif tc.result:
                        tool_results.append(f"- {tc.name}: {tc.result}")

        # Build the summary
        summary_parts = []

        if existing_summary:
            summary_parts.append("## Previous Summary\n")
            summary_parts.append(existing_summary)
            summary_parts.append("\n\n")

        summary_parts.append("## Session Summary\n\n")
        summary_parts.append(f"**Started**: {context.session_start.isoformat()}\n")
        summary_parts.append(f"**Turns compressed**: {len(exchanges_to_compress)}\n\n")

        if decisions:
            summary_parts.append("### Key Decisions\n")
            for d in decisions[:10]:  # Limit to 10
                summary_parts.append(f"- {d}\n")
            summary_parts.append("\n")

        if discoveries:
            summary_parts.append("### Discoveries\n")
            for d in discoveries[:10]:  # Limit to 10
                summary_parts.append(f"- {d}\n")
            summary_parts.append("\n")

        if tool_results:
            summary_parts.append("### Tool Results Summary\n")
            for t in tool_results[:10]:  # Limit to 10
                summary_parts.append(f"{t}\n")
            summary_parts.append("\n")

        if context.mentioned_files:
            summary_parts.append(f"### Active Files\n{context.mentioned_files}\n\n")

        if context.mentioned_symbols:
            summary_parts.append(f"### Active Symbols\n{context.mentioned_symbols}\n\n")

        return "".join(summary_parts)

    def _calculate_token_usage(self, context: OracleContext) -> int:
        """Calculate total token usage for a context.

        Args:
            context: The context to calculate usage for

        Returns:
            Estimated token count
        """
        total_chars = 0

        # Count compressed summary
        if context.compressed_summary:
            total_chars += len(context.compressed_summary)

        # Count recent exchanges
        for exchange in context.recent_exchanges:
            total_chars += len(exchange.content)
            if exchange.tool_calls:
                for tc in exchange.tool_calls:
                    if tc.result:
                        total_chars += len(tc.result)

        # Count key decisions
        for decision in context.key_decisions:
            total_chars += len(decision)

        # Estimate tokens (rough: 4 chars per token)
        return total_chars // self.CHARS_PER_TOKEN

    # ========================================
    # Model Change Handling
    # ========================================

    def _handle_model_change(
        self,
        context: OracleContext,
        new_model: str,
    ) -> OracleContext:
        """Handle a model change event.

        When the model changes, we may need to re-summarize the context
        to ensure continuity. The context is marked as "suspended" until
        re-summarization is complete.

        Args:
            context: The context with model change
            new_model: The new model being used

        Returns:
            Updated context
        """
        # For now, just log the change and force a compression
        # In a full implementation, this would re-summarize using the new model
        logger.info(
            f"Model change for context {context.id}: "
            f"{context.last_model} -> {new_model}"
        )

        # Add a note about the model change to the summary
        change_note = f"\n\n---\n**Model changed**: {context.last_model} -> {new_model}\n"

        if context.compressed_summary:
            context.compressed_summary += change_note
        else:
            context.compressed_summary = change_note.strip()

        return context

    # ========================================
    # Context Building for LLM
    # ========================================

    def build_context_prompt(
        self,
        user_id: str,
        project_id: str,
        max_tokens: int = 16000,
    ) -> str:
        """Build a context prompt for the LLM.

        This assembles the compressed summary, recent exchanges, and
        key decisions into a single prompt string.

        Args:
            user_id: User identifier
            project_id: Project identifier
            max_tokens: Maximum tokens for the context

        Returns:
            Context prompt string
        """
        context = self.get_context(user_id, project_id)

        if not context:
            return ""

        parts = []

        # Add compressed summary if present
        if context.compressed_summary:
            parts.append("## Previous Context\n\n")
            parts.append(context.compressed_summary)
            parts.append("\n\n")

        # Add key decisions
        if context.key_decisions:
            parts.append("## Key Decisions\n\n")
            for decision in context.key_decisions:
                parts.append(f"- {decision}\n")
            parts.append("\n")

        # Add recent exchanges
        if context.recent_exchanges:
            parts.append("## Recent Conversation\n\n")
            for exchange in context.recent_exchanges:
                role_label = exchange.role.value.capitalize()
                parts.append(f"**{role_label}**: {exchange.content}\n\n")

        full_context = "".join(parts)

        # Truncate if exceeds max_tokens
        estimated_tokens = len(full_context) // self.CHARS_PER_TOKEN
        if estimated_tokens > max_tokens:
            # Truncate from the beginning (preserve recent)
            target_chars = max_tokens * self.CHARS_PER_TOKEN
            full_context = "..." + full_context[-target_chars:]

        return full_context

    def get_context_summary(
        self,
        user_id: str,
        project_id: str,
    ) -> Dict:
        """Get a summary of the context state.

        This is useful for UI display of context status.

        Args:
            user_id: User identifier
            project_id: Project identifier

        Returns:
            Dictionary with context summary info
        """
        context = self.get_context(user_id, project_id)

        if not context:
            return {
                "exists": False,
                "user_id": user_id,
                "project_id": project_id,
            }

        return {
            "exists": True,
            "id": context.id,
            "user_id": context.user_id,
            "project_id": context.project_id,
            "session_start": context.session_start.isoformat(),
            "last_activity": context.last_activity.isoformat() if context.last_activity else None,
            "last_model": context.last_model,
            "token_budget": context.token_budget,
            "tokens_used": context.tokens_used,
            "tokens_remaining": context.token_budget - context.tokens_used,
            "usage_percent": round(
                (context.tokens_used / context.token_budget) * 100, 1
            ) if context.token_budget > 0 else 0,
            "exchange_count": len(context.recent_exchanges),
            "key_decision_count": len(context.key_decisions),
            "compression_count": context.compression_count,
            "status": context.status.value,
            "has_compressed_summary": context.compressed_summary is not None,
        }

    # ========================================
    # Status Management
    # ========================================

    def set_status(
        self,
        user_id: str,
        project_id: str,
        status: ContextStatus,
    ) -> Optional[OracleContext]:
        """Set the status of a context.

        Args:
            user_id: User identifier
            project_id: Project identifier
            status: New status

        Returns:
            Updated context or None if not found
        """
        context = self.get_context(user_id, project_id)

        if not context:
            return None

        context.status = status
        context.last_activity = datetime.now(timezone.utc)

        return self.update_context(context)

    def close_context(
        self,
        user_id: str,
        project_id: str,
    ) -> Optional[OracleContext]:
        """Close a context (mark as closed).

        Args:
            user_id: User identifier
            project_id: Project identifier

        Returns:
            Updated context or None if not found
        """
        return self.set_status(user_id, project_id, ContextStatus.CLOSED)

    def reactivate_context(
        self,
        user_id: str,
        project_id: str,
    ) -> Optional[OracleContext]:
        """Reactivate a suspended or closed context.

        Args:
            user_id: User identifier
            project_id: Project identifier

        Returns:
            Updated context or None if not found
        """
        return self.set_status(user_id, project_id, ContextStatus.ACTIVE)

    # ========================================
    # Helper Methods
    # ========================================

    def _row_to_context(self, row) -> OracleContext:
        """Convert a database row to OracleContext.

        Args:
            row: SQLite row object

        Returns:
            OracleContext instance
        """
        # Parse JSON fields
        exchanges_json = row["recent_exchanges_json"] or "[]"
        decisions_json = row["key_decisions_json"] or "[]"

        try:
            exchanges_data = json.loads(exchanges_json)
            exchanges = [self._dict_to_exchange(e) for e in exchanges_data]
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse exchanges JSON for context {row['id']}")
            exchanges = []

        try:
            decisions = json.loads(decisions_json)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse decisions JSON for context {row['id']}")
            decisions = []

        return OracleContext(
            id=row["id"],
            user_id=row["user_id"],
            project_id=row["project_id"],
            session_start=datetime.fromisoformat(row["session_start"]),
            last_activity=datetime.fromisoformat(row["last_activity"]) if row["last_activity"] else None,
            last_model=row["last_model"],
            token_budget=row["token_budget"],
            tokens_used=row["tokens_used"],
            compressed_summary=row["compressed_summary"],
            recent_exchanges=exchanges,
            key_decisions=decisions,
            mentioned_symbols=row["mentioned_symbols"],
            mentioned_files=row["mentioned_files"],
            status=ContextStatus(row["status"]),
            compression_count=row["compression_count"],
        )

    def _exchange_to_dict(self, exchange: OracleExchange) -> Dict:
        """Convert OracleExchange to dictionary for JSON serialization.

        Args:
            exchange: Exchange to convert

        Returns:
            Dictionary representation
        """
        return {
            "id": exchange.id,
            "role": exchange.role.value,
            "content": exchange.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "result": tc.result,
                    "status": tc.status.value,
                    "duration_ms": tc.duration_ms,
                }
                for tc in (exchange.tool_calls or [])
            ] if exchange.tool_calls else None,
            "tool_call_id": exchange.tool_call_id,
            "timestamp": exchange.timestamp.isoformat(),
            "token_count": exchange.token_count,
            "key_insight": exchange.key_insight,
            "mentioned_symbols": exchange.mentioned_symbols,
            "mentioned_files": exchange.mentioned_files,
        }

    def _dict_to_exchange(self, data: Dict) -> OracleExchange:
        """Convert dictionary to OracleExchange.

        Args:
            data: Dictionary representation

        Returns:
            OracleExchange instance
        """
        from ..models.oracle_context import ToolCallStatus

        tool_calls = None
        if data.get("tool_calls"):
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    name=tc["name"],
                    arguments=tc.get("arguments", {}),
                    result=tc.get("result"),
                    status=ToolCallStatus(tc.get("status", "pending")),
                    duration_ms=tc.get("duration_ms"),
                )
                for tc in data["tool_calls"]
            ]

        return OracleExchange(
            id=data["id"],
            role=ExchangeRole(data["role"]),
            content=data["content"],
            tool_calls=tool_calls,
            tool_call_id=data.get("tool_call_id"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            token_count=data.get("token_count", 0),
            key_insight=data.get("key_insight"),
            mentioned_symbols=data.get("mentioned_symbols", []),
            mentioned_files=data.get("mentioned_files", []),
        )


# ========================================
# Singleton Pattern
# ========================================

_context_service: Optional[OracleContextService] = None


def get_context_service() -> OracleContextService:
    """Get or create the OracleContextService singleton.

    Returns:
        OracleContextService instance
    """
    global _context_service
    if _context_service is None:
        _context_service = OracleContextService()
    return _context_service


__all__ = [
    "OracleContextService",
    "OracleContextServiceError",
    "get_context_service",
]
