---
name: protocol-compat
description: Checklist for safe ClickHouse schema/data-contract evolution (additive changes, staged migrations, downgrade thinking).
---
# Protocol/ClickHouse compatibility checklist

Use this skill whenever you modify ClickHouse schemas, migrations, materialized views, or downstream consumers that rely on those contracts.

1. Prefer additive changes
    - Adding columns/tables/partition identifiers is the default path.
    - For removals: deprecate the column or metric, signal downstream consumers, and block the drop in a later migration once everyone has migrated.

2. Backward/forward read safety
   - Existing readers must still parse older rows (compatibility with missing columns or renamed fields).
   - New readers must handle legacy rows/partitions without raising fatal errors.

3. ClickHouse migration checklist
   - What SQL verifies the schema change? Include `clickhouse-local --query "DESCRIBE TABLE ..."` or `python -m poe_trade.cli validate-schema` as part of the bundle.
   - Test new readers against production-like snapshots (targeted pytest or query suite) where possible.

4. Documentation/migration note
   - Document schema intent/impact and note any downstream consumers that must re-run ETL or rebuild materialized views.
