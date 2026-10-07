# ADR 008: Targeted run intent, capture permission and interval coverage

## Status

Accepted for the authorized engine implementation, 2026-10-06. This does not authorize real capture or disclosure. Supplements ADRs 001, 002 and 004; historical contracts remain unchanged.

## Context

Inventory captures entire eligible files; ordinary text has one frozen segment. Publication replaces complete project state. Packet relevance cannot authorize storage or justify removal of retained claims.

## Decision

An opt-in `run-request` 1.0 is frozen as `run-request.snapshot.json`, bound by additive `manifest.targeted` 1.0. Its purpose is `analysis_only` or `project_refresh`. Direct publication and review preparation reject analysis-only runs. Refresh still requires current-run support and explicit reviewed removals; no partial overlays exist.

The operator lists exact configured source/path membership before reads. `whole_file` expressly authorizes all listed bytes, including unrelated passages. `scoped_export` requires a reviewed UTF-8 export hash, original reference, locator, reviewer/time and limitations. The engine never opens that original reference. The complete request retains observed hashes, while the scope fingerprint binds only stable membership, representation mode, purpose, packet policy and composition. Content edits are comparable; selection or representation-policy edits are not.

Targeted runs require records 0.6 and referrals 1.1 regardless of alias hits. Records 0.5 and referrals 1.0 are frozen legacy readers. Records 0.6 add exhaustive interval coverage inside existing segments, per-citation attribution, reviewed aliases and project-owned assertions. Interval rows form an ordered, non-overlapping complete partition of each segment, bound to its representation hash. Rollup precedence is used, deferred, triaged_out, reviewed_no_record; used means cited, never fully read. Used intervals must intersect citations; citations must be entirely covered by used intervals. Unselected complements can only be triaged or deferred. Stage 2 rejects every deferred interval. Review binds exact records and exposes interval triage through segment rollups and the report.

Union remains the legacy default; explicit intersection intersects every supplied selector group. Empty selections fail. Ranges preserve original line numbers. Governing headings/labels/qualifiers require explicit context ranges where needed; omissions are exposed, never repaired by semantic guessing. Manual evidence-backed references supplement alias hits, using fresh routing assessment. R2 cannot support home knowledge; unknown attribution cannot support an observed home fact.

## Alternatives considered

Automatically extract passages from mixed originals: rejected because relevance cannot confer original access. Partial-release overlays: rejected because they obscure complete-snapshot removals. Repartition historical segments: rejected because it invalidates existing identity and review bindings.

## Consequences

Scoped exports and complete refreshes add operator work. The checker validates exact structure, coverage and declared attribution; semantic meaning and qualifier sufficiency remain human-reviewed. No model calls, provider changes or project.json changes are needed.

## Migration / rollout notes

Legacy manifests retain existing behavior. New profiles are explicit opt-in. Disable profiles to roll back prospectively, retaining readers for already-published records 0.6. Never rewrite frozen evidence or approved history.

## Validation impact

Synthetic gates cover excluded-original read avoidance, export tampering, comparable edits, incomparable scope changes, direct-publication rejection, mixed ranges/complements, old-schema evasion and empty alias scans. Real attribution quality remains pending.

## Related artifacts

Implemented in `kb_targeting.py`, `kb_intervals.py`, `kb_inventory.py`, `kb_packet.py`, `kb_check.py`, `kb_publish.py` and the run-request/records/referrals schemas. The targeted implementation plan records validation and the pending real-pilot gates.
