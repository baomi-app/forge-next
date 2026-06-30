import os
import sys
import json
from typing import List, Dict, Any, Tuple, Optional

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner

class SubagentsMockModel(BaseModel):
    """A single simulated model that dynamically branches its response logic 
    depending on the System Prompt (Orchestrator, SecurityExpert, LinterExpert, or QATester).
    """
    
    def __init__(self):
        self.orchestrator_step = 0
        self.security_step = 0
        self.linter_step = 0
        self.qa_step = 0

    def generate(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        
        sys_msg = messages[0]["content"] if messages else ""
        
        # ─── ROUTE 1: SECURITY EXPERT SUBAGENT ───
        if "SecurityExpert" in sys_msg:
            self.security_step += 1
            if self.security_step == 1:
                print("[SecurityExpert] Thinking: Let's read main.py to identify overflow vulnerabilities.")
                return (
                    "I will read main.py to inspect input configurations.",
                    [{"id": "sec_call_1", "type": "function", "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"filepath": "main.py"})
                    }}]
                )
            else:
                print("[SecurityExpert] Thinking: Found un-bounded raw input. Reporting.")
                return (
                    "Vulnerability Report: Line 3 uses raw 'input()' without length limit. "
                    "Recommend capping input using slice boundary, i.e., 'input().strip()[:256]'.",
                    None
                )
                
        # ─── ROUTE 2: LINTER EXPERT SUBAGENT ───
        elif "LinterExpert" in sys_msg:
            self.linter_step += 1
            if self.linter_step == 1:
                print("[LinterExpert] Thinking: Let's read main.py to analyze PEP8 and string strip format.")
                return (
                    "I will inspect main.py code style layout.",
                    [{"id": "lint_call_1", "type": "function", "function": {
                        "name": "read_file",
                        "arguments": json.dumps({"filepath": "main.py"})
                    }}]
                )
            else:
                print("[LinterExpert] Thinking: Code format check complete. Reporting styling issues.")
                return (
                    "Linter Report: Code layout has minor format issues. Ensure input reading strips trailing whitespace.",
                    None
                )
                
        # ─── ROUTE 3: QA TESTER SUBAGENT ───
        elif "QATester" in sys_msg:
            self.qa_step += 1
            if self.qa_step == 1:
                print("[QATester] Thinking: Running test suite to confirm bounds security.")
                return (
                    "I will run test_main.py to verify bounds enforcement.",
                    [{"id": "qa_call_1", "type": "function", "function": {
                        "name": "run_command",
                        "arguments": json.dumps({"command": "python test_main.py"})
                    }}]
                )
            else:
                print("[QATester] Thinking: Test passed. Reporting verification status.")
                return (
                    "QA Report: Bounds verification checks successfully executed. "
                    "Fuzz testing confirms input slice bounds guard against overflow.",
                    None
                )
                
        # ─── ROUTE 4: ORCHESTRATOR / PARENT AGENT ───
        else:
            self.orchestrator_step += 1
            
            # Step 1: Concurrently spawn SecurityExpert and LinterExpert
            if self.orchestrator_step == 1:
                print("[Orchestrator] Thinking: Let's spawn SecurityExpert and LinterExpert concurrently to audit main.py.")
                return (
                    "I will concurrently spawn two subagents (SecurityExpert and LinterExpert) to analyze main.py.",
                    [
                        {"id": "orch_call_1", "type": "function", "function": {
                            "name": "invoke_subagent",
                            "arguments": json.dumps({
                                "role": "SecurityExpert",
                                "task": "Audit main.py buffer safety."
                            })
                        }},
                        {"id": "orch_call_2", "type": "function", "function": {
                            "name": "invoke_subagent",
                            "arguments": json.dumps({
                                "role": "LinterExpert",
                                "task": "Audit main.py code formatting."
                            })
                        }}
                    ]
                )
                
            # Step 2: Apply patch based on both SecurityExpert and LinterExpert reports
            elif self.orchestrator_step == 2:
                print("[Orchestrator] Thinking: Security Expert and Linter reports received. Fixing main.py.")
                return (
                    "Applying combined boundary and styling patch to main.py input reading.",
                    [{"id": "orch_call_3", "type": "function", "function": {
                        "name": "edit_file_block",
                        "arguments": json.dumps({
                            "filepath": "main.py",
                            "start_line": 3,
                            "end_line": 3,
                            "replacement": "    data = input().strip()[:256]"
                        })
                    }}]
                )
                
            # Step 3: Dispatch QA Tester Subagent
            elif self.orchestrator_step == 3:
                print("[Orchestrator] Thinking: Patch applied. Dispatching QATester subagent to verify.")
                return (
                    "I will dispatch a QATester subagent to verify bounds safety.",
                    [{"id": "orch_call_4", "type": "function", "function": {
                        "name": "invoke_subagent",
                        "arguments": json.dumps({
                            "role": "QATester",
                            "task": "Run tests on main.py to verify bounds."
                        })
                    }}]
                )
                
            # Step 4: Done
            else:
                print("[Orchestrator] Thinking: Security audit and QA verification passed. Ending task.")
                return ("Vulnerability secured and confirmed passing QA tests.", None)


def main():
    workspace = os.path.abspath("temp_subagents")
    if not os.path.exists(workspace):
        os.makedirs(workspace)
        
    # 1. Create buggy main.py in workspace
    buggy_code = (
        "def process_input():\n"
        "    # Misconfigured buffer overflow vulnerability\n"
        "    data = input().strip()\n"
        "    return f'Processed: {data}'\n"
    )
    with open(os.path.join(workspace, "main.py"), "w", encoding="utf-8") as f:
        f.write(buggy_code)
        
    # 2. Create test_main.py in workspace
    test_code = (
        "import unittest\n"
        "import sys\n"
        "# Globally mock stdin to avoid hangs under unittest runners\n"
        "sys.stdin = sys.io = type('MockStdin', (), {'readline': lambda s: 'test_data\\n'})()\n"
        "\n"
        "from main import process_input\n"
        "\n"
        "class TestMain(unittest.TestCase):\n"
        "    def test_bounds(self):\n"
        "        # Simple bounds execution test\n"
        "        res = process_input()\n"
        "        self.assertTrue(res.startswith('Processed:'))\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n"
    )
    with open(os.path.join(workspace, "test_main.py"), "w", encoding="utf-8") as f:
        f.write(test_code)
        
    try:
        model = SubagentsMockModel()
        
        # Test command run by Verifier on completion
        test_command = "python -m unittest test_main.py"
        
        runner = AgentRunner(
            model=model,
            workspace_dir=workspace,
            test_command=test_command
        )
        
        # Spawn Orchestrator Agent
        task = "Analyze security in main.py, fix vulnerabilities, and run verification tests."
        print("[Demo Setup] Starting Orchestrator Agent Loop...")
        trace = runner.run(task, max_iterations=5, checkpoint_path="orchestrator_checkpoint.json")
        trace.print_summary()
        
    finally:
        # Clean up temporary test files
        if os.path.exists(workspace):
            import shutil
            shutil.rmtree(workspace)
            print("[Demo Cleanup] Removed temp_subagents workspace.")

if __name__ == "__main__":
    main()
