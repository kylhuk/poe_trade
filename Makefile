.PHONY: up down

COMPOSE := docker compose
SERVICES := clickhouse schema_migrator market_harvester

up:
	$(COMPOSE) up --build --detach $(SERVICES)

down:
	$(COMPOSE) down --remove-orphans
