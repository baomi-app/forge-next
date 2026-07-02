import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Tuple, List, Optional, Dict, Any

from forge.project import ProjectPolicy, ProjectProfiler


@dataclass
class VerificationCheck:
    """A runnable project verification command."""

    name: str
    command: str
    category: str
    source: str


@dataclass
class VerificationResult:
    """Structured result from one verification command."""

    check: VerificationCheck
    passed: bool
    output: str
    duration_seconds: float
    exit_code: Optional[int] = None
    failure_kind: Optional[str] = None
    triage: Optional["FailureTriage"] = None


@dataclass
class FailureTriage:
    """Actionable diagnosis for a failed verification command."""

    kind: str
    summary: str
    next_step: str
    evidence: List[str]


@dataclass
class ProjectProfile:
    """Detected workspace traits used to choose verification checks."""

    languages: List[str]
    checks: List[VerificationCheck]
    notes: List[str]


class Verifier:
    """Automated code gatekeeper for project-aware syntax, test, and quality checks."""
    
    def __init__(
        self,
        workspace_dir: str = ".",
        test_command: Optional[str] = None,
        auto_discover: bool = True,
        timeout_seconds: int = 30,
        policy: Optional[ProjectPolicy] = None,
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.test_command = test_command
        self.auto_discover = auto_discover
        self.timeout_seconds = timeout_seconds
        self.python_executable = shlex.quote(sys.executable)
        self.policy = policy or ProjectPolicy()

    def verify_syntax(self) -> Tuple[bool, List[str]]:
        """Scans all Python files recursively in the workspace to verify syntax compiles correctly.
        
        Returns:
            Tuple (is_passed, error_messages)
        """
        errors = []
        for root, dirs, files in os.walk(self.workspace_dir):
            dirs[:] = [d for d in dirs if self.policy.should_descend_dir(d)]
            
            for file in files:
                if not file.endswith(".py"):
                    continue
                    
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, self.workspace_dir)
                if not self.policy.should_track_file(rel_path):
                    continue
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        source = f.read()
                    # compile() is a quick and robust way to check for syntax/indentation errors
                    compile(source, filepath, 'exec')
                except SyntaxError as se:
                    errors.append(
                        f"Syntax Error in {rel_path} at line {se.lineno}, col {se.offset}:\n"
                        f"  {se.text.strip() if se.text else ''}\n"
                        f"  Error message: {se.msg}"
                    )
                except Exception as e:
                    errors.append(f"Unexpected error parsing {rel_path}: {str(e)}")
                    
        is_passed = len(errors) == 0
        return is_passed, errors

    def discover_project(self) -> ProjectProfile:
        """Detect project type and choose verification commands.

        Explicit test commands take precedence. Otherwise Forge looks for common
        project files and lightweight test conventions.
        """
        languages = []
        notes = []
        checks = []

        if self.test_command:
            return ProjectProfile(
                languages=self._detect_languages(),
                checks=[
                    VerificationCheck(
                        name="configured test command",
                        command=self.test_command,
                        category="test",
                        source="runner configuration"
                    )
                ],
                notes=["Using the explicitly configured verification command."]
            )

        languages = self._detect_languages()
        if not self.auto_discover:
            return ProjectProfile(
                languages=languages,
                checks=[],
                notes=["Automatic verification discovery is disabled."]
            )

        if "python" in languages:
            checks.extend(self._discover_python_checks(notes))
        if "node" in languages:
            checks.extend(self._discover_node_checks(notes))
        if "go" in languages:
            checks.append(VerificationCheck("go tests", "go test ./...", "test", "go.mod"))
        if "rust" in languages:
            checks.append(VerificationCheck("cargo tests", "cargo test", "test", "Cargo.toml"))

        if not checks:
            notes.append("No runnable project checks were discovered.")

        return ProjectProfile(languages=languages, checks=checks, notes=notes)

    def run_tests(self) -> Tuple[bool, str]:
        """Runs the registered or auto-discovered project verification commands.
        
        Returns:
            Tuple (is_passed, test_output)
        """
        profile = self.discover_project()
        if not profile.checks:
            return True, self._format_project_summary(profile)

        results = [self._run_check(check) for check in profile.checks]
        passed = all(result.passed for result in results)
        return passed, self._format_project_report(profile, results)

    def _run_check(self, check: VerificationCheck) -> VerificationResult:
        """Execute one verification command and classify failures."""
        start_time = time.time()
        try:
            argv = shlex.split(check.command)
            if not argv:
                triage = FailureTriage(
                    kind="invalid_command",
                    summary="The verification command is empty.",
                    next_step="Configure a non-empty verification command before rerunning verification.",
                    evidence=[],
                )
                return VerificationResult(
                    check=check,
                    passed=False,
                    output="Error: Verification command is empty.",
                    duration_seconds=0.0,
                    failure_kind=triage.kind,
                    triage=triage,
                )

            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                cwd=self.workspace_dir,
                timeout=self.timeout_seconds
            )
            is_passed = result.returncode == 0
            output = []
            if result.stdout:
                output.append(result.stdout)
            if result.stderr:
                output.append(result.stderr)

            test_output = "\n".join(output) or "(No output)"
            triage = None if is_passed else self.triage_failure(check, test_output, result.returncode)
            return VerificationResult(
                check=check,
                passed=is_passed,
                output=test_output,
                duration_seconds=time.time() - start_time,
                exit_code=result.returncode,
                failure_kind=None if is_passed else triage.kind,
                triage=triage,
            )
        except subprocess.TimeoutExpired:
            triage = FailureTriage(
                kind="timeout",
                summary=f"The verification command exceeded the {self.timeout_seconds}s timeout.",
                next_step="Inspect whether the command is hanging, waiting for input, or running too broad a check.",
                evidence=[f"Timed out after {self.timeout_seconds} seconds."],
            )
            return VerificationResult(
                check=check,
                passed=False,
                output=f"Error: Verification command timed out after {self.timeout_seconds} seconds.",
                duration_seconds=time.time() - start_time,
                failure_kind=triage.kind,
                triage=triage,
            )
        except FileNotFoundError as e:
            triage = FailureTriage(
                kind="missing_command",
                summary="The executable for the verification command was not found.",
                next_step="Install the missing command or update the verification command to one available in this environment.",
                evidence=[str(e)],
            )
            return VerificationResult(
                check=check,
                passed=False,
                output=f"Error: Required command was not found: {str(e)}",
                duration_seconds=time.time() - start_time,
                failure_kind=triage.kind,
                triage=triage,
            )
        except Exception as e:
            triage = FailureTriage(
                kind="launch_error",
                summary="Forge could not launch the verification command.",
                next_step="Check the command syntax, working directory, and environment before rerunning verification.",
                evidence=[str(e)],
            )
            return VerificationResult(
                check=check,
                passed=False,
                output=f"Error launching verification command: {str(e)}",
                duration_seconds=time.time() - start_time,
                failure_kind=triage.kind,
                triage=triage,
            )

    def verify(self) -> Tuple[bool, str]:
        """Runs all verification passes in sequence.
        
        Returns:
            Tuple (is_all_passed, detailed_report_str)
        """
        print("[Verifier] Running verification checks...")
        
        # 1. Syntax Check (Fastest, block-level errors)
        syntax_passed, syntax_errors = self.verify_syntax()
        if not syntax_passed:
            triage = FailureTriage(
                kind="syntax_error",
                summary="Python source failed to compile before project checks could run.",
                next_step="Fix the reported file and line first, then rerun verification.",
                evidence=syntax_errors[:3],
            )
            report = (
                "[VERIFIER FAILED] Syntax verification failed! "
                "Your changes introduced syntax or compilation errors:\n\n" + 
                self._format_triage(triage) +
                "\n\n" +
                "\n---\n".join(syntax_errors) + 
                "\n\nPlease correct these syntax issues before trying to finish."
            )
            print("[Verifier] Status: FAILED (Syntax Error)")
            return False, report
            
        # 2. Project-aware checks (tests, lint, typecheck, etc.)
        tests_passed, test_output = self.run_tests()
        if not tests_passed:
            if len(test_output) > 2500:
                test_output = test_output[:2500] + "\n... [TRUNCATED VERIFICATION OUTPUT] ..."
            report = (
                "[VERIFIER FAILED] Project verification failed. "
                "At least one discovered check did not pass:\n\n"
                f"{test_output}\n"
                "Please analyze the failure and correct the code."
            )
            print("[Verifier] Status: FAILED (Project Check Failure)")
            return False, report
                
        print("[Verifier] Status: PASSED")
        return True, "[VERIFIER PASSED] All compilation and project checks passed successfully.\n\n" + test_output

    def _detect_languages(self) -> List[str]:
        """Detect likely project languages from known files and extensions."""
        return ProjectProfiler(self.workspace_dir, policy=self.policy).profile().languages

    def _discover_python_checks(self, notes: List[str]) -> List[VerificationCheck]:
        """Find Python test commands that are likely to work in the current environment."""
        checks = []
        has_tests = self._has_python_tests()
        has_pytest_config = self._has_any_file({"pytest.ini", "tox.ini"}) or self._pyproject_mentions("pytest")

        if has_pytest_config and self._python_module_available("pytest"):
            checks.append(VerificationCheck("pytest suite", f"{self.python_executable} -m pytest", "test", "pytest configuration"))
        elif has_pytest_config:
            notes.append("Detected pytest configuration, but pytest is not importable in the current environment.")

        if has_tests and not checks:
            checks.append(VerificationCheck("unittest discovery", f"{self.python_executable} -m unittest discover", "test", "Python test files"))

        return checks

    def _discover_node_checks(self, notes: List[str]) -> List[VerificationCheck]:
        """Find Node package scripts without assuming a particular package manager."""
        package_json = os.path.join(self.workspace_dir, "package.json")
        if not os.path.exists(package_json):
            return []

        try:
            with open(package_json, "r", encoding="utf-8") as f:
                package_data: Dict[str, Any] = json.load(f)
        except Exception as e:
            notes.append(f"Could not read package.json for script discovery: {str(e)}")
            return []

        scripts = package_data.get("scripts", {})
        if not isinstance(scripts, dict):
            return []

        manager = self._node_package_manager()
        candidates = [
            ("lint", "lint", "lint"),
            ("typecheck", "typecheck", "typecheck"),
            ("test", "test", "test"),
        ]
        checks = []
        for script_name, category, display_name in candidates:
            if script_name in scripts:
                command = f"{manager} run {script_name}" if manager != "npm" or script_name != "test" else "npm test"
                checks.append(VerificationCheck(f"node {display_name}", command, category, f"package.json scripts.{script_name}"))
        return checks

    def _format_project_summary(self, profile: ProjectProfile) -> str:
        languages = ", ".join(profile.languages) if profile.languages else "unknown"
        notes = "\n".join(f"- {note}" for note in profile.notes)
        return (
            "[Project Verification]\n"
            f"Detected languages: {languages}\n"
            "Runnable checks: none\n"
            f"{notes}"
        )

    def _format_project_report(self, profile: ProjectProfile, results: List[VerificationResult]) -> str:
        lines = ["[Project Verification]"]
        languages = ", ".join(profile.languages) if profile.languages else "unknown"
        lines.append(f"Detected languages: {languages}")
        if profile.notes:
            lines.append("Notes:")
            lines.extend(f"- {note}" for note in profile.notes)
        lines.append("Checks:")
        for result in results:
            status = "PASS" if result.passed else "FAIL"
            exit_code = "n/a" if result.exit_code is None else str(result.exit_code)
            lines.append(
                f"- {status} [{result.check.category}] {result.check.name}: "
                f"`{result.check.command}` "
                f"(source: {result.check.source}, exit: {exit_code}, "
                f"duration: {result.duration_seconds:.2f}s"
                + (f", failure: {result.failure_kind}" if result.failure_kind else "")
                + ")"
            )
            if not result.passed:
                if result.triage:
                    lines.append("  " + self._format_triage(result.triage).replace("\n", "\n  "))
                output = result.output
                if len(output) > 1200:
                    output = output[:1200] + "\n... [TRUNCATED CHECK OUTPUT] ..."
                lines.append("  Output:")
                lines.append(output)
        return "\n".join(lines)

    def triage_failure(self, check: VerificationCheck, output: str, exit_code: int) -> FailureTriage:
        """Classify failed output and produce a repair-oriented hint."""
        lowered = output.lower()
        if "no module named" in lowered or "cannot find module" in lowered or "module not found" in lowered:
            return FailureTriage(
                kind="missing_dependency",
                summary="The check could not import or resolve a required dependency.",
                next_step="Verify the dependency name, install it, or adjust the code/import path to use an available module.",
                evidence=self._evidence_lines(output, ["no module named", "cannot find module", "module not found"]),
            )
        if "command not found" in lowered or "not recognized as an internal" in lowered:
            return FailureTriage(
                kind="missing_command",
                summary="The check references a command that is unavailable in this environment.",
                next_step="Install the command or change the project check to an available executable.",
                evidence=self._evidence_lines(output, ["command not found", "not recognized as an internal"]),
            )
        if "syntaxerror" in lowered or "indentationerror" in lowered:
            return FailureTriage(
                kind="syntax_error",
                summary="The verification command failed while parsing source code.",
                next_step="Fix the reported syntax or indentation location before investigating test assertions.",
                evidence=self._evidence_lines(output, ["syntaxerror", "indentationerror"]),
            )
        if "assertionerror" in lowered or "assert " in lowered or ("expected" in lowered and "actual" in lowered):
            return FailureTriage(
                kind="assertion_failure",
                summary="A test assertion failed, so behavior differs from the expected result.",
                next_step="Read the failing test expectation and adjust the implementation or test fixture accordingly.",
                evidence=self._evidence_lines(output, ["assertionerror", "assert ", "expected", "actual"]),
            )
        if "permission denied" in lowered:
            return FailureTriage(
                kind="permission_error",
                summary="The check could not access a file or execute a command because of permissions.",
                next_step="Check file permissions, executable bits, and whether the command writes outside the workspace.",
                evidence=self._evidence_lines(output, ["permission denied"]),
            )
        if "no such file or directory" in lowered:
            return FailureTriage(
                kind="missing_file",
                summary="The check expected a file or path that does not exist.",
                next_step="Create the missing file, fix the path, or run the command from the correct workspace.",
                evidence=self._evidence_lines(output, ["no such file or directory"]),
            )
        if check.category == "lint":
            return FailureTriage(
                kind="lint_failure",
                summary="A lint check reported style or static quality violations.",
                next_step="Fix the reported lint diagnostics, then rerun the lint command.",
                evidence=self._evidence_lines(output, ["error", "warning", "unexpected"]),
            )
        if check.category == "typecheck":
            return FailureTriage(
                kind="typecheck_failure",
                summary="A type checker found incompatible or unresolved types.",
                next_step="Use the reported type diagnostic to update annotations, data shapes, or call sites.",
                evidence=self._evidence_lines(output, ["error", "type", "not assignable"]),
            )
        if check.category == "test":
            return FailureTriage(
                kind="test_failure",
                summary="A test command failed, but Forge could not identify a narrower failure type.",
                next_step="Inspect the first failing test and its traceback, then rerun the focused test after fixing it.",
                evidence=self._evidence_lines(output, ["fail", "error", "traceback"]),
            )
        return FailureTriage(
            kind=f"nonzero_exit_{exit_code}",
            summary=f"The check exited with status code {exit_code}.",
            next_step="Inspect the command output and address the first actionable error.",
            evidence=self._evidence_lines(output, ["error", "fail", "warning"]),
        )

    def _classify_failure(self, check: VerificationCheck, output: str, exit_code: int) -> str:
        return self.triage_failure(check, output, exit_code).kind

    def _format_triage(self, triage: FailureTriage) -> str:
        lines = [
            "[Failure Triage]",
            f"- kind: {triage.kind}",
            f"- summary: {triage.summary}",
            f"- next step: {triage.next_step}",
        ]
        if triage.evidence:
            lines.append("- evidence:")
            lines.extend(f"  - {line}" for line in triage.evidence)
        return "\n".join(lines)

    def _evidence_lines(self, output: str, patterns: List[str], max_lines: int = 3) -> List[str]:
        matches = []
        lowered_patterns = [pattern.lower() for pattern in patterns]
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if any(pattern in lowered for pattern in lowered_patterns):
                matches.append(stripped)
            if len(matches) >= max_lines:
                return matches
        if matches:
            return matches
        for line in output.splitlines():
            stripped = line.strip()
            if stripped:
                matches.append(stripped)
            if len(matches) >= max_lines:
                break
        return matches

    def _node_package_manager(self) -> str:
        if os.path.exists(os.path.join(self.workspace_dir, "pnpm-lock.yaml")):
            return "pnpm"
        if os.path.exists(os.path.join(self.workspace_dir, "yarn.lock")):
            return "yarn"
        return "npm"

    def _has_any_file(self, filenames: set) -> bool:
        return any(os.path.exists(os.path.join(self.workspace_dir, name)) for name in filenames)

    def _has_file_with_suffix(self, suffix: str) -> bool:
        for root, dirs, files in os.walk(self.workspace_dir):
            dirs[:] = [d for d in dirs if self.policy.should_descend_dir(d)]
            if any(
                file.endswith(suffix)
                and self.policy.should_track_file(os.path.relpath(os.path.join(root, file), self.workspace_dir))
                for file in files
            ):
                return True
        return False

    def _has_python_tests(self) -> bool:
        for root, dirs, files in os.walk(self.workspace_dir):
            dirs[:] = [d for d in dirs if self.policy.should_descend_dir(d)]
            for file in files:
                path = os.path.relpath(os.path.join(root, file), self.workspace_dir)
                if not self.policy.should_track_file(path):
                    continue
                if self.policy.is_test(path) and file != "__init__.py" and file.endswith(".py"):
                    return True
        return False

    def _pyproject_mentions(self, text: str) -> bool:
        pyproject = os.path.join(self.workspace_dir, "pyproject.toml")
        if not os.path.exists(pyproject):
            return False
        try:
            with open(pyproject, "r", encoding="utf-8") as f:
                return text in f.read()
        except Exception:
            return False

    def _python_module_available(self, module_name: str) -> bool:
        result = subprocess.run(
            [sys.executable, "-c", f"import {module_name}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
