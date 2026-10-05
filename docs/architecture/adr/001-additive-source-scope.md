# ADR 001: Additive source scope for new source categories

Status: Accepted for engine design (2026-10-02). This does not approve any project source or business claim.

## Context

`src/second_brain/schemas/project.schema.json` freezes `project.json` v0.1 with five source types and at least one source. R1 also requires data, analysis, and policy sources. A classification label alone cannot make one of those sources eligible for capture. Existing runs and releases must remain verifiable from their frozen inputs.

## Decision

An optional `config/source-scope.json` v1.0 registers additional sources of type `data`, `analysis`, or `policy`, each with its own id, root, include, and exclude patterns. Its ids and roots cannot overlap the sources in `project.json` or each other. The source type describes the primary material of the file; it does not classify every passage or establish authority.

`tools/kb_inventory.py` freezes the validated sidecar as `source-scope.snapshot.json`, records its byte hash in `manifest.source_scope`, and includes its values in `scope_sha256`. `tools/kb_check.py` verifies the frozen copy without consulting the current sidecar. `tools/kb_publish.py` copies it into releases. A changed sidecar makes cross-run deltas incomparable. Runs without a sidecar keep their existing configuration path and remain readable.

## Alternatives considered

- Expanding the enum in `project.json` would simplify registration but change its frozen v0.1 contract and require a separate configuration revision.
- Reclassifying a data or policy source as one of the five legacy types would make configuration misleading and weaken provenance.
- A sidecar containing labels only would leave new sources outside capture and fail the source-registration requirement.

## Consequences

The engine can capture the three new primary source categories without changing `project.json`. The additional file and manifest binding make scope review and release verification more complex. Since v0.1 still requires at least one legacy source, a project containing only data, analysis, or policy sources is not representable without a separately authorized configuration revision. A mixed-content file has one primary source type until Patch D adds segment-level representation; no content is silently assigned several source identities. Source type is a category, never an authority rank.

## Migration / rollout notes

Existing configurations need no sidecar. An operator may add one before creating a new run, or use `kb_init.py --expanded-source` while creating a workspace with at least one legacy `--source`. Source-scope changes require a new run; frozen manifests, snapshots, reviews, and releases are never rewritten. No new file format is introduced by this decision.

## Validation impact

Synthetic tests cover all eight primary categories, mixed-content classification boundaries, duplicate ids, overlapping roots, invalid mappings, frozen-snapshot tampering, comparable evidence changes, incomparable scope changes, legacy run verification, and release self-containment. Real-source inclusion criteria and extraction fidelity still need operator and human review.

## Related artifacts

`src/second_brain/schemas/source-scope.schema.json`, `src/second_brain/schemas/manifest.schema.json`, `tools/kb_common.py`, `tools/kb_init.py`, `tools/kb_inventory.py`, `tools/kb_check.py`, `tools/kb_publish.py`, `tests/test_source_scope.py`, and `docs/REQUIREMENTS_V2_DELIVERY_PLAN.md`.
