# Stage 2 contracts

## Targeted preparation contracts (opt-in)

See [ADR 008](docs/architecture/adr/008-targeted-run-scope-and-coverage.md) and
[ADR 009](docs/architecture/adr/009-project-assertions-and-pinned-context.md).
`project.json` remains 0.1. Additive `manifest.targeted` 1.0 binds a frozen
`run-request` 1.0, stable policy digest, run purpose and optional context digest.
Legacy manifests retain their original semantics. New targeted profiles require
records 0.6 and referrals 1.1; exact legacy schemas retain records 0.5/referrals 1.0.
Records 0.6 add interval coverage, per-citation attribution, aliases and qualified
project-owned assertions. No newer schema may bypass the existing citation,
segment, event, routing, human review or publication gates.

Interval rows partition each frozen segment, in order, without gaps or overlaps.
They bind representation hashes; rollups use used > deferred > triaged_out >
reviewed_no_record. Every citation is covered by used intervals and every used
interval intersects a citation. Unselected intervals cannot claim reading.
Deferred intervals block Stage 2. Coverage does not certify semantic reading.
Referral quotes must remain entirely within selected passages and cannot overlap
triaged or deferred intervals; whole-file/segment rollups do not override this.

`analysis_only` cannot prepare publication review or publish, including through
direct entry points. `project_refresh` is a complete snapshot: all retained claims
need current evidence and removed ids need explicit human acknowledgement.
Whole-file authorization expressly includes unrelated bytes; strict isolation
consumes hashed reviewed UTF-8 exports and never reads their original references.

`context-permission` 1.0 covers run and eventual release destinations, quotes,
briefings and retained audit copies. `run-context` 1.0 freezes prior qualified
records and provenance, queries/ranking version, budgets/omissions and selected
dependencies. Prospective checks use live permission/freshness; historical checks
use frozen integrity only. Context is untrusted prior knowledge, never new-run
evidence. Preparation receipts permit only verified completed-stage resume.

Versions: `project.json` 0.1 (frozen), optional source scope 1.0, project registry 1.1 (1.0 readable), manifest 0.1 (additively extended), segment inventory 1.0, records 0.6 (0.1–0.5 readable), review 0.4 for routed runs (0.1–0.3 readable), referrals 1.1 (1.0 readable), referral intake/review/link 1.0, index access/global index 1.0. Engine version 0.4.0. Targeted run-request, context-permission and run-context are 1.0 opt-in contracts.

The machine-readable contracts are `src/second_brain/schemas/*.schema.json`; superseded versions whose required fields changed are kept in `src/second_brain/schemas/legacy/<name>-<version>.schema.json` and selected by the document's `schema_version`. The tools validate a fixed subset of JSON Schema keywords and **reject any other keyword**, so a schema edit can never be silently ignored. They then enforce cross-file invariants. These scripts are not a general-purpose JSON Schema implementation. External Draft 2020-12 validators can also consume the schemas.

Separate `visual-packet` and `visual-assessment` 1.0 contracts support the optional local human-review workflow. Packets bind inert original bytes, preview hashes/dimensions, renderers/limits and retained gaps; completed human assessments bind the exact packet digest and complete item/gap set. These packet-local ids are not evidence ids, and the assessment is not an authenticated reviewer or business approval. See [local visual review](docs/LOCAL_VISUAL_REVIEW.md) and [ADR 006](docs/architecture/adr/006-local-visual-review-packets.md). Existing capture, candidate, and publication contracts are unchanged.

## 1. Project configuration

The recovered, frozen shape is:

```json
{
  "schema_version": "0.1",
  "project": {"id": "demo", "name": "Demo", "description": "A bounded Stage 2 pilot."},
  "sources": [
    {"id": "repository", "type": "repository", "path": "/approved/external/repository", "include": ["src/**", "tests/**", "docs/**"], "exclude": []}
  ],
  "global_exclude": ["**/.git/**", "**/node_modules/**", "**/.venv/**"],
  "knowledge": {"path": "knowledge", "approved": "knowledge/approved"},
  "runs": {"path": "runs"}
}
```

This compact example illustrates the shape, not the full default exclusions.

The config must live at `<project-root>/config/project.json`. Both source-relative paths and output paths are resolved relative to **project-root**, not `config/` and not the current shell directory. Source paths may be absolute or project-relative; output paths must be normalized, project-relative paths with no `..`. Knowledge, runs, and config must not overlap. Approved must be strictly inside knowledge. External source roots must neither overlap each other nor contain/be contained by the project workspace.

`project.id` and source ids use lowercase letters/digits/hyphen/underscore, up to 64 characters. Source types are requirements, architecture, meetings, sql, and repository. Categories do not define authority precedence. Unknown JSON fields, duplicate ids, and duplicate JSON keys are rejected.

An optional `config/source-scope.json` v1.0 adds source registrations with primary type `data`, `analysis`, or `policy`; `project.json` keeps its exact v0.1 shape. Each added source has its own id, path, include, and exclude fields. Ids and resolved roots must not overlap either the base configuration or another added source. The sidecar cannot override a base source. File category does not classify every segment or establish authority. Since v0.1 requires at least one base source, a project containing only the three new categories still needs a separately authorized project-configuration revision.

An operator-maintained `projects/registry.json` v1.1 lists project ids, names, aliases, information domains, descriptive `owns_paths` references, and explicit `disclosures` grants scoped by origin, target, source id, and path glob. Registry 1.0 remains readable for mention scanning but cannot authorize referrals. The registry is not source evidence or business authority. Duplicate ids and aliases that normalize to the same word sequence within one domain are rejected. Ownership paths are routing hints only. A disclosure grant and human review are both necessary before origin-release referral context appears in an outbox; neither permits target capture or approval. There is no real registry in this checkout because no real project workspace is present.

### Target intake contracts

Patch M uses `referral-intake` 1.0 at the fixed `knowledge/referral-intake.json` path, outside the configured approved subtree. It is a mutable proposal/audit ledger, not approved knowledge or project policy. Nested referrals use the existing referrals 1.0 item contract; decisions and target links use `intake-review` 1.0 and `intake-link` 1.0. A target lock protects atomic replacement; concurrent input changes, symlinks, more than 10,000 items, or more than 16 MiB fail closed.

Discovery reads only explicitly supplied, registered same-domain origins with a current disclosure grant. Each imported item also comes from a checked approved release with frozen grant, publication history, exact review/report/routing bindings, and complete review gates. Identity is `(origin project, origin release, referral id)`. Repeats retain decisions. A new current release raises a new item; a matching source-id/path/referral slot links the earlier review item through `supersedes`, which describes review lineage, not semantic business precedence. Status observations distinguish current, superseded, withdrawn, stale (not scanned), unavailable (missing/invalid approved origin), and unauthorized (live grant revoked). Historical decisions and target links are retained, including across current-release rollback.

Intake review requires accept/decline/defer, a nonblank reason and reviewer, a timezone-bearing timestamp no earlier than discovery, and the exact origin-review hash. Acceptance embeds a proposed capture/reconciliation task. Missing capture authorization leaves it blocked. A full-file authorization explicitly covers every included part and names an absolute external source path and matching original hash. A scoped export authorization names reviewed UTF-8 bytes with an exact referred quote, hash, and scope reason; a byte-identical whole-file copy cannot be passed off as a scoped export. Task provenance preserves original project/release/referral, file hash, representation, segment, line range, quote, and locator. No evidence export, scope update, target capture, approval, or publication occurs during intake.

Target linkage requires an already published, checked report-bound target release, explicit target-record ids, target-review hash, reviewer/time/reason, and an accepted authorized capture task. Each target record must cite its own evidence with authorized original bytes and the exact referred quote. The ledger reports representation/locator equality separately from byte equality; scoped-export lineage is explicit. Linking does not establish semantic entailment or equivalent context. Independently evolving target releases retain earlier links. Ledger reviewer fields and release hash conventions do not authenticate a human or isolate an unrestricted process. See [ADR 004](docs/architecture/adr/004-reviewed-target-intake.md).

### Derived approved-release index contracts

Patch N's `index-access` 1.0 is an operator-maintained authorization outside `project.json`. It explicitly names the information domain, whole-release authorized project ids, normalized absolute `.json` output path, authorizing operator/time, and information-handling reason. A domain label or referral disclosure grant does not authorize indexing. The operator chooses the real output after project-policy/access/storage review. The index tool requires exactly the authorized project configurations on every build/check/query, checks registration/domain, and never reads project paths from an index as instructions. Output is outside the engine, selected project workspaces, base/expanded source roots, and policy/registry inputs.

`global-index` 1.0 is disposable derived lookup, not a canonical claim store or business approval. Default selection is each checked current approved release; explicit `--include-history` adds releases from publication history. Report-bound review 0.3/0.4, complete human gates, exact review/report/work/routing bindings, frozen evidence, and publication trace consistency are required. Unsupported older review versions are not promoted; old readers remain unchanged. Candidates, pending referrals, and intake tasks are excluded from indexed claims.

Each entry has a qualified project/release/record key, original reviewed record/schema/status/events, and direct links to exact frozen record/evidence context. Projects retain their domain and descriptive ownership references. Citation links distinguish parent and investigation findings, preserve line ranges, and separately identify original bytes, representation, segment, original locator, and document extraction sidecar. Legacy file-level citations keep null segment/locator fields; no segment/event review is invented. Current/historical visibility describes release selection, not active business state, authority, or semantic supersession. Reviewed proposals and uncertainties retain their epistemic status.

Generation identity deterministically binds canonical access/registry values, config/source-scope digests, current pointer/history hashes, selected release hashes, and exact derived entries. A checked query reconstructs the entire authorized selection and rejects stale access, changed pointers/histories, unavailable inputs, altered artifacts, or fabricated index content before returning claims. Historical queries require a history build. Exact rebuilds preserve bytes; a per-output exclusive lock and atomic replacement protect normal concurrent writers. Bounds are 1,000 releases, 10,000 entries, and 16 MiB per index; query limits are 1–1,000 results, default 50. No source, configuration, policy, run, approved release, or current knowledge pointer is written. An unrelated existing output is refused. Permission metadata is not identity authentication, and the release set is not a cross-project transaction. See [ADR 005](docs/architecture/adr/005-derived-approved-release-index.md).

## 2. Inventory and manifest

A run is `projects/<id>/runs/<run-id>/`. Run ids follow the same safe identifier rule. Reusing a run id never overwrites the run.

| Artifact | Responsibility |
| --- | --- |
| `project.snapshot.json` | Exact configuration values used, with canonical-JSON hash in the manifest. |
| `source-scope.snapshot.json` | Present only when the additive source scope was configured; frozen values and exact snapshot bytes are bound by `manifest.source_scope` and the scope fingerprint. |
| `segments.snapshot.json` | Present for engine 0.4.0 runs. Frozen text spans, original locators, representation digests, and extraction issues; byte hash and segment count bound in `manifest.segment_inventory`. Published releases preserve it. |
| `manifest.json` | Frozen file identities, byte hashes, paths, source categories, provenance, issues, limits, and delta. |
| `manifest.sha256` | Byte hash of the manifest; integrity check, not a digital signature. |
| `snapshots/E-….txt` | Original text-file bytes under inert names. |
| `snapshots/E-….original.<ext>`, `.evidence.md`, `.extraction.json(.sha256)` | Document capture (`--documents`): frozen original binary, derived UTF-8 text quoted by citations, and integrity-bound extraction sidecar. |
| `packets/index.json` | Bounded packet spans, overlapping segment ids and locators when available, extraction issues, explicitly unselected files, and the selection method. |
| `packets/document-navigation.md` | Generated links to selected packets grouped by frozen document content date or undated status; this is not a business-event timeline. |
| `packets/coverage-stub.json` | Written only for a selective packet build: selected inputs/segments `deferred`, the rest `triaged_out` with the selection method. New runs use records 0.3; historical runs retain the older stub. |
| `proposals/records.json` | Candidate knowledge; never automatically approved. |
| `work/` | Assistant helper scripts and intermediate outputs (including `kb_reanchor` proposals). Bound to the review by `work_sha256` and copied into the release as audit material; never read as evidence. |
| `work/mentions.json`, `work/registry.snapshot.json` | Candidate scan of checked frozen text and its validated registry value. They are intermediate work, bound by the review's work digest; records 0.5 checks recompute the scan from them. |
| `proposals/referrals.json` | Records 0.5 proposal with one R1–R4 assessment per mention and exact, segment-bound pending referrals. The checker validates target, context, home links, and disclosure grants. |
| `review.pending.json` | Human-review form with checks false. |
| `review-report.md` | Generated pre-approval review aid with record changes, frozen quote/context links, semantic questions, fidelity gaps, triage, and every warning occurrence. Its exact bytes are bound by review 0.3 and copied to the release. |

`manifest.status` is ready only with at least one captured file and no error-severity issue; an individually empty source is a warning (`empty_source_scope`). Unsupported matched files, unreadable files, detected changes during read, invalid encoding, symlinks in traversed source trees, and exceeded limits block readiness. Explicitly excluded files do not silently count as reviewed evidence.

Raw text capture is strict UTF-8, with a UTF-8 BOM accepted. Byte snapshots retain original line endings and BOM. Citation text uses Python `splitlines()` logical lines joined with `\n`; quotes exclude a BOM and exclude a final line terminator. The demo/tests cover CRLF and BOM behavior. Text containing NUL bytes is rejected. Office/PDF, structured HTML, EML, SVG, and PNG capture require `--documents`; other media files and Google shortcut files are not converted. Without `--documents`, HTML remains raw UTF-8 text and EML is unsupported. CSV stays raw text by default, even with `--documents`; `--csv-representation structured` explicitly opts in to derived row evidence. `--csv-header first-row` declares, rather than infers, labels from the first record. Both choices and the adapter version are frozen in `manifest.documents`, so a changed choice makes deltas incomparable without changing or invalidating an earlier run.

File reads detect ordinary concurrent changes during that individual read. They do not provide a transaction across files or an adversarial-filesystem sandbox. File ordering and identities are deterministic; timestamps/run ids make whole manifests intentionally non-identical across separate runs.

### Time and ordering

Every run records a monotonically increasing `sequence` and its capture `created_at`; ordering decisions (baseline choice, re-anchoring direction, publication) compare the pair `(sequence, created_at)`. A capture attempt while the machine clock is earlier than an existing run is refused (clock regression). A delta against an older run while a newer run exists is allowed but carries a `baseline_not_latest` warning, because it re-reports already-seen changes as `added`.

Each manifest file entry carries an optional `temporal` block separating content time from file-system time: `content_date` with `value`, `basis`, and `precision`, plus an informational `observed_mtime`. `content_date` precedence: `origin.content_date` from provenance (human-asserted) beats deterministic filename date patterns (for example Gemini notes `YYYY_MM_DD HH_MM GMT±HH_MM`, `YYYY-MM-DD`, `YYYY_MM_DD`), which beat nothing — a file with no dateable name has no content date. Content date is best-effort metadata, never an authority signal: a file whose name carries an old date is still `added` if captured later; `added` means newly captured, not newly written.

Provenance is bound to the bytes it describes: `origin.sha256` must match the file's hash. Different bytes under unchanged provenance raise a `provenance_not_updated` warning; provenance timestamps later than the capture (beyond a small clock-skew allowance) block readiness (`provenance_timestamp_in_future`).

### Identities

```text
canonical_json = UTF-8 JSON, sorted keys, compact separators, no NaN/Infinity
logical_id = F- + first 24 hex characters of SHA256(canonical_json([project_id, source_id, relative_path]))
legacy/text evidence_id = E- + first 24 hex characters of SHA256(canonical_json([project_id, source_id, relative_path, original_sha256]))
0.4 document evidence_id = E- + first 24 hex characters of SHA256(canonical_json([project_id, source_id, relative_path, original_sha256, representation_identity_sha256]))
```

Logical ids are stable for the same source/path within a project. New document evidence ids also change when derived text, parser versions, extraction options, locators, or extraction issues change under identical original bytes. The v1 representation digest binds those values; raw text uses a `source_text` representation and retains its historical evidence-id formula. Every 0.4 file has a representation field. A segment id binds its parent evidence id, representation digest, original locator, derived line span, and line hash. Renames/source-id changes are new logical identities; an unambiguous same-source rename requires identical original bytes and representation before the delta records `renamed`. Re-anchoring still requires exact quotes and review of changed context. Identity collisions/duplicates inside a run are rejected. See [ADR 002](docs/architecture/adr/002-quotable-representation-and-segments.md).

Provenance is optional source metadata from `config/source-provenance.json`, preserved in the manifest. Missing metadata is null, not guessed. The optional `origin.authorship` (`human`, `ai_generated`, `mixed`, `unknown`) records who wrote the exported content. `ai_generated` or `mixed`, or a non-repository file name marking a machine summary (for example "Notes by Gemini") when authorship is not stated, raises an `ai_generated_source` warning. Provenance changes count as modifications in comparable deltas even when evidence bytes remain identical.

### Delta rules

Comparable deltas require a ready prior run of the same project, a complete current capture, and the same scope fingerprint (configured sources, resolved roots, patterns, supported extensions, limits, document policy, and the version of the engine that captured the run). From engine 0.2.1, `manifest.capture_policy` freezes the supported text extensions and secret exclusion patterns with policy version `1`; configured exclusions remain in `project.snapshot.json`, limits remain in the manifest, and document extensions, extraction options, budgets, timeout, and adapter version remain in `manifest.documents` when enabled. From engine 0.3.0, an optional expanded source scope is frozen separately and bound to the fingerprint. Engine 0.4.0 additionally freezes representation and segment identity. The checker verifies 0.1.0/0.2.0 manifests with fixed historical extension and secret-pattern lists, never the current defaults. Changing a policy, source scope, or engine version makes the delta explicitly incomparable while each intact run remains verifiable. Within 0.4.0, a changed representation is a modified logical file even if the original bytes are unchanged. The lists are added, modified, removed, and unchanged logical ids. On a first run, captured files are listed as added.

A changed scope or incomplete current inventory yields `compatible: false`, empty comparison lists, and an explicit warning. A missing capture is not evidence that a source file was deleted. A delta is an input-change report, not an automatic decision about which knowledge claims remain valid.

## 3. Records and coverage

`records.json` contains schema_version, project_id, run_id, coverage, and records. It is a **complete candidate snapshot for the selected project scope**, not an append/merge patch.

Record ids use `REQ-001`, `DEC-001`, `UNC-001`, or `INV-001` style (3–6 digits). Kinds are requirement, decision, uncertainty, and investigation. All records include title, statement, epistemic_status, evidence, relations, open_questions, and investigation (null except for an investigation record).

Epistemic status is observed, interpretation, proposal, or unresolved. An observed decision means the source explicitly states a decision; it does not establish that its speaker had authority. An uncertainty must be unresolved and contain an open question. Local review status is separate from this semantic status.

Every evidence item has evidence_id, start_line, end_line, and quote. Lines are 1-based and inclusive. Quotes must match the entire referenced normalized line span exactly. Existence of a matching quote does not establish that it supports the accompanying interpretation.

Records 0.3 add `segment_id` and `representation_sha256` to every citation and `segment_coverage` for every frozen segment. A citation must fit inside one segment; a packet split does not split the segment. Segment dispositions use the same names and reading standard as file coverage. File `triaged_out`, `reviewed_no_record`, or `deferred` requires the same disposition for each child segment; a used file may contain a mix of cited, fully reviewed, triaged, and deferred segments. The Stage 2 gate rejects deferred segments in a 0.3 candidate. Records 0.1/0.2 remain valid file-level candidates and cannot claim segment-level review. HTML/EML adapter 0.3.0 introduced structural types such as heading, code, table cell, email quote, and attachment metadata. Adapter 0.4.0 adds table-row/header/caption spans; HTML data rows repeat source cell values with positional headers, an optional caption, and the preceding heading, while structured CSV rows preserve exact decoded strings with optional operator-declared first-row labels. Merged HTML cells suppress header alignment and raise a warning. These structural types do not infer entity relationships, state transitions, dates, units, business status, or visual meaning. Older document spans remain `unclassified`. Issue rows show unavailable content without creating a citable quote. Review 0.3 binds exact records bytes, warning acknowledgements, and the generated report.

Adapter 0.5.0 adds `diagram_label`, `diagram_caption`, `vector_geometry`, `image_region`, `image_annotation`, and `embedded_asset` segment types. SVG text/attributes and PNG dimensions/metadata are source structure; PNG IDAT pixels are not decoded, SVG rendering is not verified, and embedded image meaning remains unavailable. A quote from these derived segments proves only the captured source text, not visibility, legibility, image content, relationship direction/cardinality, or agreement with a caption. The original bytes remain frozen for [manual fidelity comparison](docs/VISUAL_FIDELITY_REVIEW.md); the warning/segment integrity checks do not certify visual fidelity.

Adapter 0.6.0 additionally validates PNG IDAT zlib and packed scanline/filter structure within the worker budget. It does not reconstruct pixel values, identify visual regions beyond the canvas, or perform OCR. The changed adapter version is frozen in `manifest.documents`; historical 0.5.0 evidence remains verifiable and a cross-version delta is incomparable.

Adapter 0.7.0 captures DOCX comments as citable `unclassified` metadata and paragraph/table spans. Locators identify the actual relationship-selected comment part and recorded comment ID. Metadata preserves recorded author, initials, raw `date`, last-paragraph ID, optional durable ID and raw `date_utc`; these are document annotations, not authenticated identities, business event dates, or approval. Reply parents come only from validated extended-comment links to the last paragraph. A matching `commentEx` supplies the current per-comment `resolved` flag: omitted `done` defaults to false; absent extended metadata leaves the flag and root/reply classification unknown. Replies do not inherit their parent's flag. `status_basis`, raw flags and metadata-part names retain the derivation. `resolved_at` is always null because no supported field establishes resolution time or history. Explicit anchor markers receive paragraph/node locators; target text is not inferred.

Modern follow-up placeholders retain metadata but their bodies remain unavailable. Unsupported extensions, text-bearing inline wrappers, unlinked comment parts and missing/ambiguous targets produce explicit gaps. Duplicate/ambiguous IDs, dangling/cyclic parents, malformed supported metadata and exceeded budgets block extraction without accepting truncated output. Date strings are validated against the supported four-digit-year ISO date-time profile and retain their spelling; timezone-free `date` gains no timezone, while `dateUtc` has UTC meaning by its attribute definition. Comment bodies use the existing paragraph/table walker and keep its visual/layout limitations. Frozen 0.6.2 artifacts remain unchanged and verifiable; new captures use 0.7.0 and cross-version deltas remain incomparable. See [ADR 007](docs/architecture/adr/007-docx-comment-evidence.md).

Records 0.4 add a required `events` array to each record while retaining records 0.3 segment-bound evidence and coverage. An event has a stable `EVT-...` id, statement, `evidence_refs` pointing to exact citations on its parent record, and an `event_date`; `effective_date` is optional. Date status is `known`, `approximate`, `unknown`, or `conflicting`. Known/approximate dates carry a value and precision (`year`, `month`, `day`, `minute`, or `second`); an optional same-precision `end` is an inclusive range. Timestamps include an offset, so a date-only value is never interpreted as an event at midnight. Approximate, unknown, and conflicting dates require explanatory notes; conflicts retain separately cited alternatives. `relative_to_anchor` requires a cited anchor value and derivation note. The checker verifies syntax, reference bounds, interval order, and variant consistency, not the claim's semantic support. Re-anchoring remaps event citation indexes and drops an event if any required support disappears, marking its record degraded. Older records remain readable without event claims. See [ADR 003](docs/architecture/adr/003-evidence-linked-event-dates.md).

Records 0.5 retain events and segment coverage and require a `cross_project` array on every record. Each link gives a registered target id, reason, and nullable target-record reference; a non-null reference is not resolved against another project's changing release. Accompanying `proposals/referrals.json` v1.0 gives exactly one assessed R1/R2/R3/R4 class and disposition for every verified mention. R1 constrains home and needs a cited home record; R2 describes the other project only and cannot be cited as home knowledge; R3 is context/name-drop and may be dismissed with reason or held unresolved; R4 concerns a shared component but ownership still needs human judgment. Referred items require an exact quote inside one frozen segment, target, rationale, related home ids, exact source-path capture hint, and `pending_target_review` status. A file or segment can be used for a home record while a different line is referred. Coverage remains exhaustive. A matching frozen registry 1.1 grant is necessary for the destination/source path; same-domain membership alone is insufficient. Checker success does not establish semantic class, per-segment disclosure safety, or target acceptance. Re-anchoring records 0.5 stops for fresh routing review rather than carrying stale cross-project claims.

Relations are depends_on, implements, conflicts_with, clarifies, investigates, or supersedes. Targets must be records in the same candidate set. Self-links, duplicate edges, and dangling ids are rejected. Direction is meaningful: `A depends_on B` is not the reverse. Do not add relationships simply to make the graph look connected.

Coverage must name every manifest evidence id exactly once, with one disposition:

| Disposition | Meaning |
| --- | --- |
| `used` | Actually cited by a record (checked). |
| `reviewed_no_record` | Read **in full**; nothing worth recording. |
| `triaged_out` | Deliberately not read in full because it is outside the pilot question. Requires records 0.2 and a nonempty `method` such as `path_out_of_question_scope:<globs>` or `keyword_scan:<terms>`. `method` is not allowed on any other disposition. |
| `deferred` | Not (yet) fully processed. |

These are declarations reviewed by a human, not observed reading activity. Stage 2 publication refuses `deferred`. It accepts `triaged_out` only when the review explicitly acknowledges the triaged ids, and the release index shows how much was triaged.

A decision must cite at least one non-repository source. Code shows an implementation observation, not product intent; code-only observations belong in an investigation finding or a requirement-vs-implementation uncertainty.

An investigation additionally includes a question, finite evidence-id scope, method, findings with their own citations, limitations, and next_action. Every investigation citation must belong to its declared scope. Limitations must be nonempty. Static inspection is not runtime verification.

The Stage 2 milestone (at least one of each record kind and at least one relation) is reported as `stage2_milestone` in the checker output; it is **not** a gate, because a quota gate rewards fabricating a category. The `--stage2` gate keeps the real blockers: integrity, exact quotes, links, no deferred coverage, and at least one record (an empty snapshot would retire the whole current release).

The checker also emits `semantic_hints`, which are reviewer prompts and never gates: `single_line_citations` (every citation of a record is one line), `decision_quote_pending_language` (a decision quote contains propuesto, pendiente, a validar, TBD, proposed, pending, and similar), `decision_only_ai_sourced` (an observed decision rests only on AI-generated summaries), and `triaged_coverage`.

## 4. Human review

Review 0.3 continues for unrouted candidates. Review 0.4 is required for records 0.5 and binds the approval to the exact manifest byte hash, records byte hash, referral bytes, frozen mention bytes, canonical registry digest, current previous release id, full record-id set, and removed prior record ids. Both current review versions also bind:

- `warning_summary`: written by `--prepare`; a digest of every `(code, source_id, path)` warning occurrence plus counts per code. Publication recomputes it from the manifest.
- `acknowledged_warnings`: filled in by the human as `{code: count}`; it must equal `warning_summary.counts`, so the reviewer acknowledges volume ("262 × repository_revision_unrecorded"), not just a code.
- `triaged_evidence_ids`: written by `--prepare` from the `triaged_out` coverage; `triage_acknowledged` must be true when it is nonempty.
- `triaged_segment_ids`: written by `--prepare` from `triaged_out` segment coverage; `segment_triage_acknowledged` must be true when it is nonempty. A used file can still contain an unread visual or other segment.
- `work_sha256`: written by `--prepare`; a digest of every `(path, sha256, bytes)` in the run's `work/` folder (`.DS_Store` ignored; symlinks, non-POSIX names, more than 2,000 files, more than 64 MiB in total, or more than 16 MiB per file are rejected). Publication refuses a changed `work/` and copies exactly the bytes it hashed.
- `review_report_sha256`: SHA-256 of the generated `review-report.md`. Publication checks both its bytes and a fresh render against the checked candidate, frozen evidence, warnings, and current prior release. A missing or edited report blocks publication.

All five general checks must be true: evidence support, explicit conflicts, source authority, privacy, and snapshot completeness. Review 0.4 adds `cross_project_checked`; the reviewer must confirm every assessment, source context, destination grant, and disclosure scope. Reviews 0.1 and 0.2 remain readable through frozen legacy schemas; neither can newly publish. Prepare a new review with the current engine instead.

Reviewer, timestamp with timezone, and decision=approve are required for publication. `--prepare` stamps `prepared_at`; `reviewed_at` must follow both the capture and `prepared_at` and must not be in the future, so a review cannot be backdated. `source_authority_checked` can mean that an authority gap is accurately documented as unresolved; it must not mean an invented decision owner. An AI-generated semantic review is not this approval. The CLI flag is a human confirmation convention, not identity authentication.

## 5. Publication and generated views

Publication writes a new `knowledge/approved/<run-id>/` directory with records, review, the exact bound review report, manifest, configuration snapshot, evidence snapshots, the run's `work/` folder (symlinks rejected), checker report, individual record pages, a generated Mermaid map, `open-questions.md`, `by-code.md`, and, for event-aware records 0.4/0.5, `timeline.md`. Records 0.5 additionally copy exact `referrals.json` and generate `outbox.md` only after the human approval gate; the outbox is pending target review, never automatic target import. A previous release also produces `changes-since-<previous-run>.md`, including event changes. Only then does publication update `knowledge/approved/CURRENT.json`. It checks the previous pointer and hash bindings while holding a local publication lock. The timeline uses reviewed event dates, separates unknown/conflicting dates, and displays effective dates without inferring active state, supersession, or authority. Approximate and overlapping dates receive only a deterministic display order.

Publishing a run whose `(sequence, created_at)` is older than the current release is refused unless the review sets `rollback_reason` — restoring an older snapshot is a deliberate act (for example reverting a bad export), never an accident. Every publication appends one line to the append-only `knowledge/approved/HISTORY.jsonl` (run id, sequence, capture and review times, reviewer, previous release id, rollback reason) before `CURRENT.json` is swapped, so the pointer never moves without a trace.

Old releases are not overwritten. Removing a record from the new complete snapshot requires an explicit matching removal list; historical releases retain it. `CURRENT.json` is the current selection, not an aggregate of every release. Uncertainties and proposals can remain in an approved knowledge release without becoming approved business changes.

Markdown/Mermaid views are derived, escaped representations. Edit proposed structured records, not generated views. The map generator validates its record/edge inputs and escapes labels; renderer behavior still needs verification in the user's chosen VS Code extension.
