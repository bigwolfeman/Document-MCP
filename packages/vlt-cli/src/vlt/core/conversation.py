"""Oracle conversation context management.

T062-T068: Shared conversation context across MCP tool calls with compression.

This module manages the shared conversation context for oracle sessions, enabling
multi-turn interactions where each tool call can reference prior results.

Key features:
- Exchange logging with tool name, input, output summary
- Token counting and budget management
- Automatic compression at 80% threshold
- Symbol and file mention tracking
- Conversation history persistence
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import httpx

from vlt.core.models import OracleConversation, ConversationStatus, Project
from vlt.config import Settings


logger = logging.getLogger(__name__)


class ConversationExchange:
    """A single exchange in the oracle conversation."""

    def __init__(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        output_summary: str,
        key_insights: List[str],
        mentioned_symbols: List[str] = None,
        mentioned_files: List[str] = None,
        token_count: int = 0,
        timestamp: Optional[datetime] = None
    ):
        """Initialize a conversation exchange.

        Args:
            tool_name: Name of MCP tool that was called
            input_data: Input parameters to the tool
            output_summary: Summary of the tool's output
            key_insights: Important facts/findings from this exchange
            mentioned_symbols: Code symbols referenced (classes, functions, etc.)
            mentioned_files: File paths referenced
            token_count: Approximate token count for this exchange
            timestamp: When exchange occurred (defaults to now)
        """
        self.tool_name = tool_name
        self.input_data = input_data
        self.output_summary = output_summary
        self.key_insights = key_insights or []
        self.mentioned_symbols = mentioned_symbols or []
        self.mentioned_files = mentioned_files or []
        self.token_count = token_count
        self.timestamp = timestamp or datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exchange to dictionary for JSON serialization."""
        return {
            "tool_name": self.tool_name,
            "input_data": self.input_data,
            "output_summary": self.output_summary,
            "key_insights": self.key_insights,
            "mentioned_symbols": self.mentioned_symbols,
            "mentioned_files": self.mentioned_files,
            "token_count": self.token_count,
            "timestamp": self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationExchange':
        """Create exchange from dictionary."""
        return cls(
            tool_name=data["tool_name"],
            input_data=data["input_data"],
            output_summary=data["output_summary"],
            key_insights=data.get("key_insights", []),
            mentioned_symbols=data.get("mentioned_symbols", []),
            mentioned_files=data.get("mentioned_files", []),
            token_count=data.get("token_count", 0),
            timestamp=datetime.fromisoformat(data["timestamp"])
        )

    def __repr__(self) -> str:
        return (f"ConversationExchange(tool={self.tool_name}, "
                f"insights={len(self.key_insights)}, tokens={self.token_count})")


class ConversationManager:
    """Manages oracle conversation context with compression.

    Features:
    - T062: Conversation session management
    - T063: Exchange logging
    - T064: Token counting
    - T065: Compression trigger at 80%
    - T066: LLM-based compression
    - T067: Symbol/file tracking
    """

    DEFAULT_TOKEN_BUDGET = 16000
    COMPRESSION_THRESHOLD = 0.8  # 80%
    RECENT_EXCHANGES_KEEP = 5    # Keep last N uncompressed
    SESSION_EXPIRY_HOURS = 24    # Expire inactive sessions after 24h

    def __init__(
        self,
        db: Session,
        settings: Optional[Settings] = None
    ):
        """Initialize conversation manager.

        Args:
            db: Database session
            settings: Settings instance (uses default if None)
        """
        self.db = db
        self.settings = settings or Settings()
        self.logger = logging.getLogger(__name__)

    def get_or_create_conversation(
        self,
        project_id: str,
        user_id: str,
        token_budget: int = DEFAULT_TOKEN_BUDGET
    ) -> OracleConversation:
        """Get active conversation or create new one.

        T062: Session management with expiry.

        Args:
            project_id: Project identifier
            user_id: User identifier
            token_budget: Token budget for conversation

        Returns:
            OracleConversation instance
        """
        # Ensure project exists
        project = self.db.query(Project).filter_by(id=project_id).first()
        if not project:
            project = Project(
                id=project_id,
                name=project_id,
                description=f"Project {project_id}"
            )
            self.db.add(project)
            self.db.commit()

        # Look for active conversation that hasn't expired
        expiry_cutoff = datetime.now(timezone.utc) - timedelta(hours=self.SESSION_EXPIRY_HOURS)

        conversation = (
            self.db.query(OracleConversation)
            .filter_by(project_id=project_id, user_id=user_id)
            .filter(OracleConversation.status == ConversationStatus.ACTIVE)
            .filter(OracleConversation.last_activity > expiry_cutoff)
            .first()
        )

        if conversation:
            self.logger.info(f"Resumed conversation {conversation.id} for user {user_id}")
            return conversation

        # Create new conversation
        conversation = OracleConversation(
            id=str(uuid.uuid4()),
            project_id=project_id,
            user_id=user_id,
            token_budget=token_budget,
            tokens_used=0,
            recent_exchanges_json='[]',
            status=ConversationStatus.ACTIVE,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=self.SESSION_EXPIRY_HOURS)
        )

        self.db.add(conversation)
        self.db.commit()

        self.logger.info(f"Created new conversation {conversation.id} for user {user_id}")
        return conversation

    def log_exchange(
        self,
        conversation: OracleConversation,
        tool_name: str,
        input_data: Dict[str, Any],
        output_data: Any,
        auto_compress: bool = True
    ) -> None:
        """Log a tool exchange to the conversation.

        T063: Exchange logging with summaries and insights.
        T064: Token counting.
        T065: Auto-compression trigger.
        T067: Symbol/file tracking.

        Args:
            conversation: Conversation to update
            tool_name: Name of tool that was called
            input_data: Tool input parameters
            output_data: Tool output (will be summarized)
            auto_compress: Automatically compress if threshold exceeded
        """
        # Extract summary and insights from output
        output_summary, key_insights = self._extract_output_summary(output_data)

        # Extract mentioned symbols and files
        mentioned_symbols = self._extract_symbols(output_summary)
        mentioned_files = self._extract_files(output_summary)

        # Estimate token count for this exchange
        exchange_tokens = self._estimate_tokens(
            tool_name=tool_name,
            input_data=input_data,
            output_summary=output_summary,
            key_insights=key_insights
        )

        # Create exchange object
        exchange = ConversationExchange(
            tool_name=tool_name,
            input_data=input_data,
            output_summary=output_summary,
            key_insights=key_insights,
            mentioned_symbols=mentioned_symbols,
            mentioned_files=mentioned_files,
            token_count=exchange_tokens
        )

        # Load current exchanges
        recent_exchanges = self._load_exchanges(conversation)
        recent_exchanges.append(exchange)

        # Update token count
        conversation.tokens_used += exchange_tokens

        # Update mentioned symbols/files (accumulate unique)
        self._update_mentioned_symbols(conversation, mentioned_symbols)
        self._update_mentioned_files(conversation, mentioned_files)

        # Update activity timestamp
        conversation.last_activity = datetime.now(timezone.utc)

        # Save exchanges
        self._save_exchanges(conversation, recent_exchanges)

        self.db.commit()

        self.logger.info(
            f"Logged exchange: {tool_name} (+{exchange_tokens} tokens, "
            f"total: {conversation.tokens_used}/{conversation.token_budget})"
        )

        # Check if compression needed
        if auto_compress:
            threshold = int(conversation.token_budget * self.COMPRESSION_THRESHOLD)
            if conversation.tokens_used > threshold:
                self.logger.info(
                    f"Token budget exceeded threshold ({conversation.tokens_used} > {threshold}), "
                    "triggering compression"
                )
                self.compress_conversation(conversation)

    def compress_conversation(
        self,
        conversation: OracleConversation
    ) -> None:
        """Compress old exchanges preserving key insights.

        T065: Compression trigger.
        T066: LLM-based compression preserving symbols/files/insights.

        Args:
            conversation: Conversation to compress
        """
        # Load all recent exchanges
        exchanges = self._load_exchanges(conversation)

        if len(exchanges) <= self.RECENT_EXCHANGES_KEEP:
            self.logger.info("Not enough exchanges to compress, skipping")
            return

        # Split into older (to compress) and recent (to keep)
        to_compress = exchanges[:-self.RECENT_EXCHANGES_KEEP]
        to_keep = exchanges[-self.RECENT_EXCHANGES_KEEP:]

        self.logger.info(
            f"Compressing {len(to_compress)} exchanges, keeping {len(to_keep)} recent"
        )

        # Generate compressed summary using LLM
        new_summary = self._generate_compressed_summary(
            existing_summary=conversation.compressed_summary,
            exchanges_to_compress=to_compress
        )

        # Calculate token savings
        old_tokens = sum(e.token_count for e in to_compress)
        summary_tokens = self._estimate_tokens_from_text(new_summary)
        tokens_saved = old_tokens - summary_tokens

        # Update conversation
        conversation.compressed_summary = new_summary
        conversation.tokens_used = summary_tokens + sum(e.token_count for e in to_keep)
        conversation.compression_count += 1
        conversation.status = ConversationStatus.COMPRESSED

        # Save only recent exchanges
        self._save_exchanges(conversation, to_keep)

        self.db.commit()

        self.logger.info(
            f"Compression complete: saved {tokens_saved} tokens "
            f"(new total: {conversation.tokens_used}/{conversation.token_budget})"
        )

    def get_conversation_context(
        self,
        conversation: OracleConversation,
        max_tokens: Optional[int] = None
    ) -> str:
        """Get full conversation context for tool calls.

        T068: Context injection for tools.

        Args:
            conversation: Conversation to get context from
            max_tokens: Optional token limit

        Returns:
            Formatted conversation context
        """
        parts = []

        # Add compressed summary if it exists
        if conversation.compressed_summary:
            parts.append("## Earlier Context (Compressed)\n")
            parts.append(conversation.compressed_summary)
            parts.append("\n")

        # Add recent exchanges
        exchanges = self._load_exchanges(conversation)
        if exchanges:
            parts.append("## Recent Exchanges\n")
            for exchange in exchanges:
                parts.append(f"\n### {exchange.tool_name}\n")
                parts.append(f"**Input**: {self._format_input(exchange.input_data)}\n")
                parts.append(f"**Output**: {exchange.output_summary}\n")
                if exchange.key_insights:
                    parts.append("**Key Insights**:\n")
                    for insight in exchange.key_insights:
                        parts.append(f"- {insight}\n")

        context = "".join(parts)

        # Truncate if needed
        if max_tokens:
            estimated = self._estimate_tokens_from_text(context)
            if estimated > max_tokens:
                # Simple truncation - in production, could be smarter
                ratio = max_tokens / estimated
                truncate_at = int(len(context) * ratio)
                context = context[:truncate_at] + "\n\n[Context truncated to fit token budget]"

        return context

    def close_conversation(
        self,
        conversation: OracleConversation
    ) -> None:
        """Close a conversation session.

        Args:
            conversation: Conversation to close
        """
        conversation.status = ConversationStatus.CLOSED
        self.db.commit()
        self.logger.info(f"Closed conversation {conversation.id}")

    # Private helper methods

    def _load_exchanges(self, conversation: OracleConversation) -> List[ConversationExchange]:
        """Load exchanges from JSON."""
        try:
            data = json.loads(conversation.recent_exchanges_json)
            return [ConversationExchange.from_dict(e) for e in data]
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.error(f"Failed to load exchanges: {e}")
            return []

    def _save_exchanges(
        self,
        conversation: OracleConversation,
        exchanges: List[ConversationExchange]
    ) -> None:
        """Save exchanges to JSON."""
        data = [e.to_dict() for e in exchanges]
        conversation.recent_exchanges_json = json.dumps(data)

    def _extract_output_summary(
        self,
        output_data: Any
    ) -> tuple[str, List[str]]:
        """Extract summary and insights from output.

        Returns:
            Tuple of (summary, key_insights)
        """
        # Handle different output types
        if isinstance(output_data, str):
            summary = output_data[:500] + "..." if len(output_data) > 500 else output_data
            insights = self._extract_insights_from_text(output_data)
        elif isinstance(output_data, dict):
            # For structured responses (like OracleResponse)
            if "answer" in output_data:
                summary = output_data["answer"][:500]
                insights = self._extract_insights_from_text(output_data["answer"])
            else:
                summary = json.dumps(output_data, indent=2)[:500]
                insights = []
        elif isinstance(output_data, list):
            summary = f"Returned {len(output_data)} results"
            insights = []
        else:
            summary = str(output_data)[:500]
            insights = []

        return summary, insights

    def _extract_insights_from_text(self, text: str) -> List[str]:
        """Extract key insights from text.

        Simple heuristic: Look for sentences with key phrases.
        """
        insights = []

        # Key phrases that often indicate important facts
        key_phrases = [
            r"is defined in",
            r"is used by",
            r"implements",
            r"calls",
            r"returns",
            r"handles",
            r"responsible for",
            r"key feature",
            r"important",
            r"note that",
            r"remember"
        ]

        sentences = re.split(r'[.!?]\s+', text)
        for sentence in sentences[:10]:  # Limit to first 10 sentences
            for phrase in key_phrases:
                if re.search(phrase, sentence, re.IGNORECASE):
                    insights.append(sentence.strip())
                    break

        return insights[:5]  # Limit to 5 insights per exchange

    def _extract_symbols(self, text: str) -> List[str]:
        """Extract code symbols from text.

        T067: Symbol tracking.
        """
        symbols = set()

        # Pattern for common code identifiers (PascalCase, camelCase, snake_case)
        # This is a simple heuristic - could be enhanced with AST parsing
        patterns = [
            r'\b([A-Z][a-zA-Z0-9]*(?:[A-Z][a-zA-Z0-9]*)+)\b',  # PascalCase
            r'\b([a-z][a-zA-Z0-9]*(?:[A-Z][a-zA-Z0-9]*)+)\b',  # camelCase
            r'\b([a-z_][a-z0-9_]*)\b',                          # snake_case
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            symbols.update(matches)

        # Filter out common words
        common_words = {'the', 'this', 'that', 'with', 'from', 'for', 'and', 'or'}
        symbols = {s for s in symbols if s.lower() not in common_words}

        return sorted(list(symbols))[:20]  # Limit to top 20

    def _extract_files(self, text: str) -> List[str]:
        """Extract file paths from text.

        T067: File tracking.
        """
        files = set()

        # Pattern for file paths
        patterns = [
            r'(?:src|lib|packages)/[\w/.-]+\.(?:py|ts|tsx|js|jsx)',  # Common code paths
            r'[\w/-]+\.(?:md|txt|json|yaml|toml)',                    # Config/docs
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            files.update(matches)

        # Also look for citation-style paths [file.py:123]
        citation_pattern = r'\[([\w/.-]+\.\w+)(?::\d+)?\]'
        matches = re.findall(citation_pattern, text)
        files.update(matches)

        return sorted(list(files))

    def _update_mentioned_symbols(
        self,
        conversation: OracleConversation,
        new_symbols: List[str]
    ) -> None:
        """Update accumulated mentioned symbols.

        T067: Symbol tracking.
        """
        if not new_symbols:
            return

        # Load existing symbols
        existing = set()
        if conversation.mentioned_symbols:
            existing = set(conversation.mentioned_symbols.split(','))

        # Add new symbols
        existing.update(new_symbols)

        # Save (limit to 100 symbols)
        conversation.mentioned_symbols = ','.join(sorted(list(existing))[:100])

    def _update_mentioned_files(
        self,
        conversation: OracleConversation,
        new_files: List[str]
    ) -> None:
        """Update accumulated mentioned files.

        T067: File tracking.
        """
        if not new_files:
            return

        # Load existing files
        existing = set()
        if conversation.mentioned_files:
            existing = set(conversation.mentioned_files.split(','))

        # Add new files
        existing.update(new_files)

        # Save (limit to 50 files)
        conversation.mentioned_files = ','.join(sorted(list(existing))[:50])

    def _estimate_tokens(
        self,
        tool_name: str,
        input_data: Dict[str, Any],
        output_summary: str,
        key_insights: List[str]
    ) -> int:
        """Estimate token count for an exchange.

        T064: Token counting.

        Uses simple heuristic: ~4 chars per token (GPT-3/4 rough average).
        """
        text = f"{tool_name} {json.dumps(input_data)} {output_summary} {' '.join(key_insights)}"
        return self._estimate_tokens_from_text(text)

    def _estimate_tokens_from_text(self, text: str) -> int:
        """Estimate tokens from text.

        T064: Token counting.

        Uses 4 chars per token heuristic.
        """
        return len(text) // 4

    def _format_input(self, input_data: Dict[str, Any]) -> str:
        """Format input data for display."""
        # Truncate long inputs
        formatted = json.dumps(input_data, indent=2)
        if len(formatted) > 200:
            formatted = formatted[:200] + "..."
        return formatted

    async def _generate_compressed_summary(
        self,
        existing_summary: Optional[str],
        exchanges_to_compress: List[ConversationExchange]
    ) -> str:
        """Generate compressed summary using LLM.

        T066: LLM-based compression preserving symbols/files/insights.
        """
        if not self.settings.openrouter_api_key:
            self.logger.warning("No API key for compression, using simple concatenation")
            return self._simple_compression(existing_summary, exchanges_to_compress)

        # Build compression prompt
        exchanges_text = "\n\n".join([
            f"**{e.tool_name}**: {e.output_summary}\nInsights: {', '.join(e.key_insights)}\n"
            f"Symbols: {', '.join(e.mentioned_symbols)}\nFiles: {', '.join(e.mentioned_files)}"
            for e in exchanges_to_compress
        ])

        prompt = f"""You are compressing a conversation history for an AI coding agent.

EXISTING COMPRESSED SUMMARY:
{existing_summary or "None"}

NEW EXCHANGES TO COMPRESS:
{exchanges_text}

INSTRUCTIONS:
Generate a compressed summary that:
1. Preserves ALL mentioned symbols (class/function names)
2. Preserves ALL mentioned file paths
3. Preserves key insights and decisions
4. Removes redundant details and verbose explanations
5. Is 50-70% shorter than the original

Format as concise bullet points. Focus on FACTS not prose.

COMPRESSED SUMMARY:
"""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.settings.openrouter_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.settings.openrouter_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 2000,
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    compressed = data["choices"][0]["message"]["content"]
                    self.logger.info("Generated LLM-based compressed summary")
                    return compressed
                else:
                    self.logger.error(f"LLM compression failed: {response.status_code}")
                    return self._simple_compression(existing_summary, exchanges_to_compress)

        except Exception as e:
            self.logger.error(f"Error during LLM compression: {e}")
            return self._simple_compression(existing_summary, exchanges_to_compress)

    def _simple_compression(
        self,
        existing_summary: Optional[str],
        exchanges_to_compress: List[ConversationExchange]
    ) -> str:
        """Simple compression fallback without LLM."""
        parts = []

        if existing_summary:
            parts.append(existing_summary)

        # Extract key facts
        all_symbols = set()
        all_files = set()
        all_insights = []

        for exchange in exchanges_to_compress:
            all_symbols.update(exchange.mentioned_symbols)
            all_files.update(exchange.mentioned_files)
            all_insights.extend(exchange.key_insights)

        # Build simple summary
        if all_symbols:
            parts.append(f"Symbols discussed: {', '.join(sorted(all_symbols))}")
        if all_files:
            parts.append(f"Files referenced: {', '.join(sorted(all_files))}")
        if all_insights:
            parts.append("Key findings:\n" + "\n".join(f"- {i}" for i in all_insights[:10]))

        return "\n\n".join(parts)


# Convenience functions for easy integration

def get_conversation_manager(
    db: Session,
    settings: Optional[Settings] = None
) -> ConversationManager:
    """Get a conversation manager instance.

    Args:
        db: Database session
        settings: Optional settings instance

    Returns:
        ConversationManager instance
    """
    return ConversationManager(db=db, settings=settings)
