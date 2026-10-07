#!/usr/bin/env python3
"""Prepare a review, or explicitly publish a human-reviewed immutable knowledge release."""
import argparse
import json
import html
import os
import re
import shutil
import uuid
from pathlib import Path

from .kb_targeting import publication_eligible

from .kb_common import (KBError, atomic_json, check_timestamp, contract, identifier, inside,
                       json_sha, load_project, no_symlinks, read_json, read_stable, relative,
                       run_cli, sha, utc_now, warning_summary, write_json_new, write_new,
                       CLOCK_SKEW_SECONDS, parse_ts)
from datetime import datetime, timedelta, timezone
from .kb_check import check_run, load_manifest
from .kb_event_time import date_display_sort_key, event_date_label
from .kb_review_report import render_review_report

REVIEW_CHECKS = ("evidence_support", "conflicts_explicit", "source_authority_checked",
                 "privacy_checked", "snapshot_completeness_checked")
# Requirement/user-story codes indexed by by-code.md (e.g. RF-01, RNF-03, US00001).
CODE_PATTERN = re.compile(r"\b(?:RNF|RF|US|HU)-?[0-9]{1,6}\b")
WORK_FILE_LIMIT = 16 * 1024 * 1024
WORK_MAX_FILES = 2000
WORK_MAX_BYTES = 64 * 1024 * 1024


def current_release(approved: Path, project_id: str) -> tuple[str | None, set[str]]:
    run_id, records = current_release_records(approved, project_id)
    return run_id, {r["id"] for r in records["records"]} if records else set()


def current_release_records(approved: Path, project_id: str) -> tuple[str | None, dict | None]:
    path = approved / "CURRENT.json"
    if not path.exists():
        return None, None
    no_symlinks(path)
    current = read_json(path)
    required = {"schema_version", "project_id", "run_id", "records_sha256", "manifest_sha256", "review_sha256", "published_at"}
    if set(current) != required or current["schema_version"] != "0.1" or current["project_id"] != project_id:
        raise KBError("Invalid or cross-project CURRENT pointer")
    identifier(current["run_id"], "current run id")
    release = inside(approved, current["run_id"])
    for file, key in [("records.json", "records_sha256"), ("manifest.json", "manifest_sha256"), ("review.json", "review_sha256")]:
        if sha(read_stable(inside(release, file), 16 * 1024 * 1024)) != current[key]:
            raise KBError(f"Current release integrity failure: {file}")
    old_review = read_json(release / "review.json")
    contract(old_review, "review")
    if old_review["schema_version"] in {"0.3", "0.4"}:
        if sha(read_stable(inside(release, "review-report.md"), 16 * 1024 * 1024)) != old_review["review_report_sha256"]:
            raise KBError("Current release integrity failure: review-report.md")
        if work_digest(read_work(release)) != old_review["work_sha256"]:
            raise KBError("Current release integrity failure: work/ audit trail")
    if old_review["schema_version"] == "0.4":
        for filename, key in (("referrals.json", "referrals_sha256"),
                              ("work/mentions.json", "mentions_sha256"),
                              ("work/registry.snapshot.json", "registry_sha256")):
            raw = read_stable(inside(release, filename), 16 * 1024 * 1024)
            digest = json_sha(read_json(inside(release, filename))) if filename.endswith("registry.snapshot.json") else sha(raw)
            if digest != old_review[key]:
                raise KBError(f"Current release integrity failure: {filename}")
        expected_outbox = render_outbox(read_json(inside(release, "manifest.json")),
                                        read_json(inside(release, "referrals.json")))
        if read_stable(inside(release, "outbox.md"), 16 * 1024 * 1024) != expected_outbox:
            raise KBError("Current release integrity failure: outbox.md")
    old = read_json(release / "records.json")
    if old["project_id"] != project_id or old["run_id"] != current["run_id"]:
        raise KBError("Current release identity mismatch")
    return current["run_id"], old


def prepare_review(config: Path, run: Path) -> dict:
    cfg, _, locations = load_project(config)
    m = load_manifest(run)
    publication_eligible(m)
    records_path = run / "proposals" / "records.json"
    check = check_run(run, records_path, stage2=True)
    validate_location(cfg, locations, m, run)
    previous_id, previous_data = current_release_records(locations["approved"], m["project_id"])
    previous_records = {r["id"] for r in previous_data["records"]} if previous_data else set()
    prior = None
    if previous_data is not None:
        prior_root = inside(locations["approved"], previous_id)
        check_run(prior_root, prior_root / "records.json", stage2=True, historical=True)
        prior = (prior_root, previous_data, read_json(prior_root / "manifest.json"))
    records = read_json(records_path)
    ids = {r["id"] for r in records["records"]}
    manifest_hash = sha(read_stable(run / "manifest.json", 16 * 1024 * 1024))
    records_hash = sha(read_stable(records_path, 16 * 1024 * 1024))
    work_hash = work_digest(read_work(run))
    routing = records["schema_version"] in {"0.5", "0.6"}
    referrals_raw = read_stable(inside(run, "proposals/referrals.json"), 16 * 1024 * 1024) if routing else None
    mentions_raw = read_stable(inside(run, "work/mentions.json"), 16 * 1024 * 1024) if routing else None
    registry_digest = json_sha(read_json(inside(run, "work/registry.snapshot.json"))) if routing else None
    report_bytes = render_review_report(run, m, records, check, prior)
    if len(report_bytes) > 16 * 1024 * 1024:
        raise KBError("Generated review report exceeds 16 MiB; narrow the review scope")
    if sha(read_stable(run / "manifest.json", 16 * 1024 * 1024)) != manifest_hash \
            or sha(read_stable(records_path, 16 * 1024 * 1024)) != records_hash \
            or work_digest(read_work(run)) != work_hash \
            or (routing and sha(read_stable(inside(run, "proposals/referrals.json"), 16 * 1024 * 1024)) != sha(referrals_raw)):
        raise KBError("Manifest, records, referrals, or work changed during review preparation; retry on stable inputs")
    report_path = run / "review-report.md"
    no_symlinks(report_path)
    if report_path.exists():
        if read_stable(report_path, 16 * 1024 * 1024) != report_bytes:
            raise KBError("Existing review report is stale; use a fresh run/review preparation")
    else:
        write_new(report_path, report_bytes)
    return {"schema_version": "0.4" if routing else "0.3", "project_id": m["project_id"], "run_id": m["run_id"],
            "decision": "changes_requested", "reviewer": "", "reviewed_at": None, "prepared_at": utc_now(),
            "manifest_sha256": manifest_hash,
            "records_sha256": records_hash,
            "review_report_sha256": sha(report_bytes),
            "work_sha256": work_hash,
            "previous_release_id": previous_id, "approved_record_ids": sorted(ids),
            "removed_record_ids": sorted(previous_records - ids),
            "warning_summary": warning_summary(m),
            "acknowledged_warnings": {},
            "triaged_evidence_ids": triaged_ids(records),
            "triaged_segment_ids": triaged_segment_ids(records),
            "triage_acknowledged": False,
            "segment_triage_acknowledged": False,
            "checks": {k: False for k in REVIEW_CHECKS + (("cross_project_checked",) if routing else ())},
            **({"referrals_sha256": sha(referrals_raw), "mentions_sha256": sha(mentions_raw),
                "registry_sha256": registry_digest} if routing else {}),
            "notes": "Human review required. Do not ask an agent to complete or approve this review."}


def triaged_ids(records: dict) -> list[str]:
    return sorted(c["evidence_id"] for c in records["coverage"] if c["disposition"] == "triaged_out")


def triaged_segment_ids(records: dict) -> list[str]:
    return sorted({c["segment_id"] for c in [*records.get("segment_coverage", []),
                                            *records.get("interval_coverage", [])]
                   if c["disposition"] == "triaged_out"})


def validate_location(cfg: dict, locations: dict, m: dict, run: Path) -> None:
    if cfg["project"]["id"] != m["project_id"] or json_sha(cfg) != m["config_sha256"]:
        raise KBError("Live project configuration differs from the run; create a new inventory")
    if run.resolve() != (locations["runs"] / m["run_id"]).resolve():
        raise KBError("Run directory is not at the configured project's runs/<run_id> location")


def md(text: str) -> str:
    text = html.escape(text, quote=False)
    for char in ("\\", "`", "[", "]", "*", "_", "|"):
        text = text.replace(char, "\\" + char)
    return text


def mermaid_label(text: str) -> str:
    replacements = {'"': "#quot;", "&": "#38;", "<": "#60;", ">": "#62;", "#": "#35;",
                    "\\": "#92;", "`": "#96;", "\n": " ", "\r": " "}
    return "".join(replacements.get(c, c) for c in text)


def render_views(release: Path, records: dict, m: dict, previous: tuple[dict, dict] | None = None) -> None:
    """Derived Markdown views of an approved release; records.json stays the source of truth.

    previous is the prior release's (records, manifest), used for changes-since-<run>.md.
    """
    ordered = sorted(records["records"], key=lambda r: r["id"])
    fmap = {f["evidence_id"]: f for f in m["files"]}
    nodes = {r["id"]: f"r{i}" for i, r in enumerate(ordered)}
    graph = ["flowchart LR"]
    counts = {d: 0 for d in ("used", "reviewed_no_record", "triaged_out", "deferred")}
    for c in records["coverage"]:
        counts[c["disposition"]] += 1
    links = ["[Review](review.json)", "[Structured records](records.json)", "[Evidence manifest](manifest.json)",
             "[Project map](project-map.md)", "[Open questions](open-questions.md)", "[By code](by-code.md)"]
    if (release / "review-report.md").is_file():
        links.append("[Review report](review-report.md)")
    if records["schema_version"] in {"0.4", "0.5", "0.6"}:
        links.append("[Timeline](timeline.md)")
    if records["schema_version"] in {"0.5", "0.6"}:
        links.append("[Pending referral outbox](outbox.md)")
    if previous is not None:
        links.append(f"[Changes since {md(previous[0]['run_id'])}](changes-since-{previous[0]['run_id']}.md)")
    index = [f"# {md(m['project_id'])} — approved knowledge snapshot", "",
             f"Run: `{m['run_id']}`. Approval concerns the reviewed knowledge snapshot; it does not itself approve a business requirement or decision.", "",
             " · ".join(links), "",
             f"Coverage of {len(records['coverage'])} inputs: {counts['used']} used, {counts['reviewed_no_record']} "
             f"read in full without a record, {counts['triaged_out']} triaged out (not read in full)"
             + (f", {counts['deferred']} deferred" if counts["deferred"] else "") + ".", ""]
    triage = sorted({c["method"] for c in records["coverage"] if c["disposition"] == "triaged_out"})
    if triage:
        index += ["Triage methods: " + "; ".join(f"`{md(x)}`" for x in triage), ""]
    index += ["| Record | Kind | Epistemic status |", "| --- | --- | --- |"]
    for r in ordered:
        rid = r["id"]
        graph.append(f'  {nodes[rid]}["{mermaid_label(rid + ": " + r["title"])}"]')
        index.append(f"| [{rid} — {md(r['title'])}](records/{rid}.md) | {r['kind']} | {r['epistemic_status']} |")
        body = [f"# {rid} — {md(r['title'])}", "", f"Kind: {r['kind']} · Epistemic status: {r['epistemic_status']}", "", md(r["statement"]), "", "## Evidence", ""]
        def show_evidence(ev: dict) -> None:
            f = fmap[ev["evidence_id"]]
            body.append(f"[{ev['evidence_id']}](../{f['snapshot_path']}) — {md(f['source_id'] + '/' + f['relative_path'])}, lines {ev['start_line']}–{ev['end_line']}.")
            if "document" in f:
                body.append(f"[Original artifact](../{f['document']['original_snapshot_path']}) — {f['document']['media_type']}, extraction status {f['document']['status']}.")
            body.extend("> " + md(line) for line in ev["quote"].split("\n"))
            body.append("")
        for ev in r["evidence"]:
            show_evidence(ev)
        if records["schema_version"] in {"0.4", "0.5", "0.6"} and r["events"]:
            body += ["## Events", ""]
            for event in r["events"]:
                body += [f"### {event['id']}", "", md(event["statement"]), "",
                         "Event date: " + md(event_date_label(event["event_date"])),
                         "Supporting citations: " + ", ".join(
                             f"{i + 1} ({r['evidence'][i]['evidence_id']}, "
                             f"lines {r['evidence'][i]['start_line']}–{r['evidence'][i]['end_line']})"
                             for i in event["evidence_refs"]), ""]
                if "effective_date" in event:
                    body += ["Effective date: " + md(event_date_label(event["effective_date"])), ""]
        if r["relations"]:
            body += ["## Relations", ""]
            for edge in r["relations"]:
                body.append(f"{edge['type']}: [{edge['target']}]({edge['target']}.md)")
                graph.append(f"  {nodes[rid]} -->|{edge['type']}| {nodes[edge['target']]}")
        if r["open_questions"]:
            body += ["", "## Open questions", ""] + [md(x) for x in r["open_questions"]]
        inv = r["investigation"]
        if inv is not None:
            body += ["", "## Bounded investigation", "", "**Question:** " + md(inv["question"]), "",
                     "**Scope:** " + ", ".join(f"`{x}`" for x in inv["scope"]), "",
                     "**Method:** " + md(inv["method"]), "", "### Findings", ""]
            for finding in inv["findings"]:
                body += [md(finding["claim"]), ""]
                for ev in finding["evidence"]:
                    show_evidence(ev)
            body += ["### Limitations", ""] + [md(x) for x in inv["limitations"]]
            body += ["", "**Next action:** " + md(inv["next_action"])]
        write_new(release / "records" / f"{rid}.md", ("\n".join(body) + "\n").encode("utf-8"))
    write_new(release / "index.md", ("\n".join(index) + "\n").encode("utf-8"))
    write_new(release / "project-map.mmd", ("\n".join(graph) + "\n").encode("utf-8"))
    write_new(release / "project-map.md", ("# Project map\n\nDerived from records.json; edit records and regenerate, not this view.\n\n```mermaid\n" + "\n".join(graph) + "\n```\n").encode("utf-8"))
    write_new(release / "open-questions.md", open_questions_view(ordered, m))
    write_new(release / "by-code.md", by_code_view(ordered, m))
    if records["schema_version"] in {"0.4", "0.5", "0.6"}:
        write_new(release / "timeline.md", timeline_view(records, m))
    if previous is not None:
        write_new(release / f"changes-since-{previous[0]['run_id']}.md", changes_view(records, m, *previous))


def _timeline_cell(value: str) -> str:
    """Keep source-authored text inside one Markdown list item."""
    return md(" ".join(value.split()))


def timeline_view(records: dict, m: dict) -> bytes:
    """Render reviewed event metadata without inferring precedence or active state."""
    files = {f["evidence_id"]: f for f in m["files"]}
    groups = {"dated": [], "unknown": [], "conflicting": []}
    for record in records["records"]:
        for event in record["events"]:
            when = event["event_date"]
            category = "dated" if when["status"] in {"known", "approximate"} else when["status"]
            categories = sorted({files[record["evidence"][i]["evidence_id"]]["source_type"]
                                 for i in event["evidence_refs"]})
            row = (f"- **{_timeline_cell(event_date_label(when))}** · "
                   f"[{event['id']}](records/{record['id']}.md#{event['id'].lower()}) — "
                   f"{_timeline_cell(event['statement'])} · [{record['id']}](records/{record['id']}.md) "
                   f"({md(', '.join(categories))})")
            if "effective_date" in event:
                row += "; effective: " + _timeline_cell(event_date_label(event["effective_date"]))
            key = date_display_sort_key(when["value"], when["precision"]) if category == "dated" else ""
            groups[category].append((key, event["id"], record["id"], row))
    out = [f"# Event timeline — {md(m['project_id'])} / `{m['run_id']}`", "",
           "Derived from reviewed records 0.4. Event dates describe business events; document dates and "
           "capture order do not set them. This view does not establish authority, supersession, or active state.", "",
           "Dated rows use the earliest stated calendar point as a display key. Date-only values are not "
           "midnight instants; approximate dates, ranges, and overlaps do not establish a strict order.", ""]
    for key, title in (("dated", "Dated events"), ("unknown", "Unknown dates"),
                       ("conflicting", "Conflicting dates")):
        rows = [row for _, _, _, row in sorted(groups[key])]
        out += [f"## {title} ({len(rows)})", ""] + (rows or ["None."]) + [""]
    return ("\n".join(out) + "\n").encode("utf-8")


def open_questions_view(ordered: list[dict], m: dict) -> bytes:
    out = [f"# Open questions — {md(m['project_id'])} / `{m['run_id']}`", "",
           "Every uncertainty record and every open question attached to any record. Records carry no "
           "owner field, so owners are shown as unknown until a person assigns one.", "",
           "| Record | Kind | Question | Owner |", "| --- | --- | --- | --- |"]
    for r in ordered:
        questions = list(r["open_questions"])
        if r["kind"] == "uncertainty" and not questions:
            questions = [r["statement"]]
        for q in questions:
            cell = md(" ".join(q.split()))
            out.append(f"| [{r['id']}](records/{r['id']}.md) | {r['kind']} | {cell} | unknown |")
    if len(out) == 6:
        out.append("| — | — | No open questions recorded. | — |")
    return ("\n".join(out) + "\n").encode("utf-8")


def by_code_view(ordered: list[dict], m: dict) -> bytes:
    index: dict[str, set[str]] = {}
    for r in ordered:
        texts = [r["title"], r["statement"], *r["open_questions"]] + [ev["quote"] for ev in r["evidence"]]
        if r["investigation"] is not None:
            texts += [f["claim"] for f in r["investigation"]["findings"]]
            texts += [ev["quote"] for f in r["investigation"]["findings"] for ev in f["evidence"]]
        for text in texts:
            for code in CODE_PATTERN.findall(text):
                index.setdefault(code, set()).add(r["id"])
    out = [f"# Records by requirement code — {md(m['project_id'])} / `{m['run_id']}`", "",
           "Codes found literally in record text or quotes. A code that is absent here may still be covered under another name.", "",
           "| Code | Records |", "| --- | --- |"]
    for code in sorted(index):
        out.append(f"| {code} | " + ", ".join(f"[{x}](records/{x}.md)" for x in sorted(index[code])) + " |")
    if not index:
        out.append("| — | No requirement codes found. |")
    return ("\n".join(out) + "\n").encode("utf-8")


def _citation_keys(record: dict, files: dict) -> tuple[set, set]:
    """(logical_id, quote) pairs and (evidence_id, start, end) positions of every citation."""
    cites = list(record["evidence"])
    if record["investigation"] is not None:
        cites += [ev for f in record["investigation"]["findings"] for ev in f["evidence"]]
    return ({(files[ev["evidence_id"]]["logical_id"], ev["quote"]) for ev in cites},
            {(ev["evidence_id"], ev["start_line"], ev["end_line"]) for ev in cites})


def changes_view(records: dict, m: dict, old_records: dict, old_manifest: dict) -> bytes:
    new = {r["id"]: r for r in records["records"]}
    old = {r["id"]: r for r in old_records["records"]}
    nf = {f["evidence_id"]: f for f in m["files"]}
    of = {f["evidence_id"]: f for f in old_manifest["files"]}
    fields = ("kind", "title", "statement", "epistemic_status", "relations", "open_questions", "events")
    out = [f"# Changes since `{old_records['run_id']}` — {md(m['project_id'])}", "",
           f"Compares approved release `{m['run_id']}` with the previous approved release. Evidence is "
           "compared by logical file and exact quote, so a quote that only moved lines is reported as moved.", ""]
    def section(title: str, rows: list[str]) -> None:
        out.extend([f"## {title} ({len(rows)})", ""] + (rows or ["None."]) + [""])
    section("Added records", [f"- [{x}](records/{x}.md) — {md(new[x]['title'])}" for x in sorted(set(new) - set(old))])
    section("Removed records", [f"- {x} — {md(old[x]['title'])}" for x in sorted(set(old) - set(new))])
    changed, moved, evidence = [], [], []
    for rid in sorted(set(new) & set(old)):
        diff = [k for k in fields if new[rid].get(k) != old[rid].get(k)]
        if new[rid]["investigation"] is not None or old[rid]["investigation"] is not None:
            strip = lambda inv: None if inv is None else {k: v for k, v in inv.items() if k not in ("findings", "scope")}
            if strip(new[rid]["investigation"]) != strip(old[rid]["investigation"]):
                diff.append("investigation")
        if diff:
            changed.append(f"- [{rid}](records/{rid}.md) — changed: {', '.join(diff)}")
        new_quotes, new_pos = _citation_keys(new[rid], nf)
        old_quotes, old_pos = _citation_keys(old[rid], of)
        if new_quotes != old_quotes:
            evidence.append(f"- [{rid}](records/{rid}.md) — {len(new_quotes - old_quotes)} quote(s) added, "
                            f"{len(old_quotes - new_quotes)} removed")
        elif {(p[1], p[2]) for p in new_pos} != {(p[1], p[2]) for p in old_pos}:
            moved.append(f"- [{rid}](records/{rid}.md) — same quotes at different lines")
    section("Changed records", changed)
    section("Records whose cited evidence changed", evidence)
    section("Records whose evidence only moved", moved)
    return ("\n".join(out) + "\n").encode("utf-8")


def read_work(run: Path) -> list[tuple[str, bytes]]:
    """Validated (run-relative path, bytes) of every file in the run's work/ folder."""
    work = run / "work"
    no_symlinks(work)
    if not work.exists():
        return []
    if not work.is_dir():
        raise KBError(f"Run work path is not a directory: {work}")
    entries, total = [], 0
    for directory, dirs, files in os.walk(work, followlinks=False):
        base = Path(directory)
        for name in sorted(dirs + files):
            if (base / name).is_symlink():
                raise KBError(f"Symlink not permitted in run work folder: {base / name}")
        dirs.sort()
        for name in sorted(files):
            if name == ".DS_Store":
                continue
            rel = (base / name).relative_to(run).as_posix()
            try:
                relative(rel)
            except KBError as exc:
                raise KBError(f"Rename this work file; release paths must be plain POSIX names: {rel}") from exc
            data = read_stable(base / name, WORK_FILE_LIMIT)
            total += len(data)
            entries.append((rel, data))
            if len(entries) > WORK_MAX_FILES or total > WORK_MAX_BYTES:
                raise KBError(f"Run work folder exceeds {WORK_MAX_FILES} files or {WORK_MAX_BYTES} bytes; "
                              "keep only the audit material that explains the records")
    return sorted(entries)


def work_digest(entries: list[tuple[str, bytes]]) -> str:
    return json_sha([[rel, sha(data), len(data)] for rel, data in entries])


def render_outbox(manifest: dict, routing: dict) -> bytes:
    """Render only reviewed origin-release referrals; target intake is separate."""
    files = {f["evidence_id"]: f for f in manifest["files"]}
    out = [f"# Pending referral outbox — {md(manifest['project_id'])} / {md(manifest['run_id'])}", "",
           "These are reviewed origin-project referrals, not target acceptance or approved target facts. "
           "The target must apply its own access controls, capture, evidence, review, and publication. "
           "The source-path hint does not authorize copying an entire mixed file; obtain a scoped export when needed.", ""]
    groups: dict[str, list[dict]] = {}
    for referral in routing["referrals"]:
        groups.setdefault(referral["target_project_id"], []).append(referral)
    for target, items in sorted(groups.items()):
        out += [f"## Target: {md(target)}", ""]
        for item in sorted(items, key=lambda r: r["id"]):
            source = item["source"]
            f = files[source["evidence_id"]]
            out += [f"### {item['id']} · {item['class']}", "",
                    f"**Status:** pending target review. **Origin release:** `{manifest['run_id']}`. "
                    f"**Source:** {md(f['source_id'] + '/' + f['relative_path'])}, "
                    f"[frozen representation]({f['snapshot_path']}) lines "
                    f"{source['start_line']}–{source['end_line']}, segment `{source['segment_id']}`.", "",
                    f"**Proposed summary:** {md(item['summary'])}", "",
                    f"**Why target may care:** {md(item['why_target_cares'])}", "",
                    f"**Related home records:** {', '.join(item['home_record_ids']) or 'none'}.", "",
                    f"**Suggested source-path hint:** {md(item['suggested_capture']['source_id'] + '/' + item['suggested_capture']['relative_path'])}.", "",
                    "Exact origin quote:", "<pre>" + html.escape(source["quote"], quote=False) + "</pre>", ""]
    if not groups:
        out += ["No referrals; all scanned mentions still have explicit reviewed assessments.", ""]
    return ("\n".join(out) + "\n").encode("utf-8")


def publish(config: Path, run: Path, review_path: Path, human_approved: bool = False) -> Path:
    if not human_approved:
        raise KBError("Publication requires explicit --human-approved after a real human review")
    cfg, _, locations = load_project(config)
    m = load_manifest(run)
    publication_eligible(m)
    records_path = run / "proposals" / "records.json"
    report = check_run(run, records_path, stage2=True)
    validate_location(cfg, locations, m, run)
    records_raw = read_stable(records_path, 16 * 1024 * 1024)
    routing = read_json(records_path)["schema_version"] in {"0.5", "0.6"}
    referrals_path = inside(run, "proposals/referrals.json") if routing else None
    referrals_raw = read_stable(referrals_path, 16 * 1024 * 1024) if routing else None
    no_symlinks(review_path)
    review_raw = read_stable(review_path, 16 * 1024 * 1024)
    review = read_json(review_path)
    contract(review, "review")
    if review["schema_version"] != ("0.4" if routing else "0.3"):
        raise KBError("Review version predates or mismatches the report-bound routing contract; prepare again")
    if review["decision"] != "approve" or not review["reviewer"].strip() or review["reviewed_at"] is None:
        raise KBError("Review must name a human reviewer, timestamp, and explicit approve decision")
    reviewed = parse_ts(review["reviewed_at"])
    floor = parse_ts(review.get("prepared_at") or m["created_at"])
    if reviewed < floor or reviewed < parse_ts(m["created_at"]):
        raise KBError("reviewed_at precedes the capture or the review preparation; record the real review time")
    if reviewed > datetime.now(timezone.utc) + timedelta(seconds=CLOCK_SKEW_SECONDS):
        raise KBError("reviewed_at is in the future")
    if review["project_id"] != m["project_id"] or review["run_id"] != m["run_id"]:
        raise KBError("Review belongs to a different project/run")
    manifest_raw = read_stable(run / "manifest.json", 16 * 1024 * 1024)
    if review["manifest_sha256"] != sha(manifest_raw) or review["records_sha256"] != sha(records_raw):
        raise KBError("Review is stale: the manifest or records changed after review preparation")
    if routing:
        if review["referrals_sha256"] != sha(referrals_raw) \
                or review["mentions_sha256"] != sha(read_stable(inside(run, "work/mentions.json"), 16 * 1024 * 1024)) \
                or review["registry_sha256"] != json_sha(read_json(inside(run, "work/registry.snapshot.json"))):
            raise KBError("Review is stale: referral or routing inputs changed after preparation")
    report_path = run / "review-report.md"
    no_symlinks(report_path)
    if not report_path.is_file():
        raise KBError("Missing review report; prepare and review again")
    report_raw = read_stable(report_path, 16 * 1024 * 1024)
    if review["review_report_sha256"] != sha(report_raw):
        raise KBError("Review report changed after preparation; prepare and review again")
    if not all(review["checks"].values()):
        raise KBError("All human review checks must be completed")
    records = read_json(records_path)
    ids = {r["id"] for r in records["records"]}
    if set(review["approved_record_ids"]) != ids:
        raise KBError("Review must approve the exact complete record set, not a subset")
    summary = warning_summary(m)
    if review["warning_summary"] != summary:
        raise KBError("Review warning summary does not match this manifest's warning occurrences; prepare again")
    if review["acknowledged_warnings"] != summary["counts"]:
        raise KBError(f"Review must acknowledge every warning occurrence by code and count: {summary['counts']}")
    work = read_work(run)
    if review["work_sha256"] != work_digest(work):
        raise KBError("Run work/ folder changed after review preparation; prepare and review again")
    triaged = triaged_ids(records)
    if review["triaged_evidence_ids"] != triaged:
        raise KBError("Review triage list does not match the records' triaged_out coverage; prepare again")
    if triaged and review["triage_acknowledged"] is not True:
        raise KBError(f"Review must set triage_acknowledged: {len(triaged)} inputs were triaged out, not read in full")
    segments_triaged = triaged_segment_ids(records)
    if review["triaged_segment_ids"] != segments_triaged:
        raise KBError("Review segment triage list does not match the records; prepare again")
    if segments_triaged and review["segment_triage_acknowledged"] is not True:
        raise KBError(f"Review must set segment_triage_acknowledged: {len(segments_triaged)} segments were triaged out")
    approved = locations["approved"]
    approved.mkdir(parents=True, exist_ok=True)
    lock = approved / ".publish.lock"
    write_json_new(lock, {"run_id": m["run_id"], "created_at": utc_now()})
    tmp = approved / f".{m['run_id']}.{uuid.uuid4().hex}.tmp"
    destination = approved / m["run_id"]
    try:
        current_id, prior = current_release_records(approved, m["project_id"])
        prior_ids = {r["id"] for r in prior["records"]} if prior else set()
        if review["previous_release_id"] != current_id:
            raise KBError("CURRENT changed since review preparation; prepare and review again")
        prior_context = None
        if prior is not None:
            prior_root = inside(approved, current_id)
            check_run(prior_root, prior_root / "records.json", stage2=True, historical=True)
            prior_context = (prior_root, prior, read_json(prior_root / "manifest.json"))
        if routing:
            check_run(run, records_path, stage2=True)
        if render_review_report(run, m, records, report, prior_context) != report_raw:
            raise KBError("Review report no longer matches the checked evidence; prepare and review again")
        if set(review["removed_record_ids"]) != prior_ids - ids:
            raise KBError("Removed record acknowledgement does not match the current release")
        if destination.exists():
            raise KBError("Release already exists; immutable releases are never overwritten")
        if current_id is not None:
            cur_m = read_json(inside(approved, current_id) / "manifest.json")
            older = (m.get("sequence", 0), parse_ts(m["created_at"])) < (cur_m.get("sequence", 0), parse_ts(cur_m["created_at"]))
            if older and not review.get("rollback_reason"):
                raise KBError(f"This run was captured before CURRENT ({current_id}); publishing it would roll "
                              "knowledge back in time. Set review.rollback_reason to do so deliberately")
        tmp.mkdir()
        # Byte-preserving copies: verification runs again against the completed release.
        write_new(tmp / "manifest.json", manifest_raw)
        write_new(tmp / "manifest.sha256", (sha(manifest_raw) + "\n").encode())
        write_new(tmp / "project.snapshot.json", read_stable(run / "project.snapshot.json", 16 * 1024 * 1024))
        if "targeted" in m:
            write_new(tmp / "run-request.snapshot.json", read_stable(run / "run-request.snapshot.json", 16 * 1024 * 1024))
        if "source_scope" in m:
            scope_path = m["source_scope"]["path"]
            write_new(tmp / scope_path, read_stable(inside(run, scope_path), 16 * 1024 * 1024))
        if "segment_inventory" in m:
            segment_path = m["segment_inventory"]["path"]
            write_new(tmp / segment_path, read_stable(inside(run, segment_path), 64 * 1024 * 1024))
        for f in m["files"]:
            write_new(tmp / f["snapshot_path"], read_stable(inside(run, f["snapshot_path"]), m["limits"]["max_file_bytes"]))
            if "document" in f:
                # Releases carry all three document artifacts plus the sidecar seal,
                # so check_run() against the completed release verifies them again.
                doc = f["document"]
                write_new(tmp / doc["original_snapshot_path"],
                          read_stable(inside(run, doc["original_snapshot_path"]), m["limits"]["max_file_bytes"]))
                write_new(tmp / doc["metadata_snapshot_path"],
                          read_stable(inside(run, doc["metadata_snapshot_path"]), m["limits"]["max_file_bytes"]))
                write_new(tmp / (doc["metadata_snapshot_path"] + ".sha256"),
                          read_stable(inside(run, doc["metadata_snapshot_path"] + ".sha256"), 256))
        write_new(tmp / "records.json", records_raw)
        if routing:
            write_new(tmp / "referrals.json", referrals_raw)
        write_new(tmp / "review.json", review_raw)
        write_new(tmp / "review-report.md", report_raw)
        # The exact bytes hashed above are written, so the release carries the reviewed audit trail.
        for rel, data in work:
            write_new(inside(tmp, rel), data)
        check_run(tmp, tmp / "records.json", stage2=True, historical=True)
        write_json_new(tmp / "validation.json", report)
        if routing:
            outbox_bytes = render_outbox(m, read_json(tmp / "referrals.json"))
            if len(outbox_bytes) > 16 * 1024 * 1024:
                raise KBError("Referral outbox exceeds 16 MiB; narrow the routed review scope")
            write_new(tmp / "outbox.md", outbox_bytes)
        previous = None
        if prior is not None:
            previous = (prior, read_json(inside(approved, current_id) / "manifest.json"))
        render_views(tmp, records, m, previous)
        # Detect edits during publication before advancing the current pointer.
        if sha(read_stable(records_path, 16 * 1024 * 1024)) != sha(records_raw) or sha(read_stable(review_path, 16 * 1024 * 1024)) != sha(review_raw) \
                or sha(read_stable(report_path, 16 * 1024 * 1024)) != sha(report_raw) \
                or work_digest(read_work(run)) != review["work_sha256"] \
                or (routing and sha(read_stable(referrals_path, 16 * 1024 * 1024)) != sha(referrals_raw)):
            raise KBError("Records/review/report/work changed during publication; retry after stabilizing files")
        from .kb_context import check_context
        check_context(run,m,config)
        tmp.rename(destination)
        history = approved / "HISTORY.jsonl"
        entry = {"published_at": utc_now(), "run_id": m["run_id"], "sequence": m.get("sequence"),
                 "captured_at": m["created_at"], "previous_release_id": current_id,
                 "reviewer": review["reviewer"], "reviewed_at": review["reviewed_at"],
                 "rollback_reason": review.get("rollback_reason")}
        with history.open("a", encoding="utf-8") as handle:  # append-only publication log
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        atomic_json(approved / "CURRENT.json", {"schema_version": "0.1", "project_id": m["project_id"],
                    "run_id": m["run_id"], "records_sha256": sha(records_raw),
                    "manifest_sha256": sha(manifest_raw), "review_sha256": sha(review_raw), "published_at": utc_now()})
        return destination
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        lock.unlink(missing_ok=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--prepare", action="store_true", help="Create review.pending.json with all approval checks false")
    p.add_argument("--review", type=Path)
    p.add_argument("--human-approved", action="store_true")
    a = p.parse_args()
    if a.prepare:
        if a.review or a.human_approved:
            raise KBError("--prepare cannot be combined with publication flags")
        review = prepare_review(a.project, a.run)
        path = a.run / "review.pending.json"
        write_json_new(path, review)
        print(f"Prepared {path} and {a.run / 'review-report.md'}. A human must review and save an explicit approval as review.json.")
        print("Warnings to acknowledge by count in acknowledged_warnings:")
        for code, count in review["warning_summary"]["counts"].items():
            print(f"  {count:>5} × {code}")
        if review["triaged_evidence_ids"]:
            print(f"Triaged out (not read in full): {len(review['triaged_evidence_ids'])} inputs; "
                  "set triage_acknowledged only if that is acceptable.")
        if review["triaged_segment_ids"]:
            print(f"Triaged out (not read in full): {len(review['triaged_segment_ids'])} segments; "
                  "set segment_triage_acknowledged only if that is acceptable.")
        hints = check_run(a.run, a.run / "proposals" / "records.json", stage2=True)["semantic_hints"]
        if hints:
            print("Reviewer hints (not gates):")
            for h in hints:
                print(f"  - {h['record_id'] or '(run)'}: {h['code']} — {h['detail']}")
    else:
        if not a.review:
            raise KBError("Specify --prepare, or --review with --human-approved")
        print(publish(a.project, a.run, a.review, a.human_approved))
    return 0


if __name__ == "__main__":
    run_cli(main)
