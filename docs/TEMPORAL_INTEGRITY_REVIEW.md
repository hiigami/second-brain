# Temporal integrity review: chronology, out-of-order ingestion, and versioning

This is a historical engine review using synthetic probes. Private project observations are omitted; hypothetical examples below illustrate temporal risks without source excerpts. Current behavior is documented in WORKFLOW.md and CONTRACT.md.

Prepared 2026-10-01 against the **current working tree**: commit `1ea3bfb` plus the uncommitted engine 0.2 changes (`kb_reanchor.py`, records/review schema 0.2, `TOOL_VERSION = "0.2.0"`). It complements [ANALYSIS_AND_IMPROVEMENT_PLAN.md](ANALYSIS_AND_IMPROVEMENT_PLAN.md).

Every failure below was **reproduced** with probe scripts on a scratch copy, not inferred from reading. The probes, their output, a tested patch, and a new test module are in [`validation/temporal-2026-10-01/`](../validation/temporal-2026-10-01/). Nothing in `tools/`, `schemas/`, `tests/` or `projects/` was modified.

---

## 1. Summary

Byte-level versioning is sound:

- Snapshots are content-addressed and write-once.
- Runs and releases are never overwritten.
- A revert (A→B→A) gets back the identical evidence id.
- A scope change makes the delta explicitly incomparable.

**Time is the gap.** The engine knows only one clock: the machine time at capture (`manifest.created_at`). It has no notion of *when the content was said*, so it cannot tell "added in this run" from "newest information". Several components also accept time running backwards:

- the baseline,
- re-anchoring,
- publication, which can roll `CURRENT` back to an older capture,
- review timestamps.

Two versioning paths silently mislabel changes:

- **Extractor-output drift.** The derived document text changes, but the evidence id and the delta stay "unchanged".
- **Partial evidence loss in re-anchoring.** A record survives with half its support and no flag.

| Severity | Count | Examples |
| --- | --- | --- |
| **High**: can publish chronologically wrong knowledge | 5 | No content time (T1), stale provenance (T5), CURRENT rollback (T7), extractor drift (T9), silent partial loss (T12) |
| **Medium**: misleading deltas or lost continuity | 9 | Arbitrary baseline (T3), clock regression (T4), impossible timestamps (T6), backward re-anchor (T8), rename (T10), Unicode path identity (T11), no repo time (T15), undated `supersedes` (T16), "added" ≠ "new" (T2) |
| **Low / latent** | 3 | Alphabetical packet order (T13), python-docx date trap (T14), timezone mixing (T17) |

The included patch fully fixes 10 of the 17 issues and partly fixes 3 more, with 13 new tests. The full suite stays green: **201 tests OK, 1 skipped**. The other 4, and the rest of the 3 partial ones, need contract decisions (identity v2, packet/prompt ordering, a dated `supersedes` rule). They are given as code sketches in §6.

---

## 2. The four clocks, and where each lives today

| Clock | Meaning | Illustrative example | Where it lived at the review checkpoint |
| --- | --- | --- | --- |
| **Content time** | When the statement was made or held | A filename with a date; a document with no stated date | **Nowhere structured.** Only in file names and record prose |
| **Revision time** | When this version of the file came to exist upstream (Drive modifiedTime, commit time) | An unrecorded upstream revision | Optional free-text `provenance.revision`, with no timestamp |
| **Capture time** | When the engine froze the bytes | A recorded capture timestamp | `manifest.created_at` (wall clock, 1-second resolution) and operator-supplied `provenance.captured_at` |
| **Review / publish time** | When a human approved; when CURRENT moved | none yet | `review.reviewed_at` (any timestamp accepted), `CURRENT.published_at` (overwritten each publish, with no history) |

The core rule the fixes enforce: **capture order decides which snapshot is current. Content time decides which statement is newer. Neither substitutes for the other.**

---

## 3. Scenario evaluations

### 3.1 Out-of-order ingestion (a month-old note arrives after today's)

**What happens now.** The run captures the note correctly and the delta lists it as `added` (probe P1). That is right at the capture level. But nothing in the manifest, the packets or the records says the note is from 2026-08-30. The file entry has no time field at all, and the manifest carries only `created_at`.

At the semantic level, GLM sees "new file in this run" in a packet ordered alphabetically. It must infer the date from the file name to avoid treating an old decision as the latest one, and `supersedes` relations are not checked against any date (T16).

**Hypothetical example:** alphabetical filename order can put a later-dated note before an earlier-dated note. A document with no embedded date provides no fallback for establishing content time.

**Verdict:** capture is safe. Chronology is lost before it reaches the model or the reviewer.

### 3.2 Historical vs. current timestamps

**What happens now:**

- **Content time** does not exist (T1).
- **Revision time** has no field (T15).
- **Capture time** has three weaknesses:
  - The operator's `provenance.captured_at` is only checked for having a timezone. `2099-12-31` was accepted (P3).
  - It is keyed by path, so it silently attaches to *new* bytes after a re-export (P3, T5).
  - `manifest.created_at` trusts the machine clock. A run stamped 2020 was accepted with a 2026 baseline (P2, T4).
- **Review time**: `reviewed_at = 2001-01-01` was accepted for a run captured in 2026 (P5, T6).

**Verdict:** the engine records times but never relates them to each other, so impossible histories pass every gate.

### 3.3 Updates and versioning

| Situation | Current behavior | Verdict |
| --- | --- | --- |
| File edited | New evidence id; delta `modified`; re-anchor searches for the quote | ✅ correct |
| A → B → A revert | v3 evidence id equals v1; delta `modified` vs. B (P7) | ✅ correct |
| Scope changed between runs | `compatible:false`, empty lists, explicit warning | ✅ correct |
| Re-capture with an unchanged file | Identical evidence id; coverage carried over by re-anchor | ✅ correct |
| File **renamed**, bytes identical | removed + added; re-anchor drops REQ-001/REQ-002 (P6, T10) | ❌ continuity lost |
| Statement disappears from one of two cited files | Record kept with 1 of 2 citations; its conflict relation is silently dropped; the statement still claims the conflict; structural check passes (P10, T12) | ❌ **silent loss** |
| Extractor output changes, original `.docx` bytes unchanged | Same evidence id, delta `unchanged`. Re-anchor reports `unchanged`, then its own structural check fails on the quote (P12, T9) | ❌ mislabeled |
| Same file name in NFD vs. NFC (macOS vs. other tools) | Different logical id, so delete + add (T11) | ⚠️ latent |
| Re-anchor from a *newer* run into an *older* one | Accepted (P8, T8) | ❌ time runs backwards |
| Publish an older capture after a newer one | Accepted; `CURRENT` regresses; no history file (P4, T7) | ❌ **rollback without trace** |
| Baseline is not the latest run | Accepted silently; the delta re-reports already-seen changes as `added` (P2, T3) | ❌ misleading |

---

## 4. Failure points (all reproduced)

| ID | Sev | Failure | Probe evidence (`probe-results.txt`) | Fixed in patch |
| --- | --- | --- | --- | --- |
| T1 | H | **No content time anywhere.** Meeting and document dates live only in file names and record prose | P1: file entry keys contain no time field | ✅ `files[].temporal.content_date` |
| T2 | M | **`delta.added` reads as "new information".** An old note captured late looks like news | P1 | ◐ content date now shown next to `added`; ordering rule in §6 |
| T3 | M | **Any older ready run can be the baseline**, skipping newer runs | P2: run-3 vs run-1 while run-2 exists, no warning | ✅ `baseline_not_latest` warning; `baseline_created_at` / `baseline_sequence` |
| T4 | M | **Wall-clock-only ordering**, 1-second resolution; a clock running backwards is accepted | P2: `created_at 2020-01-01` accepted | ✅ per-project `sequence`; clock-regression block |
| T5 | H | **Stale provenance**: a path-keyed `captured_at`/`revision` is attached to new bytes with no warning | P3: new bytes carry the 2026-09-30 provenance, `warnings: []` | ✅ optional `origin.sha256` (mismatch blocks); `provenance_not_updated` warning |
| T6 | M | **Impossible timestamps accepted**: future `captured_at`; `reviewed_at` before the capture or the review preparation | P3 (2099 → `ready`), P5 (2001 accepted) | ✅ blocks with skew tolerance; `prepared_at` added to the review |
| T7 | H | **Publication rollback**: an older capture becomes CURRENT; there is no publication log | P4: `CURRENT: old-capture` | ✅ refused unless `review.rollback_reason`; append-only `HISTORY.jsonl` |
| T8 | M | **Re-anchoring backwards in time** accepted | P8 | ✅ refused |
| T9 | H | **Document evidence identity ignores the derived text.** An extractor fix keeps the same evidence id and delta `unchanged` while the quoted text changed. One evidence id then names two different texts across runs | P12 (`extractor_drift_probe`) | ◐ delta and re-anchor now compare `text_sha256`; identity v2 in §6 |
| T10 | M | **Rename = delete + add**; records citing the file are dropped | P6: `dropped: [REQ-001, REQ-002]` | ✅ `delta.renamed` for byte-identical moves; re-anchor follows it |
| T11 | M | **Unicode normalization**: an NFD and an NFC spelling of the same name produce different logical ids | Equivalent filenames may use different normalization forms | ✗ needs identity v2 (§6) |
| T12 | H | **Silent partial evidence loss** in re-anchoring: a record keeps a statement that its remaining citations no longer support | P10: UNC-001 kept with 1 of 2 citations, `relations: []`, check passed | ✅ `degraded_record_ids` plus an injected open question per loss |
| T13 | L | **Alphabetical packet order** hides chronology from the model | Alphabetic filename order need not match date order | ✗ §6 (packet ordering) |
| T14 | L | **python-docx date trap**: with no `docProps/core.xml` it reports `modified = now`. Naive metadata extraction could stamp capture time as content time | Document without embedded core properties (hypothetical) | ✗ §6 guard (latent) |
| T15 | M | **Repository time unknown**: no commit SHA or time; working-tree mtimes are unreliable | Repository capture without an upstream revision | ◐ `origin.revised_at` field; git reader in §6 |
| T16 | M | **`supersedes` is undated**: A can supersede a newer B | Contract review | ✗ §6 checker rule |
| T17 | L | **Mixed timezones**: Gemini names use the organizer's offset (GMT-05 and GMT-03 in the same project). String comparison would mis-order them | Synthetic filename date-parser examples | ✅ parsed, offset kept; `content_sort_key` compares in UTC |

✅ fixed by the patch · ◐ partially fixed · ✗ proposed (§6)

---

## 5. Implemented fixes (tested patch)

**Files:** [`temporal-fixes.patch`](../validation/temporal-2026-10-01/temporal-fixes.patch), a unified diff against today's working tree. If the tree has moved, use the anchor-checked [`apply_temporal_patch.py`](../validation/temporal-2026-10-01/apply_temporal_patch.py), which refuses to half-apply.

**Tests:** [`test_temporal.py`](../validation/temporal-2026-10-01/test_temporal.py), 13 tests; the patch adds it under `tests/`.

**Results on the patched scratch copy:**

- 201 tests OK, 1 skipped.
- Probe output before and after is in [`probe-results.txt`](../validation/temporal-2026-10-01/probe-results.txt).

### 5.1 Content time is separate from file-system time (T1, T17)

The `kb_common.py` and `kb_inventory.py` changes give every file entry an optional `temporal` block:

```json
"temporal": {
  "content_date": {"value": "2026-09-25T12:00:00-05:00", "basis": "filename:gemini_notes", "precision": "minute"},
  "observed_mtime": "2026-10-01T20:25:38+00:00"
}
```

- **Precedence:** `source-provenance.json` `origin.content_date` (human-asserted) beats the deterministic filename patterns (Gemini `YYYY_MM_DD HH_MM GMT±HH_MM`, `YYYY-MM-DD`, `YYYY_MM_DD`), which beat `null`. The filename is NFC-normalized before matching.
- **No fallback to file-system or embedded dates.** `observed_mtime` is informational only. It is *never* used as content time, and is excluded from identity and from the delta (Drive sync touches mtimes).
- **Ordering:** `content_sort_key()` compares in UTC and keeps the original offset for display.

```python
def content_date_from_name(relative_path: str) -> dict | None:
    name = unicodedata.normalize("NFC", relative_path.rsplit("/", 1)[-1])
    for basis, precision, pattern in _CONTENT_DATE_PATTERNS:
        m = pattern.search(name)
        ...
        return {"value": value, "basis": basis, "precision": precision}
    return None
```

### 5.2 Provenance is bound to bytes and to time (T5, T6, T15)

There are three new optional `origin` fields, with the schema added in both `source-provenance` and `manifest`:

- `sha256` (exact bytes described),
- `content_date`,
- `revised_at`.

| Condition | Result |
| --- | --- |
| `origin.sha256` ≠ captured bytes | **error** `provenance_stale`; the run blocks |
| `captured_at` or `revised_at` later than now + 10 min skew | **error** `provenance_timestamp_in_future` |
| `revised_at` later than `captured_at` | **error** `provenance_revised_after_capture` |
| Bytes changed vs. baseline, provenance unchanged | **warning** `provenance_not_updated` |

### 5.3 Capture order no longer depends on the clock (T3, T4)

- **Sequence:** `manifest.sequence` is 1 + the maximum sequence of the project's existing runs (blocked runs included). It is the authoritative capture order; `created_at` stays informational.
- **Clock regression:** a capture whose clock is earlier than any existing run (beyond the skew) is refused before anything is written.
- **Baseline:** must not be newer than this capture. If newer ready runs exist, the warning `baseline_not_latest` names them. The delta records `baseline_created_at` and `baseline_sequence`.

### 5.4 Publication cannot silently go back in time (T6, T7)

In `kb_publish.py`:

- **Review time:** `--prepare` writes `prepared_at`. Publish requires `reviewed_at` to be ≥ the capture time, ≥ `prepared_at`, and ≤ now + skew.
- **No silent rollback:** a run whose `(sequence, created_at)` is older than CURRENT's is refused unless the review sets `rollback_reason`.
- **History:** every publish appends one line to `knowledge/approved/HISTORY.jsonl` before `CURRENT.json` is swapped:

```json
{"captured_at": "...", "previous_release_id": "new", "published_at": "...", "reviewed_at": "...",
 "reviewer": "...", "rollback_reason": "Revert a bad export; owner request", "run_id": "old", "sequence": 1}
```

### 5.5 Versioning continuity (T8, T9, T10, T12)

- **Delta compares what citations quote:** `(sha256, text_sha256, provenance)`. A change in the derived document text is now `modified` (P12 after the patch: `acta in unchanged: False`).
- **`delta.renamed`:** within one source, a removed and an added file with identical `sha256`, when unambiguous, are recorded as a rename. Identity is unchanged.
- **Re-anchoring rules (`kb_reanchor.py`):**
  - Refuses targets not captured after the previous run.
  - Follows `delta.renamed`.
  - Reports `unchanged` only when the derived-text hash also matches.
  - Any record that lost a citation, or a relation whose target lost its evidence, goes into `degraded_record_ids` and gets an explicit open question, e.g. *"Re-anchoring from b-1 lost 1 of 2 citations; re-verify that the statement is still supported before approving."*

### 5.6 Patch limitations to know

- Legacy runs have no `sequence`; they are treated as 0 and ordered by `created_at`.
- Two inventories started at the same instant could take the same sequence. Capture is a single-operator step, so this is documented rather than locked.
- `content_date` from a file name is a **claim from the name**, not verified content. The `basis` field keeps that visible.

---

## 6. Recommended next changes (need a contract decision)

### 6.1 Evidence identity v2: derived text plus Unicode normalization (T9, T11)

Today `E-` = hash(project, source, path, original_sha256). For documents, the quoted text is the derived text, so one evidence id can name two texts across runs.

Proposal: add `manifest.identity_version: 2`. `load_manifest` keeps verifying v1 runs with the v1 formula.

```python
def evidence_identity_v2(project_id, source_id, relative_path, content_sha, text_sha=None):
    path = unicodedata.normalize("NFC", relative_path)          # T11
    base = [project_id, source_id, path]
    material = base + [content_sha] + ([text_sha] if text_sha else [])   # T9
    return "F-" + json_sha(base)[:24], "E-" + json_sha(material)[:24]
```

Inventory must refuse two on-disk names that normalize to the same NFC path (`unicode_path_collision`). Re-anchor matches old v1 logical ids by recomputing the v1 id from the NFC path *and* the raw path. Also put the extractor `VERSION` into `documents_policy`, so an extractor upgrade changes `scope_sha256` explicitly.

### 6.2 Chronology in what the model and the reviewer see (T2, T13)

- `kb_packet.py`: order packets by `(source_id, content_sort_key(content_date) or "~", relative_path)`, and print `Content date: … (basis)` in each packet header. Undated files go last and are labeled `Content date: unknown`.
- Semantic-review aid and release views: add a **timeline** section, with records sorted by the latest content date of their evidence. Mark `added` files whose content date is older than the baseline's capture date as **"late-arriving historical evidence"**.
- `prompts/02_RECONCILE.md`: one rule. *"Newer means later content_date, not later capture. A late-arriving older statement can clarify or conflict with a newer one, but never supersedes it."*

### 6.3 Dated `supersedes` (T16)

In `kb_check.check_records`, warn (not fail, since dates are best-effort) when the superseding record's latest content date is earlier than the target's:

```python
def latest_date(r, files):
    keys = [content_sort_key(cd["value"]) for ev in r["evidence"]
            if (cd := (files[ev["evidence_id"]].get("temporal") or {}).get("content_date"))]
    return max(keys) if keys else None

if edge["type"] == "supersedes":
    a, b = latest_date(r, files), latest_date(records[edge["target"]], files)
    if a and b and a < b:
        temporal_warnings.append(f"{r['id']} supersedes newer {edge['target']} ({a} < {b})")
```

Surface `temporal_warnings` in the checker report and in `review.pending.json`, so the reviewer acknowledges them like other warnings.

### 6.4 Repository revision without running code (T15)

`AGENTS.md` forbids executing source code. Reading `.git` metadata is not code execution:

```python
def git_head(repo: Path) -> str | None:
    head = (repo / ".git" / "HEAD").read_text().strip()
    if not head.startswith("ref: "):
        return head                                   # detached HEAD
    ref = head[5:]
    loose = repo / ".git" / ref
    if loose.is_file():
        return loose.read_text().strip()
    packed = repo / ".git" / "packed-refs"
    for line in packed.read_text().splitlines() if packed.is_file() else []:
        if line.endswith(" " + ref):
            return line.split()[0]
    return None
```

Store the result as `origin.revision` with `kind: repository`. Leave `revised_at` null unless the operator records the commit time, because reading it requires inflating git objects. A dirty working tree stays a warning, since the engine cannot prove cleanliness without running git.

### 6.5 Guard against fabricated document dates (T14, latent)

If document metadata extraction is ever added, read dates only when the part actually exists:

```python
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    if "docProps/core.xml" not in z.namelist():
        return None            # python-docx would report modified = "now"
```

Record such dates as `revised_at` candidates with `basis: "docx_core_properties"`, never as content time.

---

## 7. General operating rules (no code needed)

1. **Always use CURRENT as the baseline.** Use `--baseline knowledge/approved/<CURRENT run>` (or the latest ready run before the first release). The patch warns otherwise.
2. **Add `content_date` to `source-provenance.json` for every document without a date in its name.** Record available provenance and the byte hash without inventing a content date. Update the entry whenever you re-export, or the run will block with `provenance_stale` (by design).
3. **Late-arriving old material is a normal new run.** Ingesting the 2026-08 meeting today is a newer *capture* (higher sequence) of older *content*. It is not a rollback, and it must not supersede newer decisions.
4. **Use `rollback_reason` only to restore a previous snapshot on purpose**, for example after a bad export. `HISTORY.jsonl` keeps the trace.
5. **Renames:** a byte-identical rename is followed automatically. Rename-plus-edit is still delete + add, so re-extract and keep the record id if the meaning is unchanged.

---

## 8. How to apply and verify

```bash
# 1. Commit or stash the current 0.2 work first; the patch is against today's working tree.
git apply -p1 --check validation/temporal-2026-10-01/temporal-fixes.patch
git apply -p1 validation/temporal-2026-10-01/temporal-fixes.patch
#    (if --check fails because files moved on:
#     uv run python validation/temporal-2026-10-01/apply_temporal_patch.py .
#     and copy validation/temporal-2026-10-01/test_temporal.py into tests/)

# 2. Full suite on your Mac (Python 3.14)
uv run python -m unittest discover -s tests -v

# 3. Re-run the probes; every ❌ in §3.3 should now print "BLOCKED BY ENGINE" or a warning
uv run python validation/temporal-2026-10-01/temporal_probe.py .
```

**Verification notes:**

- Probes and tests were run with Python 3.10 on a scratch copy, because Python 3.14 could not be downloaded in the analysis sandbox. The patch uses no 3.11+-only syntax beyond what the engine already uses. Re-run on 3.14 with `uv` before merging.
- Before the patch, `test_temporal.py` cannot even import on the unpatched tree, because the helpers do not exist. The behavioral before/after comparison is in `probe-results.txt`.
