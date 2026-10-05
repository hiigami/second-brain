"""Synthetic chronology views must not confuse event time with capture order."""
import copy
import itertools
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from kb_inventory import inventory
from kb_event_time import date_display_sort_key
from kb_packet import build_packets
from kb_publish import changes_view, render_views


CATEGORIES = ("requirements", "architecture", "meetings", "sql", "repository",
              "data", "analysis", "policy")


class ChronologyViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def fixture(self):
        files, records, coverage = [], [], []
        dates = ("2026-09-25", "2026-10-04", "2026-10-03")
        for number, category in enumerate(CATEGORIES):
            eid, rid, event_id = f"E-{number:03d}", f"REQ-{number + 1:03d}", f"EVT-{number + 1:03d}"
            files.append({"evidence_id": eid, "logical_id": f"L-{number:03d}",
                          "source_id": category, "source_type": category,
                          "relative_path": f"{category}.md", "snapshot_path": f"snapshots/{eid}.txt"})
            coverage.append({"evidence_id": eid, "disposition": "used", "note": "Synthetic."})
            records.append({"id": rid, "kind": "requirement", "title": category,
                            "statement": f"Synthetic {category} event.", "epistemic_status": "observed",
                            "evidence": [{"evidence_id": eid, "start_line": 1, "end_line": 1,
                                          "quote": f"Synthetic {category} event."}],
                            "relations": [], "open_questions": [], "investigation": None,
                            "events": [{"id": event_id, "statement": f"{category} happened",
                                        "evidence_refs": [0],
                                        "event_date": {"status": "known", "basis": "explicit_text",
                                                       "value": dates[number % 3], "precision": "day"}}]})
        manifest = {"project_id": "timeline", "run_id": "one", "files": files}
        candidate = {"schema_version": "0.4", "project_id": "timeline", "run_id": "one",
                     "coverage": coverage, "records": records}
        return candidate, manifest

    def test_business_chronology_is_stable_across_ingestion_orders_and_categories(self):
        records, manifest = self.fixture()
        views = []
        for order in itertools.permutations(range(3)):
            candidate = copy.deepcopy(records)
            candidate["records"][:3] = [candidate["records"][i] for i in order]
            release = self.root / ("order-" + "".join(map(str, order)))
            (release / "records").mkdir(parents=True)
            render_views(release, candidate, manifest)
            timeline = (release / "timeline.md").read_text()
            views.append(timeline)
            self.assertIn("[Timeline](timeline.md)", (release / "index.md").read_text())
            self.assertIn("## Events", (release / "records/REQ-001.md").read_text())
        self.assertEqual(len(set(views)), 1)
        self.assertLess(views[0].index("2026-09-25"), views[0].index("2026-10-03"))
        self.assertLess(views[0].index("2026-10-03"), views[0].index("2026-10-04"))
        for category in CATEGORIES:
            self.assertIn(category, views[0])

    def test_timezone_equivalence_unknown_conflict_range_and_effective_date(self):
        records, manifest = self.fixture()
        events = [r["events"][0] for r in records["records"]]
        events[0]["event_date"] = {"status": "known", "basis": "explicit_text",
                                     "value": "2026-09-25T12:00:00-05:00", "precision": "second"}
        events[1]["event_date"] = {"status": "known", "basis": "explicit_text",
                                     "value": "2026-09-25T17:00:00Z", "precision": "second"}
        events[1]["effective_date"] = {"status": "known", "basis": "explicit_text",
                                         "value": "2027-01-01", "precision": "day"}
        self.assertEqual(date_display_sort_key(events[0]["event_date"]["value"], "second"),
                         date_display_sort_key(events[1]["event_date"]["value"], "second"))
        events[2]["event_date"] = {"status": "unknown", "basis": "not_stated",
                                     "note": "Not stated in source."}
        events[3]["event_date"] = {"status": "conflicting", "basis": "conflicting_sources",
                                     "note": "Source disagrees.", "alternatives": [
                                         {"value": "2026-10-02", "precision": "day", "evidence_refs": [0]},
                                         {"value": "2026-10-03", "precision": "day", "evidence_refs": [0]}]}
        events[4]["event_date"] = {"status": "approximate", "basis": "explicit_text",
                                     "value": "2026-09", "end": "2026-10", "precision": "month",
                                     "note": "Approximate window."}
        additional = copy.deepcopy(events[0])
        additional["id"] = "EVT-009"
        additional["statement"] = "A second event in one document"
        records["records"][0]["events"].append(additional)
        release = self.root / "mixed"
        (release / "records").mkdir(parents=True)
        render_views(release, records, manifest)
        timeline = (release / "timeline.md").read_text()
        self.assertIn("2027-01-01", timeline)
        self.assertIn("Unknown dates", timeline)
        self.assertIn("Conflicting dates", timeline)
        self.assertIn("2026-09–2026-10", timeline)
        self.assertIn("2026-09-25T12:00:00-05:00", timeline)
        self.assertIn("2026-09-25T17:00:00Z", timeline)
        self.assertIn("EVT-009", timeline)
        self.assertIn("overlap", timeline.lower())
        self.assertNotIn("as of", timeline.lower())

    def test_changed_event_is_disclosed_in_release_diff(self):
        records, manifest = self.fixture()
        old = copy.deepcopy(records)
        records["records"][0]["events"][0]["event_date"]["value"] = "2026-09-26"
        view = changes_view(records, manifest, old, manifest).decode()
        self.assertIn("REQ-001", view.split("## Changed records")[1].split("##")[0])
        self.assertIn("events", view)

    def test_packet_navigation_uses_document_dates_and_keeps_undated_visible(self):
        source = self.root / "source"
        source.mkdir()
        for name in ("2026-10-04-today.md", "2026-09-29-older.md", "undated.md"):
            (source / name).write_text("Synthetic source.\n", encoding="utf-8")
        project = self.root / "project"
        (project / "config").mkdir(parents=True)
        config = project / "config/project.json"
        config.write_text(json.dumps({
            "schema_version": "0.1", "project": {"id": "nav", "name": "Nav", "description": "Synthetic"},
            "sources": [{"id": "notes", "type": "meetings", "path": str(source),
                         "include": ["**/*.md"], "exclude": []}],
            "global_exclude": [], "knowledge": {"path": "knowledge", "approved": "knowledge/approved"},
            "runs": {"path": "runs"}}), encoding="utf-8")
        run, _ = inventory(config, "one")
        index = build_packets(run)
        view = (run / "packets/document-navigation.md").read_text()
        self.assertLess(view.index("2026-09-29"), view.index("2026-10-04"))
        self.assertIn("Undated documents", view)
        self.assertIn("undated.md", view)
        self.assertIn("filename:iso\\_date", view)
        self.assertIn("packet-0001.md", view)
        self.assertIn("document_navigation", index)

    def test_capture_permutations_leave_business_and_document_navigation_stable(self):
        dates = ("2026-09-29", "2026-10-03", "2026-10-04")
        timelines, navigations = [], []
        for number, order in enumerate(itertools.permutations(dates)):
            root = self.root / f"capture-{number}"
            source = root / "source"
            source.mkdir(parents=True)
            project = root / "project"
            (project / "config").mkdir(parents=True)
            config = project / "config/project.json"
            config.write_text(json.dumps({
                "schema_version": "0.1",
                "project": {"id": "ingestion", "name": "Ingestion", "description": "Synthetic"},
                "sources": [{"id": "notes", "type": "meetings", "path": str(source),
                             "include": ["**/*.md"], "exclude": []}],
                "global_exclude": [], "knowledge": {"path": "knowledge", "approved": "knowledge/approved"},
                "runs": {"path": "runs"}}), encoding="utf-8")
            baseline = None
            for step, date in enumerate(order, 1):
                (source / f"{date}.md").write_text(f"{date}: synthetic event.\n", encoding="utf-8")
                baseline, manifest = inventory(config, f"step-{step}", baseline=baseline)
            self.assertEqual(manifest["sequence"], 3)
            build_packets(baseline)
            navigations.append((baseline / "packets/document-navigation.md").read_text())
            records = []
            for f in manifest["files"]:
                date = f["relative_path"][:10]
                position = dates.index(date) + 1
                records.append({"id": f"REQ-{position:03d}", "kind": "requirement",
                                "title": f"Event {date}", "statement": f"{date}: synthetic event.",
                                "epistemic_status": "observed", "relations": [],
                                "open_questions": [], "investigation": None,
                                "evidence": [{"evidence_id": f["evidence_id"], "start_line": 1,
                                              "end_line": 1, "quote": f"{date}: synthetic event."}],
                                "events": [{"id": f"EVT-{position:03d}", "statement": f"Event {date}",
                                            "evidence_refs": [0],
                                            "event_date": {"status": "known", "basis": "explicit_text",
                                                           "value": date, "precision": "day"}}]})
            candidate = {"schema_version": "0.4", "project_id": "ingestion", "run_id": "step-3",
                         "coverage": [{"evidence_id": f["evidence_id"], "disposition": "used"}
                                      for f in manifest["files"]], "records": records}
            release = root / "view"
            (release / "records").mkdir(parents=True)
            render_views(release, candidate, manifest)
            timelines.append((release / "timeline.md").read_text())
        self.assertEqual(len(set(timelines)), 1)
        self.assertEqual(len(set(navigations)), 1)


if __name__ == "__main__":
    unittest.main()
