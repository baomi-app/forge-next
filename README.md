# Forge: Minimal Coding Agent for Learning

Forge is a simplified, educational implementation of an AI Coding Agent. The goal of this repository is to break down the complex mechanics of agentic workflows into understandable, step-by-step components.

## Core Flow

```text
Task
 ↓
Agent Runner / Loop
 ↓
Context Builder (Message History & Prompts)
 ↓
Model (LLM Client / MockModel)
 ↓
Tool Executor
 ↓
Trace & Evaluation (Execution Logging)
```

## Features

- **Agent Loop**: Continuously executes the task until the model decides to stop or reaches iteration limits.
- **7 Core Coding Tools**:
  - `list_files`: Recursive listing of files in the workspace.
  - `search_code`: Search for query string inside files.
  - `read_file`: Retrieve file content with optional line numbers.
  - `apply_patch`: Search and replace string to modify files.
  - `edit_file_block`: Replace a 1-indexed inclusive line range.
  - `run_command`: Execute verification commands or tests.
  - `git_diff`: Inspect modifications.
- **Zero-Dependency Mock Mode**: Run the agent immediately without any API keys or internet connection.
- **Trace Logger**: Detailed logging of every turn (thoughts, tool inputs, outputs, tokens, execution time).
- **Verifier Gatekeeper**: Automatically checks Python syntax and optional test commands before allowing the agent to finish.
- **Self-Correction Loop**: Feeds verifier failures back into the conversation so the agent can repair its own mistakes.
- **Task Suite Benchmark**: Runs predefined coding tasks in isolated temporary workspaces and reports pass/fail metrics.
- **Workspace Isolation**: Executes each agent run from a configured workspace directory to keep file operations scoped.
- **Checkpoint & Resume**: Saves message history, iteration state, and trace steps so interrupted runs can continue.
- **Structured Planning**: Prompts agents to maintain `Plan`, `Thought`, and `Action` sections and revise plans when blocked.
- **Context Compiler**: Folds older history and extracts important traceback details from long tool outputs.
- **Local Execution Boundary**: Workspace path checks, command timeouts, and shell-free command execution for safer local demos. This is not a hardened OS sandbox for untrusted code.

## Installation

1. Create a virtual environment and activate it:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Agent

### Run Mock Demo
To see the full loop and tool execution in action (using a simulated coding scenario):
```bash
python examples/demo_mock.py
```

### Run Verifier Demo
The verifier demo shows the agent being blocked by a syntax error, receiving structured feedback, and correcting the file before finishing:
```bash
python examples/demo_verifier.py
```

### Run Task Suite
The task suite runs multiple offline coding tasks and prints a benchmark summary:
```bash
python examples/run_suite.py --mock
```

### Run Checkpoint Demo
The checkpoint demo simulates an interrupted run, saves state, and resumes from the generated checkpoint:
```bash
python examples/demo_checkpoint.py
```

### Run Planning Demo
The planning demo shows the agent revising its checklist when an initial assumption fails:
```bash
python examples/demo_planning.py
```

### Run Context Compiler Demo
The context demo shows large noisy logs being folded while the relevant traceback remains available to the agent:
```bash
python examples/demo_context.py
```

### Run Real Agent
To run on a real task with a real OpenAI/Gemini compatible API:
```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://api.openai.com/v1" # Or any proxy/alternative endpoint
python examples/run_agent.py "Your prompt here" --test-command "python -m unittest"
```

To resume a saved run:
```bash
python examples/run_agent.py --resume checkpoint.json --trace-file trace.json
```

### Run Sandbox Demo
The sandbox demo shows blocked dangerous commands, timeout handling, and workspace-only file access:
```bash
python examples/demo_sandbox.py
```

### Run MCP Demo
The MCP demo launches a local stdio JSON-RPC server, discovers its tools, and shuts the subprocess down cleanly:
```bash
python examples/demo_mcp.py
```
