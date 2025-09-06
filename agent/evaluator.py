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
        expected_result = case.get("expected_result_validation", {})

        start_time = datetime.now()
        result = {
            "case_id": case_id,
            "prompt": prompt,
            "expected_tools": expected_tools,
            "expected_parameters": expected_parameters,
            "expected_result": expected_result,
            "chosen_tool": None,
            "tool_args": None,
            "selection_correct": False,
            "call_success": False,
            "parameter_correct": False,
            "content_quality_check": False,
            "error_message": None,
            "content_quality_reason": None,
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
                result["call_result"] = call_result

                # Enhanced tool call success evaluation with multiple layers
                technical_success = self._evaluate_technical_success(call_success, call_result)
                content_quality_valid, content_reason = self._validate_content_quality(call_result, expected_result)
                
                # Store detailed results
                result["technical_success"] = technical_success
                result["content_quality_check"] = content_quality_valid
                result["content_quality_reason"] = content_reason
                
                # Overall call success: both technical success AND content quality
                result["call_success"] = technical_success and content_quality_valid
                
                # Set error message based on the failure type
                if not technical_success:
                    if not call_success:
                        result["error_message"] = f"Technical failure: Tool call failed: {call_result}"
                    else:
                        # Technical failure due to response format issues
                        if isinstance(call_result, dict):
                            actual_result = call_result.get("structuredContent", {}).get("result", "")
                            if isinstance(actual_result, str) and actual_result.startswith("Error:"):
                                result["error_message"] = f"Technical failure: {actual_result}"
                            else:
                                result["error_message"] = "Technical failure: Invalid response format"
                        else:
                            result["error_message"] = "Technical failure: Invalid response format"
                elif not content_quality_valid:
                    result["error_message"] = f"Content quality failure: {content_reason}"

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

    def _evaluate_technical_success(self, call_success: bool, call_result: Dict[str, Any]) -> bool:
        """Evaluate technical success of the tool call (JSON-RPC level).
        
        Args:
            call_success: Whether the MCP call succeeded
            call_result: The raw result from the tool call
            
        Returns:
            True if technically successful
        """
        if not call_success:
            return False
        
        # Additional check: if result contains error indicators
        if isinstance(call_result, dict):
            error_exists = call_result.get("isError", False)
            if error_exists:
                return False
            
            # Check for error messages in structured content
            structured_content = call_result.get("structuredContent", {})
            result_data = structured_content.get("result", "")
            if isinstance(result_data, str) and result_data.startswith("Error:"):
                return False
        else:
            # Non-dict response indicates format issues
            return False
        
        return True

    def _validate_content_quality(self, call_result: Dict[str, Any], expected_result: Dict[str, Any] = None) -> Tuple[bool, str]:
        """Validate the quality and completeness of tool call results.
        
        Args:
            call_result: The result returned by the tool call
            expected_result: Optional expected result validation rules
            
        Returns:
            Tuple of (is_valid, reason)
        """
        # Check if result is empty or meaningless
        if not self._has_meaningful_content(call_result):
            return False, "Empty or meaningless result"
        
        # If expected result validation is provided, use it
        if expected_result:
            return self._validate_against_expected(call_result, expected_result)
        
        # Default content quality checks
        return self._basic_content_validation(call_result)

    def _has_meaningful_content(self, call_result: Dict[str, Any]) -> bool:
        """Check if the call result contains meaningful content."""
        if not isinstance(call_result, dict):
            return False
        
        # Check for structured content
        structured_content = call_result.get("structuredContent", {})
        if isinstance(structured_content, dict):
            result_data = structured_content.get("result")
            
            # If result is a string, check it's not empty or error message
            if isinstance(result_data, str):
                result_data = result_data.strip()
                if not result_data or result_data.lower() in ["none", "null", "empty"]:
                    return False
                if result_data.startswith("Error:") or result_data.startswith("Failed:"):
                    return False
            
            # If result is a dict/object, check it has meaningful data
            elif isinstance(result_data, dict):
                # For API responses, check if data array exists and has items
                if "data" in result_data:
                    data = result_data["data"]
                    return isinstance(data, list) and len(data) > 0
                
                # For other dict responses, check for non-empty content
                return len(result_data) > 0 and any(
                    v for v in result_data.values() 
                    if v is not None and v != "" and v != []
                )
            
            # If result is a list, check it's not empty
            elif isinstance(result_data, list):
                return len(result_data) > 0
        
        # Check for content field
        content = call_result.get("content", [])
        if isinstance(content, list) and len(content) > 0:
            # Check if content has meaningful text
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "").strip()
                    if text and not text.startswith("Error:"):
                        return True
        
        return False

    def _validate_against_expected(self, call_result: Dict[str, Any], expected_result: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate call result against expected validation rules."""
        validation_type = expected_result.get("type", "basic")
        
        if validation_type == "content_check":
            return self._validate_content_check(call_result, expected_result)
        elif validation_type == "data_structure":
            return self._validate_data_structure(call_result, expected_result)
        else:
            return self._basic_content_validation(call_result)

    def _validate_content_check(self, call_result: Dict[str, Any], rules: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate content based on specific check rules."""
        structured_content = call_result.get("structuredContent", {})
        result_data = structured_content.get("result")
        
        if isinstance(result_data, str):
            try:
                import json
                result_data = json.loads(result_data.replace("'", '"'))
            except:
                pass
        
        if not isinstance(result_data, dict):
            return False, "Result is not a valid data structure"
        
        # Check minimum items if specified
        min_items = rules.get("min_items", 0)
        if "data" in result_data:
            data_items = result_data["data"]
            if isinstance(data_items, list) and len(data_items) < min_items:
                return False, f"Expected at least {min_items} items, got {len(data_items)}"
        
        # Check required fields
        required_fields = rules.get("required_fields", [])
        for field_path in required_fields:
            if not self._check_field_exists(result_data, field_path):
                return False, f"Required field '{field_path}' is missing"
        
        return True, "Content validation passed"

    def _validate_data_structure(self, call_result: Dict[str, Any], rules: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate the structure of returned data."""
        # This can be extended for specific data structure validation
        # For now, we use basic validation but could extend with rules-based checks
        _ = rules  # Acknowledge unused parameter for future extension
        return self._basic_content_validation(call_result)

    def _basic_content_validation(self, call_result: Dict[str, Any]) -> Tuple[bool, str]:
        """Perform basic content validation checks."""
        if not self._has_meaningful_content(call_result):
            return False, "No meaningful content found"
        
        # Check for obvious error indicators
        structured_content = call_result.get("structuredContent", {})
        result_data = structured_content.get("result", "")
        
        if isinstance(result_data, str):
            result_data = result_data.strip()
            error_indicators = ["error", "failed", "exception", "not found", "invalid"]
            if any(indicator in result_data.lower() for indicator in error_indicators):
                return False, f"Result contains error indicators: {result_data[:100]}"
        
        return True, "Basic validation passed"

    def _check_field_exists(self, data: Dict[str, Any], field_path: str) -> bool:
        """Check if a nested field exists in the data structure."""
        fields = field_path.split(".")
        current = data
        
        for field in fields:
            if not isinstance(current, dict) or field not in current:
                return False
            current = current[field]
        
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
                        "expected_result",
                        "chosen_tool",
                        "selection_correct",
                        "call_success",
                        "technical_success",
                        "content_quality_check",
                        "parameter_correct",
                        "error_message",
                        "content_quality_reason",
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
