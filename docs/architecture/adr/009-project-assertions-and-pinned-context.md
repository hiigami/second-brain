# ADR 009: Project-owned assertions and pinned preparation context

## Status

Accepted for the authorized engine implementation, 2026-10-06. Supplements ADRs 004 and 005. No real destination or retention permission is granted.

## Context

Approved releases own claims; the global index is disposable. Foreign context copied into a run persists in its release audit trail. Live foreign pointers and grants must not become historical integrity dependencies.

## Decision

Records 0.6 assertions have an originating record, type, exact parent evidence indexes, semantic status, reason and qualified `(project_id, run_id, record_id)` target. Direction is origin to target; equivalent/conflict groups do not merge claims. Index-derived views report resolved, unavailable or historical targets, opposing assertions and supersession cycles. Assertions never suppress underlying records, resolve disagreements, or establish applicability from dates. Foreign target changes require normal target intake/review. Re-anchoring offers citations only, clears cross-project approvals/assertions/aliases and forces fresh attribution/routing.

Ranking version 1 uses explicit terms and reviewed record aliases, weighted title/alias/statement matches, deterministic qualified-key ties, filter-preserving relationship expansion limited to two hops, reasons and omission counts. Full index verification remains required for initial retrieval; batch queries share one verified generation.

`context-permission` 1.0 explicitly authorizes selected projects, target run/release paths, quoted context, briefing and retained audit bytes with operator/time and retention reason. Index access alone is insufficient. A `run-context` 1.0 bundle is frozen under `work/` and bound by the manifest. It contains qualified records/provenance/statuses, request/query/ranking identity, budgets/omissions and selected release/config/permission bindings. Required keys that do not fit block; optional omissions are counted. Prior context is untrusted prior knowledge, never current evidence.

Prospective use, review preparation and publication verify live permission and selected dependencies. A selected foreign pointer change requires a new run; unrelated index changes do not invalidate pinned selections. The target's own pinned prior release is checked before publication, but its successful pointer swap does not retroactively invalidate the new release. Historical verification uses only frozen bytes and bindings, never live context permissions or foreign pointers. Published retention after revocation remains an operator responsibility.

Run creation coordinates bounded write-once tools. Explicit null context supports first runs; requested context failure never falls back. Stage receipts bind request/input/output hashes. Resume recognizes completed stages only after validating their outputs and inputs; interrupted stages fail clearly and require a new run, without overwriting or recapturing. Capture/packet temporary directories are cleaned by their existing exception paths; crash leftovers need operator inspection. Preparation stops before extraction, model calls, approval or publication. Index rebuilding after publication is explicit and cannot roll back publication.

## Alternatives considered

Canonical global claim store: rejected because it introduces another authority. Cached live permission checks: rejected without a separate design. Automatically replace pinned context or retry incomplete write-once stages: rejected because it conceals dependency changes and possible partial output.

## Consequences

Reproducible context adds storage and repeated validation cost; conservative selected-dependency changes require restarts. Budgets are records and UTF-8 bytes, not model tokens. Context permissions are audit declarations, not identity authentication. Real retention, retrieval usefulness and performance need a pilot.

## Migration / rollout notes

No real configuration, grant, destination, dependency or model behavior changes. Old schemas remain readable. Disposable outputs can be rebuilt; immutable releases cannot be rewritten.

## Validation impact

Synthetic tests cover unresolved/historical references, cyclic/conflicting supersession, citation-only re-anchoring, ranking ties/expansion, retained-destination permissions, stale/revoked selected context, historical independence, required budgets, first-run preparation and verified-only resume.

## Related artifacts

Implemented in `kb_index.py`, `kb_reconciliation.py`, `kb_reanchor.py`, `kb_context.py`, `kb_run.py` and the context contracts after ADR 008 scope gates. The targeted implementation plan records validation and the pending real-pilot gates.
