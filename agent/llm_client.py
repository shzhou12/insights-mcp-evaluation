"""OpenAI-compatible LLM client for MCP evaluation."""

import json
import os
from typing import Any, Dict, List, Optional

import openai


class LLMClient:
    """OpenAI-compatible LLM client that supports custom base_url and api_key."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, model: Optional[str] = None):
        """Initialize the LLM client.

        Args:
            base_url: Custom OpenAI-compatible API endpoint (e.g., vLLM, Ollama)
            api_key: API key for authentication
            model: Model name to use for generation
        """
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("MODEL", "gpt-3.5-turbo")

        if not self.api_key:
            raise ValueError("API key is required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")

        self.client = openai.OpenAI(base_url=self.base_url, api_key=self.api_key)

    def generate(
        self,
        prompt: str,
        tools_schema: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 1000,
        temperature: float = 0.1,
    ) -> Dict[str, Any]:
        """Generate response from the LLM.

        Args:
            prompt: The input prompt
            tools_schema: List of tool schemas in OpenAI format
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Dict containing:
            - content: Natural language response
            - tool_calls: List of tool calls if any (name, arguments)
            - raw_response: Full OpenAI response object
        """
        messages = [{"role": "user", "content": prompt}]

        kwargs = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}

        if tools_schema:
            kwargs["tools"] = tools_schema
            kwargs["tool_choice"] = "auto"

        try:
            response = self.client.chat.completions.create(**kwargs)

            message = response.choices[0].message
            result = {"content": message.content or "", "tool_calls": [], "raw_response": response}

            # Extract tool calls if present
            if hasattr(message, "tool_calls") and message.tool_calls:
                for tool_call in message.tool_calls:
                    result["tool_calls"].append(
                        {
                            "name": tool_call.function.name,
                            "arguments": json.loads(tool_call.function.arguments),
                            "id": tool_call.id,
                        }
                    )

            return result

        except Exception as e:
            return {
                "content": f"Error generating response: {str(e)}",
                "tool_calls": [],
                "raw_response": None,
                "error": str(e),
            }

    def format_tools_for_openai(self, mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert MCP tool schemas to OpenAI format.

        Args:
            mcp_tools: List of MCP tool definitions

        Returns:
            List of OpenAI-compatible tool schemas
        """
        openai_tools = []

        for tool in mcp_tools:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {}),
                },
            }
            openai_tools.append(openai_tool)

        return openai_tools
