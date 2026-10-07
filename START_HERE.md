# Start here — Stage 2

For an explicitly authorized targeted preparation, supply a `run-request` 1.0
and use `second-brain run create --dry-run` before capture. See
[targeted preparation](docs/CONFIG_REFERENCE.md#targeted-run-preparation).
Choose analysis-only for narrow investigation or project-refresh for a complete
snapshot. Strict isolation needs reviewed hashed UTF-8 exports; the engine never
opens their original references. Prior context needs separate permission for
the target run and eventual release audit copies. Preparation stops at manual
extraction. Fixed GLM behavior, semantic review and human approval/publication
remain required. Real capture, disclosure and pilot acceptance are separate.

This document is an executable procedure. Every step states either the exact
command to run (with exact parameters) or the exact skill prompt to give. Steps
are numbered; each step ends with **→ Next**, which tells you exactly which
step follows and what must be true before you proceed.

Cross-checked against `commands.sh` (the executable source of truth). Where the
two files disagreed, this file follows `commands.sh`; commands that exist in
only one of the two files are listed in [Reconciliation notes](#reconciliation-notes)
and in the companion file `START_HERE_EDGE_CASES.md`.

Notation: `PROJECT` and `RUN` are shell variables set in step 3. `RUN_ID` is
generated per `commands.sh`; the demo examples in `docs/` use fixed ids
such as `pilot-002`, which are equally valid values for `--run-id`.

---

## Part A — Follow the procedure for a single project

### Step 1 — Place and test the engine

- 1.1 Keep this folder in a company-approved local location, outside all
  registered source roots. Do not place it inside a source repository or a live
  Google Drive source folder.
- 1.2 The runtime is **Python 3.14 managed by `uv`** (`pyproject.toml` pins
  `>=3.14,<3.15`). Third-party dependencies declared in `pyproject.toml` are
  installed by `uv sync`: `python-docx`, `python-pptx`, `pypdf`, `defusedxml`
  (document capture) and `reportlab` (test fixtures). The core
  inventory/check/publish code uses only the standard library. No credentials,
  network access at runtime, model API, database, or Docker container is
  needed.
- 1.3 From the repository root, run exactly:

  ```bash
  uv sync --locked
  uv run --locked python -m unittest discover -s tests -v
  uv run --locked python tools/kb_sync_skills.py --check
  ```

- 1.4 Git provides the engine's integrity; there is no separate bundle hash
  check.
- 1.5 `uv run --locked second-brain --help` is the packaged command menu.
  The `tools/kb_*.py` commands below remain supported compatibility entry
  points. Installed commands use explicit workspace/checkout roots as described
  in [the CLI reference](docs/CONFIG_REFERENCE.md#packaged-commands).

**→ Next: Step 2.** Proceed only when the test suite passes and
`kb_sync_skills.py --check` reports no drift.

### Step 2 — Configure one small, question-driven pilot

- 2.1 Project workspaces are operator-created; none is included in this checkout.
  If `projects/demo/` is absent, use the `kb_init.py` command in step 2.5
  with `--project-id demo` and your approved source paths. Before capturing
  a run, copy `templates/PROJECT_POLICY.md` to `projects/demo/POLICY.md`.
  Write the **pilot question** there and the known owners and authority rules.
  Unknown authority stays *unknown*; do not guess an owner.
- 2.2 Narrow `projects/demo/config/project.json` to the files that
  question needs. Keep `schema_version: "0.1"` and the established field
  structure; change only values. A pilot must be small enough for a person to
  read every included file. Drop sources that have no content rather than
  leaving empty scopes.
- 2.3 Optionally add `projects/demo/config/source-provenance.json`,
  based on `templates/source-provenance.json` and actual export evidence:
  Drive URL, export time, comments/suggestions preservation, and for
  repositories the commit SHA (`git rev-parse HEAD` at capture time) as
  `revision`. Set `origin.authorship` to `human`, `ai_generated`, `mixed`, or
  `unknown`. Machine-written meeting summaries (for example "Notes by Gemini")
  raise an `ai_generated_source` warning from their file name unless provenance
  states the authorship. Do not reuse the template's timestamp or invent
  missing revision information.
- 2.4 Sources remain external and read-only to this workflow. Google Docs and
  other upstream materials must already have a reviewed local export. This
  engine does not perform a Google export or verify comments, suggestions, or
  tab fidelity. See [docs/SOURCE_FIDELITY.md](docs/SOURCE_FIDELITY.md).
- 2.5 To create a project workspace, run the implemented initializer (replace
  the example id, name, and source paths with approved values):

  ```bash
  uv run python tools/kb_init.py \
    --project-id my-project \
    --name "My project" \
    --source "requirements:requirements:/absolute/approved/requirements" \
    --source "repository:repository:/absolute/approved/repository" \
    --expanded-source "metrics:data:/absolute/approved/metrics" \
    --workspace projects/my-project
  ```

  (`--expanded-source` is optional; it writes `config/source-scope.json` for
  data, analysis, or policy sources. At least one legacy `--source` remains
  required by `project.json` v0.1. Per `commands.sh`, `--workspace` is optional;
  the default is this engine's `projects/<project-id>`.)

**→ Next: Step 3.** Proceed once the project `POLICY.md` exists, the pilot
question is written down, and `project.json` names only the files that
question needs.

### Step 3 — Freeze evidence and prepare packets

- 3.1 From the repository root, set the variables used by every later step
  (run-id pattern per `commands.sh`):

  ```bash
  PROJECT="projects/demo/config/project.json"
  RUN_ID="pilot-$(date +%Y%m%d-%H%M%S)"
  RUN="projects/demo/runs/$RUN_ID"
  ```

  (The demo docs use fixed ids such as `pilot-002`; either is a valid
  `--run-id` value. Pick one form and use it consistently for the run.)
- 3.2 Freeze the run — run exactly:

  ```bash
  uv run python tools/kb_inventory.py --project "$PROJECT" --run-id "$RUN_ID" --documents
  ```

- 3.3 Verify integrity — run exactly:

  ```bash
  uv run python tools/kb_check.py --run "$RUN" --inventory-only
  ```

- 3.4 Build packets — run exactly:

  ```bash
  uv run python tools/kb_packet.py --run "$RUN"
  ```

  Open `$RUN/packets/document-navigation.md` to browse selected packets by frozen document date or the undated group. This is document metadata, not the date of every event described inside a packet.

- 3.5 Proceed only when inventory returns `READY`. Inspect `manifest.json`,
  especially `sources`, `files`, and `issues`, plus `segments.snapshot.json` for locator spans and unavailable extraction issues. A blocked run is retained for
  diagnosis; fix the input or configuration and capture a new run id (step 3.1
  with a fresh `RUN_ID`). Never edit a manifest or overwrite its snapshots.
- 3.6 `--documents` freezes `.docx`, `.pdf`, `.xlsx`, `.pptx`, `.html`, `.eml`, `.svg`, and `.png` as three
  artifacts each: the original binary, a derived UTF-8 evidence text, and an
  `extraction.json` sidecar. The derived text is untrusted evidence with status
  `extracted_needs_review`. Extraction warnings must be acknowledged in the
  review like any other warning. Legacy `.ppt` additionally needs
  `--allow-legacy-ppt` and an approved local LibreOffice (`--soffice`). A
  document that fails extraction blocks the run.
  HTML is parsed inertly; external resources and scripts are not fetched or run.
  EML attachments are listed as metadata and their content remains unavailable
  until separately scoped and captured. Without `--documents`, HTML stays raw
  UTF-8 text and EML is unsupported.
  SVG labels and vector attributes are source structure, not verified rendered
  meaning; PNG capture validates the envelope and compressed scanline structure,
  and records dimensions/annotations without reconstructing pixel values.
  Embedded Office/PDF image locators likewise require comparison with the frozen
  original. See `docs/VISUAL_FIDELITY_REVIEW.md`.
  CSV remains raw text by default. When the source is a table needing row and
  column context, use `--documents --csv-representation structured`; declare
  `--csv-header first-row` only if the first record truly contains labels.
  The delimiter and encoding must be supplied explicitly when defaults do
  not match. These choices are frozen into the capture policy.
- 3.7 Packets are bounded at 16,000 Unicode characters, **not tokens**. When
  the configured scope is still larger than the question, replace step 3.4
  with question-scoped packets instead of reading everything:

  ```bash
  uv run python tools/kb_packet.py --run "$RUN" --select-glob 'src/workflows/demo/**' 'requirements/**' --grep "demo"
  ```

- 3.8 The selection is the union of `--select` evidence ids, `--select-glob`
  path globs (matched against the relative path or `source_id/relative_path`),
  and `--grep` case-insensitive terms. It also writes
  `packets/coverage-stub.json`: selected files start as `deferred` and
  everything else as `triaged_out`, with the selection method recorded. Honest
  triage is therefore the easy path.

**→ Next: Step 4.** Proceed only when inventory returned `READY`, the
inventory-only check passed, and packets exist for every manifest file you
intend to read.

### Step 4 — Use your existing GLM coding assistant

- 4.1 Open the repository in your approved editor/assistant.
- 4.2 Read `AGENTS.md`, `WORKFLOW.md`, `CONTRACT.md`, `POLICY.md`, and the
  project `POLICY.md` (the file created in step 2.1).
- 4.3 Give the assistant exactly this prompt: the full text of
  `prompts/00_START_STAGE2.md`, with its three placeholders replaced by:
  - `PROJECT_CONFIG`: `projects/demo/config/project.json` (the value of
    `$PROJECT` from step 3.1);
  - `RUN_DIR`: the value of `$RUN` from step 3.1;
  - `PILOT_QUESTION`: the bounded question recorded in
    `projects/demo/POLICY.md`.
- 4.4 That prompt directs a serial extraction → reconciliation → verification
  workflow over one packet or one small related group at a time. The assistant
  writes only to the run's `proposals/` (candidate and semantic review) and
  `work/` (helper scripts and their outputs, which publication copies into the
  release as audit material). It must not edit sources, manifests, tests,
  schemas, tools, instructions, review files, or approved knowledge.
- 4.5 The final candidate is `$RUN/proposals/records.json`. New runs use records schema 0.3 with file and segment coverage, or records 0.4 when proposing evidence-linked events. Records 0.4 requires an `events` array on every record (empty when no event is supported). Historical runs without a segment inventory retain their existing records contract.
- 4.6 Skills are kept in `.agents/skills/` and mirrored to `.claude/skills/`
  and `.coda/skills/`. After editing a skill, run exactly:

  ```bash
  uv run python tools/kb_sync_skills.py
  ```

  (Per `commands.sh`, add `--check` to only report drift.) The test suite
  fails on drift. The prompts are plain Markdown and can always be supplied
  manually.

**→ Next: Step 5.** Proceed only when the assistant has finished and
`$RUN/proposals/records.json` exists (it was produced by the skill-driven
extraction/reconcile phases; running step 5 before it exists fails with
`No such file or directory: .../proposals/records.json`).

### Step 5 — Check and review

- 5.1 Run the full Stage 2 gate — run exactly (form per `commands.sh`; it
  requires the `records.json` from step 4):

  ```bash
  uv run python tools/kb_check.py \
    --run "$RUN" \
    --records "$RUN/proposals/records.json" \
    --stage2 \
    --live \
    --report "$RUN/checks-$RUN_ID.json"
  ```

  (`--live` re-reads source files to confirm nothing changed since capture;
  `--report` persists JSON.)
- 5.2 Prepare the review — run exactly:

  ```bash
  uv run python tools/kb_publish.py --project "$PROJECT" --run "$RUN" --prepare
  ```

- 5.3 The checker report includes `coverage_counts`, the `stage2_milestone`
  (one of each record kind plus a relation; reported, not a gate), and
  `semantic_hints`. The hints flag single-line citations, pending language in
  decision quotes, and decisions that rest only on AI-generated summaries.
  Hints are prompts for the reviewer, not proof of a problem or its absence.
- 5.4 `--prepare` writes `$RUN/review.pending.json` (review schema 0.3) and `$RUN/review-report.md`, then prints each warning code with its occurrence count, the number of triaged-out inputs, and the hints. Read the report and navigate its frozen source links before saving your completed approval as `$RUN/review.json`:
  - set `decision`, your `reviewer` name, and a timezone-bearing
    `reviewed_at`;
  - set each check in `checks` only after you have done it;
  - copy the counts you consciously accept into `acknowledged_warnings` (for
    example `{"repository_revision_unrecorded": 262}`); they must equal
    `warning_summary.counts`;
  - set `triage_acknowledged: true` only if you accept that the inputs in
    `triaged_evidence_ids` were not read in full;
  - set `segment_triage_acknowledged: true` only if you accept the omitted segments listed in `triaged_segment_ids`;
  - keep the generated hashes (including `work_sha256` and `review_report_sha256`), `warning_summary`,
    record ids, and triage list unchanged, and record business-authority
    limitations in `notes`.
- 5.5 The review also binds the run's `work/` folder and exact `review-report.md` bytes: anything added or changed there after `--prepare` blocks publication until you prepare and review again. The report is regenerated against checked evidence at publication.
- 5.6 Do not set a check true just to make the command pass. If you request
  changes, leave publication blocked. If records change after review
  preparation, prepare and review again (rerun steps 5.1–5.4).

**→ Next: Step 6.** Proceed only when your completed `review.json` exists and
you genuinely approve.

### Step 6 — Publish explicitly

- 6.1 Only after your real review, run exactly:

  ```bash
  uv run python tools/kb_publish.py --project "$PROJECT" --run "$RUN" \
    --review "$RUN/review.json" --human-approved
  ```

- 6.2 Open `projects/demo/knowledge/approved/<run-id>/index.md`. The
  release includes the immutable records, review, evidence snapshots, the
  run's `work/` folder, record pages, `project-map.md`/`.mmd`,
  `open-questions.md` (the meeting agenda), `by-code.md` (RF-/RNF-/US- codes →
  records), `timeline.md` for reviewed records 0.4, and, from the second release on, `changes-since-<previous>.md`. The timeline preserves unknown and disputed event dates; it does not declare which business rule is active.
  `knowledge/approved/CURRENT.json` names the current release; old releases
  remain available.
- 6.3 No records are promoted automatically. Enforce assistant permissions in
  the work assistant and operating environment; a command-line flag is not a
  security boundary.

**→ Next: Step 7.** Proceed when a new source export arrives.

### Step 7 — Handle the next source update

- 7.1 After each new export (for example a new Gemini-notes meeting), capture
  an incremental run against the previous one — run exactly:

  ```bash
  uv run python tools/kb_inventory.py --project "$PROJECT" --run-id pilot-003 --baseline "$RUN" --documents
  ```

  (`--baseline` takes the previous ready run directory, per `commands.sh`.)
- 7.2 Carry the previous release into the new run — run exactly:

  ```bash
  uv run python tools/kb_reanchor.py --previous projects/demo/knowledge/approved/pilot-002 --run projects/demo/runs/pilot-003
  ```

- 7.3 Inspect the new delta first. Stable scope plus complete capture permits
  added/modified/removed comparisons; a changed scope or incomplete capture
  makes the comparison unavailable, and missing entries are never labeled
  deleted.
- 7.4 `kb_reanchor` finds every previous quote in the same logical file of the
  new run and writes `work/reanchored-records.json` plus
  `work/reanchor-report.json`. The report lists quotes that are unchanged,
  moved, ambiguous, or vanished, and records dropped for lack of evidence.
  Uncited coverage (`reviewed_no_record`, `triaged_out`) is carried over only
  when `--previous` is an approved release and the file's quotable text is
  identical (for documents, the derived text). From an unapproved run, such as
  the first demo pilot, nothing is carried over: its "read"
  declarations were never reviewed. Changed or new files start as `deferred`.
- 7.5 Review the report, extract only the delta, then check, review, and
  publish a complete new snapshot: before rerunning steps 3.3–3.4, set
  `RUN_ID` to the new run id (from step 7.1) and `RUN` to
  `projects/demo/runs/$RUN_ID`, then rerun steps 3.3–3.4 for the new
  run, and finally steps 4–6 with the new run.
- 7.6 Record review minutes per release in `templates/PILOT_SCORECARD.md`;
  after three releases decide go / revise / stop per
  [docs/PILOT_ACCEPTANCE.md](docs/PILOT_ACCEPTANCE.md).

**→ Next:** this is the loop's end. Each subsequent source update repeats
steps 3–7 with a new run id.

---

## Part B — Then follow the procedure for the global knowledge base

There is no single "global run" command. The engine's knowledge base is the
union of the per-project approved releases; the global level is reached by
running Part A per project and reading the approved results.

- B.1 For every project, run steps 1–7 of Part A with that project's
  `projects/<id>/config/project.json` as `PROJECT` and its own run ids.
  Workspaces for additional projects are created with the `kb_init.py` command
  in step 2.5 (one workspace per project; the initializer refuses an existing
  workspace).
- B.2 Each project's current approved release is named by that project's
  `knowledge/approved/CURRENT.json`; old releases remain available (step 6.2).
  The global picture is the set of these per-project current releases.
- B.3 The engine-level pieces shared across projects are the ones from step 1:
  the `uv` runtime, the test suite, and the skill mirrors (`.agents/skills/`
  mirrored to `.claude/skills/` and `.coda/skills/`), kept in sync with
  `uv run python tools/kb_sync_skills.py` (or `--check` to only report drift).
- B.4 Patch K provides an optional, operator-maintained `projects/registry.json`
  and a local candidate scan: `uv run python tools/kb_mentions.py --run <run>
  --registry projects/registry.json`. It writes `work/mentions.json` from frozen
  evidence and freezes the registry value in `work/`; see [configuration and CLI
  reference](docs/CONFIG_REFERENCE.md). Patch L adds a complete run-local
  `proposals/referrals.json` for records 0.5, review 0.4, and a post-approval
  origin outbox. It requires explicit disclosure grants in registry 1.1. There
  is no real registry in this checkout. Patch M adds `kb_referrals.py discover`
  with explicit target/origin configurations and registry 1.1, then `decide`
  with a human-authored accept/decline/defer artifact. The separate target intake
  ledger deduplicates scans and preserves corrections, withdrawals, and stale
  sources. Accepted work stays blocked until full-file authorization or a reviewed
  scoped export is supplied. Capture authorized evidence in the target's own run
  and repeat Part A normally; `kb_referrals.py link` can then record target-owned
  evidence and release linkage. See the [CLI reference](docs/CONFIG_REFERENCE.md).
  Patch N adds `kb_index.py build/check/query` over explicitly authorized approved
  releases. An operator-maintained access file names projects, domain, and an
  external output chosen after information-handling review. Current results are
  the default; historical lookup requires an explicit history build. Checked
  queries preserve each record's status and exact project/release/evidence links
  and reject stale access or unavailable inputs. No real access file or shared
  index exists here. Do not merge records across projects or treat an alias hit
  as permission to disclose.

---

## Reconciliation notes (START_HERE.md vs commands.sh)

Resolved in favor of `commands.sh`:

- **Stage 2 check (step 5.1).** The old text ran
  `kb_check.py --run "$RUN" --stage2 --report "$RUN/checks.json"`.
  `commands.sh` step 6 additionally passes `--records
  "$RUN/proposals/records.json"` and `--live`, and names the report
  `checks-$RUN_ID.json`. The rewritten step uses the `commands.sh` form. (The
  checker defaults `--records` to `<run>/proposals/records.json`, so the old
  form was functionally equivalent, but `--live` was missing.)
- **Run id (step 3.1).** `commands.sh` generates a timestamped run id
  (`pilot-$(date +%Y%m%d-%H%M%S)`); the old text hard-coded `pilot-002`. Both
  are valid values; the pattern follows `commands.sh` and fixed ids remain
  valid (kept in step 7's examples).
- **`kb_init.py` (step 2.5).** `commands.sh` includes `--workspace`; the old
  text omitted it. Added, noted as optional.
- **`kb_sync_skills.py`.** Both files are consistent: `--check` only reports
  drift (step 1.3), plain form writes the mirrors (step 4.6).

Commands present in only one file (preserved, not dropped):

- Only in `commands.sh`: inventory tuning flags `--document-timeout`,
  `--max-file-bytes`, `--max-total-bytes`, `--max-files` (all optional, used
  with step 3.2); packet variants `--max-chars` and `--select` (step 3.7
  variants); standalone document snapshots
  `uv run python tools/kb_extract_document.py --source <file> --out <dir>`
  and re-verification with `--verify <dir>` (optionally `--compare-source
  <file>`); direct exercise of the `kb_document_extractors.py` library (no
  CLI; invoked internally by `kb_inventory.py --documents` and
  `kb_extract_document.py`). None of these are part of the required
  procedure, so they are not steps; see `START_HERE_EDGE_CASES.md` for where
  they apply.
- Only in the old `START_HERE.md`: the two-glob `--select-glob 'a/**' 'b/**'`
  packet example (valid — the flag accepts multiple values) and the explicit
  `kb_reanchor.py` example paths (also present in `commands.sh`'s re-anchor
  section). Both kept.
