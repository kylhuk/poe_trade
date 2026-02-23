# Ask User

- Confirm which ClickHouse tables or monitoring streams should feed `/v1/ops/dashboard` once the deterministic scaffolding is replaced with live metrics.
- Decide whether checkpoint drift alerts should trigger automated restarts or remain operator-only, and document the escalation flow.
- Clarify whether the dashboard should ship with authentication or be embedded inside the internal UI; currently it is a static HTML/JS bundle.
