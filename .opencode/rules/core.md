# Core rules (applies in all modes)

## Speed with proof
- Never claim “done” without capturing command output (build/test/lint/cli) or explicitly noting “not run / N/A” for each required step.
- Prefer the smallest correct change; keep iterations Python-first and verify with an actual interpreter or CLI run when possible.
- If the repository is currently documentation/planning-only, state that the change is conceptual rather than executed.

## Scope discipline
- Break work into small, verifiable steps. Prefer “one package / one concern” changes and limit edits to the active domain (PoE tooling, ClickHouse helpers).
- Keep context lean: only open/mention the files needed to do the current step; document any assumptions about league/item semantics or data-source constraints.

## Safety & security
- Never print or persist secrets or key material in logs, tests, fixtures, or examples.
- Security-sensitive code (crypto, auth, network parsing) requires extra caution and explicit negative-path tests.
- Verify data integrity around PoE concepts (league phases, item tiers, vendor rules) and honor source licensing or rate limits.
- ClickHouse schema/query changes must stay additive; avoid destructive operations (deleting columns/tables, mass deletions) unless there is explicit written approval.

## Protocol compatibility
- Treat data schemas and ClickHouse table contracts as strict compatibility boundaries.
- Keep alterations additive unless an explicit compatibility exception is documented; highlight expected downstream consumer impact before non-additive work.
