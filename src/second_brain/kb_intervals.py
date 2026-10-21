"""Frozen-representation passage selection and honest interval coverage rollups."""
from pathlib import Path

from .kb_common import KBError


def merge_ranges(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out = []
    for start, end in sorted(spans):
        if out and start <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(end, out[-1][1]))
        else:
            out.append((start, end))
    return out


def selected_ranges(run: Path, manifest: dict, request: dict) -> tuple[dict, str]:
    from .kb_packet import select_evidence
    policy = request["packets"]
    files = {(f["source_id"], f["relative_path"]): f for f in manifest["files"]}
    explicit = {}
    for span in policy["ranges"]:
        file = files.get((span["source_id"], span["relative_path"]))
        if file is None or span["end_line"] > file["line_count"]:
            raise KBError("Requested packet range exceeds frozen evidence")
        explicit.setdefault(file["evidence_id"], []).append((span["start_line"], span["end_line"]))
    chosen, method = select_evidence(run, manifest, None, policy["globs"], policy["terms"], policy["composition"])
    filters = bool(policy["globs"] or policy["terms"])
    if not explicit:
        spans = {f["evidence_id"]: [(1, f["line_count"])] for f in files.values()
                 if f["evidence_id"] in chosen and f["line_count"]}
    elif not filters:
        spans = explicit
    elif policy["composition"] == "intersection":
        spans = {eid: rs for eid, rs in explicit.items() if eid in chosen}
    else:
        spans = dict(explicit)
        for f in files.values():
            if f["evidence_id"] in chosen and f["line_count"]:
                spans[f["evidence_id"]] = [(1, f["line_count"])]
    spans = {eid: merge_ranges(rs) for eid, rs in spans.items()}
    return spans, f"targeted:{policy['composition']}; {method or 'explicit_ranges_or_all_members'}"


def rollup(dispositions) -> str:
    values = set(dispositions)
    return next((d for d in ("used", "deferred", "triaged_out", "reviewed_no_record") if d in values), "reviewed_no_record")


def interval_stub(segments: dict, selected: dict, method: str) -> list[dict]:
    rows = []
    for s in segments["segments"]:
        boundaries = {s["line_start"], s["line_end"] + 1}
        spans = selected.get(s["evidence_id"], [])
        for start, end in spans:
            if start <= s["line_end"] and end >= s["line_start"]:
                boundaries.update((max(start, s["line_start"]), min(end + 1, s["line_end"] + 1)))
        bounds = sorted(boundaries)
        for start, stop in zip(bounds, bounds[1:]):
            chosen = any(a <= start and stop - 1 <= b for a, b in spans)
            rows.append({"segment_id": s["segment_id"], "representation_sha256": s["representation_sha256"],
                         "start_line": start, "end_line": stop - 1,
                         "disposition": "deferred" if chosen else "triaged_out",
                         "note": "Selected; reading/attribution pending." if chosen else "Unselected complement; not read.",
                         **({} if chosen else {"method": method})})
    return rows


def check_intervals(run: Path, manifest: dict, data: dict, segments: dict, citations: list[dict], stage2: bool) -> dict:
    from .kb_targeting import load_targeted
    request = load_targeted(run, manifest)
    selected = selected_ranges(run, manifest, request)[0] if request else None
    groups = {sid: [] for sid in segments}
    for row in data["interval_coverage"]:
        sid = row["segment_id"]
        if sid not in groups:
            raise KBError("Interval coverage names unknown segment")
        groups[sid].append(row)
    for sid, segment in segments.items():
        next_line = segment["line_start"]
        for row in groups[sid]:
            start, end, disp = row["start_line"], row["end_line"], row["disposition"]
            if start != next_line or end < start or end > segment["line_end"] or row["representation_sha256"] != segment["representation_sha256"]:
                raise KBError("Interval coverage must partition each frozen segment in order with its representation")
            next_line = end + 1
            if (disp == "triaged_out" and not row.get("method", "").strip()) or (disp != "triaged_out" and "method" in row):
                raise KBError("Only triaged intervals require a method")
            if selected is not None and disp in {"used", "reviewed_no_record"} and not any(
                    a <= start <= end <= b for a, b in selected.get(segment["evidence_id"], [])):
                raise KBError("Unselected interval cannot claim use or full reading")
            intersecting = [c for c in citations if c["segment_id"] == sid and c["start_line"] <= end and start <= c["end_line"]]
            if (disp == "used") != bool(intersecting):
                raise KBError("Used intervals must match cited ranges; citations cannot cross unread intervals")
            if stage2 and disp == "deferred":
                raise KBError("Stage 2 requires every interval reviewed or explicitly triaged")
        if next_line != segment["line_end"] + 1:
            raise KBError("Interval coverage omits a frozen segment complement")
    declared = {c["segment_id"]: c["disposition"] for c in data["segment_coverage"]}
    if any(declared[sid] != rollup(r["disposition"] for r in rows) for sid, rows in groups.items()):
        raise KBError("Interval disposition rollup differs from segment coverage")
    files = {c["evidence_id"]: c["disposition"] for c in data["coverage"]}
    for eid, declared_disposition in files.items():
        if declared_disposition != rollup(declared[sid] for sid, s in segments.items() if s["evidence_id"] == eid):
            raise KBError("Interval disposition rollup differs from file coverage")
    return {"interval_coverage_count": len(data["interval_coverage"]),
            "triaged_intervals": [r for r in data["interval_coverage"] if r["disposition"] == "triaged_out"]}
