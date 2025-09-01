# Red Hat Insights MCP Server Toolsets

This document explains the different toolsets available in the Red Hat Insights MCP Server and how to configure them for evaluation.

## Current Status

The current Docker image (`ghcr.io/redhatinsights/insights-mcp:latest`) appears to only provide **Image Builder** tools by default. The following tools are currently available:

✅ **Image Builder Tools (Currently Available)**
- `get_openapi` - Get OpenAPI spec for blueprint creation
- `create_blueprint` - Create custom Linux image blueprints
- `update_blueprint` - Update existing blueprints  
- `get_blueprints` - List user's image blueprints
- `get_blueprint_details` - Get detailed blueprint information
- `get_composes` - List image builds with status
- `get_compose_details` - Get detailed build information
- `blueprint_compose` - Start image build from blueprint
- `get_distributions` - List available Linux distributions

## Expected Toolsets (May Require Different Configuration)

🔄 **Advisor Tools (Expected but not currently available)**
- `advisor_get_active_rules` - Get active recommendations
- `advisor_get_rule_details` - Get detailed rule information
- `advisor_get_rule_by_text_search` - Search rules by text
- `advisor_get_recommendations_statistics` - Get statistics

🔄 **Vulnerability Tools (Expected but not currently available)**
- `vulnerability_get_cves` - List CVEs affecting systems
- `vulnerability_get_systems` - List systems in vulnerability inventory
- `vulnerability_get_cve_systems` - Get systems affected by specific CVE
- `vulnerability_explain_cves` - Explain CVE impact

🔄 **Inventory Tools (Expected but not currently available)**
- `inventory_list_hosts` - List all hosts
- `inventory_get_host_details` - Get detailed host information
- `inventory_find_host_by_name` - Find hosts by name

🔄 **Remediations Tools (Expected but not currently available)**
- `remediations_create_vulnerability_playbook` - Create Ansible playbooks for fixes

## Configuration Options

### Option 1: Docker with Environment Variables (Current)

```bash
# Current setup - provides Image Builder tools only
podman run --env INSIGHTS_CLIENT_ID --env INSIGHTS_CLIENT_SECRET --interactive --rm ghcr.io/redhatinsights/insights-mcp:latest
```

### Option 2: Local Installation with Toolset Selection

```bash
# Install locally
pip install insights-mcp-server

# Run with specific toolsets
insights-mcp --toolset=advisor,vulnerability,inventory,image-builder,remediations

# Or run with all toolsets
insights-mcp --toolset=all
```

### Option 3: Docker with Toolset Configuration (Untested)

```bash
# Try specifying toolsets via environment
podman run \
  --env INSIGHTS_CLIENT_ID \
  --env INSIGHTS_CLIENT_SECRET \
  --env MCP_TOOLSET=advisor,vulnerability,inventory,image-builder,remediations \
  --interactive --rm \
  ghcr.io/redhatinsights/insights-mcp:latest
```

## Test Case Alignment

Our test cases are designed to work with multiple toolset configurations:

1. **Image Builder Tests** - Currently functional with default Docker image
2. **Advisor Tests** - Include fallback tool names for different configurations  
3. **Vulnerability Tests** - Include fallback tool names for different configurations
4. **Inventory Tests** - Include fallback tool names for different configurations
5. **Remediations Tests** - Include fallback tool names for different configurations

## Authentication Requirements

All Insights toolsets require Red Hat Service Account credentials:

```bash
export INSIGHTS_CLIENT_ID="your-service-account-id"
export INSIGHTS_CLIENT_SECRET="your-service-account-secret"
```

## Next Steps

To fully evaluate the Insights MCP Server with all toolsets:

1. **Contact Red Hat Insights Team** - Verify correct Docker image or configuration for all toolsets
2. **Test Local Installation** - Try installing `insights-mcp-server` locally with `--toolset=all`
3. **Update Test Cases** - Once all tools are available, refine expected tool names
4. **Documentation Update** - Update main README with correct configuration

## Running Evaluations

### Current (Image Builder Only)
```bash
make test-insights          # Test connection
make eval-insights          # Run evaluation (will only test Image Builder prompts effectively)
```

### Future (All Toolsets)
```bash
# Once all toolsets are available
make eval-insights          # Will test all Advisor/Vulnerability/Inventory/Remediations prompts
```

## Tool Name Mapping

The test cases include multiple expected tool names to handle different naming conventions:

```json
{"expected_tools": ["advisor_get_active_rules", "get_active_rules"]}
```

This allows the evaluation to succeed regardless of the exact tool naming scheme used by the MCP server.
