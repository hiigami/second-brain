#!/usr/bin/env python3
"""Create/verify a new document evidence snapshot; never edit existing Stage 2 runs."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys

from .kb_document_extractors import ExtractionError, FORMATS, Limits, Options, digest, extract_bytes


def read_stable(path: Path, max_bytes: int) -> bytes:
    path = path.absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ExtractionError("symlink_not_allowed", str(path))
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ExtractionError("not_regular_file", str(path))
            if before.st_size > max_bytes:
                raise ExtractionError("input_budget_exceeded", str(path))
            raw = stream.read(max_bytes + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > max_bytes:
            raise ExtractionError("input_budget_exceeded", str(path))
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(raw) != after.st_size:
            raise ExtractionError("source_changed_during_capture", str(path))
        return raw
    except OSError as exc:
        raise ExtractionError("source_unavailable", f"{path}: {exc}") from exc


def verify(directory: Path, compare_source: Path | None = None) -> dict:
    mbytes = read_stable(directory / "extraction.json", 20 * 1024 * 1024)
    recorded_hash = read_stable(directory / "extraction.sha256", 100).decode("ascii").strip()
    if digest(mbytes) != recorded_hash:
        raise ExtractionError("metadata_hash_mismatch", "extraction.json changed")
    m = json.loads(mbytes)
    ext = m.get("source_extension")
    if ext not in FORMATS or m.get("schema_version") != "1.0" or m.get("status") != "extracted_needs_review":
        raise ExtractionError("invalid_metadata", "Unknown schema, extension or status")
    raw = read_stable(directory / ("original" + ext), 25 * 1024 * 1024)
    textbytes = read_stable(directory / "evidence.md", 8 * 1024 * 1024)
    if digest(raw) != m.get("source_sha256") or len(raw) != m.get("source_bytes"):
        raise ExtractionError("original_hash_mismatch", "Frozen original changed")
    if digest(textbytes) != m.get("text_sha256") or len(textbytes) != m.get("text_bytes"):
        raise ExtractionError("text_hash_mismatch", "Derived evidence changed")
    text = textbytes.decode("utf-8", errors="strict")
    lines = text.splitlines()
    if m.get("text_line_count") != len(lines) or not isinstance(m.get("segments"), list) or not m["segments"]:
        raise ExtractionError("invalid_metadata", "Missing segments or inconsistent line count")
    previous = 0
    for segment in m["segments"]:
        a, z = segment.get("line_start"), segment.get("line_end")
        if type(a) is not int or type(z) is not int or not previous < a <= z <= len(lines) or not isinstance(segment.get("locator"), str):
            raise ExtractionError("invalid_metadata", "Invalid or overlapping source line ranges")
        previous = z
    if compare_source is not None and digest(read_stable(compare_source, 25 * 1024 * 1024)) != m["source_sha256"]:
        raise ExtractionError("source_changed_since_capture", str(compare_source))
    return {"status": "integrity_passed", "fidelity_review": "still_required", "source_filename": m["source_filename"], "segments": len(m["segments"])}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", type=Path)
    mode.add_argument("--verify", type=Path, metavar="SNAPSHOT_DIR")
    mode.add_argument("--worker-name", help=argparse.SUPPRESS)
    p.add_argument("--out", type=Path, help="New output directory; existing directories are never overwritten")
    p.add_argument("--compare-source", type=Path, help="With --verify: also check that the live original is unchanged")
    p.add_argument("--csv-encoding", default="utf-8-sig")
    p.add_argument("--csv-delimiter", default=",")
    p.add_argument("--csv-structured", action="store_true")
    p.add_argument("--csv-header", choices=("none", "first-row"), default="none")
    p.add_argument("--allow-legacy-ppt", action="store_true", help="Trusted files only; opt in to local LibreOffice conversion")
    p.add_argument("--soffice", help="Path to approved LibreOffice executable")
    p.add_argument("--timeout", type=int, default=90, help="Worker wall-clock timeout in seconds")
    return p


def main():
    args = parser().parse_args()
    try:
        options = Options(args.csv_encoding, args.csv_delimiter, args.allow_legacy_ppt, args.soffice,
                          args.csv_structured, args.csv_header)
        if args.worker_name:
            raw = sys.stdin.buffer.read(Limits().max_input_bytes + 1)
            result = extract_bytes(raw, args.worker_name, options=options)
            print(json.dumps({"text": result.text, "metadata": result.metadata}, ensure_ascii=False))
            return 0
        if args.verify is not None:
            print(json.dumps(verify(args.verify, args.compare_source), indent=2))
            return 0
        if args.out is None or args.timeout < 1:
            raise ExtractionError("invalid_arguments", "--source needs --out and a positive --timeout")
        if args.out.exists() or args.out.is_symlink():
            raise ExtractionError("output_exists", "Choose a new snapshot directory; existing evidence is never overwritten")
        if any(p.is_symlink() for p in args.out.absolute().parents):
            raise ExtractionError("symlink_not_allowed", "Output parent path contains a symlink")
        raw = read_stable(args.source, Limits().max_input_bytes)
        command = [sys.executable, "-P", "-m", "second_brain.kb_extract_document", "--worker-name", args.source.name,
                   "--csv-encoding", args.csv_encoding, "--csv-delimiter", args.csv_delimiter,
                   "--csv-header", args.csv_header]
        if args.csv_structured:
            command.append("--csv-structured")
        if args.allow_legacy_ppt:
            command += ["--allow-legacy-ppt"]
        if args.soffice:
            command += ["--soffice", args.soffice]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=(os.name == "posix"))
        try:
            stdout, stderr = process.communicate(raw, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.communicate()
            raise ExtractionError("extraction_timeout", "Worker exceeded time budget; no snapshot was committed")
        if process.returncode != 0:
            print(stderr.decode("utf-8", errors="replace").strip(), file=sys.stderr)
            return 2
        output = json.loads(stdout)
        m = output["metadata"]
        m["source_absolute_path_at_capture"] = str(args.source.absolute())
        m["worker_timeout_seconds"] = args.timeout
        mbytes = (json.dumps(m, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        args.out.mkdir(parents=True, exist_ok=False)
        # Hash file is the final commit marker. Failed writes leave an unverifiable directory, not a ready snapshot.
        (args.out / ("original" + m["source_extension"])).write_bytes(raw)
        (args.out / "evidence.md").write_text(output["text"], encoding="utf-8", newline="\n")
        (args.out / "extraction.json").write_bytes(mbytes)
        (args.out / "extraction.sha256").write_text(digest(mbytes) + "\n", encoding="ascii")
        checked = verify(args.out)
        print(f"EXTRACTED — REVIEW REQUIRED: {args.out.resolve()}")
        print(f"{checked['segments']} source segments; {len(m['issues'])} warnings")
        return 0
    except (ExtractionError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
