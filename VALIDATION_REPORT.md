# Validation report

This report retains engine checks and synthetic validation results. Private project-run checks and findings are omitted.

## Current macOS compatibility repair — engine 0.4.0, adapter 0.6.2

Executed 2026-10-06 on Linux with synthetic inputs. The user-supplied macOS
report ran 419 tests and recorded 22 errors from the `/var` symlink path guard,
one packaged visual-worker failure while setting `RLIMIT_AS`, and two skips.
The visual test workspace now resolves the system temporary-directory alias,
matching the existing packaging fixture. Production symlink checks are unchanged.

Inspection also identified a later Linux-only `renameat2` call. macOS now uses
native `renamex_np(RENAME_EXCL)` and CPU/file-size/time controls, with the absence
of an imposed address-space cap disclosed in packet limitations. Linux retains
the 512 MiB cap. Resource setup preserves tighter inherited soft/hard limits.
The local workflow and ADR describe the platform differences and canonical paths.

Before the repair, an existing work-confinement test reproduced the path error
under a synthetic symlinked temporary parent. Three new Darwin rename tests
failed against the Linux-only binding. Two additional resource-limit tests cover
Linux/Darwin with both unlimited and tighter inherited limits. These focused
regressions are sufficient for the bounded platform branches; no property-based
follow-up is required for this repair.

| Command or check | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_visual_review tests.test_packaging` | **39 passed**, including packaged worker/contract checks outside the checkout. |
| Run all `tests.test_visual_review` cases through `uv run --locked --no-sync python` with `tempfile.tempdir` pointing at a synthetic symlinked parent | **32 passed**; the corresponding work-confinement case failed before the fixture repair. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **424 run, 423 passed, 1 skipped** (optional LibreOffice legacy `.ppt`). |
| `git diff --check` | PASS. |

Independent review then found a P2 regression: the reader's platform-dependent
limitation list rejected intact packets produced under the other profile, and
assessment results used reader-local disclosures. The new cross-profile test
failed in both directions before the correction. Verification now accepts
exactly the recognized base and macOS producer profiles independently of the
reader; preparation snapshots the profile and assessment/export retain its
bound disclosures. Unknown, incomplete, reordered and duplicated profiles
remain unsupported. Legacy packets with the base profile remain accepted.

Follow-up validation on Linux:

| Command or check | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_visual_review.VisualReviewTests.test_packet_limitations_travel_with_producer_profile tests.test_visual_review.VisualReviewTests.test_packet_rejects_unknown_or_incomplete_limitations` | **2 passed**; all four producer/reader profile combinations verify, assess and export, preserving original disclosures in results, transcription and provenance. Negative cases reach profile validation with freshly sealed synthetic manifests. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_visual_review tests.test_packaging` | **41 passed**. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **426 run, 425 passed, 1 skipped** (optional LibreOffice legacy `.ppt`). |
| `git diff --check` | PASS. |

Independent read-only re-review returned **PASS**, with the P2 defect closed
and no remaining blocking source/test findings. It reviewed all five changed
files, the profile matrix and negative tests, and the validation evidence;
native macOS execution remains the explicit nonblocking concern.

Native macOS execution remains unverified: Darwin API/resource calls were
simulated on Linux. Rerun `uv run --locked --extra visual python -m unittest
discover -s tests -v` on the user's Mac after transferring this patch. Poppler
tests remain conditional on the explicitly selected executable being available.
No dependency, lockfile, evidence contract, real project run, human approval,
publication, or model/provider configuration changed.

## Historical local visual-review checkpoint — engine 0.4.0, adapter 0.6.2

Executed 2026-10-04 on Linux with synthetic inputs. The previous four fix/preparation commits were already committed with a clean tree before this increment. `visual-review prepare/verify/assess/export` now creates separate hash-bound raster review packets, validates explicit human element/gap dispositions, computes a declared-element match fraction and exports a traceable transcription. Existing frozen evidence and publication contracts remain unchanged. Linux resource controls and atomic no-replace rename are required for packet creation.

The optional uv `visual` extra adds CairoSVG/Pillow with a deliberate lockfile update; all eleven existing locked package versions are unchanged. Twenty-two existing schema files remain byte-identical, with two new independent visual contracts. Initial tests first failed on the missing module, then exposed an external-image SVG render failure. A read-only review found three further defects: custom approved-path bypass, packet-generation mixing during export and empty-PDF false completion. Those were repaired and regression-tested; the subsequent review gate passed. Additional checks cover real PDF rasterization of nested forms, denied/escaped SVG resources, pixel/structure/ZIP budgets, HTML SVG casing/locators, viewport geometry, immutable templates, stale bindings, omissions, no overwrite and malformed assessments.

| Command or check | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **419 tests run, 418 passed, 1 skipped** (optional LibreOffice legacy `.ppt`). Includes 27 local visual-review cases and 7 source-transplant packaging cases. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_visual_review.VisualReviewTests.test_pdf_requires_explicit_renderer` | **1 passed** after the final bounded PDF executable-version failure guard was added. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv build --offline --sdist --wheel --out-dir /tmp/second-brain-visual-delivery` | PASS; both distributions include the command and new contracts. |
| Built-wheel selection through `SECOND_BRAIN_TEST_WHEEL` and `tests.test_packaging` | **7 passed** outside the checkout. |
| Extract the final sdist with the standard-library data filter, rebuild its wheel through uv, and select it for `tests.test_packaging` | **7 passed** outside the checkout; sdist also contains the compatibility shim and all 24 schemas. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv sync --locked --offline --extra visual --check` | PASS; environment matches the lockfile/extra without changes. |
| Sealed legacy `kb_check.py --stage2` and `kb_sync_skills.py --check` | PASS; legacy fixture remains structurally valid and skill mirrors match. |
| Synthetic packet preparation and `visual-review verify` at `/tmp/second-brain-visual-review-20261004` | PASS; four previews, original hashes preserved, two retained gaps (`svg_restricted`, `html_layout_unavailable`). Human assessment stays unmeasured. |
| Existing schema/dependency comparisons and `git diff --check` | PASS. |

The new [local workflow](docs/LOCAL_VISUAL_REVIEW.md) describes human comparison, denominator inventory and conditional assessment/export commands. Automated assessments use synthetic test declarations only; no real person was impersonated or scored. The demo contains an unmeasured assessment template, not accepted human references. Representative Office/PDF fidelity, original-viewer usability, real-project extraction and GLM visual access remain unverified. Office media extraction does not establish page layout; a separately reviewed PDF export is necessary for that comparison. No model/provider/API substitution, real evidence, project configuration, business approval or publication occurred. Patch G/R2/R3 acceptance remains pending the actual human comparisons and later approved-assistant blind probe.

## Historical visual-reference preparation checkpoint — engine 0.4.0, adapter 0.6.2

Executed 2026-10-04 after the blocking fixes, suppressed-content repair, and packaging changes. The new synthetic dense HTML case includes ER and state diagrams alongside entity/relationship definitions, integration SQL, model changes, and qualified values. Its regression verifies preservation of material source text and both explicit visual-interpretation gaps. `docs/VISUAL_REFERENCE_CASES.md` pins three original hashes, and `templates/VISUAL_CAPABILITY_REVIEW.md` records an initially unmeasured approved-assistant probe and human comparison. Construction oracles are not accepted human visual references and stay outside the assistant's probe input.

| Command or check | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **391 tests run, 390 passed, 1 skipped** (optional LibreOffice legacy `.ppt`). |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_document_formats -k dense_visual_reference` | **1 test passed**: six material content families preserved, with two explicit visual gaps. |
| `SECOND_BRAIN_TEST_WHEEL=/tmp/second-brain-safe-sdist-wheel/second_brain-0.4.0-py3-none-any.whl UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_packaging` | **6 tests passed** against the wheel rebuilt from the repaired source distribution outside the checkout. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv build --offline --sdist --wheel --out-dir /tmp/second-brain-delivery`, followed by `tests.test_packaging` with its built wheel selected | PASS: final distributions built; **6 packaging tests passed**. |
| Sealed legacy Stage 2 check and skill-mirror check through the compatibility scripts | PASS, as recorded in the packaging checkpoint. |
| Catalog original hashes and changed operational-document links | PASS: all three hashes match and local targets resolve. |
| `git diff --check` | PASS. |

Independent read-only review verified the fixture hashes, all six material content families, preserved proposed/pending qualifiers, and the distinction between construction expectations and human acceptance. No verified GLM-5.3-flash local viewing mechanism or saved probe result is available, as confirmed by the user. D3/Patch G/R2/R3 visual acceptance therefore remains open; a human must verify the approved mechanism, run the blind probes, and score original/rendered representative cases. Real project authorization, reviewer usability, routing/index usefulness, and repeated-release measurements remain unverified. Local code/packaging gaps addressed here do not stand in for those acceptance results. No real evidence, approval, publication, dependency declaration, lockfile, provider, or project schema was changed.

## Historical packaging checkpoint — Patch B, engine 0.4.0, adapter 0.6.2

Executed 2026-10-04 using temporary synthetic workspaces and unpacked local distributions. Runtime modules and all 22 byte-identical current/legacy schemas now live under `src/second_brain/`. The console/module dispatcher exposes the existing operator commands, and `tools/kb_*.py` remain module-alias compatibility entry points. Installed init, skill synchronization, and reset require explicit workspace/checkout roots where needed; existing publication and reset confirmation logic is retained.

The five initial distribution regressions failed on the placeholder/missing module entry point. After packaging, a read-only deputy identified a module-search regression in worker startup; a hostile-cwd regression reproduced source-package execution before the repair. Both document worker paths now use `-P`, and the repaired six-case packaging suite passes outside the checkout. Tests transplant the package or unpack a built wheel into temporary directories without installing it; they cover every command help page, current/legacy schemas, document capture, packet generation, standalone extraction/verification, explicit roots, and hostile cwd isolation. The initial check-command fixture was corrected to use its existing `--inventory-only` flag instead of assuming a candidate exists.

| Command or check | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_contract_v02 tests.test_document_integration tests.test_global_index tests.test_cross_project tests.test_reset_project` | **147 tests passed** before the safe-path regression; final integration coverage is recorded at the later full-suite checkpoint. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_packaging` | **6 tests passed**, including hostile cwd. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv build --offline --sdist --wheel --out-dir /tmp/second-brain-package-safe` | PASS: source distribution and wheel built through the existing declared backend. |
| `SECOND_BRAIN_TEST_WHEEL=/tmp/second-brain-package-safe/second_brain-0.4.0-py3-none-any.whl UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_packaging` | **6 tests passed** against the built wheel outside the checkout. |
| Rebuild a wheel from `/tmp/second-brain-package-safe/second_brain-0.4.0.tar.gz` with `uv build --offline --wheel` | PASS: the sdist carries the package, schemas, and compatibility scripts. |
| Compare relocated schemas with Git HEAD bytes | PASS: all **22** schemas are unchanged, including legacy versions. |
| Sealed legacy `kb_check.py --stage2`, `kb_sync_skills.py --check`, and console `second-brain --help` through uv | PASS. |

Independent read-only review found no remaining packaging blocker after the safe-path repair. The first offline build failed because `uv-build` was not cached; a sandbox-network retry also failed DNS. The existing declared backend was then fetched through uv with authorized network access, and subsequent builds succeeded offline. No dependency declaration, lockfile, provider, project schema, real evidence, human approval, or release changed. This closes the local packaging gap, not GLM visual access or real-project acceptance.

## Historical suppressed-content checkpoint — patches E/G, engine 0.4.0, adapter 0.6.2

Executed 2026-10-04 using synthetic fixtures only. New regressions first reproduced image alt text, resource attributes, and missing-content-id warnings emitted from suppressed HTML descendants. Adapter 0.6.2 now suppresses those emissions while retaining the enclosing unavailable-content issue, its own references, visible siblings, and parser budgets. HTML email uses the same suppression behavior. Frozen adapter 0.6.0 and 0.6.1 compatibility is covered separately; prior evidence is not rewritten.

`UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_document_formats tests.test_document_integration tests.test_segments` passed **133 tests with 1 optional LibreOffice skip** before expanding the historical compatibility subtests. The suppression-focused command (`tests.test_document_formats -k suppressed`) passed all **3 tests** after failing before the fix. The additional compatibility subtests are included in the later packaging/full-suite checkpoint. No dependency, provider, configuration schema, real evidence, approval, or publication changed. Visual interpretation and representative human acceptance remain open.

## Historical blocking-fix checkpoint — patches E/F/J, engine 0.4.0, adapter 0.6.1

Executed 2026-10-04 using temporary synthetic workspaces. All five blocking review findings are addressed: inline HTML/EML code retains surrounding qualifiers; HTML line breaks preserve value boundaries; merged cells suppress unreliable header associations for the remainder of their table; review reports expose unchanged claims and complete event statements/date qualifications with numbered citations; and prior-release evidence links survive copying the exact report into an approved release. Current-run links remain relative; prior-release links use encoded absolute local file URIs and require the prior release to remain at its recorded location.

Focused regressions reproduced the extraction and report failures before their fixes. Further regressions cover relative CLI paths, HTML fragments, link encoding and byte-identical report copying, plus frozen adapter 0.6.0 compatibility. Adapter 0.6.1 applies to new captures; historical evidence identities and frozen artifacts are preserved, and cross-version comparisons remain explicitly incomparable. Prepared reports affected by the renderer change require regeneration and fresh substantive human review; approval hashes must not simply be replaced.

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **382 tests run, 381 passed, 1 skipped** (optional LibreOffice legacy `.ppt`). |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | PASS: sealed v0.1 run and records still verify. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_sync_skills.py --check` | PASS: skill mirrors match. |
| `git diff --check` | PASS. |

Independent read-only review found no remaining blocker within these five fixes. Broader D3/Patch G visual-fidelity acceptance remains open. No real evidence, review, approval, or release was changed. Dependencies, provider settings, and `project.json` v0.1 remain unchanged; validation used the existing uv environment with `--no-sync`.

## Historical Patch N checkpoint — access-scoped approved-release index, engine 0.4.0

Executed 2026-10-04 using temporary synthetic project workspaces only. `tools/kb_index.py` builds a deterministic derived JSON index from explicitly authorized, checked approved releases. Separate index-access 1.0 authorization selects whole approved project releases and an external output path; domain membership and referral grants do not grant index access. Current and optional historical entries retain qualified project/run/record ids, original statuses and events, descriptive ownership, and exact frozen source/representation/segment provenance. Query and check reconstruct the selection against live access, registry, configuration, source scope, publication history, pointers, and bound release artifacts before returning results. Pending candidates, referral outboxes, and intake proposals are not indexed as records.

Twenty-six new tests cover duplicate local ids, deterministic rebuilds, provenance and document locators, legacy file-level records, investigation findings, current/history separation, proposals and uncertain/future dates, release removals and rollback, unavailable inputs, access revocation, cross-domain isolation, stale or forged indexes, source-scope and pointer changes during builds, protected output paths, symlinks, locks, and CLI behavior. Tests also confirm that pending target-only referrals do not become indexed facts. All captures, approvals, and publications in these tests are synthetic fixtures. No real access policy, shared index, project evidence, review, or release was created or changed.

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_global_index tests.test_cross_project tests.test_contract_v02 tests.test_record_events tests.test_segments tests.test_source_scope` | **128 tests passed**. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **368 tests run, 367 passed, 1 skipped** (optional LibreOffice legacy `.ppt`). |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | PASS: sealed v0.1 run and records still verify. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_sync_skills.py --check` | PASS: skill mirrors match. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_index.py --help` and build/query subcommand `--help` | PASS: operator CLI loads; the synthetic CLI test also executes build/check/query. |
| `git diff --check` and explicit whitespace checks for the new index tool, schemas, tests, and ADR | PASS. |

These checks establish selection, integrity, access-set isolation, and provenance mechanics. They do not establish business approval, source authority, reviewer identity, semantic usefulness, or an as-of active business state. Access is a local operator authorization artifact, not authentication; revocation prevents tool queries but does not erase an already copied index. Whole-release access is coarse, and every query verifies the complete selected input set. The index is bounded to 16 MiB, 1,000 releases, and 10,000 entries. An operator must review real access and information handling, choose an external destination, and assess lookup usefulness with authorized evidence. D3 visual fidelity and packaging remain separate open work. No Stage 2 candidate was produced. Dependencies, provider settings, and `project.json` v0.1 are unchanged; checks use the existing uv environment with `--no-sync`. See [ADR 005](docs/architecture/adr/005-derived-approved-release-index.md).

## Historical Patch M checkpoint — reviewed target intake and lifecycle, engine 0.4.0

Executed 2026-10-04 with temporary synthetic origin and target project workspaces. `tools/kb_referrals.py` adds a target intake 1.0 ledger outside approved knowledge. Discovery validates explicit approved origins, publication history, review/report/routing bindings, frozen grants, and current registry grants; origin scan summaries distinguish a checked empty outbox from unavailable or unauthorized inputs. Human intake reviews record accept/decline/defer with reasons and exact origin-review binding. Acceptance only proposes capture/reconciliation and remains blocked without explicit full-file authorization or a reviewed, hash-bound scoped export preserving the qualified quote. Non-current sources block capture work while preserving history. Target links require independently published target records citing their own authorized evidence and show byte/representation/locator comparisons separately.

Twenty new intake tests cover exact discovery/decision retries, declines and deferrals, blocked acceptance, full-file scope, scoped exports, quote preservation, changed/withdrawn origins after acceptance, target-owned evidence ids, independently evolving releases, live disclosure revocation, stale/unavailable inputs, rollback, stale human review, symlinks, locks, provenance tampering, and release/registry changes during discovery. The initial focused failure was an assertion that identical source bytes implied an identical locator: the target used another filename, and the tool correctly reported differing locators. The assertion was corrected to preserve that distinction. A final targeted regression reproduced a review change after the initial pointer validation; intake now also compares the later manifest/records/review digests to the original `CURRENT.json` bindings, and that regression passes. No real project configuration, source, export, review, or release was used or modified.

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_cross_project` | **32 tests passed** before the final mutation regression; all 33 cross-project tests are included in the final focused/full commands below. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_cross_project.ReferralIntakeTests.test_review_changed_after_pointer_validation_is_not_imported tests.test_cross_project.ReferralIntakeTests.test_scope_and_source_changes_during_discovery_do_not_write_a_ledger` | **2 tests passed** after the pointer-binding repair. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_cross_project tests.test_contract_v02 tests.test_record_events tests.test_segments tests.test_source_scope` | **102 tests passed**. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **342 tests run, 341 passed, 1 skipped** (optional LibreOffice legacy `.ppt`). |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | PASS: sealed v0.1 run and records still verify. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_sync_skills.py --check` | PASS: skill mirrors match. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_referrals.py --help` and subcommand `--help` for discover/decide/link | PASS: operator CLI loads. |
| `git diff --check` | PASS. |

These checks establish deterministic intake and provenance mechanics, not semantic routing, export fidelity, permission for every line of a mixed file, reviewer identity, or business approval. Source-path/referral-slot predecessor links are operational review lineage, not inferred business supersession. Real authorized intake/usefulness remains unverified. An operator must assess target policy/access, supply real human intake reviews and scoped exports, and capture/check/review/publish target evidence normally. No Stage 2 candidate was produced by this tooling patch. Patch N's global approved lookup and D3 visual fidelity remain open. Dependencies, provider settings, and `project.json` v0.1 are unchanged; checks use the existing uv environment with `--no-sync` rather than rebuilding the editable package.

## Historical Patch L checkpoint — reviewed segment referrals and home scope, engine 0.4.0

Executed 2026-10-04 with synthetic temporary project workspaces only. The first routed fixture failed because registry 1.1 disclosure grants were absent. The checker now recomputes every mention from frozen registry/evidence, requires one R1–R4 assessment per hit, verifies exact segment-bound referral quotes and source-path grants, and prevents R2 target-only lines from supporting home records. Review 0.4 binds referral, mention, registry, work, and report inputs with a separate false-by-default cross-project check; a synthetic human-review publication test confirms a pending origin outbox is created only after approval. Tests also cover R3 dismissal, unresolved routing, R4 shape, ungranted destinations, live registry changes, tampered frozen policy, stale referral bytes, outbox integrity, old readers, and fail-closed records 0.5 re-anchoring. No real project registration, disclosure, reviewer, or release was used.

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_cross_project tests.test_contract_v02 tests.test_record_events tests.test_segments tests.test_source_scope` | **82 tests passed**. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **322 tests run, 1 skipped** (optional LibreOffice legacy `.ppt`). |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | PASS: sealed v0.1 run and records still verify. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_sync_skills.py --check` | PASS: skill mirrors match. |
| `git diff --check` | PASS. |

The tests establish structural and binding behavior, not that an R1–R4 judgment is semantically right or that all implicit references were found. A matching path grant plus human checks cannot prove that every line of a mixed source file is safe for target capture. Patch M must keep target intake and scoped export authorization separate. `project.json` v0.1, dependencies, and provider settings remain unchanged. The existing offline editable-package rebuild blocker (missing cached `uv-build`) persists, so validation used the existing uv environment with `--no-sync`. D3 visual fidelity remains independently open.

## Historical Patch K checkpoint — scoped project registry and mention candidates, engine 0.4.0

Executed 2026-10-04 using temporary synthetic projects only. The first focused run failed because `kb_mentions.py` was absent. Registry v1.0 now validates registered ids, names/aliases, information domains, and descriptive ownership paths outside `project.json` v0.1. The scanner checks sealed run snapshots and writes `work/mentions.json` with exact source lines, candidate targets, ambiguity markers, segment locators, and registry/manifest digests. Tests exercise case/accent normalization, word boundaries, same-domain filtering, overlapping aliases, duplicate normalized aliases, invalid ownership paths, unregistered home projects, changed registry output, and tampered frozen evidence. No real registry, referral, review, or release was created.

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_cross_project tests.test_source_scope tests.test_segments tests.test_contract_v02` | **67 tests passed**. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **315 tests run, 1 skipped** (optional LibreOffice legacy `.ppt`). |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | PASS: sealed v0.1 run and records still verify. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_sync_skills.py --check` | PASS: skill mirrors match. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_mentions.py --help` | PASS: CLI loads. |
| `git diff --check` | PASS. |

The scanner detects only explicit aliases. An alias hit is a candidate, not evidence that the passage concerns a target project, a semantic R1–R4 classification, a referral, or permission to disclose. Ownership paths are descriptive and are not used for automatic routing. No real-project detection quality was assessed. The existing offline editable-package rebuild blocker (missing cached `uv-build`) persists, so checks used the existing uv environment with `--no-sync`. Patch L is next for reviewed segment referrals and home-scope boundaries; D3 visual fidelity remains independently open.

## Historical Patch J checkpoint — pre-approval review report, engine 0.4.0

Executed 2026-10-04 with synthetic temporary project workspaces. Three focused tests first failed because `review-report.md` was absent. Preparation now renders the report from the checked candidate and frozen snapshots before any approval. Review 0.3 binds its exact bytes, and synthetic publication re-renders and copies it; changed or missing reports block publication. Tests cover source quote/context links, removed and unchanged records, malicious markup escaping, multiple warning occurrences, triaged files and segments with separate acknowledgement, unavailable visual extraction, qualified dates, stale candidate/report bytes, prior-release report tampering, and legacy review 0.2 readability. No real project source, human review, or release was touched.

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_contract_v02 tests.test_document_integration tests.test_stage2 tests.test_temporal tests.test_record_events tests.test_segments` | **187 tests passed**. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **309 tests run, 1 skipped** (optional LibreOffice legacy `.ppt`). |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | PASS: sealed v0.1 run and records still verify. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_sync_skills.py --check` | PASS: skill mirrors match. |
| `git diff --check` | PASS. |

The report is a deterministic review aid, not semantic validation, item-level disposition, or business approval. Real reviewer comprehension and effort remain unmeasured. `project.json` v0.1, dependencies, and provider settings remain unchanged. The prior offline editable-package rebuild blocker (missing cached `uv-build`) persists, so checks used the existing uv environment with `--no-sync`. Patch K is next for scoped registry/mention classification; D3 visual fidelity remains independently open.

## Historical Patch I checkpoint — chronology views, engine 0.4.0

Executed 2026-10-04 with synthetic fixtures and temporary workspaces. The first focused tests failed because `timeline.md` and packet `document-navigation.md` did not exist; an initial test fixture also lacked the existing `logical_id` needed by release-diff comparison, and was corrected without relaxing the implementation. Six permutations of adding 2026-09-29, 2026-10-03, and 2026-10-04 files yield identical final business timelines and document navigation. Rendering tests exercise all eight source categories, multiple events from one document, timezone-equivalent instants, approximate ranges, unknown and conflicting dates, and a future effective date. A synthetic publication test confirms that a review-bound records 0.4 release contains the timeline; re-anchored lost support disappears from it. No real approval or release was made.

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_chronology_views tests.test_record_events tests.test_temporal tests.test_contract_v02 tests.test_stage2` | **147 tests passed**. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **302 tests run, 1 skipped** (optional LibreOffice legacy `.ppt`). |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | PASS: sealed v0.1 run and records still verify. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_sync_skills.py --check` | PASS: skill mirrors match. |
| `git diff --check` | PASS. |

The view order is a deterministic navigation aid; structural checks do not prove event dates, authority, status, or active applicability. No as-of active-state view is generated because the current record contract does not establish all validity intervals and supersession rules. `project.json` v0.1, dependencies, and provider settings remain unchanged. The prior offline editable-package rebuild blocker (missing cached `uv-build`) remains, so validation used the existing uv environment with `--no-sync`. Patch J is the next text-based feature; D3 visual fidelity and real chronology/usefulness assessment remain open.

## Historical Patch H checkpoint — records 0.4, engine 0.4.0

Executed 2026-10-04 with synthetic fixtures and temporary test workspaces. The first focused test failed because records schema 0.4 did not exist. The added event contract passes multiple-events-per-source, known/future effective dates, unknown and conflicting dates, cited relative anchors, timezone-equivalent conflict rejection, invalid dates/ranges/references, and re-anchoring when event support disappears. The checker verifies structural links and date representation only; it cannot certify that a quoted source actually supports the proposed event or time.

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_record_events tests.test_segments tests.test_temporal` | **28 tests passed**. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **296 tests run, 1 skipped** (optional LibreOffice legacy `.ppt`). |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | PASS: sealed v0.1 run and records still verify. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_sync_skills.py --check` | PASS: skill mirrors match. |
| `git diff --check` | PASS. |

No dependency, provider, or `project.json` v0.1 change was made. The prior offline editable-package rebuild blocker (missing cached `uv-build`) remains; validation used the existing uv environment with `--no-sync`. No real source capture, event adjudication, human approval, or publication occurred. Patch I owns timeline/navigation and representative chronology across all eight categories.

## Historical Patch G/D3 integrity checkpoint — engine 0.4.0, adapter 0.6.0

Executed 2026-10-04 with synthetic fixtures and temporary test workspaces. A focused regression first failed because PNG IDAT had a valid chunk CRC but invalid zlib contents and was accepted. The bounded standard-library validator now rejects corrupt, oversized, truncated, or badly filtered scanlines, checks Adam7 row sizes and palette/IDAT order, and still leaves pixel values and visual meaning unavailable. The new 64×32 probe PNG has a false green text annotation; its visually inspected synthetic construction shows red/blue regions and a small yellow square. No approved GLM visual probe or human-scored representative reference set was run.

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_document_formats tests.test_document_integration` | **113 tests run, 1 skipped**. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **289 tests run, 1 skipped** (optional LibreOffice legacy `.ppt`). |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | PASS: sealed v0.1 run and records still verify. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_sync_skills.py --check` | PASS: skill mirrors match. |
| `git diff --check` | PASS. |

Adapter 0.6.0 is frozen in new document policies; historical evidence is not rewritten. There is no new dependency, provider, API call, or `project.json` change. The prior offline editable-package rebuild blocker (missing cached `uv-build`) remains, so validation used `--no-sync`. [The approved-assistant visual-access probe](docs/VISUAL_CAPABILITY_PROBE.md) and human reference comparison remain necessary before D3/Patch G or R2/R3 can close. No real source capture, review, approval, or publication occurred.

## Historical Patch G structural checkpoint — engine 0.4.0, adapter 0.5.0

Executed 2026-10-04 with synthetic SVG/PNG fixtures and temporary test workspaces. Initial focused capture tests failed with `unsupported_extension` for SVG/PNG; a later regression failed because inline SVG inside a suppressed HTML template emitted citable geometry. Both pass after the bounded structural adapters and suppression fix. The low-opacity SVG label, conflicting caption/cardinality, missing external image, and misleading PNG text annotation exercise honest source preservation and unavailable gaps, not successful visual interpretation.

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_document_formats tests.test_document_integration` | **110 tests run, 1 skipped**. SVG/PNG envelopes and limits, source labels/attributes, embedded-asset locators, integrity/tampering, original bytes, packets, and incomparable visual-policy delta pass. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_segments` | **8 tests passed** after adapting synthetic candidate coverage to the extra DOCX asset segment; the strict checker rule was unchanged. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **286 tests run, 1 skipped** (optional LibreOffice legacy `.ppt`). The first run exposed stale Patch D test assumptions about DOCX segment count and order; the corrected helper covers every frozen segment and the rerun passes. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | PASS: the sealed historical run and records still verify. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_sync_skills.py --check` | PASS: skill mirrors match. |
| `git diff --check` | PASS. |

No dependency, provider, package-version, or `project.json` schema change was made. Offline editable-package sync remains blocked by the previously missing cached `uv-build`; validation used the existing uv environment with `--no-sync`. PNG IDAT is not decoded or validated as pixel data, SVG is not rendered, and embedded images are not interpreted. The [interim manual review](docs/VISUAL_FIDELITY_REVIEW.md) leaves D3/Patch G visual fidelity and R2/R3 acceptance open. No real evidence capture, human approval, or publication occurred.

## Historical Patch F checkpoint — engine 0.4.0, adapter 0.4.0

Executed 2026-10-03 with synthetic fixtures and temporary test workspaces. Three initial focused tests failed because HTML lacked row segments and inventory/extractor APIs lacked an explicit structured CSV choice. The implementation now preserves source-stated table-row context and freezes a structured/raw CSV choice without changing `project.json` v0.1 or engine version.

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_document_formats tests.test_document_integration` | **93 tests run, 1 skipped**: dense model tables, quoted SQL text, row/status/date/unit context, merged cells, structured CSV header/literal preservation, invalid choices, policy tampering, capture/check/packets, and comparable/incomparable deltas. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **269 tests run, 1 skipped**: optional legacy `.ppt` LibreOffice conversion. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | PASS: sealed historical run and records still verify. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_sync_skills.py --check` | PASS: skill mirrors match. |

Patch F changed no dependencies, package version, or lockfile pins. The earlier offline editable-package rebuild blocker (`uv-build` absent from the cache after Patch D) remains; tests used the existing uv environment with `--no-sync`. Structural preservation does not prove the meaning of a relationship, state transition, value, or effective date. No real sources, human approvals, or releases were changed.

## Historical Patch E checkpoint — engine 0.4.0, adapter 0.3.0

Executed 2026-10-03 with synthetic fixtures and temporary test workspaces. Two initial focused tests failed with `unsupported_extension` for `.html` and `.eml`; they pass after the inert adapters were added. HTML without `--documents` retains its raw-text capture path. The new MIME attachment regression confirms that an attached email is inventoried rather than traversed as body evidence.

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest tests.test_document_formats tests.test_document_integration` | **79 tests run, 1 skipped**: HTML/EML structure, strict encodings, malformed inputs, budgets, attachment gaps, inventory/check/packets, and incomparable policy changes. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests` | **255 tests run, 1 skipped**: optional legacy `.ppt` LibreOffice conversion. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | PASS: sealed historical run and records still verify. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_sync_skills.py --check` | PASS: skill mirrors match. |

No dependency declarations, package version, or `uv.lock` pins changed for Patch E. The earlier Patch D offline editable-package rebuild blocker (`uv-build` absent from the cache) remains; checks used the existing uv environment with `--no-sync`. These tests establish structural behavior and integrity, not real HTML/EML fidelity, semantic interpretation, or approval. No real source run, review, or publication was performed.

## Historical Patch D checkpoint — engine 0.4.0

Executed 2026-10-03 with synthetic temporary workspaces and the existing uv environment. The focused regression first failed before the fix: identical original DOCX bytes with different extracted text received the same evidence id. The 0.4.0 implementation passes that test and the checks below.

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests -p 'test_segments.py' -v` | **8 tests OK**: derived text and parser-version identity, frozen locator/gap integrity, exact segment citations and coverage, moved/vanished support, and packet-boundary spans. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests -p 'test_document_integration.py' -v` | **12 tests OK** across document capture/check/packet paths. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python -m unittest discover -s tests -v` | **239 tests OK, 1 skipped**: the optional LibreOffice legacy `.ppt` test. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | PASS: sealed v0.1 run and its five records still verify. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked --no-sync python tools/kb_sync_skills.py --check` | PASS: canonical skill mirrors remain synchronized. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv sync --locked --offline` | **Blocked** at editable-package rebuild: `uv-build>=0.12.8,<0.13.0` is absent from the offline cache. Runtime dependencies already present in `.venv` permitted `--no-sync` validation. |

The package version alone changed from 0.3.0 to 0.4.0 in `pyproject.toml`; the matching root package entry in `uv.lock` was updated without changing dependency pins. `uv lock --offline` could not resolve `defusedxml` from the local cache, and `uv sync --locked --offline --check` correctly reported that the installed editable package is still 0.3.0. A later online or cache-complete `uv sync --locked` should refresh that package. No real source capture, human review, or publication was performed. The synthetic release-copy test does not constitute a real approval.

## Historical Patch C checkpoint — engine 0.3.0

Executed in the locked uv environment against synthetic fixtures. The focused source-scope test first failed before implementation because data, analysis, and policy registrations were missing; it passed after the patch. No real project was captured or published.

| Command | Result |
| --- | --- |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv sync --locked --offline` | PASS; lockfile and local environment synchronized without network access. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked python -m unittest discover -s tests -p 'test_source_scope.py' -v` | **9 tests OK**: all eight categories, mixed-content primary type, invalid registrations, unchanged/changed-scope deltas, frozen-sidecar and metadata tampering, legacy compatibility, initializer CLI, and synthetic release copy. |
| `UV_CACHE_DIR=/tmp/second-brain-uv-cache uv run --locked python -m unittest discover -s tests -v` | **231 tests OK, 1 skipped**: the optional LibreOffice legacy `.ppt` test. |

The new sidecar is exercised only in temporary test workspaces. The v0.1 requirement for one legacy source remains; segment-level classification and real extraction quality are outside Patch C.

## Historical Patch B checkpoint — engine 0.2.1

Executed 2026-10-02 on Linux x86_64 with Python 3.14.4 and uv 0.12.7. `uv sync` installed the dependencies declared in `pyproject.toml` and generated `uv.lock`; it did not change the dependency declarations. The commands below used the locked environment and synthetic test fixtures only.

| Command | Result |
| --- | --- |
| `uv run --locked python tools/kb_sync_skills.py --check` | PASS; `.claude/skills` and `.coda/skills` match `.agents/skills`. |
| `uv run --locked python -m unittest discover -s tests -p 'test_contract_v02.py' -v` | 37 tests OK. Includes Patch A historical verification, policy tampering, and incomparable-delta checks. |
| `uv run --locked python -m unittest discover -s tests -p 'test_document_integration.py' -v` | 12 tests OK. |
| `uv run --locked python -m unittest discover -s tests -v` | **222 tests OK, 1 skipped**: the opt-in legacy `.ppt` LibreOffice test. |
| `uv run --locked python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | Passed: 5 frozen fixture files and 5 records checked. |
| `uv sync --locked --offline --check` | Passed: environment matches the lockfile; no changes required. |

The removed demo and bundle-seal scripts were not run. The legacy v0.1 fixture remains in `tests/fixtures/` and verifies in the contract suite. These checks do not establish extraction quality on real evidence, backup restoration, or human approval. No real project workspace was available in this checkout.

## Historical engine 0.2.0 checkpoint

Executed 2026-10-01 on macOS (arm64) with Python 3.14.7 via uv 0.12.8, from the working tree described in `docs/DECISIONS_AND_GAPS.md` (decision note "engine 0.2.0"). The full verbose log is `validation/test-run-2026-10-01.txt`.

## Results observed

| Command | Result |
| --- | --- |
| `uv run python -m unittest discover -s tests -v` | **195 tests run: 194 OK, 1 skipped** (`test_real_legacy_ppt_conversion`, opt-in through `KB_TEST_LEGACY_PPT=1` and a local LibreOffice). |
| `uv run python tools/kb_sync_skills.py --check` | PASS: `.claude/skills` and `.coda/skills` match `.agents/skills`. |
| `uv run python tools/kb_check.py --run tests/fixtures/legacy-run-v0.1 --records tests/fixtures/legacy-run-v0.1/records.json --stage2` | passed; a 0.1.0-engine run verifies under the 0.2.0 engine; milestone met. |

## What the suite covers

- Previous coverage (163 tests): configuration and glob rules, inventory capture/blocking, identities and delta, document capture and tamper cases, exact citations, coverage, relations, investigations, packets, hash-bound review, and immutable publication.
- New in `tests/test_contract_v02.py` (32 tests):
  - schema-keyword strictness and `additionalProperties` enforcement;
  - the recorded-`tool_version` fingerprint;
  - legacy review reads;
  - `triaged_out` rules and triage acknowledgement;
  - per-occurrence warning acknowledgement and tamper detection;
  - rejection of 0.1 reviews at publish;
  - the code-only decision rule;
  - `ai_generated_source` by file name and by provenance;
  - semantic hints;
  - the `work/` copy, its review binding (a change after `--prepare` blocks publication), symlink refusal for files and directories, and early rejection of unpublishable names;
  - the rule that `--stage2` rejects an empty record set;
  - the open-questions, by-code and changes-since views;
  - re-anchoring: moved, vanished, dropped, write-once, no carry-over from an unapproved run, carry-over only for identical text from an approved release, the document text-hash key, and rejection of unknown coverage ids;
  - glob/grep packet selection with the coverage stub;
  - skill drift.
- Changed: the two former quota-gate tests now assert that the milestone is reported without failing.

## Limits

- Tests use synthetic fixtures only. They validate tools and contracts, not GLM extraction quality or business correctness.
- A passed checker is structural evidence, not semantic validation or approval.
- The historical files in `validation/` other than `test-run-2026-10-01.txt` record the 0.1.0 bundle (84 tests, Linux, Python 3.13.5) and are kept only as history.
- Not run: the opt-in legacy `.ppt` LibreOffice test or any real-project publication.
