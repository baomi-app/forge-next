# Forge Version History

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
