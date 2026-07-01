import fnmatch
import os
from dataclasses import dataclass
from typing import Iterable, List, Optional

from forge.changes import ChangeSet, FileChange


@dataclass
class ReviewFinding:
    """One change review finding."""

    severity: str
    message: str
    path: Optional[str] = None


class ChangeReviewer:
    """Reviews task-scoped changes for delivery and commit readiness."""

    GENERATED_PATTERNS = {
        ".DS_Store",
        "*.pyc",
        "*.pyo",
        "*.log",
        "*.tmp",
        "*~",
        ".vscode/*",
        ".idea/*",
        "__pycache__/*",
        "mock_trace.json",
        "verifier_trace.json",
        "temp_*/*",
    }
    TEST_PATTERNS = {
        "test_*.py",
        "*_test.py",
        "tests/*",
        "*/tests/*",
    }
    DOC_PATTERNS = {
        "README.md",
        "VERSION.md",
        "AGENTS.md",
        "docs/*",
        "examples/*",
    }
    USER_FACING_CODE = {
        "forge/tools.py",
        "forge/runner.py",
        "forge/verifier.py",
        "forge/changes.py",
        "forge/session.py",
        "forge/completion.py",
        "forge/executor.py",
    }

    def review(self, change_set: ChangeSet, task_goal: str = "") -> str:
        """Return a human-readable review of the current transaction."""
        changes = change_set.changes()
        findings = self._findings(changes)
        status = self._status(changes, findings)
        commit_shape = self._commit_shape(changes, findings)
        commit_message = self._suggest_commit_message(changes, task_goal)

        lines = [
            f"Status: {status}",
            f"Changed files: {len(changes)}",
        ]
        if task_goal:
            lines.append(f"Task goal: {task_goal}")

        lines.append("")
        lines.append("Files:")
        if changes:
            lines.extend(f"- {change.status}: {change.path}" for change in changes)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Findings:")
        if findings:
            lines.extend(self._format_finding(finding) for finding in findings)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Commit shape:")
        lines.extend(f"- {item}" for item in commit_shape)
        lines.append(f"- suggested message: {commit_message}")

        return "\n".join(lines)

    def _findings(self, changes: List[FileChange]) -> List[ReviewFinding]:
        findings: List[ReviewFinding] = []
        if not changes:
            findings.append(ReviewFinding("BLOCK", "No transaction changes were found."))
            return findings

        for change in changes:
            if self._matches(change.path, self.GENERATED_PATTERNS):
                findings.append(
                    ReviewFinding(
                        "BLOCK",
                        "Generated, temporary, or local editor file should not be committed.",
                        change.path,
                    )
                )

        code_changes = [change for change in changes if self._is_code(change.path)]
        test_changes = [change for change in changes if self._is_test(change.path)]
        doc_changes = [change for change in changes if self._is_doc(change.path)]

        if code_changes and not test_changes:
            findings.append(
                ReviewFinding(
                    "WARN",
                    "Code changed but no test files changed. Add or update tests, or record why existing coverage is enough.",
                )
            )

        if any(change.path in self.USER_FACING_CODE for change in code_changes) and not doc_changes:
            findings.append(
                ReviewFinding(
                    "WARN",
                    "User-facing runtime behavior changed without README, VERSION, or example updates.",
                )
            )

        if len(changes) > 12:
            findings.append(
                ReviewFinding(
                    "WARN",
                    "Large transaction touches many files; verify this is still one atomic feature or fix.",
                )
            )

        return findings

    def _status(self, changes: List[FileChange], findings: List[ReviewFinding]) -> str:
        if any(finding.severity == "BLOCK" for finding in findings):
            return "BLOCK"
        if any(finding.severity == "WARN" for finding in findings):
            return "WARN"
        if changes:
            return "PASS"
        return "BLOCK"

    def _commit_shape(self, changes: List[FileChange], findings: List[ReviewFinding]) -> List[str]:
        if not changes:
            return ["not ready: no changed files"]
        if any(finding.severity == "BLOCK" for finding in findings):
            return ["not ready: blocking findings must be resolved"]
        if any(finding.severity == "WARN" for finding in findings):
            return ["review needed: warnings should be resolved or explained before commit"]
        return ["atomic candidate: changed files look consistent for one feature or fix"]

    def _suggest_commit_message(self, changes: List[FileChange], task_goal: str) -> str:
        if task_goal:
            summary = task_goal.strip().splitlines()[0].rstrip(".")
            return f"feat: {summary[:72]}"
        if any(change.status == "deleted" for change in changes):
            return "fix: remove obsolete code"
        if any(self._is_code(change.path) for change in changes):
            return "feat: update agent behavior"
        return "docs: update project documentation"

    def _is_code(self, path: str) -> bool:
        return path.endswith((".py", ".js", ".ts", ".tsx", ".go", ".rs"))

    def _is_test(self, path: str) -> bool:
        return self._matches(path, self.TEST_PATTERNS)

    def _is_doc(self, path: str) -> bool:
        return self._matches(path, self.DOC_PATTERNS)

    def _matches(self, path: str, patterns: Iterable[str]) -> bool:
        basename = os.path.basename(path)
        return any(fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(basename, pattern) for pattern in patterns)

    def _format_finding(self, finding: ReviewFinding) -> str:
        prefix = f"- {finding.severity}: "
        if finding.path:
            return f"{prefix}{finding.path}: {finding.message}"
        return f"{prefix}{finding.message}"
