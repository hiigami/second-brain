# ADR 005: Explicitly authorized derived approved-release lookup

Status: Accepted for the Patch N tooling contract (2026-10-04). This records a software design boundary, not approval of a real index destination or disclosure.

## Context

CONFIRMED: Each project owns its approved releases and current selection. Patch M's read-only approved-release validation checks publication history, review/report/routing bindings, frozen evidence, and current pointers. Registry domains and Patch L's referral grants do not authorize copying all approved project knowledge into shared storage. The delivery plan requires reproducible lookup, current/historical separation, exact provenance, and explicit access isolation.

## Decision

`tools/kb_index.py` creates a single derived `global-index` 1.0 JSON artifact. An operator-maintained `index-access` 1.0 file explicitly names the information domain, authorized project ids, absolute output path, operator, timestamp, and information-handling reason. This increment requires visibility of the selected projects' whole approved releases, including quoted context and evidence links. A restricted subset of records or segments cannot be safely represented by this grant. Same-domain membership and referral grants are insufficient. Each build, check, and query requires the live access file, registry, and exactly the explicit configurations for the authorized project set; paths stored in an index never become instructions to read another project.

There is no default real destination. The operator chooses it after access, storage, retention, and project-policy review. Output must be a normalized absolute `.json` path outside the engine, all selected project workspaces, all base/expanded source roots, and the access/registry files. An exclusive adjacent lock protects atomic replacement. An unrelated existing file cannot be overwritten as an index. No source, policy, configuration, run, approved release, or knowledge pointer is modified.

Default builds select only each project's checked current approved release. `--include-history` additionally selects published releases named in checked publication history; unread directories and candidates are never discovered by globbing. Release approval is checked through Patch M's public `load_approved_release` and `verify_approved_release` wrappers, with publication trace consistency additionally checked by the index. Historical review versions without report binding remain unsupported for indexing; existing readers are unchanged.

The index retains exact reviewed record content, original schema version, epistemic status, supported event/effective dates and uncertainty, project/domain/descriptive ownership references, and qualified `(project, release, record)` identities. Evidence links resolve parent and investigation-finding citations to checked frozen snapshots, original bytes, extraction sidecars, representation hashes, segments, line ranges, and locators. File-level records do not gain invented segment or event review. Pending referrals/intake/candidates are excluded from indexed claims. A reviewed proposal remains a proposal, and a reviewed uncertainty remains unresolved.

Deterministic generation identity binds canonical access/registry values, live config/source-scope digests, current pointers, publication histories, selected release bindings, and derived entries. Exact rebuilds preserve bytes. Checks and queries reconstruct the authorized selection and compare it with the saved artifact before returning results; changed access, missing releases/evidence, altered records, edits to the index, and detected input changes fail closed. Query defaults to current results; historical lookup requires an explicitly built history selection. Event dates do not establish active business state or authority. The selected release set is reproducible but is not a cross-project transaction.

## Alternatives considered

- Derive indexing permission from registry domain/referral grants: rejected because these describe narrower routing boundaries, not whole-release shared visibility.
- Use a fixed repository index location: rejected because this checkout has no authorized real storage destination, and policy/retention must be assessed first.
- Trust cached hashes on every lookup: cheaper, but it can return claims after access revocation or source corruption. Reconstructing from checked approved inputs is preferred for this bounded increment.
- Introduce a canonical global claim store or graph database: rejected because project releases remain the authorities for derived local knowledge. A disposable index satisfies lookup without creating another approval workflow.

## Consequences

Equal local record ids across projects coexist without deduplication. Corrections, removals, and rollbacks affect subsequent derived generations; historical records retain their exact release identities. Deleting/rebuilding the index cannot delete approved project knowledge.

Lookup costs repeated release/evidence validation and is intended for bounded project sets, not a low-latency large corpus. Limits are 1,000 releases, 10,000 entries, and 16 MiB per index, with query limits of 1–1,000 results (50 by default). Whole-release permissions are coarse; narrower disclosure requires a separately designed contract. Permission metadata is an audit convention, not human authentication or protection against an unrestricted process. Existing index copies remain subject to operator retention after revocation. Real authorization, usability, performance, and global retrieval quality remain unverified.

## Migration / rollout notes

This is opt-in and adds no real project registry, access file, shared output, scheduled job, model/API call, provider, dependency, or change to `project.json` v0.1. Old record/review readers and immutable releases remain intact. A stale or edited derived index can be rebuilt from fresh authorized inputs; malformed/unrelated files require operator inspection rather than automatic destruction.

## Validation impact

`tests/test_global_index.py` uses temporary synthetic workspaces to cover access isolation/revocation, duplicate ids, reproducible rebuilds, exact text/document/finding provenance, statuses/dates, candidates/referrals, current/history, correction/removal/rollback, absent inputs, tampering, output protection, symlinks, locks, detected policy/pointer/scope changes, and the operator CLI. Cross-project, compatibility, temporal/event/segment/source-scope suites remain regression gates. Tooling tests do not prove business truth or real usefulness.

## Related artifacts

See [delivery plan](../../REQUIREMENTS_V2_DELIVERY_PLAN.md), [CLI reference](../../CONFIG_REFERENCE.md), [ADR 004](004-reviewed-target-intake.md), and `src/second_brain/schemas/index-access.schema.json`, `src/second_brain/schemas/global-index.schema.json`.

Recommended next step: assess a real authorized intake and lookup pilot, resolve representative visual fidelity, and measure usefulness before expanding the tooling scope.
