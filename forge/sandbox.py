import os
import re
import shlex
import subprocess

class SecurityViolationError(PermissionError):
    """Raised when an agent attempts a forbidden operation within the sandbox."""
    pass

class BaseSandbox:
    """Abstract interface defining the execution boundary for the Coding Agent."""
    
    def execute_command(self, command: str, timeout_seconds: int = 10) -> str:
        raise NotImplementedError

    def read_file(self, filepath: str) -> str:
        raise NotImplementedError

    def write_file(self, filepath: str, content: str) -> None:
        raise NotImplementedError


class LocalRestrictedSandbox(BaseSandbox):
    """A local execution boundary for path checks, timeouts, and shell-free commands.

    This is not an OS security sandbox. Commands still run as the current user,
    so untrusted code requires a real container or process isolation layer.
    """
    
    def __init__(self, workspace_dir: str):
        self.workspace_dir = os.path.abspath(workspace_dir)
        # Blocklist for high-risk system commands
        self.blocked_patterns = [
            r"\brm\s+-[rf]+\b",    # rm -rf, rm -r, rm -f
            r"\bsudo\b",            # sudo privilege escalation
            r"\bchown\b",           # file owner manipulation
            r"\bchmod\b",           # permissions change
            r"\bcurl\b",            # curl web requests
            r"\bwget\b",            # wget web downloads
            r"\bsh\b",              # raw shell executions (prevent piping)
            r"/etc/passwd",         # reading system user files
        ]

    def _validate_path(self, filepath: str) -> str:
        """Helper to guarantee files remain strictly inside the sandbox directory."""
        target_path = os.path.abspath(os.path.join(self.workspace_dir, filepath))
        if os.path.commonpath([self.workspace_dir, target_path]) != self.workspace_dir:
            raise SecurityViolationError(
                f"Directory Traversal Denied: Path '{filepath}' is outside sandbox workspace '{self.workspace_dir}'"
            )
        return target_path

    def execute_command(self, command: str, timeout_seconds: int = 10) -> str:
        """Executes a CLI command without invoking a shell, under keyword and time limits."""
        # 1. Security Check: Search command string for blocked patterns
        for pattern in self.blocked_patterns:
            if re.search(pattern, command):
                return f"[Security Error] Execution Blocked: Command contains dangerous pattern '{pattern}'."

        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return f"[Security Error] Failed to parse command safely: {str(exc)}"

        if not argv:
            return "[Security Error] Empty command is not allowed."

        # 2. Execution under Sandbox boundary
        try:
            res = subprocess.run(
                argv,
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds
            )
            # Combine stdout and stderr
            output = ""
            if res.stdout:
                output += "[Stdout]\n" + res.stdout
            if res.stderr:
                output += "[Stderr]\n" + res.stderr
                
            # If both are empty
            if not output:
                output = f"Command exited with status code {res.returncode} (No output)."
            else:
                output += f"\nCommand exited with status code {res.returncode}."
                
            return output
            
        except subprocess.TimeoutExpired:
            return f"[Timeout Error] Command exceeded execution limit of {timeout_seconds} seconds and was forcefully terminated."

    def read_file(self, filepath: str) -> str:
        """Reads content after validating boundary."""
        target_path = self._validate_path(filepath)
        if not os.path.exists(target_path):
            raise FileNotFoundError(f"File not found: {filepath}")
        with open(target_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, filepath: str, content: str) -> None:
        """Writes content after validating boundary."""
        target_path = self._validate_path(filepath)
        # Ensure parent directories exist
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)


class DockerSandbox(BaseSandbox):
    """Stub class representing a Docker containerized sandbox.
    In production, this class would dispatch command executions and files 
    inside a running Docker container via docker-py.
    """
    
    def __init__(self, container_image: str = "python:3.10-slim"):
        self.container_image = container_image
        print(f"[DockerSandbox] Initialized container stub image: {self.container_image}")

    def execute_command(self, command: str, timeout_seconds: int = 10) -> str:
        return f"[DockerSandbox Mock] Running command in image {self.container_image}: {command}"

    def read_file(self, filepath: str) -> str:
        return f"[DockerSandbox Mock] Read file from container: {filepath}"

    def write_file(self, filepath: str, content: str) -> None:
        print(f"[DockerSandbox Mock] Wrote {len(content)} chars inside container file: {filepath}")
