#!/usr/bin/env python3
"""Build, verify, or query an explicitly authorized derived approved-release index."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .kb_common import (CLOCK_SKEW_SECONDS, ENGINE, KBError, atomic_json, contract,
                       identifier, inside, json_bytes, json_sha, load_project,
                       load_source_scope, no_symlinks, parse_ts, read_json,
                       read_stable, run_cli, sha, utc_now, write_json_new)
from .kb_mentions import load_registry
from .kb_referrals import load_approved_release, verify_approved_release

LIMIT = 16 * 1024 * 1024
MAX_RELEASES = 1000
MAX_ENTRIES = 10000


def _access(path: Path) -> dict:
    no_symlinks(path)
    access = read_json(path)
    contract(access, "index-access", source=path)
    if not access["authorized_by"].strip() or not access["reason"].strip() \
            or parse_ts(access["authorized_at"]) > datetime.now(timezone.utc) + timedelta(seconds=CLOCK_SKEW_SECONDS):
        raise KBError("Index access requires a named operator, reason, and non-future timestamp")
    output = Path(access["output_path"])
    no_symlinks(output)
    if not output.is_absolute() or str(output) != str(output.resolve()) or output.suffix != ".json":
        raise KBError("Index output must be an explicit normalized absolute .json path")
    return access


def _context(access_path: Path, registry_path: Path, configs: list[Path]) -> dict:
    access = _access(access_path)
    registry = load_registry(registry_path)
    projects = {p["id"]: p for p in registry["projects"]}
    selected = set(access["project_ids"])
    if not selected.issubset(projects) or any(projects[pid]["information_domain"] != access["information_domain"]
                                            for pid in selected):
        raise KBError("Index access names an unregistered or different-domain project")
    output = Path(access["output_path"])
    if output.is_relative_to(ENGINE.resolve()) or output in {access_path.resolve(), registry_path.resolve()}:
        raise KBError("Index output must be outside the engine and policy/registry inputs")
    configured = {}
    for config in configs:
        cfg, root, locations = load_project(config)
        pid = cfg["project"]["id"]
        if pid not in selected or pid in configured:
            raise KBError("Project configurations must match the explicit access set without duplicates")
        # These live paths protect input locations; frozen release content is
        # verified independently and is never recaptured from a live source.
        source_scope, _, source_roots = load_source_scope(cfg, root, locations)
        protected = [root, *source_roots.values()]
        if any(output.is_relative_to(p) for p in protected):
            raise KBError("Index output overlaps a project workspace or source root")
        configured[pid] = {"config": config.resolve(), "cfg": cfg, "locations": locations,
                           "source_scope_sha256": json_sha(source_scope) if source_scope else None,
                           "registry_project": projects[pid]}
    if set(configured) != selected:
        raise KBError("Supply exactly one project configuration for every authorized project")
    return {"access": access, "registry": registry, "access_path": access_path,
            "registry_path": registry_path, "output": output, "configured": configured}


def _history(project: dict) -> tuple[bytes, dict]:
    approved = project["locations"]["approved"]
    lock = inside(approved, ".publish.lock")
    if lock.exists():
        raise KBError("Publication is in progress; retry indexing after it completes")
    raw = read_stable(inside(approved, "HISTORY.jsonl"), LIMIT)
    entries = {}
    try:
        for line in raw.decode("utf-8").splitlines():
            if not line:
                continue
            entry = json.loads(line)
            if not isinstance(entry, dict) or not isinstance(entry.get("run_id"), str):
                raise KBError("Malformed publication history entry")
            run_id = identifier(entry["run_id"], "published run id")
            if run_id in entries:
                raise KBError("Duplicate release in publication history")
            entries[run_id] = entry
    except (ValueError, UnicodeError) as exc:
        raise KBError("Malformed publication history") from exc
    return raw, entries


def _publication_trace(release: dict, history: dict) -> None:
    entry = history[release["run_id"]]
    review = read_json(inside(release["release"], "review.json"))
    manifest = release["manifest"]
    expected = {"reviewer": review["reviewer"], "reviewed_at": review["reviewed_at"],
                "captured_at": manifest["created_at"], "sequence": manifest.get("sequence"),
                "previous_release_id": review["previous_release_id"], "rollback_reason": review.get("rollback_reason")}
    if any(entry.get(key) != value for key, value in expected.items()):
        raise KBError("Approved release differs from its publication trace")


def _evidence_links(release: dict, record: dict) -> list[dict]:
    links = []
    groups = [("record", None, record["evidence"])]
    if record["investigation"] is not None:
        groups += [("finding", i, f["evidence"]) for i, f in enumerate(record["investigation"]["findings"])]
    for role, finding, citations in groups:
        for i, cite in enumerate(citations):
            file = release["files"][cite["evidence_id"]]
            segment = release["segments"].get(cite.get("segment_id"))
            document = file.get("document")
            links.append({"role": role, "finding_index": finding, "citation_index": i,
                          "evidence_id": file["evidence_id"], "segment_id": cite.get("segment_id"),
                          "source_id": file["source_id"], "source_type": file["source_type"],
                          "relative_path": file["relative_path"],
                          "snapshot_path": str(inside(release["release"], file["snapshot_path"])),
                          "original_snapshot_path": str(inside(release["release"], document["original_snapshot_path"])) if document else None,
                          "metadata_path": str(inside(release["release"], document["metadata_snapshot_path"])) if document else None,
                          "original_sha256": file["sha256"],
                          "representation_sha256": file.get("representation", {}).get("identity_sha256"),
                          "original_locator": segment["original_locator"] if segment else None,
                          "start_line": cite["start_line"], "end_line": cite["end_line"]})
    return links


def _generation(data: dict) -> str:
    return "IDX-" + json_sha({k: v for k, v in data.items() if k != "generation_id"})[:24]


def _validate_index(data: dict, path: Path | None = None) -> None:
    contract(data, "global-index", source=path)
    if len(data["releases"]) > MAX_RELEASES or len(data["entries"]) > MAX_ENTRIES:
        raise KBError("Index exceeds 1,000 releases or 10,000 entries; narrow the access set")
    if data["generation_id"] != _generation(data):
        raise KBError("Index digest mismatch; rebuild the derived artifact")
    projects = {p["project_id"] for p in data["projects"]}
    releases = {(r["project_id"], r["run_id"]): r["visibility"] for r in data["releases"]}
    keys = set()
    if len(projects) != len(data["projects"]) or len(releases) != len(data["releases"]):
        raise KBError("Duplicate project or release selection")
    for entry in data["entries"]:
        key = f"{entry['project_id']}:{entry['run_id']}:{entry['record_id']}"
        if entry["key"] != key or key in keys or entry["project_id"] not in projects \
                or releases.get((entry["project_id"], entry["run_id"])) != entry["visibility"] \
                or entry["record"].get("id") != entry["record_id"]:
            raise KBError("Invalid or duplicate qualified index identity")
        keys.add(key)


def _unchanged(context: dict, releases: list[dict], histories: dict) -> None:
    if json_sha(_access(context["access_path"])) != json_sha(context["access"]) \
            or json_sha(load_registry(context["registry_path"])) != json_sha(context["registry"]):
        raise KBError("Index access or registry changed during operation; retry")
    for pid, project in context["configured"].items():
        cfg, root, locations = load_project(project["config"])
        source_scope, _, _ = load_source_scope(cfg, root, locations)
        scope_hash = json_sha(source_scope) if source_scope else None
        if json_sha(cfg) != json_sha(project["cfg"]) or scope_hash != project["source_scope_sha256"] \
                or sha(_history(project)[0]) != histories[pid]:
            raise KBError("Project configuration, source scope, or publication history changed during indexing; retry")
    for release in releases:
        verify_approved_release(release)


def _snapshot(context: dict, include_history: bool) -> dict:
    data = {"schema_version": "1.0", "artifact_type": "approved_release_index",
            "information_domain": context["access"]["information_domain"],
            "access_sha256": json_sha(context["access"]), "registry_sha256": json_sha(context["registry"]),
            "include_history": include_history, "projects": [], "releases": [], "entries": []}
    verified, histories = [], {}
    for pid, project in sorted(context["configured"].items()):
        history_raw, history = _history(project)
        current = load_approved_release(project["config"])
        if current is None:
            raise KBError(f"No current approved release for authorized project {pid}")
        current_id = current["run_id"]
        if current_id not in history:
            raise KBError("Current release is absent from the selected publication history")
        histories[pid] = sha(history_raw)
        registration = project["registry_project"]
        data["projects"].append({"project_id": pid, "name": registration["name"],
                                 "information_domain": data["information_domain"],
                                 "ownership_references": registration["owns_paths"],
                                 "config_path": str(project["config"]), "config_sha256": json_sha(project["cfg"]),
                                 "source_scope_sha256": project["source_scope_sha256"],
                                 "current_run_id": current_id, "current_pointer_sha256": sha(current["pointer_bytes"]),
                                 "history_sha256": histories[pid]})
        run_ids = sorted(history) if include_history else [current_id]
        if len(verified) + len(run_ids) > MAX_RELEASES:
            raise KBError("Index exceeds 1,000 releases; narrow the access set")
        for run_id in run_ids:
            release = current if run_id == current_id else load_approved_release(project["config"], run_id)
            _publication_trace(release, history)
            verified.append(release)
            visibility = "current" if run_id == current_id else "historical"
            binding = release["bindings"]
            data["releases"].append({"project_id": pid, "run_id": run_id, "visibility": visibility,
                                     "release_path": str(release["release"]),
                                     "manifest_sha256": binding["manifest.json"], "records_sha256": binding["records.json"],
                                     "review_sha256": binding["review.json"], "review_report_sha256": binding["review-report.md"],
                                     "work_sha256": release["work_sha256"]})
            for index, record in enumerate(release["records"]["records"]):
                data["entries"].append({"key": f"{pid}:{run_id}:{record['id']}", "project_id": pid,
                                        "run_id": run_id, "record_id": record["id"], "visibility": visibility,
                                        "review_status": "human_reviewed_snapshot",
                                        "record_schema_version": release["records"]["schema_version"],
                                        "record_path": str(inside(release["release"], "records.json")),
                                        "record_index": index, "record": record,
                                        "evidence_links": _evidence_links(release, record)})
                if len(data["entries"]) > MAX_ENTRIES:
                    raise KBError("Index exceeds 10,000 entries; narrow the access set")
    data["entries"].sort(key=lambda entry: entry["key"])
    data["generation_id"] = _generation(data)
    _validate_index(data)
    if len(json_bytes(data)) > LIMIT:
        raise KBError("Index exceeds 16 MiB; narrow the access set")
    _unchanged(context, verified, histories)
    return data


def build_index(access_path: Path, registry_path: Path, configs: list[Path], include_history: bool = False) -> dict:
    """Replace only an explicitly authorized external derived index, atomically."""
    context = _context(access_path, registry_path, configs)
    output = context["output"]
    lock = output.with_name(f".{output.name}.lock")
    write_json_new(lock, {"created_at": utc_now()})
    try:
        before = read_stable(output, LIMIT) if output.exists() else None
        if before is not None:
            # Rebuild may repair an edited index, but must not overwrite an
            # unrelated file simply because its path was supplied.
            contract(read_json(output), "global-index", source=output)
        data = _snapshot(context, include_history)
        if (read_stable(output, LIMIT) if output.exists() else None) != before:
            raise KBError("Index changed during rebuild; retry")
        if before != json_bytes(data):
            atomic_json(output, data)
    finally:
        lock.unlink(missing_ok=True)
    return data


def _verified(access_path: Path, registry_path: Path, configs: list[Path]) -> dict:
    context = _context(access_path, registry_path, configs)
    output = context["output"]
    if output.with_name(f".{output.name}.lock").exists():
        raise KBError("Index rebuild is in progress; retry")
    before = read_stable(output, LIMIT)
    data = read_json(output)
    _validate_index(data, output)
    if data["access_sha256"] != json_sha(context["access"]) or data["registry_sha256"] != json_sha(context["registry"]):
        raise KBError("Index access or registry is stale; rebuild before querying")
    expected = _snapshot(context, data["include_history"])
    if data != expected or read_stable(output, LIMIT) != before:
        raise KBError("Index is stale or differs from approved inputs; rebuild before querying")
    return expected


def check_index(access_path: Path, registry_path: Path, configs: list[Path]) -> dict:
    data = _verified(access_path, registry_path, configs)
    return {"status": "passed", "generation_id": data["generation_id"],
            "project_count": len(data["projects"]), "release_count": len(data["releases"]),
            "entry_count": len(data["entries"]), "include_history": data["include_history"]}


def query_verified(data: dict, text: str = "", view: str = "current", project_id: str | None = None,
                   kind: str | None = None, epistemic_status: str | None = None,
                   limit: int = 50, expand_relations: int = 0, _all_results: bool = False) -> dict:
    """Rank against one already verified generation; no cached access boundary."""
    if view not in {"current", "historical", "all"} or not 1 <= limit <= 1000 \
            or kind not in {None, "requirement", "decision", "uncertainty", "investigation"} \
            or epistemic_status not in {None, "observed", "interpretation", "proposal", "unresolved"} \
            or not 0 <= expand_relations <= 2:
        raise KBError("Query view, filters, result limit or relationship budget is invalid")
    if view == "historical" and not data["include_history"]:
        raise KBError("Build with --include-history before historical lookup")
    projects = {p["project_id"]: p for p in data["projects"]}
    if project_id is not None and project_id not in projects:
        raise KBError("Query project is outside the explicit access set")
    releases = {(r["project_id"], r["run_id"]): r for r in data["releases"]}
    terms = sorted(set(text.casefold().split()))
    def eligible(entry):
        r = entry["record"]
        return ((view == "all" or entry["visibility"] == view) and
                (not project_id or entry["project_id"] == project_id) and
                (not kind or r["kind"] == kind) and
                (not epistemic_status or r["epistemic_status"] == epistemic_status))
    pool = {e["key"]:e for e in data["entries"] if eligible(e)}
    ranked = {}
    for key, entry in pool.items():
        r = entry["record"]
        fields = {"title":(r["title"].casefold(),4), "aliases":(" ".join(r.get("aliases",[])).casefold(),5),
                  "statement":(r["statement"].casefold(),2), "questions":(" ".join(r["open_questions"]).casefold(),1),
                  "events":(" ".join(e["statement"] for e in r.get("events",[])).casefold(),1)}
        reasons, score = [], 0
        for term in terms:
            hits = [name for name,(content,weight) in fields.items() if term in content]
            if not hits:
                break
            points = sum(fields[name][1] for name in hits)
            reasons.append({"term":term,"fields":hits,"points":points})
            score += points
        else:
            ranked[key] = {"entry":entry,"ranking_score":score,"ranking_reasons":reasons,"relationship_hops":0}
    frontier = sorted(ranked)
    for hop in range(1,expand_relations+1):
        following = []
        for key in frontier:
            entry = pool[key]
            neighbors = [f"{entry['project_id']}:{entry['run_id']}:{edge['target']}" for edge in entry["record"]["relations"]]
            neighbors += [f"{a['target']['project_id']}:{a['target']['run_id']}:{a['target']['record_id']}"
                          for a in entry["record"].get("assertions",[]) if a["status"] in {"observed","interpretation"}]
            for target in sorted(set(neighbors)):
                if target in pool and target not in ranked:
                    ranked[target] = {"entry":pool[target],"ranking_score":0,"ranking_reasons":[{"via":key,"reason":"reviewed_relationship"}],"relationship_hops":hop}
                    following.append(target)
        frontier = sorted(set(following))
    matches = sorted(ranked.values(),key=lambda r:(r["relationship_hops"],-r["ranking_score"],r["entry"]["key"]))
    results = [{**r,"project":projects[r["entry"]["project_id"]],
                "release":releases[(r["entry"]["project_id"],r["entry"]["run_id"])]} for r in (matches if _all_results else matches[:limit])]
    return {"generation_id":data["generation_id"],"ranking_version":"1","query_terms":terms,
            "view":view,"include_history":data["include_history"],"total_matches":len(matches),
            "omitted_count":max(0,len(matches)-limit),"results":results,
            "limitations":["Reviewed proposals and uncertainties retain their status; ranking is lexical, not semantic.",
                           "Relationship expansion respects view/project/kind/status filters and never establishes active state."]}


def query_batch(access_path: Path, registry_path: Path, configs: list[Path], queries: list[str], **filters) -> dict:
    data = _verified(access_path,registry_path,configs)
    return {"generation_id":data["generation_id"], "queries":[query_verified(data,text=q,**filters) for q in queries]}


def query_index(access_path: Path, registry_path: Path, configs: list[Path], text: str = "",
                view: str = "current", project_id: str | None = None, kind: str | None = None,
                epistemic_status: str | None = None, limit: int = 50, expand_relations: int = 0) -> dict:
    """Return ranked reviewed records only after full fresh access/provenance checks."""
    data = _verified(access_path,registry_path,configs)
    return query_verified(data,text,view,project_id,kind,epistemic_status,limit,expand_relations)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "check", "query", "assertions"):
        command = commands.add_parser(name)
        command.add_argument("--access", type=Path, required=True)
        command.add_argument("--registry", type=Path, required=True)
        command.add_argument("--project-config", type=Path, action="append", required=True)
        if name == "build":
            command.add_argument("--include-history", action="store_true")
        if name == "query":
            command.add_argument("--text", default="")
            command.add_argument("--view", choices=("current", "historical", "all"), default="current")
            command.add_argument("--project")
            command.add_argument("--kind", choices=("requirement", "decision", "uncertainty", "investigation"))
            command.add_argument("--epistemic-status", choices=("observed", "interpretation", "proposal", "unresolved"))
            command.add_argument("--limit", type=int, default=50)
            command.add_argument("--expand-relations",type=int,default=0)
    args = parser.parse_args()
    if args.command == "build":
        data = build_index(args.access, args.registry, args.project_config, args.include_history)
        result = {"status": "built", "generation_id": data["generation_id"],
                  "entry_count": len(data["entries"]), "release_count": len(data["releases"])}
    elif args.command == "check":
        result = check_index(args.access, args.registry, args.project_config)
    elif args.command == "assertions":
        from .kb_reconciliation import assertion_views
        result = assertion_views(_verified(args.access, args.registry, args.project_config))
    else:
        result = query_index(args.access, args.registry, args.project_config, args.text,
                             args.view, args.project, args.kind, args.epistemic_status, args.limit, args.expand_relations)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    run_cli(main)
