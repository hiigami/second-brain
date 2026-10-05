"""Temporal-integrity probes for the Work Second Brain engine.

Usage: python3 temporal_probe.py <engine-root>
Each probe builds a throwaway project from tests/fixtures in a temp dir and prints
what the engine does. A probe that the engine refuses prints "BLOCKED BY ENGINE".
Nothing touches real project data.
"""
import json
import shutil
import sys
import tempfile
from datetime import datetime as _dt, timezone as _tz
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "tools")); sys.path.insert(0, str(ROOT / "tests"))
import kb_inventory
from kb_common import KBError, read_json, utc_now, write_json_new
from kb_inventory import inventory
from kb_publish import prepare_review, publish
from kb_reanchor import reanchor
from helpers import PROJECT_CONFIG, PROVENANCE, SOURCES, synthetic_records


def setup():
    t = Path(tempfile.mkdtemp()).resolve()
    shutil.copytree(SOURCES, t / "sources")
    proj = t / "projects" / "demo"; (proj / "config").mkdir(parents=True)
    cfg = read_json(PROJECT_CONFIG)
    for s in cfg["sources"]:
        s["path"] = str(t / "sources" / s["id"])
    (proj / "config" / "project.json").write_text(json.dumps(cfg))
    shutil.copyfile(PROVENANCE, proj / "config" / "source-provenance.json")
    return t, proj, proj / "config" / "project.json"


def records_for(run, m):
    rec = synthetic_records(run, m)
    cited = {e["evidence_id"] for r in rec["records"] for e in r["evidence"]}
    cited |= {e["evidence_id"] for r in rec["records"] if r["investigation"]
              for f in r["investigation"]["findings"] for e in f["evidence"]}
    for c in rec["coverage"]:
        if c["evidence_id"] not in cited:
            c["disposition"] = "reviewed_no_record"; c["note"] = "probe"
    write_json_new(run / "proposals" / "records.json", rec)
    return rec


def approve(cfg, run, reviewed_at=None):
    r = prepare_review(cfg, run)
    r.update(decision="approve", reviewer="probe", reviewed_at=reviewed_at or utc_now())
    r["checks"] = dict.fromkeys(r["checks"], True)
    r["acknowledged_warnings"] = dict(r["warning_summary"]["counts"])
    r["triage_acknowledged"] = bool(r["triaged_evidence_ids"])
    p = run / "review.json"; p.write_text(json.dumps(r)); return p


PROBES = []
def probe(fn):
    PROBES.append(fn); return fn


def kind(m, logical):
    for k in ("added", "modified", "unchanged", "removed"):
        if logical in m["delta"][k]:
            return k
    return "?"


@probe
def p1_out_of_order_and_baseline():
    """P1/P2: an older meeting arrives later; baseline skips the newest run; clock goes backwards."""
    t, proj, cfg = setup()
    r1, m1 = inventory(cfg, "run-1")
    note = t / "sources/meetings/2026-08-30-kickoff.md"
    note.write_text("# Kickoff 2026-08-30\n\nDecision: limit is 5.\nOwner: unknown.\n")
    r2, m2 = inventory(cfg, "run-2", baseline=r1)
    f = [x for x in m2["files"] if "kickoff" in x["relative_path"]][0]
    print("P1 month-old note captured today is delta:", kind(m2, f["logical_id"]))
    print("P1 per-file time fields:", f.get("temporal", "none"))
    print("P1 manifest time fields:", {k: m2[k] for k in m2 if k.endswith("_at") or k == "sequence"})
    note.write_text("# Kickoff 2026-08-30\n\nDecision: limit is 6.\nOwner: unknown.\n")
    r3, m3 = inventory(cfg, "run-3", baseline=r1)
    print("P2 run-3 baseline:", m3["delta"]["baseline_run_id"], "(newer run-2 exists); kickoff reported as:",
          kind(m3, f["logical_id"]), "| baseline warnings:",
          sorted({i["code"] for i in m3["issues"] if i["code"].startswith("baseline")}))

    class _Past(_dt):
        @classmethod
        def now(cls, tz=None):
            return _dt(2020, 1, 1, tzinfo=_tz.utc)
    saved = kb_inventory.utc_now, getattr(kb_inventory, "datetime", None)
    kb_inventory.utc_now = lambda: "2020-01-01T00:00:00+00:00"
    if saved[1] is not None:
        kb_inventory.datetime = _Past
    try:
        r4, m4 = inventory(cfg, "run-4", baseline=r3)
        print("P2 machine clock in 2020: run-4 created_at", m4["created_at"],
              "accepted although its baseline is", m3["created_at"])
    except KBError as e:
        print("P2 machine clock in 2020: BLOCKED BY ENGINE:", e)
    finally:
        kb_inventory.utc_now = saved[0]
        if saved[1] is not None:
            kb_inventory.datetime = saved[1]


@probe
def p3_stale_provenance():
    t, proj, cfg = setup()
    p1, n1 = inventory(cfg, "p-1")
    req = t / "sources/requirements/requirements.md"
    req.write_text(req.read_text() + "\nNew line added after the export described in provenance.\n")
    p2, n2 = inventory(cfg, "p-2", baseline=p1)
    b = [x for x in n2["files"] if x["source_id"] == "requirements"][0]
    print("P3 new bytes carry old captured_at/revision:", b["provenance"]["captured_at"], "/", b["provenance"]["revision"])
    print("P3 warnings on that file:", sorted({i["code"] for i in n2["issues"] if i["path"] == "requirements.md"}))
    prov = read_json(proj / "config/source-provenance.json")
    prov["entries"][0]["origin"]["captured_at"] = "2099-12-31T00:00:00+00:00"
    (proj / "config/source-provenance.json").write_text(json.dumps(prov))
    p3, n3 = inventory(cfg, "p-3")
    print("P3 captured_at=2099 -> run status:", n3["status"],
          [i["code"] for i in n3["issues"] if i["severity"] == "error"])


@probe
def p4_publication_order():
    t, proj, cfg = setup()
    old, mo = inventory(cfg, "old-capture"); records_for(old, mo)
    req = t / "sources/requirements/requirements.md"
    req.write_text(req.read_text().replace("10", "12", 1))
    new, mn = inventory(cfg, "new-capture", baseline=old); records_for(new, mn)
    publish(cfg, new, approve(cfg, new), True)
    try:
        publish(cfg, old, approve(cfg, old), True)
    except KBError as e:
        print("P4 publishing the older capture after the newer one: BLOCKED BY ENGINE:", e)
    cur = read_json(proj / "knowledge/approved/CURRENT.json")
    print("P4 CURRENT:", cur["run_id"], "| HISTORY.jsonl exists:", (proj / "knowledge/approved/HISTORY.jsonl").exists())


@probe
def p5_review_time():
    t, proj, cfg = setup()
    rr, mr = inventory(cfg, "rv"); records_for(rr, mr)
    try:
        publish(cfg, rr, approve(cfg, rr, reviewed_at="2001-01-01T00:00:00+00:00"), True)
        print("P5 reviewed_at=2001 accepted for a run captured", mr["created_at"])
    except KBError as e:
        print("P5 reviewed_at=2001: BLOCKED BY ENGINE:", e)


@probe
def p6_rename_and_partial_loss():
    t, proj, cfg = setup()
    a1, ma = inventory(cfg, "a-1"); records_for(a1, ma)
    (t / "sources/requirements/requirements.md").rename(t / "sources/requirements/requirements-v2.md")
    prov = read_json(proj / "config/source-provenance.json")
    for e in prov["entries"]:
        if e["relative_path"] == "requirements.md":
            e["relative_path"] = "requirements-v2.md"
    (proj / "config/source-provenance.json").write_text(json.dumps(prov))
    a2, mb = inventory(cfg, "a-2", baseline=a1)
    print("P6 delta added/removed/renamed:", len(mb["delta"]["added"]), len(mb["delta"]["removed"]),
          len(mb["delta"].get("renamed", [])))
    recs, rep = reanchor(a1, a2)
    print("P6 reanchor:", rep["citation_status_counts"], "| dropped:", rep["dropped_record_ids"],
          "| degraded:", rep.get("degraded_record_ids", "n/a"))


@probe
def p10_partial_evidence_loss():
    """A file genuinely disappears (not a rename): records citing it plus another file survive half-supported."""
    t, proj, cfg = setup()
    a1, ma = inventory(cfg, "b-1"); records_for(a1, ma)
    req = t / "sources/requirements/requirements.md"
    req.write_text("# Requirements\n\nRewritten from scratch; the limit line is gone.\n")
    a2, mb = inventory(cfg, "b-2", baseline=a1)
    recs, rep = reanchor(a1, a2)
    unc = [r for r in recs["records"] if r["id"] == "UNC-001"]
    print("P10 reanchor:", rep["citation_status_counts"], "| dropped:", rep["dropped_record_ids"],
          "| degraded:", rep.get("degraded_record_ids", "n/a"))
    if unc:
        print("P10 UNC-001 kept with", len(unc[0]["evidence"]), "of 2 citations; relations:", unc[0]["relations"],
              "| open questions added:", len(unc[0]["open_questions"]) - 1,
              "| structural check:", rep["structural_check"]["status"])


@probe
def p7_revert():
    t, proj, cfg = setup()
    req = t / "sources/requirements/requirements.md"; text = req.read_text()
    v1, x1 = inventory(cfg, "v-1")
    req.write_text(text + "\nTemporary edit.\n"); v2, x2 = inventory(cfg, "v-2", baseline=v1)
    req.write_text(text); v3, x3 = inventory(cfg, "v-3", baseline=v2)
    eid = lambda m: [x["evidence_id"] for x in m["files"] if x["source_id"] == "requirements"][0]
    print("P7 A->B->A: v3 evidence id equals v1:", eid(x3) == eid(x1), "| v3 delta modified:", len(x3["delta"]["modified"]))


@probe
def p8_reanchor_direction():
    t, proj, cfg = setup()
    o1, _ = inventory(cfg, "older")
    req = t / "sources/requirements/requirements.md"; req.write_text(req.read_text() + "\nExtra.\n")
    n1, mn1 = inventory(cfg, "newer", baseline=o1); records_for(n1, mn1)
    try:
        _, rep = reanchor(n1, o1)
        print("P8 re-anchoring NEWER records into an OLDER run accepted:", rep["citation_status_counts"])
    except KBError as e:
        print("P8 newer->older re-anchor: BLOCKED BY ENGINE:", e)


@probe
def p13_content_dates():
    t, proj, cfg = setup()
    for name in ("[Sync] Demo - 2026_09_25 12_00 GMT-05_00 - Notes by Gemini.md",
                 "Demo 2.0 Revision - 2026_09_30 14_00 GMT-03_00 - Notes by Gemini.md"):
        (t / "sources/meetings" / name).write_text("# notes\n\ncontent\n")
    r, m = inventory(cfg, "dates")
    for f in m["files"]:
        if f["source_id"] == "meetings":
            print("P13", f["relative_path"][:45], "->", (f.get("temporal") or {}).get("content_date", "no field"))


for fn in PROBES:
    print(f"\n=== {fn.__name__}")
    try:
        fn()
    except KBError as e:
        print("BLOCKED BY ENGINE:", e)
