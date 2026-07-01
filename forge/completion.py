from dataclasses import dataclass
from typing import Optional

from forge.context import Context
from forge.trace import ExecutionTrace, StepTrace
from forge.verifier import Verifier


@dataclass
class CompletionResult:
    """Decision for a model turn that attempted to finish."""

    passed: bool
    report: str


class CompletionGate:
    """Decides whether the agent may finish after a no-tool model response."""

    def __init__(self, verifier: Verifier):
        self.verifier = verifier

    def evaluate(
        self,
        content: Optional[str],
        context: Context,
        trace: ExecutionTrace,
        step: StepTrace,
    ) -> CompletionResult:
        """Run completion checks and update context/trace for pass or block."""
        is_passed, report = self.verifier.verify()
        if is_passed:
            step.stop_timer()
            trace.add_step(step)
            print("[Runner] Verifier PASSED! Task complete.")
            trace.finish(content or "No final response provided.")
            return CompletionResult(passed=True, report=report)

        print(f"[Runner] Verifier BLOCKED termination. Report:\n{report}")
        context.add_assistant(content, None)
        context.add_user(report)
        step.tool_results.append({
            "tool_call_id": "verifier_check",
            "name": "auto_verifier",
            "content": report,
        })
        step.stop_timer()
        trace.add_step(step)
        return CompletionResult(passed=False, report=report)
