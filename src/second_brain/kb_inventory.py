#!/usr/bin/env python3
"""Freeze explicitly scoped, external UTF-8 sources into a new evidence run."""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

from .kb_common import (DOCUMENT_EXTENSIONS, ENGINE, KBError, LEGACY_DOCUMENT_EXTENSIONS,
                       SECRET_PATTERNS, SOURCE_SCOPE_SNAPSHOT, TEXT_EXTENSIONS, TOOL_VERSION,
                       ai_summary_name, canonical,
                       check_timestamp, contract, evidence_identity, excluded,
                       extraction_snapshot_paths, identifier, json_bytes, json_sha,
                       load_project, load_source_scope, matches, no_symlinks, read_json, read_stable,
                       representation_identity,
                       relative, run_cli, sha, utc_now, write_json_new, write_new,
                       CLOCK_SKEW_SECONDS, content_date_from_name, parse_ts)
from datetime import datetime, timedelta, timezone


class CaptureBudgetReached(KBError):
    """Stop the capture rather than emit an unbounded per-file error list."""


class DocumentCaptureError(KBError):
    """A document could not be captured; .code carries the extractor error code."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code


def document_policy_digest(documents: dict) -> str:
    """Stable digest of the extraction policy (limits + options) used for a run."""
    return json_sha(documents)


def temporal_entry(origin: dict | None, rel: str, path: Path) -> dict:
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
    from .kb_check import load_manifest
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


def provenance_warnings(origin: dict | None, source_type: str, rel: str) -> list[tuple[str, str]]:
    """Warnings about how far a captured file's origin and authorship are established."""
    out = []
    if origin is not None:
        missing = [k for k, v in origin["features"].items() if v in ("unknown", "not_preserved")]
        if missing or origin["limitations"]:
            out.append(("provenance_incomplete", "Review origin limitations and unpreserved features"))
    elif source_type != "repository":
        out.append(("provenance_missing", "Local file captured; upstream revision and export fidelity are not established"))
    else:
        out.append(("repository_revision_unrecorded", "File-level working-tree snapshot only; no repository commit or whole-tree consistency established"))
    authorship = (origin or {}).get("authorship")
    if authorship in ("ai_generated", "mixed"):
        out.append(("ai_generated_source", f"Provenance declares authorship '{authorship}'; "
                    "a machine summary is not primary minutes and needs human corroboration"))
    elif authorship is None and source_type != "repository" and ai_summary_name(rel):
        out.append(("ai_generated_source", "File name marks a machine-written summary; record "
                    "origin.authorship in source-provenance.json to confirm or override"))
    return out


def extract_document_snapshot(tmp: Path, source_path: Path, name: str, raw: bytes,
                              options: dict, timeout_seconds: int) -> tuple[dict, str]:
    """Extract one document via the sandboxed worker; return (metadata, derived text).

    The worker is the supported extraction boundary: a short-lived subprocess with
    a wall-clock timeout, fed bytes already captured with read_stable. Nothing here
    re-reads the live source, and no snapshot is committed on failure.
    """
    from .kb_document_extractors import Limits
    if len(raw) > Limits().max_input_bytes:
        raise DocumentCaptureError("input_budget_exceeded",
                                   "Document exceeds the extractor raw-byte budget")
    command = [sys.executable, "-P", "-m", "second_brain.kb_extract_document",
               "--worker-name", name,
               "--csv-encoding", options["csv_encoding"],
               "--csv-delimiter", options["csv_delimiter"],
               "--csv-header", options["csv_header"]]
    if options["csv_representation"] == "structured":
        command.append("--csv-structured")
    if options["allow_legacy_ppt"]:
        command.append("--allow-legacy-ppt")
    if options["soffice"]:
        command += ["--soffice", options["soffice"]]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=(os.name == "posix"))
    try:
        stdout, stderr = process.communicate(raw, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.communicate()
        raise DocumentCaptureError("extraction_timeout",
                                   f"Worker exceeded {timeout_seconds}s; no snapshot committed") from None
    if process.returncode != 0:
        text = stderr.decode("utf-8", errors="replace").strip()
        code, _, detail = "worker_failed", "", text[:500]
        for line in text.splitlines():
            if line.startswith("ERROR: "):
                parts = line[len("ERROR: "):].split(": ", 1)
                code = parts[0] if parts else code
                detail = parts[1] if len(parts) > 1 else detail
                break
        raise DocumentCaptureError(code, detail)
    try:
        output = json.loads(stdout)
        metadata = output["metadata"]
        text = output["text"]
    except (ValueError, KeyError, TypeError) as exc:
        raise DocumentCaptureError("worker_output_invalid", f"{type(exc).__name__}: {exc}") from exc
    if metadata.get("source_filename") != name or metadata.get("schema_version") != "1.0" \
            or metadata.get("status") != "extracted_needs_review" \
            or not isinstance(metadata.get("segments"), list) or not metadata["segments"]:
        raise DocumentCaptureError("invalid_metadata", "Worker metadata failed structural validation")
    return metadata, text


def capture_document_entry(tmp: Path, source_path: Path, name: str, suffix: str,
                           data: bytes, cfg: dict, sid: str, source_type: str, rel: str,
                           provenance: dict, used_keys: set, inodes: set, identities: set,
                           extraction_options: dict, timeout_seconds: int,
                           options_sha256: str) -> dict:
    """Extract, write, and integrity-check one document; return its manifest entry.

    Writes three artifacts under the run's snapshots/ and cross-checks every hash
    against the worker metadata before the entry is accepted. Raises
    DocumentCaptureError (an error issue, never a partial entry) on failure.
    """
    from .kb_document_extractors import digest as extractor_digest
    metadata, text = extract_document_snapshot(tmp, source_path, name, data,
                                               extraction_options, timeout_seconds)
    ext = metadata["source_extension"]
    if ext != suffix:
        raise DocumentCaptureError("format_mismatch", f"Worker saw {ext}, source has {suffix}")
    text_bytes = text.encode("utf-8")
    if metadata.get("source_sha256") != extractor_digest(data) \
            or metadata.get("source_bytes") != len(data) \
            or metadata.get("text_sha256") != extractor_digest(text_bytes) \
            or metadata.get("text_bytes") != len(text_bytes) \
            or metadata.get("text_line_count") != len(text.splitlines()):
        raise DocumentCaptureError("invalid_metadata", "Worker hashes disagree with captured bytes")
    content_sha = sha(data)
    representation_sha = (representation_identity("derived_text", content_sha, metadata["text_sha256"],
                                                   metadata["adapter_version"], metadata.get("parsers", {}),
                                                   options_sha256, metadata["segments"],
                                                   metadata.get("issues", [])) if TOOL_VERSION == "0.4.0" else None)
    logical, eid = evidence_identity(cfg["project"]["id"], sid, rel, content_sha, representation_sha)
    if eid in identities:
        raise KBError("Evidence identity collision")
    identities.add(eid)
    paths = extraction_snapshot_paths(eid, suffix)
    metadata["captured_by"] = "kb_inventory"
    metadata["options_sha256"] = options_sha256
    metadata_bytes = (json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=False,
                                 allow_nan=False) + "\n").encode("utf-8")
    write_new(tmp / paths["original"], data)
    write_new(tmp / paths["text"], text_bytes)
    write_new(tmp / paths["metadata"], metadata_bytes)
    write_new(tmp / (paths["metadata"] + ".sha256"),
              (extractor_digest(metadata_bytes) + "\n").encode("ascii"))
    # Re-read what was written; a snapshot that cannot round-trip is not evidence.
    if sha((tmp / paths["original"]).read_bytes()) != content_sha \
            or sha((tmp / paths["text"]).read_bytes()) != extractor_digest(text_bytes) \
            or sha((tmp / paths["metadata"]).read_bytes()) != extractor_digest(metadata_bytes):
        raise DocumentCaptureError("snapshot_write_mismatch", "Written artifacts failed verification")
    st = source_path.stat()
    inode = (st.st_dev, st.st_ino)
    warnings = []
    if inode in inodes:
        warnings.append({"code": "duplicate_physical_file",
                         "detail": "Hard-linked content is not independent evidence"})
    inodes.add(inode)
    origin = provenance.get((sid, rel))
    if origin is not None:
        used_keys.add((sid, rel))
    for code, detail in provenance_warnings(origin, source_type, rel):
        warnings.append({"code": code, "detail": detail})
    warnings.extend(metadata.get("issues", []))
    entry = {"evidence_id": eid, "logical_id": logical,
             "source_id": sid, "source_type": source_type, "relative_path": rel,
             "sha256": content_sha, "bytes": len(data),
             "line_count": metadata["text_line_count"], "encoding": "utf-8",
             "snapshot_path": paths["text"], "provenance": origin,
             "temporal": temporal_entry(origin, rel, source_path),
             "document": {
                 "status": metadata["status"], "media_type": metadata["media_type"],
                 "original_sha256": content_sha, "original_bytes": len(data),
                 "original_snapshot_path": paths["original"],
                 "text_snapshot_path": paths["text"],
                 "text_sha256": metadata["text_sha256"], "text_bytes": len(text_bytes),
                 "text_line_count": metadata["text_line_count"],
                 "metadata_snapshot_path": paths["metadata"],
                 "metadata_sha256": extractor_digest(metadata_bytes),
                 "adapter_version": metadata["adapter_version"],
                 "parsers": metadata.get("parsers", {}),
                 "segment_count": len(metadata["segments"]),
                 "issues": list(metadata.get("issues", [])), "options_sha256": options_sha256}}
    if representation_sha is not None:
        entry["representation"] = {"version": "1", "kind": "derived_text",
                                   "text_sha256": metadata["text_sha256"],
                                   "identity_sha256": representation_sha}
    return {"entry": entry, "_warnings": warnings}


def inventory(config_path: Path, run_id: str, baseline: Path | None = None,
              max_file_bytes: int = 2_000_000, max_total_bytes: int = 50_000_000,
              max_files: int = 2000, documents: bool = False, allow_legacy_ppt: bool = False,
              soffice: str | None = None, document_timeout_seconds: int = 90,
              csv_encoding: str = "utf-8-sig", csv_delimiter: str = ",",
              csv_representation: str = "raw", csv_header: str = "none",
              request: dict | None = None, context_bundle: dict | None = None) -> tuple[Path, dict]:
    identifier(run_id, "run id")
    cfg, project, locations = load_project(config_path)
    source_scope, active_sources, source_roots = load_source_scope(cfg, project, locations)
    selected_items = None
    if request is not None:
        from .kb_targeting import preflight, selection_policy
        scope_report = preflight(config_path, request)
        if scope_report["missing"]:
            raise KBError(f"Selected inputs missing: {scope_report['missing']}")
        if (request["context"] is None) != (context_bundle is None):
            raise KBError("Requested context must be prepared explicitly before capture")
        selected_items = {(i["source_id"], i["relative_path"]): i for i in request["selection"]}
    elif context_bundle is not None:
        raise KBError("Context capture requires a targeted request")
    if min(max_file_bytes, max_total_bytes, max_files) <= 0:
        raise KBError("All inventory limits must be positive")
    if document_timeout_seconds < 1:
        raise KBError("Document extraction timeout must be positive")
    if (allow_legacy_ppt or soffice) and not documents:
        raise KBError("--allow-legacy-ppt and --soffice require --documents")
    if csv_representation not in {"raw", "structured"} or csv_header not in {"none", "first-row"}:
        raise KBError("Invalid CSV representation or header choice")
    if csv_representation == "structured" and not documents:
        raise KBError("Structured CSV requires --documents")
    if csv_header != "none" and csv_representation != "structured":
        raise KBError("A declared CSV header requires structured CSV")
    run = locations["runs"] / run_id
    no_symlinks(run)
    if run.exists():
        raise KBError(f"Run already exists; choose a new run id: {run}")
    previous = None
    if baseline:
        from .kb_check import load_manifest
        previous = load_manifest(baseline)
        if previous["project_id"] != cfg["project"]["id"]:
            raise KBError("Baseline belongs to another project")
        if previous["status"] != "ready":
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
    provenance_path = project / "config" / "source-provenance.json"
    provenance = {}
    if provenance_path.exists():
        no_symlinks(provenance_path)
        p = read_json(provenance_path)
        contract(p, "source-provenance")
        for item in p["entries"]:
            relative(item["relative_path"])
            check_timestamp(item["origin"]["captured_at"])
            key = (item["source_id"], item["relative_path"])
            if key in provenance:
                raise KBError(f"Duplicate provenance entry: {key}")
            provenance[key] = item["origin"]
    limits = dict(max_file_bytes=max_file_bytes, max_total_bytes=max_total_bytes, max_files=max_files)
    capture_policy = {"version": "1", "supported_extensions": sorted(TEXT_EXTENSIONS),
                      "secret_patterns": list(SECRET_PATTERNS)}
    scope = {"project_id": cfg["project"]["id"], "sources": active_sources,
             "resolved_roots": {k: str(v) for k, v in source_roots.items()},
             "global_exclude": cfg["global_exclude"],
             "secret_patterns": capture_policy["secret_patterns"],
             "supported_extensions": capture_policy["supported_extensions"], "limits": limits,
             "tool_version": TOOL_VERSION, "capture_policy_version": capture_policy["version"]}
    if source_scope is not None:
        scope["source_scope"] = source_scope
    if request is not None:
        scope["targeted_policy"] = selection_policy(request)
    documents_policy = None
    if documents:
        # Document extraction settings join the frozen scope only when enabled.
        from .kb_document_extractors import Limits, VERSION
        documents_policy = {
            "enabled": True, "adapter_version": VERSION,
            "extensions": sorted(DOCUMENT_EXTENSIONS | ({".csv"} if csv_representation == "structured" else set())),
            "allow_legacy_ppt": allow_legacy_ppt, "soffice": soffice,
            "csv_encoding": csv_encoding, "csv_delimiter": csv_delimiter,
            "csv_representation": csv_representation, "csv_header": csv_header,
            "timeout_seconds": document_timeout_seconds,
            "adapter_limits": asdict(Limits()),
        }
        scope["documents"] = documents_policy
        options_sha256 = document_policy_digest(documents_policy)
        extraction_options = {"csv_encoding": csv_encoding, "csv_delimiter": csv_delimiter,
                              "csv_representation": csv_representation, "csv_header": csv_header,
                              "allow_legacy_ppt": allow_legacy_ppt, "soffice": soffice}
    manifest = {"schema_version": "0.1", "tool_version": TOOL_VERSION,
                "project_id": cfg["project"]["id"], "run_id": run_id, "sequence": sequence,
                "created_at": started.isoformat(timespec="seconds"),
                "config_sha256": json_sha(cfg), "scope_sha256": json_sha(scope),
                "config_snapshot": "project.snapshot.json", "status": "ready",
                "capture_policy": capture_policy, "limits": limits, "sources": [], "files": [], "issues": [],
                "delta": {"baseline_run_id": None, "baseline_created_at": None, "baseline_sequence": None,
                          "compatible": None, "added": [], "modified": [], "removed": [], "unchanged": [],
                          "renamed": []}}
    if request is not None:
        manifest["targeted"] = {"version": "1.0", "config_path": str(config_path.resolve()), "request_path": "run-request.snapshot.json",
                               "request_sha256": sha(json_bytes(request)),
                               "policy_sha256": json_sha(selection_policy(request)),
                               "purpose": request["purpose"],
                               "context_sha256": sha(json_bytes(context_bundle)) if context_bundle is not None else None}
    if documents_policy is not None:
        # Recorded in the manifest so kb_check can rebuild the scope digest from
        # the frozen manifest alone; text-only runs omit the key entirely.
        manifest["documents"] = documents_policy
    if source_scope is not None:
        manifest["source_scope"] = {"path": SOURCE_SCOPE_SNAPSHOT,
                                    "sha256": sha(json_bytes(source_scope))}
    locations["runs"].mkdir(parents=True, exist_ok=True)
    tmp = locations["runs"] / f".{run_id}.{uuid.uuid4().hex}.tmp"
    tmp.mkdir()
    total = 0
    budget_exhausted = False
    used_keys = set()
    identities = set()
    inodes = set()

    def issue(severity: str, code: str, source_id: str | None, path: str | None, detail: str) -> None:
        manifest["issues"].append(dict(severity=severity, code=code, source_id=source_id,
                                       path=path, detail=detail))

    try:
        write_json_new(tmp / "project.snapshot.json", cfg)
        if source_scope is not None:
            write_json_new(tmp / SOURCE_SCOPE_SNAPSHOT, source_scope)
        if request is not None:
            write_json_new(tmp / "run-request.snapshot.json", request)
        if context_bundle is not None:
            contract(context_bundle, "run-context")
            write_json_new(tmp / "work/context.json", context_bundle)
        for source in sorted(active_sources, key=lambda s: s["id"]):
            sid = source["id"]
            root = source_roots[sid]
            summary = {"id": sid, "type": source["type"], "root": str(root),
                       "eligible_count": 0, "excluded_entries": 0}
            manifest["sources"].append(summary)
            patterns = cfg["global_exclude"] + source["exclude"] + capture_policy["secret_patterns"]
            if budget_exhausted:
                issue("error", "scope_not_scanned_budget", sid, None, "Capture stopped at its budget; this source was not scanned")
                continue
            if selected_items is not None and not any(source_id == sid for source_id, _ in selected_items):
                issue("warning", "unselected_source_scope", sid, None, "Source excluded by explicit targeted membership; not scanned")
                continue
            if not root.is_dir():
                issue("error", "source_unavailable", sid, None, "Source directory does not exist or is inaccessible")
                continue
            def walk_error(exc: OSError) -> None:
                issue("error", "directory_unreadable", sid, None, str(exc))
            if selected_items is None:
                walk = os.walk(root, topdown=True, followlinks=False, onerror=walk_error)
            else:
                # Only explicit members: excluded mixed originals are never opened or walked.
                walk = [(str((root / rel).parent), [], [(root / rel).name])
                        for source_id, rel in sorted(selected_items) if source_id == sid]
            for directory, dirs, files in walk:
                if budget_exhausted:
                    break
                base = Path(directory)
                keep = []
                for name in sorted(dirs):
                    p = base / name
                    rel = p.relative_to(root).as_posix()
                    if excluded(rel, patterns, directory=True):
                        summary["excluded_entries"] += 1
                    elif p.is_symlink():
                        issue("error", "symlink_skipped", sid, rel, "Narrow the scope or remove the symlink from the source snapshot")
                    else:
                        keep.append(name)
                dirs[:] = keep
                for name in sorted(files):
                    p = base / name
                    rel = p.relative_to(root).as_posix()
                    if excluded(rel, patterns) or not any(matches(rel, inc) for inc in source["include"]):
                        summary["excluded_entries"] += 1
                        continue
                    try:
                        relative(rel)
                        no_symlinks(p)
                        suffix = p.suffix.lower()
                        if suffix not in capture_policy["supported_extensions"] and not (documents and suffix in DOCUMENT_EXTENSIONS):
                            raise KBError("Unsupported extension: supply a reviewed UTF-8 export, enable "
                                          "--documents, or explicitly exclude this file")
                        if len(manifest["files"]) >= max_files:
                            raise CaptureBudgetReached("Maximum file count reached; narrow the source scope")
                        data = read_stable(p, max_file_bytes)
                        if selected_items is not None:
                            expected_hash = selected_items[(sid, rel)]["sha256"]
                            if expected_hash is not None and sha(data) != expected_hash:
                                raise KBError("Selected bytes differ from authorized export hash")
                        if total + len(data) > max_total_bytes:
                            raise CaptureBudgetReached("Maximum total byte budget reached; narrow the source scope")
                        if suffix in LEGACY_DOCUMENT_EXTENSIONS and not allow_legacy_ppt:
                            raise DocumentCaptureError(
                                "legacy_ppt_not_enabled",
                                "Legacy .ppt requires --allow-legacy-ppt and a local approved LibreOffice "
                                "conversion; export a reviewed .pptx instead")
                        if documents_policy is not None and suffix in documents_policy["extensions"]:
                            entry = capture_document_entry(
                                tmp, p, name, suffix, data, cfg, sid, source["type"], rel,
                                provenance, used_keys, inodes, identities, extraction_options,
                                document_timeout_seconds, options_sha256)
                            for item in entry.pop("_warnings"):
                                issue("warning", item["code"], sid, rel, item["detail"])
                            for severity, code, detail in provenance_time_issues(
                                    entry["entry"]["provenance"], entry["entry"]["sha256"], started):
                                issue(severity, code, sid, rel, detail)
                            manifest["files"].append(entry["entry"])
                            total += len(data)
                            summary["eligible_count"] += 1
                            continue
                        if b"\x00" in data:
                            raise KBError("NUL bytes detected; input is not supported text")
                        try:
                            text = data.decode("utf-8-sig")
                        except UnicodeDecodeError as exc:
                            raise KBError("Input is not UTF-8; export it explicitly rather than silently replacing characters") from exc
                        if not text.strip():
                            issue("warning", "empty_file", sid, rel, "No meaningful text; cannot support a cited record")
                        content_sha = sha(data)
                        logical, eid = evidence_identity(cfg["project"]["id"], sid, rel, content_sha)
                        if eid in identities:
                            raise KBError("Evidence identity collision")
                        identities.add(eid)
                        st = p.stat()
                        inode = (st.st_dev, st.st_ino)
                        if inode in inodes:
                            issue("warning", "duplicate_physical_file", sid, rel, "Hard-linked content is not independent evidence")
                        inodes.add(inode)
                        origin = provenance.get((sid, rel))
                        if origin is not None:
                            used_keys.add((sid, rel))
                        for code, detail in provenance_warnings(origin, source["type"], rel):
                            issue("warning", code, sid, rel, detail)
                        for severity, code, detail in provenance_time_issues(origin, content_sha, started):
                            issue(severity, code, sid, rel, detail)
                        snapshot = f"snapshots/{eid}.txt"
                        write_new(tmp / snapshot, data)
                        file_entry = {"evidence_id": eid, "logical_id": logical,
                            "source_id": sid, "source_type": source["type"], "relative_path": rel,
                            "sha256": content_sha, "bytes": len(data), "line_count": len(text.splitlines()),
                            "encoding": "utf-8", "snapshot_path": snapshot, "provenance": origin,
                            "temporal": temporal_entry(origin, rel, p)}
                        if TOOL_VERSION == "0.4.0":
                            file_entry["representation"] = {"version": "1", "kind": "source_text",
                                                            "text_sha256": content_sha,
                                                            "identity_sha256": representation_identity("source_text", content_sha, content_sha)}
                        manifest["files"].append(file_entry)
                        total += len(data)
                        summary["eligible_count"] += 1
                    except (KBError, OSError) as exc:
                        issue("error", "file_not_captured", sid, rel, str(exc))
                        if isinstance(exc, CaptureBudgetReached):
                            budget_exhausted = True
                            break
            if summary["eligible_count"] == 0:
                # An existing source may be intentionally empty or fully filtered.
                # Any actual scan/capture failures remain separate blocking errors.
                issue("warning", "empty_source_scope", sid, None,
                      "No files captured in this source scope; it may be empty or fully filtered. "
                      "Review include/exclude patterns and any separate capture errors")
        # A usable run needs evidence somewhere, not necessarily in every source.
        # Set this before computing the delta so an empty run is not comparable.
        if not manifest["files"]:
            issue("error", "empty_inventory", None, None,
                  "No files captured across any source; add eligible input before continuing")
        for sid, rel in sorted(set(provenance) - used_keys):
            issue("warning", "provenance_entry_unused", sid, rel, "Provenance entry does not match a captured input; check stale metadata")
        manifest["files"].sort(key=lambda f: (f["source_id"], f["relative_path"]))
        delta = manifest["delta"]
        now = {f["logical_id"]: f for f in manifest["files"]}
        if previous:
            delta["baseline_run_id"] = previous["run_id"]
            delta["baseline_created_at"] = previous["created_at"]
            delta["baseline_sequence"] = previous.get("sequence")
            newer = sorted(o["run_id"] for o in others if o["status"] == "ready"
                           and (o.get("sequence", 0), o["created_at"]) > (previous.get("sequence", 0), previous["created_at"]))
            if newer:
                issue("warning", "baseline_not_latest", None, None,
                      f"Newer ready runs exist after the baseline ({', '.join(newer)}); this delta skips them")
            incomplete = any(i["severity"] == "error" for i in manifest["issues"])
            delta["compatible"] = not incomplete and previous["scope_sha256"] == manifest["scope_sha256"]
            if delta["compatible"]:
                old = {f["logical_id"]: f for f in previous["files"]}
                delta["added"] = sorted(set(now) - set(old))
                delta["removed"] = sorted(set(old) - set(now))
                def text_sha(f):  # what citations actually quote
                    return f["document"]["text_sha256"] if "document" in f else f["sha256"]
                for k in sorted(set(old) & set(now)):
                    changed = (now[k]["sha256"], text_sha(now[k]),
                               now[k].get("representation", {}).get("identity_sha256"), canonical(now[k]["provenance"])) != \
                              (old[k]["sha256"], text_sha(old[k]),
                               old[k].get("representation", {}).get("identity_sha256"), canonical(old[k]["provenance"]))
                    delta["modified" if changed else "unchanged"].append(k)
                    if now[k]["sha256"] != old[k]["sha256"] and now[k]["provenance"] is not None \
                            and canonical(now[k]["provenance"]) == canonical(old[k]["provenance"]):
                        issue("warning", "provenance_not_updated", now[k]["source_id"], now[k]["relative_path"],
                              "Bytes changed but provenance (captured_at/revision) did not; it may describe the old export")
                by_hash = {}
                for k in delta["removed"]:
                    by_hash.setdefault((old[k]["source_id"], old[k]["sha256"]), []).append(k)
                for k in delta["added"]:
                    cands = by_hash.get((now[k]["source_id"], now[k]["sha256"]), [])
                    if len(cands) == 1 and (text_sha(old[cands[0]]),
                                            old[cands[0]].get("representation", {}).get("identity_sha256")) == \
                                           (text_sha(now[k]), now[k].get("representation", {}).get("identity_sha256")):
                        delta["renamed"].append({"from": cands.pop(), "to": k})
            else:
                issue("warning", "inventory_incomplete_delta_unavailable" if incomplete else "scope_changed", None, None,
                      "Delta is incomparable; incomplete capture or changed scope must not be interpreted as deletions")
        else:
            delta["added"] = sorted(now)
        if any(i["severity"] == "error" for i in manifest["issues"]):
            manifest["status"] = "blocked"
        if TOOL_VERSION == "0.4.0":
            from .kb_segments import build_segment_inventory
            segment_inventory = build_segment_inventory(tmp, manifest)
            contract(segment_inventory, "segments")
            manifest["segment_inventory"] = {"path": "segments.snapshot.json",
                                             "sha256": sha(json_bytes(segment_inventory)),
                                             "count": len(segment_inventory["segments"])}
            write_json_new(tmp / "segments.snapshot.json", segment_inventory)
        contract(manifest, "manifest")
        write_json_new(tmp / "manifest.json", manifest)
        write_new(tmp / "manifest.sha256", (sha((tmp / "manifest.json").read_bytes()) + "\n").encode())
        (tmp / "proposals").mkdir()
        (tmp / "packets").mkdir()
        # Assistant helper scripts and intermediate outputs; copied into releases as audit material.
        (tmp / "work").mkdir(exist_ok=True)
        if run.exists():
            raise KBError(f"Run was created concurrently; refusing replacement: {run}")
        tmp.rename(run)
        return run, manifest
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", type=Path, required=True, help="<project-root>/config/project.json")
    p.add_argument("--request", type=Path, help="Explicit run-request 1.0; context requests use run create")
    p.add_argument("--dry-run", action="store_true", help="With --request: scope preflight without source reads")
    p.add_argument("--run-id", default=None)
    p.add_argument("--baseline", type=Path, help="Previous ready run directory")
    p.add_argument("--max-file-bytes", type=int, default=2_000_000)
    p.add_argument("--max-total-bytes", type=int, default=50_000_000)
    p.add_argument("--max-files", type=int, default=2000)
    p.add_argument("--documents", action="store_true",
                   help="Capture .docx/.pdf/.xlsx/.pptx/.html/.eml/.svg/.png (and .ppt with --allow-legacy-ppt) via the "
                        "document extractors; their parsers are dependencies in pyproject.toml")
    p.add_argument("--allow-legacy-ppt", action="store_true",
                   help="With --documents: opt in to local LibreOffice conversion for legacy .ppt")
    p.add_argument("--soffice", help="With --documents: path to the approved soffice executable")
    p.add_argument("--document-timeout", type=int, default=90,
                   help="Per-document worker wall-clock timeout in seconds")
    p.add_argument("--csv-encoding", default="utf-8-sig",
                   help="With structured CSV: explicit source encoding (default utf-8-sig)")
    p.add_argument("--csv-delimiter", default=",",
                   help="With structured CSV: one delimiter character (default comma)")
    p.add_argument("--csv-representation", choices=("raw", "structured"), default="raw",
                   help="With --documents: preserve CSV as raw text (default) or capture structured rows")
    p.add_argument("--csv-header", choices=("none", "first-row"), default="none",
                   help="With structured CSV: declare the first record as column labels; never inferred")
    a = p.parse_args()
    request = read_json(a.request) if a.request else None
    if a.dry_run:
        if request is None:
            raise KBError("Dry-run requires an explicit run request")
        from .kb_targeting import preflight
        print(json.dumps(preflight(a.project, request), indent=2))
        return 0
    run_id = a.run_id or "run-" + utc_now().replace("-", "").replace(":", "").replace("+0000", "z").lower() + "-" + uuid.uuid4().hex[:6]
    run, m = inventory(a.project, run_id, a.baseline, a.max_file_bytes, a.max_total_bytes, a.max_files,
                       documents=a.documents, allow_legacy_ppt=a.allow_legacy_ppt, soffice=a.soffice,
                       document_timeout_seconds=a.document_timeout,
                       csv_encoding=a.csv_encoding, csv_delimiter=a.csv_delimiter,
                       csv_representation=a.csv_representation, csv_header=a.csv_header, request=request)
    documents_count = sum(1 for f in m["files"] if "document" in f)
    print(f"{m['status'].upper()}: {run}\nCaptured {len(m['files'])} files "
          f"({documents_count} documents); {len(m['issues'])} reported issues.")
    return 0 if m["status"] == "ready" else 2


if __name__ == "__main__":
    run_cli(main)
