"""Local visual preparation checks; no model calls or invented human scores."""
import copy
import ctypes
import errno
import io
import importlib.util
import json
import os
import resource
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, call, patch

from second_brain import kb_visual_review as visual
from second_brain.kb_common import KBError

ROOT = Path(__file__).resolve().parents[1]
HAS_VISUAL = importlib.util.find_spec("cairosvg") is not None and importlib.util.find_spec("PIL") is not None


class VisualReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # macOS temporary directories commonly use the /var -> /private/var alias.
        self.root = Path(self.temp.name).resolve()

    def source(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def packet(self, *sources):
        return visual.prepare(list(sources), self.root / "packet")

    def test_pixels_and_metadata_are_kept_separate(self):
        source = ROOT / "tests/fixtures/patch_g_visual_probe.png"
        packet = self.packet(source)
        self.assertEqual(packet["items"][0]["status"], "rendered")
        from PIL import Image
        with Image.open(self.root / "packet" / packet["items"][0]["preview_path"]) as im:
            self.assertFalse(im.info)
        self.assertEqual(visual.verify(self.root / "packet"), packet)

    @unittest.skipUnless(HAS_VISUAL, "Optional uv visual extra unavailable")
    def test_svg_keeps_internal_markers_and_records_denied_resources(self):
        packet = self.packet(ROOT / "tests/fixtures/patch_g_diagram.svg")
        self.assertEqual(packet["items"][0]["status"], "rendered")
        self.assertIn("svg_restricted", {i["code"] for i in packet["issues"]})

    @unittest.skipUnless(HAS_VISUAL, "Optional uv visual extra unavailable")
    def test_active_html_is_not_executed_and_hidden_visuals_are_excluded(self):
        html = b'<script><svg></svg></script><template><svg></svg></template><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="red"/></svg>'
        packet = self.packet(self.source("input.html", html))
        self.assertEqual(len(packet["items"]), 1)
        self.assertEqual(packet["items"][0]["status"], "rendered")
        self.assertIn("html_layout_unavailable", {i["code"] for i in packet["issues"]})

    @unittest.skipUnless(HAS_VISUAL, "Optional uv visual extra unavailable")
    def test_dense_case_exposes_both_diagrams(self):
        packet = self.packet(ROOT / "tests/fixtures/patch_g_dense_visual.html")
        self.assertEqual(len(packet["items"]), 2)
        self.assertTrue(all(i["status"] == "rendered" for i in packet["items"]))

    def test_office_assets_have_part_locators_and_page_gap(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("word/media/image1.png", (ROOT / "tests/fixtures/patch_g_visual_probe.png").read_bytes())
        packet = self.packet(self.source("example.docx", stream.getvalue()))
        self.assertIn("word/media/image1.png", packet["items"][0]["locator"])
        self.assertIn("office_layout_unavailable", {i["code"] for i in packet["issues"]})

    def test_pdf_requires_explicit_renderer(self):
        from reportlab.pdfgen.canvas import Canvas
        stream = io.BytesIO()
        canvas = Canvas(stream)
        canvas.drawString(20, 20, "Synthetic")
        canvas.save()
        packet = self.packet(self.source("example.pdf", stream.getvalue()))
        self.assertEqual(packet["items"][0]["status"], "unavailable")
        executable = self.source("pdftoppm", b"synthetic executable identity")
        executable.chmod(0o700)
        with patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(1, "pdftoppm")):
            with self.assertRaisesRegex(KBError, "version check"):
                visual.versions(executable)

    def test_tampering_original_or_preview_fails(self):
        packet = self.packet(ROOT / "tests/fixtures/patch_g_visual_probe.png")
        path = self.root / "packet" / packet["items"][0]["preview_path"]
        path.write_bytes(b"changed")
        with self.assertRaises(KBError):
            visual.verify(self.root / "packet")

    def test_no_overwrite_or_symlink_outputs(self):
        source = self.source("input.svg", b"<svg/>")
        out = self.root / "existing"
        out.mkdir()
        with self.assertRaises(KBError):
            visual.prepare([source], out)
        link = self.root / "link.svg"
        link.symlink_to(source)
        with self.assertRaises(KBError):
            visual.prepare([link], self.root / "packet")

    def assessment(self, packet, packet_root=None):
        packet_root = packet_root if packet_root is not None else self.root / "packet"
        result = copy.deepcopy(json.loads((packet_root / "assessment.template.json").read_text()))
        result["reviewer"] = "Synthetic test reviewer"
        result["reviewed_at"] = packet["created_at"]
        result["inventory_confirmed"] = True
        for item in result["items"]:
            item["elements"] = [{"id": "label", "status": "match", "observation": "Synthetic visible label", "region": [0, 0, 1, 1], "note": "Compared with original"}]
        for issue in result["issues"]:
            issue["disposition"] = "unresolved"
            issue["note"] = "Needs manual comparison"
        return result

    def test_assessment_requires_human_input_and_complete_inventory(self):
        packet = self.packet(ROOT / "tests/fixtures/patch_g_visual_probe.png")
        template = json.loads((self.root / "packet/assessment.template.json").read_text())
        with self.assertRaises(KBError):
            visual.assess(self.root / "packet", template)
        complete = self.assessment(packet)
        self.assertFalse(visual.assess(self.root / "packet", complete)["business_approval"])
        complete["items"] = []
        with self.assertRaises(KBError):
            visual.assess(self.root / "packet", complete)

    def test_invalid_region_stale_binding_and_issue_omission_fail(self):
        packet = self.packet(ROOT / "tests/fixtures/patch_g_diagram.svg")
        valid = self.assessment(packet)
        for change in ("region", "binding", "issues"):
            bad = copy.deepcopy(valid)
            if change == "region":
                bad["items"][0]["elements"][0]["region"] = [0, 0, 99999, 1]
            elif change == "binding":
                bad["packet_sha256"] = "0" * 64
            else:
                bad["issues"] = []
            with self.assertRaises(KBError):
                visual.assess(self.root / "packet", bad)

    @unittest.skipUnless(HAS_VISUAL, "Optional uv visual extra unavailable")
    def test_export_preserves_provenance_and_gaps(self):
        packet = self.packet(ROOT / "tests/fixtures/patch_g_diagram.svg")
        assessment = self.assessment(packet)
        out = self.root / "export"
        visual.export(self.root / "packet", assessment, out)
        text = (out / "transcription.md").read_text()
        self.assertIn("Synthetic visible label", text)
        self.assertIn("svg_restricted", text)
        self.assertIn(packet["sources"][0]["sha256"], text)
        with self.assertRaises(KBError):
            visual.export(self.root / "packet", assessment, out)

    @unittest.skipUnless(HAS_VISUAL, "Optional uv visual extra unavailable")
    def test_svg_pixel_colors_and_external_fetch_guard(self):
        from PIL import Image
        from second_brain.kb_visual_render import Renderer, deny_fetch
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10"><rect width="10" height="10" fill="red"/><rect x="10" width="10" height="10" fill="blue"/><image href="file:///etc/passwd"/></svg>'
        packet = self.packet(self.source("colors.svg", svg))
        item = packet["items"][0]
        with Image.open(self.root / "packet" / item["preview_path"]) as image:
            self.assertEqual(image.getpixel((10, 10)), (255, 0, 0, 255))
            self.assertEqual(image.getpixel((image.width - 10, 10)), (0, 0, 255, 255))
        with self.assertRaises(ValueError):
            deny_fetch("https://invalid.example/hidden")
        # Verify the renderer actually supplies the denial callback, even after preflight.
        with patch("cairosvg.surface.PNGSurface.convert", side_effect=ValueError("probe")) as convert:
            renderer = Renderer(self.root / "packet")
            renderer.image("S-0001", "probe", svg, ".svg")
            self.assertIs(convert.call_args.kwargs["url_fetcher"], deny_fetch)

    @unittest.skipUnless(HAS_VISUAL, "Optional uv visual extra unavailable")
    def test_svg_rejects_entities_and_escaped_css_resources(self):
        from second_brain.kb_visual_render import sanitize_svg, css_external
        for css in ('@import "https://invalid.example/x";', r'fill: u\72l("file:///tmp/x")', 'fill:url(data:image/svg+xml;base64,AAAA)'):
            self.assertTrue(css_external(css))
        self.assertFalse(css_external("marker-end:url(#arrow)"))
        with self.assertRaises(Exception):
            sanitize_svg(b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg>&x;</svg>')

    def test_oversized_zip_and_duplicate_parts_record_gaps(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("word/media/huge.png", b"x" * (65 * 1024 * 1024))
        packet = self.packet(self.source("huge.docx", stream.getvalue()))
        self.assertEqual(packet["issues"][0]["code"], "source_visuals_unavailable")
        self.assertIn("expansion limit", packet["issues"][0]["detail"])

    def test_missing_optional_renderer_is_an_explicit_gap(self):
        from second_brain.kb_visual_render import Renderer
        renderer = Renderer(self.root)
        with patch.dict("sys.modules", {"cairosvg.surface": None}):
            renderer.image("S-0001", "original", b'<svg viewBox="0 0 1 1"/>', ".svg")
        self.assertEqual(renderer.items[0]["status"], "unavailable")
        self.assertEqual(renderer.issues[0]["code"], "render_unavailable")

    @unittest.skipUnless(Path("/usr/bin/pdftoppm").is_file(), "Explicit local Poppler unavailable")
    def test_pdf_pages_render_with_explicit_executable(self):
        from reportlab.pdfgen.canvas import Canvas
        stream = io.BytesIO()
        canvas = Canvas(stream, pagesize=(100, 50))
        canvas.beginForm("nested")
        canvas.setFillColorRGB(1, 0, 0)
        canvas.rect(0, 0, 20, 20, fill=1)
        canvas.endForm()
        canvas.doForm("nested")
        canvas.showPage()
        canvas.drawString(10, 20, "Page two")
        canvas.save()
        source = self.source("pages.pdf", stream.getvalue())
        packet = visual.prepare([source], self.root / "packet", Path("/usr/bin/pdftoppm"))
        self.assertEqual([i["locator"] for i in packet["items"]], ["PDF/page[1]", "PDF/page[2]"])
        self.assertTrue(all(i["status"] == "rendered" for i in packet["items"]))
        self.assertTrue(packet["renderers"]["pdftoppm"]["sha256"])

    def test_packet_paths_and_malformed_assessments_fail_closed(self):
        packet = self.packet(ROOT / "tests/fixtures/patch_g_visual_probe.png")
        for malformed in ([], {}, {"schema_version": "1.0"}):
            with self.assertRaises(KBError):
                visual.assess(self.root / "packet", malformed)
        for relative in ("../input.png", "/tmp/input.png", "previews/../originals/S-0001.bin"):
            with self.assertRaises(KBError):
                visual.packet_file(self.root / "packet", relative)
        extra = self.root / "packet/extra.txt"
        extra.write_text("unexpected")
        with self.assertRaises(KBError):
            visual.verify(self.root / "packet")

    def test_run_outputs_are_confined_to_work(self):
        run = self.root / "run"
        run.mkdir()
        (run / "manifest.json").write_text("{}")
        for name in ("snapshots", "proposals", "knowledge/approved"):
            (run / name).mkdir(parents=True)
            with self.assertRaises(KBError):
                visual.output_path(run / name / "visuals")
        (run / "work").mkdir()
        self.assertEqual(visual.output_path(run / "work/visuals"), run / "work/visuals")

    def test_material_omissions_lower_fidelity_and_cannot_be_approved(self):
        packet = self.packet(ROOT / "tests/fixtures/patch_g_visual_probe.png")
        assessment = self.assessment(packet)
        assessment["items"][0]["elements"].append({"id": "missing_arrow", "status": "omission", "observation": "", "region": None, "note": "Synthetic missing arrow"})
        result = visual.assess(self.root / "packet", assessment)
        self.assertEqual(result["human_fidelity"]["match_fraction"], 0.5)
        self.assertEqual(result["status"], "needs_attention")
        self.assertFalse(result["business_approval"])

    def test_empty_pdf_is_not_a_successful_visual_comparison(self):
        from pypdf import PdfWriter
        stream = io.BytesIO()
        PdfWriter().write(stream)
        packet = self.packet(self.source("empty.pdf", stream.getvalue()))
        self.assertEqual(packet["issues"][0]["code"], "empty_pdf")
        result = visual.assess(self.root / "packet", self.assessment(packet))
        self.assertEqual(result["status"], "needs_attention")
        self.assertIsNone(result["human_fidelity"]["match_fraction"])

    def test_custom_approved_path_is_protected(self):
        project = self.root / "project"
        (project / "config").mkdir(parents=True)
        source = self.root / "sources"
        source.mkdir()
        # Use a real valid project contract; custom knowledge paths are supported.
        cfg = {"schema_version": "0.1", "project": {"id": "demo", "name": "Demo", "description": "Synthetic"},
               "sources": [{"id": "req", "type": "requirements", "path": str(source), "include": ["**/*.md"], "exclude": []}],
               "global_exclude": [], "knowledge": {"path": "knowledge", "approved": "knowledge/releases"}, "runs": {"path": "captures"}}
        (project / "config/project.json").write_text(json.dumps(cfg))
        for relative, allowed in (("knowledge/releases/one", False), ("other/one", False), ("captures/one", True)):
            run = project / relative
            (run / "work").mkdir(parents=True)
            (run / "manifest.json").write_text("{}")
            if allowed:
                self.assertEqual(visual.output_path(run / "work/visuals"), run / "work/visuals")
            else:
                with self.assertRaises(KBError):
                    visual.output_path(run / "work/visuals")

    def test_concurrent_empty_output_is_not_overwritten(self):
        stage = self.root / "stage"
        stage.mkdir()
        out = self.root / "out"
        out.mkdir()
        with self.assertRaises(KBError):
            visual.commit_directory(stage, out)
        self.assertTrue(stage.is_dir())
        self.assertTrue(out.is_dir())

    def test_macos_commit_uses_exclusive_rename(self):
        stage = self.root / "stage"
        stage.mkdir()
        out = self.root / "out"
        libc = Mock(spec=["renamex_np"])
        libc.renamex_np.return_value = 0
        with patch.object(visual.sys, "platform", "darwin"), patch.object(visual.ctypes, "CDLL", return_value=libc):
            visual.commit_directory(stage, out)
        libc.renamex_np.assert_called_once_with(os.fsencode(stage), os.fsencode(out), 0x00000004)

    def test_macos_concurrent_output_is_preserved(self):
        stage = self.root / "stage"
        stage.mkdir()
        (stage / "original.txt").write_text("staged")
        out = self.root / "out"
        libc = Mock(spec=["renamex_np"])

        def concurrent_output(*args):
            out.mkdir()
            ctypes.set_errno(errno.EEXIST)
            return -1

        libc.renamex_np.side_effect = concurrent_output
        with patch.object(visual.sys, "platform", "darwin"), patch.object(visual.ctypes, "CDLL", return_value=libc):
            with self.assertRaisesRegex(KBError, "concurrently"):
                visual.commit_directory(stage, out)
        self.assertEqual((stage / "original.txt").read_text(), "staged")
        self.assertTrue(out.is_dir())

    def test_missing_macos_exclusive_rename_fails_closed(self):
        stage = self.root / "stage"
        stage.mkdir()
        out = self.root / "out"
        with patch.object(visual.sys, "platform", "darwin"), patch.object(visual.ctypes, "CDLL", return_value=Mock(spec=[])):
            with self.assertRaisesRegex(KBError, "atomic no-replace"):
                visual.commit_directory(stage, out)
        self.assertTrue(stage.is_dir())
        self.assertFalse(out.exists())

    def test_worker_limits_keep_tighter_inherited_limits(self):
        for platform in ("linux", "darwin"):
            with self.subTest(platform=platform):
                inherited = {resource.RLIMIT_AS: (128 * 1024 * 1024, 256 * 1024 * 1024),
                             resource.RLIMIT_CPU: (10, 20), resource.RLIMIT_FSIZE: (1024, 2048)}
                with patch.object(visual.sys, "platform", platform), patch.object(resource, "getrlimit", side_effect=inherited.__getitem__), patch.object(resource, "setrlimit") as setter:
                    visual.set_worker_limits()
                expected = [call(resource.RLIMIT_CPU, (10, 20)), call(resource.RLIMIT_FSIZE, (1024, 2048))]
                if platform == "linux":
                    expected.insert(0, call(resource.RLIMIT_AS, inherited[resource.RLIMIT_AS]))
                self.assertEqual(setter.call_args_list, expected)

    def test_worker_limits_bound_unlimited_resources(self):
        for platform in ("linux", "darwin"):
            with self.subTest(platform=platform):
                with patch.object(visual.sys, "platform", platform), patch.object(resource, "getrlimit", return_value=(resource.RLIM_INFINITY,) * 2), patch.object(resource, "setrlimit") as setter:
                    visual.set_worker_limits()
                expected = [call(resource.RLIMIT_CPU, (60, 60)), call(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)]
                if platform == "linux":
                    expected.insert(0, call(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2))
                self.assertEqual(setter.call_args_list, expected)

    def test_packet_limitations_travel_with_producer_profile(self):
        profiles = {"linux": visual.BASE_LIMITATIONS, "darwin": visual.MACOS_LIMITATIONS}
        source = ROOT / "tests/fixtures/patch_g_visual_probe.png"
        for producer, producer_profile in profiles.items():
            packet_root = self.root / f"packet-{producer}"
            with patch.object(visual, "LIMITATIONS", producer_profile):
                packet = visual.prepare([source], packet_root)
            assessment = self.assessment(packet, packet_root)
            for consumer, consumer_profile in profiles.items():
                with self.subTest(producer=producer, consumer=consumer):
                    output = self.root / f"export-{producer}-{consumer}"
                    with patch.object(visual, "LIMITATIONS", consumer_profile):
                        self.assertEqual(visual.verify(packet_root), packet)
                        result = visual.assess(packet_root, assessment)
                        self.assertEqual(result["limitations"], producer_profile)
                        exported = visual.export(packet_root, assessment, output)
                    self.assertEqual(exported["limitations"], producer_profile)
                    provenance = json.loads((output / "provenance.json").read_text())
                    self.assertEqual(provenance["limitations"], producer_profile)
                    self.assertEqual(provenance["packet_manifest"]["limitations"], producer_profile)
                    text = (output / "transcription.md").read_text()
                    for limitation in producer_profile:
                        self.assertIn(limitation, text)
                    if producer == "linux":
                        self.assertNotIn(profiles["darwin"][-1], text)

    def test_packet_rejects_unknown_or_incomplete_limitations(self):
        packet = self.packet(ROOT / "tests/fixtures/patch_g_visual_probe.png")
        packet_root = self.root / "packet"
        required = visual.BASE_LIMITATIONS
        profiles = ([], required[:-1], [*required, "Unknown worker guarantees"],
                    list(reversed(required)), [*required, required[0]])
        for profile in profiles:
            with self.subTest(profile=profile):
                changed = copy.deepcopy(packet)
                changed["limitations"] = profile
                visual.write(packet_root / "packet.json", changed)
                (packet_root / "packet.sha256").write_text(visual.sha(visual.encoded(changed)) + "\n")
                with self.assertRaisesRegex(KBError, "Unsupported visual packet contract"):
                    visual.verify(packet_root)

    def test_export_refuses_a_different_packet_generation(self):
        packet = self.packet(ROOT / "tests/fixtures/patch_g_visual_probe.png")
        assessment = self.assessment(packet)
        different = copy.deepcopy(packet)
        different["created_at"] = "2026-10-03T00:00:00+00:00"
        # assess verifies twice; simulate replacement at export's next read.
        with patch.object(visual, "verify", side_effect=[packet, packet, different]):
            with self.assertRaises(KBError):
                visual.export(self.root / "packet", assessment, self.root / "export")
        self.assertFalse((self.root / "export").exists())

    @unittest.skipUnless(HAS_VISUAL, "Optional uv visual extra unavailable")
    def test_explicit_svg_viewport_is_preserved(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 50"><rect width="100" height="50" fill="red"/></svg>'
        packet = self.packet(self.source("viewport.svg", svg))
        item = packet["items"][0]
        self.assertEqual(item["status"], "rendered")
        self.assertEqual(item["width"], item["height"])

    @unittest.skipUnless(HAS_VISUAL, "Optional uv visual extra unavailable")
    def test_html_gradient_casing_and_svg_locators_survive(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><defs><linearGradient id="g"><stop offset="0" stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient></defs><rect width="10" height="10" fill="url(#g)"/></svg>'
        html = b'<img src="data:image/png;base64,AA==">' + svg
        packet = self.packet(self.source("gradient.html", html))
        self.assertEqual(packet["items"][1]["status"], "rendered")
        self.assertEqual(packet["items"][1]["locator"], "HTML/svg[1]@line[1]")

    @unittest.skipUnless(HAS_VISUAL, "Optional uv visual extra unavailable")
    def test_svg_structure_budget_is_a_visible_gap(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">' + b'<g>' * 102 + b'</g>' * 102 + b'</svg>'
        packet = self.packet(self.source("deep.svg", svg))
        self.assertEqual(packet["items"][0]["status"], "unavailable")
        self.assertIn("structure limit", packet["issues"][0]["detail"])

    def test_raster_pixel_budget_is_a_visible_gap(self):
        from PIL import Image
        image = Image.new("L", (4000, 2001))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        packet = self.packet(self.source("too-many-pixels.png", stream.getvalue()))
        self.assertEqual(packet["items"][0]["status"], "unavailable")
        self.assertIn("pixel limit", packet["issues"][0]["detail"])
