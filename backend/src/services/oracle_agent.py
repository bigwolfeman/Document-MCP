"""Oracle Agent - Main AI agent with tool calling (009-oracle-agent).

This replaces the subprocess-based OracleBridge with a proper agent implementation
that uses OpenRouter function calling for tool execution.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from ..models.oracle import OracleStreamChunk, SourceReference
from ..models.oracle_context import (
    ContextStatus,
    ExchangeRole,
    OracleContext,
    OracleExchange,
    ToolCall,
    ToolCallStatus,
)

logger = logging.getLogger(__name__)

# Lazy imports to avoid circular dependencies
_tool_executor = None
_prompt_loader = None


def _get_tool_executor():
    """Get ToolExecutor instance lazily."""
    global _tool_executor
    if _tool_executor is None:
        from .tool_executor import ToolExecutor
        _tool_executor = ToolExecutor()
    return _tool_executor


def _get_prompt_loader():
    """Get PromptLoader instance lazily."""
    global _prompt_loader
    if _prompt_loader is None:
        from .prompt_loader import PromptLoader
        _prompt_loader = PromptLoader()
    return _prompt_loader


class OracleAgentError(Exception):
    """Raised when Oracle agent operations fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class OracleAgent:
    """AI project manager agent with tool calling.

    The Oracle answers questions about codebases by using tools to search code,
    read documentation, query development threads, and search the web.
    """

    OPENROUTER_BASE = "https://openrouter.ai/api/v1"
    MAX_TURNS = 15
    DEFAULT_MODEL = "anthropic/claude-sonnet-4"

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """Initialize the Oracle agent.

        Args:
            api_key: OpenRouter API key
            model: Model to use (default: anthropic/claude-sonnet-4)
            project_id: Project context for tool scoping
            user_id: User ID for context tracking
        """
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.project_id = project_id
        self.user_id = user_id
        self._context: Optional[OracleContext] = None
        self._collected_sources: List[SourceReference] = []

    async def query(
        self,
        question: str,
        user_id: str,
        stream: bool = True,
        thinking: bool = False,
        max_tokens: int = 4000,
    ) -> AsyncGenerator[OracleStreamChunk, None]:
        """Run agent loop, yielding streaming chunks.

        Args:
            question: User's question
            user_id: User identifier
            stream: Whether to stream response
            thinking: Enable thinking/reasoning mode
            max_tokens: Maximum tokens in response

        Yields:
            OracleStreamChunk objects for each piece of the response
        """
        self.user_id = user_id
        self._collected_sources = []

        # Get services
        tool_executor = _get_tool_executor()
        prompt_loader = _get_prompt_loader()

        # Build initial messages
        system_prompt = prompt_loader.load(
            "oracle/system.md",
            {
                "project_id": self.project_id or "Not specified",
                "user_id": user_id,
            },
        )

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

        # Get tool definitions
        tools = tool_executor.get_tool_schemas(agent="oracle")

        # Yield thinking chunk to indicate we're starting
        yield OracleStreamChunk(
            type="thinking",
            content="Analyzing question and gathering context...",
        )

        # Agent loop
        for turn in range(self.MAX_TURNS):
            logger.debug(f"Agent turn {turn + 1}/{self.MAX_TURNS}")

            async for chunk in self._agent_turn(
                messages=messages,
                tools=tools,
                stream=stream,
                thinking=thinking,
                max_tokens=max_tokens,
                user_id=user_id,
            ):
                yield chunk

                # Check if we're done
                if chunk.type == "done":
                    return

                # If we got an error, stop
                if chunk.type == "error":
                    return

        # Max turns reached
        yield OracleStreamChunk(
            type="error",
            error="Maximum conversation turns reached without completion",
        )

    async def _agent_turn(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        stream: bool,
        thinking: bool,
        max_tokens: int,
        user_id: str,
    ) -> AsyncGenerator[OracleStreamChunk, None]:
        """Execute one turn of the agent loop.

        Args:
            messages: Conversation messages so far
            tools: Available tool definitions
            stream: Whether to stream response
            thinking: Enable thinking mode
            max_tokens: Max tokens for response
            user_id: User identifier

        Yields:
            Response chunks from this turn
        """
        # Apply thinking suffix if requested
        model = self.model
        if thinking and not model.endswith(":thinking"):
            model = f"{model}:thinking"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.OPENROUTER_BASE}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "HTTP-Referer": "https://vlt.ai",
                        "X-Title": "Vlt Oracle",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "tools": tools if tools else None,
                        "tool_choice": "auto" if tools else None,
                        "parallel_tool_calls": True,
                        "stream": stream,
                        "max_tokens": max_tokens,
                    },
                )
                response.raise_for_status()

                if stream:
                    async for chunk in self._process_stream(response, messages, user_id):
                        yield chunk
                else:
                    data = response.json()
                    async for chunk in self._process_response(data, messages, user_id):
                        yield chunk

        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter API error: {e.response.status_code} - {e.response.text}")
            yield OracleStreamChunk(
                type="error",
                error=f"API error: {e.response.status_code}",
            )
        except httpx.TimeoutException:
            logger.error("OpenRouter API timeout")
            yield OracleStreamChunk(
                type="error",
                error="Request timeout - please try again",
            )
        except Exception as e:
            logger.exception(f"Agent turn failed: {e}")
            yield OracleStreamChunk(
                type="error",
                error=f"Agent error: {str(e)}",
            )

    async def _process_stream(
        self,
        response: httpx.Response,
        messages: List[Dict[str, Any]],
        user_id: str,
    ) -> AsyncGenerator[OracleStreamChunk, None]:
        """Process streaming response from OpenRouter.

        Args:
            response: HTTP response with SSE stream
            messages: Conversation messages (mutated with assistant response)
            user_id: User identifier

        Yields:
            Parsed stream chunks
        """
        content_buffer = ""
        tool_calls_buffer: Dict[int, Dict[str, Any]] = {}
        finish_reason = None

        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue

            data_str = line[6:]  # Remove "data: " prefix
            if data_str == "[DONE]":
                break

            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            choices = data.get("choices", [])
            if not choices:
                continue

            choice = choices[0]
            delta = choice.get("delta", {})
            finish_reason = choice.get("finish_reason")

            # Handle content
            if "content" in delta and delta["content"]:
                content_buffer += delta["content"]
                yield OracleStreamChunk(
                    type="content",
                    content=delta["content"],
                )

            # Handle tool calls
            if "tool_calls" in delta:
                for tc in delta["tool_calls"]:
                    idx = tc.get("index", 0)
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }

                    if "id" in tc and tc["id"]:
                        tool_calls_buffer[idx]["id"] = tc["id"]

                    if "function" in tc:
                        if "name" in tc["function"]:
                            tool_calls_buffer[idx]["function"]["name"] = tc["function"]["name"]
                        if "arguments" in tc["function"]:
                            tool_calls_buffer[idx]["function"]["arguments"] += tc["function"]["arguments"]

        # Process finish
        if finish_reason == "tool_calls" and tool_calls_buffer:
            # Convert buffer to list
            tool_calls = [tool_calls_buffer[i] for i in sorted(tool_calls_buffer.keys())]

            # Add assistant message with tool calls
            assistant_msg = {"role": "assistant", "content": content_buffer or None}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

            # Execute tools and yield results
            async for chunk in self._execute_tools(tool_calls, messages, user_id):
                yield chunk

        elif finish_reason == "stop" or (content_buffer and not tool_calls_buffer):
            # Final response without tool calls
            messages.append({"role": "assistant", "content": content_buffer})

            # Yield sources
            for source in self._collected_sources:
                yield OracleStreamChunk(
                    type="source",
                    source=source,
                )

            # Done
            yield OracleStreamChunk(
                type="done",
                tokens_used=None,  # Could extract from response headers
                model_used=self.model,
            )

    async def _process_response(
        self,
        data: Dict[str, Any],
        messages: List[Dict[str, Any]],
        user_id: str,
    ) -> AsyncGenerator[OracleStreamChunk, None]:
        """Process non-streaming response from OpenRouter.

        Args:
            data: Parsed JSON response
            messages: Conversation messages (mutated with assistant response)
            user_id: User identifier

        Yields:
            Response chunks
        """
        choices = data.get("choices", [])
        if not choices:
            yield OracleStreamChunk(
                type="error",
                error="No response from model",
            )
            return

        choice = choices[0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason")

        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])

        if finish_reason == "tool_calls" and tool_calls:
            # Add assistant message
            messages.append(message)

            # Execute tools
            async for chunk in self._execute_tools(tool_calls, messages, user_id):
                yield chunk

        else:
            # Final response
            if content:
                yield OracleStreamChunk(
                    type="content",
                    content=content,
                )

            messages.append({"role": "assistant", "content": content})

            # Yield sources
            for source in self._collected_sources:
                yield OracleStreamChunk(
                    type="source",
                    source=source,
                )

            # Done
            usage = data.get("usage", {})
            yield OracleStreamChunk(
                type="done",
                tokens_used=usage.get("total_tokens"),
                model_used=self.model,
            )

    async def _execute_tools(
        self,
        tool_calls: List[Dict[str, Any]],
        messages: List[Dict[str, Any]],
        user_id: str,
    ) -> AsyncGenerator[OracleStreamChunk, None]:
        """Execute tool calls and add results to messages.

        Args:
            tool_calls: List of tool calls from the model
            messages: Conversation messages (mutated with tool results)
            user_id: User identifier

        Yields:
            Tool call and result chunks
        """
        tool_executor = _get_tool_executor()

        for call in tool_calls:
            call_id = call.get("id", str(uuid.uuid4()))
            function = call.get("function", {})
            name = function.get("name", "unknown")
            arguments_str = function.get("arguments", "{}")

            # Parse arguments
            try:
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError:
                arguments = {}

            # Yield tool call notification
            yield OracleStreamChunk(
                type="tool_call",
                tool_call={
                    "id": call_id,
                    "name": name,
                    "arguments": arguments_str[:200],  # Preview
                    "status": "pending",
                },
            )

            # Execute tool
            try:
                result = await tool_executor.execute(
                    name=name,
                    arguments=arguments,
                    user_id=user_id,
                )

                # Yield tool result
                yield OracleStreamChunk(
                    type="tool_result",
                    tool_result=result[:1000] if len(result) > 1000 else result,  # Truncate for display
                )

                # Extract sources from result if present
                self._extract_sources_from_result(name, result)

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": result,
                })

            except Exception as e:
                logger.exception(f"Tool execution failed: {name}")
                error_result = json.dumps({"error": str(e)})

                yield OracleStreamChunk(
                    type="tool_result",
                    tool_result=error_result,
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": error_result,
                })

    def _extract_sources_from_result(self, tool_name: str, result: str) -> None:
        """Extract source references from tool results.

        Args:
            tool_name: Name of the tool that was executed
            result: JSON result string from the tool
        """
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return

        # Handle different tool result formats
        if tool_name == "search_code":
            results = data.get("results", [])
            for r in results[:5]:  # Limit sources
                self._collected_sources.append(
                    SourceReference(
                        path=r.get("file_path", r.get("path", "")),
                        source_type="code",
                        line=r.get("line_start"),
                        snippet=r.get("content", "")[:500],
                        score=r.get("score"),
                    )
                )

        elif tool_name == "vault_search":
            results = data.get("results", [])
            for r in results[:5]:
                self._collected_sources.append(
                    SourceReference(
                        path=r.get("path", ""),
                        source_type="vault",
                        snippet=r.get("snippet", "")[:500],
                        score=r.get("score"),
                    )
                )

        elif tool_name == "vault_read":
            path = data.get("path", "")
            if path:
                self._collected_sources.append(
                    SourceReference(
                        path=path,
                        source_type="vault",
                        snippet=data.get("content", "")[:500],
                    )
                )

        elif tool_name in ("thread_read", "thread_seek"):
            results = data.get("results", data.get("entries", []))
            for r in results[:5]:
                self._collected_sources.append(
                    SourceReference(
                        path=f"thread:{r.get('thread_id', '')}",
                        source_type="thread",
                        snippet=r.get("content", "")[:500],
                        score=r.get("score"),
                    )
                )


# Singleton instance
_oracle_agent: Optional[OracleAgent] = None


def get_oracle_agent(
    api_key: str,
    model: Optional[str] = None,
    project_id: Optional[str] = None,
) -> OracleAgent:
    """Get or create an OracleAgent instance.

    Note: This creates a new instance each time since agents are stateful
    per request. Use for dependency injection in routes.

    Args:
        api_key: OpenRouter API key
        model: Model override
        project_id: Project context

    Returns:
        Configured OracleAgent
    """
    return OracleAgent(
        api_key=api_key,
        model=model,
        project_id=project_id,
    )


__all__ = ["OracleAgent", "OracleAgentError", "get_oracle_agent"]
