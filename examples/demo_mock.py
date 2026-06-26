import os
import sys

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import MockModel
from forge.runner import AgentRunner

# 1. Setup mock environment files
def setup_environment():
    print("[Demo Setup] Creating buggy main.py...")
    with open("main.py", "w", encoding="utf-8") as f:
        f.write('''def add(a, b):
    return a + b

def divide(a, b):
    return a / b
''')

    print("[Demo Setup] Creating test_main.py...")
    with open("test_main.py", "w", encoding="utf-8") as f:
        f.write('''import unittest
from main import divide

class TestMath(unittest.TestCase):
    def test_divide(self):
        # We expect a ValueError when dividing by zero
        with self.assertRaises(ValueError):
            divide(5, 0)

if __name__ == '__main__':
    unittest.main()
''')

def cleanup_environment():
    print("\n[Demo Cleanup] Cleaning up generated environment files...")
    for file in ["main.py", "test_main.py", "mock_trace.json"]:
        if os.path.exists(file):
            os.remove(file)
            print(f"Removed temporary file: {file}")

def main():
    # 1. Prepare environment
    setup_environment()
    
    # 2. Initialize Runner with the simulator MockModel
    mock_model = MockModel()
    runner = AgentRunner(model=mock_model)
    
    task = "Fix the division by zero bug in main.py so that it raises ValueError, verify with test_main.py, and inspect git diff."
    
    try:
        # 3. Execute the runner loop
        trace = runner.run(task, max_iterations=6)
        
        # 4. Save trace to file & print summary
        trace.save_to_file("mock_trace.json")
        trace.print_summary()
        
    finally:
        # 5. Cleanup
        # Give the user a moment or print instructions before cleanup.
        # We cleanup automatically to keep the workspace clean.
        cleanup_environment()

if __name__ == "__main__":
    main()
