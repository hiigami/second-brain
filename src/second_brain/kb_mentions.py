#!/usr/bin/env python3
"""List explicit same-domain project-name candidates in a sealed run's work folder."""
import argparse
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from .kb_check import load_manifest, load_segment_inventory
from .kb_common import (KBError, contract, error_context, inside, json_bytes, json_sha, no_symlinks, read_json,
                       read_stable, run_cli, sha, validate_pattern, write_new)

_TOKEN = re.compile(r"[^\W_][\w\u0300-\u036f]*", re.UNICODE)
_MAX_PROJECTS = 100
_MAX_ALIASES = 3000
_MAX_MENTIONS = 10000
_MAX_REPORT_BYTES = 16 * 1024 * 1024


def _fold(token: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", token.casefold())
                   if not unicodedata.combining(c))


def _tokens(value: str) -> list[tuple[str, int, int]]:
    return [(_fold(m.group()), m.start(), m.end()) for m in _TOKEN.finditer(value)]


def _alias_key(value: str) -> tuple[str, ...]:
    if value != value.strip():
        raise KBError(f"Project alias has leading or trailing whitespace: {value!r}")
    tokens = _tokens(value)
    if not tokens or not all(token for token, _, _ in tokens):
        raise KBError(f"Project alias has no searchable words: {value!r}")
    return tuple(token for token, _, _ in tokens)


def load_registry(path: Path) -> dict:
    """Validate registry shape, alias identity, and descriptive ownership paths."""
    no_symlinks(path)
    with error_context(path):
        return validate_registry(read_json(path))


def validate_registry(registry: dict) -> dict:
    contract(registry, "project-registry")
    if len(registry["projects"]) > _MAX_PROJECTS:
        raise KBError("Project registry exceeds 100 projects")
    ids: set[str] = set()
    aliases: dict[tuple[str, tuple[str, ...]], str] = {}
    count = 0
    for project in registry["projects"]:
        pid = project["id"]
        if pid in ids:
            raise KBError(f"Duplicate project id: {pid}")
        ids.add(pid)
        for owner in project["owns_paths"]:
            validate_pattern(owner["pattern"])
        for value in [project["name"], *project["aliases"]]:
            key = (project["information_domain"], _alias_key(value))
            prior = aliases.get(key)
            if prior is not None and prior != pid:
                raise KBError(f"Normalized project alias {value!r} is shared by {prior} and {pid} "
                              f"in information domain {key[0]}")
            aliases[key] = pid
            count += 1
            if count > _MAX_ALIASES:
                raise KBError("Project registry exceeds 3,000 names and aliases")
    if registry["schema_version"] == "1.1":
        projects = {p["id"]: p for p in registry["projects"]}
        for grant in registry["disclosures"]:
            origin, target = grant["from_project"], grant["to_project"]
            if origin not in projects or target not in projects or origin == target:
                raise KBError("Disclosure grant names an unknown or identical origin/target project")
            if projects[origin]["information_domain"] != projects[target]["information_domain"]:
                raise KBError("Disclosure grant crosses information domains")
            validate_pattern(grant["path_pattern"])
    return registry


def _alias_index(registry: dict, home_id: str) -> tuple[dict, int, str]:
    projects = {p["id"]: p for p in registry["projects"]}
    if home_id not in projects:
        raise KBError(f"Run's home project {home_id!r} is not registered")
    domain = projects[home_id]["information_domain"]
    index: dict[str, list[tuple[tuple[str, ...], str, str]]] = defaultdict(list)
    skipped = 0
    for project in sorted(registry["projects"], key=lambda p: p["id"]):
        if project["id"] == home_id:
            continue
        if project["information_domain"] != domain:
            skipped += 1
            continue
        seen: set[tuple[str, ...]] = set()
        for value in [project["name"], *project["aliases"]]:
            key = _alias_key(value)
            if key in seen:
                continue
            seen.add(key)
            index[key[0]].append((key, value, project["id"]))
    return index, skipped, domain


def _line_matches(line: str, index: dict) -> list[dict]:
    words = _tokens(line)
    found = []
    for i, (first, start, _) in enumerate(words):
        for alias, label, target in index.get(first, []):
            end_index = i + len(alias)
            if end_index > len(words) or tuple(w[0] for w in words[i:end_index]) != alias:
                continue
            end = words[end_index - 1][2]
            found.append({"start_char": start, "end_char": end, "matched_text": line[start:end],
                          "matched_alias": label, "target_project_id": target})
    for match in found:
        overlapping_targets = {other["target_project_id"] for other in found
                               if other["start_char"] < match["end_char"]
                               and match["start_char"] < other["end_char"]}
        match["classification"] = ("ambiguous_alias_overlap" if len(overlapping_targets) > 1
                                    else "explicit_alias_candidate")
    return found


def build_mention_report(run: Path, registry: dict) -> dict:
    """Recompute candidates from verified snapshots and a validated registry value."""
    validate_registry(registry)
    manifest = load_manifest(run)
    if manifest["status"] != "ready":
        raise KBError("Cannot scan mentions in a blocked run")
    manifest_digest = sha(read_stable(inside(run, "manifest.json"), 16 * 1024 * 1024))
    if manifest_digest != read_stable(inside(run, "manifest.sha256"), 256).decode("ascii").strip():
        raise KBError("Manifest changed during mention scan preparation")
    registry_digest = json_sha(registry)
    index, skipped, domain = _alias_index(registry, manifest["project_id"])
    segments = load_segment_inventory(run, manifest)
    by_evidence: dict[str, list[dict]] = defaultdict(list)
    for segment in (segments or {}).get("segments", []):
        by_evidence[segment["evidence_id"]].append(segment)
    mentions = []
    selected = None
    if "targeted" in manifest:
        from .kb_intervals import selected_ranges
        from .kb_targeting import load_targeted
        selected = selected_ranges(run, manifest, load_targeted(run, manifest))[0]
    for f in sorted(manifest["files"], key=lambda x: (x["source_id"], x["relative_path"])):
        raw = read_stable(inside(run, f["snapshot_path"]), manifest["limits"]["max_file_bytes"])
        expected = f["document"]["text_sha256"] if "document" in f else f["sha256"]
        if sha(raw) != expected:
            raise KBError(f"Snapshot integrity changed during mention scan: {f['evidence_id']}")
        lines = raw.decode("utf-8-sig").splitlines()
        for line_number, line in enumerate(lines, 1):
            if selected is not None and not any(a <= line_number <= b for a,b in selected.get(f["evidence_id"], [])):
                continue
            for match in _line_matches(line, index):
                if len(mentions) >= _MAX_MENTIONS:
                    raise KBError("Mention scan exceeds 10,000 candidate occurrences")
                target = match["target_project_id"]
                match["id"] = "M-" + json_sha([f["evidence_id"], line_number,
                                                  match["start_char"], match["end_char"], target])[:24]
                match.update({"evidence_id": f["evidence_id"], "line": line_number,
                              "line_text": line,
                              "segments": [{"segment_id": s["segment_id"],
                                            "representation_sha256": s["representation_sha256"],
                                            "original_locator": s["original_locator"]}
                                           for s in by_evidence[f["evidence_id"]]
                                           if s["line_start"] <= line_number <= s["line_end"]]})
                mentions.append(match)
    mentions.sort(key=lambda m: (m["evidence_id"], m["line"], m["start_char"],
                                 m["end_char"], m["target_project_id"]))
    if sha(read_stable(inside(run, "manifest.json"), 16 * 1024 * 1024)) != manifest_digest:
        raise KBError("Manifest changed during mention scan")
    report = {"schema_version": "1.0", "project_id": manifest["project_id"],
              "run_id": manifest["run_id"], "information_domain": domain,
              "registry_sha256": registry_digest,
              "manifest_sha256": manifest_digest,
              "scope": "explicit_names_and_aliases_of_other_registered_same_domain_projects",
              "skipped_cross_domain_projects": skipped, "mentions": mentions}
    data = json_bytes(report)
    if len(data) > _MAX_REPORT_BYTES:
        raise KBError("Mention report exceeds the 16 MiB work-file limit")
    return report


def scan_mentions(run: Path, registry_path: Path) -> dict:
    """Scan checked frozen text and write reproducible, non-approved work artifacts."""
    if registry_path.resolve().is_relative_to(run.resolve()):
        raise KBError("Project registry must be maintained outside the evidence run")
    registry = load_registry(registry_path)
    report = build_mention_report(run, registry)
    if json_sha(load_registry(registry_path)) != report["registry_sha256"]:
        raise KBError("Project registry changed during mention scan")
    snapshot = inside(run, "work/registry.snapshot.json")
    snapshot_bytes = json_bytes(registry)
    destination = inside(run, "work/mentions.json")
    if snapshot.exists() or snapshot.is_symlink():
        if read_stable(snapshot, _MAX_REPORT_BYTES) != snapshot_bytes:
            raise KBError("A different work/registry.snapshot.json already exists")
    if destination.exists() or destination.is_symlink():
        if read_stable(destination, _MAX_REPORT_BYTES) != json_bytes(report):
            raise KBError("A different work/mentions.json already exists; use a new run or retain the original")
    if not snapshot.exists():
        write_new(snapshot, snapshot_bytes)
    if not destination.exists():
        write_new(destination, json_bytes(report))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True,
                        help="Operator-maintained projects/registry.json; never inferred from source text")
    args = parser.parse_args()
    report = scan_mentions(args.run, args.registry)
    print(f"Listed {len(report['mentions'])} explicit alias candidates in "
          f"{args.run / 'work' / 'mentions.json'}; semantic routing remains pending")
    return 0


if __name__ == "__main__":
    run_cli(main)
