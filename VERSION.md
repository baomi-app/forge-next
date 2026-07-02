# Forge Version History

## v0.27.0-human-review-loop (2026-07-02)

In this version, we introduced **Human Review Loop** so agents can create explicit approval checkpoints and record human decisions before continuing sensitive plan, diff, or commit work.

### Key Changes
- **Human Review Loop (`forge/human_review.py`)**: Added checkpoint creation for plan, diff, commit, and custom stages with changed files and optional diff preview.
- **Human Review Tools (`forge/core_tools/human_review.py`)**: Added `request_human_review` for approval checkpoints and `record_human_review` for approval, rejection, or requested-change decisions.
- **Blocked Tool Results (`forge/tool_result.py`, `forge/journal.py`)**: Added a `blocked` tool-result status so approval checkpoints are distinct from successful output and hard errors.
- **Simulation Demo (`examples/demo_human_review.py`)**: Demonstrates a diff approval checkpoint, decision recording, and journal persistence.
- **Unit Tests (`tests/test_human_review.py`, `tests/test_executor.py`, `tests/test_journal.py`)**: Covers checkpoint formatting, blocked result metadata, journal recording, decision recording, and tool registration.
- **README and Agent Guidance (`README.md`, `AGENTS.md`)**: Documents the human-review boundary and the expanded core tool set.

## v0.26.0-structured-tool-result (2026-07-02)

In this version, we introduced **Structured ToolResult** so tool execution outcomes carry explicit status, content, error type, and metadata instead of relying only on output strings.

### Key Changes
- **Tool Result Model (`forge/tool_result.py`)**: Added `ToolResult` with success/error constructors, trace serialization, and text compatibility for direct callers.
- **Registry and Executor (`forge/tool_registry.py`, `forge/executor.py`)**: Standardized normal returns, tool exceptions, missing tools, JSON argument errors, and executor exceptions as structured results while preserving plain text content for model messages.
- **Trace and Journal Integration (`forge/completion.py`, `forge/journal.py`)**: Records status/error fields in trace tool results and lets journal recording use structured status before falling back to text heuristics.
- **Unit Tests (`tests/test_executor.py`, `tests/test_completion.py`, `tests/test_journal.py`)**: Covers structured success results, explicit tool-result passthrough, tool exceptions, JSON parse failures, verifier trace status, and journal failure recording.
- **README and Agent Guidance (`README.md`, `AGENTS.md`)**: Documents the structured result boundary and the rule against string-only status inference.

## v0.25.0-run-runtime-extraction (2026-07-02)

In this version, we introduced **AgentLoopRunner / AgentRunner Loop Extraction** so per-iteration model/tool/completion flow lives outside the top-level runner.

### Key Changes
- **Agent Loop Runner (`forge/agent_loop_runner.py`)**: Added a dedicated component for model turns, tool-call handoff, completion-gate handling, max-iteration termination, and checkpoint-save timing.
- **Runner Wiring (`forge/runner.py`)**: Reduced `AgentRunner.run` to session preparation, dependency synchronization, workspace directory management, and delegation to `AgentLoopRunner`.
- **Unit Tests (`tests/test_agent_loop_runner.py`)**: Covers tool-turn checkpoint saves and checkpoint cleanup when completion passes.
- **README and Agent Guidance (`README.md`, `AGENTS.md`)**: Documents the new loop boundary and runtime architecture rule.

## v0.24.0-tool-runtime-injection (2026-07-02)

In this version, we introduced **ToolCapabilities / Capability Injection** so core tools receive narrow per-run capabilities instead of reaching across the full runner.

### Key Changes
- **Tool Capabilities (`forge/tool_capabilities.py`)**: Added a small runtime object for workspace, sandbox, session-backed change state, subagent manager, journal recorder, and project policy access.
- **Registry and Executor (`forge/tool_registry.py`, `forge/executor.py`, `forge/runner.py`)**: Added runtime-first dependency injection while keeping legacy injection available for external or transition tools.
- **Core Tool Migration (`forge/core_tools/`)**: Migrated built-in tools to consume `runtime` for transaction state, journal state, project policy, sandbox access, and subagent dispatch.
- **Unit Tests (`tests/test_executor.py`, `tests/test_tools.py`, transaction tool tests)**: Covers runtime preference over legacy dependencies, hidden runtime schema parameters, and runtime-backed tool behavior.
- **README and Agent Guidance (`README.md`, `AGENTS.md`)**: Documents the runtime capability boundary and tool injection rule.

## v0.23.0-policy-verification-chain (2026-07-02)

In this version, we migrated the verification chain onto **ProjectPolicy / RepoProfile** so focused test selection and project verification share the same project rules as the rest of the agent.

### Key Changes
- **Focused Test Selection (`forge/focused.py`)**: Reused project policy for code/test/example classification while preserving existing focused command behavior.
- **Verifier (`forge/verifier.py`)**: Reused project policy and profiler for syntax exclusions, language detection, and Python test discovery.
- **Policy Markers (`forge/project.py`)**: Extended node language detection to include common lockfiles used by verifier discovery.
- **Unit Tests (`tests/test_verifier.py`, `tests/test_project.py`)**: Covers policy-backed syntax exclusions and lockfile language detection.
- **README Update (`README.md`)**: Documents that verification now uses the shared project policy/profile layer.

## v0.22.0-project-policy-profile (2026-07-02)

In this version, we introduced **ProjectPolicy / RepoProfile** so repository rules and lightweight project traits are shared instead of being hard-coded across components.

### Key Changes
- **Project Policy and Profile (`forge/project.py`)**: Added shared file classification, generated-file detection, language hints, workspace exclusions, repository profiling, and checkpoint-compatible policy serialization.
- **Low-Risk Component Migration (`forge/changes.py`, `forge/review.py`, `forge/commit.py`, `forge/edit_plan.py`, `forge/repo_map.py`)**: Migrated transaction tracking, review, commit planning, edit planning, and repo mapping to use the shared policy/profile layer.
- **File Inspection Migration (`forge/core_tools/files.py`, `forge/core_tools/symbols.py`)**: Reused project policy exclusions for file listing, search, and symbol inspection.
- **Unit Tests (`tests/test_project.py`)**: Covers classification, exclusions, repository profiling, and ChangeSet policy persistence.
- **README Update (`README.md`)**: Documents the shared project policy/profile architecture.

## v0.21.0-repo-map-v2 (2026-07-02)

In this version, we introduced **Repo Map v2** so agents can orient at the repository level before choosing files to inspect or edit.

### Key Changes
- **Repo Mapper (`forge/repo_map.py`)**: Added lightweight mapping for file roles, Python symbols, local imports, entry points, suggested inspection files, parse errors, and test-to-runtime relationships.
- **Repository Map Tool (`forge/core_tools/repo_map.py`)**: Added `inspect_repo_map` for agent-facing repository orientation with optional task-goal ranking.
- **Simulation Demo (`examples/demo_repo_map.py`)**: Demonstrates using the repository map to find a runtime file and linked test before editing.
- **Unit Tests (`tests/test_repo_map.py`)**: Covers role mapping, symbol extraction, entrypoint detection, local import links, test links, task-goal suggestions, sandbox subdirectory behavior, and registration.
- **README Update (`README.md`)**: Documents Repo Map v2 and the expanded core tool set.

## v0.20.0-task-journal (2026-07-02)

In this version, we introduced **Persistent Task Journal** so long-running tasks can preserve structured plans, decisions, tool outcomes, verification results, and next steps across checkpoints.

### Key Changes
- **Task Journal (`forge/journal.py`)**: Added structured journal entries with kind, summary, details, timestamps, formatting, and checkpoint serialization.
- **Journal Recorder (`forge/journal.py`)**: Added a recorder layer that converts runtime events into journal entries, centralizing event kinds, summaries, failure detection, and truncation policy.
- **Session and Runtime Integration (`forge/session.py`, `forge/executor.py`, `forge/completion.py`, `forge/runner.py`)**: Persisted journals in checkpoints and wired runtime components to report task starts, tool results, and completion verification outcomes through the recorder.
- **Journal Tools (`forge/core_tools/journal.py`)**: Added `journal_note` for explicit agent notes and `read_journal` for recent task history.
- **Simulation Demo (`examples/demo_task_journal.py`)**: Demonstrates recording plan, decision, verification, and tool history during a task.
- **Unit Tests (`tests/test_journal.py`)**: Covers journal formatting, checkpoint persistence, tool usage, automatic tool-result records, verifier records, and registration.
- **README Update (`README.md`)**: Documents persistent task journaling and the expanded core tool set.

## v0.19.0-edit-planner (2026-07-02)

In this version, we introduced **Patch Strategy / Edit Planner** so agents can produce an inspectable edit strategy before modifying files.

### Key Changes
- **Edit Planner (`forge/edit_plan.py`)**: Added pre-edit planning with task goals, files to inspect, planned file-level edits, scope risks, focused verification suggestions, and next steps.
- **Planning Tool (`forge/core_tools/edit_plan.py`)**: Added `plan_edits`, a tool for planning edits before patching the workspace.
- **Simulation Demo (`examples/demo_edit_planner.py`)**: Demonstrates planning, inspecting, patching, and verifying a small code/test change.
- **Unit Tests (`tests/test_edit_plan.py`)**: Covers explicit target plans, missing goals, inferred files, missing-file risks, tool execution, and tool registration.
- **README Update (`README.md`)**: Documents edit planning and the expanded core tool set.

## v0.18.0-commit-orchestration (2026-07-02)

In this version, we introduced **Commit Orchestration** so agents can turn task-scoped changes into a clear staging plan, safely update the git index, create one atomic commit, and verify the committed file set.

### Key Changes
- **Commit Planner and Orchestrator (`forge/commit.py`)**: Added transaction-aware staging recommendations, excluded-file detection, git index inspection, safe staging, commit execution, committed-file verification, and remaining-workspace reporting.
- **Commit Tools (`forge/core_tools/commit.py`)**: Added `plan_commit` for preflight planning and `commit_changes` for staging approved files and creating one git commit when the plan is safe.
- **Simulation Demo (`examples/demo_commit_orchestration.py`)**: Demonstrates an agent updating code, tests, and docs, running verification, and creating a focused commit in a temporary git repository.
- **Unit Tests (`tests/test_commit.py`)**: Covers planning states, git status inspection, safe commit execution, staged-file guardrails, transaction-backed tools, and tool registration.
- **README Update (`README.md`)**: Documents commit orchestration and the expanded core tool set.

## v0.17.0-failure-triage (2026-07-01)

In this version, we introduced **Failure Triage** so verifier failures include a classified cause, short evidence, and a repair-oriented next step for the self-correction loop.

### Key Changes
- **Failure Triage (`forge/verifier.py`)**: Added structured triage for syntax errors, missing dependencies, assertion failures, missing commands, timeouts, lint failures, typecheck failures, permission errors, and missing files.
- **Verifier Reports (`forge/verifier.py`)**: Included failure triage blocks in syntax and project verification failure reports so agents receive actionable feedback instead of raw logs alone.
- **Simulation Demo (`examples/demo_failure_triage.py`)**: Demonstrates an assertion failure being triaged, fed back to the agent, and corrected on the next iteration.
- **Unit Tests (`tests/test_verifier.py`)**: Covers triage classification and report formatting for failing tests and syntax errors.
- **README Update (`README.md`)**: Documents failure triage and the runnable demo.

## v0.16.0-focused-test-selection (2026-07-01)

In this version, we introduced **Focused Test Selection** so agents can suggest targeted verification commands from the files changed in the current task transaction.

### Key Changes
- **Focused Test Selector (`forge/focused.py`)**: Discovers focused verification commands from changed test files, demo scripts, sibling tests, and mirrored `tests/` layouts, with a safe unittest discovery fallback for unmapped code.
- **Suggestion Tool (`forge/core_tools/focused.py`)**: Added `suggest_tests`, a transaction-aware tool that reports changed files, suggested commands, and verification notes.
- **Simulation Demo (`examples/demo_focused_tests.py`)**: Demonstrates patching a file, selecting the sibling unit test from the transaction, and running the focused test.
- **Unit Tests (`tests/test_focused.py`)**: Covers project-local test discovery, changed test files, demo scripts, docs-only changes, fallback behavior, and tool registration.
- **README Update (`README.md`)**: Documents focused test selection and the expanded core tool set.

## v0.15.0-change-review-gate (2026-07-01)

In this version, we introduced a **Change Review Gate** so agents can review task-scoped changes before finishing or preparing an atomic commit.

### Key Changes
- **Change Reviewer (`forge/review.py`)**: Reviews transaction changes for blocking local artifacts, missing test evidence, missing user-facing documentation signals, and broad atomicity risks.
- **Review Tool (`forge/core_tools/review.py`)**: Added `review_changes`, a transaction-aware tool that reports PASS/WARN/BLOCK status, changed files, findings, commit shape, and a suggested commit message.
- **Simulation Demo (`examples/demo_review.py`)**: Demonstrates an agent catching a code-only edit, adding the missing test change, and passing review before verification.
- **Unit Tests (`tests/test_changes.py`)**: Covers empty transactions, local editor artifacts, missing test warnings, clean code-plus-test reviews, and tool registration.
- **README Update (`README.md`)**: Documents the new review gate, core tool, and runnable demo.

## v0.14.0-code-symbols (2026-07-01)

In this version, we added a lightweight **Python Code Symbol Inspector** so agents can orient themselves in a Python workspace before reading entire files.

### Key Changes
- **Symbol Inspection Tool (`forge/core_tools/symbols.py`)**: Added `inspect_code_symbols`, a standard-library `ast`-based tool that summarizes Python imports, classes, methods, functions, docstring first lines, and source line numbers.
- **Tool Discovery (`forge/tools.py`)**: Exposes the inspector through automatic built-in tool module discovery.
- **Unit Tests (`tests/test_tools.py`)**: Covers symbol summaries, parse error reporting, and core tool registration.
- **README Update (`README.md`)**: Documents the new core tool.

## v0.13.0-project-verifier (2026-07-01)

In this version, we upgraded the verifier from a fixed Python-only gate into a **Project-Aware Verifier**. The agent can now detect common project types and run discovered validation commands when no explicit test command is configured.

### Key Changes
- **Project Profile Detection (`forge/verifier.py`)**: Detects Python, Node, Go, and Rust workspaces from project files and source extensions.
- **Verification Check Discovery (`forge/verifier.py`)**: Discovers common runnable checks including Python unittest discovery, pytest configuration when pytest is available, package manager scripts (`lint`, `typecheck`, `test`), `go test ./...`, and `cargo test`.
- **Structured Verification Reports (`forge/verifier.py`)**: Reports each check with category, command source, exit code, duration, and failure classification to make self-correction feedback easier for the agent to act on.
- **README Update (`README.md`)**: Documents automatic project verification discovery and the explicit `--test-command` override.

## v0.12.0-change-transactions (2026-07-01)

In this version, we introduced **Change Transactions** so each agent run can track, inspect, and revert workspace file changes relative to a captured task baseline.

### Key Changes
- **ChangeSet Core (`forge/changes.py`)**: Captures workspace baselines, detects added/modified/deleted files, renders unified diffs, serializes baselines for checkpoints, and reverts files to the baseline.
- **Runner Integration (`forge/runner.py`)**: Creates a transaction baseline for each `AgentRunner` instance, saves it into checkpoints, restores it on resume, and exposes it to injected tools.
- **Transaction Tools (`forge/core_tools/changes.py`)**: Added `change_summary` and `revert_changes` so agents can review or roll back the current task transaction.
- **Simulation Demo (`examples/demo_changes.py`)**: Demonstrates inspecting a bad edit, reverting the transaction, applying the correct fix, and passing verifier checks.
- **Unit Tests (`tests/test_changes.py`)**: Covers change detection, diff formatting, revert behavior, and transaction tool registration.
- **README Update (`README.md`)**: Documents change transactions and the expanded core tool set.

## v0.11.0-runtime-architecture (2026-07-01)

In this version, we initialized the **Forge Next Runtime Architecture** so the runner can stay small while dedicated components own session state, tool execution, completion checks, subagent orchestration, and dynamic tool discovery.

### Key Changes
- **Runtime Decomposition (`forge/runner.py`, `forge/session.py`, `forge/executor.py`, `forge/completion.py`)**: Split loop state, tool dispatch, and completion handling out of the monolithic runner path.
- **Tool Registry (`forge/tool_registry.py`)**: Centralized tool registration, schema generation, dependency injection, and execution behind a dedicated registry.
- **Core Tool Modules (`forge/core_tools/`)**: Moved built-in tools into focused modules and made `forge/tools.py` discover them dynamically.
- **Subagent Manager (`forge/subagents.py`)**: Isolated subagent creation and parent resource sharing from runner orchestration.
- **Unit Tests (`tests/test_runner.py`, `tests/test_executor.py`, `tests/test_session.py`, `tests/test_completion.py`, `tests/test_subagents.py`)**: Covers the new component boundaries.
- **Repository Guidance (`AGENTS.md`)**: Added agent-facing development and atomic commit rules.

## v0.10.0-subagents (2026-06-30)

In this version, we introduced a concurrent **Subagents** pattern. This enables parent Orchestrator agents to dynamically delegate specialized sub-tasks to multiple child agents concurrently using a thread pool, while standard tools are executed sequentially to prevent write resource collisions.

### Key Changes
- **Selective Concurrency Scheduler (`forge/runner.py`)**: Refactored the tool execution loop to divide tool calls: `invoke_subagent` runs in parallel using `ThreadPoolExecutor`, while file and CLI modifying operations (like `edit_file_block`, `run_command`) run sequentially to prevent write collisions.
- **Parent Runner Injection (`forge/tools.py`, `forge/runner.py`)**: Added dynamic dependency injection of parent runner pointers inside ToolRegistry execution pipelines (hidden from LLM JSON schemas).
- **Subagent Delegation Tool (`forge/tools.py`)**: Created `invoke_subagent` function instantiating sub-runners, sharing model references/sandboxes, and parsing child trace outputs.
- **Orchestration Demo (`examples/demo_subagents.py`)**: Demonstrates a parallel 3-agent teamwork flow (Orchestrator concurrently spawning SecurityExpert and LinterExpert) auditing buffer overflows and PEP8 code styling, patching code, and running bounds verification.

## v0.9.0-skills (2026-06-30)

In this version, we introduced a folder-based **Skill Bundle** architecture. Each Skill is a standalone directory holding prompt guidelines (`SKILL.md`) for cognitive reasoning, and custom scripts (`scripts/*.py`) containing `@skill` tools for imperative actions.

### Key Changes
- **Skill Bundle Loader (`forge/skills.py`)**: Enhanced `SkillsManager` to scan subdirectories, aggregate prompt guidelines from `SKILL.md` (injecting them to Agent system prompts), and dynamically hot-load python tool functions from `scripts/` using `importlib.util`.
- **Git Commit Expert Skill (`skills/git_expert/`)**: Built a full git expert skill bundle enforcing Angular git commit conventions via regex checks.
- **Polite Sign-Off Skill (`skills/polite_reply/`)**: Added a cognitive-only (no tools) skill bundle to prove prompt guidelines execution.
- **Simulation Demo (`examples/demo_skills.py`)**: Demonstrates dynamic rules aggregation, tool rejection, system instruction-aware self-correction, and pass.

## v0.8.0-mcp (2026-06-30)

In this version, we implemented the **Model Context Protocol (MCP)** client. This allows the Agent to interface with external tool servers dynamically via stdio pipelines utilizing JSON-RPC 2.0 messages.

### Key Changes
- **MCP Client (`forge/mcp.py`)**: Built an stdio Popen process manager and a thread-safe listener loop resolving JSON-RPC callback futures. Supports protocol handshake, tool query (`tools/list`), and execution (`tools/call`).
- **Dynamic Schema Tool Injection (`forge/tools.py`)**: Enhanced `ToolRegistry` to dynamically register remote MCP JSON schemas, wrapping calls in closures executing subprocess IPC.
- **Mock MCP Server (`examples/mock_mcp_server.py`)**: Zero-dependency Python process exporting a remote mathematical tool over standard output streams.
- **MCP Orchestration Demo (`examples/demo_mcp.py`)**: Runs handshake, dynamic registration, model trace execution, and child process cleanup.

## v0.7.0-sandbox (2026-06-30)

In this version, we introduced a pluggable **Sandbox & Execution Limits** architecture. This intercepts hostile CLI commands, enforces time limits on child processes, restricts path traversal, and decouples tools from raw system calls.

### Key Changes
- **Sandbox Core (`forge/sandbox.py`)**: Defined abstract `BaseSandbox` and implemented `LocalRestrictedSandbox` supporting regex-based command filtering (`rm -rf`, `sudo`, `curl`, etc.) and execution timeouts.
- **Dependency Injection (`forge/tools.py` & `forge/runner.py`)**: Registry automatically injects the runner's Sandbox instance to matching tool signature parameters, keeping LLM JSON schemas clean.
- **Simulation Demo (`examples/demo_sandbox.py`)**: Proves execution blockage of high-risk shell inputs and time limit terminations during runtime.

## v0.6.0-context (2026-06-30)

In this version, we implemented a production-grade **Context Compiler** pattern with **Smart Traceback Extraction** and **History Message Folding** to prevent token bloat while retaining critical errors across multi-turn sessions.

### Key Changes
- **Context Compiler (`forge/context.py`)**: Enhanced `get_messages()` to dynamically compile a token-efficient messages array on the fly.
- **Smart Traceback Extraction (`forge/context.py`)**: Uses regex to identify Python tracebacks within large tool outputs, preserving only the stack trace (max 15 lines) and filtering out irrelevant logging noise.
- **History Message Folding (`forge/context.py`)**: Overwrites the content of older turns (older than 2 turns) with short placeholders like `[Output of tool X folded]` and `[Thoughts folded]`, saving 95%+ of historical tokens.
- **Simulation Demo (`examples/demo_context.py`)**: Simulates the agent patching an AttributeError despite the test command producing a massive $8.8K$ log of database connections.

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
