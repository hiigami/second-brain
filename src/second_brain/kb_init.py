#!/usr/bin/env python3
"""Create a local project workspace without touching its external sources."""
import argparse
import os
from pathlib import Path

from .kb_common import (CHECKOUT, ENGINE, EXPANDED_SOURCE_TYPES, GLOBAL_EXCLUDE, KBError,
                       SOURCE_SCOPE_NAME, SOURCE_TYPES, contract,
                       identifier, no_symlinks, run_cli, write_json_new)


def initial_config(project_id: str, name: str, source_values: list[str]) -> dict:
    sources = []
    seen = set()
    for value in source_values:
        parts = value.split(":", 2)
        if len(parts) != 3:
            raise KBError("--source format is id:type:/absolute/path (quote the whole value if needed)")
        sid, kind, raw = parts
        identifier(sid, "source id")
        if sid in seen or kind not in SOURCE_TYPES:
            raise KBError("Source ids must be unique and source types must be supported")
        seen.add(sid)
        path = Path(raw).expanduser()
        if not path.is_absolute() or not path.is_dir() or path.is_symlink():
            raise KBError(f"Source must be an existing absolute, non-symlink directory: {raw}")
        includes = ["**/*.md", "**/*.txt"]
        if kind == "sql":
            includes = ["**/*.sql", "**/*.md"]
        elif kind == "repository":
            includes = ["src/**", "tests/**", "docs/**"]
        sources.append({"id": sid, "type": kind, "path": str(path.resolve()), "include": includes, "exclude": []})
    cfg = {"schema_version": "0.1", "project": {"id": identifier(project_id, "project id"),
                "name": name, "description": "Stage 2 pilot — scoped evidence-linked knowledge."},
           "sources": sources, "global_exclude": GLOBAL_EXCLUDE,
           "knowledge": {"path": "knowledge", "approved": "knowledge/approved"}, "runs": {"path": "runs"}}
    contract(cfg, "project")
    return cfg


def initial_source_scope(project_id: str, source_values: list[str], existing_ids: set[str]) -> dict | None:
    """Build additive sources without changing the frozen project.json shape."""
    if not source_values:
        return None
    sources = []
    seen = set(existing_ids)
    for value in source_values:
        parts = value.split(":", 2)
        if len(parts) != 3:
            raise KBError("--expanded-source format is id:type:/absolute/path")
        sid, kind, raw = parts
        identifier(sid, "source id")
        if sid in seen or kind not in EXPANDED_SOURCE_TYPES:
            raise KBError("Expanded source ids must be unique and type must be data, analysis, or policy")
        seen.add(sid)
        path = Path(raw).expanduser()
        if not path.is_absolute() or not path.is_dir() or path.is_symlink():
            raise KBError(f"Source must be an existing absolute, non-symlink directory: {raw}")
        includes = ["**/*.csv", "**/*.json", "**/*.md", "**/*.txt"] if kind == "data" else ["**/*.md", "**/*.txt"]
        sources.append({"id": sid, "type": kind, "path": str(path.resolve()),
                        "include": includes, "exclude": []})
    scope = {"schema_version": "1.0", "project_id": project_id, "sources": sources}
    contract(scope, "source-scope")
    return scope


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project-id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--source", action="append", required=True, help="id:type:/absolute/path; repeat for each source")
    p.add_argument("--expanded-source", action="append", default=[],
                   help="id:data|analysis|policy:/absolute/path; writes config/source-scope.json")
    p.add_argument("--workspace", type=Path,
                   help="Required in installed distributions; checkout default: projects/<project-id>")
    a = p.parse_args()
    cfg = initial_config(a.project_id, a.name, a.source)
    source_scope = initial_source_scope(a.project_id, a.expanded_source,
                                       {source["id"] for source in cfg["sources"]})
    if a.workspace is None and CHECKOUT is None:
        raise KBError("Installed init requires --workspace outside the package installation")
    root = a.workspace or ENGINE / "projects" / a.project_id
    no_symlinks(root)
    if root.exists():
        raise KBError(f"Workspace already exists; edit its config manually or choose a new project id: {root}")
    root_abs = Path(os.path.abspath(root))
    paths = [Path(s["path"]) for s in cfg["sources"] + (source_scope["sources"] if source_scope else [])]
    for i, source in enumerate(paths):
        if root_abs.is_relative_to(source) or source.is_relative_to(root_abs):
            raise KBError("Source and project workspace must be separate")
        for other in paths[i + 1:]:
            if source.is_relative_to(other) or other.is_relative_to(source):
                raise KBError("Source roots must not overlap")
    root.mkdir(parents=True)
    write_json_new(root / "config" / "project.json", cfg)
    if source_scope is not None:
        write_json_new(root / "config" / SOURCE_SCOPE_NAME, source_scope)
    (root / "knowledge" / "approved").mkdir(parents=True)
    (root / "runs").mkdir()
    print(f"Created {root / 'config/project.json'}. Review the source scopes before inventory.")
    return 0


if __name__ == "__main__":
    run_cli(main)
