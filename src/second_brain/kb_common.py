#!/usr/bin/env python3
"""Shared, offline Stage 2 contracts.

Runtime: Python 3.14 through uv (see pyproject.toml). This module uses only the
standard library; the document parsers are imported by kb_document_extractors.
"""
import fnmatch
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Callable

# 0.2.0: document capture, ai_generated_source warnings, records/review 0.2 contracts.
# 0.2.1: frozen engine-owned capture policy; legacy fingerprints use fixed inputs.
# 0.3.0: additive, frozen source-scope registry for data/analysis/policy sources.
# 0.4.0: quotable representation identity and frozen segment inventory.
# Runs keep the version that captured them; see kb_check.load_manifest.
TOOL_VERSION = "0.4.0"
PACKAGE = Path(__file__).resolve().parent
SCHEMAS = PACKAGE / "schemas"
_checkout = PACKAGE.parents[1]
CHECKOUT = _checkout if (_checkout / "pyproject.toml").is_file() and (_checkout / "tools").is_dir() else None
ENGINE = CHECKOUT or PACKAGE
SOURCE_TYPES = ("requirements", "architecture", "meetings", "sql", "repository")
EXPANDED_SOURCE_TYPES = ("data", "analysis", "policy")
SOURCE_SCOPE_NAME = "source-scope.json"
SOURCE_SCOPE_SNAPSHOT = "source-scope.snapshot.json"
GLOBAL_EXCLUDE = [f"**/{x}/**" for x in (
    ".git", "node_modules", ".venv", "venv", "build", "dist", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".idea", ".vscode")]
SECRET_PATTERNS = ["**/.env*", "**/*.pem", "**/*.key", "**/id_rsa*",
                   "**/id_ed25519*", "**/credentials*.json", "**/token*.json",
                   "**/.ssh/**", "**/.aws/**", "**/.azure/**"]
TEXT_EXTENSIONS = set(".md .txt .sql .py .rs .kt .kts .java .js .ts .tsx .jsx .json "
                      ".yaml .yml .toml .xml .csv .mmd .graphql .proto .sh .conf .ini "
                      ".properties .html .css .go .rb .scala .c .h .cpp .hpp .cs .rst".split())
# Exact engine-owned inputs to the 0.1.0/0.2.0 scope fingerprint. Never derive
# legacy verification from mutable current capture defaults.
LEGACY_TEXT_EXTENSIONS = tuple(sorted(
    ".md .txt .sql .py .rs .kt .kts .java .js .ts .tsx .jsx .json "
    ".yaml .yml .toml .xml .csv .mmd .graphql .proto .sh .conf .ini "
    ".properties .html .css .go .rb .scala .c .h .cpp .hpp .cs .rst".split()))
LEGACY_SECRET_PATTERNS = ("**/.env*", "**/*.pem", "**/*.key", "**/id_rsa*",
                          "**/id_ed25519*", "**/credentials*.json", "**/token*.json",
                          "**/.ssh/**", "**/.aws/**", "**/.azure/**")
LEGACY_CAPTURE_VERSIONS = frozenset({"0.1.0", "0.2.0"})
# Formats routed through kb_document_extractors when document capture is enabled.
# .csv stays on the text path unless the explicit structured-CSV option is chosen.
DOCUMENT_EXTENSIONS = frozenset({".docx", ".pdf", ".xlsx", ".pptx", ".ppt", ".html", ".eml", ".svg", ".png"})
# Legacy .ppt requires an explicit opt-in flag at inventory time.
LEGACY_DOCUMENT_EXTENSIONS = frozenset({".ppt"})
# Case-insensitive file-name markers of machine-written meeting summaries. Used only
# when source-provenance.json does not state origin.authorship for the file.
AI_SUMMARY_NAME_MARKERS = ("notes by gemini", "notas de gemini", "notas por gemini",
                           "gemini notes", "ai-generated", "ai generated")


def ai_summary_name(relative_path: str) -> bool:
    return any(m in relative_path.rsplit("/", 1)[-1].lower() for m in AI_SUMMARY_NAME_MARKERS)


class KBError(Exception):
    """An actionable contract or filesystem failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_ts(value: str) -> datetime:
    """Parse an ISO 8601 timestamp that carries a timezone; compare these, never strings."""
    check_timestamp(value)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# Clock skew tolerated between an operator-supplied timestamp and this machine.
CLOCK_SKEW_SECONDS = 600

# Deterministic content-date sources, most specific first. A filename date is the
# date the *content* claims (e.g. a meeting), never the capture or file-system time.
_CONTENT_DATE_PATTERNS = (
    ("filename:gemini_notes", "minute",
     re.compile(r"(?<!\d)(\d{4})_(\d{2})_(\d{2}) (\d{2})_(\d{2}) GMT([+-]\d{2})_(\d{2})(?!\d)")),
    ("filename:iso_date", "day", re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")),
    ("filename:underscore_date", "day", re.compile(r"(?<!\d)(\d{4})_(\d{2})_(\d{2})(?!\d)")),
)


def content_date_from_name(relative_path: str) -> dict | None:
    """Best-effort, deterministic content date from a file name; None when absent or invalid."""
    import unicodedata
    name = unicodedata.normalize("NFC", relative_path.rsplit("/", 1)[-1])
    for basis, precision, pattern in _CONTENT_DATE_PATTERNS:
        m = pattern.search(name)
        if not m:
            continue
        g = m.groups()
        try:
            if precision == "minute":
                value = datetime.fromisoformat(f"{g[0]}-{g[1]}-{g[2]}T{g[3]}:{g[4]}:00{g[5]}:{g[6]}").isoformat()
            else:
                value = datetime(int(g[0]), int(g[1]), int(g[2])).date().isoformat()
        except ValueError:
            continue
        return {"value": value, "basis": basis, "precision": precision}
    return None


def content_sort_key(value: str) -> str:
    """UTC-normalized ordering key for a content_date value (date-only sorts at 00:00 UTC)."""
    if len(value) == 10:
        return value + "T00:00:00+00:00"
    return parse_ts(value).astimezone(timezone.utc).isoformat()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def json_sha(data: Any) -> str:
    return sha(canonical(data))


def json_bytes(data: Any) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _unique_pairs(items: list) -> dict:
    out = {}
    for key, value in items:
        if key in out:
            raise KBError(f"Duplicate JSON key: {key}")
        out[key] = value
    return out


def read_json(path: Path) -> Any:
    try:
        text = read_stable(path, 16 * 1024 * 1024).decode("utf-8-sig")
        return json.loads(text, object_pairs_hook=_unique_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(KBError(f"Invalid JSON: {x}")))
    except (OSError, ValueError, UnicodeError) as exc:
        raise KBError(f"Cannot read JSON {path}: {exc}") from exc


def no_symlinks(path: Path) -> None:
    """Reject currently existing symlinks in an output/artifact path."""
    absolute = Path(os.path.abspath(path))
    for part in (absolute, *absolute.parents):
        if part.is_symlink():
            raise KBError(f"Symlink not permitted: {part}")


def read_stable(path: Path, limit: int) -> bytes:
    """Bounded regular-file read; reject final-component symlinks and detected writes."""
    if path.is_symlink():
        raise KBError(f"Symlink not permitted: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise KBError(f"Not a regular file: {path}")
        if before.st_size > limit:
            raise KBError(f"File exceeds {limit} bytes: {path}")
        data = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
    if len(data) > limit:
        raise KBError(f"File exceeds {limit} bytes: {path}")
    attrs = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, x) != getattr(after, x) for x in attrs) or len(data) != after.st_size:
        raise KBError(f"File changed during read; retry on a stable source: {path}")
    return data


def write_new(path: Path, data: bytes) -> None:
    no_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(data)
    except FileExistsError as exc:
        raise KBError(f"Refusing to overwrite: {path}") from exc


def write_json_new(path: Path, data: Any) -> None:
    write_new(path, json_bytes(data))


def atomic_json(path: Path, data: Any) -> None:
    no_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        write_new(temp, json_bytes(data))
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def identifier(value: str, label: str = "identifier") -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise KBError(f"Invalid {label}: {value!r}; use 1–64 lowercase letters, digits, '-' or '_'.")
    return value


def relative(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise KBError(f"Expected a nonempty POSIX relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ("", ".", "..") for p in value.split("/")):
        raise KBError(f"Path must be normalized, relative, and traversal-free: {value!r}")
    return path


def inside(root: Path, value: str) -> Path:
    p = root.joinpath(*relative(value).parts)
    no_symlinks(p)
    if not p.resolve().is_relative_to(root.resolve()):
        raise KBError(f"Path escapes root {root}: {value}")
    return p


# Keywords validate_schema implements. Anything else in a schema is a contract
# error, never a silently ignored constraint.
SCHEMA_KEYWORDS = frozenset({
    "$schema", "title", "description", "$comment",  # annotations only
    "type", "const", "enum", "anyOf", "properties", "required", "additionalProperties",
    "items", "minItems", "uniqueItems", "minLength", "maxLength", "pattern", "minimum", "maximum"})


def validate_schema(data: Any, schema: dict, at: str = "$") -> None:
    """Validate exactly the JSON Schema keyword subset used by this bundle.

    This is deliberately not advertised as a general JSON Schema implementation.
    Unsupported keywords raise KBError so a schema edit cannot be silently ignored.
    """
    if not isinstance(schema, dict):
        raise KBError(f"{at}: schema node must be an object")
    unknown = set(schema) - SCHEMA_KEYWORDS
    if unknown:
        raise KBError(f"{at}: unsupported schema keywords {sorted(unknown)}")
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                validate_schema(data, option, at)
                return
            except KBError:
                pass
        raise KBError(f"{at}: no allowed representation matched")
    if "const" in schema and data != schema["const"]:
        raise KBError(f"{at}: expected {schema['const']!r}")
    if "enum" in schema and data not in schema["enum"]:
        raise KBError(f"{at}: expected one of {schema['enum']}")
    if "type" in schema:
        kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        allowed = {"object": type(data) is dict, "array": type(data) is list,
                   "string": type(data) is str, "integer": type(data) is int,
                   "boolean": type(data) is bool, "null": data is None}
        if not any(allowed.get(k, False) for k in kinds):
            raise KBError(f"{at}: expected {kinds}, got {type(data).__name__}")
    if isinstance(data, dict):
        props = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(data)
        extra = set(data) - set(props)
        if missing:
            raise KBError(f"{at}: missing keys {sorted(missing)}")
        additional = schema.get("additionalProperties", True)
        if extra and additional is False:
            raise KBError(f"{at}: unknown keys {sorted(extra)}")
        for key, value in data.items():
            if key in props:
                validate_schema(value, props[key], f"{at}.{key}")
            elif isinstance(additional, dict):
                validate_schema(value, additional, f"{at}.{key}")
    elif isinstance(data, list):
        if len(data) < schema.get("minItems", 0):
            raise KBError(f"{at}: too few items")
        if schema.get("uniqueItems") and len({canonical(x) for x in data}) != len(data):
            raise KBError(f"{at}: duplicate items")
        for i, value in enumerate(data):
            if "items" in schema:
                validate_schema(value, schema["items"], f"{at}[{i}]")
    elif isinstance(data, str):
        if len(data) < schema.get("minLength", 0) or len(data) > schema.get("maxLength", 10**12):
            raise KBError(f"{at}: invalid string length")
        if "pattern" in schema and re.search(schema["pattern"], data) is None:
            raise KBError(f"{at}: does not match {schema['pattern']}")
    elif type(data) is int:
        if data < schema.get("minimum", -10**18) or data > schema.get("maximum", 10**18):
            raise KBError(f"{at}: out of range")


def contract(data: Any, name: str) -> None:
    """Validate against the current schema, or a frozen schemas/legacy/<name>-<version> one."""
    path = SCHEMAS / f"{name}.schema.json"
    version = data.get("schema_version") if isinstance(data, dict) else None
    if isinstance(version, str) and re.fullmatch(r"[0-9]+\.[0-9]+", version):
        legacy = SCHEMAS / "legacy" / f"{name}-{version}.schema.json"
        if legacy.is_file():
            path = legacy
    validate_schema(data, read_json(path))


def warning_summary(manifest: dict) -> dict:
    """Digest of every warning occurrence, so a review acknowledges volume, not just codes."""
    occurrences = sorted(([i["code"], i["source_id"], i["path"]] for i in manifest["issues"]
                          if i["severity"] == "warning"), key=lambda x: tuple(v or "" for v in x))
    counts: dict[str, int] = {}
    for code, _, _ in occurrences:
        counts[code] = counts.get(code, 0) + 1
    return {"sha256": json_sha(occurrences), "counts": dict(sorted(counts.items()))}


def check_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
    except (ValueError, AttributeError) as exc:
        raise KBError(f"Expected an ISO 8601 timestamp with timezone: {value!r}") from exc


def validate_pattern(pattern: str) -> None:
    relative(pattern)
    if any("**" in part and part != "**" for part in pattern.split("/")):
        raise KBError(f"'**' must occupy a whole segment: {pattern}")
    if "[" in pattern or "]" in pattern or pattern.startswith("!"):
        raise KBError(f"Use only literals, '*', '?', and whole-segment '**': {pattern}")


def matches(path: str, pattern: str) -> bool:
    """Case-sensitive, source-root anchored glob; ** means zero or more segments."""
    a, b = tuple(path.split("/")), tuple(pattern.split("/"))
    @lru_cache(maxsize=None)
    def match(i: int, j: int) -> bool:
        if j == len(b):
            return i == len(a)
        if b[j] == "**":
            return match(i, j + 1) or (i < len(a) and match(i + 1, j))
        return i < len(a) and fnmatch.fnmatchcase(a[i], b[j]) and match(i + 1, j + 1)
    return match(0, 0)


def excluded(path: str, patterns: list[str], directory: bool = False) -> bool:
    if any(matches(path, p) for p in patterns):
        return True
    # A directory pattern such as **/build/** excludes the directory itself.
    return directory and any(p.endswith("/**") and matches(path, p[:-3]) for p in patterns)


def load_project(path: Path) -> tuple[dict, Path, dict]:
    no_symlinks(path)
    path = path.resolve()
    if path.name != "project.json" or path.parent.name != "config":
        raise KBError("Project config must live at <project-root>/config/project.json")
    cfg = read_json(path)
    contract(cfg, "project")
    project = path.parent.parent
    outputs = {"knowledge": inside(project, cfg["knowledge"]["path"]),
               "approved": inside(project, cfg["knowledge"]["approved"]),
               "runs": inside(project, cfg["runs"]["path"])}
    if outputs["approved"] == outputs["knowledge"] or not outputs["approved"].is_relative_to(outputs["knowledge"]):
        raise KBError("knowledge.approved must be strictly within knowledge.path")
    reserved = project / "config"
    roots = [outputs["knowledge"], outputs["runs"], reserved]
    for i, a in enumerate(roots):
        for b in roots[i + 1:]:
            if a.is_relative_to(b) or b.is_relative_to(a):
                raise KBError("knowledge, runs, and config directories must not overlap")
    seen = set()
    source_roots = []
    for s in cfg["sources"]:
        if s["id"] in seen:
            raise KBError(f"Duplicate source id: {s['id']}")
        seen.add(s["id"])
        raw = Path(s["path"]).expanduser()
        raw = raw if raw.is_absolute() else project / raw
        if raw.is_symlink():
            raise KBError(f"Source root itself must not be a symlink: {raw}")
        resolved = raw.resolve()
        if resolved.is_relative_to(project) or project.is_relative_to(resolved):
            raise KBError(f"Source roots must be external to the project workspace: {resolved}")
        for prior in source_roots:
            if resolved.is_relative_to(prior) or prior.is_relative_to(resolved):
                raise KBError(f"Overlapping source roots: {resolved} and {prior}")
        source_roots.append(resolved)
        for p in s["include"] + s["exclude"]:
            validate_pattern(p)
    for p in cfg["global_exclude"]:
        validate_pattern(p)
    outputs["source_roots"] = dict(zip([s["id"] for s in cfg["sources"]], source_roots))
    return cfg, project, outputs


def load_source_scope(cfg: dict, project: Path, locations: dict) -> tuple[dict | None, list[dict], dict]:
    """Return the optional additive source registry and validated combined roots."""
    path = project / "config" / SOURCE_SCOPE_NAME
    if not path.exists() and not path.is_symlink():
        return None, list(cfg["sources"]), dict(locations["source_roots"])
    no_symlinks(path)
    scope = read_json(path)
    contract(scope, "source-scope")
    if scope["project_id"] != cfg["project"]["id"]:
        raise KBError("Source scope belongs to another project")
    roots = dict(locations["source_roots"])
    all_roots = list(roots.values())
    for source in scope["sources"]:
        sid = source["id"]
        if sid in roots:
            raise KBError(f"Duplicate source id across project and source scope: {sid}")
        raw = Path(source["path"]).expanduser()
        raw = raw if raw.is_absolute() else project / raw
        if raw.is_symlink():
            raise KBError(f"Source root itself must not be a symlink: {raw}")
        resolved = raw.resolve()
        if resolved.is_relative_to(project) or project.is_relative_to(resolved):
            raise KBError(f"Source roots must be external to the project workspace: {resolved}")
        for prior in all_roots:
            if resolved.is_relative_to(prior) or prior.is_relative_to(resolved):
                raise KBError(f"Overlapping source roots: {resolved} and {prior}")
        for pattern in source["include"] + source["exclude"]:
            validate_pattern(pattern)
        roots[sid] = resolved
        all_roots.append(resolved)
    return scope, list(cfg["sources"]) + list(scope["sources"]), roots


def representation_identity(kind: str, original_sha: str, text_sha: str,
                            adapter_version: str | None = None, parsers: dict | None = None,
                            options_sha: str | None = None, segments: list | None = None,
                            issues: list | None = None) -> str:
    """Bind quotable bytes and, for derived text, the frozen extraction inputs."""
    if kind == "source_text":
        return json_sha(["source_text-v1", original_sha])
    if kind == "derived_text":
        return json_sha(["derived_text-v1", original_sha, text_sha,
                        adapter_version, parsers, options_sha, segments, issues])
    raise KBError(f"Unknown representation kind: {kind}")


def evidence_identity(project_id: str, source_id: str, relative_path: str, content_sha: str,
                      representation_sha: str | None = None) -> tuple[str, str]:
    base = [project_id, source_id, relative_path]
    identity = base + [content_sha]
    if representation_sha is not None:
        identity.append(representation_sha)
    return "F-" + json_sha(base)[:24], "E-" + json_sha(identity)[:24]


def extraction_snapshot_paths(evidence_id: str, extension: str) -> dict:
    """Canonical artifact layout for one captured document (all run-relative).

    - original: frozen original binary bytes (never decoded as UTF-8)
    - text: derived UTF-8 evidence text readers quote against
    - metadata: extraction metadata JSON (contains the full segment map)
    The metadata sidecar's detached digest lives at metadata path + ".sha256".
    """
    if not evidence_id.startswith("E-"):
        raise KBError(f"Invalid evidence id: {evidence_id!r}")
    if extension not in DOCUMENT_EXTENSIONS and extension != ".csv":
        raise KBError(f"Unsupported document extension: {extension!r}")
    return {
        "original": f"snapshots/{evidence_id}.original{extension}",
        "text": f"snapshots/{evidence_id}.evidence.md",
        "metadata": f"snapshots/{evidence_id}.extraction.json",
    }


def run_cli(func: Callable[[], int]) -> None:
    try:
        code = func()
    except (KBError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        code = 2
    raise SystemExit(code)
