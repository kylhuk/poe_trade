.PHONY: up down build rebuild qa-up qa-down qa-seed qa-fault-scanner qa-fault-stash-empty qa-fault-api-unavailable qa-fault-service-action-failure qa-fault-clear qa-frontend qa-verify-product ci-deterministic ci-deterministic-ml-evidence ci-smoke-cli ci-api-contract backtest-all

COMPOSE := docker compose
QA_COMPOSE := $(COMPOSE) -f docker-compose.yml -f docker-compose.qa.yml --env-file .env.qa
SERVICES := clickhouse schema_migrator market_harvester scanner_worker ml_trainer poeninja_snapshot api
APP_SERVICES := schema_migrator market_harvester account_stash_harvester scanner_worker ml_trainer poeninja_snapshot api ml_v3_ops
PYTHON := .venv/bin/python
BACKTEST_LEAGUE ?= Mirage
BACKTEST_DAYS ?= 14
BACKTEST_FLAGS ?=
ML_EVIDENCE_ROOT ?= .sisyphus/evidence
ML_EVIDENCE_LOG ?= .sisyphus/evidence/task-12-deterministic-pack.log

up:
	$(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml up --detach $(SERVICES)

build:
	$(COMPOSE) build $(APP_SERVICES)

rebuild: build
	$(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml up --detach $(SERVICES)

down:
	$(COMPOSE) down --remove-orphans

qa-up:
	@test -f .env.qa || cp .env.qa.example .env.qa
	$(QA_COMPOSE) up --build --detach

qa-down:
	$(QA_COMPOSE) down --remove-orphans --volumes

qa-seed:
	$(PYTHON) -m poe_trade.qa_contract seed --output .sisyphus/evidence/product/task-1-qa-environment/qa-seed.json

qa-fault-scanner:
	$(PYTHON) -m poe_trade.qa_contract fault --name scanner_degraded --output .sisyphus/evidence/product/task-1-qa-environment/qa-fault-scanner.json

qa-fault-stash-empty:
	$(PYTHON) -m poe_trade.qa_contract fault --name stash_empty --output .sisyphus/evidence/product/task-1-qa-environment/qa-fault-stash-empty.json

qa-fault-api-unavailable:
	$(PYTHON) -m poe_trade.qa_contract fault --name api_unavailable --output .sisyphus/evidence/product/task-1-qa-environment/qa-fault-api-unavailable.json

qa-fault-service-action-failure:
	$(PYTHON) -m poe_trade.qa_contract fault --name service_action_failure --output .sisyphus/evidence/product/task-1-qa-environment/qa-fault-service-action-failure.json

qa-fault-clear:
	$(PYTHON) -m poe_trade.qa_contract clear-faults --output .sisyphus/evidence/product/task-1-qa-environment/qa-fault-clear.json

qa-frontend:
	cd frontend && npm run qa:dev

qa-verify-product:
	.venv/bin/pytest tests/unit/test_api_*.py tests/unit/test_strategy_*.py tests/unit/test_ml_*.py
	cd frontend && npm run test && npm run build && npm run test:inventory && npx playwright test
	$(PYTHON) -m poe_trade.evidence_bundle

backtest-all:
	$(PYTHON) -m poe_trade.cli research backtest-all --league "$(BACKTEST_LEAGUE)" --days "$(BACKTEST_DAYS)" $(BACKTEST_FLAGS)

update:
	$(PYTHON) -m poe_trade.cli refresh gold --group refs

ci-api-contract:
	.venv/bin/pytest tests/unit/test_api_ops_routes.py tests/unit/test_api_ops_analytics.py

ci-smoke-cli:
	$(PYTHON) -m poe_trade.cli --help
	$(PYTHON) -m poe_trade.cli service --name market_harvester -- --help
	$(PYTHON) -m poe_trade.cli refresh gold --group refs --dry-run
	$(PYTHON) -m poe_trade.cli strategy list
	$(PYTHON) -m poe_trade.cli research backtest --strategy bulk_essence --league Mirage --days 14 --dry-run
	$(PYTHON) -m poe_trade.cli scan once --league Mirage --dry-run
	$(PYTHON) -m poe_trade.cli journal buy --strategy bulk_essence --league Mirage --item-or-market-key sample --price-chaos 100 --quantity 20 --dry-run
	$(PYTHON) -m poe_trade.cli report daily --help
	$(PYTHON) -m poe_trade.cli alerts list --help
	$(PYTHON) -m poe_trade.cli sync psapi-once --help

ci-deterministic-ml-evidence:
	$(PYTHON) scripts/verify_ml_deterministic_pack.py --evidence-root "$(ML_EVIDENCE_ROOT)" --output-log "$(ML_EVIDENCE_LOG)"

ci-deterministic: ci-api-contract
	.venv/bin/pytest tests/unit
	npm --prefix frontend run test:deterministic
	$(MAKE) ci-smoke-cli
	docker compose -f docker-compose.yml -f docker-compose.qa.yml --env-file .env.qa.example config
	$(MAKE) ci-deterministic-ml-evidence
