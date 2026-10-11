#!/usr/bin/env python3
"""Discover reviewed origin referrals and record human target intake, never publish."""
import argparse
import copy
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .kb_check import check_run, load_manifest, load_segment_inventory
from .kb_common import (CLOCK_SKEW_SECONDS, KBError, atomic_json, contract, inside,
                       json_bytes, json_sha, load_project, matches, no_symlinks,
                       parse_ts, read_json, read_stable, run_cli, sha, utc_now,
                       validate_schema, warning_summary, write_json_new)
from .kb_mentions import load_registry
from .kb_publish import (current_release_records, read_work, render_outbox,
                        triaged_ids, triaged_segment_ids, work_digest)

LIMIT = 16 * 1024 * 1024
MAX_ITEMS = 10000


def _item_id(origin: str, run: str, referral: str) -> str:
    return "INT-" + json_sha([origin, run, referral])[:24]


def _family(item: dict) -> tuple:
    # A repeated source-path/referral slot is a review lineage hint, not proof
    # that the new business claim semantically supersedes the old one.
    return (item["origin_project_id"], item["source_file"]["source_id"],
            item["source_file"]["relative_path"], item["referral"]["id"])


def _has_quote(text: str, quote: str) -> bool:
    return "\n" + quote + "\n" in "\n" + "\n".join(text.splitlines()) + "\n"


def _source_file(origin: dict, referral: dict) -> dict:
    file = origin["files"][referral["source"]["evidence_id"]]
    segment = origin["segments"][referral["source"]["segment_id"]]
    return {"source_id": file["source_id"], "relative_path": file["relative_path"],
            "sha256": file["sha256"], "original_locator": segment["original_locator"]}


def _task(item: dict, review: dict) -> dict | None:
    if review["decision"] != "accept":
        return None
    capture = review["capture_authorization"]
    status = ("blocked_source_" + item["source_status"] if item["source_status"] != "current" else
              "proposed_capture_reconciliation" if capture else "blocked_capture_authorization")
    return {"status": status,
            "intake_review_sha256": json_sha(review), "capture_authorization": capture,
            "provenance": {"origin_project_id": item["origin_project_id"],
                           "origin_run_id": item["origin_run_id"],
                           "origin_review_sha256": item["origin_review_sha256"],
                           "referral_id": item["referral"]["id"],
                           "source_file": item["source_file"], "source": item["referral"]["source"]}}


def _human(review: dict, floor: str) -> None:
    if not review["reviewer"].strip() or not review["reason"].strip():
        raise KBError("A named human reviewer and nonblank reason are required")
    timestamp = parse_ts(review["reviewed_at"])
    if timestamp < parse_ts(floor) or timestamp > datetime.now(timezone.utc) + timedelta(seconds=CLOCK_SKEW_SECONDS):
        raise KBError("Human review timestamp precedes the item/release or is in the future")


def _validate_ledger(data: dict, project_id: str) -> None:
    contract(data, "referral-intake")
    if data["project_id"] != project_id or len(data["items"]) > MAX_ITEMS:
        raise KBError("Wrong target project or intake exceeds 10,000 items")
    scan_ids = [s["project_id"] for s in data["origin_scans"]]
    if len(scan_ids) != len(set(scan_ids)) or project_id in scan_ids \
            or any((s["status"] == "checked") != (s["run_id"] is not None) for s in data["origin_scans"]):
        raise KBError("Invalid or duplicate origin scan summary")
    seen = {}
    # Reuse the exact referral item shape, without weakening that contract.
    from .kb_common import SCHEMAS
    referral_schema = read_json(SCHEMAS / "referrals.schema.json")
    for item in data["items"]:
        validate_schema(item["referral"], referral_schema["properties"]["referrals"]["items"])
        if item["referral"]["target_project_id"] != project_id or item["origin_project_id"] == project_id \
                or item["id"] != _item_id(item["origin_project_id"], item["origin_run_id"], item["referral"]["id"]) \
                or item["id"] in seen:
            raise KBError("Duplicate, invalid or cross-project intake identity")
        seen[item["id"]] = item
        if item["source_status"] != item["observations"][-1]["status"]:
            raise KBError("Intake status differs from its audit trail")
        for observation in item["observations"]:
            parse_ts(observation["at"])
        decisions = set()
        for decision in item["decisions"]:
            contract(decision, "intake-review")
            _human(decision, item["observations"][0]["at"])
            if decision["item_id"] != item["id"] or decision["origin_review_sha256"] != item["origin_review_sha256"] \
                    or json_sha(decision) in decisions:
                raise KBError("Duplicate or mismatched intake review")
            if decision["decision"] != "accept" and decision["capture_authorization"] is not None:
                raise KBError("Only acceptance may authorize a proposed capture")
            decisions.add(json_sha(decision))
        expected = _task(item, item["decisions"][-1]) if item["decisions"] else None
        if item["capture_task"] != expected:
            raise KBError("Capture task differs from the last explicit intake review")
        links = set()
        for link in item["target_links"]:
            if set(link) != {"review", "evidence_comparison"}:
                raise KBError("Invalid target link audit entry")
            contract(link["review"], "intake-link")
            _human(link["review"], item["observations"][0]["at"])
            if link["review"]["item_id"] != item["id"] or json_sha(link["review"]) in links:
                raise KBError("Duplicate or mismatched target link")
            links.add(json_sha(link["review"]))
            for comparison in link["evidence_comparison"]:
                if set(comparison) != {"record_id", "evidence_id", "original_sha256",
                                      "representation_sha256", "original_locator", "comparison"} \
                        or comparison["record_id"] not in link["review"]["record_ids"] \
                        or comparison["comparison"] not in {"same_representation_and_locator",
                                                            "different_representation_or_locator", "scoped_export"}:
                    raise KBError("Invalid target evidence comparison")
            if {c["record_id"] for c in link["evidence_comparison"]} != set(link["review"]["record_ids"]):
                raise KBError("Target link must compare evidence for every linked record")
    for item in data["items"]:
        previous = item["supersedes"]
        if previous is not None and (previous not in seen or _family(seen[previous]) != _family(item)):
            raise KBError("Invalid intake review lineage")
        chain = {item["id"]}
        while previous is not None:
            if previous in chain:
                raise KBError("Cyclic intake review lineage")
            chain.add(previous)
            previous = seen[previous]["supersedes"]


@contextmanager
def _ledger(config: Path):
    cfg, _, locations = load_project(config)
    # Fixed derived/audit location; never inside the approved subtree.
    path = inside(locations["knowledge"], "referral-intake.json")
    if path.is_relative_to(locations["approved"]):
        raise KBError("Intake ledger overlaps approved knowledge")
    lock = inside(locations["knowledge"], ".referral-intake.lock")
    write_json_new(lock, {"created_at": utc_now()})
    try:
        before = read_stable(path, LIMIT) if path.exists() else None
        data = read_json(path) if before is not None else {
            "schema_version": "1.0", "project_id": cfg["project"]["id"], "origin_scans": [], "items": []}
        _validate_ledger(data, cfg["project"]["id"])
        original = copy.deepcopy(data)
        yield data
        _validate_ledger(data, cfg["project"]["id"])
        if data != original or before is None:
            if len(json_bytes(data)) > LIMIT:
                raise KBError("Intake ledger exceeds 16 MiB")
            if (read_stable(path, LIMIT) if path.exists() else None) != before:
                raise KBError("Intake ledger changed during operation; retry")
            atomic_json(path, data)
    finally:
        lock.unlink(missing_ok=True)


def _approved_release(config: Path, run_id: str | None = None) -> dict | None:
    cfg, _, locations = load_project(config)
    project_id = cfg["project"]["id"]
    pointer_path = inside(locations["approved"], "CURRENT.json")
    pointer_bytes = read_stable(pointer_path, LIMIT) if pointer_path.exists() else None
    current, _ = current_release_records(locations["approved"], project_id)
    if run_id is None:
        run_id = current
    if run_id is None:
        return None
    # A prepared review placed in an approved-looking directory is not a release.
    history_path = inside(locations["approved"], "HISTORY.jsonl")
    history = read_stable(history_path, LIMIT).decode("utf-8").splitlines()
    try:
        published = [json.loads(line) for line in history if line]
    except ValueError as exc:
        raise KBError("Malformed publication history") from exc
    if not any(isinstance(entry, dict) and entry.get("run_id") == run_id for entry in published):
        raise KBError("Release is absent from the publication history")
    release = inside(locations["approved"], run_id)
    check_run(release, inside(release, "records.json"), stage2=True, historical=True)
    manifest = load_manifest(release)
    records = read_json(inside(release, "records.json"))
    review = read_json(inside(release, "review.json"))
    contract(review, "review", source=release / "review.json")
    if review["schema_version"] not in {"0.3", "0.4"} or review["decision"] != "approve" \
            or not review["reviewer"].strip() or not all(review["checks"].values()) \
            or review["project_id"] != project_id or manifest["project_id"] != project_id \
            or review["run_id"] != run_id or manifest["run_id"] != run_id:
        raise KBError("Intake requires a published, approved report-bound release")
    _human({"reviewer": review["reviewer"], "reviewed_at": review["reviewed_at"], "reason": "Approved release"},
           max(manifest["created_at"], review["prepared_at"] or manifest["created_at"], key=parse_ts))
    for filename, key in (("manifest.json", "manifest_sha256"), ("records.json", "records_sha256"),
                          ("review-report.md", "review_report_sha256")):
        if sha(read_stable(inside(release, filename), LIMIT)) != review[key]:
            raise KBError(f"Approved release binding changed: {filename}")
    if work_digest(read_work(release)) != review["work_sha256"] \
            or set(review["approved_record_ids"]) != {r["id"] for r in records["records"]} \
            or review["warning_summary"] != warning_summary(manifest) \
            or review["acknowledged_warnings"] != review["warning_summary"]["counts"] \
            or review["triaged_evidence_ids"] != triaged_ids(records) \
            or review["triaged_segment_ids"] != triaged_segment_ids(records) \
            or (triaged_ids(records) and not review["triage_acknowledged"]) \
            or (triaged_segment_ids(records) and not review["segment_triage_acknowledged"]):
        raise KBError("Approved release audit or review gate changed")
    referrals = []
    if records["schema_version"] in {"0.5", "0.6"}:
        if review["schema_version"] != "0.4":
            raise KBError("Routed release lacks routing approval")
        for filename, key in (("referrals.json", "referrals_sha256"),
                              ("work/mentions.json", "mentions_sha256"),
                              ("work/registry.snapshot.json", "registry_sha256")):
            path = inside(release, filename)
            digest = json_sha(read_json(path)) if filename.endswith("registry.snapshot.json") else sha(read_stable(path, LIMIT))
            if digest != review[key]:
                raise KBError(f"Approved routing binding changed: {filename}")
        routing = read_json(inside(release, "referrals.json"))
        if read_stable(inside(release, "outbox.md"), LIMIT) != render_outbox(manifest, routing):
            raise KBError("Approved outbox changed")
        referrals = routing["referrals"]
    bound_files = ["manifest.json", "records.json", "review.json", "review-report.md"]
    if referrals or records["schema_version"] in {"0.5", "0.6"}:
        bound_files += ["referrals.json", "outbox.md"]
    segments = load_segment_inventory(release, manifest)
    result = {"project_id": project_id, "run_id": run_id, "release": release,
              "manifest": manifest, "records": records, "referrals": referrals,
              "files": {f["evidence_id"]: f for f in manifest["files"]},
              "segments": {s["segment_id"]: s for s in segments["segments"]} if segments else {},
              "review_sha256": sha(read_stable(inside(release, "review.json"), LIMIT)),
              "bindings": {f: sha(read_stable(inside(release, f), LIMIT)) for f in bound_files},
              "work_sha256": review["work_sha256"],
              "pointer_path": pointer_path, "pointer_bytes": pointer_bytes}
    if run_id == current:
        pointer = json.loads(pointer_bytes.decode("utf-8-sig"))
        for filename, key in (("manifest.json", "manifest_sha256"), ("records.json", "records_sha256"),
                              ("review.json", "review_sha256")):
            if result["bindings"][filename] != pointer[key]:
                raise KBError("Approved release changed after CURRENT validation; retry")
    _stable_pointer(result)
    return result


def _stable_pointer(origin: dict) -> None:
    if (read_stable(origin["pointer_path"], LIMIT) if origin["pointer_path"].exists() else None) != origin["pointer_bytes"]:
        raise KBError("CURRENT changed during intake; retry")
    if any(sha(read_stable(inside(origin["release"], file), LIMIT)) != digest
           for file, digest in origin["bindings"].items()) \
            or work_digest(read_work(origin["release"])) != origin["work_sha256"]:
        raise KBError("Approved release changed during intake; retry")
    check_run(origin["release"], inside(origin["release"], "records.json"), stage2=True, historical=True)


def load_approved_release(config: Path, run_id: str | None = None) -> dict | None:
    """Read a checked published release for other derived tools, without mutation."""
    return _approved_release(config, run_id)


def verify_approved_release(release: dict) -> None:
    """Reject detected pointer, bound-artifact, or frozen-evidence changes."""
    _stable_pointer(release)


def _allowed(registry: dict, origin: str, target: str, source: dict) -> bool:
    projects = {p["id"]: p for p in registry["projects"]}
    return origin in projects and target in projects and origin != target \
        and projects[origin]["information_domain"] == projects[target]["information_domain"] \
        and any(g["from_project"] == origin and g["to_project"] == target
                and g["source_id"] == source["source_id"] and matches(source["relative_path"], g["path_pattern"])
                for g in registry["disclosures"])


def _registry(path: Path, target: str) -> dict:
    registry = load_registry(path)
    if registry["schema_version"] != "1.1" or target not in {p["id"] for p in registry["projects"]}:
        raise KBError("Target intake requires registry 1.1 and a registered target")
    return registry


def _observe(item: dict, status: str, reason: str) -> None:
    if item["source_status"] != status:
        item["source_status"] = status
        item["observations"].append({"at": utc_now(), "status": status, "reason": reason})
        if item["decisions"]:
            item["capture_task"] = _task(item, item["decisions"][-1])


def discover(config: Path, registry_path: Path, origin_configs: list[Path]) -> dict:
    """Update only the target ledger, using an explicit authorized origin set."""
    target = load_project(config)[0]["project"]["id"]
    registry = _registry(registry_path, target)
    origins = {}
    for origin_config in origin_configs:
        pid = load_project(origin_config)[0]["project"]["id"]
        if pid == target or pid in origins:
            raise KBError("Origin configurations must be unique and different from target")
        # Do not even inspect release content for unregistered/cross-domain origins.
        projects = {p["id"]: p for p in registry["projects"]}
        if pid not in projects or projects[pid]["information_domain"] != projects[target]["information_domain"] \
                or not any(g["from_project"] == pid and g["to_project"] == target for g in registry["disclosures"]):
            origins[pid] = ("unauthorized", None)
            continue
        try:
            origin = _approved_release(origin_config)
            origins[pid] = ("current" if origin else "unavailable", origin)
        except (KBError, OSError, UnicodeError):
            # No source content or filesystem diagnostics are exported on failure.
            origins[pid] = ("unavailable", None)
    with _ledger(config) as data:
        scans = {s["project_id"]: {"project_id": s["project_id"], "status": "stale", "run_id": None}
                 for s in data["origin_scans"]}
        scans.update({pid: {"project_id": pid, "status": "checked" if origin else status,
                            "run_id": origin["run_id"] if origin else None}
                      for pid, (status, origin) in origins.items()})
        data["origin_scans"] = [scans[pid] for pid in sorted(scans)]
        by_id = {item["id"]: item for item in data["items"]}
        visible = {}
        for pid, (_, origin) in origins.items():
            if origin is None:
                continue
            files = {f["evidence_id"]: f for f in origin["manifest"]["files"]}
            for referral in origin["referrals"]:
                if referral["target_project_id"] != target:
                    continue
                file = files[referral["source"]["evidence_id"]]
                if not _allowed(registry, pid, target, file):
                    continue
                iid = _item_id(pid, origin["run_id"], referral["id"])
                source = _source_file(origin, referral)
                item = {"id": iid, "origin_project_id": pid, "origin_run_id": origin["run_id"],
                        "origin_review_sha256": origin["review_sha256"], "referral": referral,
                        "source_file": source, "supersedes": None, "source_status": "current",
                        "observations": [{"at": utc_now(), "status": "current", "reason": "Discovered from authorized approved origin."}],
                        "decisions": [], "capture_task": None, "target_links": []}
                if iid in by_id:
                    old = by_id[iid]
                    if any(old[k] != item[k] for k in ("origin_review_sha256", "referral", "source_file")):
                        raise KBError("An immutable origin item changed; restore its approved release")
                    item = old
                    _observe(item, "current", "Origin release is current and authorized again.")
                else:
                    predecessors = [i for i in data["items"] if _family(i) == _family(item)]
                    if predecessors:
                        item["supersedes"] = predecessors[-1]["id"]
                    data["items"].append(item)
                    by_id[iid] = item
                visible[_family(item)] = iid
        for item in data["items"]:
            if visible.get(_family(item)) == item["id"]:
                continue
            pid = item["origin_project_id"]
            status, origin = origins.get(pid, ("stale", None))
            if not _allowed(registry, pid, target, item["source_file"]):
                status, reason = "unauthorized", "Current registry no longer authorizes this source/destination."
            elif origin is None:
                reason = "Origin not scanned." if status == "stale" else "Approved origin unavailable or failed integrity validation."
            elif _family(item) in visible:
                status, reason = "superseded", "A different current origin release raises a fresh target review item."
            else:
                status, reason = "withdrawn", "Referral absent from the checked current approved origin release."
            _observe(item, status, reason)
        for _, origin in origins.values():
            if origin is not None:
                _stable_pointer(origin)
        if json_sha(load_registry(registry_path)) != json_sha(registry):
            raise KBError("Registry changed during discovery; retry")
    return data


def _find(data: dict, item_id: str) -> dict:
    item = next((i for i in data["items"] if i["id"] == item_id), None)
    if item is None:
        raise KBError("Unknown intake item; discover it first")
    return item


def _capture(item: dict, review: dict, project: Path) -> None:
    capture = review["capture_authorization"]
    if capture is None:
        return
    if review["decision"] != "accept" or not capture["reason"].strip():
        raise KBError("Capture authorization requires acceptance and an explicit scope reason")
    path = Path(capture["path"])
    no_symlinks(path)
    if not path.is_absolute() or path.resolve().is_relative_to(project):
        raise KBError("Capture source must be an explicit absolute path outside the target workspace")
    raw = read_stable(path, LIMIT)
    if sha(raw) != capture["sha256"]:
        raise KBError("Authorized capture bytes changed")
    if capture["mode"] == "full_file":
        if sha(raw) != item["source_file"]["sha256"]:
            raise KBError("Full-file authorization does not match the origin's original bytes")
    else:
        if sha(raw) == item["source_file"]["sha256"]:
            raise KBError("An entire original file requires explicit full_file authorization")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError as exc:
            raise KBError("Scoped export must be reviewed UTF-8 text") from exc
        if "\x00" in text or not _has_quote(text, item["referral"]["source"]["quote"]):
            raise KBError("Scoped export must preserve the exact referred quote with its qualifiers")


def decide(config: Path, registry_path: Path, origin_config: Path, review_path: Path) -> dict:
    """Record an explicit human accept/decline/defer; acceptance only proposes work."""
    review = read_json(review_path)
    contract(review, "intake-review", source=review_path)
    cfg, project, _ = load_project(config)
    registry = _registry(registry_path, cfg["project"]["id"])
    origin = _approved_release(origin_config)
    if origin is None:
        raise KBError("Approved origin unavailable")
    with _ledger(config) as data:
        item = _find(data, review["item_id"])
        if origin["project_id"] != item["origin_project_id"] or origin["run_id"] != item["origin_run_id"] \
                or origin["review_sha256"] != item["origin_review_sha256"] \
                or review["origin_review_sha256"] != item["origin_review_sha256"] \
                or item["referral"] not in origin["referrals"] \
                or item["source_file"] != _source_file(origin, item["referral"]):
            raise KBError("Intake review is stale or refers to a different approved origin")
        if not _allowed(registry, item["origin_project_id"], cfg["project"]["id"], item["source_file"]):
            raise KBError("Current registry does not authorize target disclosure")
        _human(review, item["observations"][0]["at"])
        # An exact retry neither duplicates work nor replays an old decision over
        # a later review. A new judgment needs a new human review artifact.
        if review not in item["decisions"]:
            if item["decisions"] and parse_ts(review["reviewed_at"]) < parse_ts(item["decisions"][-1]["reviewed_at"]):
                raise KBError("Intake review predates the latest decision")
            _capture(item, review, project)
            item["decisions"].append(review)
            item["capture_task"] = _task(item, review)
        _observe(item, "current", "Origin and disclosure revalidated at target review.")
        _stable_pointer(origin)
        if json_sha(load_registry(registry_path)) != json_sha(registry):
            raise KBError("Registry changed during target review; retry")
    return item


def link_target(config: Path, link_path: Path) -> dict:
    """Audit an already published target claim using its own checked evidence."""
    review = read_json(link_path)
    contract(review, "intake-link", source=link_path)
    target = _approved_release(config, review["target_run_id"])
    if target is None or review["target_review_sha256"] != target["review_sha256"]:
        raise KBError("Target release link is stale")
    _human(review, read_json(inside(target["release"], "review.json"))["reviewed_at"])
    with _ledger(config) as data:
        item = _find(data, review["item_id"])
        if review in [link["review"] for link in item["target_links"]]:
            return item
        task = item["capture_task"]
        if task is None or task["capture_authorization"] is None:
            raise KBError("Target linkage requires an accepted, explicitly authorized capture task")
        _human(review, item["decisions"][-1]["reviewed_at"])
        files = {f["evidence_id"]: f for f in target["manifest"]["files"]}
        segments = load_segment_inventory(target["release"], target["manifest"])
        segments = {s["segment_id"]: s for s in segments["segments"]} if segments else {}
        records = {r["id"]: r for r in target["records"]["records"]}
        comparisons = []
        capture = task["capture_authorization"]
        for rid in review["record_ids"]:
            if rid not in records:
                raise KBError("Target record is absent from its approved release")
            matched = []
            citations = list(records[rid]["evidence"])
            if records[rid]["investigation"] is not None:
                citations += [c for f in records[rid]["investigation"]["findings"] for c in f["evidence"]]
            for cite in citations:
                file = files[cite["evidence_id"]]
                if file["sha256"] != capture["sha256"] or not _has_quote(cite["quote"], item["referral"]["source"]["quote"]):
                    continue
                segment = segments.get(cite.get("segment_id"))
                rep = file.get("representation", {}).get("identity_sha256")
                locator = segment["original_locator"] if segment else None
                comparison = "scoped_export" if capture["mode"] == "scoped_export" else (
                    "same_representation_and_locator" if rep == item["referral"]["source"]["representation_sha256"]
                    and locator == item["source_file"]["original_locator"] else "different_representation_or_locator")
                matched.append({"record_id": rid, "evidence_id": file["evidence_id"],
                                "original_sha256": file["sha256"], "representation_sha256": rep,
                                "original_locator": locator, "comparison": comparison})
            if not matched:
                raise KBError("Target record lacks its own citation to the authorized bytes and referred quote")
            comparisons.extend(matched)
        item["target_links"].append({"review": review, "evidence_comparison": comparisons})
        _stable_pointer(target)
    return item


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("discover", help="Update the target intake ledger from explicit approved origins")
    scan.add_argument("--config", type=Path, required=True)
    scan.add_argument("--registry", type=Path, required=True)
    scan.add_argument("--origin-config", type=Path, action="append", required=True)
    decision = commands.add_parser("decide", help="Record a human-authored intake-review 1.0 JSON artifact")
    decision.add_argument("--config", type=Path, required=True)
    decision.add_argument("--registry", type=Path, required=True)
    decision.add_argument("--origin-config", type=Path, required=True)
    decision.add_argument("--review", type=Path, required=True)
    link = commands.add_parser("link", help="Record a human-authored intake-link 1.0 to an approved target release")
    link.add_argument("--config", type=Path, required=True)
    link.add_argument("--review", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "discover":
        result = discover(args.config, args.registry, args.origin_config)
    elif args.command == "decide":
        result = decide(args.config, args.registry, args.origin_config, args.review)
    else:
        result = link_target(args.config, args.review)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    run_cli(main)
