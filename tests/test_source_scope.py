"""Synthetic registration and frozen-scope checks for expanded source categories."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from kb_check import check_run, load_manifest
from kb_common import KBError, read_json, sha, utc_now, write_json_new
from kb_inventory import inventory
import kb_inventory
from kb_init import initial_source_scope, main as init_main
from kb_publish import prepare_review, publish
from helpers import PROJECT_CONFIG, SOURCES, synthetic_records


class SourceScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.sources = self.root / "sources"
        shutil.copytree(SOURCES, self.sources)
        self.project = self.root / "projects" / "demo"
        (self.project / "config").mkdir(parents=True)
        self.config = self.project / "config" / "project.json"
        cfg = read_json(PROJECT_CONFIG)
        for source in cfg["sources"]:
            source["path"] = str(self.sources / source["id"])
        self.config.write_text(json.dumps(cfg), encoding="utf-8")
        self.scope_path = self.project / "config" / "source-scope.json"
        self.scope = {"schema_version": "1.0", "project_id": "demo", "sources": []}
        for kind, name, text in (
            ("data", "values.csv", "code,value\n001,10\n"),
            ("analysis", "assessment.md", "# Analysis\nA draft policy is discussed here.\n"),
            ("policy", "rule.md", "# Draft policy\nProposed requirement, not active.\n"),
        ):
            directory = self.sources / kind
            directory.mkdir()
            (directory / name).write_text(text, encoding="utf-8")
            self.scope["sources"].append({"id": kind, "type": kind, "path": str(directory),
                                          "include": ["**/*"], "exclude": []})
        self.save_scope()

    def save_scope(self):
        self.scope_path.write_text(json.dumps(self.scope), encoding="utf-8")

    def test_inventory_captures_eight_categories_with_frozen_primary_types(self):
        run, manifest = inventory(self.config, "one")
        self.assertEqual({source["type"] for source in manifest["sources"]},
                         {"requirements", "architecture", "meetings", "sql", "repository",
                          "data", "analysis", "policy"})
        self.assertEqual({f["source_type"] for f in manifest["files"]},
                         {source["type"] for source in manifest["sources"]})
        self.assertEqual(next(f for f in manifest["files"] if f["source_id"] == "analysis")["source_type"],
                         "analysis")
        self.assertEqual(check_run(run)["status"], "passed")
        self.assertEqual(read_json(run / "source-scope.snapshot.json"), self.scope)

    def test_source_scope_rejects_duplicate_ids_overlaps_and_invalid_mapping(self):
        cases = (
            lambda: self.scope["sources"][0].update(id="requirements"),
            lambda: self.scope["sources"][0].update(path=str(self.sources / "requirements")),
            lambda: self.scope["sources"][0].update(path=str(self.sources / "analysis")),
            lambda: self.scope["sources"][0].update(type="repository"),
            lambda: self.scope["sources"][0].update(include=["[bad]"]),
            lambda: self.scope.update(project_id="other"),
        )
        for i, change in enumerate(cases):
            with self.subTest(case=i):
                original = json.loads(json.dumps(self.scope))
                change()
                self.save_scope()
                with self.assertRaises(KBError):
                    inventory(self.config, f"bad-{i}")
                self.scope = original

    def test_changed_source_scope_is_incomparable_and_old_run_stays_valid(self):
        first, _ = inventory(self.config, "one")
        self.scope["sources"][0]["exclude"] = ["**/scratch/**"]
        self.save_scope()
        second, manifest = inventory(self.config, "two", baseline=first)
        self.assertEqual(load_manifest(first)["status"], "ready")
        self.assertEqual(check_run(second)["status"], "passed")
        self.assertFalse(manifest["delta"]["compatible"])
        self.assertIn("scope_changed", {issue["code"] for issue in manifest["issues"]})

    def test_same_source_scope_reports_changed_evidence_normally(self):
        first, old = inventory(self.config, "one")
        (self.sources / "data" / "values.csv").write_text("code,value\n001,11\n", encoding="utf-8")
        _, new = inventory(self.config, "two", baseline=first)
        self.assertTrue(new["delta"]["compatible"])
        data_id = next(f["logical_id"] for f in old["files"] if f["source_id"] == "data")
        self.assertIn(data_id, new["delta"]["modified"])

    def test_text_only_v021_run_without_sidecar_still_verifies(self):
        self.scope_path.unlink()
        with mock.patch.object(kb_inventory, "TOOL_VERSION", "0.2.1"):
            run, manifest = inventory(self.config, "old")
        self.assertNotIn("source_scope", manifest)
        self.assertEqual(check_run(run)["status"], "passed")

    def test_tampered_frozen_source_scope_is_rejected(self):
        run, manifest = inventory(self.config, "one")
        snapshot = run / "source-scope.snapshot.json"
        original = snapshot.read_bytes()
        snapshot.write_bytes(original + b" ")
        with self.assertRaisesRegex(KBError, "source scope|Source scope"):
            load_manifest(run)
        snapshot.write_bytes(original)
        manifest["source_scope"]["sha256"] = "0" * 64
        raw = json.dumps(manifest).encode("utf-8")
        (run / "manifest.json").write_bytes(raw)
        (run / "manifest.sha256").write_text(sha(raw) + "\n")
        with self.assertRaisesRegex(KBError, "source scope|Source scope"):
            load_manifest(run)

    def test_project_v01_stays_frozen_and_initializer_registers_expanded_source(self):
        cfg = read_json(self.config)
        cfg["sources"][0]["type"] = "data"
        self.config.write_text(json.dumps(cfg), encoding="utf-8")
        with self.assertRaises(KBError):
            inventory(self.config, "bad")
        scope = initial_source_scope("demo", [f"new-data:data:{self.sources / 'data'}"],
                                    {"requirements"})
        self.assertEqual(scope["sources"][0]["type"], "data")
        with self.assertRaises(KBError):
            initial_source_scope("demo", [f"requirements:data:{self.sources / 'data'}"],
                                 {"requirements"})

    def test_initializer_writes_sidecar_in_synthetic_workspace(self):
        workspace = self.root / "new-project"
        args = ["kb_init.py", "--project-id", "new-project", "--name", "Synthetic",
                "--source", f"notes:requirements:{self.sources / 'requirements'}",
                "--expanded-source", f"values:data:{self.sources / 'data'}",
                "--workspace", str(workspace)]
        with mock.patch.object(sys, "argv", args):
            self.assertEqual(init_main(), 0)
        self.assertEqual(read_json(workspace / "config" / "project.json")["schema_version"], "0.1")
        sidecar = read_json(workspace / "config" / "source-scope.json")
        self.assertEqual(sidecar["sources"][0]["type"], "data")
        self.assertEqual(sidecar["project_id"], "new-project")

    def test_published_release_carries_frozen_source_scope(self):
        run, manifest = inventory(self.config, "one")
        records = synthetic_records(run, manifest)
        for row in records["coverage"]:
            if row["evidence_id"] in {f["evidence_id"] for f in manifest["files"]
                                      if f["source_type"] in {"data", "analysis", "policy"}}:
                row["disposition"] = "reviewed_no_record"
        write_json_new(run / "proposals" / "records.json", records)
        review = prepare_review(self.config, run)
        review.update(decision="approve", reviewer="Synthetic test operator",
                      reviewed_at=utc_now(), notes="TEST ONLY: simulated approval")
        review["checks"] = dict.fromkeys(review["checks"], True)
        review["acknowledged_warnings"] = dict(review["warning_summary"]["counts"])
        review_path = run / "review.json"
        review_path.write_text(json.dumps(review), encoding="utf-8")
        release = publish(self.config, run, review_path, True)
        self.assertEqual((release / "source-scope.snapshot.json").read_bytes(),
                         (run / "source-scope.snapshot.json").read_bytes())
        self.assertEqual((release / "segments.snapshot.json").read_bytes(),
                         (run / "segments.snapshot.json").read_bytes())
        self.assertEqual(check_run(release, release / "records.json", stage2=True)["status"], "passed")


if __name__ == "__main__":
    unittest.main()
