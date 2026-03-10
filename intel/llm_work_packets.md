# LLM Work Packets

These packets are meant to be given sequentially to coding LLMs.

---

# Packet 1
Repository bootstrap

Tasks:

Create repo structure

backend/
frontend/
infra/

Implement Docker Compose with

clickhouse
postgres
redis
backend
frontend

---

# Packet 2
ClickHouse ingestion

Implement

stash API consumer

Steps:

1 connect to API
2 store JSON
3 insert into stash_events
4 maintain cursor

---

# Packet 3
Item parser

Extract:

base type
ilvl
rarity
mods
links
sockets

Insert parsed results into parsed_items.

---

# Packet 4
Strategy engine

Load YAML strategies.

Run evaluation queries.

Return opportunities.

---

# Packet 5
Backtesting engine

Replay historical stash data.

Compute:

profit
ROI
fill rate

---

# Packet 6
Alert system

Periodic scans.

Send alerts via:

Discord
UI
Browser search URL

---

# Packet 7
Web UI

Dashboard:

opportunities
profit charts
strategy toggles

---

# Packet 8
Advanced strategies

Add modules for:

corruption EV
crafting EV
market making
