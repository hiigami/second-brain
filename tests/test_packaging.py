"""Exercise the distribution outside the checkout, without installing it.

Set SECOND_BRAIN_TEST_WHEEL to a built wheel to repeat these checks against its
contents. Otherwise transplant the source package into a temporary directory.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        wheel = os.environ.get("SECOND_BRAIN_TEST_WHEEL")
        if wheel:
            with zipfile.ZipFile(wheel) as archive:
                for member in archive.infolist():
                    if member.filename.startswith("second_brain/") and not member.is_dir():
                        path = self.root / member.filename
                        self.assertTrue(path.resolve().is_relative_to(self.root))
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(archive.read(member))
                metadata = next(name for name in archive.namelist()
                                if name.endswith(".dist-info/entry_points.txt"))
                self.assertIn("second-brain = second_brain:main", archive.read(metadata).decode())
        else:
            shutil.copytree(ROOT / "src/second_brain", self.root / "second_brain")
        self.env = dict(os.environ, PYTHONPATH=str(self.root), PYTHONNOUSERSITE="1")

    def cli(self, *args, cwd=None):
        return subprocess.run([sys.executable, "-P", "-m", "second_brain", *args], cwd=cwd or self.root,
                              env=self.env, text=True, capture_output=True, timeout=30)

    def test_help_and_all_command_entrypoints_outside_checkout(self):
        result = self.cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Hello", result.stdout)
        for command in ("init", "inventory", "packet", "check", "reanchor", "publish",
                        "mentions", "referrals", "index", "context", "run", "extract-document", "visual-review", "sync-skills", "reset-project"):
            with self.subTest(command=command):
                result = self.cli(command, "--help")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout)

    def test_legacy_schemas_are_available_outside_checkout(self):
        run = self.root / "legacy-run"
        shutil.copytree(ROOT / "tests/fixtures/legacy-run-v0.1", run)
        result = self.cli("check", "--run", str(run), "--records", str(run / "records.json"), "--stage2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"status": "passed"', result.stdout)

    def test_current_schema_and_document_worker_outside_checkout(self):
        sources = self.root / "sources"
        sources.mkdir()
        (sources / "claim.html").write_text("<p>Still <code>NOT</code> approved</p>")
        workspace = self.root / "projects/demo"
        result = self.cli("init", "--project-id", "demo", "--name", "Synthetic",
                          "--workspace", str(workspace), "--source", f"req:requirements:{sources}")
        self.assertEqual(result.returncode, 0, result.stderr)
        config = workspace / "config/project.json"
        cfg = json.loads(config.read_text())
        cfg["sources"][0]["include"] = ["**/*.html"]
        config.write_text(json.dumps(cfg))
        result = self.cli("inventory", "--project", str(config), "--run-id", "packaged", "--documents")
        self.assertEqual(result.returncode, 0, result.stderr)
        run = workspace / "runs/packaged"
        manifest = json.loads((run / "manifest.json").read_text())
        self.assertEqual(manifest["documents"]["adapter_version"], "0.7.0")
        evidence = (run / manifest["files"][0]["snapshot_path"]).read_text()
        self.assertIn("Still NOT approved", evidence)
        result = self.cli("check", "--run", str(run), "--inventory-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli("packet", "--run", str(run))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((run / "packets/index.json").is_file())

    def test_standalone_document_worker_and_verification_outside_checkout(self):
        source = self.root / "input.html"
        source.write_text('<template><img alt="Hidden"></template><p>Visible</p>')
        snapshot = self.root / "snapshot"
        result = self.cli("extract-document", "--source", str(source), "--out", str(snapshot))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Hidden", (snapshot / "evidence.md").read_text())
        result = self.cli("extract-document", "--verify", str(snapshot))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_docx_comment_worker_outside_checkout(self):
        try:
            from test_docx_comments import comment_docx
        except ImportError:
            from tests.test_docx_comments import comment_docx
        source = self.root / "annotations.docx"
        source.write_bytes(comment_docx(body=False))
        snapshot = self.root / "docx-snapshot"
        result = self.cli("extract-document", "--source", str(source), "--out", str(snapshot))
        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = (snapshot / "evidence.md").read_text()
        self.assertIn("Reply text", evidence)
        self.assertIn('"resolved_at": null', evidence)
        self.assertIn('"date": "2026-09-01T12:30:00"', evidence)
        result = self.cli("extract-document", "--verify", str(snapshot))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_visual_packet_worker_and_contracts_outside_checkout(self):
        source = self.root / "pixel.png"
        source.write_bytes((ROOT / "tests/fixtures/patch_g_visual_probe.png").read_bytes())
        packet = self.root / "visual-packet"
        result = self.cli("visual-review", "prepare", "--source", str(source), "--out", str(packet))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["human_assessment"], "pending")
        result = self.cli("visual-review", "verify", "--packet", str(packet))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["fidelity"], "unmeasured")
        result = self.cli("visual-review", "assess", "--packet", str(packet),
                          "--assessment", str(packet / "assessment.template.json"))
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_installed_commands_require_explicit_workspace_and_engine_roots(self):
        source = self.root / "sources"
        source.mkdir()
        result = self.cli("init", "--project-id", "demo", "--name", "Synthetic",
                          "--source", f"req:requirements:{source}")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("--workspace", result.stderr)
        result = self.cli("sync-skills", "--check")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("--engine", result.stderr)
        result = self.cli("reset-project", "--project", str(self.root / "projects/demo/config/project.json"))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("--projects-root", result.stderr)
        self.assertFalse((self.root / "second_brain/projects").exists())

    def test_workers_do_not_import_a_package_from_the_callers_directory(self):
        hostile = self.root / "untrusted-checkout"
        shadow = hostile / "second_brain"
        shadow.mkdir(parents=True)
        marker = self.root / "source-executed"
        (shadow / "__init__.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
            "raise RuntimeError('Untrusted source package executed')\n")
        sources = self.root / "sources"
        sources.mkdir()
        source = sources / "claim.html"
        source.write_text("<p>Inert source</p>")
        workspace = self.root / "projects/demo"
        result = self.cli("init", "--project-id", "demo", "--name", "Synthetic",
                          "--workspace", str(workspace), "--source", f"req:requirements:{sources}", cwd=hostile)
        self.assertEqual(result.returncode, 0, result.stderr)
        config = workspace / "config/project.json"
        cfg = json.loads(config.read_text())
        cfg["sources"][0]["include"] = ["**/*.html"]
        config.write_text(json.dumps(cfg))
        result = self.cli("inventory", "--project", str(config), "--run-id", "safe-worker", "--documents", cwd=hostile)
        self.assertFalse(marker.exists(), "Inventory worker imported untrusted cwd content")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli("extract-document", "--source", str(source), "--out", str(self.root / "snapshot"), cwd=hostile)
        self.assertFalse(marker.exists(), "Standalone worker imported untrusted cwd content")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
