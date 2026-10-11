"""User-facing diagnostics exercised with synthetic inputs only."""
import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from kb_common import KBError, blocked_inventory_error, contract, read_json, run_cli, validate_schema
from kb_inventory import inventory
from helpers import PROJECT_CONFIG, SOURCES, synthetic_records


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.sources = self.root / "sources"
        shutil.copytree(SOURCES, self.sources)
        self.config = self.root / "project/config/project.json"
        self.config.parent.mkdir(parents=True)
        self.cfg = read_json(PROJECT_CONFIG)
        for source in self.cfg["sources"]:
            source["path"] = str(self.sources / source["id"])
        self.config.write_text(json.dumps(self.cfg), encoding="utf-8")

    def cli(self, command, *arguments, legacy=False):
        entry = [str(ROOT / "tools" / f"kb_{command}.py")] if legacy else ["-m", "second_brain", command]
        result = subprocess.run([sys.executable, *entry, *map(str, arguments)],
                                text=True, capture_output=True, timeout=30, cwd=ROOT)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        return result

    def test_read_json_invalid_content_names_file_cause_and_recovery(self):
        path = self.root / "input.json"
        for content, cause in ((b'{"id": 1, "id": 2}', "Duplicate JSON key: id"),
                               (b'{"value": NaN}', "Invalid JSON: NaN"),
                               (b'{\n  "id":\n}', "line 3"),
                               (b'\xff', "UTF-8")):
            with self.subTest(content=content):
                path.write_bytes(content)
                with self.assertRaises(KBError) as raised:
                    read_json(path)
                message = str(raised.exception)
                self.assertIn(str(path), message)
                self.assertIn(cause, message)
                self.assertIn("Suggestion:", message)

    def test_validate_schema_invalid_alternative_preserves_nested_reason(self):
        schema = {"anyOf": [{"type": "null"}, {
            "type": "object", "properties": {"question": {"type": "string"}},
            "required": ["question"], "additionalProperties": False}]}
        with self.assertRaises(KBError) as raised:
            validate_schema({"question": 42}, schema, "$.records[0].investigation")
        self.assertIn("$.records[0].investigation.question", str(raised.exception))
        self.assertIn("string", str(raised.exception))
        self.assertIn("int", str(raised.exception))
        validate_schema(None, schema)
        validate_schema({"question": "What happened?"}, schema)

    def test_cli_invalid_project_names_file_and_field_for_both_entrypoints(self):
        self.cfg["sources"][0]["include"] = "**/*.md"
        self.config.write_text(json.dumps(self.cfg), encoding="utf-8")
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                result = self.cli("inventory", "--project", self.config, "--run-id", "bad", legacy=legacy)
                self.assertIn(str(self.config), result.stderr)
                self.assertIn("$.sources[0].include", result.stderr)
                self.assertIn("array", result.stderr)
                self.assertIn("Suggestion:", result.stderr)

    def test_cli_blocked_inventory_lists_source_file_and_specific_cause(self):
        source = self.sources / "meetings/broken.md"
        source.write_bytes(b"\xff")
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                run_id = "blocked-legacy" if legacy else "blocked"
                result = self.cli("inventory", "--project", self.config, "--run-id", run_id, legacy=legacy)
                run = self.root / "project/runs" / run_id
                self.assertIn("BLOCKED:", result.stdout)
                for command, args in ((None, ()), ("check", ("--inventory-only",)), ("packet", ())):
                    diagnostic = result if command is None else self.cli(command, "--run", run, *args, legacy=legacy)
                    self.assertIn(str(source), diagnostic.stderr)
                    self.assertIn("file_not_captured", diagnostic.stderr)
                    self.assertIn("not UTF-8", diagnostic.stderr)
                    self.assertIn(str(run / "manifest.json"), diagnostic.stderr)
                    self.assertIn("new run", diagnostic.stderr)

    def test_cli_invalid_record_names_candidate_and_nested_field(self):
        run, manifest = inventory(self.config, "records")
        records = synthetic_records(run, manifest)
        records["records"][-1]["investigation"]["question"] = 42
        candidate = run / "proposals/records.json"
        candidate.write_text(json.dumps(records), encoding="utf-8")
        result = self.cli("check", "--run", run)
        self.assertIn(str(candidate), result.stderr)
        self.assertIn("$.records[4].investigation.question", result.stderr)
        self.assertIn("string", result.stderr)

    def test_cli_quote_mismatch_names_record_candidate_and_frozen_file(self):
        run, manifest = inventory(self.config, "quote")
        records = synthetic_records(run, manifest)
        record = records["records"][0]
        citation = record["evidence"][0]
        citation["quote"] = "Incorrect synthetic quote"
        candidate = run / "proposals/records.json"
        candidate.write_text(json.dumps(records), encoding="utf-8")
        result = self.cli("check", "--run", run)
        evidence = next(f for f in manifest["files"] if f["evidence_id"] == citation["evidence_id"])
        for detail in (str(candidate), record["id"], str(run / evidence["snapshot_path"]),
                       "Quote differs", "Suggestion:"):
            self.assertIn(detail, result.stderr)

    def test_run_cli_missing_file_keeps_failure_code_and_adds_recovery(self):
        path = self.root / "missing.json"
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(SystemExit) as raised:
            run_cli(lambda: path.read_bytes())
        self.assertEqual(raised.exception.code, 2)
        self.assertIn(str(path), output.getvalue())
        self.assertIn("Suggestion:", output.getvalue())

    def test_cli_changed_frozen_artifacts_name_the_actual_file(self):
        for artifact in ("text", "segments", "manifest"):
            with self.subTest(artifact=artifact):
                run, manifest = inventory(self.config, f"changed-{artifact}")
                paths = {"text": run / manifest["files"][0]["snapshot_path"],
                         "segments": run / manifest["segment_inventory"]["path"],
                         "manifest": run / "manifest.json"}
                path = paths[artifact]
                path.write_bytes(path.read_bytes() + b"\nChanged synthetic artifact\n")
                result = self.cli("check", "--run", run, "--inventory-only")
                self.assertIn(f"File: {path}", result.stderr)
                self.assertIn("restore", result.stderr.lower())
                self.assertIn("do not", result.stderr.lower())

    def test_contract_engine_schema_error_names_schema_and_maintainer(self):
        schema = self.root / "example.schema.json"
        schema.write_text('{"type": "object", "unsupported": true}', encoding="utf-8")
        with mock.patch("kb_common.SCHEMAS", self.root), self.assertRaises(KBError) as raised:
            contract({}, "example", source=self.config)
        self.assertIn(f"File: {schema}", str(raised.exception))
        self.assertIn("unsupported schema keywords", str(raised.exception))
        self.assertIn("maintainer", str(raised.exception))
        self.assertNotIn(f"File: {self.config}", str(raised.exception))

    def test_blocked_inventory_error_bounds_output_and_points_to_complete_report(self):
        manifest = {"sources": [{"id": "notes", "root": str(self.sources)}],
                    "issues": [{"severity": "error", "source_id": "notes", "code": "file_not_captured",
                                "path": f"file-{i}.txt", "detail": "Input is not UTF-8"} for i in range(23)]}
        message = str(blocked_inventory_error(self.root, manifest))
        self.assertIn("23 blocking issue(s)", message)
        self.assertIn("file-19.txt", message)
        self.assertNotIn("file-20.txt", message)
        self.assertIn("3 additional blocking issue(s)", message)
        self.assertIn(str(self.root / "manifest.json"), message)


if __name__ == "__main__":
    unittest.main()
