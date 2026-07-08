import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Tuple, List, Optional, Dict, Any

from forge.command_policy import CommandPolicy
from forge.llm_decisions import LLMDecisionError
from forge.project import ProjectFileCollector, ProjectPolicy


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
        decision_service: Optional[Any] = None,
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.test_command = test_command
        self.auto_discover = auto_discover
        self.timeout_seconds = timeout_seconds
        self.python_executable = shlex.quote(sys.executable)
        self.policy = policy or ProjectPolicy()
        self.decision_service = decision_service
        self.command_policy = CommandPolicy()

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
        if self.test_command:
            return ProjectProfile(
                languages=[],
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

        if not self.auto_discover:
            return ProjectProfile(
                languages=[],
                checks=[],
                notes=["Automatic verification discovery is disabled."]
            )

        if not self.decision_service:
            return ProjectProfile(
                languages=[],
                checks=[],
                notes=["LLM project verification planning is not configured."],
            )

        try:
            decision = self.decision_service.plan_project_verification(
                ProjectFileCollector(self.workspace_dir, policy=self.policy).facts()
            )
        except LLMDecisionError as exc:
            return ProjectProfile(
                languages=[],
                checks=[],
                notes=[f"LLM project verification planning failed: {exc}"],
            )

        notes = list(decision.notes)
        checks = []
        for check in decision.checks:
            allowed, reason = self.command_policy.validate(check.command)
            if not allowed:
                notes.append(f"LLM suggested an unsafe project verification command '{check.command}': {reason}")
                continue
            checks.append(
                VerificationCheck(
                    name=check.name,
                    command=check.command,
                    category=check.category,
                    source=check.source,
                )
            )

        if not checks:
            notes.append("No runnable project checks were selected by LLM.")

        return ProjectProfile(languages=decision.languages, checks=checks, notes=notes)

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
        """Ask the LLM to classify failed output and produce a repair-oriented hint."""
        if not self.decision_service:
            return FailureTriage(
                kind="llm_unavailable",
                summary="LLM failure triage is not configured.",
                next_step="Configure an LLMDecisionService so Forge can diagnose this verification failure.",
                evidence=self._first_nonempty_lines(output),
            )
        try:
            decision = self.decision_service.triage_failure(check, output, exit_code)
            return FailureTriage(
                kind=decision.kind,
                summary=decision.summary,
                next_step=decision.next_step,
                evidence=decision.evidence,
            )
        except LLMDecisionError as exc:
            return FailureTriage(
                kind="llm_decision_error",
                summary="LLM failure triage returned an invalid or unavailable decision.",
                next_step="Fix the LLM decision configuration or rerun with a valid structured triage response.",
                evidence=[str(exc), *self._first_nonempty_lines(output, max_lines=2)],
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

    def _first_nonempty_lines(self, output: str, max_lines: int = 3) -> List[str]:
        matches = []
        for line in output.splitlines():
            stripped = line.strip()
            if stripped:
                matches.append(stripped)
            if len(matches) >= max_lines:
                break
        return matches
