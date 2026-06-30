import sys
import json

def fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    if n == 1:
        return 1
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

def write_response(response: dict):
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()

def main():
    # Loop indefinitely reading JSON-RPC requests from standard input
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break # stdin closed, shut down server
            
            line = line.strip()
            if not line:
                continue
                
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})
            
            # If it is a notification (no 'id' provided), we ignore it or handle silently
            if req_id is None:
                continue
                
            # 1. Handle Handshake Initialize
            if method == "initialize":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "fibonacci-mcp-server",
                            "version": "1.0.0"
                        }
                    }
                }
                write_response(res)
                
            # 2. Handle Tools Discovery List
            elif method == "tools/list":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "calculate_fibonacci",
                                "description": "Computes the N-th Fibonacci number. Excellent for calculating mathematical sequences.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "n": {
                                            "type": "integer",
                                            "description": "The sequence index to calculate (0-indexed)."
                                        }
                                    },
                                    "required": ["n"]
                                }
                            }
                        ]
                    }
                }
                write_response(res)
                
            # 3. Handle Tools Remote Execution Call
            elif method == "tools/call":
                tool_name = params.get("name")
                args = params.get("arguments", {})
                
                if tool_name == "calculate_fibonacci":
                    n_val = int(args.get("n", 0))
                    val = fibonacci(n_val)
                    
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"The {n_val}-th Fibonacci number is {val}."
                                }
                            ]
                        }
                    }
                    write_response(res)
                else:
                    # Unknown tool error
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32601,
                            "message": f"Tool '{tool_name}' not found."
                        }
                    }
                    write_response(res)
            else:
                # Unsupported method error
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method '{method}' not found."
                    }
                }
                write_response(res)
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            # Send general JSON-RPC internal error
            try:
                res = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": f"Internal server error: {str(e)}"
                    }
                }
                write_response(res)
            except Exception:
                pass

if __name__ == "__main__":
    main()
