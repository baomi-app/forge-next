import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Tuple, List, Optional, Dict, Any


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
        timeout_seconds: int = 30
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.test_command = test_command
        self.auto_discover = auto_discover
        self.timeout_seconds = timeout_seconds
        self.python_executable = shlex.quote(sys.executable)
        # Re-use the exclude directory logic from tools
        self.exclude_dirs = {".git", "__pycache__", ".venv", ".agents", "node_modules", ".gemini"}

    def verify_syntax(self) -> Tuple[bool, List[str]]:
        """Scans all Python files recursively in the workspace to verify syntax compiles correctly.
        
        Returns:
            Tuple (is_passed, error_messages)
        """
        errors = []
        for root, dirs, files in os.walk(self.workspace_dir):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            
            for file in files:
                if not file.endswith(".py"):
                    continue
                    
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        source = f.read()
                    # compile() is a quick and robust way to check for syntax/indentation errors
                    compile(source, filepath, 'exec')
                except SyntaxError as se:
                    rel_path = os.path.relpath(filepath, self.workspace_dir)
                    errors.append(
                        f"Syntax Error in {rel_path} at line {se.lineno}, col {se.offset}:\n"
                        f"  {se.text.strip() if se.text else ''}\n"
                        f"  Error message: {se.msg}"
                    )
                except Exception as e:
                    rel_path = os.path.relpath(filepath, self.workspace_dir)
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
                return VerificationResult(
                    check=check,
                    passed=False,
                    output="Error: Verification command is empty.",
                    duration_seconds=0.0,
                    failure_kind="invalid_command"
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
            return VerificationResult(
                check=check,
                passed=is_passed,
                output=test_output,
                duration_seconds=time.time() - start_time,
                exit_code=result.returncode,
                failure_kind=None if is_passed else self._classify_failure(check, test_output, result.returncode)
            )
        except subprocess.TimeoutExpired:
            return VerificationResult(
                check=check,
                passed=False,
                output=f"Error: Verification command timed out after {self.timeout_seconds} seconds.",
                duration_seconds=time.time() - start_time,
                failure_kind="timeout"
            )
        except FileNotFoundError as e:
            return VerificationResult(
                check=check,
                passed=False,
                output=f"Error: Required command was not found: {str(e)}",
                duration_seconds=time.time() - start_time,
                failure_kind="missing_command"
            )
        except Exception as e:
            return VerificationResult(
                check=check,
                passed=False,
                output=f"Error launching verification command: {str(e)}",
                duration_seconds=time.time() - start_time,
                failure_kind="launch_error"
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
            report = (
                "[VERIFIER FAILED] Syntax verification failed! "
                "Your changes introduced syntax or compilation errors:\n\n" + 
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
        languages = []
        root_files = set(os.listdir(self.workspace_dir)) if os.path.exists(self.workspace_dir) else set()

        if root_files & {"pyproject.toml", "setup.py", "requirements.txt"} or self._has_file_with_suffix(".py"):
            languages.append("python")
        if root_files & {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}:
            languages.append("node")
        if "go.mod" in root_files:
            languages.append("go")
        if "Cargo.toml" in root_files:
            languages.append("rust")

        return languages

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
                output = result.output
                if len(output) > 1200:
                    output = output[:1200] + "\n... [TRUNCATED CHECK OUTPUT] ..."
                lines.append("  Output:")
                lines.append(output)
        return "\n".join(lines)

    def _classify_failure(self, check: VerificationCheck, output: str, exit_code: int) -> str:
        lowered = output.lower()
        if "no module named" in lowered or "cannot find module" in lowered or "module not found" in lowered:
            return "missing_dependency"
        if "command not found" in lowered or "not recognized as an internal" in lowered:
            return "missing_command"
        if check.category == "lint":
            return "lint_failure"
        if check.category == "typecheck":
            return "typecheck_failure"
        if check.category == "test":
            return "test_failure"
        return f"nonzero_exit_{exit_code}"

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
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            if any(file.endswith(suffix) for file in files):
                return True
        return False

    def _has_python_tests(self) -> bool:
        for root, dirs, files in os.walk(self.workspace_dir):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            for file in files:
                if file.startswith("test_") and file.endswith(".py"):
                    return True
                if file.endswith("_test.py"):
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
