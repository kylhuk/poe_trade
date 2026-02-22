---
description: Make a safe protobuf change (additive-only, buf-aware).
agent: proto-engineer
---

Goal: $ARGUMENTS

Process
1) Identify the exact .proto(s) involved and current field numbers.
2) Propose an additive-only change (or stop and escalate if breaking is required).
3) Ensure removed/renamed fields are RESERVED (tags and names).
4) Make the change.
5) If possible, run:
   - buf lint
   - buf breaking (against main or a pinned baseline)
   - generation steps used in this repo
6) Summarize wire-compat implications.

Evidence
- If you ran commands, include command + output snippet.
