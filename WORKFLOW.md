# Stage 2 workflow

Targeted preparation is an explicitly authorized opt-in engine path described in
ADRs 008–009. Operators supply a versioned run request with exact capture scope,
purpose, packet policy and either explicit no-context or separately permitted
prior context. Analysis-only work cannot replace approved project state. Refresh
still follows the serial manual extraction, reconciliation, semantic review and
human publication sequence below. Preparation never calls a model.

## Entry condition

The operator has an approved local project workspace and approved UTF-8 source snapshots. Stage 1 is a source-fidelity prerequisite, not something this bundle claims to have performed. The real pilot is intentionally narrow enough to review end to end.

## State sequence

```text
CONFIGURED
  -> INVENTORY_READY (or INVENTORY_BLOCKED)
  -> PACKETS_READY
  -> CANDIDATE_EXTRACTED
  -> CANDIDATE_RECONCILED
  -> STRUCTURALLY_CHECKED
  -> SEMANTICALLY_REVIEWED
  -> HUMAN_APPROVED (or CHANGES_REQUESTED)
  -> PUBLISHED
```

This is an operational sequence implemented by separate CLI steps and human/assistant actions. It is not an autonomous scheduler or graph runtime. Commands do not schedule themselves, run in the background, or invoke a model.

## Operator: targeted run preparation

After authorizing exact membership and any context retention, supply `run-request`
1.0 to `second-brain run create`. `--dry-run` checks path scope and requested prior
context without writing or opening source content. `context: null` explicitly
supports first runs; requested retrieval failure blocks before capture. Strict
mixed-source isolation consumes reviewed hashed UTF-8 exports without opening
their original references. Whole-file mode explicitly retains all selected bytes.

The command freezes the request/purpose, captures selected evidence, prepares
packets and exhaustive interval stubs, scans selected mentions, offers prior
citation suggestions, and writes `work/assistant-briefing.md` and a reconciliation
checklist. Hash receipts permit verified completed-stage resume only. Interrupted
write-once stages require a new run id; never overwrite packets or recapture.
The preparation handoff is inventory/context checking, not extraction or semantic
validation. Continue serially using the prompts and records 0.6/referrals 1.1.

`analysis_only` cannot prepare publication review or publish. `project_refresh`
must revalidate retained claims with current evidence or propose explicitly
reviewed removals. Ranked prior context cannot be current-run evidence. Context
permission/freshness is checked prospectively before use/review/publication;
historical verification uses frozen bindings and survives later foreign changes.
After human publication, rebuild derived indexes separately. A stale-index or
refresh failure never rolls back the successful project release. See the
[CLI reference](docs/CONFIG_REFERENCE.md#targeted-run-preparation).

## Operator: configuration and capture

Read `project.json`, root/project policies, and source-fidelity notes. Start with a small project slice, not the entire work drive. Capture with `kb_inventory.py`; stop on a blocked run. Check missing provenance, unsupported files, source counts, and any delta. Approving a warning later does not make missing information exist.

The inventory creates a new run, copies exact eligible bytes into inert `.txt` snapshots, hashes them, and seals the manifest. It does not rewrite sources. Capture is file-by-file, not an atomic point-in-time snapshot of an entire repository or Google document collection. Pause edits or use an immutable export/checkout when cross-file consistency matters.

Generate packets with `kb_packet.py`. Inspect the packet index, `packets/document-navigation.md`, source counts, and, for new runs, `segments.snapshot.json` with its locators and unavailable extraction issues. The navigation page uses frozen document content dates and an undated group; it does not infer business event time. When the configured scope is wider than the pilot question, select by `--select-glob` and/or `--grep`. This records omitted evidence and writes `packets/coverage-stub.json`, which marks unselected files and segments `triaged_out` with the selection method. The final Stage 2 gate refuses `deferred` coverage and requires the reviewer to acknowledge triage explicitly.

For an explicitly registered multi-project workspace, the operator may run `kb_mentions.py --run <run> --registry <projects/registry.json>`. It checks sealed snapshots, scans only explicit names and aliases of other projects in the same information domain, and writes `work/mentions.json` plus `work/registry.snapshot.json`. It does not infer relevance, completeness, shared-component ownership, or permission to disclose. A same-domain label alone is insufficient permission. Registry 1.1 adds explicit origin/target/source-path disclosure grants for the later referral gate; registry 1.0 can scan but cannot authorize referrals.

## GLM pass 1: extraction

Use `prompts/01_EXTRACT.md` and the `kb-extract` skill. Read one bounded packet or a small related group. Produce candidate records using the current manifest's ids and exact lines. Keep proposed/unknown material separate from observed statements. Maintain a run-local list of batches inspected.

An intermediate candidate may retain deferred coverage. It is not publishable. For a new run, use records 0.3 or 0.4 to bind citations and coverage to frozen segments as well as files; records 0.4 additionally carry evidence-linked event dates. `reviewed_no_record` means the file or segment was read in full; a keyword scan or path filter is `triaged_out` with its method, never `reviewed_no_record`. Helper scripts the assistant writes go in the run's `work/` folder, which is copied into the release as audit material. All records and evidence must already satisfy the structural contract when running the non-Stage-2 checker. Do not state that all material has been reviewed just because all files were inventoried.

## GLM pass 2: reconciliation

Use `prompts/02_RECONCILE.md` and `kb-reconcile`. Reconcile duplicates and actual relations, preserving source conflicts. Existing approved knowledge is a prior snapshot to revalidate, not a superior authority over new source evidence. The operator runs `kb_reanchor.py --previous <release> --run <run>`, which proposes re-anchored records in `work/reanchored-records.json` and reports every quote that moved, changed, or vanished. Start reconciliation from that proposal and re-extract the records it drops. Every kept fact needs support in the current run. Stable record meanings retain ids; changed meanings receive a new id or an explicit reviewed revision, with prior releases preserved.

Produce one complete project-scope `proposals/records.json`, not an implicit patch. Omitted prior record ids will be disclosed in the review as removals. Do not copy unchanged records blindly; even a claim whose evidence bytes stayed unchanged may depend on another changed record or assumption.

For a routed run, use records 0.5 and a complete `proposals/referrals.json` v1.0. Assess every scanned mention as R1 (constrains home), R2 (other project only), R3 (context/name-drop), or R4 (shared component), with an explicit referred, linked-home, dismissed, or unresolved disposition and reason. R2 material must not become a home record. A pending referral cites exact frozen segment text and keeps target acceptance pending. The checker requires an explicit matching frozen registry disclosure grant; the human still reviews the exact context and whether this segment may be shown to the destination. A suggested exact source path is not permission for the target to capture an entire mixed file. Re-anchoring records 0.5 deliberately stops; reassess mentions, target links, and grants for each new run.

## GLM pass 3: bounded investigation and verification

Use `prompts/03_INVESTIGATE.md` for one code/schema question and `prompts/04_VERIFY.md` / `kb-verify` for semantic review. Restrict conclusions to the files/lines actually inspected. Proposed queries are text artifacts only; no live database execution is authorized by this workflow.

Run `kb_check.py --stage2` against the final candidate. The checker validates JSON shape, source/run identity, byte integrity, exact citation ranges/quotes, explicit coverage, investigation scope, and links. It cannot validate entailment, relevance, decision authority, real model quality, or whether the assistant honestly read a packet. It does reject decisions that cite only repository evidence. Its `semantic_hints` (single-line citations, pending language in decision quotes, decisions resting only on AI-generated summaries) must each be addressed in the semantic review. The record-kind quota is reported as `stage2_milestone`, not enforced.

Use at most two repair attempts after the first checker attempt. Each repair must address an actual error, preserve evidence, and rerun checks. If semantic questions remain, write them into the records/review note rather than polishing them into certainty. A second pass by the same model is additional scrutiny, not an independent judge.

Write `proposals/semantic-review.md`: findings, supporting record/evidence ids, ambiguities, and a recommendation of ready-for-human-review or changes-required. It is never a human approval.

## Operator: review and publication

Prepare the review using `kb_publish.py --prepare`. This creates false approval checks, hashes of the exact candidate, manifest, and generated `review-report.md`, the previous release id, proposed approved ids, and disclosed removals. Routed records 0.5 use review 0.4, which additionally binds referrals, mention scan, registry digest, and a false `cross_project_checked` gate. The report shows record changes and unchanged records, frozen quote context, routing assessments, semantic questions, fidelity gaps, triage, and warning occurrences before approval. Review exact quotes in context, status/authority, conflict treatment, coverage, destination disclosure, and information-handling compliance; the report is a navigation aid, not approval or proof that no issue exists.

Save an explicit approval as `review.json` only when satisfied. Every warning must be consciously acknowledged by code and occurrence count (`acknowledged_warnings`), and any triaged-out inputs through `triage_acknowledged`; preserving an unresolved issue can be legitimate, but fabricating its resolution cannot. Do not change hashes manually to bypass review after editing records. Re-prepare in a fresh filename/run as documented in troubleshooting, then repeat the substantive review.

Publish with the explicit human flag. Publication checks hashes, report rendering, and current-release lineage again, obtains a local lock, builds a new immutable release including the bound review report and run's `work/` folder, verifies the copied evidence, generates views (record pages, project map, open questions, records by code, event timeline, changes since the previous release), and atomically replaces `CURRENT.json`. For routed runs it also copies exact referrals and generates an origin-release `outbox.md` grouped by target, labeled pending target review. Target intake remains separate. The timeline preserves uncertainty and does not assert a current or superseding business state. It never edits upstream sources or an existing approved release.

## Operator: target referral intake

Run `kb_referrals.py discover` with the target configuration, registry 1.1, and each explicitly authorized origin configuration. Only checked current approved releases with both frozen and current disclosure grants contribute referral context. The target's `knowledge/referral-intake.json` v1.0 is separate from approved knowledge. Repeated scans preserve decisions; a changed origin release creates a fresh review item. Removed referrals become withdrawn, inaccessible or invalid origins become unavailable, and omitted origins become stale. Earlier decisions and target links remain historical.

A human supplies an `intake-review` 1.0 to `kb_referrals.py decide`: accept, decline-with-reason, or defer, bound to the origin review hash with reviewer/time. Acceptance proposes capture/reconciliation, never a target claim. Without explicit capture authorization the task is blocked. Authorize every part of a full-file copy or supply a reviewed scoped UTF-8 export with its byte hash and exact qualified referral text. The tool records traceable origin provenance but neither exports nor captures material.

Register only authorized target source scope, capture a new target run, and follow the normal extraction, checking, human review, and publication sequence. A human-authored `intake-link` 1.0 can then attach target release/record ids through `kb_referrals.py link`; the tool checks the target's own citations and separately records original hashes, representation hashes, and locators. Changed or withdrawn origins never silently modify approved target records. See [the CLI reference](docs/CONFIG_REFERENCE.md) and [ADR 004](docs/architecture/adr/004-reviewed-target-intake.md). Real-project authorization and usefulness remain unverified here.

## Operator: approved-release lookup

After assessing real intake, project policies, access, and storage/retention, an operator supplies an `index-access` 1.0 file and explicitly selected project configurations to `kb_index.py build`. The access file authorizes the projects' whole approved releases and a specific external `.json` output; same-domain membership and referral grants are insufficient. This checkout creates no real permission or shared destination. Current approved releases are selected by default; `--include-history` additionally selects published historical releases.

The derived index preserves each reviewed record's project/release/id, schema version, epistemic status, supported event/effective dates, ownership references, and exact frozen evidence links. Candidates, pending referrals, and intake tasks are excluded from indexed claims. `kb_index.py check` and `query` reconstruct the authorized selection and refuse stale policy, changed pointers, unavailable evidence, or altered artifacts. Query defaults to current records and offers explicit historical/all selection, project/kind/status/text filters, and bounded results. A reviewed proposal is still a proposal; source dates are not active-state or authority assertions.

Rebuild after publication, removal, rollback, or authorization change. The index is disposable and affects no project's approved knowledge or source. Its release set is recorded for reproducibility, not as a cross-project transaction. Real permission granularity, usability, and performance still need assessment. See [CLI reference](docs/CONFIG_REFERENCE.md) and [ADR 005](docs/architecture/adr/005-derived-approved-release-index.md).

## Completion

The deliverable is a reviewed project snapshot containing requirements, decisions, uncertainties, evidence links, at least one real relationship, one generated project map, and one bounded investigation. Do not force unsupported categories into the data. Choose an appropriate pilot scope or report why the Stage 2 milestone has not been met.

The real-project pilot is successful only after the semantic and usefulness criteria in `docs/PILOT_ACCEPTANCE.md` are assessed. Passing the synthetic test suite is necessary tooling evidence, not proof that GLM produces better work.

## Repeat cadence

After each new export (for example a Gemini-notes meeting): capture a new run with `--baseline`, run `kb_reanchor.py` against the current release, extract only the delta, check, review, and publish. Record review minutes per release in `templates/PILOT_SCORECARD.md`. Decide go / revise / stop after three releases, per `docs/PILOT_ACCEPTANCE.md`.
