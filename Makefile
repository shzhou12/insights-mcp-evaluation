# MCP Evaluation Makefile

.PHONY: help install test clean smoke example

help:	## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:	## Install dependencies
	pip install -e .

install-dev:	## Install development dependencies
	pip install -e ".[dev]"

setup-node:	## Setup Node.js environment (if using nvm)
	@if [ -d "$$HOME/.nvm" ]; then \
		echo "Loading nvm environment..."; \
		export NVM_DIR="$$HOME/.nvm" && [ -s "$$NVM_DIR/nvm.sh" ] && . "$$NVM_DIR/nvm.sh"; \
	else \
		echo "nvm not found. Please ensure Node.js/npx is available."; \
	fi

test:	## Run smoke test
	./scripts/smoke.sh

example:	## Run example usage
	python scripts/example_usage.py

clean:	## Clean output files and cache
	rm -rf out/
	rm -rf __pycache__/
	rm -rf agent/__pycache__/
	rm -rf *.egg-info/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

smoke: test	## Alias for test

format:	## Format code with black
	black --line-length 120 agent/ scripts/

lint:	## Run linting
	mypy agent/
	black --check --line-length 120 agent/ scripts/

check: format lint	## Run all checks

# Connection testing targets
test-filesystem:	## Test filesystem MCP server connection
	@echo "Loading nvm and testing filesystem connection..."
	@export NVM_DIR="$$HOME/.nvm" && [ -s "$$NVM_DIR/nvm.sh" ] && . "$$NVM_DIR/nvm.sh" && \
	python -m agent.main test-connection -- npx @modelcontextprotocol/server-filesystem .

test-insights:	## Test Insights MCP server connection
	python -m agent.main test-connection -- "podman run --env INSIGHTS_CLIENT_ID --env INSIGHTS_CLIENT_SECRET --interactive --rm ghcr.io/redhatinsights/insights-mcp:latest"

# Quick evaluation targets
eval-filesystem:	## Quick filesystem evaluation
	@mkdir -p out
	@echo "Loading nvm and running filesystem evaluation..."
	@export NVM_DIR="$$HOME/.nvm" && [ -s "$$NVM_DIR/nvm.sh" ] && . "$$NVM_DIR/nvm.sh" && \
	python -m agent.main evaluate \
		--cases tests/cases.jsonl \
		--mcp-command npx @modelcontextprotocol/server-filesystem . \
		--log out/filesystem.jsonl

eval-insights:	## Quick Red Hat Insights MCP evaluation (all test cases)
	@mkdir -p out
	python -m agent.main evaluate \
		--cases tests/cases.jsonl \
		--mcp-command "podman run --env INSIGHTS_CLIENT_ID --env INSIGHTS_CLIENT_SECRET --interactive --rm ghcr.io/redhatinsights/insights-mcp:latest" \
		--log out/insights.jsonl

eval-image-builder:	## Quick Image Builder evaluation (currently available tools only)
	@mkdir -p out
	python -m agent.main evaluate \
		--cases tests/image_builder_cases.jsonl \
		--mcp-command "podman run --env INSIGHTS_CLIENT_ID --env INSIGHTS_CLIENT_SECRET --interactive --rm ghcr.io/redhatinsights/insights-mcp:latest" \
		--log out/image-builder.jsonl

eval-calculator:	## Quick calculator evaluation
	@mkdir -p out
	@echo "Loading nvm and running calculator evaluation..."
	@export NVM_DIR="$$HOME/.nvm" && [ -s "$$NVM_DIR/nvm.sh" ] && . "$$NVM_DIR/nvm.sh" && \
	python -m agent.main evaluate \
		--cases tests/cases.jsonl \
		--mcp-command npx @modelcontextprotocol/server-calculator \
		--log out/calculator.jsonl

summary:	## Generate summary from latest log
	@latest_log=$$(ls -t out/*.jsonl 2>/dev/null | head -1); \
	if [ -n "$$latest_log" ]; then \
		echo "Summarizing: $$latest_log"; \
		python -m agent.main summarize "$$latest_log" --csv out/summary.csv; \
	else \
		echo "No log files found in out/"; \
	fi

# Environment setup helpers
env-check:	## Check environment setup
	@echo "Checking Python environment..."
	@python --version
	@echo "Checking pip packages..."
	@pip show mcp || echo "⚠️  Please run 'make install' first"
	@echo "Checking Node.js environment..."
	@if command -v npx >/dev/null 2>&1; then \
		echo "✅ npx found: $$(npx --version)"; \
	elif [ -d "$$HOME/.nvm" ]; then \
		echo "nvm found, but Node.js not loaded. Run: export NVM_DIR=\"\$$HOME/.nvm\" && [ -s \"\$$NVM_DIR/nvm.sh\" ] && . \"\$$NVM_DIR/nvm.sh\""; \
	else \
		echo "❌ Node.js/npx not found. Please install Node.js or nvm"; \
	fi

# Usage examples
example-all:	## Run all evaluation examples
	$(MAKE) eval-filesystem
	$(MAKE) eval-calculator  
	$(MAKE) summary

# Docker alternatives (for environments without Node.js)
eval-filesystem-docker:	## Run filesystem evaluation using Docker
	@mkdir -p out
	docker run --rm -v "$$(pwd)":/workspace -w /workspace \
		node:18 npx @modelcontextprotocol/server-filesystem /workspace &
	sleep 2
	python -m agent.main evaluate \
		--cases tests/cases.jsonl \
		--mcp-command docker exec $$(docker ps -q) npx @modelcontextprotocol/server-filesystem /workspace \
		--log out/filesystem-docker.jsonl
