#!/usr/bin/env python3
"""Check frozen-input integrity, exact citations, record links, and Stage 2 coverage."""
import argparse
import json
from collections import Counter
from pathlib import Path

from .kb_common import (KBError, LEGACY_CAPTURE_VERSIONS, LEGACY_SECRET_PATTERNS,
                       LEGACY_TEXT_EXTENSIONS, TOOL_VERSION,
                       ai_summary_name, blocked_inventory_error, check_timestamp, contract,
                       error_context, evidence_identity, extraction_snapshot_paths,
                       inside, integrity_error, json_sha, no_symlinks, read_json, read_stable, relative,
                       representation_identity,
                       run_cli, sha, utc_now, write_json_new)
from .kb_segments import build_segment_inventory
from .kb_event_time import check_record_events


def load_segment_inventory(run: Path, manifest: dict) -> dict | None:
    """Read the sealed segment inventory after manifest integrity verification."""
    binding = manifest.get("segment_inventory")
    if binding is None:
        return None
    raw = read_stable(inside(run, binding["path"]), 64 * 1024 * 1024)
    if sha(raw) != binding["sha256"]:
        raise integrity_error("Segment inventory checksum mismatch", inside(run, binding["path"]))
    data = read_json(inside(run, binding["path"]))
    contract(data, "segments", source=inside(run, binding["path"]))
    if data["project_id"] != manifest["project_id"] or data["run_id"] != manifest["run_id"] \
            or len(data["segments"]) != binding["count"]:
        raise integrity_error("Segment inventory manifest binding mismatch", inside(run, binding["path"]))
    return data


def load_manifest(run: Path) -> dict:
    no_symlinks(run)
    raw = read_stable(inside(run, "manifest.json"), 16 * 1024 * 1024)
    seal = read_stable(inside(run, "manifest.sha256"), 256).decode("ascii").strip()
    if sha(raw) != seal:
        raise integrity_error("Manifest checksum mismatch; restore the original run, do not reseal a modified manifest", run / "manifest.json")
    m = read_json(run / "manifest.json")
    contract(m, "manifest", source=run / "manifest.json")
    check_timestamp(m["created_at"])
    cfg = read_json(inside(run, m["config_snapshot"]))
    contract(cfg, "project", source=inside(run, m["config_snapshot"]))
    if json_sha(cfg) != m["config_sha256"] or cfg["project"]["id"] != m["project_id"]:
        raise KBError("Configuration snapshot mismatch", path=inside(run, m["config_snapshot"]),
                      suggestion="Restore the original snapshot from an authorized backup or create a new run; do not reseal changed evidence.")
    source_scope = None
    if "source_scope" in m:
        if m["tool_version"] in {"0.1.0", "0.2.0", "0.2.1"}:
            raise KBError("Historical manifest cannot declare an expanded source scope")
        source_scope_raw = read_stable(inside(run, m["source_scope"]["path"]), 16 * 1024 * 1024)
        if sha(source_scope_raw) != m["source_scope"]["sha256"]:
            raise integrity_error("Source scope snapshot checksum mismatch", inside(run, m["source_scope"]["path"]))
        source_scope = read_json(inside(run, m["source_scope"]["path"]))
        contract(source_scope, "source-scope", source=inside(run, m["source_scope"]["path"]))
        if source_scope["project_id"] != m["project_id"]:
            raise KBError("Source scope project mismatch")
    sources = {s["id"]: s for s in m["sources"]}
    configured_sources = cfg["sources"] + (source_scope["sources"] if source_scope else [])
    configured = {s["id"]: s for s in configured_sources}
    if len(sources) != len(m["sources"]) or len(configured) != len(configured_sources):
        raise KBError("Duplicate source id in manifest/configuration")
    if set(sources) != set(configured):
        raise KBError("Source set differs from frozen configuration")
    for sid, source in sources.items():
        if source["type"] != configured[sid]["type"] or not Path(source["root"]).is_absolute():
            raise KBError("Invalid source type/root in manifest")
    policy = m.get("capture_policy")
    if m["tool_version"] in LEGACY_CAPTURE_VERSIONS:
        if policy is not None:
            raise KBError("Legacy manifest cannot declare a capture policy")
        extensions, secrets = list(LEGACY_TEXT_EXTENSIONS), list(LEGACY_SECRET_PATTERNS)
    else:
        if policy is None:
            raise KBError("Manifest lacks its frozen capture policy")
        extensions, secrets = policy["supported_extensions"], policy["secret_patterns"]
        if extensions != sorted(extensions):
            raise KBError("Capture policy extensions must be sorted")
    scope = {"project_id": m["project_id"], "sources": configured_sources,
             "resolved_roots": {k: s["root"] for k, s in sources.items()},
             "global_exclude": cfg["global_exclude"], "secret_patterns": secrets,
             "supported_extensions": extensions, "limits": m["limits"],
             # The engine version that captured the run, not this checker's version, so
             # older runs still verify after a TOOL_VERSION bump.
             "tool_version": m["tool_version"]}
    if policy is not None:
        scope["capture_policy_version"] = policy["version"]
    if source_scope is not None:
        scope["source_scope"] = source_scope
    if "documents" in m:
        # The frozen policy is part of the scope fingerprint for document runs.
        if policy is not None and "adapter_version" not in m["documents"]:
            raise KBError("Document policy lacks its frozen adapter version")
        document_policy = m["documents"]
        if document_policy["adapter_version"] in {"0.4.0", "0.5.0", "0.6.0", "0.6.1", "0.6.2", "0.7.0"}:
            representation = document_policy.get("csv_representation")
            header = document_policy.get("csv_header")
            if representation not in {"raw", "structured"} or header not in {"none", "first-row"} \
                    or (header != "none" and representation != "structured") \
                    or ((".csv" in document_policy["extensions"]) != (representation == "structured")):
                raise KBError("Invalid frozen structured-CSV capture policy")
        elif ".csv" in document_policy["extensions"]:
            raise KBError("Historical document policy cannot capture structured CSV")
        scope["documents"] = m["documents"]
    from .kb_targeting import load_targeted, selection_policy
    targeted = load_targeted(run, m)
    if targeted is not None:
        scope["targeted_policy"] = selection_policy(targeted)
    if json_sha(scope) != m["scope_sha256"]:
        raise KBError("Scope fingerprint mismatch")
    ids, logicals, keys = set(), set(), set()
    counts = Counter()
    total = 0
    for f in m["files"]:
        relative(f["relative_path"])
        suffix = Path(f["relative_path"]).suffix.lower()
        if "document" in f:
            if "documents" not in m or suffix not in m["documents"]["extensions"]:
                raise KBError("Document extension is outside the frozen capture policy")
        elif suffix not in extensions:
            raise KBError("Text extension is outside the frozen capture policy")
        if f["source_id"] not in sources or f["source_type"] != sources[f["source_id"]]["type"]:
            raise KBError("Evidence refers to an unknown/mismatched source")
        representation = f.get("representation")
        if m["tool_version"] == "0.4.0":
            if representation is None:
                raise KBError("Manifest lacks a frozen quotable representation")
        elif representation is not None:
            raise KBError("Historical manifest cannot declare a quotable representation")
        identity_sha = representation["identity_sha256"] if representation and "document" in f else None
        logical, eid = evidence_identity(m["project_id"], f["source_id"], f["relative_path"],
                                         f["sha256"], identity_sha)
        key = (f["source_id"], f["relative_path"])
        if f["evidence_id"] != eid or f["logical_id"] != logical:
            raise KBError("Evidence identity mismatch")
        if eid in ids or logical in logicals or key in keys:
            raise KBError("Duplicate evidence/file identity")
        ids.add(eid); logicals.add(logical); keys.add(key)
        if "document" in f:
            # Document evidence: sha256/bytes describe the frozen original binary;
            # snapshot_path/line_count/encoding describe the derived UTF-8 text.
            doc = f["document"]
            expected = extraction_snapshot_paths(eid, Path(doc["original_snapshot_path"]).suffix)
            if doc["original_snapshot_path"] != expected["original"] \
                    or f["snapshot_path"] != expected["text"] or doc["text_snapshot_path"] != expected["text"] \
                    or doc["metadata_snapshot_path"] != expected["metadata"]:
                raise KBError(f"Unexpected document snapshot layout: {eid}")
            if doc["original_sha256"] != f["sha256"] or doc["original_bytes"] != f["bytes"]:
                raise KBError(f"Document original identity mismatch: {eid}")
            original_raw = read_stable(inside(run, doc["original_snapshot_path"]), m["limits"]["max_file_bytes"])
            if sha(original_raw) != doc["original_sha256"] or len(original_raw) != doc["original_bytes"]:
                raise integrity_error(f"Document original integrity failure: {eid}", inside(run, doc["original_snapshot_path"]))
            raw = read_stable(inside(run, f["snapshot_path"]), m["limits"]["max_file_bytes"])
            if sha(raw) != doc["text_sha256"] or len(raw) != doc["text_bytes"]:
                raise integrity_error(f"Document derived-text integrity failure: {eid}", inside(run, f["snapshot_path"]))
            try:
                lines_text = raw.decode("utf-8-sig")
            except UnicodeError as exc:
                raise integrity_error(f"Invalid derived-text encoding: {eid}", inside(run, f["snapshot_path"])) from exc
            if b"\x00" in raw or len(lines_text.splitlines()) != doc["text_line_count"] \
                    or doc["text_line_count"] != f["line_count"] \
                    or doc["original_sha256"] == doc["text_sha256"]:
                raise integrity_error(f"Document derived-text content mismatch: {eid}", inside(run, f["snapshot_path"]))
            metadata_raw = read_stable(inside(run, doc["metadata_snapshot_path"]), m["limits"]["max_file_bytes"])
            if sha(metadata_raw) != doc["metadata_sha256"]:
                raise integrity_error(f"Document metadata integrity failure: {eid}", inside(run, doc["metadata_snapshot_path"]))
            seal = read_stable(inside(run, doc["metadata_snapshot_path"] + ".sha256"), 128).decode("ascii").strip()
            if seal != doc["metadata_sha256"]:
                raise integrity_error(f"Document metadata sidecar mismatch: {eid}", inside(run, doc["metadata_snapshot_path"] + ".sha256"))
            try:
                metadata = json.loads(metadata_raw.decode("utf-8"))
            except (UnicodeError, ValueError) as exc:
                raise integrity_error(f"Document metadata is not readable JSON: {eid}", inside(run, doc["metadata_snapshot_path"])) from exc
            if metadata.get("schema_version") != "1.0" or metadata.get("status") != "extracted_needs_review" \
                    or metadata.get("source_sha256") != f["sha256"] \
                    or metadata.get("text_sha256") != doc["text_sha256"] \
                    or metadata.get("adapter_version") != doc["adapter_version"] \
                    or metadata.get("options_sha256") != doc["options_sha256"] \
                    or not isinstance(metadata.get("segments"), list) \
                    or len(metadata["segments"]) != doc["segment_count"]:
                raise integrity_error(f"Document metadata disagrees with the manifest: {eid}", inside(run, doc["metadata_snapshot_path"]))
            if representation is not None:
                expected_rep = representation_identity("derived_text", f["sha256"], doc["text_sha256"],
                                                        doc["adapter_version"], doc["parsers"],
                                                        doc["options_sha256"], metadata["segments"],
                                                        metadata.get("issues", []))
                if representation != {"version": "1", "kind": "derived_text",
                                       "text_sha256": doc["text_sha256"],
                                       "identity_sha256": expected_rep} or metadata.get("parsers") != doc["parsers"] \
                        or metadata.get("issues") != doc["issues"]:
                    raise KBError(f"Document representation identity mismatch: {eid}")
            if "documents" in m and json_sha(m["documents"]) != doc["options_sha256"]:
                raise KBError(f"Document options digest does not match the frozen policy: {eid}")
            if "documents" not in m:
                raise KBError(f"Manifest contains document evidence without a documents policy: {eid}")
            if policy is not None and m["documents"].get("adapter_version") != doc["adapter_version"]:
                raise KBError(f"Document adapter version disagrees with the frozen policy: {eid}")
            counts[f["source_id"]] += 1
            total += f["bytes"]
            continue
        if f["snapshot_path"] != f"snapshots/{eid}.txt":
            raise KBError("Unexpected snapshot path")
        raw = read_stable(inside(run, f["snapshot_path"]), m["limits"]["max_file_bytes"])
        if sha(raw) != f["sha256"] or len(raw) != f["bytes"]:
            raise integrity_error(f"Snapshot integrity failure: {eid}", inside(run, f["snapshot_path"]))
        if representation is not None and representation != {
                "version": "1", "kind": "source_text", "text_sha256": f["sha256"],
                "identity_sha256": representation_identity("source_text", f["sha256"], f["sha256"])}:
            raise KBError(f"Text representation identity mismatch: {eid}")
        try:
            lines = raw.decode("utf-8-sig").splitlines()
        except UnicodeError as exc:
            raise integrity_error(f"Invalid snapshot encoding: {eid}", inside(run, f["snapshot_path"])) from exc
        if b"\x00" in raw or len(lines) != f["line_count"]:
            raise integrity_error(f"Snapshot line count/content mismatch: {eid}", inside(run, f["snapshot_path"]))
        if f["provenance"] is not None:
            check_timestamp(f["provenance"]["captured_at"])
        content_date = (f.get("temporal") or {}).get("content_date")
        if content_date and len(content_date["value"]) > 10:
            check_timestamp(content_date["value"])
        counts[f["source_id"]] += 1
        total += len(raw)
    if total > m["limits"]["max_total_bytes"] or len(m["files"]) > m["limits"]["max_files"]:
        raise KBError("Manifest exceeds its declared limits")
    if any(s["eligible_count"] != counts[sid] for sid, s in sources.items()):
        raise KBError("Manifest source count mismatch")
    # Empty individual sources are allowed; empty whole inventories are not.
    if m["status"] == "ready" and (
        not m["files"] or any(i["severity"] == "error" for i in m["issues"])
    ):
        raise KBError("Manifest marked ready despite blocking issues or no captured files")
    if m["tool_version"] == "0.4.0":
        frozen_segments = load_segment_inventory(run, m)
        if frozen_segments is None or frozen_segments != build_segment_inventory(run, m):
            raise KBError("Segment inventory disagrees with frozen evidence")
    elif "segment_inventory" in m:
        raise KBError("Historical manifest cannot declare a segment inventory")
    if targeted is not None:
        from .kb_context import check_context
        check_context(run,m)
    return m


def verify_live(m: dict) -> None:
    roots = {s["id"]: Path(s["root"]) for s in m["sources"]}
    for f in m["files"]:
        live = inside(roots[f["source_id"]], f["relative_path"])
        raw = read_stable(live, m["limits"]["max_file_bytes"])
        if sha(raw) != f["sha256"]:
            raise KBError(f"Live source changed since capture: {f['source_id']}/{f['relative_path']}")
    # This is a targeted check, not a rescan. A new inventory is needed to detect additions.


RECORD_KIND_PREFIX = {"requirement": "REQ", "decision": "DEC", "uncertainty": "UNC", "investigation": "INV"}
# Words that mark a statement as not (yet) decided. Matched case-insensitively in quotes.
PENDING_MARKERS = ("propuesto", "propuesta", "pendiente", "a validar", "a definir", "por confirmar",
                   "tbd", "proposed", "pending", "to be confirmed")


def _citations(record: dict) -> list[dict]:
    out = list(record["evidence"])
    if record["investigation"] is not None:
        for finding in record["investigation"]["findings"]:
            out.extend(finding["evidence"])
    return out


def semantic_hints(m: dict, data: dict) -> list[dict]:
    """Reviewer hints about likely overstatement. Hints never fail a check."""
    files = {f["evidence_id"]: f for f in m["files"]}
    ai_sourced = {(i["source_id"], i["path"]) for i in m["issues"] if i["code"] == "ai_generated_source"}
    # Runs captured before the ai_generated_source warning existed: apply the file-name rule.
    ai_sourced |= {(f["source_id"], f["relative_path"]) for f in m["files"]
                   if f["source_type"] != "repository" and (f["provenance"] or {}).get("authorship") is None
                   and ai_summary_name(f["relative_path"])}
    hints = []
    def hint(code: str, rid: str | None, detail: str) -> None:
        hints.append({"code": code, "record_id": rid, "detail": detail})
    for r in data["records"]:
        cites = _citations(r)
        if cites and all(ev["start_line"] == ev["end_line"] for ev in cites):
            hint("single_line_citations", r["id"], "Every citation is one line; check that conditions, "
                 "status qualifiers, and surrounding table rows are not lost")
        if r["kind"] == "decision":
            found = sorted({w for ev in cites for w in PENDING_MARKERS if w in ev["quote"].lower()})
            if found:
                hint("decision_quote_pending_language", r["id"], f"Quote contains {found}; it may be a "
                     "proposal or pending item rather than a decision")
            if r["epistemic_status"] == "observed" and all(
                    (files[ev["evidence_id"]]["source_id"], files[ev["evidence_id"]]["relative_path"]) in ai_sourced
                    for ev in r["evidence"]):
                hint("decision_only_ai_sourced", r["id"], "Observed decision rests only on AI-generated "
                     "summaries; default to interpretation unless a human-authored source corroborates it")
    triaged = [c for c in data["coverage"] if c["disposition"] == "triaged_out"]
    if triaged:
        methods = sorted({c["method"] for c in triaged})
        hints.append({"code": "triaged_coverage", "record_id": None,
                      "detail": f"{len(triaged)} of {len(data['coverage'])} inputs were triaged out, not read in "
                                f"full, by: {methods}"})
    return hints


def check_records(run: Path, m: dict, records_path: Path, stage2: bool = False) -> dict:
    with error_context(records_path):
        return _check_records(run, m, records_path, stage2)


def _check_records(run: Path, m: dict, records_path: Path, stage2: bool) -> dict:
    no_symlinks(records_path)
    data = read_json(records_path)
    contract(data, "records", source=records_path)
    if data["project_id"] != m["project_id"] or data["run_id"] != m["run_id"]:
        raise KBError("Records belong to another project or run")
    if "targeted" in m and data["schema_version"] != "0.6":
        raise KBError("Targeted profile requires records 0.6; older schemas cannot bypass routing or intervals")
    segment_bound = data["schema_version"] in {"0.3", "0.4", "0.5", "0.6"}
    segment_data = load_segment_inventory(run, m) if segment_bound else None
    if segment_bound and segment_data is None:
        raise KBError("Records 0.3/0.4 require a frozen segment inventory")
    if not segment_bound and "segment_coverage" in data:
        raise KBError("Segment coverage requires records 0.3/0.4")
    if data["schema_version"] in {"0.4", "0.5", "0.6"}:
        if any("events" not in r for r in data["records"]):
            raise KBError("Records 0.4 require an events array on every record")
    elif any("events" in r for r in data["records"]):
        raise KBError("Event metadata requires records 0.4")
    segments = {s["segment_id"]: s for s in (segment_data or {}).get("segments", [])}
    files = {f["evidence_id"]: f for f in m["files"]}
    lines = {eid: read_stable(inside(run, f["snapshot_path"]), m["limits"]["max_file_bytes"]).decode("utf-8-sig").splitlines()
             for eid, f in files.items()}
    records = {r["id"]: r for r in data["records"]}
    if len(records) != len(data["records"]):
        duplicates = sorted(rid for rid, count in Counter(r["id"] for r in data["records"]).items() if count > 1)
        raise KBError(f"Duplicate record ids: {duplicates}",
                      suggestion="Give each distinct claim a unique record id and update its relation targets.")
    coverage = {x["evidence_id"]: x for x in data["coverage"]}
    if len(coverage) != len(data["coverage"]) or set(coverage) != set(files):
        duplicates = sorted(eid for eid, count in Counter(c["evidence_id"] for c in data["coverage"]).items() if count > 1)
        raise KBError("Coverage must list every manifest evidence id exactly once; "
                      f"missing={sorted(set(files) - set(coverage))}, unknown={sorted(set(coverage) - set(files))}, duplicate={duplicates}",
                      suggestion="Reconcile the candidate coverage with this run's manifest or coverage stub, using one honest disposition per evidence id.")
    for eid, cov in coverage.items():
        if cov["disposition"] == "triaged_out":
            if data["schema_version"] == "0.1":
                raise KBError(f"Coverage 'triaged_out' requires records schema_version 0.2: {eid}")
            if not cov.get("method", "").strip():
                raise KBError(f"Coverage 'triaged_out' requires a nonempty triage method: {eid}")
        elif "method" in cov:
            raise KBError(f"Coverage 'method' is only allowed for 'triaged_out': {eid}")
    referenced = set()
    referenced_segments = set()
    citation_count = 0
    relation_count = 0
    def cite(ev: dict, record_id: str) -> None:
        nonlocal citation_count
        eid = ev["evidence_id"]
        if eid not in files:
            raise KBError(f"Unknown/stale evidence id: {eid} (record {record_id})",
                          suggestion="Use an evidence id from this run's manifest and revalidate the citation against its frozen lines.")
        start, end = ev["start_line"], ev["end_line"]
        source = files[eid]
        context = (f"record {record_id}; frozen file {run / source['snapshot_path']}; "
                   f"source {source['source_id']}:{source['relative_path']}")
        suggestion = "Correct the candidate citation using the exact lines in the frozen file; do not edit the frozen evidence."
        if start > end or end > len(lines[eid]):
            raise KBError(f"Citation line range is invalid: {eid} {start}:{end} ({context}); file has {len(lines[eid])} lines",
                          suggestion=suggestion)
        expected = "\n".join(lines[eid][start - 1:end])
        if ev["quote"] != expected:
            raise KBError(f"Quote differs from exact frozen lines: {eid} {start}:{end} ({context})",
                          suggestion=suggestion)
        if segment_bound:
            segment_id = ev.get("segment_id")
            segment = segments.get(segment_id)
            if segment is None or segment["evidence_id"] != eid \
                    or segment["representation_sha256"] != ev.get("representation_sha256") \
                    or start < segment["line_start"] or end > segment["line_end"]:
                raise KBError(f"Citation does not bind one frozen segment: {eid} {start}:{end} ({context})",
                              suggestion="Check the segment id, representation hash and line bounds against segments.snapshot.json; correct the candidate citation.")
            referenced_segments.add(segment_id)
        elif "segment_id" in ev or "representation_sha256" in ev:
            raise KBError("Segment citations require records 0.3")
        referenced.add(eid)
        citation_count += 1
    for r in records.values():
        if not r["id"].startswith(RECORD_KIND_PREFIX[r["kind"]] + "-"):
            raise KBError(f"Record prefix/kind mismatch: {r['id']}")
        for ev in r["evidence"]:
            cite(ev, r["id"])
        if r["kind"] == "decision" and all(files[ev["evidence_id"]]["source_type"] == "repository" for ev in r["evidence"]):
            raise KBError(f"Decision cites only repository evidence: {r['id']}. Code shows an implementation "
                          "observation, not product intent; cite a non-repository source, or record it as an "
                          "investigation finding or a requirement-vs-implementation uncertainty")
        seen_edges = set()
        for edge in r["relations"]:
            if edge["target"] not in records or edge["target"] == r["id"]:
                raise KBError(f"Dangling/self relation from {r['id']} to {edge['target']}")
            key = (edge["type"], edge["target"])
            if key in seen_edges:
                raise KBError(f"Duplicate relation: {r['id']} {key}")
            seen_edges.add(key)
            relation_count += 1
        if r["kind"] == "uncertainty" and (r["epistemic_status"] != "unresolved" or not r["open_questions"]):
            raise KBError(f"Uncertainty needs unresolved status and an open question: {r['id']}")
        if r["kind"] == "investigation":
            inv = r["investigation"]
            if inv is None:
                raise KBError(f"Investigation details required: {r['id']}")
            if not set(inv["scope"]).issubset(files):
                raise KBError(f"Investigation scope contains unknown evidence: {r['id']}")
            cited = {ev["evidence_id"] for ev in r["evidence"]}
            for finding in inv["findings"]:
                for ev in finding["evidence"]:
                    cite(ev, r["id"])
                    cited.add(ev["evidence_id"])
            if not cited.issubset(inv["scope"]):
                raise KBError(f"Investigation cites beyond declared scope: {r['id']}")
        elif r["investigation"] is not None:
            raise KBError(f"Only investigation records may contain investigation details: {r['id']}")
    if {eid for eid, cov in coverage.items() if cov["disposition"] == "used"} != referenced:
        raise KBError("Coverage 'used' entries must match the evidence actually cited")
    segment_coverage = {}
    if segment_bound:
        if "segment_coverage" not in data:
            raise KBError("Records 0.3 require segment coverage")
        segment_coverage = {x["segment_id"]: x for x in data["segment_coverage"]}
        if len(segment_coverage) != len(data["segment_coverage"]) or set(segment_coverage) != set(segments):
            raise KBError("Segment coverage must list every frozen segment exactly once")
        for sid, cov in segment_coverage.items():
            if cov["disposition"] == "triaged_out":
                if not cov.get("method", "").strip():
                    raise KBError(f"Triaged segment requires a method: {sid}")
            elif "method" in cov:
                raise KBError(f"Segment coverage method is only allowed for triaged_out: {sid}")
        if {sid for sid, cov in segment_coverage.items() if cov["disposition"] == "used"} != referenced_segments:
            raise KBError("Segment coverage 'used' entries must match cited segments")
        for sid, segment in segments.items():
            parent = coverage[segment["evidence_id"]]["disposition"]
            child = segment_coverage[sid]["disposition"]
            if data["schema_version"] != "0.6" and parent in {"triaged_out", "reviewed_no_record", "deferred"} and child != parent:
                raise KBError(f"Segment coverage conflicts with its file disposition: {sid}")
    interval_counts = {}
    assertion_hints = []
    if data["schema_version"] == "0.6":
        from .kb_reconciliation import check_assertions
        assertion_hints = check_assertions(m, data)
        from .kb_intervals import check_intervals
        interval_counts = check_intervals(run, m, data, segments, [e for r in records.values() for e in _citations(r)], stage2)
        for r in records.values():
            refs = [a["evidence_ref"] for a in r["attribution"]]
            if sorted(refs) != list(range(len(_citations(r)))):
                raise KBError("Every parent citation needs exactly one attribution assessment")
            for a in r["attribution"]:
                if a["class"] == "R2" or (a["class"] in {"unknown", "R3"} and r["epistemic_status"] == "observed"):
                    raise KBError("Other-project-only or unknown attribution cannot become observed home knowledge")
                if a["class"] == "home" and a["project_id"] != m["project_id"]:
                    raise KBError("Home attribution must name this project")
                if a["class"] in {"R1", "R4"} and not any(l["project_id"] == a["project_id"] for l in r["cross_project"]):
                    raise KBError("R1/R4 attribution requires a freshly assessed cross-project link")
    if stage2 and not records:
        raise KBError("Stage 2 publication requires at least one record; an empty snapshot would also retire "
                      "every record of the current release")
    if stage2 and any(c["disposition"] == "deferred" for c in coverage.values()):
        raise KBError("Stage 2 publication requires all scoped evidence reviewed or explicitly triaged; "
                      "narrow scope or finish deferred inputs")
    if stage2 and any(c["disposition"] == "deferred" for c in segment_coverage.values()):
        raise KBError("Stage 2 publication requires all frozen segments reviewed or explicitly triaged")
    # The Stage 2 milestone (one of each kind plus a relation) is reported, never a gate:
    # a quota gate rewards fabricating a category to pass.
    missing_kinds = sorted(set(RECORD_KIND_PREFIX) - {r["kind"] for r in records.values()})
    event_count, event_status, effective_status = (check_record_events(data["records"])
                                                    if data["schema_version"] in {"0.4", "0.5", "0.6"} else (0, {}, {}))
    return {**interval_counts, "assertion_hints": assertion_hints, "record_count": len(records), "citation_count": citation_count,
            "event_count": event_count, "event_date_status_counts": event_status,
            "effective_date_status_counts": effective_status,
            "relation_count": relation_count, "coverage_count": len(coverage),
            "coverage_counts": dict(sorted(Counter(c["disposition"] for c in coverage.values()).items())),
            "segment_coverage_counts": dict(sorted(Counter(c["disposition"] for c in segment_coverage.values()).items())),
            "unavailable_segment_issues": sum(1 for i in (segment_data or {}).get("issues", [])
                                              if i["status"] == "unavailable"),
            "kind_counts": dict(Counter(r["kind"] for r in records.values())),
            "stage2_milestone": {"met": not missing_kinds and relation_count > 0,
                                 "missing_record_kinds": missing_kinds, "has_relation": relation_count > 0},
            "semantic_hints": semantic_hints(m, data)}


def check_run(run: Path, records_path: Path | None = None, stage2: bool = False, live: bool = False, historical: bool = False) -> dict:
    m = load_manifest(run)
    if m["status"] != "ready":
        raise blocked_inventory_error(run, m)
    from .kb_context import check_context
    context_report = check_context(run,m, Path(m["targeted"]["config_path"]) if "targeted" in m and not historical else None)
    if live:
        verify_live(m)
    records_raw = read_stable(records_path, 16 * 1024 * 1024) if records_path is not None else None
    counts = check_records(run, m, records_path, stage2) if records_path is not None else {}
    if records_path is not None:
        records_data = read_json(records_path)
        if records_data["schema_version"] in {"0.5", "0.6"}:
            from .kb_referrals_contract import check_referrals
            counts.update(check_referrals(run, m, records_data))
        if sha(read_stable(records_path, 16 * 1024 * 1024)) != sha(records_raw):
            raise KBError("Records changed during checking; retry on stable inputs")
    return {"status": "passed", "checked_at": utc_now(), "tool_version": TOOL_VERSION,
            "project_id": m["project_id"], "run_id": m["run_id"],
            "file_count": len(m["files"]), "stage2_gate": stage2, **context_report,
            "live_existing_files_checked": live, **counts,
            "limitations": ["Checks establish integrity and structural consistency, not semantic truth or upstream authority.",
                            "Coverage dispositions are declarations requiring human review; triaged_out inputs were not read in full.",
                            "semantic_hints are reviewer prompts, not gates; their absence is not semantic validation.",
                            "Live checking does not discover newly added files; use a new inventory for that."]}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--records", type=Path)
    p.add_argument("--inventory-only", action="store_true")
    p.add_argument("--stage2", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--historical", action="store_true", help="Frozen integrity only; never a prospective permission/publication check")
    p.add_argument("--report", type=Path)
    a = p.parse_args()
    if a.inventory_only and a.stage2:
        raise KBError("--inventory-only and --stage2 are mutually exclusive")
    path = None if a.inventory_only else (a.records or a.run / "proposals" / "records.json")
    report = check_run(a.run, path, a.stage2, a.live, a.historical)
    if a.report:
        write_json_new(a.report, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    run_cli(main)
