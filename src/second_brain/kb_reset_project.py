#!/usr/bin/env python3
"""Remove everything in a project workspace except config/project.json.

Operator-only and destructive: runs, approved releases, CURRENT.json, POLICY.md and
source-provenance.json are deleted. Runs and knowledge are git-ignored, so they cannot
be recovered from git; back them up first. Without --confirm this is a dry run.
External sources are never touched: they live outside the workspace by contract.
"""
import argparse
import os
import shutil
from pathlib import Path

from .kb_common import CHECKOUT, ENGINE, KBError, identifier, load_project, no_symlinks, run_cli

KEEP = Path("config") / "project.json"


def _size(path: Path) -> tuple[int, int]:
    """(files, bytes) under path without following symlinks."""
    if path.is_symlink() or not path.is_dir():
        return 1, path.lstat().st_size
    files = size = 0
    for directory, dirs, names in os.walk(path, followlinks=False):
        for name in names + [d for d in dirs if (Path(directory) / d).is_symlink()]:
            files += 1
            size += (Path(directory) / name).lstat().st_size
    return files, size


def plan_reset(config: Path, projects_root: Path = ENGINE / "projects") -> dict:
    """Validate the workspace and list what a reset would delete. Deletes nothing."""
    config = Path(os.path.abspath(config))
    if config.is_symlink() or config.parent.is_symlink():
        raise KBError(f"Refusing a symlinked project configuration: {config}")
    cfg, root, locations = load_project(config)
    project_id = identifier(cfg["project"]["id"], "project id")
    projects_root = projects_root.resolve()
    no_symlinks(root)
    if root.parent != projects_root or root.name != project_id:
        raise KBError(f"Only workspaces at {projects_root}/<project-id> can be reset; got {root} for "
                      f"project id {project_id!r}")
    if (root / ".git").exists():
        raise KBError(f"Workspace contains a .git entry; refusing to clean a repository: {root}")
    lock = locations["approved"] / ".publish.lock"
    if lock.exists() or lock.is_symlink():
        raise KBError(f"A publication may be in progress ({lock}); wait for it or resolve the stale lock first")
    targets = [p for p in sorted(root.iterdir()) if p.name != "config"]
    targets += [p for p in sorted((root / "config").iterdir()) if p.name != "project.json"]
    entries = []
    for p in targets:
        files, size = _size(p)
        entries.append({"path": p.relative_to(root).as_posix(), "files": files, "bytes": size,
                        "kind": "symlink" if p.is_symlink() else "directory" if p.is_dir() else "file"})
    approved = locations["approved"]
    releases = sorted(p.name for p in approved.iterdir()
                      if p.is_dir() and not p.is_symlink() and not p.name.startswith(".")) if approved.is_dir() else []
    return {"project_id": project_id, "root": str(root), "keep": KEEP.as_posix(), "entries": entries,
            "approved_releases": releases, "current_pointer": (approved / "CURRENT.json").exists()}


def reset_project(config: Path, confirm: str | None = None, delete_approved_releases: bool = False,
                  projects_root: Path = ENGINE / "projects") -> dict:
    """Delete every workspace entry except config/project.json when confirm equals the project id."""
    plan = plan_reset(config, projects_root)
    plan["deleted"] = False
    if confirm is None:
        return plan
    if confirm != plan["project_id"]:
        raise KBError(f"--confirm must repeat the project id exactly: {plan['project_id']!r}")
    if (plan["approved_releases"] or plan["current_pointer"]) and not delete_approved_releases:
        raise KBError(f"Approved knowledge exists ({len(plan['approved_releases'])} release(s)); add "
                      "--delete-approved-releases only after preserving them as required")
    root = Path(plan["root"])
    keep = root / KEEP
    kept_bytes = keep.read_bytes()
    for entry in plan["entries"]:
        p = root / entry["path"]
        if p.is_symlink() or not p.is_dir():
            p.unlink(missing_ok=True)  # removes a link itself, never its target
        else:
            shutil.rmtree(p)
    remaining = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    if remaining != ["config", KEEP.as_posix()] or keep.read_bytes() != kept_bytes:
        raise KBError(f"Reset left unexpected state; inspect {root}: {remaining}")
    plan["deleted"] = True
    return plan


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", type=Path, required=True, help="projects/<project-id>/config/project.json")
    p.add_argument("--projects-root", type=Path, default=CHECKOUT / "projects" if CHECKOUT else None,
                   help="Approved parent of project workspaces; required outside a checkout")
    p.add_argument("--confirm", metavar="PROJECT_ID", help="Repeat the project id to actually delete; omit for a dry run")
    p.add_argument("--delete-approved-releases", action="store_true",
                   help="Also required when knowledge/approved holds releases or CURRENT.json")
    a = p.parse_args()
    if a.projects_root is None:
        raise KBError("Installed reset requires --projects-root pointing to the approved workspace parent")
    result = reset_project(a.project, a.confirm, a.delete_approved_releases, a.projects_root)
    total_files = sum(e["files"] for e in result["entries"])
    total_bytes = sum(e["bytes"] for e in result["entries"])
    verb = "Deleted" if result["deleted"] else "Would delete"
    print(f"{verb} from {result['root']} (keeping {result['keep']}):")
    for e in result["entries"]:
        print(f"  {e['kind']:<9} {e['path']}  ({e['files']} files, {e['bytes']:,} bytes)")
    if not result["entries"]:
        print("  nothing; only config/project.json is present")
    print(f"Total: {total_files} files, {total_bytes:,} bytes.")
    if result["approved_releases"] or result["current_pointer"]:
        print(f"Approved releases: {', '.join(result['approved_releases']) or 'none'}; "
              f"CURRENT.json {'present' if result['current_pointer'] else 'absent'}.")
    if not result["deleted"]:
        print("DRY RUN: nothing was deleted. Runs and knowledge are git-ignored and unrecoverable once deleted; "
              f"back them up, then rerun with --confirm {result['project_id']}.")
    return 0


if __name__ == "__main__":
    run_cli(main)
