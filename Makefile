# Pre-Market AI Agent — common tasks. `make help` lists them.
export APP_UID := $(shell id -u)
export APP_GID := $(shell id -g)

.DEFAULT_GOAL := help
.PHONY: help up report down logs ps test lint fmt build clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Build and start everything; the agent runs once (Grafana: http://localhost:3000)
	@test -f .env || (echo "Missing .env — run: cp .env.example .env" && exit 1)
	mkdir -p reports
	docker compose up -d --build
	@echo "Grafana    http://localhost:3000  (dashboard: Pre-Market AI Agent)"
	@echo "Prometheus http://localhost:9090"
	@echo "Agent logs: make logs"

report: ## Run the agent again, e.g. `make report ARGS="--force --date 2026-10-12"`
	docker compose run --rm agent $(ARGS)

down: ## Stop all containers (data volumes are kept)
	docker compose down

logs: ## Follow the agent's JSON logs
	docker compose logs -f agent

ps: ## Show container status
	docker compose ps -a

test: ## Run the test suite
	uv run pytest

lint: ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

fmt: ## Auto-fix lint issues and format
	uv run ruff check --fix .
	uv run ruff format .

build: ## Build the agent image only
	docker compose build agent

clean: ## Stop containers AND delete metrics/dashboard volumes
	docker compose down -v
