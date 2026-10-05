"""kb_reset_project: dry run by default, keeps only config/project.json, guarded deletion."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from kb_common import KBError, read_json, utc_now, write_json_new
from kb_inventory import inventory
from kb_publish import prepare_review, publish
from kb_reset_project import plan_reset, reset_project
from helpers import PROJECT_CONFIG, SOURCES, synthetic_records


class ResetProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.sources = self.root / "sources"
        shutil.copytree(SOURCES, self.sources)
        self.projects = self.root / "projects"
        self.project = self.projects / "demo"
        (self.project / "config").mkdir(parents=True)
        self.config = self.project / "config" / "project.json"
        cfg = read_json(PROJECT_CONFIG)
        for source in cfg["sources"]:
            source["path"] = str(self.sources / source["id"])
        self.config.write_text(json.dumps(cfg), encoding="utf-8")
        self.config_bytes = self.config.read_bytes()
        (self.project / "POLICY.md").write_text("policy\n")
        (self.project / ".hidden").write_text("x\n")
        self.run, self.manifest = inventory(self.config, "run-001")
        # Any other file in config/ is deleted too (written after inventory so capture stays valid).
        (self.project / "config" / "notes.txt").write_text("local note\n")

    def reset(self, **kw):
        return reset_project(self.config, projects_root=self.projects, **kw)

    def remaining(self):
        return sorted(p.relative_to(self.project).as_posix() for p in self.project.rglob("*"))

    def source_hashes(self):
        return {p: p.read_bytes() for p in self.sources.rglob("*") if p.is_file()}

    def test_dry_run_deletes_nothing(self):
        before = self.remaining()
        result = self.reset()
        self.assertFalse(result["deleted"])
        self.assertEqual(self.remaining(), before)
        self.assertEqual({e["path"] for e in result["entries"]},
                         {".hidden", "POLICY.md", "runs", "config/notes.txt"})

    def test_confirmed_reset_keeps_only_project_json_and_never_touches_sources(self):
        sources = self.source_hashes()
        result = self.reset(confirm="demo")
        self.assertTrue(result["deleted"])
        self.assertEqual(self.remaining(), ["config", "config/project.json"])
        self.assertEqual(self.config.read_bytes(), self.config_bytes)
        self.assertEqual(self.source_hashes(), sources)
        self.assertEqual(self.reset(confirm="demo")["entries"], [])  # idempotent

    def test_confirmation_must_repeat_the_project_id(self):
        with self.assertRaisesRegex(KBError, "repeat the project id"):
            self.reset(confirm="other")
        self.assertIn("runs", self.remaining())

    def test_approved_releases_need_an_explicit_flag(self):
        records = synthetic_records(self.run, self.manifest)
        write_json_new(self.run / "proposals" / "records.json", records)
        review = prepare_review(self.config, self.run)
        review.update(decision="approve", reviewer="Synthetic test operator (simulated)", reviewed_at=utc_now())
        review["checks"] = dict.fromkeys(review["checks"], True)
        review["acknowledged_warnings"] = dict(review["warning_summary"]["counts"])
        (self.run / "review.json").write_text(json.dumps(review))
        publish(self.config, self.run, self.run / "review.json", True)
        self.assertEqual(plan_reset(self.config, self.projects)["approved_releases"], ["run-001"])
        with self.assertRaisesRegex(KBError, "delete-approved-releases"):
            self.reset(confirm="demo")
        self.assertTrue((self.project / "knowledge" / "approved" / "CURRENT.json").exists())
        self.reset(confirm="demo", delete_approved_releases=True)
        self.assertEqual(self.remaining(), ["config", "config/project.json"])

    def test_publication_lock_blocks_reset(self):
        lock = self.project / "knowledge" / "approved" / ".publish.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text("publishing\n")
        with self.assertRaisesRegex(KBError, "publication may be in progress"):
            self.reset(confirm="demo", delete_approved_releases=True)

    def test_symlinks_inside_the_workspace_are_removed_not_followed(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep\n")
        (self.project / "link-dir").symlink_to(outside, target_is_directory=True)
        (self.project / "link-file").symlink_to(outside / "keep.txt")
        (self.run / "work" / "nested-link").symlink_to(outside, target_is_directory=True)
        self.reset(confirm="demo")
        self.assertEqual(self.remaining(), ["config", "config/project.json"])
        self.assertEqual((outside / "keep.txt").read_text(), "keep\n")

    def test_symlinked_configuration_is_refused(self):
        real = self.root / "elsewhere" / "config"
        real.mkdir(parents=True)
        shutil.copyfile(self.config, real / "project.json")
        link = self.projects / "linked" / "config"
        link.parent.mkdir()
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaises(KBError):
            reset_project(link / "project.json", projects_root=self.projects)

    def test_workspace_must_be_projects_slash_project_id(self):
        other = self.root / "home"
        (other / "config").mkdir(parents=True)
        shutil.copyfile(self.config, other / "config" / "project.json")
        with self.assertRaisesRegex(KBError, "Only workspaces at"):
            reset_project(other / "config" / "project.json", confirm="demo", projects_root=self.projects)
        renamed = self.projects / "renamed"
        (renamed / "config").mkdir(parents=True)
        shutil.copyfile(self.config, renamed / "config" / "project.json")
        with self.assertRaisesRegex(KBError, "Only workspaces at"):
            reset_project(renamed / "config" / "project.json", confirm="demo", projects_root=self.projects)

    def test_repository_workspace_is_refused(self):
        (self.project / ".git").mkdir()
        with self.assertRaisesRegex(KBError, "repository"):
            self.reset(confirm="demo")


if __name__ == "__main__":
    unittest.main()
