# Forge Version History

## v0.5.0-planning (2026-06-30)

In this version, we introduced structured **Planning & Replanning**. This forces the Agent to always maintain a Plan checklist in its context, and dynamically rewrite it upon discovering environmental roadblocks.

### Key Changes
- **Structured Prompt Upgrade (`forge/runner.py`)**: Modified `DEFAULT_SYSTEM_PROMPT` to enforce `Plan / Thought / Action` sections on agent reasoning outputs.
- **Simulation Demo (`examples/demo_planning.py`)**: Created a simulator demonstrating the agent's plan evolving from 2 steps to 4 steps when blocked by a missing dependency.

## v0.4.0-checkpoint (2026-06-26)

In this version, we introduced **Checkpointing and Session Resuming**. This allows the Coding Agent to preserve its state (messages history, iterations count, and trace steps) to disk, allowing it to recover and resume from crashes or interruptions.

### Key Changes
- **Serialization Methods (`forge/runner.py`)**: Added `save_checkpoint` and `load_checkpoint` to dump and load state dictionary into a JSON file after every iteration.
- **Trace Reconstruction (`forge/trace.py`)**: Added `StepTrace.from_dict` to easily reconstruct the previous step logs during resume.
- **Resume Capability (`forge/runner.py`)**: Enhanced `AgentRunner.run` to accept a `resume_from` path, restoring context memory and starting the iteration loop directly from the exact step of interruption.
- **Simulation Demo (`examples/demo_checkpoint.py`)**: Added a 2-stage demo demonstrating the agent crashing mid-run, preserving state, and resuming seamlessly.
- **CLI Upgrades (`examples/run_agent.py`)**: Added a `--resume` option to CLI.

## v0.3.0-suite (2026-06-26)

In this version, we implemented a **Task Suite (Benchmark Platform)** to programmatically evaluate Agent performance in isolated workspaces. We also introduced a CWD-switching sandboxing mechanism in the runner.

### Key Changes
- **Task Suite Module (`forge/suite.py`)**: Defines `CodingTask` and `TaskSuite` with 2 physical coding benchmarks (Math division bug and String reverse words implementation).
- **CWD Sandboxing (`forge/runner.py`)**: Intercepts Agent execution and switches process working directory using `os.chdir(workspace_dir)` to isolate tool file read/write paths.
- **Suite Benchmark CLI (`examples/run_suite.py`)**: Executes tasks in parallel temp folders under `temp_tasks/`, auto-verifies outputs, and prints a formatted summary table.
- **Suite Mock Model**: Multi-task mock model that handles state resets and adapts logic to solve multiple suite tasks.

## v0.2.0-verifier (2026-06-26)

In this version, we introduced an automated **Verifier** gatekeeper to automatically check python syntax and run test suites when the model attempts to declare task completion. This enables the Agent to perform **Self-Correction** upon receiving test failures or compiler error feedbacks.

### Key Changes
- **Verifier Module (`forge/verifier.py`)**: Checks workspace files for syntax errors using `compile()` and runs unit test suites via subprocess command.
- **Self-Correction Loop (`forge/runner.py`)**: Intercepts termination attempts when the model returns empty `tool_calls`. Rejects exit and feeds errors back into the prompt history if checks fail.
- **Simulation Demo (`examples/demo_verifier.py`)**: A mock simulation showing the agent correcting its own syntax error (missing colon) in real-time.
- **CLI Upgrades (`examples/run_agent.py`)**: Added `--test-command` option to support automated verification command execution.

## v0.1.0-mvp (2026-06-26)

This is the initial Minimum Viable Product (MVP) of the Forge Agent framework. It establishes a fully functional, easy-to-understand skeleton for a local CLI Coding Agent.

### Core Architecture Implemented

- **Agent Runner / Loop**: Handles iterative prompting, token safety limits, decision flow, and tool execution orchestration.
- **Context Builder**: Manages message histories conforming to standardized OpenAI API role specifications (`system`, `user`, `assistant`, `tool`).
- **7 Core Coding Tools**:
  - `list_files` (Recursively view files)
  - `search_code` (Line-by-line codebase grep)
  - `read_file` (Read file content with optional line numbers)
  - `apply_patch` (Targeted search-and-replace text patches)
  - `edit_file_block` (Replace a 1-indexed inclusive line range)
  - `run_command` (Execute terminal verification/tests)
  - `git_diff` (Inspect current changes)
- **Trace Logger**: Records step-by-step performance metrics, duration, models prompt snapshot, tool execution outputs, and saves them to a structured JSON file.
- **Demos & CLI**:
  - `examples/demo_mock.py`: Zero-dependency, offline simulation demonstrating a complete debug-patch-verify cycle.
  - `examples/run_agent.py`: CLI entrypoint compatible with OpenAI/Gemini APIs.
