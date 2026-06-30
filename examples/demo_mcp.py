import os
import sys
import json
from typing import List, Dict, Any, Tuple, Optional

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from forge.model import BaseModel
from forge.runner import AgentRunner
from forge.tools import registry
from forge.mcp import MCPClient

class MCPMockModel(BaseModel):
    """A simulated model that detects and utilizes dynamically registered 
    external MCP tools to perform sequencing operations.
    """
    
    def __init__(self):
        self.step_idx = 0

    def generate(
        self, 
        messages: List[Dict[str, Any]], 
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]]]:
        self.step_idx += 1
        
        # Iteration 1: The model detects 'calculate_fibonacci' in its tool list and calls it
        if self.step_idx == 1:
            print("[MockModel] Thinking: Let's calculate the 10-th Fibonacci number using MCP tools.")
            return (
                "I will query the external Fibonacci MCP tool to compute the 10-th sequence index.",
                [{"id": "mcp_call_1", "type": "function", "function": {
                    "name": "calculate_fibonacci",
                    "arguments": json.dumps({"n": 10})
                }}]
            )
            
        # Iteration 2: Done
        else:
            print("[MockModel] Thinking: Got result from remote server. Ending task.")
            return ("The calculations have been completed successfully by the remote MCP server.", None)


def main():
    # Setup MCP Client and path to mock server
    client = MCPClient()
    server_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "mock_mcp_server.py"))
    
    # Connect client using Python interpreter to execute mock_mcp_server.py
    try:
        client.connect([sys.executable, server_script])
        
        print("[Demo Setup] Initiating MCP handshake...")
        init_res = client.initialize()
        print(f"[Demo Setup] Handshake successful! Server Info: {init_res.get('serverInfo', {})}")
        
        print("[Demo Setup] Discovering remote tools...")
        tools = client.list_tools()
        print(f"[Demo Setup] Remote tools exported: {[t['name'] for t in tools]}")
        
        # Register remote tools dynamically into the global Agent tool registry
        for t in tools:
            name = t["name"]
            desc = t["description"]
            schema = t["inputSchema"]
            
            # Use closure to bind tool name and client reference
            def create_callback(tool_name):
                return lambda **args: client.call_tool(tool_name, args)
                
            registry.register_mcp_tool(
                name=name,
                description=desc,
                input_schema=schema,
                execute_callback=create_callback(name)
            )
            
        task = "Use the remote calculate_fibonacci tool to compute the 10th fibonacci number."
        
        # Initialize runner. MCP tools require no physical workspace modifications, 
        # so we run it in a dummy sandbox folder
        workspace = os.path.abspath("temp_mcp")
        if not os.path.exists(workspace):
            os.makedirs(workspace)
            
        model = MCPMockModel()
        runner = AgentRunner(
            model=model, 
            workspace_dir=workspace,
            test_command="python -c \"pass\"" # Empty command since no tests are needed
        )
        
        trace = runner.run(task, max_iterations=3, checkpoint_path="mcp_checkpoint.json")
        trace.print_summary()
        
    finally:
        # Clean up sandbox folder
        if os.path.exists("temp_mcp"):
            import shutil
            shutil.rmtree("temp_mcp")
            print("[Demo Cleanup] Removed temp_mcp workspace.")
            
        # Guarantee subprocess termination to prevent orphan processes
        client.close()

if __name__ == "__main__":
    main()
