"""Tool registry for converting MCP tools to model-compatible schemas."""

from typing import Any, Dict, List, Tuple


class ToolRegistry:
    """Registry for managing MCP tools and converting them to model formats."""

    def __init__(self):
        """Initialize the tool registry."""
        self.tools: Dict[str, Dict[str, Any]] = {}

    def register_tools(self, mcp_tools: List[Dict[str, Any]]) -> None:
        """Register tools from MCP server response.

        Args:
            mcp_tools: List of tools from MCP tools/list response
        """
        for tool in mcp_tools:
            name = tool.get("name", "")
            if name:
                self.tools[name] = tool

    def get_tool_names(self) -> List[str]:
        """Get list of registered tool names.

        Returns:
            List of tool names
        """
        return list(self.tools.keys())

    def get_tool(self, name: str) -> Dict[str, Any]:
        """Get tool definition by name.

        Args:
            name: Tool name

        Returns:
            Tool definition or empty dict if not found
        """
        return self.tools.get(name, {})

    def to_openai_schema(self) -> List[Dict[str, Any]]:
        """Convert registered tools to OpenAI function calling schema.

        Returns:
            List of tools in OpenAI format
        """
        openai_tools = []

        for tool_name, tool_def in self.tools.items():
            # Convert MCP tool to OpenAI format
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_def.get("description", ""),
                    "parameters": self._convert_input_schema(tool_def.get("inputSchema", {})),
                },
            }
            openai_tools.append(openai_tool)

        return openai_tools

    def _convert_input_schema(self, input_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Convert MCP inputSchema to OpenAI parameters format.

        Args:
            input_schema: MCP tool input schema

        Returns:
            OpenAI-compatible parameters schema
        """
        # If the schema is already in the right format, return as-is
        if "type" in input_schema and input_schema.get("type") == "object":
            return input_schema

        # Handle case where inputSchema might be missing or malformed
        if not input_schema:
            return {"type": "object", "properties": {}, "required": []}

        # If it has properties but no type, assume it's an object
        if "properties" in input_schema:
            result = {
                "type": "object",
                "properties": input_schema["properties"],
                "required": input_schema.get("required", []),
            }
            return result

        # Default fallback
        return {"type": "object", "properties": {}, "required": []}

    def validate_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate a tool call against the registered schema.

        Args:
            tool_name: Name of the tool to call
            arguments: Arguments for the tool call

        Returns:
            Tuple of (is_valid, error_message)
        """
        if tool_name not in self.tools:
            return False, f"Tool '{tool_name}' not found in registry"

        tool_def = self.tools[tool_name]
        input_schema = tool_def.get("inputSchema", {})

        # Basic validation - check required fields
        required_fields = input_schema.get("required", [])
        for field in required_fields:
            if field not in arguments:
                return False, f"Required field '{field}' missing from arguments"

        return True, ""

    def get_tool_info(self) -> Dict[str, Any]:
        """Get summary information about registered tools.

        Returns:
            Dict with tool count and names
        """
        return {
            "total_tools": len(self.tools),
            "tool_names": list(self.tools.keys()),
            "tools_with_schemas": sum(1 for tool in self.tools.values() if tool.get("inputSchema")),
        }

    def clear(self) -> None:
        """Clear all registered tools."""
        self.tools.clear()


from typing import Tuple
