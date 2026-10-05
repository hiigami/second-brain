"""Deterministic, unapproved human-review aid from checked frozen evidence."""
import html
from pathlib import Path

from .kb_check import load_segment_inventory
from .kb_common import inside, read_json, read_stable
from .kb_event_time import event_date_label


def _inline(value: object) -> str:
    text = html.escape(" ".join(str(value).split()), quote=False)
    for char in ("\\", "`", "[", "]", "*", "_", "|"):
        text = text.replace(char, "\\" + char)
    return text


def _pre(value: str) -> str:
    return "<pre>\n" + html.escape(value, quote=False) + "\n</pre>"


def _evidence_link(report_run: Path, root: Path, path: str) -> str:
    # Current evidence travels with the byte-identical report. Prior evidence
    # stays in its release, so its link must survive the report's relocation.
    root = root.resolve()
    target = inside(root, path)
    if root == report_run.resolve():
        return target.relative_to(root).as_posix()
    return target.as_uri()


def _citation(report_run: Path, root: Path, manifest: dict, files: dict, segments: dict,
              citation: dict) -> list[str]:
    f = files[citation["evidence_id"]]
    start, end = citation["start_line"], citation["end_line"]
    lines = read_stable(inside(root, f["snapshot_path"]), manifest["limits"]["max_file_bytes"]).decode("utf-8-sig").splitlines()
    context = "\n".join(
        f"L{i:06d}{' [cited]' if start <= i <= end else '        '} | {lines[i - 1]}"
        for i in range(max(1, start - 2), min(len(lines), end + 2) + 1))
    snapshot_link = _evidence_link(report_run, root, f["snapshot_path"])
    out = [f"- **Source:** {_inline(f['source_id'])} ({_inline(f['source_type'])}) / "
           f"{_inline(f['relative_path'])}; `{f['evidence_id']}`, lines {start}–{end}. "
           f"[Frozen representation]({snapshot_link})."]
    if "segment_id" in citation:
        segment = segments[citation["segment_id"]]
        out.append(f"  Segment `{citation['segment_id']}`; original locator: "
                   f"{_inline(segment['original_locator'])}; extraction status: {segment['extraction_status']}.")
    if "document" in f:
        original_link = _evidence_link(report_run, root, f["document"]["original_snapshot_path"])
        out.append(f"  [Original artifact]({original_link}); "
                   f"extraction status: {_inline(f['document']['status'])}.")
    out += ["  Exact quote:", _pre(citation["quote"]), "  Context (two lines on either side where available):",
            _pre(context), ""]
    return out


def _record_summary(record: dict | None) -> str:
    if record is None:
        return "Absent from this complete snapshot."
    events = ", ".join(
        f"{e['id']}: {e['statement']}; event {event_date_label(e['event_date'])}"
        + (f"; effective {event_date_label(e['effective_date'])}"
           if "effective_date" in e else "")
        for e in record.get("events", [])) or "none"
    return (f"{record['kind']} / {record['epistemic_status']}: {record['statement']} "
            f"Events: {events}.")


def _events(record: dict) -> list[str]:
    out = []
    for event in record.get("events", []):
        out += [f"**Event `{event['id']}`:** {_inline(event['statement'])}",
                "Supporting citations: " + ", ".join(str(i + 1) for i in event["evidence_refs"]),
                "Event date: " + _inline(event_date_label(event["event_date"])), ""]
        if "effective_date" in event:
            out += ["Effective date: " + _inline(event_date_label(event["effective_date"])), ""]
    return out


def _review_question(record: dict, change: str) -> tuple[str, str, str]:
    kind = record["kind"]
    if kind == "decision":
        question = "Does the cited context establish a final decision and its authority, rather than a proposal?"
    elif kind == "uncertainty":
        question = "Are both sides of the uncertainty and the unresolved status preserved?"
    elif kind == "investigation":
        question = "Do the scoped citations support each finding without implying runtime verification?"
    else:
        question = "Does each citation support the stated requirement, scope, status, and conditions?"
    if change == "changed":
        question += " What justifies the change from the previous approved record?"
    severity = "high" if kind == "uncertainty" or change == "changed" else "review"
    return severity, question, "Inspect the exact quote in context; correct the candidate or record the unresolved issue before approval."


def render_review_report(run: Path, manifest: dict, records: dict, check: dict,
                         previous: tuple[Path, dict, dict] | None = None) -> bytes:
    """Render every candidate and material review prompt from verified inputs.

    The caller validates both runs before invoking this function. Output is a
    derived aid, not a reviewer disposition or approval.
    """
    files = {f["evidence_id"]: f for f in manifest["files"]}
    inventory = load_segment_inventory(run, manifest)
    segments = {s["segment_id"]: s for s in (inventory or {}).get("segments", [])}
    prior_root, prior_records, prior_manifest = previous if previous else (None, None, None)
    old = {r["id"]: r for r in prior_records["records"]} if prior_records else {}
    old_files = {f["evidence_id"]: f for f in prior_manifest["files"]} if prior_manifest else {}
    old_inventory = load_segment_inventory(prior_root, prior_manifest) if previous else None
    old_segments = {s["segment_id"]: s for s in (old_inventory or {}).get("segments", [])}
    now = {r["id"]: r for r in records["records"]}
    hints = {}
    for hint in check["semantic_hints"]:
        hints.setdefault(hint["record_id"], []).append(hint)
    out = [f"# Proposed review report — {_inline(manifest['project_id'])} / `{manifest['run_id']}`", "",
           "This is a generated review aid, not semantic validation or human approval. Every approval check "
           "in review.pending.json starts false. Read unchanged records and frozen evidence too.", "",
           f"Candidate: `proposals/records.json`. Previous approved release: "
           f"`{prior_records['run_id'] if prior_records else 'none'}`.", "",
           "## Potential blockers and required checks", "",
           "The structural Stage 2 checker passed. It cannot decide semantic support, authority, "
           "source fidelity, privacy, or whether triaged material can be omitted. Resolve material "
           "issues below before approving; leave checks false or request changes otherwise.", "",
           ]
    potential = []
    for rid in sorted(set(old) - set(now)):
        potential.append(f"- **High:** `{rid}` is removed. Verify the reason and current coverage before accepting removal.")
    for record in records["records"]:
        if record["kind"] == "uncertainty" or record["epistemic_status"] == "unresolved":
            potential.append(f"- **High:** `{record['id']}` remains unresolved. Preserve the question and review both sides.")
    for issue in (inventory or {}).get("issues", []):
        potential.append(f"- **Potential high:** `{issue['evidence_id']}` has unavailable or review-required "
                         f"material at {_inline(issue['locator'] or 'unspecified locator')}: "
                         f"{_inline(issue['detail'])}. Check dependent claims.")
    for c in records["coverage"]:
        if c["disposition"] == "triaged_out":
            potential.append(f"- **Review:** `{c['evidence_id']}` was triaged out. Verify omission is acceptable.")
    for c in records.get("segment_coverage", []):
        if c["disposition"] == "triaged_out":
            potential.append(f"- **Review:** segment `{c['segment_id']}` was triaged out. Verify omission is acceptable.")
    out += potential or ["No automatic potential blockers identified; semantic and fidelity review is still required."]
    out += ["", "## Record and change review", ""]
    for rid in sorted(set(now) | set(old)):
        current, former = now.get(rid), old.get(rid)
        change = "removed" if current is None else "added" if former is None else "unchanged" if current == former else "changed"
        record = current or former
        severity, question, action = _review_question(record, change)
        if change == "removed":
            severity = "high"
            question = "Is removing this previously approved record justified by current evidence and scope?"
            action = "Check the previous citations and current coverage; retain, revise, or explicitly accept the removal."
        out += [f"### {rid} — {_inline(record['title'])} ({change})", "",
                f"**Severity:** {severity}. **Why it matters:** "
                + ("The current complete snapshot removes a prior record."
                   if change == "removed" else "A proposed claim may change what readers believe about the project."),
                f"**What must the reviewer verify?** {_inline(question)}",
                f"**Action:** {_inline(action)}", ""]
        if change != "unchanged":
            out += ["**Before:** " + _inline(_record_summary(former)), "",
                    "**After:** " + _inline(_record_summary(current)), ""]
        else:
            out += ["Record content is unchanged from the previous approved release; its meaning and current support still require review.", "",
                    "**Current claim:** " + _inline(_record_summary(current)), ""]
        if current:
            out += _events(current)
            out += ["**Current frozen citations:**", ""]
            for number, citation in enumerate(current["evidence"], 1):
                out += [f"**Citation {number}:**", ""]
                out += _citation(run, run, manifest, files, segments, citation)
            if current["investigation"] is not None:
                investigation = current["investigation"]
                out += ["Investigation question: " + _inline(investigation["question"]),
                        "Method: " + _inline(investigation["method"]),
                        "Limitations: " + _inline("; ".join(investigation["limitations"])),
                        "Next action: " + _inline(investigation["next_action"]), ""]
                for finding in current["investigation"]["findings"]:
                    out += ["Finding: " + _inline(finding["claim"]), ""]
                    for citation in finding["evidence"]:
                        out += _citation(run, run, manifest, files, segments, citation)
            for question_text in current["open_questions"]:
                out += ["Open question: " + _inline(question_text), ""]
        if former and change in {"changed", "removed"}:
            out += ["**Previous approved events:**", ""] if former.get("events") else []
            out += _events(former)
            out += ["**Previous approved citations:**", ""]
            for number, citation in enumerate(former["evidence"], 1):
                out += [f"**Citation {number}:**", ""]
                out += _citation(run, prior_root, prior_manifest, old_files, old_segments, citation)
        for hint in hints.get(rid, []):
            out += [f"Semantic question `{hint['code']}`: {_inline(hint['detail'])}. "
                    "Action: inspect the cited context and resolve or preserve the uncertainty.", ""]
    out += ["## Semantic questions", ""]
    questions = [f"- `{h['record_id'] or '(run)'}` / `{h['code']}`: {_inline(h['detail'])}. "
                 "Action: inspect cited context and decide whether the candidate needs correction."
                 for h in check["semantic_hints"]]
    questions += [f"- `{r['id']}` open question: {_inline(q)}. Action: preserve or resolve with evidence."
                  for r in records["records"] for q in r["open_questions"]]
    out += questions or ["None reported. This does not certify semantics."]
    out += ["", "## Fidelity gaps and unavailable material", ""]
    gaps = []
    segment_issue_keys = {(i["evidence_id"], i["code"], i["locator"], i["detail"])
                          for i in (inventory or {}).get("issues", [])}
    for f in manifest["files"]:
        for issue in f.get("document", {}).get("issues", []):
            if (f["evidence_id"], issue["code"], issue.get("locator"), issue["detail"]) in segment_issue_keys:
                continue
            gaps.append(f"- **High / review:** {_inline(f['source_id'] + '/' + f['relative_path'])} — "
                        f"<code>{html.escape(issue['code'], quote=False)}</code> at {_inline(issue.get('locator') or 'unspecified locator')}: "
                        f"{_inline(issue['detail'])}. Question: does this affect a claim? "
                        "Action: inspect the original artifact or keep the claim unresolved.")
    for issue in (inventory or {}).get("issues", []):
        f = files[issue["evidence_id"]]
        gaps.append(f"- **High / review:** {_inline(f['source_id'] + '/' + f['relative_path'])} — "
                    f"<code>{html.escape(issue['code'], quote=False)}</code> at {_inline(issue['locator'] or 'unspecified locator')}: "
                    f"{_inline(issue['detail'])}. Question: is required content unavailable? "
                    "Action: obtain an authorized faithful source or keep dependent claims unresolved.")
    out += gaps or ["None reported by structural extraction. Fidelity still requires human comparison."]
    out += ["", "## Date and project-routing uncertainties", ""]
    temporal = []
    for record in records["records"]:
        for event in record.get("events", []):
            for field in ("event_date", "effective_date"):
                value = event.get(field)
                if value and (field == "effective_date" or value["status"] != "known"
                              or value["basis"] == "relative_to_anchor"):
                    temporal.append(f"- **Review:** `{record['id']}` / `{event['id']}` {field}: "
                                    f"{_inline(value['status'])} {_inline(value.get('value', ''))} "
                                    f"({_inline(value['basis'])}). "
                                    "Question: do cited lines support this date and qualification? "
                                    "Action: retain uncertainty until resolved by evidence and human review.")
    out += temporal or ["No non-known event dates recorded; this does not prove date accuracy."]
    if records.get("schema_version") == "0.5":
        routing = read_json(inside(run, "proposals/referrals.json"))
        scan = read_json(inside(run, "work/mentions.json"))
        assessments = {a["mention_id"]: a for a in routing["assessments"]}
        referrals = {r["id"]: r for r in routing["referrals"]}
        out += ["", "## Cross-project routing review", "",
                "Every alias hit has a proposed R1–R4 assessment. Confirm its semantic class, home scope, "
                "exact quote, destination grant, and whether the target is permitted to see this context. "
                "A pending referral does not approve target knowledge.", ""]
        for hit in scan["mentions"]:
            assessment = assessments[hit["id"]]
            out += [f"### {hit['id']} · {_inline(assessment['class'])} · {_inline(assessment['disposition'])}", "",
                    f"**Candidate target:** {_inline(hit['target_project_id'])}. "
                    f"**Matched alias:** {_inline(hit['matched_alias'])}. "
                    f"**Reason:** {_inline(assessment['reason'])}. "
                    f"**Home records:** {', '.join(assessment['home_record_ids']) or 'none'}. "
                    f"**Referral:** {_inline(assessment['referral_id'] or 'none')}.", ""]
            if hit["classification"] == "ambiguous_alias_overlap":
                out += ["**Ambiguous alias overlap:** check the intended project before approval.", ""]
            if assessment["referral_id"]:
                ref = referrals[assessment["referral_id"]]
                out += [f"**Proposed target summary:** {_inline(ref['summary'])}. "
                        f"**Why target may care:** {_inline(ref['why_target_cares'])}.", ""]
                out += _citation(run, run, manifest, files, segments, ref["source"])
            else:
                segment = hit["segments"][0]
                out += _citation(run, run, manifest, files, segments,
                                 {"evidence_id": hit["evidence_id"], "segment_id": segment["segment_id"],
                                  "start_line": hit["line"], "end_line": hit["line"],
                                  "quote": hit["line_text"]})
    else:
        out += ["", "Project routing is not assessed automatically. Check whether any cited passage concerns "
               "another project before approving home-project knowledge.", ""]
    out += ["## Triaged inputs", ""]
    triaged = [c for c in records["coverage"] if c["disposition"] == "triaged_out"]
    for item in sorted(triaged, key=lambda c: c["evidence_id"]):
        f = files[item["evidence_id"]]
        out.append(f"- **Review:** `{item['evidence_id']}` {_inline(f['source_id'] + '/' + f['relative_path'])}; "
                   f"method: {_inline(item['method'])}. Question: is omission acceptable for this question? "
                   "Action: inspect if material or explicitly acknowledge triage; do not call it fully reviewed.")
    segment_triaged = [c for c in records.get("segment_coverage", []) if c["disposition"] == "triaged_out"]
    for item in sorted(segment_triaged, key=lambda c: c["segment_id"]):
        segment = segments[item["segment_id"]]
        f = files[segment["evidence_id"]]
        out.append(f"- **Review:** segment `{item['segment_id']}` in "
                   f"{_inline(f['source_id'] + '/' + f['relative_path'])}; "
                   f"original locator: {_inline(segment['original_locator'])}; "
                   f"method: {_inline(item['method'])}. Question: is omitting this segment acceptable? "
                   "Action: inspect if material or explicitly acknowledge segment triage.")
    out += (["None."] if not triaged and not segment_triaged else []) + ["", "## Warning occurrences", ""]
    warnings = sorted((i for i in manifest["issues"] if i["severity"] == "warning"),
                      key=lambda i: (i["code"], i["source_id"] or "", i["path"] or "", i["detail"]))
    for number, issue in enumerate(warnings, 1):
        out += [f"### Warning {number}: <code>{html.escape(issue['code'], quote=False)}</code>", "",
                f"**Severity:** warning. **Source:** {_inline(issue['source_id'] or '(run)')} / "
                f"{_inline(issue['path'] or '(run)')}. **Why it matters:** {_inline(issue['detail'])}", "",
                "**Question:** Does this occurrence affect source trust, completeness, or a proposed claim? "
                "**Action:** Inspect it and acknowledge this occurrence in the warning count only if acceptable.", ""]
    if not warnings:
        out += ["None reported. Absence of warnings is not semantic validation.", ""]
    return ("\n".join(out) + "\n").encode("utf-8")
