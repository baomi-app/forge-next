# AGENTS.md

Guidance for coding agents working on Forge.

## Project Shape

Forge is a small educational coding-agent framework. Keep changes easy to read and scoped to the feature being demonstrated.

## Development Rules

- Keep commit history linear and organized by feature version.
- Do not commit local IDE/editor configuration such as `.vscode/`.
- Prefer standard-library Python unless a dependency is already required.
- Keep examples runnable as lightweight demonstrations.
- Update README and VERSION entries when changing user-facing behavior.

## Verification

Run focused checks for the feature you touch, and use these broader checks before finishing larger changes:

```bash
python -m compileall forge examples skills
python examples/demo_mock.py
python examples/run_suite.py --mock
```
