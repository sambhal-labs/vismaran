.PHONY: help install up down seed demo test lint typecheck clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install vismaran + all adapter extras + dev tools via uv
	uv sync --extra all --extra demo --extra dev

up:  ## Bring up the local stack (neo4j + postgres+pgvector + clickhouse + tensorzero)
	docker compose up -d
	@echo ""
	@echo "Stack up. Endpoints:"
	@echo "  Neo4j browser:    http://localhost:7474  (neo4j / vismarandev)"
	@echo "  Postgres:         postgres://vismaran:vismarandev@localhost:5432/vismaran"
	@echo "  ClickHouse:       http://localhost:8123  (default / no password)"
	@echo "  TensorZero gw:    http://localhost:3000"

down:  ## Stop and remove the local stack
	docker compose down

seed:  ## Seed Alice / Bob / Carol across all three memory layers via vismaran_sdk
	uv run python -m examples.fastapi_demo.backend.seed

demo:  ## Run the FastAPI + HTMX demo on http://localhost:8000
	uv run uvicorn examples.fastapi_demo.backend.app:app --reload --port 8000

test:  ## Run the unit + integration test suite (requires `make up` first for integration)
	uv run pytest

test-unit:  ## Run only unit tests (no docker needed)
	uv run pytest -m "not integration"

lint:  ## Lint with ruff
	uv run ruff check .

typecheck:  ## Type-check with pyright
	uv run pyright

clean:  ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info src/*.egg-info .pytest_cache .ruff_cache .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
