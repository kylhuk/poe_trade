# Path of Exile Trading Intelligence Suite
Comprehensive Implementation Blueprint

Purpose:
Create an automated research and trading intelligence system that discovers profitable
Path of Exile trading strategies using Public Stash data stored in ClickHouse.

The system consists of two tools sharing a strategy engine:

1. Strategy Research Lab
2. Opportunity Scanner / Alert Engine

The system does NOT automate gameplay. It only generates intelligence.

---

# Architecture Overview

System Layers

Data Layer
ClickHouse
Postgres
Redis

Backend Services
Ingestion
Strategy Engine
Backtester
Alert Generator

Interface Layer
Web UI
Browser Trade Search Links
Discord / Push Notifications

---

# Data Sources

Primary
Public Stash API

Secondary
Currency Exchange API
PoE Trade queries (generated search URLs)

Optional
Manual trade journal
Client.txt logs

---

# Core Design Principle

Everything is a strategy.

Strategy structure:

input item
transform
expected output
profit model
execution method

Examples:

Buy undervalued essence → bulk sell
Buy cheap cluster → craft → sell
Buy fragments → assemble set → sell

---

# Core Modules

## Ingestion Service

Consumes Public Stash API

Stores:

item_id
timestamp
account
price
league
mods
base type
item level
links
sockets

---

## Strategy Engine

Loads strategies from YAML files.

Evaluates strategies against ClickHouse data.

Produces opportunities.

---

## Backtesting Engine

Simulates strategy performance.

Calculates:

profit
ROI
capital required
fill probability
profit per hour

---

## Alert Engine

Runs periodic scans.

Outputs:

browser search
discord alert
UI notification

---

# Data Model

Events Table

stash_events

item_id
timestamp
price
account
league
raw_json

Items Table

parsed_items

item_id
base_type
ilvl
rarity
mods
influence
sockets
links

Listings Table

active_listings

item_id
price
currency
listed_at
account

---

# Strategy DSL

Example

strategy_id: essence_bulk_flip

input:
  type: essence

action:
  buy
  bulk_sell

parameters:
  min_stack: 20

evaluation:
  min_profit: 30 chaos

---

# Opportunity Score

score =

profit_expected
× fill_probability
÷ capital_required

---

# Alert Output

Example:

Strategy: Essence Bulk Flip

Buy:
Screaming Essence of Greed
1c each

Sell:
Bulk 30 for 45c

Profit:
15c

Search URL:
https://pathofexile.com/trade/search/...

---

# UI

Dashboard

Active opportunities
Strategy performance
Capital usage
Profit history

---

# Deployment

Docker containers

services:

backend
clickhouse
postgres
redis
frontend

---

# Phases

Phase 1
ingestion
schema
strategy runner

Phase 2
backtesting

Phase 3
alerts

Phase 4
UI

Phase 5
advanced strategies
