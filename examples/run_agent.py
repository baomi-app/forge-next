import os
import sys
import argparse

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import OpenAIModel
from forge.runner import AgentRunner

def main():
    parser = argparse.ArgumentParser(description="Forge: Run a real LLM Coding Agent CLI.")
    parser.add_argument("task", type=str, nargs="?", default="", help="The task for the Coding Agent to execute (optional if resuming).")
    parser.add_argument("--model", type=str, default="gpt-4o", help="Model name to use (default: gpt-4o).")
    parser.add_argument("--max-iterations", type=int, default=10, help="Max loops (default: 10).")
    parser.add_argument("--trace-file", type=str, default="trace.json", help="Path to save the execution trace JSON (default: trace.json).")
    parser.add_argument("--test-command", type=str, default=None, help="Command to run the project's test suite for verification.")
    parser.add_argument("--resume", type=str, default=None, help="Path to checkpoint.json to resume from.")
    args = parser.parse_args()

    # If not resuming, task is required
    if not args.resume and not args.task:
        parser.error("the following arguments are required: task (unless --resume is specified)")

    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")
    
    if not api_key:
        print("\n[Error] OPENAI_API_KEY environment variable is not set!")
        print("Please set it before running, or use a custom proxy base url if needed:")
        print("  export OPENAI_API_KEY=\"your-key\"")
        print("  export OPENAI_BASE_URL=\"https://api.openai.com/v1\"  # Optional")
        print("\nAlternatively, you can run the zero-dependency mock demonstration:")
        print("  python examples/demo_mock.py")
        sys.exit(1)

    print(f"Initializing Real Agent with model: {args.model}")
    if base_url:
        print(f"Using Custom API Endpoint: {base_url}")
        
    model = OpenAIModel(model_name=args.model, api_key=api_key, base_url=base_url)
    runner = AgentRunner(model=model, test_command=args.test_command)

    try:
        trace = runner.run(
            args.task, 
            max_iterations=args.max_iterations, 
            resume_from=args.resume
        )
        trace.save_to_file(args.trace_file)
        trace.print_summary()
    except KeyboardInterrupt:
        print("\n[Runner] Interrupted by user. Exiting.")
    except Exception as e:
        print(f"\n[Error] Execution failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
