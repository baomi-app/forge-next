import os
import copy
from typing import Optional
from threading import RLock
from forge.completion import CompletionGate
from forge.executor import ToolExecutor
from forge.model import BaseModel
from forge.tools import ToolRegistry, registry
from forge.trace import ExecutionTrace, StepTrace
from forge.verifier import Verifier
from forge.sandbox import LocalRestrictedSandbox
from forge.session import AgentSession
from forge.subagents import SubagentManager
from forge.tool_capabilities import ToolCapabilities

DEFAULT_SYSTEM_PROMPT_TEMPLATE = """You are a software engineering assistant (Coding Agent) running locally in a workspace directory.
You have access to these coding tools: {tool_names}.

Your goal is to complete the user's task using these tools.

To work effectively, you must follow a structured reasoning process. Every response you output must adhere strictly to the following formatting blocks:

Plan:
- [ ] List out your high-level steps here. Use markdown checkboxes.
- Use `[x]` for finished steps, `[/]` for the current active step, and `[ ]` for future remaining steps.
- IMPORTANT: If you encounter an unexpected error, a blocked dependency, or new findings, you must dynamically edit (re-plan) this list to resolve the roadblocks.

Thought:
Describe your observations, findings, and decisions. Explain what you learned from the last tool's output and what your logic is for the next action.

Action:
State what you are doing. If you need to invoke tools, output the tool calls immediately following this response. If the task is finished and verified, summarize your final solution here and output no tool calls.
"""


def build_system_prompt(tool_registry: Optional[ToolRegistry] = None) -> str:
    """Build the default system prompt from the currently registered tool definitions."""
    active_registry = tool_registry or registry
    tool_names = [
        definition["function"]["name"]
        for definition in active_registry.tool_definitions
        if definition.get("type") == "function" and "function" in definition
    ]
    rendered_names = ", ".join(tool_names) if tool_names else "no tools"
    return DEFAULT_SYSTEM_PROMPT_TEMPLATE.format(tool_names=rendered_names)


DEFAULT_SYSTEM_PROMPT = build_system_prompt(registry)


class AgentRunner:
    """The central orchestrator that runs the core Agent Loop with Checkpointing support."""

    def __init__(
        self,
        model: BaseModel,
        system_prompt: Optional[str] = None,
        workspace_dir: str = ".",
        test_command: Optional[str] = None,
        tool_registry: Optional[ToolRegistry] = None,
        model_lock: Optional[RLock] = None,
        tool_lock: Optional[RLock] = None
    ):
        self.model = model
        self.tool_registry = tool_registry or registry
        self.system_prompt = system_prompt or build_system_prompt(self.tool_registry)
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.verifier = Verifier(workspace_dir=self.workspace_dir, test_command=test_command)
        self.sandbox = LocalRestrictedSandbox(self.workspace_dir)
        self.session = AgentSession(
            workspace_dir=self.workspace_dir,
            system_prompt=self.system_prompt,
            test_command=self.verifier.test_command,
        )
        self.completion_gate = CompletionGate(self.verifier, journal_recorder=self.session.journal_recorder)
        self.change_set = self.session.change_set
        self.model_lock = model_lock or RLock()
        self.tool_lock = tool_lock or RLock()
        self.subagent_manager = SubagentManager(self)
        self.tool_capabilities = self._build_tool_capabilities()
        self.tool_executor = ToolExecutor(
            tool_registry=self.tool_registry,
            sandbox=self.sandbox,
            runner=self,
            session=self.session,
            subagent_manager=self.subagent_manager,
            tool_lock=self.tool_lock,
            journal_recorder=self.session.journal_recorder,
            runtime=self.tool_capabilities,
        )

    def _build_tool_capabilities(self) -> ToolCapabilities:
        return ToolCapabilities(
            workspace_dir=self.workspace_dir,
            sandbox=self.sandbox,
            session=self.session,
            subagent_manager=self.subagent_manager,
            journal_recorder=self.session.journal_recorder,
        )

    def save_checkpoint(self, filepath: str, current_iteration: int, context, trace: ExecutionTrace):
        """Serialize current run memory to disk."""
        self.session.current_iteration = current_iteration
        self.session.context = context
        self.session.trace = trace
        self.session.test_command = self.verifier.test_command
        self.session.change_set = self.change_set
        try:
            self.session.save_checkpoint(filepath)
            print(f"[Checkpoint] Successfully saved session state to {filepath}")
        except Exception as e:
            print(f"[Warning] Failed to save checkpoint to {filepath}: {str(e)}")

    def load_checkpoint(self, filepath: str):
        """Deserialize checkpoint state from disk."""
        data = self.session.load_checkpoint(filepath)
        print(f"[Checkpoint] Successfully loaded session state from {filepath}")
        return data

    def run(
        self,
        task: str,
        max_iterations: int = 10,
        resume_from: Optional[str] = None,
        checkpoint_path: str = "checkpoint.json"
    ) -> ExecutionTrace:
        """Executes the main agent loop for a given task, supporting crash recovery from checkpoint.

        Args:
            task: The user query/task description.
            max_iterations: Maximum loop iterations (turns).
            resume_from: Optional path to a checkpoint JSON file to resume from.
            checkpoint_path: Filename to save iteration checkpoints to.
        """
        # Save original working directory to restore later
        original_cwd = os.getcwd()

        start_iteration = 0
        restored = False

        # If resume_from is requested, we change CWD to the workspace to find the file
        try:
            os.chdir(self.workspace_dir)

            if resume_from and os.path.exists(resume_from):
                task = self.session.restore_checkpoint(resume_from)
                print(f"[Checkpoint] Successfully loaded session state from {resume_from}")
                start_iteration = self.session.current_iteration
                self.system_prompt = self.session.system_prompt
                self.verifier.test_command = self.session.test_command
                self.change_set = self.session.change_set
                self.completion_gate.journal_recorder = self.session.journal_recorder
                self.tool_capabilities = self._build_tool_capabilities()
                restored = True

                print(f"[Runner] Resuming agent loop from Iteration {start_iteration + 1}...")
        except Exception as e:
            print(f"[Warning] Failed to load resume file. Starting fresh: {str(e)}")
            os.chdir(original_cwd) # Fallback CWD reset

        # If starting fresh
        if not restored:
            self.session.start(task)
            self.completion_gate.journal_recorder = self.session.journal_recorder
            self.tool_capabilities = self._build_tool_capabilities()
            print(f"\n[Runner] Starting fresh Agent Loop for task: '{task}'")

        context = self.session.context
        trace = self.session.trace
        self.tool_executor.session = self.session
        self.tool_executor.journal_recorder = self.session.journal_recorder
        self.tool_executor.runtime = self.tool_capabilities
        self.tool_executor.runner = self
        self.tool_executor.sandbox = self.sandbox
        self.tool_executor.subagent_manager = self.subagent_manager

        print(f"[Runner] Max iterations: {max_iterations}")
        print(f"[Runner] Workspace isolated to: {self.workspace_dir}")

        try:
            # Always ensure cwd is switched to workspace
            os.chdir(self.workspace_dir)

            for iteration in range(start_iteration + 1, max_iterations + 1):
                print(f"\n[Runner] === Iteration {iteration} ===")

                step = StepTrace(step_idx=iteration)
                step.start_timer()

                # 2. Get current history & tool schemas
                messages = context.get_messages()
                # Deep copy messages for tracing to keep a clean snapshot of context state at this step
                step.input_messages = copy.deepcopy(messages)

                # Fetch tool schemas from registry
                tool_definitions = self.tool_registry.tool_definitions

                # 3. Model call (Context -> Model)
                try:
                    with self.model_lock:
                        content, tool_calls = self.model.generate(messages, tool_definitions)
                except Exception as e:
                    err_msg = f"Fatal Error calling model: {str(e)}"
                    print(f"[Runner] {err_msg}")
                    trace.finish(err_msg)
                    return trace

                step.model_text_response = content
                if tool_calls:
                    step.tool_calls = tool_calls

                # Print thoughts if any
                if content:
                    print(f"[Model Thought/Message]: {content.strip()}")

                # 4. Handle tool execution / continuation decision
                if not tool_calls:
                    result = self.completion_gate.evaluate(content, context, trace, step)
                    if result.passed:
                        if os.path.exists(checkpoint_path):
                            os.remove(checkpoint_path)
                            print(f"[Checkpoint] Cleaned up temporary checkpoint file: {checkpoint_path}")
                        break

                    self.save_checkpoint(checkpoint_path, iteration, context, trace)
                    continue

                # If tool calls are requested, we must add the assistant response to the conversation history.
                # Tool-calling chat APIs require matching tool results to their respective assistant tool calls.
                context.add_assistant(content, tool_calls)

                self.tool_executor.execute_tool_calls(tool_calls, context, step)

                step.stop_timer()
                trace.add_step(step)

                # Save checkpoint at the end of each successful iteration
                self.save_checkpoint(checkpoint_path, iteration, context, trace)

            else:
                # Loop exhausted without model stopping voluntarily
                print("\n[Runner] Warning: Reached max iterations limit!")
                trace.finish("Failed: Maximum iterations reached without resolving the task.")

        finally:
            # Always restore the original working directory
            os.chdir(original_cwd)

        return trace
