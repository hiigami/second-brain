"""Apply the proposed temporal-integrity fixes to a scratch copy of the engine.

Usage: python3 apply_temporal_patch.py <engine-root>
Every replacement asserts that its anchor exists exactly once, so the patch
fails loudly instead of half-applying against a drifted tree.
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()


def edit(rel, old, new, count=1):
    p = ROOT / rel
    s = p.read_text(encoding="utf-8")
    n = s.count(old)
    if n != count:
        raise SystemExit(f"{rel}: anchor found {n}x (expected {count}):\n{old[:120]}")
    p.write_text(s.replace(old, new), encoding="utf-8")


# ---------------------------------------------------------------- kb_common
edit("tools/kb_common.py", "def utc_now() -> str:\n    return datetime.now(timezone.utc).isoformat(timespec=\"seconds\")\n",
'''def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_ts(value: str) -> datetime:
    """Parse an ISO 8601 timestamp that carries a timezone; compare these, never strings."""
    check_timestamp(value)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# Clock skew tolerated between an operator-supplied timestamp and this machine.
CLOCK_SKEW_SECONDS = 600

# Deterministic content-date sources, most specific first. A filename date is the
# date the *content* claims (e.g. a meeting), never the capture or file-system time.
_CONTENT_DATE_PATTERNS = (
    ("filename:gemini_notes", "minute",
     re.compile(r"(?<!\\d)(\\d{4})_(\\d{2})_(\\d{2}) (\\d{2})_(\\d{2}) GMT([+-]\\d{2})_(\\d{2})(?!\\d)")),
    ("filename:iso_date", "day", re.compile(r"(?<!\\d)(\\d{4})-(\\d{2})-(\\d{2})(?!\\d)")),
    ("filename:underscore_date", "day", re.compile(r"(?<!\\d)(\\d{4})_(\\d{2})_(\\d{2})(?!\\d)")),
)


def content_date_from_name(relative_path: str) -> dict | None:
    """Best-effort, deterministic content date from a file name; None when absent or invalid."""
    import unicodedata
    name = unicodedata.normalize("NFC", relative_path.rsplit("/", 1)[-1])
    for basis, precision, pattern in _CONTENT_DATE_PATTERNS:
        m = pattern.search(name)
        if not m:
            continue
        g = m.groups()
        try:
            if precision == "minute":
                value = datetime.fromisoformat(f"{g[0]}-{g[1]}-{g[2]}T{g[3]}:{g[4]}:00{g[5]}:{g[6]}").isoformat()
            else:
                value = datetime(int(g[0]), int(g[1]), int(g[2])).date().isoformat()
        except ValueError:
            continue
        return {"value": value, "basis": basis, "precision": precision}
    return None


def content_sort_key(value: str) -> str:
    """UTC-normalized ordering key for a content_date value (date-only sorts at 00:00 UTC)."""
    if len(value) == 10:
        return value + "T00:00:00+00:00"
    return parse_ts(value).astimezone(timezone.utc).isoformat()
''')

# ---------------------------------------------------------------- schemas
def schema_edit(rel, fn):
    p = ROOT / rel
    s = json.loads(p.read_text(encoding="utf-8"))
    fn(s)
    p.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

CONTENT_DATE = {"anyOf": [{"type": "object", "properties": {
    "value": {"type": "string", "minLength": 10},
    "basis": {"type": "string", "minLength": 1},
    "precision": {"type": "string", "enum": ["day", "minute", "second"]}},
    "required": ["value", "basis", "precision"], "additionalProperties": False}, {"type": "null"}]}
ORIGIN_EXTRA = {
    "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$",
               "description": "Optional. Exact bytes this provenance describes; a mismatch blocks capture (stale metadata)."},
    "content_date": {"type": "string", "minLength": 10,
                     "description": "Optional. When the content was authored/held (ISO date or timestamp with timezone). Overrides filename dates."},
    "revised_at": {"type": "string", "minLength": 20,
                   "description": "Optional. Upstream revision time (Drive modifiedTime, commit time)."},
}

def add_origin_fields(origin_schema):
    origin_schema["properties"].update(ORIGIN_EXTRA)

def prov_schema(s):
    add_origin_fields(s["properties"]["entries"]["items"]["properties"]["origin"])
schema_edit("schemas/source-provenance.schema.json", prov_schema)

def manifest_schema(s):
    props = s["properties"]
    props["sequence"] = {"type": "integer", "minimum": 1,
                         "description": "Per-project capture order; authoritative over created_at for ordering."}
    fprops = props["files"]["items"]["properties"]
    add_origin_fields(fprops["provenance"]["anyOf"][0])
    fprops["temporal"] = {"type": "object", "properties": {
        "content_date": CONTENT_DATE,
        "observed_mtime": {"anyOf": [{"type": "string", "minLength": 20}, {"type": "null"}]}},
        "required": ["content_date", "observed_mtime"], "additionalProperties": False,
        "description": "Content time vs file-system time; neither is capture time (manifest.created_at)."}
    d = props["delta"]["properties"]
    d["baseline_created_at"] = {"anyOf": [{"type": "string", "minLength": 20}, {"type": "null"}]}
    d["baseline_sequence"] = {"anyOf": [{"type": "integer", "minimum": 1}, {"type": "null"}]}
    d["renamed"] = {"type": "array", "minItems": 0, "items": {"type": "object", "properties": {
        "from": {"type": "string", "minLength": 1}, "to": {"type": "string", "minLength": 1}},
        "required": ["from", "to"], "additionalProperties": False}}
schema_edit("schemas/manifest.schema.json", manifest_schema)

def review_schema(s):
    s["properties"]["prepared_at"] = {"type": "string", "minLength": 20,
                                      "description": "Written by --prepare; reviewed_at must not precede it."}
    s["properties"]["rollback_reason"] = {"type": "string", "minLength": 1,
                                          "description": "Required to publish a capture older than CURRENT."}
schema_edit("schemas/review.schema.json", review_schema)

# ---------------------------------------------------------------- kb_inventory
edit("tools/kb_inventory.py", "                       relative, run_cli, sha, utc_now, write_json_new, write_new)\n",
     "                       relative, run_cli, sha, utc_now, write_json_new, write_new,\n"
     "                       CLOCK_SKEW_SECONDS, content_date_from_name, parse_ts)\n"
     "from datetime import datetime, timedelta, timezone\n")

edit("tools/kb_inventory.py", "def provenance_warnings(origin: dict | None, source_type: str, rel: str) -> list[tuple[str, str]]:",
'''def temporal_entry(origin: dict | None, rel: str, path: Path) -> dict:
    """Separate content time from file-system time; capture time lives on the manifest."""
    if origin is not None and origin.get("content_date"):
        value = origin["content_date"]
        content = {"value": value, "basis": "provenance",
                   "precision": "day" if len(value) == 10 else "second"}
    else:
        content = content_date_from_name(rel)
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    except OSError:
        mtime = None
    return {"content_date": content, "observed_mtime": mtime}


def provenance_time_issues(origin: dict | None, content_sha: str, now: datetime) -> list[tuple[str, str, str]]:
    """(severity, code, detail) for provenance that is stale or claims an impossible time."""
    out = []
    if origin is None:
        return out
    if origin.get("sha256") and origin["sha256"] != content_sha:
        out.append(("error", "provenance_stale", "Provenance describes different bytes (sha256 mismatch); "
                    "update source-provenance.json for the new export"))
    limit = now + timedelta(seconds=CLOCK_SKEW_SECONDS)
    for key in ("captured_at", "revised_at"):
        if origin.get(key) and parse_ts(origin[key]) > limit:
            out.append(("error", "provenance_timestamp_in_future", f"{key} is later than this capture"))
    if origin.get("revised_at") and parse_ts(origin["revised_at"]) > parse_ts(origin["captured_at"]):
        out.append(("error", "provenance_revised_after_capture", "revised_at is later than captured_at"))
    if origin.get("content_date") and len(origin["content_date"]) > 10:
        check_timestamp(origin["content_date"])
    return out


def prior_runs(runs_dir: Path, current: str) -> list[dict]:
    """Sealed manifests of this project's other runs (blocked runs included: they consumed a sequence)."""
    from kb_check import load_manifest
    out = []
    if not runs_dir.is_dir():
        return out
    for child in sorted(runs_dir.iterdir()):
        if child.name.startswith(".") or child.name == current or not (child / "manifest.json").is_file():
            continue
        try:
            out.append(load_manifest(child))
        except KBError:
            continue  # tampered/legacy runs are reported by kb_check, not used for ordering
    return out


def provenance_warnings(origin: dict | None, source_type: str, rel: str) -> list[tuple[str, str]]:''')

# Document entries: add temporal + time issues
edit("tools/kb_inventory.py", '''    entry = {"evidence_id": eid, "logical_id": logical,
             "source_id": sid, "source_type": source_type, "relative_path": rel,
             "sha256": content_sha, "bytes": len(data),
             "line_count": metadata["text_line_count"], "encoding": "utf-8",
             "snapshot_path": paths["text"], "provenance": origin,''',
'''    entry = {"evidence_id": eid, "logical_id": logical,
             "source_id": sid, "source_type": source_type, "relative_path": rel,
             "sha256": content_sha, "bytes": len(data),
             "line_count": metadata["text_line_count"], "encoding": "utf-8",
             "snapshot_path": paths["text"], "provenance": origin,
             "temporal": temporal_entry(origin, rel, source_path),''')

# Baseline + sequence + clock checks
edit("tools/kb_inventory.py", '''        if previous["status"] != "ready":
            raise KBError("A blocked inventory cannot be a baseline")
''', '''        if previous["status"] != "ready":
            raise KBError("A blocked inventory cannot be a baseline")
    started = datetime.now(timezone.utc)
    others = prior_runs(locations["runs"], run_id)
    latest = max((parse_ts(o["created_at"]) for o in others), default=None)
    if latest is not None and started + timedelta(seconds=CLOCK_SKEW_SECONDS) < latest:
        raise KBError(f"Clock regression: this machine's time {started.isoformat()} is earlier than an existing "
                      f"run ({latest.isoformat()}); fix the clock before capturing")
    sequence = 1 + max((o.get("sequence", 0) for o in others), default=0)
    if previous:
        if parse_ts(previous["created_at"]) > started + timedelta(seconds=CLOCK_SKEW_SECONDS):
            raise KBError("Baseline was captured after this run; a delta must compare against an older capture")
''')

edit("tools/kb_inventory.py", '''    manifest = {"schema_version": "0.1", "tool_version": TOOL_VERSION,
                "project_id": cfg["project"]["id"], "run_id": run_id, "created_at": utc_now(),''',
'''    manifest = {"schema_version": "0.1", "tool_version": TOOL_VERSION,
                "project_id": cfg["project"]["id"], "run_id": run_id, "sequence": sequence,
                "created_at": started.isoformat(timespec="seconds"),''')

# Text entries: temporal + provenance time issues
edit("tools/kb_inventory.py", '''                        for code, detail in provenance_warnings(origin, source["type"], rel):
                            issue("warning", code, sid, rel, detail)
                        snapshot = f"snapshots/{eid}.txt"''',
'''                        for code, detail in provenance_warnings(origin, source["type"], rel):
                            issue("warning", code, sid, rel, detail)
                        for severity, code, detail in provenance_time_issues(origin, content_sha, started):
                            issue(severity, code, sid, rel, detail)
                        snapshot = f"snapshots/{eid}.txt"''')
edit("tools/kb_inventory.py", '''                            "encoding": "utf-8", "snapshot_path": snapshot, "provenance": origin})''',
'''                            "encoding": "utf-8", "snapshot_path": snapshot, "provenance": origin,
                            "temporal": temporal_entry(origin, rel, p)})''')
# Document provenance time issues (after capture_document_entry returns)
edit("tools/kb_inventory.py", '''                            for item in entry.pop("_warnings"):
                                issue("warning", item["code"], sid, rel, item["detail"])''',
'''                            for item in entry.pop("_warnings"):
                                issue("warning", item["code"], sid, rel, item["detail"])
                            for severity, code, detail in provenance_time_issues(
                                    entry["entry"]["provenance"], entry["entry"]["sha256"], started):
                                issue(severity, code, sid, rel, detail)''')

# Delta: baseline metadata, latest-baseline warning, text hash, renames, stale provenance
edit("tools/kb_inventory.py", '''        if previous:
            delta["baseline_run_id"] = previous["run_id"]''',
'''        if previous:
            delta["baseline_run_id"] = previous["run_id"]
            delta["baseline_created_at"] = previous["created_at"]
            delta["baseline_sequence"] = previous.get("sequence")
            newer = sorted(o["run_id"] for o in others if o["status"] == "ready"
                           and (o.get("sequence", 0), o["created_at"]) > (previous.get("sequence", 0), previous["created_at"]))
            if newer:
                issue("warning", "baseline_not_latest", None, None,
                      f"Newer ready runs exist after the baseline ({', '.join(newer)}); this delta skips them")''')
edit("tools/kb_inventory.py", '''                for k in sorted(set(old) & set(now)):
                    changed = (now[k]["sha256"], canonical(now[k]["provenance"])) != (old[k]["sha256"], canonical(old[k]["provenance"]))
                    delta["modified" if changed else "unchanged"].append(k)''',
'''                def text_sha(f):  # what citations actually quote
                    return f["document"]["text_sha256"] if "document" in f else f["sha256"]
                for k in sorted(set(old) & set(now)):
                    changed = (now[k]["sha256"], text_sha(now[k]), canonical(now[k]["provenance"])) != \\
                              (old[k]["sha256"], text_sha(old[k]), canonical(old[k]["provenance"]))
                    delta["modified" if changed else "unchanged"].append(k)
                    if now[k]["sha256"] != old[k]["sha256"] and now[k]["provenance"] is not None \\
                            and canonical(now[k]["provenance"]) == canonical(old[k]["provenance"]):
                        issue("warning", "provenance_not_updated", now[k]["source_id"], now[k]["relative_path"],
                              "Bytes changed but provenance (captured_at/revision) did not; it may describe the old export")
                by_hash = {}
                for k in delta["removed"]:
                    by_hash.setdefault((old[k]["source_id"], old[k]["sha256"]), []).append(k)
                for k in delta["added"]:
                    cands = by_hash.get((now[k]["source_id"], now[k]["sha256"]), [])
                    if len(cands) == 1:
                        delta["renamed"].append({"from": cands.pop(), "to": k})''')
edit("tools/kb_inventory.py", '''                "delta": {"baseline_run_id": None, "compatible": None,
                          "added": [], "modified": [], "removed": [], "unchanged": []}}''',
'''                "delta": {"baseline_run_id": None, "baseline_created_at": None, "baseline_sequence": None,
                          "compatible": None, "added": [], "modified": [], "removed": [], "unchanged": [],
                          "renamed": []}}''')

# ---------------------------------------------------------------- kb_check
edit("tools/kb_check.py", '''        if f["provenance"] is not None:
            check_timestamp(f["provenance"]["captured_at"])
        counts[f["source_id"]] += 1
        total += len(raw)''',
'''        if f["provenance"] is not None:
            check_timestamp(f["provenance"]["captured_at"])
        content_date = (f.get("temporal") or {}).get("content_date")
        if content_date and len(content_date["value"]) > 10:
            check_timestamp(content_date["value"])
        counts[f["source_id"]] += 1
        total += len(raw)''')

# ---------------------------------------------------------------- kb_publish
edit("tools/kb_publish.py", "                       run_cli, sha, utc_now, warning_summary, write_json_new, write_new)\n",
     "                       run_cli, sha, utc_now, warning_summary, write_json_new, write_new,\n"
     "                       CLOCK_SKEW_SECONDS, parse_ts)\n"
     "from datetime import datetime, timedelta, timezone\n")
edit("tools/kb_publish.py", '''            "decision": "changes_requested", "reviewer": "", "reviewed_at": None,''',
'''            "decision": "changes_requested", "reviewer": "", "reviewed_at": None, "prepared_at": utc_now(),''')
edit("tools/kb_publish.py", '''    check_timestamp(review["reviewed_at"])
    if review["project_id"] != m["project_id"] or review["run_id"] != m["run_id"]:''',
'''    reviewed = parse_ts(review["reviewed_at"])
    floor = parse_ts(review.get("prepared_at") or m["created_at"])
    if reviewed < floor or reviewed < parse_ts(m["created_at"]):
        raise KBError("reviewed_at precedes the capture or the review preparation; record the real review time")
    if reviewed > datetime.now(timezone.utc) + timedelta(seconds=CLOCK_SKEW_SECONDS):
        raise KBError("reviewed_at is in the future")
    if review["project_id"] != m["project_id"] or review["run_id"] != m["run_id"]:''')
edit("tools/kb_publish.py", '''        if destination.exists():
            raise KBError("Release already exists; immutable releases are never overwritten")''',
'''        if destination.exists():
            raise KBError("Release already exists; immutable releases are never overwritten")
        if current_id is not None:
            cur_m = read_json(inside(approved, current_id) / "manifest.json")
            older = (m.get("sequence", 0), parse_ts(m["created_at"])) < (cur_m.get("sequence", 0), parse_ts(cur_m["created_at"]))
            if older and not review.get("rollback_reason"):
                raise KBError(f"This run was captured before CURRENT ({current_id}); publishing it would roll "
                              "knowledge back in time. Set review.rollback_reason to do so deliberately")''')
edit("tools/kb_publish.py", '''        tmp.rename(destination)
        atomic_json(approved / "CURRENT.json",''',
'''        tmp.rename(destination)
        history = approved / "HISTORY.jsonl"
        entry = {"published_at": utc_now(), "run_id": m["run_id"], "sequence": m.get("sequence"),
                 "captured_at": m["created_at"], "previous_release_id": current_id,
                 "reviewer": review["reviewer"], "reviewed_at": review["reviewed_at"],
                 "rollback_reason": review.get("rollback_reason")}
        with history.open("a", encoding="utf-8") as handle:  # append-only publication log
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\\n")
        atomic_json(approved / "CURRENT.json",''')
if "import json" not in (ROOT / "tools/kb_publish.py").read_text():
    edit("tools/kb_publish.py", "import argparse\n", "import argparse\nimport json\n")

# ---------------------------------------------------------------- kb_reanchor
edit("tools/kb_reanchor.py", "from kb_common import KBError, contract, inside, no_symlinks, read_json, read_stable, run_cli, utc_now, write_json_new\n",
     "from kb_common import KBError, contract, inside, no_symlinks, parse_ts, read_json, read_stable, run_cli, utc_now, write_json_new\n")
edit("tools/kb_reanchor.py", '''    if new_m["project_id"] != old_m["project_id"]:
        raise KBError("Previous records belong to another project")''',
'''    if new_m["project_id"] != old_m["project_id"]:
        raise KBError("Previous records belong to another project")
    if (new_m.get("sequence", 0), parse_ts(new_m["created_at"])) <= (old_m.get("sequence", 0), parse_ts(old_m["created_at"])):
        raise KBError("The target run was not captured after the previous records' run; re-anchoring only moves forward in time")''')
edit("tools/kb_reanchor.py", '''    new_by_logical = {f["logical_id"]: f for f in new_m["files"]}''',
'''    new_by_logical = {f["logical_id"]: f for f in new_m["files"]}
    # Follow byte-identical renames recorded by inventory (same source, same sha256).
    renamed_to = {}
    if new_m["delta"].get("baseline_run_id") == old_m["run_id"]:
        renamed_to = {r["from"]: r["to"] for r in new_m["delta"].get("renamed", [])}

    def text_sha(f: dict) -> str:
        return f["document"]["text_sha256"] if "document" in f else f["sha256"]''')
edit("tools/kb_reanchor.py", '''        target = new_by_logical.get(src["logical_id"])
        if target is None:
            row["status"] = "file_absent"
            return None''',
'''        target = new_by_logical.get(src["logical_id"])
        if target is None and src["logical_id"] in renamed_to:
            target = new_by_logical.get(renamed_to[src["logical_id"]])
            row["renamed_to"] = f"{target['source_id']}/{target['relative_path']}"
        if target is None:
            row["status"] = "file_absent"
            return None''')
edit("tools/kb_reanchor.py", '''        if target["sha256"] == src["sha256"]:
            status, start = "unchanged", ev["start_line"]''',
'''        if target["sha256"] == src["sha256"] and text_sha(target) == text_sha(src):
            status, start = "unchanged", ev["start_line"]''')
edit("tools/kb_reanchor.py", '''    kept, dropped = [], []
    for r in old["records"]:
        r = copy.deepcopy(r)
        r["evidence"] = [e for e in (move(ev, r["id"], "evidence") for ev in r["evidence"]) if e]''',
'''    kept, dropped, degraded = [], [], []
    for r in old["records"]:
        r = copy.deepcopy(r)
        before = len(r["evidence"]) + (sum(len(f["evidence"]) for f in r["investigation"]["findings"]) if r["investigation"] else 0)
        r["evidence"] = [e for e in (move(ev, r["id"], "evidence") for ev in r["evidence"]) if e]''')
edit("tools/kb_reanchor.py", '''        if not r["evidence"] or (inv is not None and not inv["findings"]):
            dropped.append(r["id"])
        else:
            kept.append(r)''',
'''        after = len(r["evidence"]) + (sum(len(f["evidence"]) for f in inv["findings"]) if inv else 0)
        if not r["evidence"] or (inv is not None and not inv["findings"]):
            dropped.append(r["id"])
        else:
            if after < before:
                degraded.append(r["id"])
                r["open_questions"].append(
                    f"Re-anchoring from {old['run_id']} lost {before - after} of {before} citations; "
                    "re-verify that the statement is still supported before approving.")
            kept.append(r)''')
edit("tools/kb_reanchor.py", '''    ids = {r["id"] for r in kept}
    dropped_relations = []
    for r in kept:
        for edge in r["relations"]:
            if edge["target"] not in ids:
                dropped_relations.append({"record_id": r["id"], **edge})''',
'''    ids = {r["id"] for r in kept}
    dropped_relations = []
    for r in kept:
        for edge in r["relations"]:
            if edge["target"] not in ids:
                dropped_relations.append({"record_id": r["id"], **edge})
                if r["id"] not in degraded:
                    degraded.append(r["id"])
                r["open_questions"].append(
                    f"Relation {edge['type']} -> {edge['target']} was dropped because the target lost its evidence; "
                    "re-verify this record's statement.")''')
edit("tools/kb_reanchor.py", '''              "dropped_record_ids": dropped, "dropped_relations": dropped_relations,''',
'''              "dropped_record_ids": dropped, "degraded_record_ids": sorted(degraded),
              "dropped_relations": dropped_relations,''')

print("patch applied to", ROOT)

# ---------------------------------------------------------------- existing test that derives a 0.1 review
# from a freshly prepared 0.2 review: prepared_at is a 0.2-only field, so strip it like the others.
edit("tests/test_contract_v02.py",
     '''if k not in ("warning_summary", "acknowledged_warnings", "triaged_evidence_ids", "triage_acknowledged")}''',
     '''if k not in ("warning_summary", "acknowledged_warnings", "triaged_evidence_ids", "triage_acknowledged",
                               "prepared_at")}''')
print("test adjusted")
