# Vault CLI (vlt) - Quickstart Guide

## 1. Installation

1.  Unzip the package.
2.  Open a terminal in the `vlt-cli` directory.
3.  Install:
    ```bash
    pip install -e .
    ```

## 2. Configuration

1.  Initialize the DB:
    ```bash
    vlt init
    ```

2.  Set API Key:
    ```bash
    vlt config set-key sk-or-v1-...
    ```

## 3. Project Setup (The Identity Layer)

Go to your project directory and initialize its identity:

```bash
cd ~/Projects/my-app
vlt init --project my-app
```
*This creates a `vlt.toml` file. Commit this to Git.*

## 4. Core Workflow

1.  **Start a Thread**:
    ```bash
    vlt thread new optimization "Starting SAT implementation."
    ```
    *(Note: Project is auto-detected from `vlt.toml`)*

2.  **Log Thoughts**:
    ```bash
    vlt thread push optimization "SAT is too slow."
    ```

3.  **Sign Your Work (Multi-Agent)**:
    ```bash
    vlt --author "Architect" thread push optimization "Suggesting pivot to GJK."
    ```

4.  **Review State**:
    ```bash
    vlt thread read optimization
    ```
    *(Shows Summary + Last 5 thoughts)*

5.  **Deep Dive**:
    ```bash
    vlt thread read optimization --all
    vlt thread read optimization --search "pivot"
    ```

## 5. The Knowledge Graph

- **Tagging**:
    ```bash
    # Get node ID from read output
    vlt tag <node_id> pivot
    ```

- **Linking**:
    ```bash
    vlt link <node_id> other-thread --note "Caused by"
    ```

## 6. The Librarian

Run this in the background to enable Summarization and Search:

```bash
vlt librarian run --daemon
```