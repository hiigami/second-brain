# Architecture — implemented Stage 2 subset

```text
Authoritative Google/client sources and repositories
        │ approved Stage 1 local representations (outside this bundle's importer scope)
        ▼
External local source directories
        │ project.json v0.1 + optional source-scope.json define scope
        │ no authority policy in config
        ▼
Deterministic inventory + exact-byte snapshots + manifest
        │ frozen quotable representations and segment locators
        │ bounded line-numbered packets
        ▼
Existing work coding assistant: GLM-5.3-flash, fixed default effort
        │ serial extract / reconcile / bounded investigation / verify
        ▼
Run-local candidate records, semantic-review notes, and work/ audit material
        │ deterministic structural checks; explicit human review
        ▼
Immutable reviewed local knowledge snapshot + generated views
        │ kb_reanchor carries records into the next run by exact quote
```

## Implemented boundaries

The shared engine contains instructions, schemas, prompts, skills, local tools, tests, and documentation. Project workspaces hold configuration, run evidence/proposals, and approved derived knowledge. Input sources stay external. The only automatically replaced durable pointer is the selected project's approved/CURRENT.json after successful explicit publication, and each publication first appends one line to the append-only approved/HISTORY.jsonl; a rollback to an older capture is refused unless the review declares a `rollback_reason`.

The source graph and project map describe relationships between knowledge records. They are not an execution graph or graph database. Records may remain disconnected when no justified relationship exists; a visually connected map is not more important than accurate evidence.

Python handles discovery, byte hashes, line budgets, integrity, link consistency, and publication. The model handles bounded interpretation, source reconciliation, and analysis. A human handles project-specific authority and approval. These responsibilities are intentionally separate.

For engine 0.3.0, `project.json` retains its five source types. Optional `config/source-scope.json` v1.0 registers data, analysis, and policy roots; inventory freezes it as `source-scope.snapshot.json` and binds the snapshot hash and source values in the manifest and scope fingerprint. The checker verifies that frozen copy without relying on live configuration, and publication preserves it. Changed registration makes run deltas incomparable. The sidecar does not confer authority or classify individual passages. See [ADR 001](architecture/adr/001-additive-source-scope.md).

Engine 0.4.0 binds document evidence ids to the actual derived representation, including parser versions, options, locators, and extraction issues. Every new run freezes `segments.snapshot.json`, which maps citable text spans to their original locators and lists unavailable extraction material separately. Records 0.3 bind quotes and coverage to these segments; older records retain file-level semantics. The checker reconstructs the segment inventory from frozen artifacts, packets expose segment ids, re-anchoring keeps only quotes that still fit a new segment, and publication preserves the sidecar. See [ADR 002](architecture/adr/002-quotable-representation-and-segments.md).

Patch M's `tools/kb_referrals.py` adds an operator-invoked target intake boundary after origin publication. Explicit approved origin configurations, frozen routing review, and live registry 1.1 grants feed a versioned target `knowledge/referral-intake.json` ledger outside approved knowledge. Human intake decisions create only capture/reconciliation proposals; full-file scope or a reviewed scoped export needs separate authorization. The target uses its own capture, evidence ids, checks, review, and publication. Corrections/withdrawals create review history, and target links compare original bytes, representations, and locators without rewriting either project's approved release. The ledger is an additional atomically replaced audit artifact, protected by its own lock; it is not a knowledge pointer or global claim store. See [ADR 004](architecture/adr/004-reviewed-target-intake.md).

Patch N's `tools/kb_index.py` builds an explicitly authorized derived JSON lookup outside the engine, project workspaces, and sources. An `index-access` 1.0 file names the whole-release project scope, information domain, authorizing operator/time/reason, and reviewed output destination; registry domains and referral grants do not grant indexing permission. Patch M's public read-only release validators plus publication trace checks establish input bindings. Generation identity records canonical access/registry/config/scope values, current pointers, histories, exact selected releases, and record/evidence projections. Current/history remain separate, local record ids remain qualified, and proposal/uncertainty/date semantics are preserved. Queries reconstruct the authorized release selection before returning results, so a cached index alone cannot establish fresh authorization or provenance. The index has its own lock/atomic replacement and never changes a canonical release or pointer. It is a reproducible derived selection, not a cross-project transaction or second authority. See [ADR 005](architecture/adr/005-derived-approved-release-index.md).

## Document evidence (optional, opt-in)

When `kb_inventory.py` runs with `--documents`, `.docx`/`.pdf`/`.xlsx`/`.pptx`/`.html`/`.eml`/`.svg`/`.png` (legacy `.ppt` only with explicit opt-in) are captured as three separately hashed artifacts: original bytes, derived UTF-8 evidence text, and an integrity-bound `extraction.json` sidecar carrying parser versions and locators. Extraction runs in a worker subprocess with a wall-clock timeout. HTML/EML adapter 0.3.0 uses only inert standard-library parsing: HTML headings, cells, code and text and EML headers, body variants, quote context and attachment inventory become structural segments. JavaScript is never run, links are never fetched, and attachment content is never silently treated as extracted. Parser budgets and explicit unavailable issues preserve this boundary. The extractors (`tools/kb_document_extractors.py`) remain a standalone component; the manifest contract stays additively versioned at v0.1 (it later also gained optional `provenance.authorship`, then the temporal fields of `docs/TEMPORAL_INTEGRITY_REVIEW.md`: per-file `temporal.content_date`/`observed_mtime`, provenance `origin.sha256` binding, run `sequence`, and `delta.renamed`) (see the decision note in `docs/DECISIONS_AND_GAPS.md`). Derived text is untrusted evidence at status `extracted_needs_review` — a locator is generated metadata, not authority, and fidelity warnings flow into the existing human review acknowledgement gate.

Adapter 0.4.0 adds citable HTML table rows with column positions, source-stated headers/captions, and preceding-heading context. It does not infer relationships from adjacent labels; merged cells and ragged widths warn. CSV keeps its historical raw-text path unless the operator selects `--documents --csv-representation structured`; an optional declared first-row header adds labels without inference. The representation choice, options, and adapter version are frozen in the document policy and bound to the derived evidence identity. A changed choice makes deltas incomparable while previous runs remain verifiable.

Adapter 0.5.0 preserves SVG source labels and vector attributes through the existing defused XML parser, and PNG envelope/dimensions/annotations through the standard library. It inventories embedded visual assets in Office/PDF without claiming their contents. These source structures and locators are citable as derived text, while visual meaning remains an unavailable issue. PNG pixels are not decoded; SVG rendering and PDF nested form resources are not inspected. The worker limits input/output, XML structure, PNG dimensions/chunks and wall time; these controls do not substitute for OS sandboxing or [human visual comparison](VISUAL_FIDELITY_REVIEW.md). The frozen adapter policy and representation identity keep earlier runs verifiable and changed policies incomparable.

Adapter 0.6.0 validates PNG compressed scanlines and filter bytes through a bounded standard-library zlib stream. No pixel values are reconstructed, OCR runs, or new parser dependency is introduced. This closes a malformed-IDAT acceptance gap without changing the visual-meaning boundary. The [synthetic capability probe](VISUAL_CAPABILITY_PROBE.md) is prepared for the approved assistant; its result and human reference comparison remain external to the checkout.

Records 0.4 add evidence-linked event objects to the existing segment-bound candidate contract. Each event selects exact parent-record citations and keeps event date apart from optional effective date and file/capture time; status, precision, offsets, ranges, conflict alternatives, and relative anchors stay explicit. The checker validates these structures without inferring temporal truth. Re-anchoring drops events whose cited support disappears and reports the degraded parent record. Publication preserves the exact records bytes under the existing review hash and generates a separate `timeline.md` for records 0.4. Packet generation produces `document-navigation.md` from frozen file dates before candidates exist; it cannot assign business event dates. See [ADR 003](architecture/adr/003-evidence-linked-event-dates.md).

Patch J's `kb_publish.py --prepare` generates `review-report.md` before approval from checked candidate records and frozen evidence, with individual warning occurrences, citation context, unchanged/changed/removed records, triage, and fidelity gaps. Review 0.3 binds the report's bytes alongside records and manifest; publication regenerates it and refuses stale or missing content. Frozen review 0.1/0.2 schemas remain readable, while new publication requires report-bound 0.3. The report cannot assign semantic correctness or turn its own questions into reviewer dispositions.

## Not implemented

No live Google Workspace importer, Workspace Studio flow, task creation, autonomous LLM executor, multi-agent graph runtime, vector store, content-based secret scanner, semantic-entailment judge, image/video parser, CI service, or multi-user signing system. Local source snapshots are not globally atomic and the publication flag is not authentication.

No claim is made that this workflow already improves the user's GLM output. The synthetic test suite validates mechanics; the real pilot validates usefulness and model behavior.

## Engine layout

The tools are flat scripts in `tools/` that import each other through the script directory; tests add `tools/` to `sys.path`. `src/second_brain/` is still the uv project stub. Moving the tools into a package with `[project.scripts]` entry points is proposed in the improvement plan (Phase 2, step 5) but not done.
