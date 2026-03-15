# Comprehensive Codebase Review Follow-up

## Context
- Parent plan `comprehensive-codebase-review` is complete and passed final wave.
- Remaining evidence-backed unresolved items from `.sisyphus/evidence/review/task-16-risk-closeout.json` are now the scope of this follow-up plan.
- External-only blocker remains: live credential-gated auth/stash/restart flows require valid live credentials and cannot be solved from repo code alone.

## TODOs
- [ ] 1. Fix API/server CORS configuration so `https://poe.lama-lan.ch` is explicitly allowed and verify the behavior with deterministic tests plus direct header checks.
- [ ] 2. Add ML-to-scanner integration behind an additive, test-backed contract path so scanner recommendations can carry ML influence without breaking current consumers.
- [ ] 3. Design and implement the first additive candidate/data-diagnostics mart slice needed to eliminate the current `gold_*` no-data/coarse-gap blind spot, with targeted verification.
- [ ] 4. Update docs/CI/evidence for the follow-up changes and classify any remaining truly external blockers.
- [ ] F1. Follow-up compliance review
- [ ] F2. Follow-up code quality review
- [ ] F3. Follow-up real flow review
- [ ] F4. Follow-up scope fidelity review
