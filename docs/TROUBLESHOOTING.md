# Troubleshooting and recovery

## Missing or empty source

Each configured path must be a readable directory. An individually empty source is an `empty_source_scope` warning; a run with no captured file at all is blocked. Globs are relative to that directory. An initializer's repository defaults expect top-level src, tests, or docs. Remove an unused source entry or narrow/change the scope deliberately; do not manufacture content for it.

## Unsupported input, encoding, or long line

Inventory does not convert media, cloud shortcut, or other unsupported files. Supply a reviewed UTF-8 representation and record its limitations. Never silently discard relevant comments or content. For a packet line exceeding its budget, raise the character budget explicitly or prepare a reviewed structured excerpt with provenance. No truncation fallback is performed.

## Document extraction failures (`--documents`)

A document that fails extraction is a blocking `file_not_captured` error naming the source path and the extractor code; the run stays blocked and is never silently downgraded to an empty or text snapshot. Common codes and the next human action:

- `dependency_missing` — run `uv sync`; the parsers are dependencies in `pyproject.toml`. Nothing is installed at runtime; the error names the missing distribution.
- `extraction_budget_exceeded` — the document exceeds a configured limit (pages/slides, cells, segments, output size). Narrow the scope, split the document, or deliberately raise the relevant limit for a new run.
- `legacy_ppt_opt_in_required` — legacy `.ppt` needs `--allow-legacy-ppt` plus an approved local LibreOffice via `--soffice`; exporting a reviewed `.pptx` is usually the better path. The optional legacy-`.ppt` test is skipped unless `KB_TEST_LEGACY_PPT=1` is set and LibreOffice is approved locally.
- `encrypted_document` / `format_mismatch` / `invalid_text` — the original itself is unreadable, renamed, or password-protected. Recapture a reviewed, unencrypted export; the tools do not decrypt or strip protection.
- `tracked_changes_require_review` / `docx_structure_requires_export` — the document contains unreviewed revisions or content controls; produce a cleaned, reviewed export.
- Worker timeout — a document exceeding the per-file wall-clock limit (`--document-timeout`, default 90 s) kills the worker and blocks the run; inspect the file for pathological content before retrying with a higher limit.

Every extractor warning (hidden sheets/slides, ragged CSV, unverified XLSX caches, no-text pages) becomes a manifest warning that must be explicitly acknowledged by count in `review.json` (`acknowledged_warnings`) before publication; warnings are never auto-acknowledged.

## Checker and review errors introduced in engine 0.2

- `Decision cites only repository evidence` — re-cast the record as an investigation finding or a requirement-vs-implementation uncertainty, or cite the non-repository source that states the decision.
- `Coverage 'triaged_out' requires records schema_version 0.2` / `requires a nonempty triage method` — set `"schema_version": "0.2"` and record how the input was excluded (start from `packets/coverage-stub.json`).
- `Review uses the 0.1 per-code acknowledgement contract` — a review prepared by the 0.1 engine cannot publish. As the human operator, archive the old `review.pending.json` under a historical name and run `--prepare` again.
- `Review must acknowledge every warning occurrence by code and count` — copy the counts printed by `--prepare` (also in `warning_summary.counts`) into `acknowledged_warnings` after you have reviewed them.
- `Review warning summary does not match` / `Review triage list does not match` — the review was hand-edited or belongs to other records; prepare again.
- `Scope fingerprint mismatch` on an old run after upgrading — the checker uses the run's recorded `tool_version`; if this still fails, the manifest or configuration snapshot was changed. Do not reseal it.
- `unsupported schema keywords` — a schema uses a JSON Schema keyword the local validator does not implement; implement it in `validate_schema` (with a test) rather than relying on it being ignored.
- `Run work/ folder changed after review preparation` / `Records/review/work changed during publication` — something wrote to `work/` after `--prepare`. Inspect the change; if it belongs in the audit trail, prepare and review again.
- `Rename this work file` / `Symlink not permitted in run work folder` / `Run work folder exceeds` — release paths must be plain POSIX names without `:` or `\`, regular files only, within the file-count and size caps. Fix `work/` before `--prepare`.
- `Stage 2 publication requires at least one record` — an empty candidate cannot publish; it would retire every record of the current release.
- `Previous coverage names evidence absent from its manifest` (kb_reanchor) — the previous records do not belong to that run; check them with `kb_check.py` first.
- Skill drift in the test suite — edit `.agents/skills/` and run `uv run python tools/kb_sync_skills.py`.

## Symlink or overlapping roots

Use real, approved directory paths. Configured roots are canonicalized once; the source root itself and traversed symlinks are rejected. Output and artifact paths reject symlink components. Sources and the project workspace must remain separate. Root-level/directory symlink handling is conservative and can block a run even when the linked directory was not intended for extraction; explicitly exclude it or prepare a clean source snapshot.

## Blocked inventory or incomparable delta

Inspect manifest.issues, correct the underlying source/configuration, and use a new run id. A blocked run is diagnostic evidence, not a candidate for analysis/publication. If scope changed or capture is incomplete, the delta cannot make deletion claims. Do not hand-edit the manifest or its seal to make it ready.

## Existing output

Runs, packets, checker report files, pending reviews, and releases are non-overwriting. Choose a new run id for a new capture. To preserve several checker attempts in one run, use distinct report names (`checks-01.json`, `checks-02.json`). An agent must never overwrite evidence to make a rerun succeed.

## Records changed after a review template was prepared

The old hash-bound review is stale. As the human operator, archive the old pending review under a clearly historical filename, then run `--prepare` again. Review the changed candidate substantively before creating a new `review.json`. Do not simply replace the hash in an old approval. Agents may not manage these approval files.

## CURRENT changed while reviewing

Another publication superseded the previous-release reference. Prepare and review against the now-current release. Check the newly computed removed_record_ids. Do not clear that list merely to avoid discussing a removal.

## Stale publication lock or interrupted publication

The lock is `knowledge/approved/.publish.lock`. Do not delete it while another publisher is active. After verifying that no process is publishing, the human operator may archive/remove a stale lock and inspect any temporary or orphan release directory. Never automatically delete historical releases.

A crash after the new release directory is renamed but before CURRENT is updated can leave an unselected release. The previous CURRENT remains the selected snapshot; the tool refuses to overwrite the orphan. Preserve it for audit and perform a fresh reviewed run. Manual pointer repair/rollback is not implemented by the bundle.

## Snapshot or current-release integrity failure

Do not reseal changed evidence. Restore the original evidence from an authorized backup or recapture in a new run. The SHA files detect accidental inconsistency, not malicious modification by someone who can rewrite the entire bundle and all hashes.

## Host permissions and security

The tools operate under the current user's filesystem permissions. They are not an OS sandbox, multi-user authorization system, concurrent source snapshot system, or secret scanner. Limit the assistant's write permissions to the run's `proposals/` and `work/` locations. Verify behavior on your own host, filesystem, Python version, and editor before using client material.
