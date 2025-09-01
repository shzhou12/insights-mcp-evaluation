#!/bin/bash

# Smoke test script for MCP evaluation
# Tests basic functionality with a filesystem MCP server

set -e

echo "=== MCP Evaluation Smoke Test ==="
echo

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_ROOT/out/smoke_test.jsonl"
CSV_FILE="$PROJECT_ROOT/out/smoke_test.csv"

# Environment variables with defaults
export OPENAI_API_KEY="${OPENAI_API_KEY:-your-api-key-here}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://localhost:11434/v1}"  # Default Ollama
export MODEL="${MODEL:-llama3.2}"

echo "Configuration:"
echo "  LLM API: $OPENAI_BASE_URL"
echo "  Model: $MODEL"
echo "  Log file: $LOG_FILE"
echo

# Check dependencies
echo "Checking dependencies..."

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is required but not found"
    exit 1
fi

# Check if npx is available (for MCP filesystem server)
if ! command -v npx &> /dev/null; then
    echo "Error: npx is required but not found (install Node.js)"
    exit 1
fi

echo "✅ Dependencies check passed"
echo

# Test MCP server connection
echo "Testing MCP server connection..."
MCP_COMMAND=(npx -y @modelcontextprotocol/server-filesystem "$PROJECT_ROOT")

echo "MCP command: ${MCP_COMMAND[*]}"

# Test connection using our tool
cd "$PROJECT_ROOT"
if python3 -m agent.main test-connection "${MCP_COMMAND[@]}"; then
    echo "✅ MCP server connection successful"
else
    echo "❌ MCP server connection failed"
    echo "Make sure you have Node.js installed and can run: ${MCP_COMMAND[*]}"
    exit 1
fi
echo

# Create a simple test cases file for smoke test
SMOKE_CASES="$PROJECT_ROOT/tests/smoke_cases.jsonl"
cat > "$SMOKE_CASES" << 'EOF'
{"case_id": "smoke_list", "prompt": "List all files in the current directory", "expected_tools": ["list_directory"]}
{"case_id": "smoke_read", "prompt": "Read the contents of the README.md file", "expected_tools": ["read_file"]}
EOF

echo "Created smoke test cases: $SMOKE_CASES"
echo

# Check environment variables
if [ "$OPENAI_API_KEY" = "your-api-key-here" ]; then
    echo "⚠️  Warning: Using default API key. Set OPENAI_API_KEY environment variable."
    echo "   For Ollama: export OPENAI_API_KEY=ollama"
    echo "   For local vLLM: export OPENAI_API_KEY=your-actual-key"
    echo
fi

# Run evaluation
echo "Running smoke test evaluation..."
echo "Command: python3 -m agent.main evaluate --cases \"$SMOKE_CASES\" --log \"$LOG_FILE\" --mcp-command ${MCP_COMMAND[*]}"

if python3 -m agent.main evaluate \
    --cases "$SMOKE_CASES" \
    --log "$LOG_FILE" \
    --mcp-command "${MCP_COMMAND[@]}"; then
    echo "✅ Evaluation completed successfully"
else
    echo "❌ Evaluation failed"
    exit 1
fi
echo

# Generate summary
echo "Generating summary report..."
if python3 -m agent.main summarize "$LOG_FILE" --csv "$CSV_FILE"; then
    echo "✅ Summary generated successfully"
    echo "📊 Detailed CSV report: $CSV_FILE"
else
    echo "❌ Summary generation failed"
    exit 1
fi
echo

echo "=== Smoke Test Completed Successfully ==="
echo
echo "Files generated:"
echo "  📄 Evaluation log: $LOG_FILE"
echo "  📊 CSV report: $CSV_FILE"
echo "  🧪 Test cases: $SMOKE_CASES"
echo
echo "To run a full evaluation:"
echo "  python3 -m agent.main evaluate --cases tests/cases.jsonl --log out/eval.jsonl --mcp-command ${MCP_COMMAND[*]}"
echo "  python3 -m agent.main summarize out/eval.jsonl --csv out/eval.csv"