"""Engine 0.2 contracts: strict schemas, triage, per-occurrence warnings, provenance rules,
work folders, release views, re-anchoring, and question-scoped packets. Synthetic data only."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import kb_check
import kb_document_extractors
import kb_inventory
from kb_common import (ENGINE, SCHEMAS, SCHEMA_KEYWORDS, TOOL_VERSION, KBError, contract, read_json,
                       sha, utc_now, validate_schema, write_json_new)
from kb_inventory import inventory
from kb_check import check_run, load_manifest
from kb_packet import build_packets
from kb_publish import prepare_review, publish
from kb_reanchor import quotable_sha, reanchor
from kb_review_report import render_review_report
from kb_sync_skills import drift
from helpers import LEGACY_RUN, PROJECT_CONFIG, PROVENANCE, SOURCES, synthetic_records


class ContractTests(unittest.TestCase):
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
        self.config.write_text(json.dumps(self.cfg), encoding="utf-8")
        self.provenance = self.project / "config" / "source-provenance.json"
        shutil.copyfile(PROVENANCE, self.provenance)

    def full_run(self, rid="run-001", version="0.1"):
        run, m = inventory(self.config, rid)
        records = synthetic_records(run, m, version)
        path = run / "proposals" / "records.json"
        write_json_new(path, records)
        return run, m, records, path

    def save(self, path, data):
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def approve(self, run, **overrides):
        review = prepare_review(self.config, run)
        review.update(decision="approve", reviewer="Synthetic test operator (simulated)", reviewed_at=utc_now(),
                      notes="UNIT TEST ONLY. Not a real human approval.")
        review["checks"] = dict.fromkeys(review["checks"], True)
        review["acknowledged_warnings"] = dict(review["warning_summary"]["counts"])
        review["triage_acknowledged"] = bool(review["triaged_evidence_ids"])
        review.update(overrides)
        path = run / "review.json"
        self.save(path, review)
        return path, review

    # --- strict schema validator -------------------------------------------------
    def test_unknown_schema_keyword_rejected(self):
        with self.assertRaises(KBError):
            validate_schema([1, 2, 3], {"type": "array", "maxItems": 2})

    def test_all_schemas_use_only_supported_keywords(self):
        def walk(node, at):
            self.assertTrue(set(node) <= SCHEMA_KEYWORDS, f"{at}: {set(node) - SCHEMA_KEYWORDS}")
            for prop, sub in node.get("properties", {}).items():
                walk(sub, f"{at}.{prop}")
            for key in ("items", "additionalProperties"):
                if isinstance(node.get(key), dict):
                    walk(node[key], f"{at}.{key}")
            for i, sub in enumerate(node.get("anyOf", [])):
                walk(sub, f"{at}.anyOf[{i}]")
        for path in sorted(SCHEMAS.rglob("*.schema.json")):
            with self.subTest(schema=path.name):
                walk(read_json(path), path.name)

    def test_additional_properties_schema_is_enforced(self):
        schema = {"type": "object", "properties": {}, "additionalProperties": {"type": "string", "minLength": 1}}
        validate_schema({"python-docx": "1.2.0"}, schema)
        with self.assertRaises(KBError):
            validate_schema({"python-docx": ""}, schema)

    # --- tool version and fingerprint ---------------------------------------------
    def test_new_run_records_current_tool_version(self):
        run, m = inventory(self.config, "one")
        self.assertEqual(m["tool_version"], TOOL_VERSION)
        self.assertTrue((run / "work").is_dir())

    def test_old_engine_run_still_checks_under_newer_engine(self):
        self.assertNotEqual(read_json(LEGACY_RUN / "manifest.json")["tool_version"], TOOL_VERSION)
        self.assertEqual(check_run(LEGACY_RUN, LEGACY_RUN / "records.json", stage2=True)["status"], "passed")

    def test_fingerprint_uses_recorded_tool_version(self):
        run, m = inventory(self.config, "one")
        with mock.patch.object(kb_check, "TOOL_VERSION", "9.9.9"):
            self.assertEqual(check_run(run)["status"], "passed")

    def test_historical_run_survives_supported_extension_change(self):
        # A sealed legacy run must retain its capture-time allowlist semantics.
        with mock.patch.object(kb_check, "TEXT_EXTENSIONS", {".new"}, create=True):
            self.assertEqual(check_run(LEGACY_RUN, LEGACY_RUN / "records.json",
                                       stage2=True)["status"], "passed")

    def test_new_run_freezes_capture_policy_and_extension_change_is_incomparable(self):
        first, old = inventory(self.config, "one")
        self.assertEqual(old["capture_policy"]["supported_extensions"],
                         sorted(kb_inventory.TEXT_EXTENSIONS))
        with mock.patch.object(kb_inventory, "TEXT_EXTENSIONS",
                               kb_inventory.TEXT_EXTENSIONS | {".new"}):
            second, new = inventory(self.config, "two", baseline=first)
        self.assertEqual(check_run(first)["status"], "passed")
        self.assertEqual(check_run(second)["status"], "passed")
        self.assertFalse(new["delta"]["compatible"])
        self.assertEqual(new["delta"]["removed"], [])
        self.assertIn("scope_changed", {issue["code"] for issue in new["issues"]})

    def test_resealed_capture_policy_tampering_is_rejected(self):
        run, _ = inventory(self.config, "one")
        path = run / "manifest.json"
        manifest = read_json(path)
        manifest["capture_policy"]["supported_extensions"].append(".zzz")
        self.save(path, manifest)
        (run / "manifest.sha256").write_text(sha(path.read_bytes()) + "\n")
        with self.assertRaisesRegex(KBError, "Scope fingerprint mismatch"):
            load_manifest(run)
        del manifest["capture_policy"]
        self.save(path, manifest)
        (run / "manifest.sha256").write_text(sha(path.read_bytes()) + "\n")
        with self.assertRaisesRegex(KBError, "lacks its frozen capture policy"):
            load_manifest(run)

    def test_secret_exclusion_policy_change_is_incomparable(self):
        first, _ = inventory(self.config, "one")
        with mock.patch.object(kb_inventory, "SECRET_PATTERNS",
                               kb_inventory.SECRET_PATTERNS + ["**/private-note.txt"]):
            second, manifest = inventory(self.config, "two", baseline=first)
        self.assertEqual(check_run(second)["status"], "passed")
        self.assertFalse(manifest["delta"]["compatible"])
        self.assertIn("scope_changed", {issue["code"] for issue in manifest["issues"]})

    def test_document_adapter_version_change_is_incomparable(self):
        first, old = inventory(self.config, "one", documents=True)
        self.assertEqual(old["documents"]["adapter_version"], kb_document_extractors.VERSION)
        with mock.patch.object(kb_document_extractors, "VERSION", "9.9.9"):
            second, new = inventory(self.config, "two", baseline=first, documents=True)
        self.assertEqual(check_run(second)["status"], "passed")
        self.assertFalse(new["delta"]["compatible"])
        self.assertIn("scope_changed", {issue["code"] for issue in new["issues"]})

    def test_legacy_review_schema_still_reads(self):
        contract(read_json(LEGACY_RUN / "review.json"), "review")

    # --- triage --------------------------------------------------------------------
    def triaged_run(self):
        """A 0.1-shaped run whose sql input is uncited and marked triaged_out."""
        run, m, records, path = self.full_run()
        sql_eid = next(f["evidence_id"] for f in m["files"] if f["source_id"] == "sql")
        inv = next(r for r in records["records"] if r["kind"] == "investigation")
        inv["evidence"] = [ev for ev in inv["evidence"] if ev["evidence_id"] != sql_eid]
        inv["investigation"]["findings"] = [f for f in inv["investigation"]["findings"]
                                            if all(ev["evidence_id"] != sql_eid for ev in f["evidence"])]
        sql = next(c for c in records["coverage"] if c["evidence_id"] == sql_eid)
        sql.update(disposition="triaged_out", method="path_out_of_question_scope:requirements/**")
        self.save(path, records)
        return run, path, records, sql_eid

    def test_triaged_out_needs_records_v02_and_method(self):
        run, path, records, sql_eid = self.triaged_run()
        with self.assertRaises(KBError):
            check_run(run, path)  # 0.1 records cannot triage
        records["schema_version"] = "0.2"
        sql = next(c for c in records["coverage"] if c["evidence_id"] == sql_eid)
        del sql["method"]
        self.save(path, records)
        with self.assertRaises(KBError):
            check_run(run, path)  # triage needs a method
        sql["method"] = "path_out_of_question_scope:requirements/**"
        other = next(c for c in records["coverage"] if c["disposition"] == "used")
        other["method"] = "not allowed"
        self.save(path, records)
        with self.assertRaises(KBError):
            check_run(run, path)  # method only on triaged_out
        del other["method"]
        self.save(path, records)
        report = check_run(run, path, stage2=True)
        self.assertEqual(report["coverage_counts"]["triaged_out"], 1)
        self.assertIn("triaged_coverage", {h["code"] for h in report["semantic_hints"]})

    def test_publish_requires_triage_acknowledgement(self):
        run, path, records, sql_eid = self.triaged_run()
        records["schema_version"] = "0.2"
        self.save(path, records)
        rp, review = self.approve(run, triage_acknowledged=False)
        self.assertEqual(review["triaged_evidence_ids"], [sql_eid])
        with self.assertRaises(KBError):
            publish(self.config, run, rp, True)
        rp, review = self.approve(run, triaged_evidence_ids=[])
        with self.assertRaises(KBError):
            publish(self.config, run, rp, True)
        rp, review = self.approve(run)
        release = publish(self.config, run, rp, True)
        self.assertIn("1 triaged out (not read in full)", (release / "index.md").read_text())

    # --- warnings acknowledged per occurrence ----------------------------------------
    def test_warning_acknowledgement_is_by_count(self):
        for name in ("empty-a.md", "empty-b.md"):
            (self.sources / "requirements" / name).write_text("")
        run, m, records, path = self.full_run()
        cited = {ev["evidence_id"] for r in records["records"] for ev in r["evidence"]}
        cited |= {ev["evidence_id"] for r in records["records"] if r["investigation"]
                  for f in r["investigation"]["findings"] for ev in f["evidence"]}
        for c in records["coverage"]:
            if c["evidence_id"] not in cited:
                c["disposition"] = "reviewed_no_record"
        self.save(path, records)
        counts = prepare_review(self.config, run)["warning_summary"]["counts"]
        self.assertEqual(counts["empty_file"], 2)
        rp, _ = self.approve(run, acknowledged_warnings={**counts, "empty_file": 1})
        with self.assertRaises(KBError):
            publish(self.config, run, rp, True)
        rp, _ = self.approve(run)
        publish(self.config, run, rp, True)

    def test_hand_edited_warning_summary_rejected(self):
        run, m, records, path = self.full_run()
        rp, review = self.approve(run)
        review["warning_summary"]["sha256"] = "0" * 64
        self.save(rp, review)
        with self.assertRaises(KBError):
            publish(self.config, run, rp, True)

    def test_prepared_report_exposes_context_questions_and_each_warning(self):
        run, m, records, path = self.full_run()
        review = prepare_review(self.config, run)
        report_path = run / "review-report.md"
        report = report_path.read_text()
        self.assertEqual(review["schema_version"], "0.3")
        self.assertEqual(review["review_report_sha256"], sha(report_path.read_bytes()))
        self.assertIn("REQ-001", report)
        self.assertIn("UNC-001", report)
        self.assertIn("requirements.md", report)
        self.assertIn("lines 3–3", report)
        self.assertIn("L000003", report)
        self.assertIn("The interactive search response must contain at most 10 candidates.", report)
        self.assertIn("What must the reviewer verify?", report)
        for issue in m["issues"]:
            if issue["severity"] == "warning":
                self.assertIn(issue["code"], report)
                self.assertIn(issue["detail"], report)

    def test_review_report_unchanged_record_keeps_its_statement_visible(self):
        run, manifest, records, path = self.full_run()
        records["records"][0]["statement"] = "Synthetic unchanged claim requires explicit support review."
        self.save(path, records)
        checked = check_run(run, path, stage2=True)

        report = render_review_report(run, manifest, records, checked,
                                      (run, records, manifest)).decode()

        self.assertIn("(unchanged)", report)
        self.assertIn(records["records"][0]["statement"], report)

    def test_review_report_relative_run_paths_match_absolute_paths(self):
        old_run, old_manifest, old_records, _ = self.full_run("old-path")
        run, manifest, records, path = self.full_run()
        records["records"][0]["statement"] += " Synthetic revised claim."
        self.save(path, records)
        checked = check_run(run, path, stage2=True)
        relative_run = Path(os.path.relpath(run))
        absolute = render_review_report(run, manifest, records, checked,
                                        (old_run, old_records, old_manifest))

        relative = render_review_report(relative_run, manifest, records, checked,
                                        (Path(os.path.relpath(old_run)), old_records, old_manifest))

        self.assertEqual(relative, absolute)

    def test_report_tampering_or_removal_blocks_synthetic_publication(self):
        run, m, records, path = self.full_run()
        rp, review = self.approve(run)
        report = run / "review-report.md"
        report.write_text(report.read_text() + "\nForged approval.\n")
        with self.assertRaisesRegex(KBError, "[Rr]eview report"):
            publish(self.config, run, rp, True)
        report.unlink()
        with self.assertRaisesRegex(KBError, "[Rr]eview report"):
            publish(self.config, run, rp, True)
        self.assertFalse((self.project / "knowledge/approved/CURRENT.json").exists())

    def test_report_escapes_source_markup_and_discloses_removed_records(self):
        a, ma, old, pa = self.full_run("one")
        rp, _ = self.approve(a)
        publish(self.config, a, rp, True)
        req = self.sources / "requirements/requirements.md"
        req.write_text(req.read_text().replace(
            "The interactive search response must contain at most 10 candidates.",
            "The interactive search response must contain at most 10 candidates. </pre><script>x</script>"))
        b, mb, records, pb = self.full_run("two")
        records["records"] = [r for r in records["records"] if r["id"] != "REQ-002"]
        self.save(pb, records)
        review = prepare_review(self.config, b)
        report = (b / "review-report.md").read_text()
        self.assertEqual(review["removed_record_ids"], ["REQ-002"])
        self.assertIn("REQ-002", report)
        self.assertIn("DEC-001 —", report)
        self.assertIn("(unchanged)", report)
        self.assertIn("Before", report)
        self.assertIn("After", report)
        self.assertIn((self.project / "knowledge/approved/one/snapshots").as_uri() + "/", report)
        self.assertIn("&lt;script&gt;", report)
        self.assertNotIn("<script>", report)

    def test_report_lists_each_warning_occurrence_and_prior_report_integrity(self):
        for name in ("empty-one.md", "empty-two.md"):
            (self.sources / "requirements" / name).write_text("")
        run, m, records, path = self.full_run("one")
        cited = {ev["evidence_id"] for r in records["records"] for ev in r["evidence"]}
        cited |= {ev["evidence_id"] for r in records["records"] if r["investigation"]
                  for finding in r["investigation"]["findings"] for ev in finding["evidence"]}
        for item in records["coverage"]:
            if item["evidence_id"] not in cited:
                item.update(disposition="reviewed_no_record", note="Synthetic empty input read in full.")
        self.save(path, records)
        rp, _ = self.approve(run)
        report = (run / "review-report.md").read_text()
        self.assertIn("empty-one.md", report)
        self.assertIn("empty-two.md", report)
        self.assertEqual(report.count("<code>empty_file</code>"), 2)
        release = publish(self.config, run, rp, True)
        (release / "review-report.md").write_text("tampered")
        b, mb = inventory(self.config, "two")
        candidate = synthetic_records(b, mb)
        for item in candidate["coverage"]:
            if item["evidence_id"] not in {ev["evidence_id"] for r in candidate["records"] for ev in r["evidence"]}:
                item.update(disposition="reviewed_no_record", note="Synthetic empty input read in full.")
        write_json_new(b / "proposals/records.json", candidate)
        with self.assertRaises(KBError):
            prepare_review(self.config, b)

    def test_triaged_input_is_visible_and_changed_candidate_stales_report(self):
        run, path, records, sql_eid = self.triaged_run()
        records["schema_version"] = "0.2"
        self.save(path, records)
        prepare_review(self.config, run)
        report = (run / "review-report.md").read_text()
        self.assertIn("## Triaged inputs", report)
        self.assertIn(sql_eid, report)
        self.assertIn("path\\_out\\_of\\_question\\_scope", report)
        records["records"][0]["title"] += " revised"
        self.save(path, records)
        with self.assertRaisesRegex(KBError, "stale"):
            prepare_review(self.config, run)

    def test_review_02_remains_readable_but_cannot_publish(self):
        run, m, records, path = self.full_run()
        rp, review = self.approve(run)
        review["schema_version"] = "0.2"
        del review["review_report_sha256"]
        del review["triaged_segment_ids"]
        del review["segment_triage_acknowledged"]
        contract(review, "review")
        self.save(rp, review)
        with self.assertRaisesRegex(KBError, "report-bound"):
            publish(self.config, run, rp, True)

    def test_v01_review_cannot_publish(self):
        run, m, records, path = self.full_run()
        rp, review = self.approve(run)
        legacy = {k: v for k, v in review.items()
                  if k not in ("warning_summary", "acknowledged_warnings", "triaged_evidence_ids",
                               "triage_acknowledged", "triaged_segment_ids", "segment_triage_acknowledged", "work_sha256",
                               "prepared_at", "review_report_sha256")}
        legacy.update(schema_version="0.1", acknowledged_issue_codes=sorted(review["warning_summary"]["counts"]))
        self.save(rp, legacy)
        contract(legacy, "review")
        with self.assertRaises(KBError):
            publish(self.config, run, rp, True)

    # --- provenance-aware rules ------------------------------------------------------
    def test_code_only_decision_rejected(self):
        run, m, records, path = self.full_run()
        repo = next(f for f in m["files"] if f["source_type"] == "repository")
        decision = next(r for r in records["records"] if r["kind"] == "decision")
        decision["evidence"] = [{"evidence_id": repo["evidence_id"], "start_line": 3, "end_line": 3, "quote": "MAX_RESULTS = 10"}]
        arch = next(c for c in records["coverage"] if c["evidence_id"] == next(f["evidence_id"] for f in m["files"] if f["source_id"] == "architecture"))
        arch["disposition"] = "reviewed_no_record"
        self.save(path, records)
        with self.assertRaisesRegex(KBError, "only repository evidence"):
            check_run(run, path)

    def test_ai_summary_file_name_raises_warning(self):
        (self.sources / "meetings" / "Sync - Notes by Gemini.md").write_text("Se acordó algo.\n")
        (self.sources / "repository" / "src" / "notes by gemini.py").write_text("x = 1\n")
        run, m = inventory(self.config, "one")
        flagged = [(i["source_id"], i["path"]) for i in m["issues"] if i["code"] == "ai_generated_source"]
        self.assertEqual(flagged, [("meetings", "Sync - Notes by Gemini.md")])

    def test_provenance_authorship_overrides_file_name(self):
        (self.sources / "meetings" / "Sync - Notes by Gemini.md").write_text("Se acordó algo.\n")
        data = read_json(self.provenance)
        entry = json.loads(json.dumps(data["entries"][0]))
        entry.update(source_id="meetings", relative_path="Sync - Notes by Gemini.md")
        entry["origin"]["authorship"] = "human"
        data["entries"].append(entry)
        next(e for e in data["entries"] if e["source_id"] == "requirements")["origin"]["authorship"] = "ai_generated"
        self.save(self.provenance, data)
        run, m = inventory(self.config, "one")
        flagged = [(i["source_id"], i["path"]) for i in m["issues"] if i["code"] == "ai_generated_source"]
        self.assertEqual(flagged, [("requirements", "requirements.md")])

    def test_semantic_hints_flag_single_lines_and_pending_language(self):
        run, m, records, path = self.full_run()
        meeting = next(f for f in m["files"] if f["source_id"] == "meetings")
        decision = next(r for r in records["records"] if r["kind"] == "decision")
        decision["evidence"].append({"evidence_id": meeting["evidence_id"], "start_line": 3, "end_line": 3,
                                     "quote": "PROPUESTA (no aprobada): ampliar el límite de candidatos de 10 a 20."})
        self.save(path, records)
        hints = {(h["code"], h["record_id"]) for h in check_run(run, path)["semantic_hints"]}
        self.assertIn(("single_line_citations", "REQ-001"), hints)
        self.assertNotIn(("single_line_citations", "DEC-001"), hints)
        self.assertIn(("decision_quote_pending_language", "DEC-001"), hints)

    # --- work folder and release views ------------------------------------------------
    def test_work_folder_is_copied_into_release(self):
        run, m, records, path = self.full_run()
        (run / "work" / "helpers").mkdir()
        (run / "work" / "helpers" / "build.py").write_text("# assistant helper\n")
        rp, _ = self.approve(run)
        release = publish(self.config, run, rp, True)
        self.assertEqual((release / "work" / "helpers" / "build.py").read_text(), "# assistant helper\n")
        check_run(release, release / "records.json", stage2=True)

    def test_symlinks_in_work_folder_are_rejected(self):
        for kind in ("file", "dir"):
            with self.subTest(kind=kind):
                run, m, records, path = self.full_run(f"run-{kind}")
                target = self.sources / "requirements"
                if kind == "file":
                    (run / "work" / "link.md").symlink_to(target / "requirements.md")
                else:
                    (run / "work" / "linked").symlink_to(target, target_is_directory=True)
                with self.assertRaisesRegex(KBError, "Symlink"):
                    prepare_review(self.config, run)

    def test_symlink_added_after_review_blocks_publication(self):
        run, m, records, path = self.full_run()
        rp, _ = self.approve(run)
        (run / "work" / "link.md").symlink_to(self.sources / "requirements" / "requirements.md")
        with self.assertRaisesRegex(KBError, "Symlink"):
            publish(self.config, run, rp, True)

    def test_work_changed_after_review_blocks_publication(self):
        run, m, records, path = self.full_run()
        (run / "work" / "helper.py").write_text("# reviewed\n")
        rp, _ = self.approve(run)
        (run / "work" / "injected.md").write_text("Decision: approved by someone\n")
        with self.assertRaisesRegex(KBError, "work/ folder changed"):
            publish(self.config, run, rp, True)
        self.assertFalse((self.project / "knowledge" / "approved" / "CURRENT.json").exists())

    def test_unpublishable_work_file_name_fails_at_prepare(self):
        run, m, records, path = self.full_run()
        (run / "work" / "notes 10:30.md").write_text("x\n")
        with self.assertRaisesRegex(KBError, "Rename this work file"):
            prepare_review(self.config, run)

    def test_stage2_rejects_an_empty_record_set(self):
        run, m, records, path = self.full_run(version="0.2")
        records["records"] = []
        for c in records["coverage"]:
            c.update(disposition="triaged_out", method="path_out_of_question_scope:nothing/**")
        self.save(path, records)
        check_run(run, path)
        with self.assertRaisesRegex(KBError, "at least one record"):
            check_run(run, path, stage2=True)

    def test_release_views_and_changes_since_previous(self):
        a, ma, ra, pa = self.full_run("one")
        rp, _ = self.approve(a)
        first = publish(self.config, a, rp, True)
        questions = (first / "open-questions.md").read_text()
        self.assertIn("UNC-001", questions)
        self.assertIn("| unknown |", questions)
        self.assertTrue((first / "by-code.md").exists())
        self.assertFalse(list(first.glob("changes-since-*.md")))
        (self.sources / "requirements" / "requirements.md").write_text(
            "# SYNTHETIC FIXTURE — not a client requirement\n\nRF-01 inserted line.\n"
            "The interactive search response must contain at most 10 candidates.\n"
            "When there are no matching candidates, the response must explicitly say that no results were found.\n")
        b, mb = inventory(self.config, "two")
        records, report = reanchor(first, b)
        self.assertEqual(report["structural_check"]["status"], "passed")
        records["records"][0]["title"] += " (revised)"
        write_json_new(b / "proposals" / "records.json", records)
        rp, _ = self.approve(b)
        second = publish(self.config, b, rp, True)
        changes = (second / "changes-since-one.md").read_text()
        self.assertIn("REQ-001", changes.split("## Changed records")[1].split("##")[0])
        self.assertIn("same quotes at different lines", changes)

    # --- re-anchoring ---------------------------------------------------------------
    def test_reanchor_reports_moved_and_vanished_quotes(self):
        a, ma, ra, pa = self.full_run("one")
        req = self.sources / "requirements" / "requirements.md"
        req.write_text("# SYNTHETIC FIXTURE — not a client requirement\n\nInserted line.\n"
                       "The interactive search response must contain at most 10 candidates.\n")
        b, mb = inventory(self.config, "two")
        records, report = reanchor(a, b)
        statuses = {(r["record_id"], r["status"]) for r in report["citations"]}
        self.assertIn(("REQ-001", "moved"), statuses)
        self.assertIn(("REQ-002", "vanished"), statuses)
        self.assertIn("REQ-002", report["dropped_record_ids"])
        self.assertIn(("DEC-001", "unchanged"), statuses)
        req1 = next(r for r in records["records"] if r["id"] == "REQ-001")
        self.assertEqual(req1["evidence"][0]["start_line"], 4)
        self.assertEqual(report["structural_check"]["status"], "passed")
        self.assertTrue((b / "work" / "reanchored-records.json").exists())
        with self.assertRaises(KBError):
            reanchor(a, b)  # outputs are write-once

    def reviewed_no_record_run(self, rid):
        """Run whose sql input is read-but-uncited (reviewed_no_record)."""
        run, m = inventory(self.config, rid)
        records = synthetic_records(run, m, "0.2")
        sql_eid = next(f["evidence_id"] for f in m["files"] if f["source_id"] == "sql")
        inv = next(r for r in records["records"] if r["kind"] == "investigation")
        inv["evidence"] = [ev for ev in inv["evidence"] if ev["evidence_id"] != sql_eid]
        inv["investigation"]["findings"] = [f for f in inv["investigation"]["findings"]
                                            if all(ev["evidence_id"] != sql_eid for ev in f["evidence"])]
        next(c for c in records["coverage"] if c["evidence_id"] == sql_eid)["disposition"] = "reviewed_no_record"
        path = run / "proposals" / "records.json"
        write_json_new(path, records)
        return run, m, path

    def coverage_by_source(self, records, manifest):
        sources = {f["evidence_id"]: f["source_id"] for f in manifest["files"]}
        return {sources[c["evidence_id"]]: c["disposition"] for c in records["coverage"]}

    def test_reanchor_does_not_carry_coverage_from_an_unapproved_run(self):
        a, ma, pa = self.reviewed_no_record_run("one")
        b, mb = inventory(self.config, "two")
        records, report = reanchor(a, b)
        self.assertFalse(report["previous_is_approved_release"])
        self.assertEqual(self.coverage_by_source(records, mb)["sql"], "deferred")

    def test_reanchor_carries_identical_coverage_from_an_approved_release(self):
        a, ma, pa = self.reviewed_no_record_run("one")
        rp, _ = self.approve(a)
        release = publish(self.config, a, rp, True)
        (self.sources / "sql" / "schema.sql").write_text("-- changed\n")
        b, mb = inventory(self.config, "two")
        records, report = reanchor(release, b)
        self.assertTrue(report["previous_is_approved_release"])
        self.assertEqual(self.coverage_by_source(records, mb)["sql"], "deferred")  # changed text
        (self.sources / "sql" / "schema.sql").write_bytes((SOURCES / "sql" / "schema.sql").read_bytes())
        c, mc = inventory(self.config, "three")
        records, report = reanchor(release, c)
        self.assertEqual(self.coverage_by_source(records, mc)["sql"], "reviewed_no_record")
        self.assertIn("approved release one", next(c["note"] for c in records["coverage"]
                                                   if c["disposition"] == "reviewed_no_record"))

    def test_reanchor_compares_quotable_text_for_documents(self):
        text = {"sha256": "a" * 64}
        doc = {"sha256": "a" * 64, "document": {"text_sha256": "b" * 64}}
        newer_extractor = {"sha256": "a" * 64, "document": {"text_sha256": "c" * 64}}
        self.assertEqual(quotable_sha(text), "a" * 64)
        self.assertNotEqual(quotable_sha(doc), quotable_sha(newer_extractor))

    def test_reanchor_rejects_coverage_for_unknown_evidence(self):
        a, ma, ra, pa = self.full_run("one")
        ra["coverage"][0]["evidence_id"] = "E-" + "0" * 24
        self.save(pa, ra)
        b, mb = inventory(self.config, "two")
        with self.assertRaisesRegex(KBError, "absent from its manifest"):
            reanchor(a, b)

    # --- question-scoped packets ------------------------------------------------------
    def test_packet_glob_selection_writes_triage_stub(self):
        run, m = inventory(self.config, "one")
        index = build_packets(run, globs=["requirements/**", "src/*.py"])
        selected = {f["source_id"] for f in m["files"] if f["evidence_id"] in index["selected_evidence_ids"]}
        self.assertEqual(selected, {"requirements", "repository"})
        stub = read_json(run / "packets" / "coverage-stub.json")
        contract(stub, "records")
        triaged = [c for c in stub["coverage"] if c["disposition"] == "triaged_out"]
        self.assertEqual(len(triaged), 3)
        self.assertTrue(all(c["method"].startswith("path_out_of_question_scope:") for c in triaged))

    def test_packet_grep_selection_is_case_insensitive(self):
        run, m = inventory(self.config, "one")
        index = build_packets(run, terms=["azure search"])
        self.assertEqual(len(index["selected_evidence_ids"]), 1)
        self.assertIn("keyword_scan:azure search", index["selection_method"])

    def test_full_packet_build_has_no_stub(self):
        run, m = inventory(self.config, "one")
        index = build_packets(run)
        self.assertIsNone(index["selection_method"])
        self.assertFalse((run / "packets" / "coverage-stub.json").exists())

    # --- skills ---------------------------------------------------------------------
    def test_skill_mirrors_match_canonical_skills(self):
        self.assertEqual(drift(), {}, "run: uv run python tools/kb_sync_skills.py")


if __name__ == "__main__":
    unittest.main()
