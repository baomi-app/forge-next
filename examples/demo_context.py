import os
import sys
import json
from typing import List, Dict, Any, Tuple, Optional

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner

class ContextMockModel(BaseModel):
    """A simulated model that relies on truncated test outputs containing 
    AttributeError traceback.
    """
    
    def __init__(self):
        self.step_idx = 0

    def generate(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        self.step_idx += 1
        
        # Iteration 1: List files
        if self.step_idx == 1:
            print("[MockModel] Thinking: Let's list files to find main.py.")
            return (
                "I will list workspace files to locate the configuration script.",
                [{"id": "ct_call_1", "type": "function", "function": {"name": "list_files", "arguments": "{}"}}]
            )
            
        # Iteration 2: Read main.py
        elif self.step_idx == 2:
            print("[MockModel] Thinking: Reading main.py.")
            return (
                "I see main.py. Let me read its contents.",
                [{"id": "ct_call_2", "type": "function", "function": {"name": "read_file", "arguments": json.dumps({"filepath": "main.py"})}}]
            )
            
        # Iteration 3: Run the test suite (generates huge junk logs + AttributeError)
        elif self.step_idx == 3:
            print("[MockModel] Thinking: Let's run tests to verify logic.")
            return (
                "I will run the tests to check for configuration attributes.",
                [{"id": "ct_call_3", "type": "function", "function": {
                    "name": "run_command",
                    "arguments": json.dumps({"command": "python -m unittest test_main.py"})
                }}]
            )
            
        # Iteration 4: Fix the AttributeError
        # Model receives truncated logs but successfully locates the AttributeError trace at the end.
        elif self.step_idx == 4:
            print("[MockModel] Thinking: AttributeError located in traceback. Applying patch to fix it.")
            target = "def __init__(self):\n        # Bug: Missing self.database_url attribute\n        pass"
            replacement = "def __init__(self):\n        self.database_url = \"sqlite:///test.db\""
            return (
                "I see an AttributeError: 'Config' object has no attribute 'database_url' in the traceback error logs. I will patch main.py to define this attribute.",
                [{"id": "ct_call_4", "type": "function", "function": {
                    "name": "apply_patch",
                    "arguments": json.dumps({
                        "filepath": "main.py",
                        "target": target,
                        "replacement": replacement
                    })
                }}]
            )
            
        # Iteration 5: Done!
        else:
            print("[MockModel] Thinking: All green. Ending task.")
            return ("The database url attribute bug has been successfully resolved and tested.", None)


def setup_environment(workspace: str):
    if not os.path.exists(workspace):
        os.makedirs(workspace)
        
    print("[Demo Setup] Creating buggy main.py...")
    with open(os.path.join(workspace, "main.py"), "w", encoding="utf-8") as f:
        f.write('''class Config:
    def __init__(self):
        # Bug: Missing self.database_url attribute
        pass
''')

    print("[Demo Setup] Creating test_main.py (generating 100+ lines of connection logs)...")
    with open(os.path.join(workspace, "test_main.py"), "w", encoding="utf-8") as f:
        f.write('''import unittest
from main import Config

class TestConfig(unittest.TestCase):
    def test_database(self):
        config = Config()
        
        # Simulate 120 lines of database connection printouts
        for i in range(120):
            print(f"[Log] Database host 192.168.1.{i} connection: PENDING... RETRYING...")
            
        # Critical error at the very end
        print(config.database_url)

if __name__ == '__main__':
    unittest.main()
''')

def cleanup_environment(workspace: str):
    print(f"\n[Demo Cleanup] Removing sandbox workspace: {workspace}")
    import shutil
    if os.path.exists(workspace):
        shutil.rmtree(workspace)


def main():
    workspace = os.path.abspath("temp_context")
    setup_environment(workspace)
    
    task = "Run tests, find why Config fails, and patch it."
    
    try:
        model = ContextMockModel()
        runner = AgentRunner(
            model=model, 
            workspace_dir=workspace, 
            test_command="python -m unittest test_main.py"
        )
        
        # Run agent loop (will automatically trigger context truncation on step 3)
        trace = runner.run(task, max_iterations=6, checkpoint_path="context_checkpoint.json")
        
        trace.print_summary()
        
    finally:
        cleanup_environment(workspace)

if __name__ == "__main__":
    main()
