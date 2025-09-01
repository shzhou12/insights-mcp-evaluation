"""Main evaluation orchestrator for MCP tool evaluation."""

import argparse
import json
import os
import sys
from typing import Any, Dict, List

from .evaluator import Evaluator
from .llm_client import LLMClient


def load_test_cases(cases_file: str) -> List[Dict[str, Any]]:
    """Load test cases from JSONL file.

    Args:
        cases_file: Path to JSONL file with test cases

    Returns:
        List of test case dictionaries
    """
    cases = []

    if not os.path.exists(cases_file):
        print(f"Error: Test cases file not found: {cases_file}")
        return cases

    try:
        with open(cases_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    try:
                        case = json.loads(line)
                        # Add line number as case_id if not present
                        if "case_id" not in case:
                            case["case_id"] = f"case_{line_num}"
                        cases.append(case)
                    except json.JSONDecodeError as e:
                        print(f"Warning: Invalid JSON on line {line_num}: {e}")

    except Exception as e:
        print(f"Error reading test cases file: {e}")

    return cases


def run_evaluation(
    cases_file: str, mcp_command: List[str], log_file: str = "out/eval.jsonl", llm_config: Dict[str, Any] = None
) -> None:
    """Run evaluation on test cases.

    Args:
        cases_file: Path to test cases JSONL file
        mcp_command: Command to start MCP server
        log_file: Path to output log file
        llm_config: LLM configuration (base_url, api_key, model)
    """
    # Load test cases
    cases = load_test_cases(cases_file)
    if not cases:
        print("No valid test cases found. Exiting.")
        return

    print(f"Loaded {len(cases)} test cases from {cases_file}")

    # Initialize LLM client
    llm_config = llm_config or {}
    try:
        llm_client = LLMClient(
            base_url=llm_config.get("base_url"), api_key=llm_config.get("api_key"), model=llm_config.get("model")
        )
    except Exception as e:
        print(f"Error initializing LLM client: {e}")
        return

    # Initialize evaluator
    evaluator = Evaluator(llm_client, mcp_command, log_file)

    print(f"Starting evaluation with MCP command: {' '.join(mcp_command)}")
    print(f"Results will be logged to: {log_file}")
    print()

    # Run evaluation on each case
    successful_cases = 0
    for i, case in enumerate(cases, 1):
        case_id = case.get("case_id", f"case_{i}")
        print(f"[{i}/{len(cases)}] Evaluating case: {case_id}")

        try:
            result = evaluator.evaluate_case(case)

            if result.get("error_message"):
                print(f"  ❌ Error: {result['error_message']}")
            else:
                selection = "✅" if result.get("selection_correct") else "❌"
                call = "✅" if result.get("call_success") else "❌"
                call_error = result.get("error_message", None)
                parameters_correct = "✅" if result.get("parameter_correct") else "❌"
                parameters_result = result.get("tool_args", None)
                chosen = result.get("chosen_tool", "None")
                print(f"  Tool selection: {selection} (chose: {chosen})")
                if call_error:
                    print(f"  Tool call: {call} ({call_error})")
                else:
                    print(f"  Tool call: {call}")
                print(f"  Parameter validation: {parameters_correct} ({parameters_result})")
                successful_cases += 1

        except Exception as e:
            print(f"  ❌ Evaluation failed: {e}")

        print()

    print(f"Evaluation completed. {successful_cases}/{len(cases)} cases ran successfully.")
    print(f"Detailed results logged to: {log_file}")


def run_summary(log_file: str, output_csv: str = None) -> None:
    """Run summary analysis on evaluation log.

    Args:
        log_file: Path to evaluation log file
        output_csv: Optional path to output CSV file
    """
    summary = Evaluator.summarize(log_file, output_csv)

    if "error" in summary:
        print(f"Error: {summary['error']}")
        return

    Evaluator.print_summary(summary)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="MCP Tool Evaluation")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Evaluate command
    eval_parser = subparsers.add_parser("evaluate", help="Run evaluation on test cases")
    eval_parser.add_argument("--cases", required=True, help="Path to test cases JSONL file")
    eval_parser.add_argument("--log", default="out/eval.jsonl", help="Output log file")
    eval_parser.add_argument("--mcp-command", nargs="+", required=True, help="Command to start MCP server")
    eval_parser.add_argument("--llm-base-url", help="LLM API base URL")
    eval_parser.add_argument("--llm-api-key", help="LLM API key")
    eval_parser.add_argument("--llm-model", help="LLM model name")

    # Summary command
    summary_parser = subparsers.add_parser("summarize", help="Summarize evaluation results")
    summary_parser.add_argument("log_file", help="Path to evaluation log file")
    summary_parser.add_argument("--csv", help="Output detailed CSV file")

    # Test connection command
    test_parser = subparsers.add_parser("test-connection", help="Test MCP server connection")
    test_parser.add_argument("mcp_command", nargs="+", help="Command to start MCP server")

    args = parser.parse_args()

    if args.command == "evaluate":
        llm_config = {"base_url": args.llm_base_url, "api_key": args.llm_api_key, "model": args.llm_model}
        run_evaluation(args.cases, args.mcp_command, args.log, llm_config)

    elif args.command == "summarize":
        run_summary(args.log_file, args.csv)

    elif args.command == "test-connection":
        from .mcp_stdio import test_connection

        if test_connection(args.mcp_command):
            print("✅ MCP server connection successful!")
        else:
            print("❌ MCP server connection failed!")
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
