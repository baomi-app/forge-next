import os
import sys
import json
from typing import List, Dict, Any, Tuple, Optional

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner

class SandboxMockModel(BaseModel):
    """A simulated model that attempts multiple dangerous commands and infinite loops 
    to demonstrate sandbox safety and timeout controls, before completing a task 
    using the new edit_file_block tool.
    """
    
    def __init__(self):
        self.step_idx = 0

    def generate(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        self.step_idx += 1
        
        # Iteration 1: Attempt dangerous rm -rf command (Blocked)
        if self.step_idx == 1:
            print("[MockModel] Thinking: Attempting to clear the local build files using rm -rf.")
            return (
                "I will clean up the build directory using a recursive remove command.",
                [{"id": "sb_call_1", "type": "function", "function": {
                    "name": "run_command",
                    "arguments": json.dumps({"command": "rm -rf /some/dangerous/path"})
                }}]
            )
            
        # Iteration 2: Attempt network curl fetch (Blocked)
        elif self.step_idx == 2:
            print("[MockModel] Thinking: Attempting to fetch web assets via curl.")
            return (
                "The cleanup command was blocked by the sandbox. I will try to fetch external assets instead.",
                [{"id": "sb_call_2", "type": "function", "function": {
                    "name": "run_command",
                    "arguments": json.dumps({"command": "curl -s http://example.com/asset.zip"})
                }}]
            )
            
        # Iteration 3: Run hanging infinite loop command (Timeout Terminated)
        elif self.step_idx == 3:
            print("[MockModel] Thinking: Executing a command that hangs indefinitely.")
            # Run a quick python block that sleeps for 15 seconds to simulate infinite loop
            return (
                "The curl command was blocked. I will run a local computation process to test the runner.",
                [{"id": "sb_call_3", "type": "function", "function": {
                    "name": "run_command",
                    "arguments": json.dumps({"command": "python -c \"import time; time.sleep(15)\""})
                }}]
            )
            
        # Iteration 4: Read calculator.py to locate the divide-by-zero bug
        elif self.step_idx == 4:
            print("[MockModel] Thinking: Let's focus on the actual task. Reading calculator.py.")
            return (
                "I will read the calculator script to inspect the logic.",
                [{"id": "sb_call_4", "type": "function", "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"filepath": "calculator.py"})
                }}]
            )
            
        # Iteration 5: Fix bug using the new edit_file_block tool
        elif self.step_idx == 5:
            print("[MockModel] Thinking: Applying line-block edit to replace the division line.")
            # Bug is on line 2 (return a / b). We replace line 2 to 2 with defensive check
            target_replacement = "    if b == 0:\n        return 0\n    return a / b"
            return (
                "I see the division bug on line 2. I will apply a precise line-range replacement.",
                [{"id": "sb_call_5", "type": "function", "function": {
                    "name": "edit_file_block",
                    "arguments": json.dumps({
                        "filepath": "calculator.py",
                        "start_line": 2,
                        "end_line": 2,
                        "replacement": target_replacement
                    })
                }}]
            )
            
        # Iteration 6: Re-run tests and finish
        elif self.step_idx == 6:
            print("[MockModel] Thinking: Re-running test commands to verify.")
            return (
                "I will re-run the unit tests to confirm the fix.",
                [{"id": "sb_call_6", "type": "function", "function": {
                    "name": "run_command",
                    "arguments": json.dumps({"command": "python -m unittest test_calc.py"})
                }}]
            )
            
        # Iteration 7: Done!
        else:
            print("[MockModel] Thinking: Sandboxed run completed successfully.")
            return ("The sandbox execution limits have been demonstrated and the calculator bug successfully fixed.", None)


def setup_environment(workspace: str):
    if not os.path.exists(workspace):
        os.makedirs(workspace)
        
    print("[Demo Setup] Creating calculator.py with divide by zero bug...")
    with open(os.path.join(workspace, "calculator.py"), "w", encoding="utf-8") as f:
        f.write('''def divide(a, b):
    return a / b
''')

    print("[Demo Setup] Creating test_calc.py...")
    with open(os.path.join(workspace, "test_calc.py"), "w", encoding="utf-8") as f:
        f.write('''import unittest
from calculator import divide

class TestCalc(unittest.TestCase):
    def test_divide(self):
        self.assertEqual(divide(6, 2), 3)
        self.assertEqual(divide(5, 0), 0) # Trigger boundary check

if __name__ == '__main__':
    unittest.main()
''')

def cleanup_environment(workspace: str):
    print(f"\n[Demo Cleanup] Removing sandbox workspace: {workspace}")
    import shutil
    if os.path.exists(workspace):
        shutil.rmtree(workspace)


def main():
    workspace = os.path.abspath("temp_sandbox")
    setup_environment(workspace)
    
    task = "Inspect calculator.py, fix divide-by-zero, and run tests."
    
    try:
        model = SandboxMockModel()
        runner = AgentRunner(
            model=model, 
            workspace_dir=workspace, 
            test_command="python -m unittest test_calc.py"
        )
        
        # In this sandbox, we configure LocalRestrictedSandbox's execute_command
        # to timeout after 2 seconds instead of the default 10, to speed up this demo.
        # We achieve this by patching runner or simply setting the sandbox limit
        runner.sandbox.execute_command = lambda cmd, timeout_seconds=2: runner.sandbox.__class__.execute_command(runner.sandbox, cmd, timeout_seconds=timeout_seconds)
        
        # Run agent loop
        trace = runner.run(task, max_iterations=8, checkpoint_path="sandbox_checkpoint.json")
        
        trace.print_summary()
        
    finally:
        cleanup_environment(workspace)

if __name__ == "__main__":
    main()
