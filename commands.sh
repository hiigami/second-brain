#!/usr/bin/env bash
# Reference commands for the Work Second Brain engine. All Python runs via uv.
# Sections are menus, not a single pipeline: copy the lines you need.
set -euo pipefail
cd "$(dirname "$0")"

# Operator-created workspace; verify this file and its approved source paths first.
PROJECT="projects/demo/config/project.json"
RUN_ID="pilot-$(date +%Y%m%d-%H%M%S)"
RUN="projects/demo/runs/$RUN_ID"

# =============================================================================
# RUN ORDER: execute the numbered sections in this order for each new run
# =============================================================================
#
#   1. [step 1] Inventory (kb_inventory.py)
#        Freezes the run; state INVENTORY_READY.
#   2. [step 2] Inventory-only check (kb_check.py --inventory-only)
#        Integrity of manifest/snapshots/packets. No records needed.
#   3. [step 3] Packets (kb_packet.py)
#        Builds evidence packets; state PACKETS_READY.
#   4. [step 4] Extraction (kb-extract skill, prompts/01_EXTRACT.md)
#        Skill/prompt-driven work (no CLI). Creates $RUN/proposals/records.json.
#   5. [step 5] Reconcile (kb-reconcile skill, prompts/02_RECONCILE.md)
#        Skill/prompt-driven work (no CLI). Reconciles records.json.
#   6. [step 6] Stage 2 check (kb_check.py --stage2 --records ...)
#        REQUIRES records.json produced by steps 4-5. Running it before
#        extraction fails with:
#        "No such file or directory: .../proposals/records.json"
#   7. [step 7] Publication (kb_publish.py)
#        Human-only steps; the agent must never run these.
#
# Notes:
#   - Steps 4-5 are AI-assisted extraction/reconciliation guided by the
#     skills and prompts, not tool commands; nothing to run in this file.
#   - The inventory-only check (step 2) can run at any time after step 1.
#   - Sections below without a step number (one-time setup, extractor
#     library, standalone snapshots, re-anchor) are outside the per-run
#     order: setup runs once per workspace, re-anchor only when carrying a
#     previous release into a new run.
# =============================================================================

# --- One-time setup ---------------------------------------------------------

# Install Python 3.14 and the dependencies from pyproject.toml, then run the suite.
# uv sync --locked
# uv run --locked python -m unittest discover -s tests -v
# Mirror .agents/skills into .claude/skills and .coda/skills (add --check to only report drift).
# uv run python tools/kb_sync_skills.py

# Create a new project workspace. --source repeats per source, format
# id:type:/absolute/path with type in:
#   requirements | architecture | meetings | sql | repository
# uv run python tools/kb_init.py \
#   --project-id my-project \
#   --name "My Project" \
#   --source "req:requirements:/absolute/path/to/requirements" \
#   --source "repo:repository:/absolute/path/to/repo" \
#   --expanded-source "metrics:data:/absolute/path/to/metrics" \
#   --workspace projects/my-project
# Expanded sources are optional and go in config/source-scope.json; at least one
# base --source is still required by frozen project.json v0.1.

# --- [step 1] Inventory: freeze a new run -----------------------------------

# Add --documents to also capture .docx/.pdf/.xlsx/.pptx as evidence
# (parsers are dependencies in pyproject.toml, installed by uv sync).
uv run python tools/kb_inventory.py \
  --project "$PROJECT" \
  --run-id "$RUN_ID" \
  --documents

# Document-capture tuning (all optional, used with --documents):
#   --allow-legacy-ppt            opt in to local LibreOffice conversion for legacy .ppt
#   --soffice /path/to/soffice    approved soffice executable for legacy .ppt
#   --document-timeout 90         per-document worker wall-clock timeout (seconds)
# Capture-budget defaults, adjustable with or without --documents:
#   --max-file-bytes 2000000      per-file byte cap
#   --max-total-bytes 50000000    total byte cap
#   --max-files 2000              file count cap
# Incremental capture against a previous ready run directory:
#   --baseline "projects/demo/runs/<previous-run-id>"

# --- Document extractor library (no CLI; used internally) --------------------

# tools/kb_document_extractors.py is a library, not a CLI: it is invoked
# automatically by `kb_inventory.py --documents` and `kb_extract_document.py`
# below, so no separate run is needed in the normal workflow. To exercise it
# directly, call extract_bytes() from Python (example verified with a CSV):
#
# uv run python -c "
# import sys; sys.path.insert(0, 'tools')
# from pathlib import Path
# from kb_document_extractors import extract_bytes
# raw = Path('/absolute/path/to/file.docx').read_bytes()
# result = extract_bytes(raw, 'file.docx')
# print(result.metadata['status'], len(result.metadata['segments']))
# print(result.text)
# "
# Formats: .docx .pptx .pdf .xlsx .csv (.ppt only with allow_legacy_ppt=True
# in Options). Output status is always extracted_needs_review.

# --- Standalone document snapshots (no run needed) ---------------------------

# Extract one document into a new snapshot directory (never overwrites).
# For legacy .ppt add --allow-legacy-ppt (and --soffice if not on PATH).
uv run python tools/kb_extract_document.py \
  --source "/absolute/path/to/requirements.docx" \
  --out "./prepared/requirements-001"

# Re-verify a snapshot's integrity; optionally also check the live original
# is byte-identical to what was captured.
uv run python tools/kb_extract_document.py \
  --verify "./prepared/requirements-001" \
  --compare-source "/absolute/path/to/requirements.docx"

# --- [step 2] Check: verify a run (inventory-only) ---------------------------

# Integrity-only check of manifest, snapshots, and packets
# (no records needed; run any time after step 1).
uv run python tools/kb_check.py \
  --run "$RUN" \
  --inventory-only

# --- [step 3] Packets: build evidence packets --------------------------------

# Default: one packet per captured file.
uv run python tools/kb_packet.py \
  --run "$RUN"

# Variants: cap packet text length, or build a question-scoped subset. Selection
# is the union of evidence ids, path globs (relative path or source_id/relative
# path), and case-insensitive grep terms; unselected files stay explicit in
# index.json and packets/coverage-stub.json starts them as triaged_out.
# uv run python tools/kb_packet.py --run "$RUN" --max-chars 8000
# uv run python tools/kb_packet.py --run "$RUN" --select E-0123456789abcdef01234567
# uv run python tools/kb_packet.py --run "$RUN" --select-glob 'src/workflows/demo/**' --grep "demo"

# --- [steps 4-5] Extraction and reconcile: skill/prompt-driven, no CLI -------
#
# Run the kb-extract skill with prompts/01_EXTRACT.md to read packets and
# produce $RUN/proposals/records.json, then the kb-reconcile skill with
# prompts/02_RECONCILE.md to reconcile it. There is no tool command for
# these steps; the Stage 2 gate in step 6 needs their output to exist.

# --- [step 6] Check: full Stage 2 gate ---------------------------------------

# Full Stage 2 gate against the candidate records. REQUIRES
# $RUN/proposals/records.json to exist first; that file is produced by
# steps 4-5 (extraction and reconcile, skill/prompt-driven work), so
# running this before extraction fails with "No such file or directory".
# --live re-reads source files to confirm nothing changed since capture.
# --report persists JSON.
# uv run python tools/kb_check.py \
#   --run "$RUN" \
#   --records "$RUN/proposals/records.json" \
#   --stage2 \
#   --live \
#   --report "$RUN/checks-$RUN_ID.json"

# --- Re-anchor: carry the previous release into a new run ---------------------

# Writes work/reanchored-records.json and work/reanchor-report.json in the new run.
# uv run python tools/kb_reanchor.py \
#   --previous "projects/demo/knowledge/approved/<previous-run-id>" \
#   --run "$RUN"

# --- [step 7] Publication (human-only steps; the agent must never run these) -
# Prepare review.pending.json (all approval checks false; prints warning counts,
# triage, and reviewer hints):
# uv run python tools/kb_publish.py --project "$PROJECT" --run "$RUN" --prepare
# After human review, publish with an explicit approval file:
# uv run python tools/kb_publish.py --project "$PROJECT" --run "$RUN" \
#   --review "$RUN/review.json" --human-approved

# --- Project reset (operator-only; outside the per-run order) -----------------

# Remove everything in the project workspace except config/project.json. The
# first form is a dry run. Back up runs/ and knowledge/ first: they are
# git-ignored and unrecoverable once deleted. Add --delete-approved-releases
# when knowledge/approved holds releases. The agent must never run this.
# uv run python tools/kb_reset_project.py --project "$PROJECT"
# uv run python tools/kb_reset_project.py --project "$PROJECT" --confirm demo
