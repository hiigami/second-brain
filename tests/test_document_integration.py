"""End-to-end document-run integrity: inventory -> check -> packets -> tamper cases.

Offline synthetic regression; requires the optional document stack
(python-docx; python-pptx/reportlab for the format matrix) from
pyproject.toml (installed by uv sync), like test_document_formats.py.
"""
import hashlib
import json
import re
import shutil
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from kb_common import DOCUMENT_EXTENSIONS, KBError
from kb_inventory import inventory
from kb_check import check_run, load_manifest
from kb_packet import build_packets
from kb_review_report import render_review_report

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:  # pragma: no cover - optional stack
    HAS_DOCX = False

if HAS_DOCX:
    # Works under both `unittest discover -s tests` (top-level modules) and
    # package-style execution (`python -m unittest discover`).
    try:
        from test_document_formats import pdf_fixture, pptx_fixture, xlsx_fixture
    except ImportError:
        from tests.test_document_formats import pdf_fixture, pptx_fixture, xlsx_fixture
    HAS_FIXTURES = True
else:
    HAS_FIXTURES = False


def docx_bytes(paragraphs):
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


class DocumentRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "proj"
        (self.project / "config").mkdir(parents=True)
        self.config = self.project / "config" / "project.json"

    def tearDown(self):
        self.temp.cleanup()

    def write_config(self, files):
        """files: mapping of source-relative name -> bytes."""
        source = self.root / "src"
        if not source.exists():
            source.mkdir()
        for name, data in files.items():
            (source / name).write_bytes(data)
        self.config.write_text(json.dumps({
            "schema_version": "0.1",
            "project": {"id": "docdemo", "name": "Doc", "description": "integration"},
            "sources": [{"id": "docs", "type": "requirements", "path": str(source),
                         "include": ["**/*"], "exclude": []}],
            "global_exclude": [],
            "knowledge": {"path": "knowledge", "approved": "knowledge/approved"},
            "runs": {"path": "runs"},
        }), encoding="utf-8")
        return source

    def new_run(self, files, run_id, **kwargs):
        self.write_config(files)
        return inventory(self.config, run_id, documents=True, **kwargs)

    def standard_source(self):
        self.run, self.manifest = self.new_run({
            "acuerdo.docx": docx_bytes(["Primer acuerdo: congelar el alcance.",
                                        "Segundo: revisar proveedores."]),
            "notas.txt": "texto simple\n".encode("utf-8"),
        }, "doc-run-1")

    def document_file(self, manifest=None):
        manifest = manifest or self.manifest
        return next(f for f in manifest["files"] if "document" in f)

    def test_review_report_links_resolve_before_and_after_copying_to_release(self):
        def candidate(run, manifest, record_id):
            file = manifest["files"][0]
            segments = json.loads((run / "segments.snapshot.json").read_text())["segments"]
            segment = segments[0]
            lines = (run / file["snapshot_path"]).read_text().splitlines()
            records = {"schema_version": "0.3", "project_id": manifest["project_id"], "run_id": manifest["run_id"],
                       "coverage": [{"evidence_id": file["evidence_id"], "disposition": "used", "note": "Synthetic citation."}],
                       "segment_coverage": [{"segment_id": s["segment_id"],
                                             "disposition": "used" if s == segment else "reviewed_no_record",
                                             "note": "Synthetic source read in full."} for s in segments],
                       "records": [{"id": record_id, "kind": "requirement", "title": "Synthetic clause",
                                    "statement": "The synthetic clause remains proposed.", "epistemic_status": "proposal",
                                    "evidence": [{"evidence_id": file["evidence_id"], "segment_id": segment["segment_id"],
                                                  "representation_sha256": segment["representation_sha256"],
                                                  "start_line": segment["line_start"], "end_line": segment["line_end"],
                                                  "quote": "\n".join(lines[segment["line_start"] - 1:segment["line_end"]])}],
                                    "relations": [], "open_questions": [], "investigation": None}]}
            path = run / "proposals/records.json"
            path.write_text(json.dumps(records))
            return records, check_run(run, path, stage2=True)

        # This copies synthetic evidence/report files only, without a review or publication.
        self.project = self.root / "review project (synthetic) #"
        self.config = self.project / "config/project.json"
        self.config.parent.mkdir(parents=True)
        files = {"notes.html": b"<p>Synthetic clause remains proposed.</p>"}
        old_run, old_manifest = self.new_run(files, "link-one")
        old, _ = candidate(old_run, old_manifest, "REQ-001")
        prior = self.project / "knowledge/approved/link-one"
        shutil.copytree(old_run, prior)
        run, manifest = self.new_run(files, "link-two")
        records, checked = candidate(run, manifest, "REQ-002")

        report = render_review_report(run, manifest, records, checked, (prior, old, old_manifest))
        prepared_path = run / "review-report.md"
        prepared_path.write_bytes(report)
        copied_path = self.project / "knowledge/approved/link-two/review-report.md"
        shutil.copytree(run, copied_path.parent)
        shutil.copyfile(prepared_path, copied_path)

        links = re.findall(r"\[(Frozen representation|Original artifact)\]\(([^)]+)\)", report.decode())
        self.assertEqual(len(links), 4)
        for report_path in (prepared_path, copied_path):
            for label, target in links:
                with self.subTest(location=report_path, label=label, target=target):
                    parsed = urlparse(target)
                    resolved = Path(unquote(parsed.path)) if parsed.scheme == "file" else (report_path.parent / target).resolve()
                    self.assertTrue(resolved.is_file(), f"Broken evidence link: {target}")
        self.assertEqual(copied_path.read_bytes(), report)

    def tampered_copy(self, mutate):
        copy = self.root / "tampered"
        if copy.exists():
            shutil.rmtree(copy)
        shutil.copytree(self.run, copy)
        manifest = json.loads((copy / "manifest.json").read_text(encoding="utf-8"))
        mutate(copy, manifest, self.document_file(manifest))
        (copy / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (copy / "manifest.sha256").write_text(
            hashlib.sha256((copy / "manifest.json").read_bytes()).hexdigest() + "\n",
            encoding="utf-8")
        return copy

    def assert_blocked(self, mutate, expected_fragment):
        try:
            load_manifest(self.tampered_copy(mutate))
        except (KBError, OSError) as exc:
            self.assertIn(expected_fragment, str(exc))
        else:
            self.fail("tamper case was not blocked: " + mutate.__name__)

    def test_inventory_froze_documents_policy_and_artifacts(self):
        self.standard_source()
        self.assertEqual("ready", self.manifest["status"])
        self.assertIn("documents", self.manifest)
        document = self.document_file()["document"]
        for key in ["original_sha256", "text_sha256", "text_bytes", "text_line_count",
                    "metadata_sha256", "metadata_snapshot_path", "options_sha256",
                    "adapter_version", "segment_count"]:
            self.assertIn(key, document)
        self.assertNotEqual(document["original_sha256"], document["text_sha256"])

    def test_html_eml_inventory_segments_and_fidelity_gaps(self):
        fixtures = ROOT / "tests/fixtures"
        self.run, self.manifest = self.new_run({
            "model.html": (fixtures / "patch_e_dense.html").read_bytes(),
            "message.eml": (fixtures / "patch_e_multipart.eml").read_bytes(),
        }, "web-mail-run")
        self.assertEqual("ready", self.manifest["status"])
        self.assertEqual("passed", check_run(self.run)["status"])
        by_name = {f["relative_path"]: f for f in self.manifest["files"]}
        self.assertEqual({"model.html", "message.eml"}, set(by_name))
        self.assertTrue(all("document" in f for f in by_name.values()))
        segments = json.loads((self.run / "segments.snapshot.json").read_text())
        self.assertIn("code", {s["content_type"] for s in segments["segments"]})
        self.assertIn("email_quote", {s["content_type"] for s in segments["segments"]})
        self.assertIn("eml_attachment_not_extracted",
                      {i["code"] for i in segments["issues"] if i["status"] == "unavailable"})
        self.assertTrue(build_packets(self.run)["packets"])

    def test_svg_png_capture_preserves_originals_and_unavailable_visuals(self):
        fixtures = ROOT / "tests/fixtures"
        files = {"diagram.svg": (fixtures / "patch_g_diagram.svg").read_bytes(),
                 "pixels.png": (fixtures / "patch_g_pixels.png").read_bytes()}
        self.run, self.manifest = self.new_run(files, "visual-run")
        self.assertEqual("ready", self.manifest["status"])
        self.assertEqual("passed", check_run(self.run)["status"])
        self.assertEqual(set(files), {f["relative_path"] for f in self.manifest["files"]})
        for f in self.manifest["files"]:
            self.assertEqual(files[f["relative_path"]],
                             (self.run / f["document"]["original_snapshot_path"]).read_bytes())
        segments = json.loads((self.run / "segments.snapshot.json").read_text())
        self.assertIn("image_region", {s["content_type"] for s in segments["segments"]})
        self.assertIn("png_pixels_not_interpreted",
                      {i["code"] for i in segments["issues"] if i["status"] == "unavailable"})
        self.assertTrue(build_packets(self.run)["packets"])
        review_aid = render_review_report(self.run, self.manifest,
                                          {"records": [], "coverage": []},
                                          {"semantic_hints": []}).decode()
        self.assertIn("png_pixels_not_interpreted", review_aid)
        self.assertIn("Fidelity gaps and unavailable material", review_aid)

    def test_visual_policy_change_is_incomparable_and_old_run_still_verifies(self):
        raw = {"diagram.svg": (ROOT / "tests/fixtures/patch_g_diagram.svg").read_bytes()}
        base, old = self.new_run(raw, "svg-base")
        self.assertEqual("passed", check_run(base)["status"])
        with patch("kb_inventory.DOCUMENT_EXTENSIONS", DOCUMENT_EXTENSIONS - {".png"}):
            _, changed = self.new_run(raw, "svg-new-policy", baseline=base)
        self.assertEqual("ready", changed["status"])
        self.assertFalse(changed["delta"]["compatible"])
        self.assertEqual("passed", check_run(base)["status"])

    def test_adapter_bugfix_preserves_frozen_runs_and_marks_new_capture_incomparable(self):
        from kb_document_extractors import Options, extract_bytes

        def frozen_adapter(tmp, source_path, name, raw, options, timeout_seconds):
            result = extract_bytes(raw, name, options=Options(structured_csv=True, csv_header="first-row"))
            return result.metadata, result.text

        files = {"values.csv": b"Amount,Status\n10,pending\n"}
        for version in ("0.6.0", "0.6.1"):
            with self.subTest(version=version):
                suffix = version.replace(".", "-")
                with patch("kb_document_extractors.VERSION", version), \
                        patch("kb_inventory.extract_document_snapshot", side_effect=frozen_adapter):
                    base, old = self.new_run(files, "before-" + suffix,
                                             csv_representation="structured", csv_header="first-row")
                old_manifest = (base / "manifest.json").read_bytes()

                current, new = self.new_run(files, "after-" + suffix, baseline=base,
                                            csv_representation="structured", csv_header="first-row")

                self.assertEqual(old["documents"]["adapter_version"], version)
                self.assertNotEqual(new["documents"]["adapter_version"], version)
                self.assertEqual(check_run(base)["status"], "passed")
                self.assertEqual(check_run(current)["status"], "passed")
                self.assertFalse(new["delta"]["compatible"])
                self.assertEqual((base / "manifest.json").read_bytes(), old_manifest)
                self.assertNotEqual(old["files"][0]["evidence_id"], new["files"][0]["evidence_id"])

    def test_visual_metadata_tampering_is_rejected(self):
        self.run, self.manifest = self.new_run(
            {"pixels.png": (ROOT / "tests/fixtures/patch_g_pixels.png").read_bytes()}, "png-tamper")
        def mutate(copy, manifest, file):
            metadata_path = copy / file["document"]["metadata_snapshot_path"]
            metadata = json.loads(metadata_path.read_text())
            metadata["details"]["png_width"] = 99
            metadata_path.write_text(json.dumps(metadata))
        self.assert_blocked(mutate, "metadata")

    def test_html_eml_capture_policy_change_makes_delta_incomparable(self):
        raw = {"message.eml": (ROOT / "tests/fixtures/patch_e_multipart.eml").read_bytes()}
        base, _ = self.new_run(raw, "email-base")
        _, same = self.new_run(raw, "email-same", baseline=base)
        self.assertTrue(same["delta"]["compatible"])
        _, changed = self.new_run(raw, "email-policy", baseline=base, csv_delimiter=";")
        self.assertFalse(changed["delta"]["compatible"])

    def test_html_without_documents_keeps_legacy_raw_text_path(self):
        raw = (ROOT / "tests/fixtures/patch_e_dense.html").read_bytes()
        self.write_config({"model.html": raw})
        run, manifest = inventory(self.config, "html-raw-run")
        self.assertEqual("ready", manifest["status"])
        self.assertNotIn("document", manifest["files"][0])
        self.assertEqual(raw, (run / manifest["files"][0]["snapshot_path"]).read_bytes())

    def test_csv_representation_choice_is_frozen_and_incomparable(self):
        raw = {"values.csv": (ROOT / "tests/fixtures/patch_f_values.csv").read_bytes()}
        self.write_config(raw)
        base, old = inventory(self.config, "csv-raw", documents=True)
        self.assertNotIn("document", old["files"][0])
        structured, new = inventory(self.config, "csv-structured", baseline=base, documents=True,
                                    csv_representation="structured", csv_header="first-row",
                                    csv_delimiter=";")
        self.assertIn("document", new["files"][0])
        self.assertFalse(new["delta"]["compatible"])
        self.assertEqual("passed", check_run(base)["status"])
        self.assertEqual("passed", check_run(structured)["status"])
        packet_index = build_packets(structured)
        segment_inventory = json.loads((structured / "segments.snapshot.json").read_text())
        row_ids = {s["segment_id"] for s in segment_inventory["segments"]
                   if s["content_type"] == "table_row"}
        self.assertTrue(row_ids)
        self.assertTrue(row_ids <= {s["segment_id"] for s in packet_index["segments"]})
        same, same_manifest = inventory(self.config, "csv-same", baseline=structured, documents=True,
                                        csv_representation="structured", csv_header="first-row",
                                        csv_delimiter=";")
        self.assertTrue(same_manifest["delta"]["compatible"])
        self.assertEqual("passed", check_run(same)["status"])
        _, changed = inventory(self.config, "csv-no-header", baseline=structured, documents=True,
                               csv_representation="structured", csv_delimiter=";")
        self.assertFalse(changed["delta"]["compatible"])

    def test_csv_representation_requires_explicit_document_capture(self):
        self.write_config({"values.csv": b"Code,Value\n00123,42\n"})
        with self.assertRaises(KBError):
            inventory(self.config, "bad-structured", csv_representation="structured")
        with self.assertRaises(KBError):
            inventory(self.config, "bad-header", documents=True, csv_header="first-row")

    def test_csv_frozen_policy_tampering_is_rejected(self):
        raw = {"values.csv": (ROOT / "tests/fixtures/patch_f_values.csv").read_bytes()}
        self.run, self.manifest = self.new_run(raw, "csv-tamper", csv_representation="structured",
                                               csv_header="first-row", csv_delimiter=";")
        self.assert_blocked(lambda c, m, f: m["documents"].__setitem__("csv_representation", "raw"),
                            "Invalid frozen structured-CSV capture policy")

    def test_check_passes_including_live(self):
        self.standard_source()
        report = check_run(self.run, live=True)
        self.assertEqual("passed", report["status"])
        self.assertEqual(2, report["file_count"])

    def test_packets_note_derived_text(self):
        self.standard_source()
        index = build_packets(self.run)
        packet = (self.run / index["packets"][0]["path"]).read_text(encoding="utf-8")
        self.assertIn("derived UTF-8 text extracted from", packet)
        self.assertIn("extracted_needs_review", packet)
        self.assertIn("Original artifact:", packet)

    def test_tamper_cases_are_blocked(self):
        self.standard_source()
        # Policy edits are caught by the scope digest, hence the shared expectation.
        self.assert_blocked(lambda c, m, f: m["documents"].__setitem__("timeout_seconds", 99),
                            "Scope fingerprint")
        self.assert_blocked(lambda c, m, f: m.pop("documents"),
                            "Scope fingerprint")

        def flip_text(copy, manifest, file):
            path = copy / file["snapshot_path"]
            data = b"x" + path.read_bytes()[1:]
            path.write_bytes(data)
            file["document"]["text_sha256"] = hashlib.sha256(data).hexdigest()
            file["document"]["text_bytes"] = len(data)

        def drop_sidecar(copy, manifest, file):
            (copy / (file["document"]["metadata_snapshot_path"] + ".sha256")).unlink()

        def hash_reuse(copy, manifest, file):
            file["document"]["text_sha256"] = file["document"]["original_sha256"]

        def bad_metadata_hash(copy, manifest, file):
            file["document"]["metadata_sha256"] = "0" * 64

        def bad_layout(copy, manifest, file):
            file["snapshot_path"] = file["document"]["text_snapshot_path"] + ".bak"

        self.assert_blocked(flip_text, "metadata disagrees")
        self.assert_blocked(drop_sidecar, "extraction.json.sha256")
        self.assert_blocked(hash_reuse, "derived-text integrity failure")
        self.assert_blocked(bad_metadata_hash, "metadata integrity failure")
        self.assert_blocked(bad_layout, "Unexpected document snapshot layout")


@unittest.skipUnless(HAS_FIXTURES,
                     "python-docx/reportlab/python-pptx not installed; run uv sync (see pyproject.toml)")
class DocumentMatrixTests(DocumentRunTests):
    def test_supported_formats_end_to_end(self):
        self.run, self.manifest = self.new_run({
            "a.docx": docx_bytes(["Parrafo uno."]),
            "b.pdf": pdf_fixture(),
            "c.pptx": pptx_fixture(),
            "d.xlsx": xlsx_fixture(),
        }, "matrix-run-1")
        self.assertEqual("ready", self.manifest["status"])
        media = {f["relative_path"]: f["document"]["media_type"]
                 for f in self.manifest["files"]}
        self.assertEqual(4, len(media))
        self.assertIn("application/pdf", media.values())
        self.assertIn("application/vnd.openxmlformats-officedocument.presentationml.presentation",
                      media.values())
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", media.values())
        report = check_run(self.run)
        self.assertEqual("passed", report["status"])
        for file in self.manifest["files"]:
            self.assertGreater(file["line_count"], 0)

    def test_corrupt_document_blocks_run(self):
        self.run, self.manifest = self.new_run({"roto.docx": b"this is not a zip archive"},
                                               "corrupt-run")
        self.assertEqual("blocked", self.manifest["status"])
        errors = [i for i in self.manifest["issues"] if i["severity"] == "error"]
        self.assertTrue(any(i["code"] == "file_not_captured" and i["path"] == "roto.docx"
                            for i in errors))
        # load_manifest still reads a blocked run (for diagnosis); using it as
        # evidence via check_run is what fails closed.
        with self.assertRaises(KBError) as context:
            check_run(self.run)
        self.assertIn("blocked", str(context.exception))

    def test_fidelity_warning_surfaces_for_review(self):
        self.run, self.manifest = self.new_run({"planilla.xlsx": xlsx_fixture()}, "warn-run")
        self.assertEqual("ready", self.manifest["status"])
        warning_codes = {i["code"] for i in self.manifest["issues"] if i["severity"] == "warning"}
        self.assertIn("hidden_sheet_included", warning_codes)
        document = self.document_file()
        self.assertIn("hidden_sheet_included",
                      {i["code"] for i in document["document"]["issues"]})

    def test_delta_semantics_with_documents(self):
        source = {"a.docx": docx_bytes(["Parrafo estable."])}
        first_run, first_manifest = self.new_run(source, "base-run")
        second_run, second_manifest = self.new_run(source, "same-run", baseline=first_run)
        self.assertTrue(second_manifest["delta"]["compatible"])
        self.assertEqual([], second_manifest["delta"]["modified"])
        self.assertIn(first_manifest["files"][0]["logical_id"],
                      second_manifest["delta"]["unchanged"])
        # Any policy change (here: csv delimiter option) changes the scope digest,
        # so the delta degrades explicitly to incomparable instead of lying.
        third_run, third_manifest = self.new_run(source, "policy-run", baseline=second_run,
                                                 csv_delimiter=";")
        self.assertFalse(third_manifest["delta"]["compatible"])
        self.assertIn("scope_changed", {i["code"] for i in third_manifest["issues"]})


if __name__ == "__main__":
    unittest.main()
