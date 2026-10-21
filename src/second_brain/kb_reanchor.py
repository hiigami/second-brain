#!/usr/bin/env python3
"""Re-anchor a previous release's records into a new run by exact quote. No model call.

For every citation, the same logical file is located in the new run and the exact
quote is searched for. The output is a *proposal* in the new run's work/ folder plus
a report of every quote that moved, changed, or vanished; a human or the assistant
reviews it before copying anything to proposals/records.json.

Coverage that was not cited (reviewed_no_record, triaged_out) is carried over only from
an approved release, and only for files whose quotable text is byte-identical. From an
unapproved run nothing is carried over: an unreviewed declaration of "read" stays unproven.
"""
import argparse
import copy
from pathlib import Path

from .kb_common import (KBError, contract, inside, no_symlinks, parse_ts, read_json, read_stable,
                       run_cli, sha, utc_now, write_json_new)
from .kb_check import check_records, load_manifest, load_segment_inventory


def _records_path(previous: Path) -> Path:
    for candidate in (previous / "records.json", previous / "proposals" / "records.json"):
        if candidate.is_file():
            return candidate
    raise KBError(f"No records.json (release) or proposals/records.json (run) under {previous}")


def quotable_sha(f: dict) -> str:
    """Hash of the text citations quote: derived text for documents, raw bytes otherwise."""
    return f["document"]["text_sha256"] if "document" in f else f["sha256"]


def representation_sha(f: dict) -> str | None:
    """Return the frozen representation identity when this engine version has one."""
    return (f.get("representation") or {}).get("identity_sha256")


def approved_release(previous: Path, m: dict, records_path: Path) -> bool:
    """True only for a published release whose review approved exactly these records."""
    review_path = previous / "review.json"
    if records_path != previous / "records.json" or not review_path.is_file():
        return False
    no_symlinks(review_path)
    review = read_json(review_path)
    contract(review, "review", source=review_path)
    limit = 16 * 1024 * 1024
    return (review["decision"] == "approve" and review["run_id"] == m["run_id"]
            and review["records_sha256"] == sha(read_stable(records_path, limit))
            and review["manifest_sha256"] == sha(read_stable(previous / "manifest.json", limit)))


def _find(lines: list[str], quote: list[str]) -> list[int]:
    k = len(quote)
    return [i + 1 for i in range(len(lines) - k + 1) if lines[i:i + k] == quote]


def verify_quotes(run: Path, m: dict, records: dict) -> None:
    """Every previous citation must be exact against its own frozen snapshot."""
    files = {f["evidence_id"]: f for f in m["files"]}
    for r in records["records"]:
        cites = list(r["evidence"])
        if r["investigation"] is not None:
            cites += [ev for f in r["investigation"]["findings"] for ev in f["evidence"]]
        for ev in cites:
            f = files.get(ev["evidence_id"])
            if f is None:
                raise KBError(f"Previous record {r['id']} cites unknown evidence {ev['evidence_id']}")
            lines = read_stable(inside(run, f["snapshot_path"]), m["limits"]["max_file_bytes"]).decode("utf-8-sig").splitlines()
            if "\n".join(lines[ev["start_line"] - 1:ev["end_line"]]) != ev["quote"]:
                raise KBError(f"Previous record {r['id']} has an inexact quote; fix the previous records first")


def reanchor(previous: Path, run: Path, out_dir: Path | None = None, citation_only: bool = False) -> tuple[dict, dict]:
    old_m = load_manifest(previous)
    old_path = _records_path(previous)
    no_symlinks(old_path)
    old = read_json(old_path)
    contract(old, "records", source=old_path)
    routed = old["schema_version"] in {"0.5", "0.6"}
    if routed and not citation_only:
        raise KBError("Routing-aware records 0.5 cannot be re-anchored automatically; reassess mentions, "
                      "referrals, and disclosure grants in the new run")
    if old["project_id"] != old_m["project_id"] or old["run_id"] != old_m["run_id"]:
        raise KBError("Previous records do not belong to the previous manifest")
    new_m = load_manifest(run)
    if new_m["status"] != "ready":
        raise KBError("Cannot re-anchor into a blocked inventory")
    if new_m["project_id"] != old_m["project_id"]:
        raise KBError("Previous records belong to another project")
    if (new_m.get("sequence", 0), parse_ts(new_m["created_at"])) <= (old_m.get("sequence", 0), parse_ts(old_m["created_at"])):
        raise KBError("The target run was not captured after the previous records' run; re-anchoring only moves forward in time")
    old_files = {f["evidence_id"]: f for f in old_m["files"]}
    unknown = sorted({c["evidence_id"] for c in old["coverage"]} - set(old_files))
    if unknown:
        raise KBError(f"Previous coverage names evidence absent from its manifest: {unknown[:5]}")
    verify_quotes(previous, old_m, old)
    if old["schema_version"] in {"0.3", "0.4", "0.5", "0.6"}:
        check_records(previous, old_m, old_path)
    carry_over = approved_release(previous, old_m, old_path)
    output_segment_bound = "targeted" in new_m or old["schema_version"] in {"0.3", "0.4", "0.5", "0.6"}
    new_segments = load_segment_inventory(run, new_m)
    if output_segment_bound and new_segments is None:
        raise KBError("Cannot re-anchor segment-bound records into a run without frozen segments")
    segments_by_evidence = {}
    for segment in (new_segments or {}).get("segments", []):
        segments_by_evidence.setdefault(segment["evidence_id"], []).append(segment)
    new_by_logical = {f["logical_id"]: f for f in new_m["files"]}
    from .kb_targeting import load_targeted
    from .kb_intervals import selected_ranges
    request = load_targeted(run, new_m)
    selection = selected_ranges(run, new_m, request)[0] if request else None
    # Follow byte-identical renames recorded by inventory (same source, same sha256).
    renamed_to = {}
    if new_m["delta"].get("baseline_run_id") == old_m["run_id"]:
        renamed_to = {r["from"]: r["to"] for r in new_m["delta"].get("renamed", [])}
    cache: dict[str, list[str]] = {}
    def lines(f: dict) -> list[str]:
        if f["evidence_id"] not in cache:
            raw = read_stable(inside(run, f["snapshot_path"]), new_m["limits"]["max_file_bytes"])
            cache[f["evidence_id"]] = raw.decode("utf-8-sig").splitlines()
        return cache[f["evidence_id"]]

    report_rows = []
    def move(ev: dict, rid: str, where: str) -> dict | None:
        src = old_files[ev["evidence_id"]]
        row = {"record_id": rid, "location": where, "old_evidence_id": ev["evidence_id"],
               "path": f"{src['source_id']}/{src['relative_path']}",
               "old_lines": [ev["start_line"], ev["end_line"]], "new_evidence_id": None, "new_lines": None}
        report_rows.append(row)
        target = new_by_logical.get(src["logical_id"])
        if target is None and src["logical_id"] in renamed_to:
            target = new_by_logical.get(renamed_to[src["logical_id"]])
            if target is not None:  # rename target absent from the manifest would be an inventory bug
                row["renamed_to"] = f"{target['source_id']}/{target['relative_path']}"
        if target is None:
            row["status"] = "file_absent"
            return None
        quote = ev["quote"].split("\n")
        span = ev["end_line"] - ev["start_line"]
        same_text = target["sha256"] == src["sha256"] and quotable_sha(target) == quotable_sha(src)
        same_representation = representation_sha(target) == representation_sha(src)
        def exposed(start: int) -> bool:
            return selection is None or any(a <= start and start + span <= b
                                             for a,b in selection.get(target["evidence_id"], []))
        if same_text and same_representation and exposed(ev["start_line"]):
            status, start = "unchanged", ev["start_line"]
        else:
            all_hits = _find(lines(target), quote)
            hits = [h for h in all_hits if exposed(h)]
            if ev["start_line"] in hits:
                status, start = ("representation_changed" if same_text else "same_lines_file_changed"), ev["start_line"]
            elif len(hits) == 1:
                status, start = "moved", hits[0]
            elif hits:
                status, start = "moved_ambiguous", min(hits, key=lambda h: abs(h - ev["start_line"]))
                row["candidates"] = hits
            else:
                row["status"] = "outside_selected_passages" if all_hits else "vanished"
                return None
        moved = {"evidence_id": target["evidence_id"], "start_line": start, "end_line": start + span,
                 "quote": ev["quote"]}
        if output_segment_bound:
            segment = next((s for s in segments_by_evidence.get(target["evidence_id"], [])
                            if s["line_start"] <= start and s["line_end"] >= start + span), None)
            if segment is None:
                row["status"] = "segment_unavailable"
                return None
            moved["segment_id"] = segment["segment_id"]
            moved["representation_sha256"] = segment["representation_sha256"]
            row["new_segment_id"] = segment["segment_id"]
        row.update(status=status, new_evidence_id=target["evidence_id"], new_lines=[start, start + span])
        return moved

    kept, dropped, degraded, dropped_events = [], [], [], []
    for r in old["records"]:
        r = copy.deepcopy(r)
        if routed:
            r["cross_project"] = []
            if old["schema_version"] == "0.6":
                r["assertions"], r["aliases"] = [], []
            r["open_questions"].append("Fresh attribution, mentions, routing, assertions and disclosure review required; citation suggestion only.")
        before = len(r["evidence"]) + (sum(len(f["evidence"]) for f in r["investigation"]["findings"]) if r["investigation"] else 0)
        moved_evidence, index_map = [], {}
        for index, ev in enumerate(r["evidence"]):
            moved = move(ev, r["id"], "evidence")
            if moved:
                index_map[index] = len(moved_evidence)
                moved_evidence.append(moved)
        r["evidence"] = moved_evidence
        if old["schema_version"] in {"0.4", "0.5", "0.6"}:
            kept_events = []
            for event in r["events"]:
                required = set(event["evidence_refs"])
                for key in ("event_date", "effective_date"):
                    time = event.get(key)
                    if time is None:
                        continue
                    if "anchor_ref" in time:
                        required.add(time["anchor_ref"])
                    for alternative in time.get("alternatives", []):
                        required.update(alternative["evidence_refs"])
                if not required.issubset(index_map):
                    dropped_events.append(event["id"])
                    if r["id"] not in degraded:
                        degraded.append(r["id"])
                    r["open_questions"].append(
                        f"Event {event['id']} lost supporting evidence during re-anchoring; re-extract its date and meaning.")
                    continue
                event["evidence_refs"] = [index_map[i] for i in event["evidence_refs"]]
                for key in ("event_date", "effective_date"):
                    time = event.get(key)
                    if time is None:
                        continue
                    if "anchor_ref" in time:
                        time["anchor_ref"] = index_map[time["anchor_ref"]]
                    for alternative in time.get("alternatives", []):
                        alternative["evidence_refs"] = [index_map[i] for i in alternative["evidence_refs"]]
                kept_events.append(event)
            r["events"] = kept_events
        inv = r["investigation"]
        if inv is not None:
            findings = []
            for i, finding in enumerate(inv["findings"]):
                finding["evidence"] = [e for e in (move(ev, r["id"], f"finding[{i}]") for ev in finding["evidence"]) if e]
                if finding["evidence"]:
                    findings.append(finding)
            inv["findings"] = findings
            scope = {new_by_logical[old_files[e]["logical_id"]]["evidence_id"] for e in inv["scope"]
                     if e in old_files and old_files[e]["logical_id"] in new_by_logical}
            scope |= {ev["evidence_id"] for ev in r["evidence"]}
            scope |= {ev["evidence_id"] for f in findings for ev in f["evidence"]}
            inv["scope"] = sorted(scope)
        after = len(r["evidence"]) + (sum(len(f["evidence"]) for f in inv["findings"]) if inv else 0)
        if not r["evidence"] or (inv is not None and not inv["findings"]):
            dropped.append(r["id"])
        else:
            if after < before:
                degraded.append(r["id"])
                r["open_questions"].append(
                    f"Re-anchoring from {old['run_id']} lost {before - after} of {before} citations; "
                    "re-verify that the statement is still supported before approving.")
            kept.append(r)
    ids = {r["id"] for r in kept}
    dropped_relations = []
    for r in kept:
        for edge in r["relations"]:
            if edge["target"] not in ids:
                dropped_relations.append({"record_id": r["id"], **edge})
                if r["id"] not in degraded:
                    degraded.append(r["id"])
                r["open_questions"].append(
                    f"Relation {edge['type']} -> {edge['target']} was dropped because the target lost its evidence; "
                    "re-verify this record's statement.")
        r["relations"] = [e for e in r["relations"] if e["target"] in ids]

    cited = {ev["evidence_id"] for r in kept for ev in r["evidence"]}
    cited |= {ev["evidence_id"] for r in kept if r["investigation"] for f in r["investigation"]["findings"] for ev in f["evidence"]}
    old_cov = {old_files[c["evidence_id"]]["logical_id"]: (c, old_files[c["evidence_id"]]) for c in old["coverage"]}
    coverage = []
    for f in new_m["files"]:
        eid = f["evidence_id"]
        prior = old_cov.get(f["logical_id"])
        if eid in cited:
            entry = {"evidence_id": eid, "disposition": "used", "note": f"Cited by re-anchored records from {old['run_id']}."}
        elif carry_over and old["schema_version"] not in {"0.3", "0.4", "0.5", "0.6"} and prior \
                and quotable_sha(prior[1]) == quotable_sha(f) \
                and representation_sha(prior[1]) == representation_sha(f) \
                and prior[0]["disposition"] in ("reviewed_no_record", "triaged_out"):
            entry = {"evidence_id": eid, "disposition": prior[0]["disposition"],
                     "note": f"Carried over from approved release {old['run_id']}: identical text. "
                             f"Previous note: {prior[0]['note']}"}
            if "method" in prior[0]:
                entry["method"] = prior[0]["method"]
        elif prior and not carry_over and prior[0]["disposition"] != "used":
            entry = {"evidence_id": eid, "disposition": "deferred",
                     "note": f"{old['run_id']} is not an approved release, so its '{prior[0]['disposition']}' "
                             f"declaration is not carried over; read this file. Previous note: {prior[0]['note']}"}
        else:
            entry = {"evidence_id": eid, "disposition": "deferred",
                     "note": f"New or changed since {old['run_id']} (or previously used); not yet read in this run."}
        coverage.append(entry)
    records = {"schema_version": old["schema_version"] if old["schema_version"] in {"0.3", "0.4", "0.5", "0.6"} else "0.2",
               "project_id": new_m["project_id"], "run_id": new_m["run_id"],
               "coverage": coverage, "records": kept}
    if output_segment_bound:
        cited_segments = {ev["segment_id"] for r in kept for ev in r["evidence"]}
        cited_segments |= {ev["segment_id"] for r in kept if r["investigation"]
                           for finding in r["investigation"]["findings"] for ev in finding["evidence"]}
        records["segment_coverage"] = [
            {"segment_id": s["segment_id"],
             "disposition": "used" if s["segment_id"] in cited_segments else "deferred",
             "note": "Re-anchored citation; verify support in context." if s["segment_id"] in cited_segments
                     else "Not reviewed in this run; read before changing disposition."}
            for s in new_segments["segments"]]
    if "targeted" in new_m or old["schema_version"] == "0.6":
        from .kb_intervals import interval_stub, rollup
        records["schema_version"] = "0.6"
        selection = selection if selection is not None else {
            f["evidence_id"]:[(1,f["line_count"])] for f in new_m["files"] if f["line_count"]}
        intervals = interval_stub(new_segments, selection, "targeted_reanchor_unselected_complement")
        cites = [ev for r in kept for ev in r["evidence"]]
        cites += [ev for r in kept if r["investigation"] for f in r["investigation"]["findings"] for ev in f["evidence"]]
        partition = []
        for row in intervals:
            boundaries = {row["start_line"],row["end_line"]+1}
            hits = [c for c in cites if c.get("segment_id") == row["segment_id"] and c["start_line"] <= row["end_line"] and row["start_line"] <= c["end_line"]]
            for c in hits:
                boundaries.update((max(row["start_line"],c["start_line"]),min(row["end_line"]+1,c["end_line"]+1)))
            bounds=sorted(boundaries)
            for a,b in zip(bounds,bounds[1:]):
                part=dict(row,start_line=a,end_line=b-1)
                if row["disposition"] != "triaged_out" and any(c["start_line"] <= a and b-1 <= c["end_line"] for c in hits):
                    part["disposition"]="used"
                partition.append(part)
        records["interval_coverage"] = partition
        for c in records["segment_coverage"]:
            c["disposition"] = rollup(r["disposition"] for r in partition if r["segment_id"] == c["segment_id"])
            c.pop("method",None)
            if c["disposition"] == "triaged_out": c["method"]="targeted_reanchor_unselected_complement"
        for c in records["coverage"]:
            children={s["segment_id"] for s in new_segments["segments"] if s["evidence_id"] == c["evidence_id"]}
            c["disposition"] = rollup(r["disposition"] for r in records["segment_coverage"] if r["segment_id"] in children)
            c.pop("method",None)
            if c["disposition"] == "triaged_out": c["method"]="targeted_reanchor_unselected_complement"
        for r in kept:
            r["cross_project"],r["assertions"],r["aliases"] = [],[],[]
            r["events"] = r.get("events",[])
            citations=list(r["evidence"])
            if r["investigation"]: citations += [e for f in r["investigation"]["findings"] for e in f["evidence"]]
            r["attribution"]=[{"evidence_ref":i,"class":"unknown","project_id":None,
                               "reason":"Fresh manual attribution required; citation match does not establish scope."} for i,_ in enumerate(citations)]
    from .kb_reconciliation import reconciliation_report
    reconciliation = reconciliation_report(run,new_m,records,old,old_m)
    counts: dict[str, int] = {}
    for row in report_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    report = {"schema_version": "0.1", "created_at": utc_now(), "previous_run_id": old["run_id"],
              "previous_is_approved_release": carry_over,
              "run_id": new_m["run_id"], "citation_status_counts": dict(sorted(counts.items())),
              "dropped_record_ids": dropped, "degraded_record_ids": sorted(degraded),
              "dropped_event_ids": dropped_events,
              "dropped_relations": dropped_relations,
              "deferred_inputs": sum(1 for c in coverage if c["disposition"] == "deferred"),
              "citations": report_rows, "routing_reassessment_required": routed or "targeted" in new_m,
              "reconciliation": reconciliation,
              "limitations": ["An unchanged quote can still mean something different if its surrounding text changed; "
                              "read moved and changed-file citations in context.",
                              "Records dropped for lack of evidence need re-extraction, not silent removal.",
                              "Uncited coverage is carried over only from an approved release with identical text; "
                              "everything else starts deferred.",
                              "Legacy records remain file-level proposals; upgrade to records 0.3 before claiming "
                              "segment coverage." if old["schema_version"] not in {"0.3", "0.4", "0.5", "0.6"} else
                              "Re-anchored segment coverage starts deferred unless the segment is cited.",
                              "This is a proposal: it is not a review and does not approve anything."]}
    out_dir = out_dir or run / "work"
    no_symlinks(out_dir)
    out_records = out_dir / "reanchored-records.json"
    write_json_new(out_records, records)
    try:
        report["structural_check"] = {"status": "passed", **check_records(run, new_m, out_records)}
    except KBError as exc:
        report["structural_check"] = {"status": "failed", "error": str(exc)}
    write_json_new(out_dir / "reanchor-report.json", report)
    return records, report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--previous", type=Path, required=True, help="Previous release dir (knowledge/approved/<run>) or run dir")
    p.add_argument("--run", type=Path, required=True, help="New ready run to re-anchor into")
    p.add_argument("--out-dir", type=Path, help="Default: <run>/work")
    p.add_argument("--citation-only", action="store_true", help="Allow routed citation suggestions; discard approvals and reassess all routing")
    a = p.parse_args()
    records, report = reanchor(a.previous, a.run, a.out_dir, a.citation_only)
    out = a.out_dir or a.run / "work"
    print(f"Re-anchored {len(records['records'])} records; dropped {len(report['dropped_record_ids'])}. "
          f"Citations: {report['citation_status_counts']}. Deferred inputs: {report['deferred_inputs']}.\n"
          f"Proposal: {out / 'reanchored-records.json'}\nReport: {out / 'reanchor-report.json'}")
    return 0


if __name__ == "__main__":
    run_cli(main)
