# Forge Next: Coding Agent

Forge Next is a coding agent aimed at real software engineering work, not just a demo of an agent loop. The project is growing toward an agent that can understand a repository, plan and make changes, verify its work, recover from failures, collaborate with humans, and prepare clean delivery units.

This branch starts from the local development loop: task-scoped edits, project checks, failure feedback, diff review, focused verification, checkpoints, and subagent delegation. The current features are building blocks for that larger agent.

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

## Runtime Architecture

Forge keeps the runtime split into focused components:

- `AgentRunner`: orchestrates the main loop, model calls, tool dispatch, completion checks, checkpoint timing, and trace return.
- `AgentSession`: owns per-run state such as context, trace, change transaction state, current iteration, and checkpoint serialization.
- `ToolExecutor`: handles model-requested tool calls, including argument parsing, dependency injection, standard tool execution, concurrent subagent dispatch, and tool-result recording.
- `SubagentManager`: creates specialized child agents while sharing parent runtime resources such as model, workspace, sandbox, registry, and locks.
- `CompletionGate`: decides whether a no-tool model response may finish the task, using the verifier and feeding failures back into context.
- `Verifier`: runs syntax checks, configured test commands, and project-discovered checks.
- `ChangeSet`: tracks task-scoped workspace changes and supports summaries, diffs, checkpoint persistence, and revert.
- `ChangeReviewer`: reviews task-scoped changes for commit readiness, missing verification signals, local artifacts, and atomicity risks.

New runtime behavior should land in the narrowest matching component instead of growing `AgentRunner` or broadening core tools.

## Features

- **Agent Loop**: Continuously executes the task until the model decides to stop or reaches iteration limits.
- **11 Core Coding Tools**:
  - `list_files`: Recursive listing of files in the workspace.
  - `search_code`: Search for query string inside files.
  - `inspect_code_symbols`: Summarize Python imports, classes, methods, and functions with line numbers.
  - `read_file`: Retrieve file content with optional line numbers.
  - `apply_patch`: Search and replace string to modify files.
  - `edit_file_block`: Replace a 1-indexed inclusive line range.
  - `run_command`: Execute verification commands or tests.
  - `git_diff`: Inspect modifications.
  - `change_summary`: Inspect the current task transaction changes and diff.
  - `revert_changes`: Revert all file changes made since the current task transaction baseline.
  - `review_changes`: Review the current transaction for delivery and commit-readiness risks.
- **Zero-Dependency Mock Mode**: Run the agent immediately without any API keys or internet connection.
- **Trace Logger**: Detailed logging of every turn (thoughts, tool inputs, outputs, tokens, execution time).
- **Project-Aware Verifier Gatekeeper**: Automatically checks Python syntax, runs explicit verification commands, and discovers common project checks such as Python unittest, package scripts, Go tests, and Cargo tests before allowing the agent to finish.
- **Self-Correction Loop**: Feeds verifier failures back into the conversation so the agent can repair its own mistakes.
- **Task Suite Benchmark**: Runs predefined coding tasks in isolated temporary workspaces and reports pass/fail metrics.
- **Workspace Isolation**: Executes each agent run from a configured workspace directory to keep file operations scoped.
- **Change Transactions**: Captures a workspace baseline for each run, reports task-scoped changes, and can revert the current transaction.
- **Change Review Gate**: Reviews task-scoped changes for local artifacts, missing test evidence, missing documentation signals, and commit atomicity before finishing.
- **Checkpoint & Resume**: Saves message history, iteration state, and trace steps so interrupted runs can continue.
- **Structured Planning**: Prompts agents to maintain `Plan`, `Thought`, and `Action` sections and revise plans when blocked.
- **Context Compiler**: Folds older history and extracts important traceback details from long tool outputs.
- **Local Execution Boundary**: Workspace path checks, command timeouts, and shell-free command execution for safer local runs. This is not a hardened OS sandbox for untrusted code.

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

### Run Change Transactions Demo
The change transactions demo shows an agent inspecting a bad edit, reverting it to the task baseline, and then applying the correct fix:
```bash
python examples/demo_changes.py
```

### Run Change Review Demo
The change review demo shows an agent catching a code-only edit, adding the missing test update, and reviewing the transaction again before finishing:
```bash
python examples/demo_review.py
```

### Run Real Agent
To run on a real task with a real OpenAI/Gemini compatible API:
```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://api.openai.com/v1" # Or any proxy/alternative endpoint
python examples/run_agent.py "Your prompt here" --test-command "python -m unittest"
```

If `--test-command` is omitted, Forge still performs Python syntax checks and tries to discover common project verification commands from files such as `package.json`, `go.mod`, `Cargo.toml`, pytest configuration, or Python test files.

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

### Run Skills Demo
Skills can add prompt guidance and Python tools from folders under `skills/`. Tool registration is idempotent by name, and runners can use cloned registries when a demo needs isolation:
```bash
python examples/demo_skills.py
```

### Run Subagents Demo
Subagents can be launched concurrently for delegation, while shared model calls and standard tool executions are serialized through parent-owned locks:
```bash
python examples/demo_subagents.py
```
