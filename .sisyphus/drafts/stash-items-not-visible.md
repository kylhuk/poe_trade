# Draft: Stash Items Not Visible

## Requirements (confirmed)
- "I cannot see any stash items. Check this repo here, check the frontend-repo therer: /home/hal9000/docker/poe-frontend and also check @apispec.yml . Figure out what's wrong."

## Technical Decisions
- Diagnose by comparing backend routes, OpenAPI spec, and frontend API usage before proposing any fix.
- Treat the primary issue as a data-availability / gating problem unless a contract mismatch proves otherwise.

## Research Findings
- Backend stash routes are wired in `poe_trade/api/app.py` and implemented in `poe_trade/api/stash.py`.
- `poe_trade/stash_scan.py` only returns stash tabs/items from published scan data; no published scan means empty tabs/status.
- Frontend stash UI is driven by `src/components/tabs/StashViewerTab.tsx` and normalizes responses in `src/services/api.ts`.
- Frontend auth/proxy flow can hide the stash tab entirely when the user is not approved or not authenticated.
- `apispec.yml` matches the route set, but it documents `tabIndex` on `/api/v1/stash/tabs` even though backend behavior does not appear to use it.

## Open Questions
- None blocking; likely root cause is unpublished/empty stash data or session/auth gating.

## Scope Boundaries
- INCLUDE: current repo stash API, frontend stash UI/data flow, apispec.yml contract.
- EXCLUDE: source changes until the mismatch is identified.
