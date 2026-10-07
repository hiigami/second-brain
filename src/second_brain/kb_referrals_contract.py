"""Validate run-local routing proposals against frozen evidence and scoped grants."""
from pathlib import Path

from .kb_common import (KBError, contract, inside, json_sha, matches, read_json,
                       read_stable, sha)
from .kb_mentions import build_mention_report, validate_registry


def check_referrals(run: Path, manifest: dict, records: dict) -> dict:
    """Check complete mention disposition and exact, authorized referral context."""
    from .kb_check import load_segment_inventory

    registry_path = inside(run, "work/registry.snapshot.json")
    registry = validate_registry(read_json(registry_path))
    if registry["schema_version"] != "1.1":
        raise KBError("Records 0.5 routing requires registry 1.1 with explicit disclosure grants")
    mention_path = inside(run, "work/mentions.json")
    mention_raw = read_stable(mention_path, 16 * 1024 * 1024)
    mentions = read_json(mention_path)
    if mentions != build_mention_report(run, registry):
        raise KBError("Mention report differs from the frozen registry or evidence")
    path = inside(run, "proposals/referrals.json") if (run / "proposals/referrals.json").is_file() else inside(run, "referrals.json")
    proposals = read_json(path)
    contract(proposals, "referrals")
    if records["schema_version"] == "0.6" and proposals["schema_version"] != "1.1":
        raise KBError("Records 0.6 require referrals 1.1 with manual-reference accounting")
    if proposals["project_id"] != manifest["project_id"] or proposals["run_id"] != manifest["run_id"]:
        raise KBError("Referrals belong to another project or run")
    if proposals["registry_sha256"] != json_sha(registry) or proposals["mentions_sha256"] != sha(mention_raw):
        raise KBError("Referrals are stale against the frozen registry or mention scan")
    hits = {m["id"]: m for m in mentions["mentions"]}
    if len(mentions["mentions"]) + len(proposals.get("manual_mentions", [])) > 10000:
        raise KBError("Scanned plus manual references exceed 10,000; narrow the run")
    for manual in proposals.get("manual_mentions", []):
        source = manual["source"]
        file = next((f for f in manifest["files"] if f["evidence_id"] == source["evidence_id"]), None)
        inventory = load_segment_inventory(run, manifest)
        segment = next((s for s in inventory["segments"] if s["segment_id"] == source["segment_id"]), None)
        if file is None or segment is None or segment["evidence_id"] != source["evidence_id"] \
                or segment["representation_sha256"] != source["representation_sha256"] \
                or not segment["line_start"] <= source["start_line"] <= source["end_line"] <= segment["line_end"]:
            raise KBError("Manual reference must bind an exact frozen segment range")
        lines = read_stable(inside(run, file["snapshot_path"]), manifest["limits"]["max_file_bytes"]).decode("utf-8-sig").splitlines()
        if source["quote"] != "\n".join(lines[source["start_line"] - 1:source["end_line"]]):
            raise KBError("Manual reference quote differs from frozen evidence")
        if "targeted" in manifest:
            from .kb_intervals import selected_ranges
            from .kb_targeting import load_targeted
            selected = selected_ranges(run, manifest, load_targeted(run, manifest))[0]
            if not any(a <= source["start_line"] <= source["end_line"] <= b for a,b in selected.get(source["evidence_id"], [])):
                raise KBError("Manual reference is outside selected passages")
        projects = {p["id"]: p for p in registry["projects"]}
        target = manual["target_project_id"]
        if target not in projects or target == manifest["project_id"] or projects[target]["information_domain"] != projects[manifest["project_id"]]["information_domain"]:
            raise KBError("Manual reference target must be a different registered same-domain project")
        mid = "M-" + json_sha(["manual", source, target])[:24]
        if mid in hits:
            raise KBError("Duplicate manual reference")
        hits[mid] = {"id": mid, "evidence_id": source["evidence_id"], "line": source["start_line"],
                     "end_line": source["end_line"], "target_project_id": target,
                     "segments": [{"segment_id": source["segment_id"]}]}
    assessments = {a["mention_id"]: a for a in proposals["assessments"]}
    if len(assessments) != len(proposals["assessments"]) \
            or set(assessments) != set(hits):
        raise KBError("Every scanned mention requires exactly one routing assessment")
    referrals = {r["id"]: r for r in proposals["referrals"]}
    if len(referrals) != len(proposals["referrals"]):
        raise KBError("Duplicate referral ids")
    projects = {p["id"]: p for p in registry["projects"]}
    home_domain = projects[manifest["project_id"]]["information_domain"]
    files = {f["evidence_id"]: f for f in manifest["files"]}
    segments = {s["segment_id"]: s for s in load_segment_inventory(run, manifest)["segments"]}
    records_by_id = {r["id"]: r for r in records["records"]}
    file_coverage = {c["evidence_id"]: c for c in records["coverage"]}
    segment_coverage = {c["segment_id"]: c for c in records["segment_coverage"]}
    selected = None
    if "targeted" in manifest:
        from .kb_intervals import selected_ranges
        from .kb_targeting import load_targeted
        selected = selected_ranges(run, manifest, load_targeted(run, manifest))[0]
    linked: set[tuple[str, str]] = set()
    used_referrals = set()
    for mid, assessment in assessments.items():
        hit = hits[mid]
        if not hit["segments"]:
            raise KBError(f"Mention lacks a frozen segment locator: {mid}")
        target = hit["target_project_id"]
        kind, disposition = assessment["class"], assessment["disposition"]
        homes = assessment["home_record_ids"]
        if any(rid not in records_by_id for rid in homes):
            raise KBError(f"Assessment {mid} links an unknown home record")
        if (kind == "R2" and homes) or (kind == "R3" and (homes or disposition not in {"dismissed", "unresolved"})):
            raise KBError(f"R2 target-only or R3 context mention has an invalid home disposition: {mid}")
        if kind == "R1" and not homes:
            raise KBError(f"R1 constrains home and requires a cited home record: {mid}")
        if disposition == "linked_home" and (kind not in {"R1", "R4"} or not homes):
            raise KBError(f"Linked-home mention lacks a relevant home record: {mid}")
        if disposition == "dismissed" and kind != "R3":
            raise KBError(f"Only R3 context mentions may be dismissed: {mid}")
        if homes:
            f = files[hit["evidence_id"]]
            if not any(g["from_project"] == manifest["project_id"] and g["to_project"] == target
                       and g["source_id"] == f["source_id"] and matches(f["relative_path"], g["path_pattern"])
                       for g in registry["disclosures"]):
                raise KBError(f"No explicit disclosure grant covers the home cross-project link: {mid}")
        if disposition == "referred":
            rid = assessment["referral_id"]
            referral = referrals.get(rid)
            if referral is None or rid in used_referrals or kind == "R3":
                raise KBError(f"Referral mapping is missing, repeated, or R3: {mid}")
            used_referrals.add(rid)
            if referral["target_project_id"] != target or referral["class"] != kind \
                    or referral["home_record_ids"] != homes:
                raise KBError(f"Referral target/class/home links disagree with mention {mid}")
            source = referral["source"]
            f = files.get(source["evidence_id"])
            segment = segments.get(source["segment_id"])
            if f is None or source["evidence_id"] != hit["evidence_id"] or segment is None \
                    or segment["evidence_id"] != hit["evidence_id"] \
                    or segment["representation_sha256"] != source["representation_sha256"] \
                    or not (segment["line_start"] <= source["start_line"] <= hit["line"]
                            <= hit.get("end_line", hit["line"]) <= source["end_line"] <= segment["line_end"]):
                raise KBError(f"Referral citation is outside the frozen mention segment: {rid}")
            lines = read_stable(inside(run, f["snapshot_path"]), manifest["limits"]["max_file_bytes"]).decode("utf-8-sig").splitlines()
            if source["quote"] != "\n".join(lines[source["start_line"] - 1:source["end_line"]]):
                raise KBError(f"Referral quote differs from frozen evidence: {rid}")
            if selected is not None and not any(a <= source["start_line"] <= source["end_line"] <= b
                                               for a,b in selected.get(source["evidence_id"], [])):
                raise KBError(f"Referral is outside selected passages: {rid}")
            if any(row["segment_id"] == source["segment_id"]
                   and row["start_line"] <= source["end_line"] and source["start_line"] <= row["end_line"]
                   and row["disposition"] in {"triaged_out", "deferred"}
                   for row in records.get("interval_coverage", [])):
                raise KBError(f"Referral cites an unread interval: {rid}")
            if file_coverage[f["evidence_id"]]["disposition"] in {"triaged_out", "deferred"} \
                    or segment_coverage[segment["segment_id"]]["disposition"] in {"triaged_out", "deferred"}:
                raise KBError(f"Referral cites material marked unread: {rid}")
            capture = referral["suggested_capture"]
            if capture != {"source_id": f["source_id"], "relative_path": f["relative_path"],
                            "include_pattern": f["relative_path"]}:
                raise KBError(f"Referral capture suggestion must name only the exact source path: {rid}")
            if target not in projects or projects[target]["information_domain"] != home_domain:
                raise KBError(f"Referral targets an unregistered or different-domain project: {rid}")
            if not any(g["from_project"] == manifest["project_id"] and g["to_project"] == target
                       and g["source_id"] == f["source_id"] and matches(f["relative_path"], g["path_pattern"])
                       for g in registry["disclosures"]):
                raise KBError(f"No explicit disclosure grant covers referral destination/source: {rid}")
        elif assessment["referral_id"] is not None:
            raise KBError(f"Non-referred mention has a referral id: {mid}")
        if kind == "R2":
            for record in records["records"]:
                cites = list(record["evidence"])
                if record["investigation"] is not None:
                    cites += [e for finding in record["investigation"]["findings"] for e in finding["evidence"]]
                if any(e["evidence_id"] == hit["evidence_id"]
                       and e["start_line"] <= hit.get("end_line", hit["line"]) and hit["line"] <= e["end_line"] for e in cites):
                    raise KBError(f"R2 target-only mention was cited as home knowledge: {mid}")
        for home in homes:
            record = records_by_id[home]
            if not any(e["evidence_id"] == hit["evidence_id"]
                       and e["start_line"] <= hit["line"] <= hit.get("end_line", hit["line"]) <= e["end_line"] for e in record["evidence"]):
                raise KBError(f"Home cross-project record lacks this mention's evidence: {mid}")
            linked.add((home, target))
    if used_referrals != set(referrals):
        raise KBError("Every referral must map to one assessed mention")
    declared = set()
    for record in records["records"]:
        for link in record["cross_project"]:
            target = link["project_id"]
            if target == manifest["project_id"] or target not in projects \
                    or projects[target]["information_domain"] != home_domain:
                raise KBError(f"Home record links an invalid cross-project target: {record['id']}")
            if link["target_record"] is not None and not link["target_record"].startswith(target + ":"):
                raise KBError(f"Target record reference does not match project {target}")
            pair = (record["id"], target)
            if pair in declared:
                raise KBError(f"Duplicate home cross-project link: {pair}")
            declared.add(pair)
    if declared != linked:
        raise KBError("Home cross-project links must match assessed R1/R4 mention evidence")
    if records["schema_version"] == "0.6":
        for record in records["records"]:
            for attribution in record["attribution"]:
                if attribution["class"] not in {"R1", "R4"}:
                    continue
                cites = list(record["evidence"])
                if record["investigation"] is not None:
                    cites += [e for f in record["investigation"]["findings"] for e in f["evidence"]]
                cite = cites[attribution["evidence_ref"]]
                if not any(a["class"] == attribution["class"] and record["id"] in a["home_record_ids"]
                           and hits[mid]["target_project_id"] == attribution["project_id"]
                           and hits[mid]["evidence_id"] == cite["evidence_id"]
                           and cite["start_line"] <= hits[mid]["line"] <= cite["end_line"]
                           for mid,a in assessments.items()):
                    raise KBError("Citation attribution lacks matching fresh evidence-backed routing assessment")
    return {"mention_assessment_count": len(assessments), "referral_count": len(referrals),
            "routing_unresolved_count": sum(a["disposition"] == "unresolved" for a in assessments.values())}
