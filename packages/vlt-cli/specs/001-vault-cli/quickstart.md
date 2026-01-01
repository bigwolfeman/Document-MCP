# Vault CLI (vlt) Quickstart

## Installation
```bash
pip install vlt-cli
vlt init
```

## Workflow

### 1. Start a New Task
```bash
vlt thread new crypto-bot optim-strategy "Starting optimization of the bellman-ford algo using cuda."
```

### 2. Log Thoughts (The "Pulse")
```bash
vlt thread push crypto-bot/optim-strategy "Attempt 1 failed. Shared memory overflow."
vlt thread push crypto-bot/optim-strategy "Switching to global memory approach."
```

### 3. Check State
```bash
vlt thread read crypto-bot/optim-strategy
```
*Output:*
```markdown
# Thread: Optim Strategy
## Summary
Agent is migrating from shared memory to global memory due to overflows...
```

### 4. Search Memory
```bash
vlt thread seek -a "memory overflow"
```

## Running the Librarian
To process summaries in the background:
```bash
vlt librarian run --daemon
```
