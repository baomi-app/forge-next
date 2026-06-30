import os
import sys
import json
from typing import List, Dict, Any, Tuple, Optional

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner

class PlanningMockModel(BaseModel):
    """A simulated model demonstrating a structured Plan-Thought-Action loop 
    and a dynamic Replanning sequence when blocked by an import error.
    """
    
    def __init__(self):
        self.step_idx = 0

    def generate(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        self.step_idx += 1
        
        # Iteration 1: List files in workspace
        if self.step_idx == 1:
            print("[MockModel] Thinking: Formulating initial plan and scanning files.")
            response = """Plan:
- [/] 1. Scan directory files to locate tests
- [ ] 2. Run the test suite

Thought:
I need to examine the workspace directory to find which python files contain our unit tests.

Action:
Listing files in the workspace.
"""
            return (
                response,
                [{"id": "p_call_1", "type": "function", "function": {"name": "list_files", "arguments": "{}"}}]
            )
            
        # Iteration 2: Attempt to run the test suite
        elif self.step_idx == 2:
            print("[MockModel] Thinking: Found test_math.py. Attempting to run it.")
            response = """Plan:
- [x] 1. Scan directory files to locate tests
- [/] 2. Run the test suite

Thought:
I see 'test_math.py' in the file list. I will execute it using run_command to verify the workspace logic.

Action:
Running test suite via unittest.
"""
            return (
                response,
                [{"id": "p_call_2", "type": "function", "function": {
                    "name": "run_command",
                    "arguments": json.dumps({"command": "python -m unittest test_math.py"})
                }}]
            )
            
        # Iteration 3: DETECT BLOCK & REPLAN
        # The tool result from run_command will show a ModuleNotFoundError for 'nonexistent_dependency_abc123'.
        # The agent dynamically edits its Plan to add a cleanup step.
        elif self.step_idx == 3:
            print("[MockModel] Thinking: Oh no! Blocked by import error. Replanning to remove import.")
            response = """Plan:
- [x] 1. Scan directory files to locate tests
- [x] 2. Run the test suite (Blocked: missing nonexistent_dependency_abc123 dependency)
- [/] 3. Remove redundant nonexistent_dependency_abc123 import in test_math.py (Replanned step)
- [ ] 4. Re-run test suite

Thought:
The test failed because it tries to import 'nonexistent_dependency_abc123', which is not installed. Looking closely at test_math.py, this import is redundant and unused. I will patch test_math.py to remove it.

Action:
Applying patch to test_math.py.
"""
            target = "import nonexistent_dependency_abc123\nimport unittest"
            replacement = "import unittest"
            return (
                response,
                [{"id": "p_call_3", "type": "function", "function": {
                    "name": "apply_patch",
                    "arguments": json.dumps({
                        "filepath": "test_math.py",
                        "target": target,
                        "replacement": replacement
                    })
                }}]
            )
            
        # Iteration 4: Re-run tests now that block is resolved
        elif self.step_idx == 4:
            print("[MockModel] Thinking: Redundant import removed. Re-running tests.")
            response = """Plan:
- [x] 1. Scan directory files to locate tests
- [x] 2. Run the test suite (Blocked: missing nonexistent_dependency_abc123 dependency)
- [x] 3. Remove redundant nonexistent_dependency_abc123 import in test_math.py
- [/] 4. Re-run test suite

Thought:
Now that the redundant import has been successfully patched, the test suite should execute without any import errors.

Action:
Executing unittest command again.
"""
            return (
                response,
                [{"id": "p_call_4", "type": "function", "function": {
                    "name": "run_command",
                    "arguments": json.dumps({"command": "python -m unittest test_math.py"})
                }}]
            )
            
        # Iteration 5: Done!
        else:
            print("[MockModel] Thinking: Verification successful. Stopping.")
            response = """Plan:
- [x] 1. Scan directory files to locate tests
- [x] 2. Run the test suite (Blocked: missing nonexistent_dependency_abc123 dependency)
- [x] 3. Remove redundant nonexistent_dependency_abc123 import in test_math.py
- [x] 4. Re-run test suite (Passed)

Thought:
All tests are running green now. The roadblock has been successfully resolved and changes verified.

Action:
Task is complete!
"""
            return (response, None)


def setup_environment(workspace: str):
    if not os.path.exists(workspace):
        os.makedirs(workspace)
        
    print("[Demo Setup] Creating test_math.py with redundant import bug...")
    with open(os.path.join(workspace, "test_math.py"), "w", encoding="utf-8") as f:
        f.write('''import nonexistent_dependency_abc123
import unittest

class TestSimple(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(True)

if __name__ == '__main__':
    unittest.main()
''')

def cleanup_environment(workspace: str):
    print(f"\n[Demo Cleanup] Removing sandbox workspace: {workspace}")
    import shutil
    if os.path.exists(workspace):
        shutil.rmtree(workspace)


def main():
    workspace = os.path.abspath("temp_planning")
    setup_environment(workspace)
    
    task = "Run the tests in the workspace and verify all pass."
    
    try:
        # Initialize Runner locked to the sandboxed workspace
        model = PlanningMockModel()
        runner = AgentRunner(
            model=model, 
            workspace_dir=workspace, 
            test_command="python -m unittest test_math.py"
        )
        
        # Run agent loop
        trace = runner.run(task, max_iterations=6, checkpoint_path="plan_checkpoint.json")
        
        # Print summary of the final trace
        trace.print_summary()
        
    finally:
        cleanup_environment(workspace)

if __name__ == "__main__":
    main()
