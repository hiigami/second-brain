#!/usr/bin/env python3
"""Copy the canonical .agents/skills into each assistant's skill folder, or check for drift."""
import argparse
from pathlib import Path

from .kb_common import CHECKOUT, ENGINE, KBError, no_symlinks, read_stable, run_cli

CANONICAL = ".agents/skills"
MIRRORS = (".claude/skills", ".coda/skills")


def skill_files(root: Path) -> dict[str, bytes]:
    no_symlinks(root)
    if not root.is_dir():
        return {}
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise KBError(f"Symlink not permitted in skills: {path}")
        if path.is_file() and path.name != ".DS_Store":
            out[path.relative_to(root).as_posix()] = read_stable(path, 1024 * 1024)
    return out


def drift(engine: Path = ENGINE) -> dict[str, list[str]]:
    canonical = skill_files(engine / CANONICAL)
    if not canonical:
        raise KBError(f"No canonical skills found under {engine / CANONICAL}")
    report = {}
    for mirror in MIRRORS:
        files = skill_files(engine / mirror)
        diff = sorted(k for k in set(canonical) | set(files) if canonical.get(k) != files.get(k))
        if diff:
            report[mirror] = diff
    return report


def sync(engine: Path = ENGINE) -> list[str]:
    canonical = skill_files(engine / CANONICAL)
    written = []
    for mirror in MIRRORS:
        root = engine / mirror
        stale = sorted(set(skill_files(root)) - set(canonical))
        if stale:
            raise KBError(f"{mirror} has files absent from {CANONICAL}; move or delete them by hand: {stale}")
        for rel, data in canonical.items():
            target = root / rel
            no_symlinks(target)
            if not target.exists() or target.read_bytes() != data:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                written.append(f"{mirror}/{rel}")
    return written


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", help="Report drift and exit 1 instead of writing")
    p.add_argument("--engine", type=Path, default=CHECKOUT, help="Checkout containing canonical and mirrored skills")
    a = p.parse_args()
    if a.engine is None:
        raise KBError("Installed skill synchronization requires --engine pointing to the engine checkout")
    if a.check:
        report = drift(a.engine)
        for mirror, files in report.items():
            print(f"DRIFT {mirror}: {', '.join(files)}")
        if not report:
            print(f"PASS: {', '.join(MIRRORS)} match {CANONICAL}")
        return 1 if report else 0
    written = sync(a.engine)
    print("\n".join(f"updated {x}" for x in written) or "Already in sync")
    return 0


if __name__ == "__main__":
    run_cli(main)
