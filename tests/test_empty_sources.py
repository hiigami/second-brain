"""Regression checks for the empty-source compatibility fix to bundle v0.1.0."""
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
from kb_common import KBError, read_json, sha
from kb_inventory import inventory
from kb_packet import build_packets
from helpers import LEGACY_RUN, PROJECT_CONFIG, SOURCES


class EmptySourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.sources = self.root / "sources"
        shutil.copytree(SOURCES, self.sources)
        self.project = self.root / "projects" / "demo"
        (self.project / "config").mkdir(parents=True)
        self.config = self.project / "config" / "project.json"
        self.cfg = read_json(PROJECT_CONFIG)
        for source in self.cfg["sources"]:
            source["path"] = str(self.sources / source["id"])
        self.save_config()

    def save_config(self):
        self.config.write_text(json.dumps(self.cfg), encoding="utf-8")

    def clear_source(self, sid):
        root = self.sources / sid
        shutil.rmtree(root)
        root.mkdir()

    def issues(self, manifest, code):
        return [i for i in manifest["issues"] if i["code"] == code]

    def assert_ready(self, run, manifest):
        self.assertEqual(manifest["status"], "ready")
        self.assertFalse(any(i["severity"] == "error" for i in manifest["issues"]))
        self.assertEqual(check_run(run)["status"], "passed")

    def test_empty_source_is_warning_and_packets_work(self):
        self.clear_source("meetings")
        run, manifest = inventory(self.config, "one")
        self.assert_ready(run, manifest)
        empty = self.issues(manifest, "empty_source_scope")
        self.assertEqual(len(empty), 1)
        self.assertEqual((empty[0]["source_id"], empty[0]["severity"]), ("meetings", "warning"))
        summary = next(s for s in manifest["sources"] if s["id"] == "meetings")
        self.assertEqual(summary["eligible_count"], 0)
        self.assertEqual(len(build_packets(run)["selected_evidence_ids"]), 4)

    def test_only_repository_populated_is_ready(self):
        for sid in ("architecture", "meetings", "requirements", "sql"):
            self.clear_source(sid)
        run, manifest = inventory(self.config, "one")
        self.assert_ready(run, manifest)
        self.assertEqual(len(manifest["files"]), 1)
        self.assertEqual(len(self.issues(manifest, "empty_source_scope")), 4)
        self.assertEqual({f["source_id"] for f in manifest["files"]}, {"repository"})

    def test_all_sources_empty_still_blocks(self):
        for s in self.cfg["sources"]:
            self.clear_source(s["id"])
        run, manifest = inventory(self.config, "one")
        self.assertEqual(manifest["status"], "blocked")
        self.assertEqual(len(self.issues(manifest, "empty_source_scope")), 5)
        self.assertEqual(len(self.issues(manifest, "empty_inventory")), 1)
        self.assertEqual(self.issues(manifest, "empty_inventory")[0]["severity"], "error")
        load_manifest(run)  # A blocked diagnostic manifest must remain readable.
        with self.assertRaises(KBError):
            check_run(run)
        with self.assertRaises(KBError):
            build_packets(run)

    def test_nested_empty_directories_are_nonblocking(self):
        self.clear_source("meetings")
        (self.sources / "meetings" / "future" / "notes").mkdir(parents=True)
        run, manifest = inventory(self.config, "one")
        self.assert_ready(run, manifest)
        self.assertEqual(len(self.issues(manifest, "empty_source_scope")), 1)

    def test_fully_filtered_scope_is_visible_as_warning(self):
        source = next(s for s in self.cfg["sources"] if s["id"] == "meetings")
        source["include"] = ["**/*.sql"]
        self.save_config()
        run, manifest = inventory(self.config, "one")
        self.assert_ready(run, manifest)
        self.assertEqual(len(self.issues(manifest, "empty_source_scope")), 1)
        summary = next(s for s in manifest["sources"] if s["id"] == "meetings")
        self.assertGreater(summary["excluded_entries"], 0)

    def test_missing_source_still_blocks(self):
        shutil.rmtree(self.sources / "meetings")
        run, manifest = inventory(self.config, "one")
        self.assertEqual(manifest["status"], "blocked")
        self.assertEqual(self.issues(manifest, "source_unavailable")[0]["severity"], "error")
        with self.assertRaises(KBError):
            check_run(run)

    def test_directory_read_error_still_blocks(self):
        # Deterministic injected permission error; valid even when tests run as root.
        def denied_walk(root, **kwargs):
            kwargs["onerror"](PermissionError("fixture directory denied"))
            return iter(())
        with mock.patch("kb_inventory.os.walk", side_effect=denied_walk):
            run, manifest = inventory(self.config, "one")
        self.assertEqual(manifest["status"], "blocked")
        self.assertTrue(self.issues(manifest, "directory_unreadable"))
        self.assertTrue(all(i["severity"] == "error" for i in self.issues(manifest, "directory_unreadable")))
        with self.assertRaises(KBError):
            check_run(run)

    def test_failed_capture_in_zero_capture_scope_still_blocks(self):
        self.clear_source("meetings")
        (self.sources / "meetings" / "broken.md").write_bytes(b"\xff")
        run, manifest = inventory(self.config, "one")
        self.assertEqual(manifest["status"], "blocked")
        self.assertEqual(self.issues(manifest, "empty_source_scope")[0]["severity"], "warning")
        self.assertEqual(self.issues(manifest, "file_not_captured")[0]["severity"], "error")
        with self.assertRaises(KBError):
            check_run(run)

    def test_gitkeep_without_exclusion_remains_explicit_error(self):
        (self.sources / "repository" / "src" / ".gitkeep").write_text("", encoding="utf-8")
        run, manifest = inventory(self.config, "one")
        self.assertEqual(manifest["status"], "blocked")
        failures = self.issues(manifest, "file_not_captured")
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["path"], "src/.gitkeep")
        with self.assertRaises(KBError):
            check_run(run)

    def test_explicit_gitkeep_and_ds_store_exclusions_work_at_all_depths(self):
        source = next(s for s in self.cfg["sources"] if s["id"] == "repository")
        source["include"] = ["**/*"]
        self.cfg["global_exclude"].extend(["**/.gitkeep", "**/.DS_Store"])
        self.save_config()
        for directory in (self.sources / "repository", self.sources / "repository" / "src"):
            (directory / ".gitkeep").write_text("", encoding="utf-8")
            (directory / ".DS_Store").write_bytes(b"\x00\xfffixture")
        run, manifest = inventory(self.config, "one")
        self.assert_ready(run, manifest)
        self.assertEqual(len(manifest["files"]), 5)
        self.assertFalse(self.issues(manifest, "file_not_captured"))
        summary = next(s for s in manifest["sources"] if s["id"] == "repository")
        self.assertEqual(summary["excluded_entries"], 4)

    def test_placeholder_only_source_is_warning_after_exclusion(self):
        self.clear_source("meetings")
        source = next(s for s in self.cfg["sources"] if s["id"] == "meetings")
        source["include"] = ["**/*"]
        source["exclude"] = ["**/.gitkeep"]
        self.save_config()
        (self.sources / "meetings" / ".gitkeep").write_text("", encoding="utf-8")
        run, manifest = inventory(self.config, "one")
        self.assert_ready(run, manifest)
        self.assertEqual(self.issues(manifest, "empty_source_scope")[0]["severity"], "warning")
        self.assertFalse(self.issues(manifest, "file_not_captured"))

    def test_last_file_removed_from_one_source_is_valid_delta(self):
        baseline, old = inventory(self.config, "one")
        removed = next(f["logical_id"] for f in old["files"] if f["source_id"] == "meetings")
        self.clear_source("meetings")
        run, manifest = inventory(self.config, "two", baseline=baseline)
        self.assert_ready(run, manifest)
        self.assertTrue(manifest["delta"]["compatible"])
        self.assertEqual(manifest["delta"]["removed"], [removed])

    def test_all_empty_delta_remains_incomparable(self):
        baseline, _ = inventory(self.config, "one")
        for s in self.cfg["sources"]:
            self.clear_source(s["id"])
        run, manifest = inventory(self.config, "two", baseline=baseline)
        self.assertEqual(manifest["status"], "blocked")
        self.assertFalse(manifest["delta"]["compatible"])
        self.assertEqual(manifest["delta"]["removed"], [])
        self.assertTrue(self.issues(manifest, "inventory_incomplete_delta_unavailable"))
        load_manifest(run)

    def test_missing_source_delta_is_not_false_deletion(self):
        baseline, _ = inventory(self.config, "one")
        shutil.rmtree(self.sources / "meetings")
        run, manifest = inventory(self.config, "two", baseline=baseline)
        self.assertEqual(manifest["status"], "blocked")
        self.assertFalse(manifest["delta"]["compatible"])
        self.assertEqual(manifest["delta"]["removed"], [])
        load_manifest(run)

    def test_forged_ready_whole_empty_inventory_is_rejected(self):
        for s in self.cfg["sources"]:
            self.clear_source(s["id"])
        run, manifest = inventory(self.config, "one")
        # Test-only reseal: exercise semantic validation independently of checksum validation.
        # Real run manifests must never be edited/resealed to bypass a blocked result.
        manifest["status"] = "ready"
        manifest["issues"] = [i for i in manifest["issues"] if i["severity"] != "error"]
        path = run / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        (run / "manifest.sha256").write_text(sha(path.read_bytes()) + "\n", encoding="ascii")
        with self.assertRaises(KBError):
            load_manifest(run)

    def test_old_ready_demo_still_checks(self):
        run = LEGACY_RUN
        self.assertEqual(check_run(run, run / "records.json", stage2=True)["status"], "passed")


if __name__ == "__main__":
    unittest.main()
