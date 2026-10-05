"""Temporal integrity: content vs capture time, ordering of runs, releases and re-anchoring,
stale provenance, renames and partial evidence loss. Synthetic fixtures only."""
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import kb_inventory
from kb_common import KBError, content_date_from_name, content_sort_key, read_json, utc_now, write_json_new
from kb_inventory import inventory
from kb_publish import prepare_review, publish
from kb_reanchor import reanchor
from helpers import PROJECT_CONFIG, PROVENANCE, SOURCES, synthetic_records


class TemporalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name).resolve()
        self.sources = root / "sources"
        shutil.copytree(SOURCES, self.sources)
        self.project = root / "projects" / "demo"
        (self.project / "config").mkdir(parents=True)
        self.config = self.project / "config" / "project.json"
        cfg = read_json(PROJECT_CONFIG)
        for s in cfg["sources"]:
            s["path"] = str(self.sources / s["id"])
        self.config.write_text(json.dumps(cfg), encoding="utf-8")
        self.prov_path = self.project / "config" / "source-provenance.json"
        shutil.copyfile(PROVENANCE, self.prov_path)
        self.req = self.sources / "requirements" / "requirements.md"

    def tearDown(self):
        self.temp.cleanup()

    def records(self, run, m):
        rec = synthetic_records(run, m, schema_version="0.2")
        cited = {e["evidence_id"] for r in rec["records"] for e in r["evidence"]}
        cited |= {e["evidence_id"] for r in rec["records"] if r["investigation"]
                  for f in r["investigation"]["findings"] for e in f["evidence"]}
        for c in rec["coverage"]:
            if c["evidence_id"] not in cited:
                c.update(disposition="reviewed_no_record", note="test")
        write_json_new(run / "proposals" / "records.json", rec)

    def review(self, run, **extra):
        r = prepare_review(self.config, run)
        r.update(decision="approve", reviewer="Synthetic test operator (simulated)", reviewed_at=utc_now())
        r["checks"] = dict.fromkeys(r["checks"], True)
        r["acknowledged_warnings"] = dict(r["warning_summary"]["counts"])
        r["triage_acknowledged"] = bool(r["triaged_evidence_ids"])
        r.update(extra)
        path = run / "review.json"
        path.write_text(json.dumps(r), encoding="utf-8")
        return path

    def edit_provenance(self, fn):
        p = read_json(self.prov_path); fn(p); self.prov_path.write_text(json.dumps(p), encoding="utf-8")

    # --- content time vs capture time ---------------------------------------------------
    def test_content_dates_from_names(self):
        g = content_date_from_name("[Sync] Demo - 2026_09_25 12_00 GMT-05_00 - Notes by Gemini.docx")
        self.assertEqual(g, {"value": "2026-09-25T12:00:00-05:00", "basis": "filename:gemini_notes", "precision": "minute"})
        self.assertEqual(content_date_from_name("notes/2026-08-30-kickoff.md")["value"], "2026-08-30")
        self.assertIsNone(content_date_from_name("meeting.md"))
        self.assertIsNone(content_date_from_name("2026-13-45-bad.md"))
        # Ordering normalizes offsets: 12:00 GMT-05 (17:00Z) precedes 14:30 GMT-03 (17:30Z) only in UTC.
        self.assertLess(content_sort_key("2026-09-25T12:00:00-05:00"), content_sort_key("2026-09-25T14:30:00-03:00"))

    def test_old_note_captured_late_keeps_its_content_date(self):
        r1, _ = inventory(self.config, "one")
        (self.sources / "meetings" / "2026-08-30-kickoff.md").write_text("# Kickoff\n\nLimit 5.\n", encoding="utf-8")
        r2, m2 = inventory(self.config, "two", baseline=r1)
        f = next(x for x in m2["files"] if "kickoff" in x["relative_path"])
        self.assertEqual(f["temporal"]["content_date"]["value"], "2026-08-30")
        self.assertLess(f["temporal"]["content_date"]["value"], m2["created_at"][:10])
        self.assertEqual(m2["sequence"], 2)

    def test_provenance_content_date_overrides_filename(self):
        self.edit_provenance(lambda p: p["entries"][0]["origin"].update(content_date="2026-07-01"))
        _, m = inventory(self.config, "one")
        f = next(x for x in m["files"] if x["source_id"] == p_source(self.prov_path))
        self.assertEqual(f["temporal"]["content_date"], {"value": "2026-07-01", "basis": "provenance", "precision": "day"})

    # --- provenance staleness and impossible times --------------------------------------
    def test_provenance_bound_to_other_bytes_blocks(self):
        self.edit_provenance(lambda p: p["entries"][0]["origin"].update(sha256="0" * 64))
        _, m = inventory(self.config, "one")
        self.assertEqual(m["status"], "blocked")
        self.assertIn("provenance_stale", {i["code"] for i in m["issues"]})

    def test_changed_bytes_with_unchanged_provenance_warns(self):
        r1, _ = inventory(self.config, "one")
        self.req.write_text(self.req.read_text() + "\nLater edit.\n", encoding="utf-8")
        _, m = inventory(self.config, "two", baseline=r1)
        self.assertIn("provenance_not_updated", {i["code"] for i in m["issues"]})

    def test_future_capture_time_blocks(self):
        self.edit_provenance(lambda p: p["entries"][0]["origin"].update(captured_at="2099-01-01T00:00:00+00:00"))
        _, m = inventory(self.config, "one")
        self.assertIn("provenance_timestamp_in_future", {i["code"] for i in m["issues"] if i["severity"] == "error"})

    # --- run ordering --------------------------------------------------------------------
    def test_baseline_skipping_newer_run_warns(self):
        r1, _ = inventory(self.config, "one")
        inventory(self.config, "two", baseline=r1)
        _, m3 = inventory(self.config, "three", baseline=r1)
        self.assertIn("baseline_not_latest", {i["code"] for i in m3["issues"]})
        self.assertEqual(m3["delta"]["baseline_sequence"], 1)

    def test_clock_regression_blocks_capture(self):
        inventory(self.config, "one")
        class Past(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2020, 1, 1, tzinfo=timezone.utc)
        with mock.patch.object(kb_inventory, "datetime", Past):
            with self.assertRaises(KBError):
                inventory(self.config, "two")

    # --- publication ordering ------------------------------------------------------------
    def test_older_capture_cannot_silently_replace_current(self):
        old, mo = inventory(self.config, "old"); self.records(old, mo)
        self.req.write_text(self.req.read_text().replace("10", "12", 1), encoding="utf-8")
        new, mn = inventory(self.config, "new", baseline=old); self.records(new, mn)
        publish(self.config, new, self.review(new), True)
        with self.assertRaises(KBError):
            publish(self.config, old, self.review(old), True)
        publish(self.config, old, self.review(old, rollback_reason="Revert a bad export; owner request (test)"), True)
        history = (self.project / "knowledge/approved/HISTORY.jsonl").read_text().splitlines()
        self.assertEqual([json.loads(l)["run_id"] for l in history], ["new", "old"])
        self.assertIsNotNone(json.loads(history[1])["rollback_reason"])

    def test_review_time_must_follow_preparation(self):
        run, m = inventory(self.config, "one"); self.records(run, m)
        with self.assertRaises(KBError):
            publish(self.config, run, self.review(run, reviewed_at="2001-01-01T00:00:00+00:00"), True)
        with self.assertRaises(KBError):
            publish(self.config, run, self.review(run, reviewed_at="2099-01-01T00:00:00+00:00"), True)

    # --- re-anchoring --------------------------------------------------------------------
    def test_reanchor_only_moves_forward(self):
        old, _ = inventory(self.config, "old")
        self.req.write_text(self.req.read_text() + "\nExtra.\n", encoding="utf-8")
        new, mn = inventory(self.config, "new", baseline=old); self.records(new, mn)
        with self.assertRaises(KBError):
            reanchor(new, old)

    def test_byte_identical_rename_is_followed(self):
        a, ma = inventory(self.config, "a"); self.records(a, ma)
        self.req.rename(self.req.with_name("requirements-v2.md"))
        self.edit_provenance(lambda p: [e.update(relative_path="requirements-v2.md") for e in p["entries"]
                                        if e["relative_path"] == "requirements.md"])
        b, mb = inventory(self.config, "b", baseline=a)
        self.assertEqual(len(mb["delta"]["renamed"]), 1)
        records, report = reanchor(a, b)
        self.assertEqual(report["dropped_record_ids"], [])
        self.assertEqual(report["structural_check"]["status"], "passed")

    def test_partial_evidence_loss_is_flagged(self):
        a, ma = inventory(self.config, "a"); self.records(a, ma)
        self.req.write_text("# Requirements\n\nRewritten; the limit line is gone.\n", encoding="utf-8")
        b, _ = inventory(self.config, "b", baseline=a)
        records, report = reanchor(a, b)
        self.assertIn("UNC-001", report["degraded_record_ids"])
        unc = next(r for r in records["records"] if r["id"] == "UNC-001")
        self.assertTrue(any("lost" in q for q in unc["open_questions"]))


def p_source(prov_path):
    return read_json(prov_path)["entries"][0]["source_id"]


if __name__ == "__main__":
    unittest.main()
