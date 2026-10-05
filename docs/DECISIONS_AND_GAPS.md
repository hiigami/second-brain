# Recovery, design decisions, and remaining gaps

Prepared 2026-09-30 for the Work Second Brain project.

This document retains engine decisions and synthetic validation history. Private project runs, source excerpts, and business findings are omitted.

## Conversation coverage and evidence limits

The project conversation context and retrieved conversation summaries were reviewed for:

| Conversation | Date | Relevant recovered content |
| --- | --- | --- |
| Second Brain Setup | 2026-09-29 | Google Workspace-centered knowledge system; source-fidelity importer first; first connected project bundle second; Studio intake later. |
| Improve GLM Coding Performance | 2026-09-29 | Fixed GLM-5.3-flash and default effort; existing copied instructions/skills do not by themselves satisfy the user's quality needs. |
| GLM 53 Flash Setup | 2026-09-30 | Global engine and per-project workspace; external sources; accepted project.json v0.1; next piece was deterministic inventory plus manifest. |

The visible acceptance was: “Freeze this as out project.json v0.1 and proceed with the next design piece.” The retrieved material established the field shape and core paths, but did not expose a complete original chat export or every original example value. No relevant attached/live project source documents were available through the file search used for this reconstruction. Unrelated Library results were not used as Stage 2 authority.

Accordingly, this bundle does **not** claim a verbatim or exhaustive reconstruction. It preserves recovered decisions and labels new implementation details below. Do not treat the synthetic examples or default values as recovered client facts.

## Preserved decisions and constraints

| Item | Treatment in this bundle |
| --- | --- |
| `project.json` v0.1 accepted | Retained field shape: schema_version; project id/name/description; individually identified sources with id/type/path/include/exclude; global_exclude; knowledge path/approved; runs path. |
| Separate shared engine and project workspaces | Root instructions/tools/skills; `projects/<id>/config/project.json`, `runs/`, `knowledge/approved/`. |
| Sources remain external | Enforced external, non-overlapping source roots. Local snapshots never replace their upstream owners. |
| Governance stays out of project.json | Root instructions and policy, plus optional project policy. No authority flags added to the frozen config. |
| Stage 2 first connected bundle | Requirements, decisions, uncertainties, evidence links, one project map, one bounded code/schema investigation. |
| Tool/model constraints | Existing approved GLM-5.3-flash at fixed default effort; optional limited Claude; Google tools and VS Code; no Obsidian/Notion. |
| Later-stage boundary | No Workspace Studio task promotion, writeback, live sync, media processing, or scale-out orchestration. |
| Next unfinished design piece | Implemented deterministic `kb_inventory.py` and the new `manifest.json` v0.1 contract. |

The recovered global exclusion directories were `.git`, `node_modules`, `.venv`, `venv`, `build`, `dist`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.idea`, and `.vscode`. They are present in the starter. A separate code-level sensitive-filename denylist is a new defensive implementation choice.

## Newly supplied in this request, not previously frozen

The exact manifest/record/review schemas, SHA-256 identity formulas, local publication layout, provenance sidecar contract, UTF-8-only support boundary, packet size, source budget defaults, CLI flags, and executable tests are implementation proposals delivered as version 0.1.0. Their code is runnable; their design was not separately accepted in the earlier conversation.

Important new choices are deliberately conservative: freeze exact bytes rather than hash live files only; fail on partial eligible-file capture; keep unchanged bytes distinguishable from changed provenance; never equate a scope change/inaccessible source with deletion; bind human review to exact records; publish immutable complete snapshots with removal disclosure.

The prior project discussion used the acronym “OKF” in its high-level bundle description, but no definitive format specification was recovered. This bundle therefore does not claim conformance to an unspecified OKF standard. Its concrete Markdown/JSON contracts are documented directly.

## Remaining questions and local prerequisites

The user's real local source paths, Stage 1 importer implementation/status, export fidelity, project-specific decision owners, company retention rules, work-assistant skill-discovery behavior, and Mermaid extension version were not established. The initializer/template make these local setup items visible rather than guessing them.

Model extraction quality and benefit relative to a prior Claude analysis require a real, bounded pilot. No GLM or Claude run was performed to produce the synthetic example or the validation results. The bundle's automated tests assess the tools and contracts, not model reasoning quality.

## Exact next step

The next design piece is no longer just a proposal: inventory, manifest, and downstream local checks are implemented. The current next step is in `docs/ANALYSIS_AND_IMPROVEMENT_PLAN.md`, Phase 4: select an authorized bounded pilot question, configure its scope, and capture a new run.

## Decision note: native document evidence integration (2026-09-30)

Implements `docs/INTEGRATE_WITH_STAGE2.md`. Adds `.docx`, `.pdf`, `.xlsx`, `.pptx`, and opted-in legacy `.ppt` as evidence via `tools/kb_document_extractors.py`, which stays a component (never rewritten) while the engine gains capture/check/packet/publish integration. Decisions recorded here govern that patch series:

- **Manifest contract:** additive-optional under `schema_version: "0.1"`. Each file entry may carry a new optional `document` object (derived-text hash/bytes/lines, snapshot paths, metadata hash, adapter version, parsers, media type, segment count, status, options digest). Old manifests without it remain valid and read identically; the meaning of existing fields is unchanged. `project.json` stays frozen at v0.1.
- **Artifact layout:** per document, the run gains `snapshots/<eid>.original.<ext>` (frozen binary; `sha256` field keeps the **original** hash), `snapshots/<eid>.evidence.md` (derived UTF-8 text; hashed separately), and `snapshots/<eid>.extraction.json` + `.sha256` (metadata incl. the full segment map). Existing `snapshots/<eid>.txt` remains text-file-only, so the distinction is physically visible. The segment map lives only in the sidecar (integrity-bound by the metadata hash); the manifest carries just `segment_count`.
- **CSV routing:** `.csv` stays on the text path by default (current behavior unchanged). Strict spreadsheet parsing of CSV via the extractor is available later as an explicit opt-in recorded in the policy digest.
- **Option surface:** CLI flags only for the pilot (`--documents`, `--allow-legacy-ppt`, `--soffice`). A `documents-policy.json` is deferred until repeated runs need identical settings; if added later it must enter `scope_sha256`.
- **Delta semantics:** for document entries, `delta.modified` triggers when the original hash, derived-text hash, or extraction adapter/policy versions change; `scope_sha256` gains the document/policy component so old-vs-new scope comparisons degrade explicitly to `scope_changed`.
- **Known pre-existing issue (user decision 2026-09-30):** `tools/kb_verify_bundle.py` fails at commit `ccd31c1` on a clean tree — `tools/kb_check.py` and `tools/kb_inventory.py` no longer match the sealed `BUNDLE_FILES.json`/`SHA256SUMS` (the packager edited them after sealing). Decision: leave the bundle hash check failing as a documented known issue; the working gate for this patch series is `python3 -m unittest discover -s tests -v`. Do not re-seal the distribution manifest to make the gate pass.
- **Human checkpoints:** contract files (`schemas/`, engine tools) are touched only under the explicit authorization of `docs/INTEGRATE_WITH_STAGE2.md`, with review stops after each patch. The full test matrix lands in `tests/test_document_integration.py` per the plan in `.agents/plans/2026-09-30-16-54-integrate-document-extractors.md`.

- **Series completion (2026-09-30):** Patches 1-5 implemented and gated: capture worker integration with timeout/process-group kill; `kb_check` document validation (both hashes, metadata sidecar, layout, raw-hash-reuse rejection, options binding); packet NOTICE/locator framing; publish release copies and view links; full `tests/test_document_integration.py` matrix (multi-format end-to-end, tamper cases, corrupt-document blocking, fidelity-warning surfacing, delta/policy semantics). Suite: 163 tests OK (1 skipped: legacy `.ppt` LibreOffice test, opt-in via `KB_TEST_LEGACY_PPT=1`). The `kb_verify_bundle.py` known issue above still stands by user decision; the working gate remains the unittest suite.

## Decision note: engine 0.2.0 workflow hardening (2026-10-01)

Implements Phases 1–3 and the tooling of Phase 5 of `docs/ANALYSIS_AND_IMPROVEMENT_PLAN.md`.

- **Bundle sealing retired (reverses the 2026-09-30 known-issue decision).** Git now provides engine integrity. `kb_verify_bundle.py`, `SHA256SUMS`, and `BUNDLE_FILES.json` are no longer part of the workflow or the docs; a check that always fails teaches people to ignore checks. The files themselves are left for the operator to delete.
- **Demos removed from the workflow.** The synthetic sources, the project config, and the legacy v0.1 run moved to `tests/fixtures/`; `synthetic_records()` moved to `tests/helpers.py`. `kb_demo.py`, `projects/demo/`, and `projects/inventory-search/` are no longer referenced and are left for the operator to delete.
- **Runtime documented as Python 3.14 via uv** with the dependencies in `pyproject.toml`; `requirements-documents.txt` references were removed.
- **`TOOL_VERSION` 0.2.0.** The checker rebuilds `scope_sha256` with the run's recorded `tool_version`, so legacy 0.1.0 runs still verify. A 0.1.0 baseline is not delta-comparable with a 0.2.0 capture (`scope_changed`), which is correct because capture behavior changed.
- **Strict schema validation.** `validate_schema` rejects any keyword it does not implement and now enforces `additionalProperties` given as a schema; previously the document `parsers` map constraint was silently ignored.
- **Records 0.2 / review 0.2.** Added the `triaged_out` disposition with a required `method`. The review acknowledges warnings per occurrence count, carries the triaged ids with `triage_acknowledged`, and binds a digest of every warning occurrence. 0.1 records still check. 0.1 reviews validate against `schemas/legacy/` but cannot publish.
- **Provenance-aware rules.** Optional `origin.authorship` and an `ai_generated_source` warning, also raised from file names such as "Notes by Gemini". Decisions must cite at least one non-repository source; this is a hard error and applies to 0.1 records too. Checker success does not replace semantic support or human approval.
- **Quota → report.** One-of-each-kind plus a relation is now `stage2_milestone` in the report, not a gate. `semantic_hints` flag single-line citations, pending language in decision quotes, and decisions resting only on AI summaries.
- **`work/` folder.** New runs get `work/` for assistant helpers; publication copies it into the release. Run-local helper outputs belong in this audit trail; root-level assistant scratch work is excluded from Git.
- **Between-run tooling.** `kb_reanchor.py` (exact-quote re-anchoring with a moved/vanished report), `kb_packet.py --select-glob/--grep` with a `triaged_out` coverage stub, and generated `open-questions.md`, `by-code.md`, and `changes-since-<prev>.md` views at publication.
- **One skill source.** `.agents/skills` is canonical; `kb_sync_skills.py` mirrors it, and a test fails on drift.
- **Independent review fixes (2026-10-01).**
  - The review now binds `work/` through `work_sha256`, and publication copies exactly the hashed bytes.
  - `--stage2` requires at least one record.
  - `kb_reanchor` compares the quotable text (derived text for documents) rather than the original bytes, and carries uncited coverage only from an approved release. Coverage declarations from an unapproved run return as `deferred` for fresh assessment.
  - `kb_reanchor` also rejects previous coverage that names unknown evidence.
- **Not done:**
  - operator-owned backup, recovery, configuration, and human review before a real pilot;
  - packaging the tools into `src/second_brain` with entry points (Phase 2, step 5);
  - scoping an authorized real pilot (Phase 4, human-owned);
  - cross-project mentions (Phase 6, deferred until a second project exists).

**Patch B hygiene update (2026-10-02):** The files left for operator deletion in the 0.2.0 note (`kb_demo.py`, `kb_verify_bundle.py`, `SHA256SUMS`, `BUNDLE_FILES.json`) and obsolete prompt project configs were removed under the authorized engine-development task. The sealed legacy v0.1 test fixture and historical validation logs were preserved. Skill mirrors now match `.agents/skills`; a locked uv environment runs the full synthetic suite (222 tests OK, 1 optional LibreOffice test skipped). The operator still owns real-project configuration, backups, review, and publication; packaging entry points remain separate work.

**Patch C source-registration decision (2026-10-03):** [ADR 001](architecture/adr/001-additive-source-scope.md) records an optional `source-scope.json` v1.0 sidecar for data, analysis, and policy roots while `project.json` v0.1 stays frozen. Every new run freezes and verifies the sidecar; changed scope is incomparable across runs. Engine 0.3.0 passed 9 focused tests and the full synthetic suite (231 tests, 1 optional LibreOffice skip). A project still needs at least one legacy source under v0.1, and classification inside mixed-content files awaits Patch D. No real run or approval was changed.

**Patch D representation/segment decision (2026-10-03):** [ADR 002](architecture/adr/002-quotable-representation-and-segments.md) records engine 0.4.0 document evidence ids bound to the frozen derived representation, `segments.snapshot.json` v1.0, and opt-in records 0.3 segment citations/coverage. Old run readers and file-level records remain available. The DOCX adapter now identifies embedded image parts as unavailable without interpreting pixels. The focused suite passed 8 tests, document integration passed 12, and the full synthetic suite passed 239 tests with 1 optional LibreOffice skip through `uv run --locked --no-sync`. Offline `uv sync` could not rebuild the editable package because `uv-build` was missing from the local cache; dependency pins were unchanged. No real run, review, or approval was changed. Patch E is next.

**Authorized review fixes and packaging (2026-10-04):** Adapter 0.6.1 fixes inline qualifiers, line breaks, and unreliable merged-table header mappings; adapter 0.6.2 suppresses image/resource evidence under excluded HTML content. The report exposes unchanged claims, complete event/date qualifiers, numbered citations, and stable links to prior evidence. Runtime modules and byte-identical current/legacy schemas are now packaged under `src/second_brain/`; `second-brain` dispatches the existing operator commands and `tools/kb_*.py` remain compatibility entry points. Installed commands require explicit workspace roots where needed, and workers use safe-path startup. The declared build backend was fetched through uv for a local wheel build; dependency declarations and lockfile were unchanged. Built-wheel tests run outside the checkout without installing the wheel. See `VALIDATION_REPORT.md` for executed checks. The [visual catalog](VISUAL_REFERENCE_CASES.md) and [review template](../templates/VISUAL_CAPABILITY_REVIEW.md) make the remaining GLM/human assessment concrete; they do not complete visual acceptance or any real-project pilot.

## Decision note: temporal integrity for runs and publications (2026-10-01)

Implements the fixes from `docs/TEMPORAL_INTEGRITY_REVIEW.md`. The engine treated "captured last" as "written last" and had no defense against out-of-order publications or backdated reviews; this patch separates content time from capture time and makes the run history explicit. All changes are additive under manifest v0.1; `project.json` stays frozen.

- **Run ordering.** `kb_inventory.py` stamps each run with a monotonically increasing `sequence` (one plus the project's highest existing sequence; blocked runs count too, since they consumed one). Ordering everywhere compares `(sequence, created_at)`. A capture while the machine clock is earlier than the newest existing run is refused (clock regression), and a baseline captured after this run is refused. Deltas against a non-latest baseline are allowed but warn `baseline_not_latest`.
- **Content dates.** Each manifest file entry may carry a `temporal` block: `content_date` (`value`/`basis`/`precision`, from provenance `origin.content_date`, else deterministic filename patterns such as Gemini exports), plus informational `observed_mtime`. Content date is metadata, never authority: an old-named file captured now is still `added`.
- **Provenance binding.** `origin.sha256` must match the file's hash (`provenance_not_updated` warning otherwise); provenance timestamps in the future beyond a small skew allowance block readiness (`provenance_timestamp_in_future`).
- **Rename recognition.** Within one source, a removed/added pair with identical bytes and quotable text is recorded in `delta.renamed` when unambiguous; `kb_reanchor.py` follows renames so citations carry over. Rename-plus-edit stays delete + add.
- **Review timing.** `--prepare` stamps `prepared_at`; publication requires `reviewed_at` to follow both the capture and `prepared_at` (no backdating).
- **Rollback gate and history.** Publishing a run older than the current release is refused unless the review declares `rollback_reason`. Every publication appends one line to the append-only `knowledge/approved/HISTORY.jsonl` before `CURRENT.json` is swapped.
- **Contract/docs sync.** `CONTRACT.md` gained the "Time and ordering" section and the rename/`prepared_at`/rollback/HISTORY prose; `docs/ARCHITECTURE.md` documents the new surfaces. Non-blocking review items (contract text, defensive rename lookup in `kb_reanchor.py`) closed 2026-10-01.
- **Gate:** full unittest suite 208 tests OK (1 skipped, legacy `.ppt`), including `tests/test_temporal.py`; rename-follow and degraded-record probes (`validation/temporal-2026-10-01/`) reproduce unchanged after the doc/polish pass.
