import sys
import json
import threading
import subprocess
from typing import List, Dict, Any, Optional

class MCPClient:
    """A lightweight Model Context Protocol (MCP) Client implementing JSON-RPC 2.0 
    over subprocess stdio transport.
    """
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.request_counter = 0
        self.pending_responses: Dict[int, Dict[str, Any]] = {}
        self.listener_thread: Optional[threading.Thread] = None
        self.stderr_thread: Optional[threading.Thread] = None
        self._request_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self.is_running = False

    def connect(self, command: List[str]):
        """Launches the MCP server subprocess and starts the background stdio listener."""
        print(f"[MCP Client] Connecting to server via command: {' '.join(command)}")
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line buffered
        )
        self.is_running = True
        
        # Start background daemon thread to read responses from stdout
        self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listener_thread.start()
        self.stderr_thread = threading.Thread(target=self._drain_stderr_loop, daemon=True)
        self.stderr_thread.start()

    def _listen_loop(self):
        """Continuously reads JSON-RPC messages from stdout line-by-line."""
        try:
            while self.is_running and self.process and self.process.stdout:
                line = self.process.stdout.readline()
                if not line:
                    break  # Pipe closed
                
                line = line.strip()
                if not line:
                    continue
                
                try:
                    message = json.loads(line)
                    self._handle_incoming_message(message)
                except json.JSONDecodeError:
                    print(f"[MCP Client Warning] Failed to parse JSON from server: {line}")
        except Exception as e:
            if self.is_running:
                print(f"[MCP Client Error] Exception in listen thread: {str(e)}")

    def _drain_stderr_loop(self):
        """Continuously drains stderr so verbose MCP servers cannot block on a full pipe."""
        try:
            while self.is_running and self.process and self.process.stderr:
                line = self.process.stderr.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    print(f"[MCP Server stderr] {line}", file=sys.stderr)
        except Exception as e:
            if self.is_running:
                print(f"[MCP Client Error] Exception in stderr thread: {str(e)}")

    def _handle_incoming_message(self, message: Dict[str, Any]):
        """Resolves correlation IDs for pending requests."""
        # We only care about responses (which contain an 'id' matches our request list)
        req_id = message.get("id")
        with self._pending_lock:
            record = self.pending_responses.get(req_id) if req_id is not None else None
        if record:
            record["response"] = message
            record["event"].set()  # Wake up caller thread

    def _send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 5.0) -> Dict[str, Any]:
        """Dispatches a synchronous JSON-RPC request and blocks until a response is received."""
        if not self.process or not self.process.stdin:
            raise RuntimeError("MCP Client is not connected to any server.")
            
        with self._request_lock:
            self.request_counter += 1
            req_id = self.request_counter
        
        req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {}
        }
        
        event = threading.Event()
        with self._pending_lock:
            self.pending_responses[req_id] = {"event": event, "response": None}
        
        # Write JSON line to subprocess stdin
        try:
            with self._write_lock:
                self.process.stdin.write(json.dumps(req) + "\n")
                self.process.stdin.flush()
        except IOError as e:
            with self._pending_lock:
                self.pending_responses.pop(req_id, None)
            raise RuntimeError(f"Failed to write to MCP Server pipe: {str(e)}")
            
        # Wait for matching response in listen thread
        success = event.wait(timeout=timeout)
        if not success:
            with self._pending_lock:
                self.pending_responses.pop(req_id, None)
            raise TimeoutError(f"MCP Request {req_id} ({method}) timed out after {timeout} seconds.")
            
        with self._pending_lock:
            res = self.pending_responses.pop(req_id)["response"]
        if "error" in res:
            raise RuntimeError(f"MCP Server error: {res['error']}")
            
        return res.get("result", {})

    def _send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        """Sends a JSON-RPC notification (no 'id' expected, fire-and-forget)."""
        if not self.process or not self.process.stdin:
            return
        req = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        try:
            with self._write_lock:
                self.process.stdin.write(json.dumps(req) + "\n")
                self.process.stdin.flush()
        except IOError:
            pass

    def initialize(self) -> Dict[str, Any]:
        """Perform the protocol handshake."""
        params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "forge-mcp-client", "version": "0.1.0"}
        }
        result = self._send_request("initialize", params)
        # Send initialized confirmation notification
        self._send_notification("notifications/initialized")
        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        """Query the list of tools exported by the server."""
        result = self._send_request("tools/list")
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Call a remote tool and extract its plain text response."""
        params = {
            "name": name,
            "arguments": arguments
        }
        result = self._send_request("tools/call", params, timeout=10.0)
        # Typically returns content list: [{'type': 'text', 'text': '...'}]
        contents = result.get("content", [])
        text_outputs = []
        for c in contents:
            if c.get("type") == "text":
                text_outputs.append(c.get("text", ""))
        return "\n".join(text_outputs)

    def close(self):
        """Shutdown the listener thread and cleanly terminate the server subprocess."""
        self.is_running = False
        if self.process:
            print("[MCP Client] Shutting down subprocess...")
            try:
                self.process.stdin.close()
            except Exception:
                pass
            try:
                self.process.stdout.close()
            except Exception:
                pass
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
            self.process = None
