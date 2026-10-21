"""Complete-snapshot reconciliation and project-owned assertion review aids."""
from pathlib import Path

from .kb_common import KBError, json_sha, read_stable


def reconciliation_report(run: Path, manifest: dict, candidate: dict, prior: dict | None,
                          prior_manifest: dict | None = None) -> dict:
    old = {r["id"]: r for r in (prior or {}).get("records", [])}
    now = {r["id"]: r for r in candidate["records"]}
    files = {f["logical_id"]: f for f in manifest["files"]}
    old_files = {f["evidence_id"]: f for f in (prior_manifest or {}).get("files", [])}
    rows = []
    meaning = lambda r: {k:r[k] for k in ("kind", "title", "statement", "epistemic_status")}
    for rid in sorted(set(old) | set(now)):
        before, after = old.get(rid), now.get(rid)
        status = "new" if before is None else "removed" if after is None else "retained" if meaning(before) == meaning(after) else "revised"
        unsupported = []
        for citation in (before or {}).get("evidence", []):
            previous_file = old_files.get(citation["evidence_id"])
            file = files.get(previous_file["logical_id"]) if previous_file else None
            if file is None:
                unsupported.append({"evidence_id":citation["evidence_id"], "reason":"outside_current_capture; scope narrowing is not deletion"})
            else:
                lines = read_stable(run/file["snapshot_path"], manifest["limits"]["max_file_bytes"]).decode("utf-8-sig").splitlines()
                quote = citation["quote"].split("\n")
                if not any(lines[i:i+len(quote)] == quote for i in range(len(lines)-len(quote)+1)):
                    unsupported.append({"evidence_id":citation["evidence_id"], "reason":"prior exact quote unavailable; re-extract support"})
        rows.append({"record_id":rid, "status":status, "unsupported_prior_citations":unsupported,
                     "unresolved": bool(after and (after["epistemic_status"] == "unresolved" or after["open_questions"])),
                     "action":"Explicit human-reviewed removal required" if status == "removed" else
                              "Review changed meaning and record identity" if status == "revised" else
                              "Revalidate current citation entailment; no blind carry-forward"})
    return {"schema_version":"1.0", "run_id":manifest["run_id"], "rows":rows,
            "candidate_sha256":json_sha(candidate), "previous_run_id":(prior or {}).get("run_id"),
            "limitations":["Exact-quote availability is not semantic support or business approval.",
                           "Removed prior records require deliberate review; missing capture is not source deletion."]}


def check_assertions(manifest: dict, records: dict) -> list[dict]:
    hints = []
    ids = {r["id"] for r in records["records"]}
    for record in records["records"]:
        seen = set()
        for assertion in record["assertions"]:
            refs = assertion["evidence_refs"]
            if any(i >= len(record["evidence"]) for i in refs):
                raise KBError("Assertion needs exact parent evidence indexes")
            target = assertion["target"]
            key = (assertion["type"], target["project_id"], target["run_id"], target["record_id"])
            if key in seen:
                raise KBError("Duplicate project-owned assertion")
            seen.add(key)
            local = target["project_id"] == manifest["project_id"] and target["run_id"] == manifest["run_id"]
            if local and (target["record_id"] not in ids or target["record_id"] == record["id"]):
                raise KBError("Assertion has a dangling or self local target")
            if target["project_id"] != manifest["project_id"] and not any(
                    l["project_id"] == target["project_id"] for l in record["cross_project"]):
                raise KBError("Foreign assertion requires freshly assessed routing/disclosure")
            hints.append({"owner_record_id":record["id"], "type":assertion["type"], "target":target,
                          "target_integrity":"local_candidate" if local else "unresolved_until_authorized_index_lookup",
                          "status":assertion["status"], "reason":assertion["reason"]})
    return hints


def assertion_views(data: dict) -> dict:
    """Resolve only authorized selected entries, retain disagreements and cycles."""
    entries = {e["key"]: e for e in data["entries"]}
    rows, graph, equivalent = [], {}, {}
    established_statuses = {"observed", "interpretation"}
    for key, entry in sorted(entries.items()):
        for assertion in entry["record"].get("assertions", []):
            target = assertion["target"]
            target_key = f"{target['project_id']}:{target['run_id']}:{target['record_id']}"
            other = entries.get(target_key)
            rows.append({"owner":key, "target":target_key, "assertion":assertion,
                         "target_status":"unavailable_or_outside_selection" if other is None else other["visibility"]})
            # Proposals/unresolved assertions do not establish supersession/equivalence.
            if assertion["status"] not in established_statuses:
                continue
            if assertion["type"] == "supersedes":
                graph.setdefault(key, set()).add(target_key)
            if assertion["type"] == "equivalent_to" and other is not None:
                equivalent.setdefault(key,set()).add(target_key)
                equivalent.setdefault(target_key,set()).add(key)
    def reaches(start, goal):
        pending, seen = [start], set()
        while pending:
            item = pending.pop()
            if item == goal:
                return True
            if item not in seen:
                seen.add(item)
                pending.extend(graph.get(item,()))
        return False
    pairs = {}
    for row in rows:
        pairs.setdefault(frozenset((row["owner"],row["target"])),[]).append(row)
    for row in rows:
        row["supersession_cycle"] = (row["assertion"]["type"] == "supersedes"
                                     and row["assertion"]["status"] in established_statuses
                                     and reaches(row["target"],row["owner"]))
        row["opposing_assertions"] = [r["owner"] for r in pairs[frozenset((row["owner"],row["target"]))]
                                      if r is not row and r["assertion"]["type"] != row["assertion"]["type"]]
    groups, visited = [], set()
    for key in sorted(equivalent):
        if key in visited:
            continue
        pending, group = [key], set()
        while pending:
            item = pending.pop()
            if item in group:
                continue
            group.add(item)
            pending.extend(equivalent.get(item,()))
        visited.update(group)
        groups.append(sorted(group))
    return {"assertions":rows, "equivalence_groups":groups,
            "limitations":["Groups are derived project-owned assertions; records are never merged or suppressed.",
                           "Dates and publication order do not establish applicability or supersession."]}
