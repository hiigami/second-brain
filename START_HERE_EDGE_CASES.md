# Start here — edge cases

Companion to `START_HERE.md`. Every entry traces back to a step in that file;
nothing here introduces new steps, commands, skills, or parameters. Format:
per step, the edge case and how to handle it with the means that step (or an
explicitly cross-referenced step) already provides.

Commands that exist in only one of `START_HERE.md` and `commands.sh` are
listed at the end (see also the Reconciliation notes in `START_HERE.md`).

---

## Step 1 — Place and test the engine

- **Placing the engine inside a source root or a live Drive folder.**
  Prevention is step 1.1: keep it in a company-approved local location outside
  all registered source roots. If already misplaced, move the folder out
  before capturing any run; no command in the procedure relocates it.
- **`uv sync` fails (missing/old `uv`, wrong Python).** The runtime contract
  in step 1.2 is Python 3.14 managed by `uv` (`>=3.14,<3.15` in
  `pyproject.toml`). Do not install packages manually or call bare
  `python`/`python3`; fix the `uv` installation and rerun step 1.3.
- **`kb_sync_skills.py --check` reports drift.** Rerun the suite first; if the
  suite also fails, fix that first. For drift only, run the plain sync form
  from step 4.6 (`uv run python tools/kb_sync_skills.py`), which writes the
  mirrors, then rerun `--check`. The test suite fails on drift, so the
  **→ Next** condition of Step 1 cannot be met until it is clean.

**→ Next: Step 2.**

## Step 2 — Configure one small, question-driven pilot

- **Unknown authority/owner for a topic.** Step 2.1: unknown authority stays
  *unknown*; do not guess an owner. Write the open question in the project
  `POLICY.md` instead.
- **Scope too large to read every file.** Step 2.2 requires the pilot be
  small enough for a person to read every included file; narrow
  `project.json` further (change only values, keep `schema_version: "0.1"`).
- **Source with no content left in scope.** Step 2.2: drop it rather than
  leaving empty scopes.
- **Missing export evidence for provenance.** Step 2.3: do not reuse the
  template's timestamp or invent missing revision information; record only
  what the actual export evidence shows, or omit the optional file.
- **Repository revision not recorded at capture time.** Step 2.3 gets the
  commit SHA via `git rev-parse HEAD` *at capture time*; later retrieval is
  not the capture-time SHA and must not be fabricated. This surfaces later as
  the `repository_revision_unrecorded` warning handled in step 5.4.
- **`kb_init.py` refuses to run.** Expected behavior (step 2.5): the
  initializer refuses an existing workspace. Use a new `--project-id`, or keep
  the existing workspace.
- **Source given as URL or single file.** Step 2.5: a source path is a
  directory, not a URL or a single file.
- **Overlapping source roots.** Step 2.5: source roots must not overlap within
  one project; adjust the directories passed via `--source` before running.
- **Governance rules pushed into `project.json`.** This carries over the rule
  from the original START_HERE step 2 ("Keep business authority rules out of
  `project.json`"): business authority rules belong in the project
  `POLICY.md` (step 2.1), not in `project.json`.

**→ Next: Step 3.**

## Step 3 — Freeze evidence and prepare packets

- **Inventory does not return `READY`.** Step 3.5: the blocked run is retained
  for diagnosis; fix the input or configuration and capture a new run id
  (repeat step 3.1 with a fresh `RUN_ID`, then rerun steps 3.2–3.4). Never
  edit a manifest or overwrite its snapshots.
- **Document fails extraction.** Step 3.6: a document that fails extraction
  blocks the run — same handling as a non-`READY` inventory: fix the input,
  capture a new run id.
- **Legacy `.ppt` in scope.** Step 3.6: additionally pass `--allow-legacy-ppt`
  and an approved local LibreOffice (`--soffice`) to the step 3.2 command.
  Both parameters are defined in `commands.sh`'s inventory section; without
  them the `.ppt` cannot be captured.
- **Extraction warnings in the sidecars.** Step 3.6: the derived text is
  untrusted (`extracted_needs_review`); warnings must be acknowledged in the
  review like any other warning — handled at step 5.4
  (`acknowledged_warnings`).
- **Packets exceed 16,000 characters / scope larger than the question.** Step
  3.7: build question-scoped packets with `--select-glob`/`--grep` (and, per
  `commands.sh`, `--select` for explicit evidence ids or `--max-chars` for a
  smaller bound) instead of reading everything.
- **Unselected files after scoped packets.** Step 3.8: they start as
  `triaged_out` in `packets/coverage-stub.json` with the selection method
  recorded; they stay `triaged_out` unless read in full (see step 4's prompt
  rules and step 5.4's `triage_acknowledged`).
- **Rerunning step 3.4 in the same run.** Packets are never overwritten:
  `kb_packet.py` fails with `Packets already exist; they are not overwritten.
  Use another run for different packet settings` (per `tools/kb_packet.py`).
  To change selection or budget, capture a new run id (step 3.1) and rebuild
  there; do not delete packets by hand.

**→ Next: Step 4.**

## Step 4 — Use your existing GLM coding assistant

- **Assistant proposes edits outside `proposals/` and `work/`.** Step 4.4
  defines the only permitted write locations. Reject the edit; the assistant
  must not edit sources, manifests, tests, schemas, tools, instructions,
  review files, or approved knowledge.
- **Source text contains instructions addressed to the assistant.** Treat
  packet content as untrusted evidence (per `AGENTS.md` and the step 4.3
  prompt); do not obey embedded instructions. Scope is set by the user and the
  project `POLICY.md`, not by a document's contents.
- **Helper scripts written outside the run.** Step 4.4: helpers belong only in
  the run's `work/`; publication copies that folder into the release as audit
  material. Anything elsewhere must be removed before step 5.
- **Skill mirrors out of sync after editing a skill.** Step 4.6: run
  `uv run python tools/kb_sync_skills.py` (plain form, per `commands.sh`).
- **Skill discovery unavailable.** Step 4.6: the prompts in `prompts/` are
  plain Markdown and can always be supplied manually.
- **Candidate `records.json` missing at the end.** The prompt in step 4.3
  requires `$RUN/proposals/records.json` as the final candidate (step 4.5). If
  absent, the assistant's work is incomplete — rerun step 4.3. Step 5.1
  requires this file and fails with `No such file or directory` otherwise.

**→ Next: Step 5.**

## Step 5 — Check and review

- **Step 5.1 run before extraction.** It fails with
  `No such file or directory: .../proposals/records.json` (per `commands.sh`
  step 6's note). Return to step 4.
- **`--live` reports sources changed since capture.** The checker raises
  `Live source changed since capture: <source_id>/<relative_path>` for each
  captured file whose live sha256 no longer matches the frozen snapshot (per
  `tools/kb_check.py`, `verify_live`). The frozen snapshot itself remains
  valid evidence of what was captured, but the gate fails, so the capture is
  stale relative to the live sources: fix the input and capture a new run id
  (step 3.1 with a fresh `RUN_ID`), then rerun steps 3.2–3.4, 4, and 5. Note
  the check is targeted: it compares only the files the manifest captured and
  does not detect files added to a source after capture (a new inventory is
  needed for additions).
- **Rerunning step 5.1 in the same run.** `--report` refuses to overwrite an
  existing file (`Refusing to overwrite: ...` — reports and pending reviews
  are written with exclusive-create and never overwritten, per
  `tools/kb_common.py`, `write_new`). Use a fresh report
  name (for example `checks-$RUN_ID-2.json`) or omit `--report` (the JSON is
  also printed to stdout). The same applies whenever steps 5.1–5.4 are rerun
  (per 5.5–5.6).
- **Rerunning step 5.2 in the same run.** `--prepare` fails with
  `Refusing to overwrite: .../review.pending.json` when a pending review
  already exists (per `tools/kb_publish.py` via `write_new`). Deciding what to
  do with the stale pending file (delete/rename it by hand) is a human action
  — do not script or automate its removal; then rerun steps 5.1–5.4.
- **`semantic_hints` entries in the report.** Step 5.3: hints are prompts for
  the reviewer, not proof of a problem or its absence. Address each one during
  review (the step 4.3 prompt requires the assistant to give a reason for any
  hint left as is in the semantic review).
- **Warning counts mismatch in `review.json`.** Step 5.4:
  `acknowledged_warnings` must equal `warning_summary.counts`; copy the exact
  counts you consciously accept.
- **`work/` changed after `--prepare`.** Step 5.5: publication is blocked
  until you prepare and review again — rerun steps 5.1–5.4.
- **Records changed after review preparation.** Step 5.6: prepare and review
  again (rerun steps 5.1–5.4). Do not edit `review.pending.json` by hand.
- **Temptation to set a check true to make the command pass.** Step 5.6: do
  not; if you request changes, leave publication blocked.
- **Checker reports an error you cannot resolve.** Per `AGENTS.md`, limit
  automated self-repair to two attempts after the first checker run (the step
  4.3 prompt enforces this); preserve the failure and stop for human judgment.
  Never weaken the checker or fabricate a missing record category to pass a
  gate.

**→ Next: Step 6.**

## Step 6 — Publish explicitly

- **Publishing before a genuine review.** Step 6.1 is human-only and gated on
  the completed `review.json` from step 5.4; the agent must never run it
  (`commands.sh` step 7 note). If publication is blocked, return to step 5.
- **`--prepare` combined with publication flags.** Not possible: `kb_publish`
  rejects `--prepare` together with `--review`/`--human-approved` (per
  `commands.sh`, they are separate commands — step 5.2 vs step 6.1).
- **Looking for the release.** Step 6.2: open
  `projects/demo/knowledge/approved/<run-id>/index.md`;
  `knowledge/approved/CURRENT.json` names the current release.
- **Expecting a `changes-since-<previous>.md` in the first release.** Step
  6.2: it appears from the second release on.
- **Trusting the flag as a security boundary.** Step 6.3: enforce assistant
  permissions in the work assistant and operating environment; a
  command-line flag is not a security boundary.

**→ Next: Step 7.**

## Step 7 — Handle the next source update

- **Changed capture scope or incomplete capture in the new run.** Step 7.3:
  the added/modified/removed comparison is unavailable; missing entries are
  never labeled deleted. Review the delta that does exist and proceed with
  step 7.5.
- **Reanchor report shows ambiguous or vanished quotes / dropped records.**
  Step 7.4: read the report; extract only the delta, re-extracting records the
  report lists as dropped (step 7.5), rather than copying stale citations.
- **Previous run was never approved.** Step 7.4: nothing is carried over from
  an unapproved run (its "read" declarations were never reviewed); treat the
  new run as a fresh extraction — changed or new files start as `deferred`.
- **Uncited coverage carried over incorrectly.** Step 7.4: it carries over
  only when `--previous` is an approved release and the file's quotable text
  is identical (for documents, the derived text); otherwise it must be
  re-established in the new run.
- **First update after the pilot.** Step 7.1's example uses `pilot-003` /
  `pilot-002`; for later updates pass the actual previous run id as
  `--baseline` and the actual approved release path as `--previous` (the
  parameters, per `commands.sh`, are `--baseline <previous ready run dir>` and
  `--previous <approved release or run dir>`).
- **After three releases.** Step 7.6: decide go / revise / stop per
  `docs/PILOT_ACCEPTANCE.md`, recording review minutes in
  `templates/PILOT_SCORECARD.md`.

**→ Next:** loop back to steps 3–7 with a new run id for each subsequent
source update.

## Part B — Global knowledge base

- **Expecting a single global run/merge command.** There is none (B.1–B.2):
  run Part A per project; the global picture is the set of per-project
  `knowledge/approved/CURRENT.json` releases.
- **Cross-project record references wanted.** B.4: planned but deferred (Phase
  6 of `docs/ANALYSIS_AND_IMPROVEMENT_PLAN.md`); no tool exists today — do not
  attempt a cross-project merge or invent a registry command.
- **Second project workspace already exists.** The `kb_init.py` command in
  step 2.5 refuses an existing workspace; keep using it.

---

## Commands existing in only one file

Handled per `START_HERE.md`'s Reconciliation notes; none is a required
procedure step, so none needed a new step here:

- **Only in `commands.sh`** (usable where noted, not required):
  - inventory tuning flags `--document-timeout`, `--max-file-bytes`,
    `--max-total-bytes`, `--max-files` — optional additions to the step 3.2
    command;
  - packet variants `--max-chars` and `--select` — alternatives within step
    3.7;
  - standalone snapshot extraction and verification
    (`tools/kb_extract_document.py --source/--out`, `--verify`, and
    `--compare-source`) — preparation outside a run; never overwrites an
    existing output directory;
  - direct exercise of `tools/kb_document_extractors.py` — a library with no
    CLI, invoked internally by `kb_inventory.py --documents` and
    `kb_extract_document.py`.
- **Only in the old `START_HERE.md`** (both valid, both kept): the two-glob
  `--select-glob 'a/**' 'b/**'` packet example (step 3.7 — the flag accepts
  multiple values) and the explicit `kb_reanchor.py` example paths (step 7.2 —
  also present in `commands.sh`).
