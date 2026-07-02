# AGENTS.md

Guidance for coding agents working on Forge.

## Project Shape

Forge Next is a coding agent for real software engineering work. Keep changes easy to read and scoped to the capability or fix being implemented.

## Development Rules

- Keep commit history linear and organized by feature version.
- Keep commits atomic: one commit must contain exactly one feature or fix, a feature or fix must not be split across multiple commits, and each commit must exclude unrelated changes.
- Do not commit local IDE/editor configuration such as `.vscode/`.
- Prefer standard-library Python unless a dependency is already required.
- Keep examples runnable as lightweight workflow simulations.
- Update README and VERSION entries when changing user-facing behavior.

## Runtime Architecture Boundaries

- Keep `AgentRunner` focused on the agent loop: prepare context, call the model, dispatch tools, evaluate completion, checkpoint progress, and return the trace.
- Put per-run state and checkpoint serialization in `AgentSession`, not directly in `AgentRunner`.
- Put iteration advancement in `AgentLoopRunner`: model turn execution, tool-call handoff, completion-gate invocation, and checkpoint-save timing.
- Put model-requested tool execution details in `ToolExecutor`, including tool-call partitioning, JSON argument parsing, dependency injection, and result recording.
- Represent tool execution outcomes with `ToolResult`; do not infer tool status only from output strings.
- Put human approval checkpoints in `HumanReviewLoop` and the human-review tools; do not bury approval requirements inside unrelated tool output.
- Put subagent creation, shared runtime resources, and subagent checkpoint naming in `SubagentManager`.
- Put no-tool completion decisions in `CompletionGate`; verifier pass/block handling should not be reimplemented in `AgentRunner`.
- Put workspace edit baselines, summaries, diffs, and reverts in `ChangeSet`.
- Keep tools thin. When a tool needs runtime state, prefer injecting `ToolCapabilities`; do not pass the whole runner into core tools.

## Verification

Run focused checks for the feature you touch, and use these broader checks before finishing larger changes:

```bash
python -m compileall forge examples skills tests
python -m unittest discover
for demo in examples/demo_*.py; do python "$demo"; done
python examples/run_suite.py --mock
```
