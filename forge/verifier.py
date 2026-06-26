import os
import subprocess
from typing import Tuple, List, Optional

class Verifier:
    """Automated code gatekeeper for checking syntax, running tests, and validating changes."""
    
    def __init__(self, workspace_dir: str = ".", test_command: Optional[str] = None):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.test_command = test_command
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

    def run_tests(self) -> Tuple[bool, str]:
        """Runs the registered test suite command.
        
        Returns:
            Tuple (is_passed, test_output)
        """
        if not self.test_command:
            return True, "No test command specified. Skipping test suite verification."
            
        try:
            # Run test with 30s timeout
            result = subprocess.run(
                self.test_command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.workspace_dir,
                timeout=30
            )
            is_passed = result.returncode == 0
            
            output = []
            if result.stdout:
                output.append(result.stdout)
            if result.stderr:
                output.append(result.stderr)
                
            test_output = "\n".join(output)
            return is_passed, test_output
        except subprocess.TimeoutExpired:
            return False, "Error: Verification test suite timed out after 30 seconds."
        except Exception as e:
            return False, f"Error launching verification test suite: {str(e)}"

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
            
        # 2. Test Suite Check (Functional logic errors)
        if self.test_command:
            tests_passed, test_output = self.run_tests()
            if not tests_passed:
                # Truncate test output if it's exceptionally long
                if len(test_output) > 1500:
                    test_output = test_output[:1500] + "\n... [TRUNCATED TEST OUTPUT] ..."
                report = (
                    "[VERIFIER FAILED] Unit tests failed! "
                    "Your changes broke the test suite. Details below:\n\n"
                    f"{test_output}\n"
                    "Please analyze the failure and correct the code."
                )
                print("[Verifier] Status: FAILED (Test Suite Failure)")
                return False, report
                
        print("[Verifier] Status: PASSED")
        return True, "[VERIFIER PASSED] All compilation and test checks passed successfully."
