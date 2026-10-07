# Targeted ingestion state promotion and run context implementation plan

Date: 2026-10-06. Baseline inspected: `4bf4dba`.

Status: authorized implementation and remediation complete for Phases 1–6. The three initial review defects, adjacent resume race and final mixed-status cycle diagnostic are closed by regression tests and independent re-review; final synthetic validation passed. Earlier failures and implementation evidence are retained below. Real-pilot acceptance and rollout remain pending. Architect review was read-only and acceptable with the revisions incorporated below. Implementation checks and independent review do not authorize real access or publication.

This plan addresses three gaps: isolating relevant project content in mixed sources, reconciling extracted information into approved project knowledge and global lookup, and using that knowledge when preparing subsequent runs. It is the bounded implementation handoff for these capabilities. The broader [roadmap](ANALYSIS_AND_IMPROVEMENT_PLAN.md) and [requirements delivery plan](REQUIREMENTS_V2_DELIVERY_PLAN.md) retain their other commitments, including format and visual-fidelity work.

Saving this plan does not authorize implementation, real source capture, configuration changes, disclosure, approval, or publication. A later explicit implementation request authorizes engine development within the requested phases; operational access and human approval remain separate.

## Instructions for the implementing Codex session

1. Read `AGENTS.md`, `WORKFLOW.md`, `CONTRACT.md`, `POLICY.md`, this plan, and the selected project's policy when a real project is involved. Inspect the current code and worktree before relying on this baseline. Runtime modules and schemas live under `src/second_brain/`; `tools/` contains compatibility entry points. Some historical documentation uses the older layout.
2. Confirm which phases the user has authorized. Execute those phases in dependency order, with one writer and small coherent patches. Do not request repeated approval for already-authorized engine changes.
3. Resolve the contracts in Phase 1 before implementing dependent behavior. Preserve existing accepted ADRs and add successor decisions where semantics change.
4. Run focused verification after each patch and record commands, outcomes, limitations, and remaining gates. Use Python through `uv`; do not install tooling or alter dependencies merely to run validation.
5. Keep synthetic engine tests separate from real operational work. Never manufacture a real approval, invoke real publication, change frozen evidence, or weaken checks to pass a gate.
6. Update phase status and completion evidence in this document as implementation progresses. Do not label a phase complete when its acceptance criteria remain unmet. If real-pilot inputs are unavailable, complete authorized tooling work and identify that remaining gate explicitly.

Suggested later handoff prompt:

> Implement the engine changes in Phases 1 through 6 of `docs/TARGETED_INGESTION_STATE_AND_CONTEXT_PLAN.md`, then complete the synthetic validation in Phase 7. Follow its architect-reviewed constraints, resolve the Phase 1 contracts first, work in small patches, and record actual validation evidence. Preserve project.json v0.1, historical compatibility, fixed GLM behavior, and human approval/publication. Do not configure or capture real projects, grant disclosure, install dependencies, or publish real knowledge. Report the separately authorized real-pilot work that remains.

## Outcomes and boundaries

The completed workflow must capture authorized project material, preserve the context required to interpret it, promote only evidence-supported claims through human review, and supply reproducible prior context to subsequent runs.

- Keep `project.json` v0.1 unchanged. Governance and permissions belong outside it.
- Keep the existing GLM-5.3-flash assistant at its fixed default effort. Add no model calls, provider, graph database, or multi-agent framework.
- Keep project releases authoritative for derived local knowledge. The global index remains disposable; it does not become a separate global approval store.
- Preserve immutable releases, exact evidence, uncertainty, explicit removals, and human approval/publication.
- Treat sources and retrieved context as untrusted data. They cannot widen permissions or supply execution instructions.
- Preserve legacy readers and behavior for legacy artifacts. New profiles must have explicit, versioned enforcement.
- Distinguish structural validity from semantic correctness and business approval. Accuracy and effort improvements require measurement.

## Baseline gaps

| Area | Confirmed implementation | Gap to close |
| --- | --- | --- |
| Capture | `kb_inventory.py` filters source paths and captures whole eligible files. | Mixed files retain unrelated passages; packet filtering occurs after capture. |
| Packet selection | `kb_packet.py` unions explicit IDs, globs, and keyword hits at file level. | No passage selection or explicit intersection mode. |
| Attribution | `kb_mentions.py` scans registered aliases; records 0.5 checks enforce assessed R1–R4 dispositions. | Implicit references and semantic ownership need review; older records do not invoke the routing gate. |
| Coverage | `kb_segments.py` represents ordinary text as one whole-file segment. | Whole-segment selection cannot isolate mixed-project text. |
| Promotion | Publication replaces the selected complete project snapshot; `kb_reanchor.py` refuses records 0.5. | Narrow capture can omit retained knowledge; routed citation reuse needs safe assistance. |
| Global lookup | `kb_index.py` preserves qualified approved records and validates freshness. | It does not reconcile cross-project assertions or rank results by relevance. |
| Run preparation | Inventory, packets, mentions, re-anchoring, and index lookup are separate commands. | No `run create` command or automatic inclusion of approved prior context. |

## Phase status

| Phase | Deliverable | Status |
| --- | --- | --- |
| 1 | Contracts and evaluation baseline | Complete (real cohort pending) |
| 2 | Explicit capture scope and run intent | Complete |
| 3 | Passage selection and project attribution | Complete after remediation (semantic quality requires review) |
| 4 | Project reconciliation and global assertion views | Complete after remediation (project-owned assertions, no global merge) |
| 5 | Ranked retrieval and frozen run context | Complete |
| 6 | Run creation and recovery | Complete after packet and concurrent-resume remediation |
| 7 | Validation, real pilot, and gradual rollout | Synthetic revalidation complete; real pilot and rollout pending |

Implement Phases 1–6 in order. Build synthetic acceptance cases from Phase 1 onward; Phase 7 consolidates regression evidence and measures real usefulness.

## Phase 1 Define contracts and establish the baseline

Separate material permitted in storage, passages exposed to the assistant, and claims eligible for project knowledge. Relevance does not establish permission.

Freeze two run purposes in the manifest:

- `analysis_only`: supports narrow investigation and cannot publish a replacement project snapshot.
- `project_refresh`: produces a complete project snapshot and must revalidate retained claims against current-run evidence. Missing support blocks completion unless retirement is deliberately reviewed.

Specify the minimal new contracts: an operator run request, a frozen selection/profile contract where necessary, and a context contract with separate destination permission. Extend existing records/referral contracts for reviewed assertions rather than creating an independent global relation ledger. Assign exact schema versions during this phase and preserve prior readers.

Add successor ADRs referencing [ADR 002](architecture/adr/002-quotable-representation-and-segments.md), [ADR 004](architecture/adr/004-reviewed-target-intake.md), and [ADR 005](architecture/adr/005-derived-approved-release-index.md). Settle range coverage, publication eligibility, relation ownership, and context persistence before dependent patches.

Define synthetic cases and the requirements for a human-reviewed pilot reference set: mixed-project documents, aliases and implicit references, shared components, missing qualifiers, proposals, contradictions, changed dependencies, and retained prior claims. Define metric denominators and agree pilot thresholds before measuring results.

**File scope:** `CONTRACT.md`, `WORKFLOW.md`, `src/second_brain/schemas/`, new ADR files under `docs/architecture/adr/`, `docs/PILOT_ACCEPTANCE.md`, and `templates/PILOT_SCORECARD.md`.

**Exit gate:** each gap has an acceptance scenario; scope, permission, coverage, versioning, and run-intent contracts are explicit. A real reference cohort may remain pending authorization, but synthetic contract design can proceed.

## Phase 2 Make capture scope explicit and enforceable

Add an operator-supplied selection that narrows configured sources before file content is opened or copied. Preflight must disclose included files, exclusions, unresolved scope, and missing inputs without opening excluded originals.

Strict isolation of mixed documents requires a reviewed scoped UTF-8 export with a content hash and traceable provenance. Do not read the original merely to regenerate or verify an export when original access is not authorized. Whole-file mode remains available only with authorization for the entire file and an explicit disclosure that unrelated content may be retained. Tools cannot infer whole-file permission from names, paths, or relevance scores.

Bind stable selection policy, membership, run intent, and composition semantics into scope identity. Store observed content hashes separately so ordinary edits produce comparable deltas; changed selection policy or representation rules produce an explicit incomparable delta.

Enforce run intent in the publication implementation, not only in the eventual orchestration command. Legacy manifests keep legacy behavior. A narrow analysis cannot replace `CURRENT.json` through a direct publication entry point.

**File scope:** `src/second_brain/kb_inventory.py`, `kb_common.py`, `kb_check.py`, `kb_publish.py`, relevant schemas, `tests/test_source_scope.py`, and new targeting tests.

**Exit gate:** strict-mode tests show no reads or copies of excluded originals, changed export bytes are detected, ordinary content edits remain comparable, and narrow runs cannot silently retire project knowledge.

## Phase 3 Select passages and enforce project attribution

Deliver whole-segment selection first, then exact line-range selection. Freeze selected intervals and omitted complements against original representation hashes and existing segment IDs. Do not rewrite or repartition historical segments. Define an additive interval-coverage contract and its file/segment rollups before enabling partial ranges.

Preserve governing headings, table labels, and status qualifiers. Expose context omissions to semantic review. `used` means cited, not fully read; `reviewed_no_record` requires full reading at the claimed coverage level. Unread ranges remain explicitly triaged or deferred under the applicable gate.

Add explicit union/intersection selection semantics while preserving existing union behavior for legacy calls. Empty or budget-limited selections must be visible, never silently replaced with broader input.

Extend existing R1–R4 attribution to include evidence-grounded references found during manual reading, not only alias hits. Registered aliases and path hints are leads. Other-project-only material cannot become home claims, and unknown attribution cannot become an observed home fact. Freeze the targeted profile and make the checker reject attempts to evade it by using an older records schema. New profiles must retain honest coverage even when scans find no aliases.

**File scope:** `src/second_brain/kb_packet.py`, `kb_segments.py`, `kb_mentions.py`, `kb_check.py`, `kb_referrals_contract.py`, coverage/routing schemas, `prompts/01_EXTRACT.md`, relevant canonical skills, `tests/test_segments.py`, `tests/test_cross_project.py`, and `tests/test_contract_v02.py`.

**Exit gate:** mixed-project examples expose the selected passages with necessary qualifications, exclude other-project-only claims from home records, account for unread complements, and enforce routing independently of the submitted records version. Semantic accuracy remains separately reviewed.

## Phase 4 Strengthen promotion and cross project integration

Generate a reconciliation report for retained, new, revised, removed, unsupported, and unresolved records. A `project_refresh` must include current evidence for retained claims or block with the missing support identified. Scope narrowing is not source deletion. Retirement requires an explicit human-reviewed removal; do not introduce partial-release overlays or blind carry-forward.

Extend records 0.5 re-anchoring only to suggest citation matches. Require fresh mention assessment, routing classifications, disclosure checks, and referrals. Stable meanings retain IDs; changed meanings require a new ID or explicit reviewed revision.

Represent cross-project equivalence, conflict, and dependency as evidence-backed assertions owned by the originating project, with qualified project/release/record references. Validate reference integrity and disclose unavailable, historical, or conflicting targets. The index derives grouped views from these assertions; it does not merge records or change target knowledge. Target changes continue through target intake and review.

Business applicability and supersession require explicit supported assertions. Dates, capture order, and release recency cannot establish active state. Define relation direction and contradictory/cyclic supersession handling without suppressing the underlying evidence.

**File scope:** `src/second_brain/kb_reanchor.py`, `kb_review_report.py`, `kb_check.py`, `kb_publish.py`, `kb_index.py`, records/referral/review contracts, `prompts/02_RECONCILE.md`, `prompts/04_VERIFY.md`, relevant canonical skills, and promotion/routing/index tests.

**Exit gate:** retained knowledge is revalidated or deliberately retired; no routing approval or proposal is silently promoted; cross-project disagreements remain qualified, visible, and project-owned.

## Phase 5 Build useful and reproducible run context

Improve lookup with deterministic ranking, explicit query terms, reviewed aliases, project/kind/status filters, and bounded expansion of reviewed relationships. Return ranking reasons, deterministic tie handling, and omitted-result counts. This improves retrieval mechanics without claiming semantic understanding of project needs.

Batch retrieval against a verified index generation where practical. Do not weaken existing access and integrity checks or introduce caching without a separate evidence-backed design.

Create a frozen run-context bundle under the run's `work/` containing selected qualified records, exact provenance and statuses, query/profile/ranking version, budget and omissions, index generation, and selected release/permission bindings. The assistant briefing must distinguish prior knowledge from current-run evidence. Prior context cannot justify new current-run claims without authorized capture and revalidation.

Require explicit permission to copy foreign-project context into both the target run and its eventual release audit trail. Existing index-destination permission does not grant this. Include original quoted context, derived briefings, and retained audit copies in the destination assessment.

Use two lifecycles. New retrieval, use, review preparation, and publication check live permission and selected dependency freshness. Historical release verification checks frozen hashes and bindings without depending on future foreign pointers or grants. Revocation blocks new use; retention of already-published bytes remains an operator responsibility.

Pin context per run. Under the conservative initial policy, changed selected context requires a new run rather than in-place replacement. Recheck selected dependencies before the target publication pointer swap, without treating that publication's own pointer change as retroactive invalidation. Where feasible, unrelated index changes must not force a restart of already-pinned selected context; initial index lookup retains its full verification contract.

**File scope:** `src/second_brain/kb_index.py`, `kb_check.py`, `kb_publish.py`, read-only release validation boundaries in `kb_referrals.py`, context contracts, and proposed new `src/second_brain/kb_context.py` plus `tests/test_run_context.py`.

**Exit gate:** context is reproducible and attributable; stale/revoked selected inputs block new use; permissions cover retained destinations; historical local release integrity survives subsequent foreign publication or revocation.

## Phase 6 Connect preparation through run create

Add a proposed `second-brain run create` command with a read-only dry-run mode. Implement it as coordination of existing bounded operations, without a scheduler or generic workflow framework.

1. Validate explicit run purpose, scope, permissions, and context requirements.
2. Retrieve authorized context and report scope suggestions. Suggestions cannot widen the request or grant access.
3. Capture the explicitly selected evidence.
4. Prepare selected packets, mention scans, citation suggestions, reconciliation checklist, and assistant briefing.
5. Check preparation completeness and selected context freshness; report the next manual extraction/review action.

Requested context failure must stop clearly. A context-free mode must be explicit, not a silent fallback. First runs without prior approved knowledge need a clearly reported supported path.

Define stage states and input/output hashes. Resume only recognized completed stages whose inputs and outputs still match. Existing capture and packet operations are write-once: interrupted stages need a documented temporary-output recovery path or an explicit failure requiring a new run, never overwrite or accidental recapture. Changed frozen scope requires a new run.

Stop before semantic extraction, model invocation, human approval, or publication. Post-publication index rebuilding remains a separate explicit operator action, with visible stale-index status. Index refresh failure cannot roll back successful project publication.

**File scope:** proposed new `src/second_brain/kb_run.py` and `tests/test_run_create.py`, `src/second_brain/cli.py`, existing preparation tools, `tests/test_packaging.py`, `START_HERE.md`, `WORKFLOW.md`, and `docs/CONFIG_REFERENCE.md`.

**Exit gate:** an end-to-end synthetic preparation uses authorized prior context, respects scope, supports first-run/no-context behavior, recovers only verified stages, and hands off to the existing manual assistant workflow.

## Phase 7 Validate effectiveness and roll out gradually

Run focused tests after each patch, then regression suites appropriate to changed contracts. Existing suites include `tests/test_source_scope.py`, `test_segments.py`, `test_contract_v02.py`, `test_cross_project.py`, `test_global_index.py`, `test_stage2.py`, `test_temporal.py`, `test_record_events.py`, and `test_packaging.py`. Add targeting, context, and orchestration cases where their contracts require them.

Repository-supported full validation is `uv run --locked python -m unittest discover -s tests -v`; skill mirror verification is `uv run --locked python tools/kb_sync_skills.py --check`. Use an existing synchronized environment without installing or changing dependencies; if necessary use the no-sync equivalent and report environment limitations. Actual executed commands and results are recorded below. If canonical skills change, update their maintained mirrors through the established workflow.

Compare the existing and revised workflows on the same authorized human-reviewed reference cohort using the fixed GLM assistant. Count uncertain attribution and unavailable evidence separately from correct results. Record manual work separately from tool runtime.

| Measure | Required interpretation |
| --- | --- |
| Project-attribution precision and recall | Unrelated claims admitted and relevant claims missed against labeled reference claims. |
| Unrelated packet content | Unnecessary material exposed to the assistant, separate from content retained in authorized storage. |
| Unsupported promotion and lost qualifiers | Whether extracted claims preserve evidence meaning, proposal status, and uncertainty. |
| Retained-record and conflict coverage | Whether refreshes preserve existing knowledge and material disagreements. |
| Context retrieval recall and answer usefulness | Whether needed prior facts are retrieved and improve the same reference tasks. |
| Review time and preparation latency | Total operator/model/tool effort, including scoped-export work and repeated freshness checks. |

Agree denominators and usefulness thresholds before seeing results. Require zero unauthorized capture/disclosure, fabricated evidence, silent proposal promotion, or unintended record removal in the acceptance set. Tooling success does not establish real-world extraction quality.

Roll out by explicit project opt-in after synthetic gates and the relevant real-pilot criteria pass. Preserve legacy readers and immutable releases. Rollback disables new profiles and rebuilds disposable outputs; it never rewrites approved history. Once new schema versions are published, rollback must retain a compatible reader rather than reverting blindly to an older binary.

**Exit gate:** synthetic gates pass, the authorized pilot meets agreed criteria, and the operator accepts review effort. Missing real-project access or pilot measurements remain explicit pending work.

## Architect review and incorporated revisions

The architect reviewed the proposed design on 2026-10-06 using a lightweight architecture tradeoff review. Verdict: **acceptable with the revisions incorporated in this plan**. This is design review, not approval of real access, business claims, or publication.

| Finding | Incorporated decision | Acceptance scenario |
| --- | --- | --- |
| Narrow runs can replace complete state | Manifest-bound `analysis_only` and `project_refresh`; enforcement in publication itself. | A refresh missing retained-record support blocks without implicit retirement. |
| Text segments span whole files | Add frozen interval coverage before partial-line selection. | Selected ranges and unread complements remain accounted for without claiming full reading. |
| Relevance cannot authorize storage | Strict mode consumes reviewed exports; no excluded-original reads. | An authorized excerpt can be captured without opening an unauthorized mixed original. |
| Scope hashes can destroy delta usefulness | Stable selection policy in scope identity; observed hashes stored separately. | Ordinary edits compare; selection-policy changes are explicitly incomparable. |
| Live foreign state can invalidate history | Separate prospective permission/freshness checks from frozen historical integrity. | Revocation blocks new use but does not corrupt historical release verification. |
| Context may change during preparation | Pin selected dependencies, recheck before pointer swap, require a fresh run on change. | A selected foreign release changes mid-run; publication blocks and frozen artifacts remain intact. |
| Existing APIs are write-once | Resume verified completed stages only; specify temporary-output recovery. | Interrupted packet creation cannot overwrite or silently recapture evidence. |
| Global merging creates a new authority | Project-owned reviewed assertions and derived grouped views. | An origin assertion never alters a target record or resolves disagreement automatically. |

Tradeoffs remain explicit: scoped exports add operator work; complete refreshes cost more than narrow analysis; pinned context can require restarts; full index verification can dominate latency; substantive conflict resolution stays with source owners and human review.

Do not introduce partial-release overlays, a canonical global claim store, automatic semantic capture authorization, or automatic records 0.5 routing carry-forward to avoid these tradeoffs.

## Resolved contracts and remaining pilot decision

- Resolved by ADR 008: exact contract versions/legacy dispatch, selected intervals and file/segment rollups, strict export provenance, stable scope identity and publication intent.
- Resolved by ADR 009: retained-destination context permission, frozen/historical versus live/prospective checks, project-owned qualified assertions and visible supersession conflicts/cycles, record/byte budgets, and verified completed-stage recovery. No real destination is chosen here.
- Pending human action: select an authorized real cohort, source/destination permissions and reviewers, then agree measurable thresholds before the Phase 7 pilot. No real project workspace or project policy was selected for this implementation.

## Completion evidence

Implementation authorization: 2026-10-06. Checkout HEAD remains the inspected `4bf4dba`; pre-existing `docs/ANALYSIS_AND_IMPROVEMENT_PLAN.md` edits are preserved. The plan was untracked before implementation. No real project/policy was selected.

### Phases 1–2

- Accepted successor ADRs 008 and 009 resolve version dispatch, range rollups, intent, assertion ownership, destination retention, budgets and verified-only recovery. Added run-request/context-permission/run-context 1.0, records 0.6 and referrals 1.1 schemas with exact legacy records 0.5/referrals 1.0 readers; additive targeted manifest binding leaves project.json 0.1 intact. Updated CONTRACT, WORKFLOW, PILOT_ACCEPTANCE and scorecard with synthetic scenarios and pending real denominators/thresholds.
- `kb_targeting.py`, inventory/check/publication enforce exact selected membership before content reads, reviewed export hashes/provenance, stable-policy scope fingerprints and direct analysis-only publication/review rejection. Publication copies the frozen request.
- Checks actually executed: `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests -p 'test_source_scope.py' -v` (baseline: 9 passed); same command with `test_contract_v02.py` (45 passed); `test_targeting.py` (5 passed); `git diff --check` passed.
- Environment: ordinary uv command could not create its default cache lock on the read-only filesystem. Task-local cache plus locked/no-sync uses existing dependencies without installation. No lockfile/dependency change.
- Limits: permission/reviewer fields are audit declarations, not authentication. Export fidelity, relevant qualifiers and real cohort quality still need human review. Whole-file mode deliberately retains all selected bytes; no real storage permission is granted.


### Phases 3–4

- Packet union/intersection and whole-segment/exact-range selectors retain original lines; targeted selectors/budgets are frozen in the request. `kb_intervals.py` accounts for omitted complements and enforces partitions, representation hashes, actual use, rollups and Stage 2 deferred rejection. Targeted profiles require records 0.6 even with zero alias hits. All parent/finding citations require declared attribution; R2 and unknown observed-home claims block. Referrals 1.1 adds exact manual references with fresh R1–R4 assessment. Alias scans respect targeted exposure ranges. Review discloses interval triage and binds its containing segments.
- `kb_reconciliation.py` reports new/retained/revised/removed records, unavailable prior support and unresolved claims. Existing complete-snapshot human removal gates remain. `reanchor --citation-only` permits routed exact-quote suggestions but clears routing/assertions/aliases and requires fresh attribution and disclosures. Normal routed automatic carry-forward still refuses.
- Records 0.6 assertions bind parent evidence and qualified targets. Authorized index `assertions` derives equivalence groups, unavailable/historical targets, opposing assertions and supersession cycles without merging, suppressing or modifying claims.
- Focused checks: targeted suite 11 passed; reconciliation suite initially 10 passed (included six imported passage tests; corrected discovery to avoid duplicates); segment suite 9 passed; cross-project suite 33 passed. `git diff --check` passed. Commands use the Phase 1 locked/no-sync prefix and unittest discover patterns `test_targeting.py`, `test_reconciliation.py`, `test_segments.py`, `test_cross_project.py`.
- Compatibility regression initially failed one legacy triage-method-prefix assertion; restored the original union label and reran `test_contract_v02.py`: 45 passed. This was an engine regression, not a waived gate.
- Limits: qualifier/heading sufficiency, attribution, alias meaning and assertion entailment remain substantive semantic review. Operators must include necessary context ranges. Foreign target existence is resolved only against authorized selected index entries; outside-selection targets remain explicitly unavailable, never presumed absent.

### Phases 5–6

- `kb_index.py` adds deterministic weighted lexical/alias ranking, qualified-key ties, reasons/omissions, bounded filter-preserving relationship expansion and batch retrieval with one fully verified generation. `kb_context.py` freezes exact selected records, provenance/status, queries/ranking, budgets and selected dependencies; required missing or over-budget context blocks before capture. Separate context permission covers quoted context, briefings and retained run/release audit bytes. Frozen hashes are checked again after parsing.
- Prospective checking validates selected permission, policy/configuration, registry/access and release/pointer bindings. Review preparation and publication use prospective checks, including the check immediately before release/pointer work. Historical release checking uses frozen integrity, survives later foreign publication/revocation and the target's own successful pointer update. Unrelated index generation changes do not invalidate pinned context.
- `kb_run.py` and CLI/compatibility entry points coordinate capture, packets, mentions, citation suggestions, briefing/checklist and checks. Explicit no-context first runs are supported. Requested-context errors do not fall back. Read-only dry runs perform no source-content capture. Receipts bind inputs and required output hashes; only completed prefixes resume, ready resume preserves bytes, and interrupted write-once stages require a new run. Preparation creates no candidate or approval and stops for manual extraction. Prior released records are historically validated before citation suggestions; index rebuilding stays explicit after publication.
- Focused checks with the Phase 1 locked/no-sync prefix: `test_global_index.py` (26 passed), `test_run_context.py` (9 passed), `test_run_create.py` (final focused run: 12 passed), `test_targeting.py` (final focused run: 13 passed) and `test_reconciliation.py` (5 passed). The CLI `run create --help` and `context --help` completed successfully.
- Independent read-only delivery review initially found legacy records 0.1/0.2 re-anchoring into targeted runs could omit new segment bindings. Corrected output-version dispatch and added both legacy-version integration cases. It also identified recursive supersession traversal risk; replaced traversal with an iterative walk and verified a 1,100-edge case. Re-review: PASS, no remaining blocking engine finding. Added synthetic successful own-prior-context and foreign-assertion publication/index cases and rejection of receipts omitting required outputs.
- A context freshness test initially failed because its mocked publication hook also affected the fixture's foreign publication; isolated the mock, then the focused suite passed. No engine gate was weakened.
- Limits: context selection is deterministic lexical retrieval, not semantic reasoning. Permission fields are operator audit declarations; retention and semantic review remain human duties. Required context uses record/UTF-8-byte budgets, not tokens. Run creation uses existing default text capture; adapter-specific document capture options remain in the existing inventory entry point. No document fidelity or real usefulness claim is made.

### Phase 7 synthetic acceptance and remaining gates

| Synthetic acceptance | Executed evidence | Remaining human boundary |
| --- | --- | --- |
| Exact scope before reads; mixed strict exports; unavailable unselected roots; analysis-only publication blocked | `test_targeting.py`, `test_source_scope.py` | Original/export permission and fidelity |
| Whole segments/ranges, union/intersection, truthful complements, mandatory targeted profile and manual attribution | `test_targeting.py`, `test_segments.py`, `test_cross_project.py` | Include necessary headings/qualifiers; judge attribution |
| Complete refresh/removals, citation-only legacy upgrades, qualified assertions and visible cycles/disagreement | `test_reconciliation.py`, `test_run_create.py`, existing contract/promotion suites | Current citations need semantic support; exact removals need human review |
| Ranking/filter/batch mechanics, required budgets, separate retained permission, selected freshness and historical independence | `test_run_context.py`, `test_global_index.py`, `test_run_create.py` | Retrieval recall, usefulness, retention and permission assessment |
| First run, authorized prior context, dry run, completed-prefix resume and interrupted-stage rejection | `test_run_create.py` | Manual fixed-GLM extraction, semantic verification and approval |

- Initial full regression: `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests -v` ran 486 tests, `OK (skipped=1)`. Additional focused tests then passed for legacy preparation, own-context and foreign-assertion publication, passage selection and required receipt outputs. Final full-suite evidence follows below.
- Final regression with the same command: **491 tests ran in 59.639 seconds, 490 succeeded and one skipped**, `OK (skipped=1)`. The skip is `test_real_legacy_ppt_conversion`, which requires the explicit `KB_TEST_LEGACY_PPT=1` gate and an installed LibreOffice converter. That optional environment integration remains unexecuted; nothing was installed to enable it. Temporary command output is in `/tmp/second-brain-targeted-final-regression.log`; the command and results here are the durable completion evidence.
- `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_sync_skills.py --check`: PASS. Canonical extraction/reconciliation/verification skills and their maintained mirrors agree. `git diff --check`: PASS.
- The initial implementation reported engine/documentation gates complete; the fresh independent review and remediation evidence below supersede that judgment. The full Phase 7 exit gate is **not passed**. Real pilot measurements, reference labels, agreed usefulness thresholds, review-effort acceptance and explicit project opt-in remain pending. The scorecard records the required denominators and zero-tolerance failures without inventing results or thresholds.
- No real configuration/capture/disclosure grant, model/API call, installation or knowledge publication occurred. Publication integration tests use temporary synthetic projects and synthetic human-review fixtures only. project.json remains v0.1; historical schema readers and fixed assistant behavior remain intact. Unrelated roadmap edits are preserved.

### Fresh independent review and remediation (2026-10-06)

The requested fresh review returned **FAIL**, with three reproduced findings. This
supersedes the earlier review PASS; the failures were preserved and no checker was
weakened. The user authorized the suggested fixes, focused regressions, full
validation and re-review. Root remained the single writer.

| Finding | Confirmed cause / bounded correction | Regression evidence |
| --- | --- | --- |
| P1: referral crosses selected/unread complements | Exact quote and whole-file/segment checks passed while interval coverage was ignored. `kb_referrals_contract.py` now checks the complete quote against frozen selection and rejects every triaged/deferred overlap. | Two new `test_targeting.py` tests initially failed with no exception. Valid referrals pass, selected reviewed context remains usable, and both excluded/unread expansions now fail. Focused suite: 15 passed; legacy cross-project suite: 33 passed. |
| P2: re-anchor suggests excluded current citations | Quote relocation ran before selected-range filtering, including the unchanged-byte fast path. `kb_reanchor.py` now filters that fast path and all matching positions before retaining parent/finding citations, reports `outside_selected_passages`, and keeps missing record ids visible. | Two new `test_reconciliation.py` tests initially failed: excluded quote retained and outside-selection duplicate preferred. Both now pass, with selected duplicates still suggested. Focused suite: 7 passed; contract suite: 45 passed; segment suite: 9 passed. |
| P2: ready resume skips omitted packet bodies | Receipt validation required metadata and hashed only the paths the receipt supplied. `kb_run.py` now binds the parsed index to its exact checked bytes and requires indexed packets plus metadata to match both the receipt and current packet file tree. | Two new `test_run_create.py` tests initially failed (four failures across missing-entry unchanged/altered/deleted subcases and unexpected output). All 14 focused tests now pass; rejected resumes preserve bytes and verified ready/completed-prefix resume remains supported. |

The positive controls and exact frozen quotes ruled out malformed fixtures,
stale hashes and permission-schema errors as the regression causes. Existing
legacy behavior remains covered. Deterministic boundary cases are sufficient
for these fixes now; broader generated interval partitions can be a later
hardening exercise without installing dependencies for this task.

Diagnostic alternatives were bounded: referral failures could have come from
inexact quotes, stale selection, or missing interval checks; exact-quote controls
and frozen selection isolated the interval guard. Re-anchoring could have lost
text, lacked a segment, or ignored selection; identical bytes and valid segment
bindings isolated selection filtering. Resume could have miscomputed hashes,
failed context freshness, or omitted output enumeration; ordinary altered packets
were already rejected and unchanged context passed, isolating output membership.
The later race distinguished a held lock, changed dependencies, and stale receipt
state: the competitor released its lock and kept dependencies unchanged, while
the delayed caller still held the old completed prefix.

Focused commands use `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked
--no-sync python -m unittest discover -s tests -p '<suite>' -v`, with actual
patterns `test_targeting.py`, `test_cross_project.py`, `test_reconciliation.py`,
`test_contract_v02.py`, `test_segments.py` and `test_run_create.py`.
`git diff --check` passed after each engine patch. At that checkpoint the affected
phase gates remained open until final full regression and independent review;
their completed results are recorded below. Real pilot and optional converter
validation remain separate pending work.

The first remediation full suite ran 497 tests in 61.122 seconds, `OK
(skipped=1)`, with 496 successes and the same optional LibreOffice/PPT skip. Scope
re-review returned PASS and independently checked omitted parent/finding support,
dropped event reporting, surviving event-index remapping and rebuilt attribution.
Recovery re-review closed the packet-output finding but reproduced an adjacent
P2 race: two continuations can validate the same prefix before locking; the
delayed caller could overwrite a newer ready receipt, then fail on a write-once
artifact. That new finding kept Phase 6 open.

Added `test_create_run_delayed_resume_preserves_completed_receipt`, scheduling
the competitor to finish between validation and lock acquisition. A test-only
reentrancy guard was corrected before confirming the engine overwrite failure.
`kb_run.py` now compares the validated receipt with freshly read state under the
acquired lock, before any stage mutation. Changed state fails with an explicit
verified-resume retry; no completed receipt or output is rewritten. The focused
`test_run_create.py` suite now has 15 tests, all passed after the race correction.

Independent re-review: the scope reviewer returned PASS for referral and
re-anchor fixes; the recovery reviewer returned PASS for packet receipts and the
race correction. The latter independently ran five focused tests and repeated
the original two-thread interleaving: first caller completed, delayed caller was
rejected, all completed bytes remained unchanged, and subsequent ready resume
succeeded. These are engine fix closures, not semantic or real-use approval.

Final post-remediation command: `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run
--locked --no-sync python -m unittest discover -s tests -v`, exit 0. **498 tests
ran in 60.495 seconds: 497 successes and one optional skip**, `OK (skipped=1)`.
The unchanged skip requires `KB_TEST_LEGACY_PPT=1` and installed LibreOffice;
no dependency was installed. Temporary output is in
`/tmp/second-brain-targeted-remediation-final.log`. Skill mirror check and
`git diff --check` passed. project.json v0.1, dependencies, operating policy and
the unrelated roadmap edits remain unchanged by remediation. No real operational
authorization or publication was exercised. Phases 3, 4 and 6 engine gates are
closed; Phase 7 real-pilot labels, permissions, thresholds, reviewer effort and
opt-in remain pending human work.

Final independent deputy readiness gate: **PASS** for the authorized remediation,
with no remaining critical or non-critical finding requiring a change. The
reviewer inspected the final regression log, packet membership and under-lock
state checks, byte-preservation regressions and documented pilot boundaries, and
independently verified `git diff --check`. Optional converter and real-pilot
validation do not count as passed engine remediation evidence.

## Final diagnostic review and correction

A fresh independent Phase 1–6 review found no blocking enforcement defect, but
reported one P2 diagnostic inconsistency: a proposed or unresolved supersession
edge could be marked as cyclic even though that status was excluded from the
supersession graph. The Phase 5–6 security review returned PASS. This finding
did not suppress records or bypass human approval; it required a correction to
the derived assertion view.

Before the fix, `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync
python -m unittest discover -s tests -p 'test_reconciliation.py' -k mixed_status -v`
ran one regression test and failed all eight mixed-status subcases. The test also
covers all four observed/interpretation pairings that should still form cycles,
preserves proposal/unresolved rows and statuses, and checks input immutability.

`kb_reconciliation.py` now uses the same established-status predicate for graph
construction and cycle flags. `docs/CONFIG_REFERENCE.md` states this diagnostic
boundary. The focused command with `-p 'test_reconciliation.py' -v` passed all
eight tests, including the existing 1,100-edge chain and true-cycle checks.
Final command: `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync
python -m unittest discover -s tests -v`, exit 0. **499 tests ran in 60.167 seconds:
498 successes and one optional LibreOffice skip**, `OK (skipped=1)`. Temporary
output is in `/tmp/second-brain-cycle-diagnostic-regression.log`.

Independent re-review returned **PASS** with no actionable finding in this fix.
The reviewer independently probed both mixed-status and established cycles and
verified input/status preservation; `git diff --check` passed. This closes the
P2 diagnostic finding. Phases 1–6 and synthetic Phase 7 checks are complete;
optional converter validation and real-pilot validation remain pending. The next
human action is to authorize pilot inputs and access, provide independent
reviewers, and agree the acceptance thresholds before measuring real usefulness.
No real configuration, capture, disclosure grant or publication was performed.

## Commit delivery for testing on another computer

The user authorized local commits for transfer and real-pilot testing. Delivery
branch: `codex/targeted-ingestion`, based on `4bf4dba`. Architecture decisions are
committed separately from the coupled engine, schemas, regression tests and
matching workflow documentation; this plan records the completion evidence.
Pre-existing edits in `docs/ANALYSIS_AND_IMPROVEMENT_PLAN.md` are excluded from the
commits and preserved in the working tree.

Pre-commit revalidation: `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked
--no-sync python -m unittest discover -s tests -v`, exit 0. **499 tests ran in
60.514 seconds: 498 successes and one optional LibreOffice skip**,
`OK (skipped=1)`. Temporary output is in
`/tmp/second-brain-commit-regression.log`. `uv run --locked --no-sync python
tools/kb_sync_skills.py --check` (with the same cache override), `git diff --check`
and `git diff --cached --check` passed. No dependency installation was needed.

Local commits do not transfer the branch automatically. The operator must push
or otherwise transfer it, check out the same commit on the pilot host, and record
that revision in the scorecard. Real-pilot acceptance remains pending the human
authorization, labels, thresholds and review described above.
