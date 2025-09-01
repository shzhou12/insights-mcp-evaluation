"""Evaluator for tracking tool selection accuracy and call success rates."""

import csv
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .llm_client import LLMClient
from .mcp_stdio import MCPStdioClient
from .registry import ToolRegistry


class Evaluator:
    """Evaluates MCP tool usage with accuracy and success rate metrics."""

    def __init__(self, llm_client: LLMClient, mcp_command: List[str], log_path: str = "out/eval.jsonl"):
        """Initialize the evaluator.

        Args:
            llm_client: LLM client for generating responses
            mcp_command: Command to start MCP server
            log_path: Path to log evaluation results
        """
        self.llm_client = llm_client
        self.mcp_command = mcp_command
        self.log_path = log_path
        self.registry = ToolRegistry()

        # Ensure log directory exists
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def evaluate_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a single test case.

        Args:
            case: Test case with prompt, expected_tools, etc.

        Returns:
            Evaluation result with metrics and details
        """
        case_id = case.get("case_id", f"case_{int(time.time())}")
        prompt = case.get("prompt", "")
        expected_tools = case.get("expected_tools", [])
        expected_parameters = case.get("expected_parameters", {})

        start_time = datetime.now()
        result = {
            "case_id": case_id,
            "prompt": prompt,
            "expected_tools": expected_tools,
            "expected_parameters": expected_parameters,
            "chosen_tool": None,
            "tool_args": None,
            "selection_correct": False,
            "call_success": False,
            "parameter_correct": False,
            "error_message": None,
            "timestamp": start_time.isoformat(),
            "duration_ms": 0,
        }

        try:
            # Connect to MCP server and get tools
            with MCPStdioClient(self.mcp_command) as mcp_client:
                if not mcp_client.initialize():
                    result["error_message"] = "Failed to initialize MCP client"
                    return result

                success, tools = mcp_client.list_tools()
                if not success:
                    result["error_message"] = "Failed to list tools from MCP server"
                    return result

                # Register tools
                self.registry.clear()
                self.registry.register_tools(tools)

                # Get OpenAI-compatible tool schema
                openai_tools = self.registry.to_openai_schema()

                # Generate LLM response
                llm_response = self.llm_client.generate(
                    prompt=prompt, tools_schema=openai_tools if openai_tools else None
                )

                if "error" in llm_response:
                    result["error_message"] = f"LLM error: {llm_response['error']}"
                    return result

                # Check if tool was called
                tool_calls = llm_response.get("tool_calls", [])
                if not tool_calls:
                    # No tool call - this counts as selection error
                    result["selection_correct"] = False
                    result["call_success"] = False
                    return result

                # Use first tool call for evaluation
                first_call = tool_calls[0]
                chosen_tool = first_call["name"]
                tool_args = first_call["arguments"]

                result["chosen_tool"] = chosen_tool
                result["tool_args"] = tool_args

                # Check tool selection correctness
                result["selection_correct"] = chosen_tool in expected_tools

                # Check parameter correctness before attempting tool call
                result["parameter_correct"] = self._validate_parameters(tool_args, expected_parameters)

                # Attempt tool call
                call_success, call_result = mcp_client.call_tool(chosen_tool, tool_args)

                # Judge tool call success based on JSON-RPC response:
                # Success = no error field in response OR explicit success=true
                if call_success:
                    # Additional check: if result contains success field, it must be true
                    if isinstance(call_result, dict):
                        error_exists = call_result.get("isError", True)
                        result["call_success"] = not error_exists

                        actual_result = call_result.get("structuredContent", {}).get("result", "")
                        if isinstance(actual_result, str) and actual_result.startswith("Error:"):
                            result["call_success"] = False
                            result["error_message"] = actual_result
                    else:
                        result["call_success"] = False
                    result["call_result"] = call_result
                else:
                    result["call_success"] = False
                    result["error_message"] = f"Tool call failed: {call_result}"

        except Exception as e:
            result["error_message"] = f"Evaluation error: {str(e)}"

        finally:
            # Calculate duration
            end_time = datetime.now()
            result["duration_ms"] = int((end_time - start_time).total_seconds() * 1000)

        # Log result
        self._log_result(result)

        return result

    def _validate_parameters(self, actual_params: Dict[str, Any], expected_params: Dict[str, str]) -> bool:
        """Validate that tool parameters contain the required minimum set.

        Args:
            actual_params: Parameters provided in the tool call
            expected_params: Expected parameters with requirement level (e.g., {"param": "required"})

        Returns:
            True if all required parameters are present and valid
        """
        if not expected_params:
            # No parameter requirements - always correct
            return True

        # Check that all required parameters are present
        for param_name, requirement in expected_params.items():
            if requirement == "required":
                if param_name not in actual_params:
                    return False
                # Check that the parameter has a non-empty value
                param_value = actual_params[param_name]
                if param_value is None or (isinstance(param_value, str) and param_value.strip() == ""):
                    return False

        return True

    def _log_result(self, result: Dict[str, Any]) -> None:
        """Log evaluation result to JSONL file.

        Args:
            result: Evaluation result to log
        """
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"Failed to log result: {e}")

    @staticmethod
    def summarize(log_path: str, output_csv: Optional[str] = None) -> Dict[str, Any]:
        """Summarize evaluation results from log file.

        Args:
            log_path: Path to JSONL log file
            output_csv: Optional path to output detailed CSV

        Returns:
            Summary statistics
        """
        if not os.path.exists(log_path):
            return {"error": f"Log file not found: {log_path}"}

        results = []
        total_cases = 0
        correct_selections = 0
        successful_calls = 0
        correct_parameters = 0

        # Read log file
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        result = json.loads(line)
                        results.append(result)
                        total_cases += 1

                        if result.get("selection_correct", False):
                            correct_selections += 1

                        if result.get("call_success", False):
                            successful_calls += 1

                        if result.get("parameter_correct", False):
                            correct_parameters += 1

        except Exception as e:
            return {"error": f"Failed to read log file: {e}"}

        # Calculate metrics
        selection_accuracy = correct_selections / total_cases if total_cases > 0 else 0.0
        call_success_rate = successful_calls / total_cases if total_cases > 0 else 0.0
        parameter_accuracy = correct_parameters / total_cases if total_cases > 0 else 0.0

        summary = {
            "total_cases": total_cases,
            "selection_accuracy": selection_accuracy,
            "call_success_rate": call_success_rate,
            "parameter_accuracy": parameter_accuracy,
            "correct_selections": correct_selections,
            "successful_calls": successful_calls,
            "correct_parameters": correct_parameters,
            "detailed_results": results,
        }

        # Generate CSV if requested
        if output_csv and results:
            try:
                with open(output_csv, "w", newline="", encoding="utf-8") as csvfile:
                    fieldnames = [
                        "case_id",
                        "prompt",
                        "expected_tools",
                        "expected_parameters",
                        "chosen_tool",
                        "selection_correct",
                        "call_success",
                        "parameter_correct",
                        "error_message",
                        "timestamp",
                        "duration_ms",
                    ]
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()

                    for result in results:
                        # Only include fields that are in fieldnames, with defaults for missing fields
                        csv_row = {}
                        for field in fieldnames:
                            if field in result:
                                value = result[field]
                                # Convert lists and dicts to string for CSV
                                if field == "expected_tools" and isinstance(value, list):
                                    csv_row[field] = ",".join(value)
                                elif field == "expected_parameters" and isinstance(value, dict):
                                    csv_row[field] = json.dumps(value)
                                else:
                                    csv_row[field] = value
                            else:
                                # Provide default values for missing fields
                                csv_row[field] = ""

                        writer.writerow(csv_row)

                print(f"Detailed CSV report saved to: {output_csv}")

            except Exception as e:
                summary["csv_error"] = f"Failed to write CSV: {e}"

        return summary

    @staticmethod
    def print_summary(summary: Dict[str, Any]) -> None:
        """Print summary statistics in a readable format.

        Args:
            summary: Summary dictionary from summarize()
        """
        if "error" in summary:
            print(f"Error: {summary['error']}")
            return

        print("=== MCP Evaluation Summary ===")
        print(f"Total test cases: {summary['total_cases']}")
        print(
            f"Tool selection accuracy: {summary['selection_accuracy']:.2%} ({summary['correct_selections']}/{summary['total_cases']})"
        )
        print(
            f"Tool call success rate: {summary['call_success_rate']:.2%} ({summary['successful_calls']}/{summary['total_cases']})"
        )
        print(
            f"Parameter accuracy: {summary['parameter_accuracy']:.2%} ({summary['correct_parameters']}/{summary['total_cases']})"
        )
        print()

        # Show failed cases
        failed_selections = [r for r in summary["detailed_results"] if not r.get("selection_correct", False)]
        failed_calls = [r for r in summary["detailed_results"] if not r.get("call_success", False)]
        failed_parameters = [r for r in summary["detailed_results"] if not r.get("parameter_correct", False)]

        if failed_selections:
            print("Failed tool selections:")
            for result in failed_selections:
                expected = ", ".join(result.get("expected_tools", []))
                chosen = result.get("chosen_tool", "None")
                print(f"  Case {result.get('case_id', '?')}: expected [{expected}], chose '{chosen}'")

        if failed_calls:
            print("Failed tool calls:")
            for result in failed_calls:
                tool = result.get("chosen_tool", "unknown")
                error = result.get("error_message", "Unknown error")
                print(f"  Case {result.get('case_id', '?')}: {tool} - {error}")

        if failed_parameters:
            print("Failed parameter validation:")
            for result in failed_parameters:
                tool = result.get("chosen_tool", "unknown")
                expected_params = result.get("expected_parameters", {})
                actual_params = result.get("tool_args", {})
                missing_params = [k for k, v in expected_params.items() if v == "required" and k not in actual_params]
                print(f"  Case {result.get('case_id', '?')}: {tool} - missing required parameters: {missing_params}")


# Fix the typo in the variable name
def summarize(log_path: str, output_csv: Optional[str] = None) -> Dict[str, Any]:
    """Standalone function to summarize evaluation results."""
    return Evaluator.summarize(log_path, output_csv)
