.PHONY: up down

COMPOSE := docker compose --profile optional
SERVICES := clickhouse schema_migrator market_harvester stash_scribe

up:
	$(COMPOSE) up --build --detach $(SERVICES)

down:
	$(COMPOSE) down --remove-orphans
