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

### Run Real Agent
To run on a real task with a real OpenAI/Gemini compatible API:
```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://api.openai.com/v1" # Or any proxy/alternative endpoint
python examples/run_agent.py "Your prompt here"
```
