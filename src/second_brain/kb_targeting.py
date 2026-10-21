"""Explicit targeted capture and frozen policy; no relevance-derived permission."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .kb_common import (CLOCK_SKEW_SECONDS, KBError, contract, excluded, inside,
                        json_bytes, json_sha, load_project, load_source_scope, matches,
                        no_symlinks, parse_ts, read_json, read_stable, relative, sha,
                        SECRET_PATTERNS)


def validate_request(request: dict, project_id: str) -> dict:
    contract(request, "run-request")
    if request["project_id"] != project_id:
        raise KBError("Run request belongs to another project")
    for key in ("authorized_by", "permission_reason", "registry_path"):
        if not request[key].strip():
            raise KBError(f"Run request requires {key}")
    if parse_ts(request["authorized_at"]) > datetime.now(timezone.utc) + timedelta(seconds=CLOCK_SKEW_SECONDS):
        raise KBError("Run authorization timestamp is in the future")
    seen = set()
    for item in request["selection"]:
        relative(item["relative_path"])
        key = (item["source_id"], item["relative_path"])
        if key in seen:
            raise KBError("Duplicate selected source/path")
        seen.add(key)
        if request["capture_mode"] == "scoped_export":
            origin = item["provenance"]
            if not item["sha256"] or origin is None or not all(
                    origin[k].strip() for k in ("original_reference", "locator", "reviewed_by")):
                raise KBError("Scoped export requires a hash and reviewed traceable provenance")
            if parse_ts(origin["reviewed_at"]) > datetime.now(timezone.utc) + timedelta(seconds=CLOCK_SKEW_SECONDS):
                raise KBError("Export review timestamp is in the future")
    for span in request["packets"]["ranges"]:
        if (span["source_id"], span["relative_path"]) not in seen or span["start_line"] > span["end_line"]:
            raise KBError("Packet range is outside selected membership or reversed")
    return request


def selection_policy(request: dict) -> dict:
    """Exclude observed hashes and human metadata from comparable scope identity."""
    return {"version": "1.0", "purpose": request["purpose"],
            "capture_mode": request["capture_mode"],
            "membership": sorted([[i["source_id"], i["relative_path"]] for i in request["selection"]]),
            "packets": request["packets"], "records_contract": "0.6"}


def preflight(config: Path, request: dict) -> dict:
    """Inspect scope/path metadata only; never open source content or excluded originals."""
    cfg, project, locations = load_project(config)
    validate_request(request, cfg["project"]["id"])
    _, sources, roots = load_source_scope(cfg, project, locations)
    by_id = {s["id"]: s for s in sources}
    included, missing = [], []
    for item in request["selection"]:
        sid, rel = item["source_id"], item["relative_path"]
        source = by_id.get(sid)
        if source is None or not any(matches(rel, g) for g in source["include"]) or excluded(
                rel, cfg["global_exclude"] + source["exclude"] + SECRET_PATTERNS):
            raise KBError(f"Selection widens configured scope: {sid}/{rel}")
        path = inside(roots[sid], rel)
        no_symlinks(path)
        if request["capture_mode"] == "scoped_export" and path.suffix.lower() not in {".txt", ".md"}:
            raise KBError("Strict scoped capture requires reviewed UTF-8 .txt/.md exports")
        included.append({"source_id": sid, "relative_path": rel, "path": str(path)})
        if not path.is_file():
            missing.append(f"{sid}/{rel}")
    return {"included": included, "missing": missing, "unresolved_scope": [],
            "exclusions": "Every configured path outside explicit selection is excluded before content reads.",
            "retained_content": ("Whole selected files, including unrelated passages." if request["capture_mode"] == "whole_file"
                                 else "Reviewed exports only; original references are never opened."),
            "policy_sha256": json_sha(selection_policy(request))}


def load_targeted(run: Path, manifest: dict) -> dict | None:
    binding = manifest.get("targeted")
    if binding is None:
        return None
    if manifest["tool_version"] != "0.4.0":
        raise KBError("Historical capture version cannot declare targeted profile")
    raw = read_stable(inside(run, binding["request_path"]), 16 * 1024 * 1024)
    if sha(raw) != binding["request_sha256"]:
        raise KBError("Frozen run request checksum mismatch")
    request = validate_request(read_json(inside(run, binding["request_path"])), manifest["project_id"])
    if sha(json_bytes(request)) != binding["request_sha256"]:
        raise KBError("Frozen request changed while reading")
    if json_sha(selection_policy(request)) != binding["policy_sha256"] or request["purpose"] != binding["purpose"]:
        raise KBError("Targeted policy or purpose binding mismatch")
    expected = {(i["source_id"], i["relative_path"]): i for i in request["selection"]}
    for file in manifest["files"]:
        item = expected.get((file["source_id"], file["relative_path"]))
        if item is None or (item["sha256"] is not None and item["sha256"] != file["sha256"]):
            raise KBError("Captured file lies outside authorization or export hash")
    if manifest["status"] == "ready" and len(manifest["files"]) != len(expected):
        raise KBError("Ready targeted capture omits selected membership")
    if (request["context"] is None) != (binding["context_sha256"] is None):
        raise KBError("Requested context is missing or context-free request has unexpected context")
    return request


def publication_eligible(manifest: dict) -> None:
    if manifest.get("targeted", {}).get("purpose") == "analysis_only":
        raise KBError("analysis_only runs cannot prepare publication review or replace project knowledge")
