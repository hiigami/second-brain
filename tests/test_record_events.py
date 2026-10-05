"""Synthetic records 0.4 event-time contract checks."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from kb_check import check_records
from kb_common import KBError, read_json, utc_now
from kb_inventory import inventory
from kb_publish import prepare_review, publish, render_views
from kb_reanchor import reanchor
from kb_review_report import render_review_report


class RecordEventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        source = root / "source"
        source.mkdir()
        self.source_file = source / "timeline.md"
        self.source_file.write_text(
            "2026-09-25: request submitted.\n"
            "2026-10-01: review completed; effective from 2027-01-01.\n"
            "One note says 2026-10-02; another says 2026-10-03.\n",
            encoding="utf-8")
        project = root / "project"
        (project / "config").mkdir(parents=True)
        config = project / "config" / "project.json"
        config.write_text(json.dumps({
            "schema_version": "0.1",
            "project": {"id": "events", "name": "Events", "description": "Synthetic"},
            "sources": [{"id": "notes", "type": "meetings", "path": str(source),
                         "include": ["**/*.md"], "exclude": []}],
            "global_exclude": [],
            "knowledge": {"path": "knowledge", "approved": "knowledge/approved"},
            "runs": {"path": "runs"},
        }), encoding="utf-8")
        self.config = config
        self.run, self.manifest = inventory(config, "events-one")
        f = self.manifest["files"][0]
        segment = read_json(self.run / "segments.snapshot.json")["segments"][0]
        lines = (self.run / f["snapshot_path"]).read_text().splitlines()
        def cite(n):
            return {"evidence_id": f["evidence_id"], "segment_id": segment["segment_id"],
                    "representation_sha256": segment["representation_sha256"],
                    "start_line": n, "end_line": n, "quote": lines[n - 1]}
        self.records = {
            "schema_version": "0.4", "project_id": "events", "run_id": "events-one",
            "coverage": [{"evidence_id": f["evidence_id"], "disposition": "used", "note": "Synthetic evidence."}],
            "segment_coverage": [{"segment_id": segment["segment_id"], "disposition": "used",
                                  "note": "Synthetic evidence."}],
            "records": [{"id": "REQ-001", "kind": "requirement", "title": "Synthetic events",
                         "statement": "The fixture records a submission and review.",
                         "epistemic_status": "observed", "evidence": [cite(1), cite(2), cite(3)],
                         "relations": [], "open_questions": [], "investigation": None,
                         "events": [
                             {"id": "EVT-001", "statement": "Request submitted",
                              "evidence_refs": [0],
                              "event_date": {"status": "known", "value": "2026-09-25",
                                             "precision": "day", "basis": "explicit_text"}},
                             {"id": "EVT-002", "statement": "Review completed",
                              "evidence_refs": [1],
                              "event_date": {"status": "known", "value": "2026-10-01",
                                             "precision": "day", "basis": "explicit_text"},
                              "effective_date": {"status": "known", "value": "2027-01-01",
                                                 "precision": "day", "basis": "explicit_text"}}
                         ]}]}
        self.out = root / "records.json"

    def check(self, data=None):
        self.out.write_text(json.dumps(data or self.records), encoding="utf-8")
        return check_records(self.run, self.manifest, self.out, stage2=True)

    def test_multiple_events_and_future_effective_date_are_valid(self):
        self.assertEqual(self.check()["event_count"], 2)

    def test_review_report_shows_event_claims_and_supporting_citations(self):
        self.check()

        report = render_review_report(self.run, self.manifest, self.records,
                                      {"semantic_hints": []}).decode()

        for event in self.records["records"][0]["events"]:
            self.assertIn(event["statement"], report)
        self.assertIn("Supporting citations: 1", report)
        self.assertIn("Supporting citations: 2", report)

    def test_review_report_preserves_conflicting_and_relative_date_qualifications(self):
        data = copy.deepcopy(self.records)
        events = data["records"][0]["events"]
        events[0]["event_date"] = {
            "status": "approximate", "basis": "relative_to_anchor", "value": "2026-09-26",
            "end": "2026-09-27", "precision": "day", "anchor_ref": 0, "anchor_value": "2026-09-25",
            "note": "Synthetic next-day interpretation needs confirmation."}
        events[1]["event_date"] = {
            "status": "conflicting", "basis": "conflicting_sources", "note": "Review-date conflict remains unresolved.",
            "alternatives": [
                {"value": "2026-10-02", "precision": "day", "evidence_refs": [2]},
                {"value": "2026-10-03", "precision": "day", "evidence_refs": [2]}]}
        events[1]["evidence_refs"] = [1, 2]
        self.check(data)

        report = render_review_report(self.run, self.manifest, data, {"semantic_hints": []}).decode()

        self.assertIn("Review-date conflict remains unresolved.", report)
        self.assertIn("2026-10-02 (day; citations 3)", report)
        self.assertIn("2026-10-03 (day; citations 3)", report)
        self.assertIn("2026-09-26–2026-09-27", report)
        self.assertIn("anchor 2026-09-25 (citation 1)", report)
        self.assertIn("Synthetic next-day interpretation needs confirmation.", report)

    def test_review_report_previous_events_preserve_removed_qualifications(self):
        old = copy.deepcopy(self.records)
        old["records"][0]["events"][0]["event_date"] = {
            "status": "approximate", "basis": "explicit_text", "value": "2026-09-25",
            "precision": "day", "note": "Earlier date remains tentative pending corroboration."}
        self.check(old)
        self.check()

        report = render_review_report(self.run, self.manifest, self.records, {"semantic_hints": []},
                                      (self.run, old, self.manifest)).decode()

        self.assertIn("Earlier date remains tentative pending corroboration.", report)

    def test_synthetic_release_generates_review_bound_timeline(self):
        self.check()
        (self.run / "proposals/records.json").write_text(json.dumps(self.records), encoding="utf-8")
        review = prepare_review(self.config, self.run)
        review.update(decision="approve", reviewer="Synthetic test operator (simulated)",
                      reviewed_at=utc_now(), notes="UNIT TEST ONLY. Not a real human approval.")
        review["checks"] = dict.fromkeys(review["checks"], True)
        review["acknowledged_warnings"] = dict(review["warning_summary"]["counts"])
        review["triage_acknowledged"] = bool(review["triaged_evidence_ids"])
        review_path = self.run / "review.json"
        review_path.write_text(json.dumps(review), encoding="utf-8")
        release = publish(self.config, self.run, review_path, human_approved=True)
        self.assertIn("EVT-001", (release / "timeline.md").read_text())
        self.assertIn("2027-01-01", (release / "timeline.md").read_text())
        self.assertIn("2027-01-01", (release / "review-report.md").read_text())
        self.assertIn("[Timeline](timeline.md)", (release / "index.md").read_text())
        self.assertIn("[Review report](review-report.md)", (release / "index.md").read_text())

    def test_older_schema_cannot_claim_event_support(self):
        data = copy.deepcopy(self.records)
        data["schema_version"] = "0.3"
        with self.assertRaises(KBError):
            self.check(data)
        data = copy.deepcopy(self.records)
        del data["records"][0]["events"]
        with self.assertRaises(KBError):
            self.check(data)

    def test_event_rejects_unsupported_citation_and_invalid_dates(self):
        for change in (
            lambda d: d["records"][0]["events"][0].update(evidence_refs=[9]),
            lambda d: d["records"][0]["events"][0]["event_date"].update(value="2026-02-30"),
            lambda d: d["records"][0]["events"][0]["event_date"].update(value="2026-09-25T12:00:00"),
            lambda d: d["records"][0]["events"][0]["event_date"].update(end="2026-09-24"),
        ):
            data = copy.deepcopy(self.records)
            change(data)
            with self.subTest(data=data), self.assertRaises(KBError):
                self.check(data)

    def test_unknown_conflicting_and_relative_dates_keep_qualifiers(self):
        data = copy.deepcopy(self.records)
        events = data["records"][0]["events"]
        events[0]["event_date"] = {"status": "unknown", "basis": "not_stated",
                                   "note": "The event is stated without a reliable date."}
        events[1]["event_date"] = {
            "status": "conflicting", "basis": "conflicting_sources", "note": "Two dates are stated.",
            "alternatives": [
                {"value": "2026-10-02", "precision": "day", "evidence_refs": [2]},
                {"value": "2026-10-03", "precision": "day", "evidence_refs": [2]}]}
        events[1]["evidence_refs"] = [1, 2]
        self.assertEqual(self.check(data)["event_date_status_counts"],
                         {"conflicting": 1, "unknown": 1})
        events[1]["event_date"] = {
            "status": "approximate", "basis": "relative_to_anchor", "value": "2026-10-02",
            "precision": "day", "anchor_ref": 1, "anchor_value": "2026-10-01",
            "note": "Synthetic anchored next-day interpretation; human review required."}
        self.assertEqual(self.check(data)["event_date_status_counts"],
                         {"approximate": 1, "unknown": 1})
        del events[1]["event_date"]["anchor_ref"]
        with self.assertRaises(KBError):
            self.check(data)

    def test_timezone_equivalent_conflict_is_rejected(self):
        data = copy.deepcopy(self.records)
        event = data["records"][0]["events"][0]
        event["event_date"] = {
            "status": "conflicting", "basis": "conflicting_sources", "note": "Alleged conflict.",
            "alternatives": [
                {"value": "2026-09-25T12:00:00-05:00", "precision": "second", "evidence_refs": [0]},
                {"value": "2026-09-25T17:00:00Z", "precision": "second", "evidence_refs": [0]}]}
        with self.assertRaises(KBError):
            self.check(data)
        event["event_date"]["alternatives"][0].update(
            value="2026-09-25T12:00-05:00", precision="minute")
        with self.assertRaises(KBError):
            self.check(data)

    def test_duplicate_event_ids_and_invented_unknown_date_are_rejected(self):
        data = copy.deepcopy(self.records)
        data["records"][0]["events"][1]["id"] = "EVT-001"
        with self.assertRaises(KBError):
            self.check(data)
        data = copy.deepcopy(self.records)
        data["records"][0]["events"][0]["event_date"] = {
            "status": "unknown", "basis": "not_stated", "value": "2026-09-25",
            "note": "The date is not established."}
        with self.assertRaises(KBError):
            self.check(data)

    def test_reanchor_drops_event_when_date_support_disappears(self):
        prior = self.run / "proposals" / "records.json"
        prior.write_text(json.dumps(self.records), encoding="utf-8")
        self.source_file.write_text(
            "2026-10-01: review completed; effective from 2027-01-01.\n"
            "One note says 2026-10-02; another says 2026-10-03.\n", encoding="utf-8")
        second, manifest = inventory(self.config, "events-two", baseline=self.run)
        moved, report = reanchor(self.run, second)
        self.assertEqual(moved["schema_version"], "0.4")
        self.assertEqual([e["id"] for e in moved["records"][0]["events"]], ["EVT-002"])
        self.assertEqual(moved["records"][0]["events"][0]["evidence_refs"], [0])
        self.assertEqual(report["dropped_event_ids"], ["EVT-001"])
        self.assertIn("REQ-001", report["degraded_record_ids"])
        self.assertEqual(check_records(second, manifest, second / "work/reanchored-records.json")["event_count"], 1)
        view = second / "work" / "synthetic-view"
        (view / "records").mkdir(parents=True)
        render_views(view, moved, manifest)
        timeline = (view / "timeline.md").read_text()
        self.assertIn("EVT-002", timeline)
        self.assertNotIn("EVT-001", timeline)


if __name__ == "__main__":
    unittest.main()
