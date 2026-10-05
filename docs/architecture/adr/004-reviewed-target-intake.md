# ADR 004: Reviewed target intake outside approved knowledge

Status: Accepted for the Patch M tooling contract (2026-10-04). This records a software boundary, not business approval or authorization of a real disclosure.

## Context

CONFIRMED: Patch L publishes exact segment referrals in an origin release only after review 0.4. Its frozen source-path disclosure grant covers referral context, not every part of a mixed source file. Target knowledge has its own evidence ids, checks, human approval, immutable releases, and current selection. `project.json` remains v0.1.

## Decision

`tools/kb_referrals.py` maintains `knowledge/referral-intake.json` v1.0 outside the configured approved subtree. Only explicitly supplied origin configurations are scanned. Discovery validates approved current releases, publication history, frozen evidence, review/report/routing bindings, and the current registry 1.1 disclosure grant before copying an authorized referral into the target ledger. Invalid or inaccessible origins are unavailable; missing scans are stale, not withdrawals. Pointer and registry changes detected during intake abort the write.

Identity includes origin project, release, and referral id. Exact repeats preserve the ledger and decisions. A new release's matching source-path/referral slot raises a new review item with a predecessor link. This is an operational lineage hint, not proof of business supersession. Selecting an older approved release restores its existing item without duplicating or erasing history.

A human-authored `intake-review` 1.0 records accept, decline, or defer, a reason, reviewer, timestamp, and origin-review hash. Acceptance proposes capture/reconciliation; absent capture authorization keeps it blocked. A non-current origin blocks new capture work while preserving earlier acceptance and target links. Full-file capture requires explicit authorization for every included part and a matching original-byte hash. Otherwise a human supplies a reviewed UTF-8 scoped export whose hash and preserved exact quote are checked. The task retains origin release, original hash, representation, segment, lines, quote, and locator as provenance. The tool does not create an export, change scope, capture a run, or approve a target fact.

After normal target capture, checking, review, and publication, an `intake-link` 1.0 can bind explicit target records to a verified published target release. Each record needs its own citation to authorized bytes and the referred quote. Byte equality, representation equality, and locator equality are compared separately; different extraction context remains visible. Corrections, withdrawals, and independently evolving releases retain decisions and target links without rewriting approved knowledge.

## Alternatives considered

- Store intake in project policy: rejected because operational deduplication and decision history are not authority rules.
- Keep a separate immutable task file for each decision: workable, but it duplicates the ledger's audit data and introduces another synchronization boundary. The proposed task is embedded in the versioned ledger for this increment.
- Reuse origin evidence ids directly in target records: rejected because the target must capture and review its own evidence and disclosure scope.

## Consequences

Intake is repeatable and reversible independently of approved knowledge. A per-target exclusive lock and atomic replacement prevent ordinary concurrent ledger writes. Bounds are 10,000 items and 16 MiB; exceeding them requires an explicit retention or storage decision.

Operator work remains necessary: semantic relevance, authorization for every included part, export fidelity, source registration, and business supersession cannot be inferred by hashes. Ledger history retains previously disclosed context after a grant is revoked; authorized retention/deletion remains an operator responsibility. JSON reviewer fields are an audit convention, not identity authentication or a security boundary against an unrestricted user. Release sets are checked separately, not as a cross-project transaction.

## Migration / rollout notes

No migration of frozen records, reviews, registries, runs, or releases is needed. Existing readers and project configuration remain unchanged. Use explicit operator commands only after real project policies and access have been checked. No real projects are configured in this checkout.

## Validation impact

Synthetic `tests/test_cross_project.py` exercises retries, decisions, scoped exports, provenance, corrections, withdrawal after acceptance, release linkage, independent evolution, disclosure revocation, integrity failures, concurrency detection, and rollback. Legacy evidence and the full suite remain regression gates. These checks do not measure real routing quality or human review usefulness.

## Related artifacts

See [the delivery plan](../../REQUIREMENTS_V2_DELIVERY_PLAN.md), [CLI reference](../../CONFIG_REFERENCE.md), and `src/second_brain/schemas/referral-intake.schema.json`, `src/second_brain/schemas/intake-review.schema.json`, and `src/second_brain/schemas/intake-link.schema.json`.

Recommended next step: assess real target intake under authorized project policies before Patch N's global approved lookup.
