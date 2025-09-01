# Red Hat Insights MCP Evaluation

A framework for evaluating [Red Hat Insights MCP Server](https://github.com/RedHatInsights/insights-mcp) performance across three key metrics: **Tool Selection Accuracy**, **Tool Call Success Rate**, and **Parameter Correctness**.

The framework evaluates LLM interactions with Red Hat Insights services:
- **Advisor**: System optimization recommendations
- **Vulnerability Management**: CVE tracking and remediation
- **Inventory**: System and host management  
- **Image Builder**: Custom RHEL image creation
- **Remediations**: Automated fix generation with Ansible

## Evaluation Metrics

**1. Tool Selection Correctness**
- Measures if the LLM chooses the expected tool for a task
- Score: 1 if correct tool is called, 0 otherwise

**2. Tool Call Success** 
- Measures if tool calls execute without JSON-RPC errors
- Score: 1 if all required calls succeed, 0 otherwise

**3. Parameter Correctness**
- Measures if tool calls include required parameters with valid schema
- Score: 1 if schema validation passes and minimal parameters present, 0 otherwise

## Quick Start

### Prerequisites
- Python 3.8+
- Node.js (for testing filesystem MCP servers)
- OpenAI-compatible LLM endpoint

### Installation

```bash
# Clone the repository
git clone https://github.com/insights-mcp/insights-mcp-evaluation
cd insights-mcp-evaluation

# Install with uv (recommended)
uv sync

# Or install with pip
uv pip install -e .

# For development
uv sync --dev
# Or: pip install -e ".[dev]"
```

### Configuration

**1. LLM Configuration**
```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"  # or your local endpoint
export MODEL="gpt-3.5-turbo"
```

**2. Red Hat Insights Authentication**
```bash
export INSIGHTS_CLIENT_ID="your-service-account-id" 
export INSIGHTS_CLIENT_SECRET="your-service-account-secret"
```

### Running Evaluation

**Using Makefile:**
```bash
# Check environment setup
make env-check

# Test connection 
make test-insights

# Run evaluation
make eval-insights

# Generate summary
make summary
```

## MCP Server Options

The framework supports various MCP servers:

- **Red Hat Insights (Container)**: `podman run --env INSIGHTS_CLIENT_ID --env INSIGHTS_CLIENT_SECRET --interactive --rm ghcr.io/redhatinsights/insights-mcp:latest`
- **Red Hat Insights (Local)**: `insights-mcp --toolset=advisor,vulnerability,inventory,image-builder,remediations`
- **Filesystem (Testing)**: `npx @modelcontextprotocol/server-filesystem <directory>`
- **Calculator (Testing)**: `npx @modelcontextprotocol/server-calculator`

## Output Format

**JSONL Log Entry:**
```json
{
  "case_id": "advisor_recommendations_basic",
  "prompt": "Show me active recommendations for my systems", 
  "expected_tools": ["advisor__get_active_rules"],
  "chosen_tool": "advisor__get_active_rules",
  "selection_correct": true,
  "call_success": true,
  "parameter_correct": true,
  "timestamp": "2024-01-15T10:30:00",
  "duration_ms": 1500
}
```

**CSV Summary:**
- Columns: `case_id`, `prompt`, `expected_tools`, `chosen_tool`, `selection_correct`, `call_success`, `parameter_correct`, `error_message`, `timestamp`, `duration_ms`

## Development

**Code Quality:**
```bash
# Format and lint
make format
make lint

# Run all checks
make check
```

**Testing:**
```bash
# Run tests
pytest

# With coverage
pytest --cov=agent
```

**Available Commands:**
```bash
make help  # Show all available commands
```

## Limitations

- Single-step tool evaluation only
- Evaluates first tool choice (no retry logic)
- Basic error detection (MCP-level errors)

## Extensions

Future enhancements could include:
- Multi-step workflow evaluation
- Advanced parameter validation
- Performance metrics (latency, throughput)
- A/B testing between LLM configurations
- CI/CD integration