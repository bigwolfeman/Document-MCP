# Quickstart: Oracle Agent Architecture

**Feature**: 009-oracle-agent
**Time to First Result**: ~30 minutes

## Prerequisites

- Python 3.11+
- Running backend server (`uv run uvicorn src.api.main:app --reload`)
- OpenRouter API key configured
- Indexed codebase (`vlt coderag init`)

## Step 1: Create OracleAgent Service (15 min)

Create `backend/src/services/oracle_agent.py`:

```python
"""Oracle Agent - Main agent with tool calling."""

from __future__ import annotations
import json
import logging
from typing import AsyncGenerator, Dict, List, Any, Optional
from datetime import datetime
import httpx

from ..models.oracle import OracleStreamChunk
from .tool_executor import ToolExecutor
from .prompt_loader import PromptLoader

logger = logging.getLogger(__name__)

class OracleAgent:
    """AI project manager agent with tool calling."""

    OPENROUTER_BASE = "https://openrouter.ai/api/v1"
    MAX_TURNS = 15

    def __init__(
        self,
        api_key: str,
        model: str = "anthropic/claude-sonnet-4",
        project_id: Optional[str] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.project_id = project_id
        self.tool_executor = ToolExecutor()
        self.prompt_loader = PromptLoader()

    async def query(
        self,
        question: str,
        user_id: str,
        stream: bool = True,
    ) -> AsyncGenerator[OracleStreamChunk, None]:
        """Run agent loop, yielding chunks."""

        # Build initial messages
        system_prompt = self.prompt_loader.load("oracle/system.md", {
            "project_id": self.project_id,
        })

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

        # Get tool definitions
        tools = self.tool_executor.get_tool_schemas(agent="oracle")

        # Agent loop
        for turn in range(self.MAX_TURNS):
            async for chunk in self._agent_turn(messages, tools, stream):
                yield chunk

                # Check if we're done
                if chunk.type == "done":
                    return

                # If tool calls, execute and continue
                if chunk.type == "tool_calls":
                    tool_results = await self._execute_tools(
                        chunk.tool_calls, user_id
                    )
                    messages.extend(tool_results)

        # Max turns reached
        yield OracleStreamChunk(
            type="error",
            error="Max turns reached without completion"
        )

    async def _agent_turn(
        self,
        messages: List[Dict],
        tools: List[Dict],
        stream: bool,
    ) -> AsyncGenerator[OracleStreamChunk, None]:
        """Execute one turn of the agent loop."""

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.OPENROUTER_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "HTTP-Referer": "https://vlt.ai",
                    "X-Title": "Vlt Oracle",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "parallel_tool_calls": True,
                    "stream": stream,
                },
            )
            response.raise_for_status()

            if stream:
                async for chunk in self._process_stream(response):
                    yield chunk
            else:
                data = response.json()
                async for chunk in self._process_response(data):
                    yield chunk

    async def _execute_tools(
        self,
        tool_calls: List[Dict],
        user_id: str,
    ) -> List[Dict]:
        """Execute tool calls and return message list."""
        results = []

        for call in tool_calls:
            yield OracleStreamChunk(
                type="tool_call",
                tool_call={
                    "id": call["id"],
                    "name": call["function"]["name"],
                    "arguments": call["function"]["arguments"],
                }
            )

            result = await self.tool_executor.execute(
                name=call["function"]["name"],
                arguments=json.loads(call["function"]["arguments"]),
                user_id=user_id,
            )

            yield OracleStreamChunk(
                type="tool_result",
                tool_result=result,
            )

            results.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": result,
            })

        return results
```

## Step 2: Create ToolExecutor (10 min)

Create `backend/src/services/tool_executor.py`:

```python
"""Tool Executor - Dispatches tool calls to implementations."""

from typing import Dict, Any, List
import json

# Import existing services
from .vault import VaultService
from .indexer import IndexerService
from .thread_service import ThreadService
from .oracle_bridge import OracleBridge

class ToolExecutor:
    """Executes tool calls by routing to appropriate services."""

    def __init__(self):
        self.vault = VaultService()
        self.indexer = IndexerService()
        self.threads = ThreadService()
        self.oracle_bridge = OracleBridge()

        # Tool registry
        self.tools = {
            "search_code": self._search_code,
            "find_definition": self._find_definition,
            "vault_read": self._vault_read,
            "vault_write": self._vault_write,
            "vault_search": self._vault_search,
            "thread_push": self._thread_push,
            "thread_read": self._thread_read,
            "thread_seek": self._thread_seek,
            # Add more as implemented
        }

    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        user_id: str,
    ) -> str:
        """Execute a tool and return result as string."""
        if name not in self.tools:
            return json.dumps({"error": f"Unknown tool: {name}"})

        try:
            result = await self.tools[name](user_id, **arguments)
            return json.dumps(result, default=str)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def get_tool_schemas(self, agent: str = "oracle") -> List[Dict]:
        """Get OpenRouter-compatible tool schemas."""
        # Load from tools.json
        import json
        from pathlib import Path

        tools_file = Path(__file__).parent.parent.parent / "prompts" / "tools.json"
        # Fallback to contracts if prompts not set up yet
        if not tools_file.exists():
            tools_file = Path(__file__).parent.parent.parent.parent / "specs" / "009-oracle-agent" / "contracts" / "tools.json"

        with open(tools_file) as f:
            data = json.load(f)

        # Filter by agent scope
        return [
            {"type": t["type"], "function": t["function"]}
            for t in data["tools"]
            if agent in t.get("agent_scope", ["oracle"])
        ]

    # Tool implementations
    async def _search_code(self, user_id: str, query: str, limit: int = 5, **kwargs) -> Dict:
        result = await self.oracle_bridge.search_code(query, limit=limit)
        return result

    async def _vault_read(self, user_id: str, path: str) -> Dict:
        note = self.vault.read_note(user_id, path)
        return {"path": path, "content": note.get("body", ""), "title": note.get("title", "")}

    async def _vault_write(self, user_id: str, path: str, body: str, title: str = None) -> Dict:
        self.vault.write_note(user_id, path, title=title, body=body)
        return {"status": "ok", "path": path}

    async def _vault_search(self, user_id: str, query: str, limit: int = 5) -> Dict:
        results = self.indexer.search_notes(user_id, query, limit=limit)
        return {"results": results}

    async def _thread_push(self, user_id: str, thread_id: str, content: str, **kwargs) -> Dict:
        # Use thread service
        entry = self.threads.add_entry(user_id, thread_id, content, author="oracle")
        return {"status": "ok", "entry_id": entry.get("entry_id")}

    async def _thread_read(self, user_id: str, thread_id: str, limit: int = 10) -> Dict:
        thread = self.threads.get_thread(user_id, thread_id, include_entries=True, entries_limit=limit)
        return thread

    async def _thread_seek(self, user_id: str, query: str, limit: int = 5) -> Dict:
        results = self.threads.search_threads(user_id, query, limit=limit)
        return results
```

## Step 3: Create PromptLoader (5 min)

Create `backend/src/services/prompt_loader.py`:

```python
"""Prompt Loader - Load and render prompt templates."""

from pathlib import Path
from typing import Dict, Any, Optional
import jinja2

class PromptLoader:
    """Load prompts from the prompts/ directory."""

    def __init__(self, prompts_dir: Optional[Path] = None):
        self.prompts_dir = prompts_dir or Path(__file__).parent.parent.parent / "prompts"

        # Fallback to inline prompts if directory doesn't exist
        if not self.prompts_dir.exists():
            self.prompts_dir = None

        if self.prompts_dir:
            self.env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(str(self.prompts_dir)),
                autoescape=False,
            )
        else:
            self.env = None

    def load(self, path: str, context: Dict[str, Any] = None) -> str:
        """Load and render a prompt template."""
        if self.env:
            try:
                template = self.env.get_template(path)
                return template.render(context or {})
            except jinja2.TemplateNotFound:
                pass

        # Fallback to inline prompts
        return self._get_inline_prompt(path, context or {})

    def _get_inline_prompt(self, path: str, context: Dict) -> str:
        """Inline prompts for bootstrapping before prompts/ is created."""
        prompts = {
            "oracle/system.md": """You are the Oracle, an AI project manager that helps developers understand their codebase.

You have access to tools for:
- Searching code and finding definitions
- Reading and writing documentation
- Recording decisions to memory threads
- Searching the web for external information

Always cite your sources using [file:line] or [note-path] format.
Be honest when you can't find relevant context.
Use tools proactively to gather information before answering.

Project: {{ project_id or 'Not specified' }}
""",
            "librarian/system.md": """You are the Librarian, a specialized agent for organizing documentation.

Your job is to:
- Move and rename notes while updating wikilinks
- Create index pages for folders
- Organize documentation into logical structure
- Provide summaries of vault contents

Focus only on vault organization tasks. Report completion to the Oracle.
""",
        }

        template_str = prompts.get(path, f"Prompt not found: {path}")
        template = jinja2.Template(template_str)
        return template.render(context)
```

## Step 4: Update Oracle Route (5 min)

Update `backend/src/api/routes/oracle.py` to use OracleAgent:

```python
# Add to existing imports
from ..services.oracle_agent import OracleAgent

# Add new streaming endpoint (or update existing)
@router.post("/stream")
async def oracle_stream(
    request: OracleRequest,
    auth: AuthContext = Depends(get_current_user),
):
    """Stream Oracle response with tool calls."""
    from ..services.user_settings import get_user_settings

    settings = get_user_settings(auth.user_id)
    agent = OracleAgent(
        api_key=settings.openrouter_api_key,
        model=settings.oracle_model,
        project_id=request.project_id,
    )

    async def generate():
        async for chunk in agent.query(
            question=request.question,
            user_id=auth.user_id,
            stream=True,
        ):
            yield f"data: {chunk.model_dump_json()}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )
```

## Verify It Works

```bash
# 1. Start backend
cd backend
uv run uvicorn src.api.main:app --reload --port 8000

# 2. Test the endpoint
curl -X POST http://localhost:8000/api/oracle/stream \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What does the OracleAgent class do?"}'
```

Expected output: SSE stream with tool calls and answer.

## Next Steps

1. Create `backend/prompts/` directory with full prompts
2. Add context persistence (oracle_contexts table)
3. Implement remaining tools
4. Add Librarian subagent
5. Convert vlt-cli oracle to thin client
