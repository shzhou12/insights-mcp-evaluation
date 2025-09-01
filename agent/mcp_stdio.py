"""MCP stdio client for connecting to MCP servers via stdin/stdout."""

import json
import shlex
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple


class MCPStdioClient:
    """Minimal MCP client that connects to servers via stdio using JSON-RPC."""

    def __init__(self, command: List[str], timeout: float = 30.0):
        """Initialize MCP client with server command.

        Args:
            command: Command and arguments to start the MCP server
            timeout: Timeout for operations in seconds
        """
        self.command = command
        self.timeout = timeout
        self.process: Optional[subprocess.Popen] = None
        self.request_id = 0
        self.initialized = False

    def start(self) -> bool:
        """Start the MCP server process.

        Returns:
            True if started successfully, False otherwise
        """
        try:
            # Handle case where command is a single string with spaces (e.g., from quoted arguments)
            command = self.command
            if len(command) == 1 and " " in command[0]:
                # Split the single string into proper command arguments
                command = shlex.split(command[0])

            self.process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=0
            )
            return True
        except Exception as e:
            print(f"Failed to start MCP server: {e}")
            return False

    def stop(self):
        """Stop the MCP server process."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def _send_request(self, method: str, params: Optional[Dict] = None) -> Tuple[bool, Dict]:
        """Send a JSON-RPC request to the server.

        Args:
            method: JSON-RPC method name
            params: Parameters for the method

        Returns:
            Tuple of (success, response_data)
        """
        if not self.process or not self.process.stdin:
            return False, {"error": "Server not started"}

        self.request_id += 1
        request = {"jsonrpc": "2.0", "id": self.request_id, "method": method}

        if params:
            request["params"] = params

        try:
            # Send request
            request_json = json.dumps(request) + "\n"
            self.process.stdin.write(request_json)
            self.process.stdin.flush()

            # Read response with timeout
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                if self.process.stdout and self.process.stdout.readable():
                    line = self.process.stdout.readline()
                    if line.strip():
                        try:
                            response = json.loads(line.strip())
                            if response.get("id") == self.request_id:
                                if "error" in response:
                                    return False, response["error"]
                                return True, response.get("result", {})
                        except json.JSONDecodeError:
                            continue
                time.sleep(0.01)

            return False, {"error": "Timeout waiting for response"}

        except Exception as e:
            return False, {"error": f"Request failed: {str(e)}"}

    def initialize(self) -> bool:
        """Initialize the MCP connection.

        Returns:
            True if initialization successful
        """
        if not self.process:
            if not self.start():
                return False

        # Send initialize request
        params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "insights-mcp-evaluation", "version": "1.0.0"},
        }

        success, response = self._send_request("initialize", params)
        if not success:
            print(f"Initialize failed: {response}")
            return False

        # Send initialized notification
        initialized_request = {"jsonrpc": "2.0", "method": "notifications/initialized"}

        try:
            if self.process and self.process.stdin:
                initialized_json = json.dumps(initialized_request) + "\n"
                self.process.stdin.write(initialized_json)
                self.process.stdin.flush()
        except Exception as e:
            print(f"Failed to send initialized notification: {e}")
            return False

        self.initialized = True
        return True

    def list_tools(self) -> Tuple[bool, List[Dict[str, Any]]]:
        """List available tools from the MCP server.

        Returns:
            Tuple of (success, tools_list)
        """
        if not self.initialized:
            if not self.initialize():
                return False, []

        success, response = self._send_request("tools/list")
        if not success:
            return False, []

        tools = response.get("tools", [])
        return True, tools

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Call a tool on the MCP server.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tuple of (success, result_data)
        """
        if not self.initialized:
            if not self.initialize():
                return False, {"error": "Not initialized"}

        params = {"name": name, "arguments": arguments}

        success, response = self._send_request("tools/call", params)
        return success, response

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


def test_connection(command: List[str]) -> bool:
    """Test if we can connect to an MCP server.

    Args:
        command: Command to start the MCP server

    Returns:
        True if connection successful
    """
    try:
        with MCPStdioClient(command) as client:
            if client.initialize():
                success, tools = client.list_tools()
                if success:
                    print(f"Successfully connected. Found {len(tools)} tools.")
                    for tool in tools:
                        print(f"  - {tool.get('name', 'unknown')}: {tool.get('description', 'no description')}")
                    return True
        return False
    except Exception as e:
        print(f"Connection test failed: {e}")
        return False
