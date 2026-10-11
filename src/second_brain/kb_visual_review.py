"""Prepare and check local visual packets; record explicit human comparisons.

These artifacts are neither evidence representations nor approval records.
"""
import argparse
import ctypes
import errno
import hashlib
import html
import importlib.metadata
import json
import os
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .kb_common import CHECKOUT, PACKAGE, KBError, contract, load_project, no_symlinks, parse_ts, read_json, read_stable, run_cli, utc_now
from .kb_visual_render import MAX_BYTES, MAX_DIMENSION, MAX_ITEMS, MAX_PAGES, MAX_PIXELS

VERSION = "1.0"
MAX_PACKET_BYTES = 64 * 1024 * 1024
BASE_LIMITATIONS = [
    "Rendered previews require human comparison with the originals; rendering is not fidelity or semantic validation.",
    "Human inventory declarations and reviewer names are not authenticated by this command.",
    "No GLM capability result, business approval, scope authorization or publication is produced.",
    "The bounded worker is defense in depth, not a general hostile-file sandbox.",
]
MACOS_LIMITATIONS = [*BASE_LIMITATIONS,
    "The macOS worker has CPU, file-size and wall-clock limits but no imposed address-space cap; input and renderer budgets still apply."]
LIMITATIONS = MACOS_LIMITATIONS if sys.platform == "darwin" else BASE_LIMITATIONS


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def write(path, value):
    path.write_bytes(encoded(value))


def output_path(out, sources=()):
    out = Path(out).absolute()
    no_symlinks(out)
    out = out.resolve()
    if out.exists() or not out.parent.is_dir():
        raise KBError("Output must be a fresh directory with an existing parent")
    if any(out == p or out.is_relative_to(p) for p in sources):
        raise KBError("Output overlaps a selected source")
    if out.is_relative_to(PACKAGE) or "approved" in out.parts:
        raise KBError("Output cannot modify package files or approved knowledge")
    run = next((p for p in out.parents if (p / "manifest.json").is_file()), None)
    if run and not out.is_relative_to(run / "work"):
        raise KBError("Run-local visual artifacts must be inside work/")
    if CHECKOUT and out.is_relative_to(CHECKOUT) and not run:
        raise KBError("Use a development output outside the checkout or a run's work/")
    for parent in out.parents:
        config = parent / "config/project.json"
        if config.is_file():
            _, _, locations = load_project(config)
            if out.is_relative_to(locations["approved"]):
                raise KBError("Output cannot modify the configured approved subtree")
            if not run or run.parent != locations["runs"] or not out.is_relative_to(run / "work"):
                raise KBError("Project artifacts require a configured runs/<run>/work/ output")
    return out


def commit_directory(stage, out):
    """Atomic no-replace rename on Linux/macOS, including concurrent empty dirs."""
    output_path(out)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if sys.platform == "linux":
            rename = libc.renameat2
            rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            args = (-100, os.fsencode(stage), -100, os.fsencode(out), 1)  # AT_FDCWD, RENAME_NOREPLACE
        elif sys.platform == "darwin":
            rename = libc.renamex_np
            rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
            args = (os.fsencode(stage), os.fsencode(out), 0x00000004)  # RENAME_EXCL
        else:
            raise KBError("Visual packet creation requires Linux or macOS atomic no-replace support")
    except AttributeError as exc:
        raise KBError("Visual packet creation needs native atomic no-replace rename support") from exc
    rename.restype = ctypes.c_int
    if rename(*args) != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise KBError("Refusing to overwrite an output created concurrently")
        raise OSError(error, os.strerror(error), str(out))


def versions(pdftoppm):
    result = {"python": sys.version.split()[0]}
    for name in ("CairoSVG", "Pillow", "pypdf", "defusedxml", "tinycss2"):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = "unavailable"
    if pdftoppm:
        path = Path(pdftoppm).absolute()
        no_symlinks(path)
        if not path.is_file() or not os.access(path, os.X_OK) or path.name != "pdftoppm":
            raise KBError("--pdftoppm must name an explicitly selected executable named pdftoppm")
        data = read_stable(path, 128 * 1024 * 1024)
        with tempfile.TemporaryFile() as output:
            try:
                subprocess.run([str(path), "-v"], stdout=output, stderr=output, check=True, timeout=5)
            except subprocess.SubprocessError as exc:
                raise KBError("Selected pdftoppm failed its bounded version check") from exc
            if output.tell() > 16 * 1024:
                raise KBError("Unexpected pdftoppm version output")
            output.seek(0)
            result["pdftoppm"] = {"path": str(path), "sha256": sha(data),
                                  "version": output.read().decode("utf-8", errors="replace").strip()}
    else:
        result["pdftoppm"] = None
    return result


def assessment_template(packet, digest):
    return {"schema_version": VERSION, "packet_sha256": digest, "reviewer": None,
            "reviewed_at": None, "inventory_confirmed": False,
            "items": [{"id": item["id"], "elements": []} for item in packet["items"]],
            "issues": [{"id": issue["id"], "disposition": "unmeasured", "note": ""}
                       for issue in packet["issues"]]}


def index_page(packet):
    escape = lambda value: html.escape(str(value), quote=True)
    parts = ['<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\'; style-src \'unsafe-inline\'">',
             '<title>Local visual review</title><style>body{font:16px sans-serif;max-width:1000px;margin:2em auto}img{max-width:100%;background:white}code{overflow-wrap:anywhere}</style>',
             '<h1>Local visual review — assessment pending</h1>']
    parts.extend(f"<p>{escape(value)}</p>" for value in packet["limitations"])
    for source in packet["sources"]:
        parts.append(f"<h2>{escape(source['id'])}: {escape(source['filename'])}</h2><p>Original SHA-256: <code>{source['sha256']}</code>. Exact bytes: <code>{source['original_path']}</code> (inert copy; inspect with a trusted viewer).</p>")
    for item in packet["items"]:
        parts.append(f"<h2>{item['id']}</h2><p>{escape(item['source_id'])} / {escape(item['locator'])}: {escape(item['status'])}</p>")
        if item["preview_path"]:
            parts.append(f'<img src="{item["preview_path"]}" alt="Preview {item["id"]}">')
    parts.append("<h2>Gaps requiring disposition</h2>")
    parts.extend(f"<p>{escape(i['id'])} — {escape(i['source_id'])} / {escape(i['locator'])}: <b>{escape(i['code'])}</b>. {escape(i['detail'])}</p>" for i in packet["issues"])
    return "\n".join(parts).encode()


def prepare(sources, out, pdftoppm=None):
    if not sources or len(sources) > 8:
        raise KBError("Select between 1 and 8 source files")
    paths = []
    for source in sources:
        path = Path(source).absolute()
        no_symlinks(path)
        if not path.is_file():
            raise KBError("Selected source is not a regular file")
        paths.append(path.resolve())
    if len(set(paths)) != len(paths):
        raise KBError("Duplicate selected sources")
    out = output_path(out, paths)
    renderer_versions = versions(pdftoppm)
    stage = Path(tempfile.mkdtemp(prefix=".visual-review-", dir=out.parent))
    try:
        (stage / "originals").mkdir()
        (stage / "previews").mkdir()
        inventory = []
        for number, path in enumerate(paths, 1):
            data = read_stable(path, MAX_BYTES)
            relative = f"originals/S-{number:04}.bin"
            (stage / relative).write_bytes(data)
            inventory.append({"id": f"S-{number:04}", "filename": path.name, "source_path_at_capture": str(path),
                              "extension": path.suffix.lower(), "original_path": relative, "sha256": sha(data), "bytes": len(data)})
        if sum(source["bytes"] for source in inventory) > 32 * 1024 * 1024:
            raise KBError("Selected originals exceed 32 MiB total")
        write(stage / ".worker.json", {"sources": inventory, "pdftoppm": renderer_versions["pdftoppm"]})
        with (stage / ".worker.log").open("wb") as log:
            process = subprocess.Popen([sys.executable, "-P", "-m", "second_brain.kb_visual_review", "--worker", str(stage)],
                                       cwd=stage, stdout=log, stderr=log, start_new_session=True)
            try:
                process.wait(timeout=90)
            except subprocess.TimeoutExpired as exc:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise KBError("Visual worker exceeded 90 seconds; no packet created") from exc
        if process.returncode != 0:
            raise KBError("Visual worker failed; no packet created: " + (stage / ".worker.log").read_bytes()[:2000].decode(errors="replace"))
        result = read_json(stage / ".worker.result.json")
        for name in (".worker.json", ".worker.result.json", ".worker.log"):
            (stage / name).unlink()
        packet = {"schema_version": VERSION, "created_at": utc_now(), "renderers": renderer_versions,
                  "limits": {"source_bytes": MAX_BYTES, "image_pixels": MAX_PIXELS, "max_dimension": MAX_DIMENSION,
                             "max_items": MAX_ITEMS, "max_pdf_pages": MAX_PAGES, "worker_seconds": 90},
                  "sources": inventory, "items": result["items"], "issues": result["issues"], "limitations": list(LIMITATIONS),
                  "files": {}}
        (stage / "index.html").write_bytes(index_page(packet))
        review = ["# Local visual review — human assessment pending", "", *packet["limitations"],
                  "", "Open index.html in a trusted local browser to inspect the raster previews. Originals are inert .bin copies.",
                  "Copy assessment.template.json outside this packet before entering reviewer identity, time, material elements and gap dispositions.", ""]
        for item in packet["items"]:
            review.append(f"{item['id']}: {item['source_id']} / {item['locator']} — {item['status']}; preview: {item['preview_path']}")
        review.extend("\n" + issue["id"] + ": " + issue["code"] + " — " + issue["detail"] for issue in packet["issues"])
        (stage / "review.md").write_text("\n".join(review) + "\n")
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                data = path.read_bytes()
                packet["files"][path.relative_to(stage).as_posix()] = {"sha256": sha(data), "bytes": len(data)}
        if sum(file["bytes"] for file in packet["files"].values()) > MAX_PACKET_BYTES:
            raise KBError("Visual packet exceeds total byte limit")
        write(stage / "packet.json", packet)
        digest = sha((stage / "packet.json").read_bytes())
        (stage / "packet.sha256").write_text(digest + "\n")
        write(stage / "assessment.template.json", assessment_template(packet, digest))
        verify(stage)
        if out.exists():
            raise KBError("Output appeared during preparation")
        commit_directory(stage, out)
        return packet
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def packet_file(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts or Path(relative).as_posix() != relative:
        raise KBError("Invalid packet-relative path")
    path = root / relative
    no_symlinks(path)
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise KBError("Missing or unsafe packet file")
    return path


def verify(root):
    root = Path(root).absolute()
    no_symlinks(root)
    root = root.resolve()
    raw = read_stable(packet_file(root, "packet.json"), 4 * 1024 * 1024)
    digest = read_stable(packet_file(root, "packet.sha256"), 65).decode().strip()
    if sha(raw) != digest:
        raise KBError("Packet manifest hash mismatch")
    packet = read_json(root / "packet.json")
    if sha(encoded(packet)) != digest:
        raise KBError("Packet manifest must use the canonical encoding")
    contract(packet, "visual-packet", source=root / "packet.json")
    if packet.get("schema_version") != VERSION or packet.get("limitations") not in (BASE_LIMITATIONS, MACOS_LIMITATIONS):
        raise KBError("Unsupported visual packet contract")
    parse_ts(packet["created_at"])
    files = packet["files"]
    if not isinstance(files, dict) or sum(f["bytes"] for f in files.values()) > MAX_PACKET_BYTES:
        raise KBError("Invalid visual packet inventory")
    for relative, entry in files.items():
        data = read_stable(packet_file(root, relative), MAX_PACKET_BYTES)
        if len(data) != entry["bytes"] or sha(data) != entry["sha256"]:
            raise KBError("Visual packet content mismatch: " + relative)
    expected = set(files) | {"packet.json", "packet.sha256", "assessment.template.json"}
    actual = set()
    for path in root.rglob("*"):
        no_symlinks(path)
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != expected:
        raise KBError("Unexpected or missing files in visual packet")
    template = read_json(packet_file(root, "assessment.template.json"))
    if template != assessment_template(packet, digest):
        raise KBError("Assessment template must stay unmeasured; fill a separate copy")
    sources = packet["sources"]
    items = packet["items"]
    issues = packet["issues"]
    for values in (sources, items, issues):
        if len({v["id"] for v in values}) != len(values):
            raise KBError("Duplicate visual inventory IDs")
    if not 1 <= len(sources) <= 8 or len(items) > MAX_ITEMS:
        raise KBError("Visual inventory count exceeds contract")
    ids = {s["id"] for s in sources}
    for source in sources:
        if files.get(source["original_path"]) != {"sha256": source["sha256"], "bytes": source["bytes"]}:
            raise KBError("Original binding mismatch")
    for item in items:
        if item["source_id"] not in ids or not item["locator"]:
            raise KBError("Invalid visual source/locator binding")
        if item["status"] == "rendered":
            file = files.get(item["preview_path"], {})
            if file.get("sha256") != item["preview_sha256"] or not all(type(item[k]) is int and 0 < item[k] <= MAX_DIMENSION for k in ("width", "height")):
                raise KBError("Invalid preview binding or dimensions")
            header = read_stable(packet_file(root, item["preview_path"]), 8 * 1024 * 1024)[:24]
            if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR" or struct.unpack(">II", header[16:24]) != (item["width"], item["height"]):
                raise KBError("Preview dimensions do not match its PNG header")
        elif item["status"] != "unavailable" or any(item[k] is not None for k in ("preview_path", "preview_sha256", "width", "height")):
            raise KBError("Invalid unavailable visual item")
        elif not any(i["source_id"] == item["source_id"] and i["locator"] == item["locator"] for i in issues):
            raise KBError("Unavailable visual item needs an explicit gap")
    if any(i["source_id"] not in ids or not i["locator"] for i in issues):
        raise KBError("Invalid visual gap binding")
    return packet


def nonblank(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 16_000


def assess(root, assessment):
    packet = verify(root)
    contract(assessment, "visual-assessment")
    digest = sha(encoded(packet))
    if set(assessment) != {"schema_version", "packet_sha256", "reviewer", "reviewed_at", "inventory_confirmed", "items", "issues"}:
        raise KBError("Unexpected assessment fields")
    if assessment["schema_version"] != VERSION or assessment["packet_sha256"] != digest:
        raise KBError("Assessment binds a different packet")
    if not nonblank(assessment["reviewer"]) or assessment["inventory_confirmed"] is not True:
        raise KBError("A human reviewer must declare the complete material-element inventory")
    when = parse_ts(assessment["reviewed_at"])
    if when < parse_ts(packet["created_at"]) or (when - datetime.now(timezone.utc)).total_seconds() > 600:
        raise KBError("Invalid human review timestamp")
    lookup = {i["id"]: i for i in packet["items"]}
    values = assessment["items"]
    if len(values) != len(lookup) or {v["id"] for v in values} != set(lookup):
        raise KBError("Human assessment must cover every visual item exactly once")
    counts = {status: 0 for status in ("match", "omission", "unsupported", "unavailable", "unresolved")}
    for value in values:
        if set(value) != {"id", "elements"} or not isinstance(value["elements"], list) or not 1 <= len(value["elements"]) <= 1000:
            raise KBError("Each visual needs a bounded, nonempty material-element inventory")
        if len({e["id"] for e in value["elements"]}) != len(value["elements"]):
            raise KBError("Duplicate material-element IDs")
        item = lookup[value["id"]]
        for element in value["elements"]:
            if set(element) != {"id", "status", "observation", "region", "note"} or not nonblank(element["id"]) or element["status"] not in counts or not nonblank(element["note"]) or not isinstance(element["observation"], str) or len(element["observation"]) > 16_000:
                raise KBError("Invalid material-element disposition")
            status, region = element["status"], element["region"]
            if status == "match" and (item["status"] != "rendered" or not nonblank(element["observation"]) or region is None):
                raise KBError("A match needs a rendered preview, region and observed text")
            if region is not None:
                if item["status"] != "rendered" or not isinstance(region, list) or len(region) != 4 or not all(type(n) is int for n in region):
                    raise KBError("Invalid preview region")
                x, y, width, height = region
                if min(x, y) < 0 or min(width, height) <= 0 or x + width > item["width"] or y + height > item["height"]:
                    raise KBError("Preview region exceeds image bounds")
            counts[status] += 1
    issues = assessment["issues"]
    if len(issues) != len(packet["issues"]) or {i["id"] for i in issues} != {i["id"] for i in packet["issues"]}:
        raise KBError("Human assessment must retain every packet gap")
    for issue in issues:
        if set(issue) != {"id", "disposition", "note"} or issue["disposition"] not in {"acknowledged_unavailable", "unresolved"} or not nonblank(issue["note"]):
            raise KBError("Gaps need a human disposition; they cannot be cleared by this command")
    attention = not sum(counts.values()) or bool(issues) or any(counts[k] for k in counts if k != "match")
    if sha(encoded(verify(root))) != digest:
        raise KBError("Packet changed during human-assessment verification")
    total = sum(counts.values())
    return {"status": "needs_attention" if attention else "human_comparison_recorded", "packet_sha256": digest,
            "assessment_sha256": sha(encoded(assessment)), "counts": counts, "business_approval": False,
            "human_fidelity": {"matched_elements": counts["match"], "declared_elements": total,
                               "match_fraction": counts["match"] / total if total else None,
                               "basis": "Human-declared material elements; unresolved/omitted elements remain in denominator. Gaps remain separate."},
            "glm_capability": "unverified", "limitations": packet["limitations"]}


def export(root, assessment, out):
    result = assess(root, assessment)
    packet = verify(root)
    if sha(encoded(packet)) != result["packet_sha256"]:
        raise KBError("Packet changed between assessment and export")
    out = output_path(out, [Path(root).resolve()])
    stage = Path(tempfile.mkdtemp(prefix=".visual-export-", dir=out.parent))
    try:
        # Fence every human string as plain text: exported observations remain untrusted evidence.
        text = ["# Human visual observations — separate source, pending capture and approval", "",
                f"Packet SHA-256: {result['packet_sha256']}", f"Assessment SHA-256: {result['assessment_sha256']}",
                f"Comparison status: {result['status']}; GLM capability: unverified; business approval: false."]
        def literal(value):
            return "\n".join("    " + line for line in str(value).splitlines())
        text.extend(["\nReviewer declaration:", literal(assessment["reviewer"]), assessment["reviewed_at"]])
        for source in packet["sources"]:
            text.extend([f"\n## {source['id']} original", literal(source["filename"]), f"SHA-256: {source['sha256']}"])
        lookup = {i["id"]: i for i in packet["items"]}
        for value in assessment["items"]:
            item = lookup[value["id"]]
            text.extend([f"\n## {item['id']} — {item['source_id']}", "Original locator:", literal(item["locator"]),
                         f"Asset SHA-256: {item['asset_sha256']}", f"Preview SHA-256: {item['preview_sha256']}"])
            for element in value["elements"]:
                text.extend(["\nElement:", literal(element["id"]), f"Disposition: {element['status']}; preview pixel region [x,y,width,height]: {element['region']}",
                             "Human observation:", literal(element["observation"]), "Human note:", literal(element["note"])])
        text.append("\n## Retained gaps and limitations")
        decisions = {i["id"]: i for i in assessment["issues"]}
        for issue in packet["issues"]:
            decision = decisions[issue["id"]]
            text.extend([f"\n{issue['id']}: {issue['code']}; {decision['disposition']}", literal(issue["locator"]), literal(issue["detail"]), literal(decision["note"])])
        text.extend(packet["limitations"])
        data = ("\n".join(text) + "\n").encode()
        (stage / "transcription.md").write_bytes(data)
        write(stage / "assessment.json", assessment)
        write(stage / "provenance.json", {"schema_version": VERSION, **result, "transcription_sha256": sha(data),
                                          "packet_manifest": packet, "capture_required": True})
        if out.exists():
            raise KBError("Export output appeared during preparation")
        if sha(encoded(verify(root))) != result["packet_sha256"]:
            raise KBError("Packet changed during export")
        commit_directory(stage, out)
        return result
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def set_worker_limits():
    """Apply platform budgets without relaxing inherited soft or hard limits."""
    import resource
    if sys.platform not in ("linux", "darwin"):
        raise KBError("Visual worker resource controls require Linux or macOS")
    limits = [(resource.RLIMIT_CPU, 60), (resource.RLIMIT_FSIZE, 16 * 1024 * 1024)]
    if sys.platform == "linux":
        limits.insert(0, (resource.RLIMIT_AS, 512 * 1024 * 1024))
    # Darwin can reject lowering RLIMIT_AS below the interpreter's virtual size.
    # The packet discloses the absent cap; retain all other budgets and controls.
    for kind, budget in limits:
        soft, hard = resource.getrlimit(kind)
        hard = budget if hard == resource.RLIM_INFINITY else min(hard, budget)
        soft = hard if soft == resource.RLIM_INFINITY else min(soft, hard)
        resource.setrlimit(kind, (soft, hard))


def worker(root):
    set_worker_limits()
    from .kb_visual_render import Renderer
    root = Path(root)
    config = read_json(root / ".worker.json")
    converter = config["pdftoppm"]
    if converter and sha(read_stable(Path(converter["path"]), 128 * 1024 * 1024)) != converter["sha256"]:
        raise KBError("Selected PDF renderer changed")
    renderer = Renderer(root, converter["path"] if converter else None)
    for source in config["sources"]:
        try:
            renderer.source(source)
        except Exception as exc:
            renderer.gap(source["id"], "original", "source_visuals_unavailable", f"{type(exc).__name__}: {str(exc)[:400]}")
    write(root / ".worker.result.json", {"items": renderer.items, "issues": renderer.issues})
    return 0


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        return worker(sys.argv[2])
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare", help="Create a fresh local visual packet")
    prepare_parser.add_argument("--source", type=Path, action="append", required=True)
    prepare_parser.add_argument("--out", type=Path, required=True)
    prepare_parser.add_argument("--pdftoppm", type=Path, help="Explicit trusted local Poppler executable")
    for name in ("verify", "assess", "export"):
        command = commands.add_parser(name)
        command.add_argument("--packet", type=Path, required=True)
        if name != "verify":
            command.add_argument("--assessment", type=Path, required=True)
        if name == "export":
            command.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        packet = prepare(args.source, args.out, args.pdftoppm)
        result = {"status": "prepared", "packet": str(args.out), "items": len(packet["items"]),
                  "gaps": len(packet["issues"]), "human_assessment": "pending", "glm_capability": "unverified"}
    elif args.command == "verify":
        packet = verify(args.packet)
        result = {"status": "integrity_verified", "items": len(packet["items"]), "fidelity": "unmeasured"}
    else:
        assessment = read_json(args.assessment)
        contract(assessment, "visual-assessment", source=args.assessment)
        result = export(args.packet, assessment, args.out) if args.command == "export" else assess(args.packet, assessment)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    run_cli(main)
