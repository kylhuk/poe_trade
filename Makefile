.PHONY: up down backtest-all

COMPOSE := docker compose
SERVICES := clickhouse schema_migrator market_harvester
PYTHON := .venv/bin/python
BACKTEST_LEAGUE ?= Mirage
BACKTEST_DAYS ?= 14
BACKTEST_FLAGS ?=

up:
	$(COMPOSE) up --build --detach $(SERVICES)

down:
	$(COMPOSE) down --remove-orphans

backtest-all:
	$(PYTHON) -m poe_trade.cli research backtest-all --league "$(BACKTEST_LEAGUE)" --days "$(BACKTEST_DAYS)" $(BACKTEST_FLAGS)

update:
	$(PYTHON) -m poe_trade.cli refresh gold --group refs
