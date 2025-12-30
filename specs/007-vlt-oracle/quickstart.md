# Quickstart: Vlt Oracle

**Feature**: 007-vlt-oracle
**Time to first query**: ~10 minutes

## Prerequisites

- Python 3.11+
- vlt-cli installed (`pip install vlt-cli`)
- OpenRouter API key configured (`vlt config set-key <key>`)
- Document-MCP running (for vault search)

## Step 1: Initialize Project

```bash
# Create vlt.toml in your project root
cat > vlt.toml << 'EOF'
[project]
name = "my-project"
id = "my-project"

[coderag]
include = ["src/**/*.py", "lib/**/*.py"]
exclude = ["tests/", "**/test_*.py"]

[oracle]
vault_url = "http://localhost:8000"
EOF
```

## Step 2: Index Your Code

```bash
# Index the codebase (creates embeddings for all functions/classes)
vlt coderag init

# Check indexing status
vlt coderag status
```

Expected output:
```
CodeRAG Status: my-project
├── Files indexed: 47
├── Code chunks: 312
├── Languages: python (312)
├── Last indexed: 2025-12-30T10:30:00
└── Storage: 4.2 MB
```

## Step 3: Ask the Oracle

```bash
# Basic question
vlt oracle "How does authentication work in this project?"

# Filter to code only
vlt oracle --source=code "What functions handle user input?"

# Show retrieval traces (debugging)
vlt oracle --explain "Why was caching implemented?"

# JSON output (for scripts/agents)
vlt oracle --json "List all API endpoints"
```

## Step 4: Use via MCP (Claude Desktop/Code)

Add to your Claude Desktop config:

```json
{
  "mcpServers": {
    "vlt-oracle": {
      "command": "vlt",
      "args": ["mcp", "serve"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

Then in Claude:
> "Use ask_oracle to find how authentication works"

## Step 5: Use via Web UI

1. Open Document-MCP web interface
2. Click the Oracle chat panel (brain icon)
3. Type your question
4. Click sources to navigate to relevant code/docs

## Common Commands Reference

| Command | Description |
|---------|-------------|
| `vlt oracle "question"` | Ask across all sources |
| `vlt oracle -s code "q"` | Code-only search |
| `vlt oracle -s vault "q"` | Docs-only search |
| `vlt oracle --explain "q"` | Show retrieval traces |
| `vlt coderag init` | Index codebase |
| `vlt coderag sync` | Update changed files |
| `vlt coderag status` | Check index health |
| `vlt coderag search "q"` | Direct code search |

## Troubleshooting

### "No code index found"
Run `vlt coderag init` first.

### "Vault search failed"
Check Document-MCP is running: `curl http://localhost:8000/health`

### "Rate limit exceeded"
OpenRouter has limits. Wait 60s or upgrade plan.

### "Low relevance results"
Try more specific questions. Use `--explain` to see what's being retrieved.

## Next Steps

- Configure `vlt.toml` include/exclude patterns for your project structure
- Set up incremental indexing via `vlt coderag sync` in git hooks
- Explore the call graph: `vlt coderag graph "FunctionName"`
