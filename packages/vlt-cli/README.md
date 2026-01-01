# Vault CLI (vlt) - v0.2.0

**Purpose**: A Cognitive Hard Drive for AI Agents and Power Users.

`vlt` is a command-line tool designed to provide long-term, semantic memory for your work. It allows you to offload your "stream of consciousness" into a persistent, searchable database, preventing context window bloat and enabling you to pick up exactly where you left off.

## Key Features

- **Project Identity**: Auto-detects project context from `vlt.toml`.
- **Low-Latency Logging**: `vlt thread push` is optimized for speed (<50ms).
- **Asynchronous Summarization**: A background "Librarian" compresses raw thoughts into concise summaries using LLMs (Grok-4.1-Fast by default).
- **Semantic Search**: Recall past decisions (`vlt thread seek`) or search within a thread (`vlt thread read --search`).
- **Knowledge Graph**: Tag (`#bug`) and Link (`relates to`) thoughts to build a connected web of reasoning.
- **Author Attribution**: Sign your thoughts with `--author` to support multi-agent collaboration.

## Requirements

- Python 3.11+
- An [OpenRouter](https://openrouter.ai/) API Key.
- **Universal Ctags** (required for Oracle feature): Install via `apt install universal-ctags` (Linux) or `brew install universal-ctags` (macOS).

## Installation

See [QUICKSTART.md](QUICKSTART.md) for detailed instructions.

```bash
pip install -e .
vlt config set-key <YOUR_OPENROUTER_KEY>
```

## Feedback

Please report any bugs or feature requests to the developer.