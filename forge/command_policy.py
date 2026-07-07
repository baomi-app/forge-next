import os
import shlex
from dataclasses import dataclass
from typing import Tuple


@dataclass
class CommandPolicy:
    """Validation policy for LLM-suggested verification commands."""

    allowed_executables = {
        "cargo",
        "go",
        "mypy",
        "node",
        "npm",
        "pnpm",
        "pytest",
        "python",
        "python3",
        "ruff",
        "tsc",
        "yarn",
    }
    blocked_tokens = {";", "|", "&", ">", "<", "`", "$(", ")", "\n"}

    def validate(self, command: str) -> Tuple[bool, str]:
        if not command or not command.strip():
            return False, "empty command"
        if any(token in command for token in self.blocked_tokens):
            return False, "command contains shell metacharacters"
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return False, f"command cannot be parsed safely: {exc}"
        if not argv:
            return False, "empty command"
        executable = os.path.basename(argv[0])
        if executable not in self.allowed_executables and not executable.startswith("python"):
            return False, f"executable '{argv[0]}' is not allowed for verification suggestions"
        return True, ""
