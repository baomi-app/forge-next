import os
import sys
import json
from typing import List, Dict, Any, Tuple, Optional

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner

class VerifierMockModel(BaseModel):
    """A simulated model that specifically demonstrates the 'Self-Correction' 
    loop triggered by Verifier feedback.
    """
    def __init__(self):
        self.step_idx = 0

    def generate(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        self.step_idx += 1
        
        # Step 1: List files to find code
        if self.step_idx == 1:
            print("[MockModel] Thinking: First step, let me check the codebase.")
            return (
                "I will list the files in the workspace.",
                [{
                    "id": "v_call_1",
                    "type": "function",
                    "function": {"name": "list_files", "arguments": json.dumps({"directory": "."})}
                }]
            )
            
        # Step 2: Read main.py
        elif self.step_idx == 2:
            print("[MockModel] Thinking: Let's read main.py.")
            return (
                "I see main.py. Let me read it to check for issues.",
                [{
                    "id": "v_call_2",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": json.dumps({"filepath": "main.py"})}
                }]
            )
            
        # Step 3: Attempt to write a patch, but deliberately make a SYNTAX ERROR (missing colon)
        # AND attempt to finish the task immediately.
        elif self.step_idx == 3:
            print("[MockModel] Thinking: Let me modify main.py but make a mistake (missing ':') and try to finish.")
            target = "def add(a, b):\n    return a + b"
            # Buggy replacement missing the colon ':'
            buggy_replacement = "def add(a, b)\n    return a + b"
            return (
                "I will update add() function.",
                [{
                    "id": "v_call_3",
                    "type": "function",
                    "function": {
                        "name": "apply_patch",
                        "arguments": json.dumps({
                            "filepath": "main.py",
                            "target": target,
                            "replacement": buggy_replacement
                        })
                    }
                }]
            )
            
        # Step 4: Model attempts to STOP. It thinks it is done.
        elif self.step_idx == 4:
            print("[MockModel] Thinking: I applied the patch. I will declare I am done now!")
            return (
                "I have updated main.py. I am finished with the task!",
                None
            )
            
        # Step 5: Model receives the Verifier's compile block error (missing colon).
        # It realizes it made a mistake, applies a correct patch, and attempts to run tests.
        elif self.step_idx == 5:
            print("[MockModel] Thinking: Oh! The system blocked me. I see a syntax error: missing colon. Let me correct it.")
            target = "def add(a, b)\n    return a + b"
            correct_replacement = "def add(a, b):\n    return a + b"
            return (
                "Oops, I introduced a syntax error (missing colon). Let me patch that right away.",
                [{
                    "id": "v_call_5",
                    "type": "function",
                    "function": {
                        "name": "apply_patch",
                        "arguments": json.dumps({
                            "filepath": "main.py",
                            "target": target,
                            "replacement": correct_replacement
                        })
                    }
                }]
            )
            
        # Step 6: Model attempts to stop again after fixing the syntax.
        else:
            print("[MockModel] Thinking: Syntax is fixed. Let me try to finish now.")
            return (
                "I have fixed the syntax error and tested my changes. The task is fully complete now!",
                None
            )


# Setup / cleanup logic for the demo environment
def setup_environment():
    print("[Demo Setup] Creating main.py...")
    with open("main.py", "w", encoding="utf-8") as f:
        f.write('''def add(a, b):
    return a + b
''')

    print("[Demo Setup] Creating test_main.py...")
    with open("test_main.py", "w", encoding="utf-8") as f:
        f.write('''import unittest
from main import add

class TestMath(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

if __name__ == '__main__':
    unittest.main()
''')

def cleanup_environment():
    print("\n[Demo Cleanup] Cleaning up generated environment files...")
    for file in ["main.py", "test_main.py", "verifier_trace.json"]:
        if os.path.exists(file):
            os.remove(file)
            print(f"Removed temporary file: {file}")

def main():
    setup_environment()
    
    mock_model = VerifierMockModel()
    
    # We configure the AgentRunner with our automated verification command
    runner = AgentRunner(
        model=mock_model,
        test_command="python -m unittest test_main.py"
    )
    
    task = "Inspect the codebase, ensure main.py compiles and passes tests."
    
    try:
        # Run agent loop
        trace = runner.run(task, max_iterations=8)
        
        # Save trace
        trace.save_to_file("verifier_trace.json")
        trace.print_summary()
        
    finally:
        cleanup_environment()

if __name__ == "__main__":
    main()
