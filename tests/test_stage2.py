"""Offline regression and adversarial checks using synthetic data only."""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
from kb_common import (KBError, contract, evidence_identity, inside, json_sha, load_project,
                       matches, read_json, sha, utc_now, validate_pattern, write_json_new)
from kb_inventory import inventory
from kb_check import check_run, load_manifest
from kb_packet import build_packets
from kb_publish import prepare_review, publish, mermaid_label
from helpers import PROJECT_CONFIG, PROVENANCE, SOURCES, synthetic_records


class Stage2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
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
        shutil.copyfile(PROVENANCE, self.project / "config" / "source-provenance.json")

    def tearDown(self):
        self.temp.cleanup()

    def save_config(self):
        self.config.write_text(json.dumps(self.cfg), encoding="utf-8")

    def run_inventory(self, rid="run-001", **kw):
        return inventory(self.config, rid, **kw)

    def full_run(self, rid="run-001"):
        run, manifest = self.run_inventory(rid)
        records = synthetic_records(run, manifest)
        path = run / "proposals" / "records.json"
        write_json_new(path, records)
        return run, manifest, records, path

    def save_records(self, path, records):
        path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")

    def approved_review(self, run):
        review = prepare_review(self.config, run)
        review.update(decision="approve", reviewer="Synthetic test operator (simulated)", reviewed_at=utc_now(),
                      notes="UNIT TEST ONLY. Not a real human approval.")
        review["checks"] = dict.fromkeys(review["checks"], True)
        review["acknowledged_warnings"] = dict(review["warning_summary"]["counts"])
        review["triage_acknowledged"] = bool(review["triaged_evidence_ids"])
        path = run / "review.json"
        path.write_text(json.dumps(review), encoding="utf-8")
        return path, review

    def assert_bad_record(self, mutate, stage2=True):
        run, m, records, path = self.full_run()
        mutate(records)
        self.save_records(path, records)
        with self.assertRaises(KBError):
            check_run(run, path, stage2=stage2)

    def test_frozen_project_shape(self):
        self.assertEqual(set(self.cfg), {"schema_version", "project", "sources", "global_exclude", "knowledge", "runs"})
        self.assertEqual(self.cfg["schema_version"], "0.1")
        load_project(self.config)

    def test_policy_cannot_leak_into_project_json(self):
        self.cfg["authority"] = "meetings win"
        self.save_config()
        with self.assertRaises(KBError): load_project(self.config)

    def test_duplicate_source_id_rejected(self):
        self.cfg["sources"][1]["id"] = self.cfg["sources"][0]["id"]
        self.save_config()
        with self.assertRaises(KBError): load_project(self.config)

    def test_output_traversal_rejected(self):
        self.cfg["runs"]["path"] = "../outside"
        self.save_config()
        with self.assertRaises(KBError): load_project(self.config)

    def test_overlapping_outputs_rejected(self):
        self.cfg["runs"]["path"] = "knowledge/runs"
        self.save_config()
        with self.assertRaises(KBError): load_project(self.config)

    def test_approved_must_be_inside_knowledge(self):
        self.cfg["knowledge"]["approved"] = "other"
        self.save_config()
        with self.assertRaises(KBError): load_project(self.config)

    def test_source_inside_workspace_rejected(self):
        self.cfg["sources"][0]["path"] = str(self.project / "inputs")
        self.save_config()
        with self.assertRaises(KBError): load_project(self.config)

    def test_source_enclosing_workspace_rejected(self):
        self.cfg["sources"][0]["path"] = str(self.root)
        self.save_config()
        with self.assertRaises(KBError): load_project(self.config)

    def test_overlapping_source_roots_rejected(self):
        self.cfg["sources"][1]["path"] = str(self.sources)
        self.save_config()
        with self.assertRaises(KBError): load_project(self.config)

    def test_globstar_zero_or_more_segments(self):
        for path in ["a.md", "one/a.md", "one/two/a.md"]:
            self.assertTrue(matches(path, "**/*.md"))
        self.assertTrue(matches("src/a.py", "src/**"))
        self.assertFalse(matches("a/src/a.py", "src/**"))
        self.assertFalse(matches("one/two.py", "*.py"))

    def test_globs_case_sensitive(self):
        self.assertFalse(matches("README.MD", "**/*.md"))

    def test_invalid_glob_dialect_rejected(self):
        for pattern in ["../**", "!src/**", "a/**.py", "a/[ab].py", "/src/**"]:
            with self.subTest(pattern=pattern), self.assertRaises(KBError): validate_pattern(pattern)

    def test_root_and_nested_exclusions(self):
        for path in ["repository/src/build/a.py", "repository/src/sub/build/a.py"]:
            p = self.sources / path; p.parent.mkdir(parents=True, exist_ok=True); p.write_text("secret = 1")
        run, m = self.run_inventory()
        self.assertEqual(len(m["files"]), 5)
        self.assertEqual(m["status"], "ready")

    def test_default_sensitive_file_patterns(self):
        for name in [".env", ".env.production", "key.pem", "credentials-prod.json", "token.json"]:
            (self.sources / "repository" / "src" / name).write_text("sensitive")
        run, m = self.run_inventory()
        self.assertEqual(len(m["files"]), 5)

    def test_stable_evidence_identity_across_runs(self):
        a, ma = self.run_inventory("one")
        b, mb = self.run_inventory("two", baseline=a)
        self.assertEqual(ma["files"], mb["files"])
        self.assertEqual(len(mb["delta"]["unchanged"]), 5)
        self.assertEqual(mb["delta"]["modified"], [])

    def test_content_change_new_evidence_same_logical_id(self):
        a, ma = self.run_inventory("one")
        (self.sources / "requirements" / "requirements.md").write_text("Changed requirement\n")
        b, mb = self.run_inventory("two", baseline=a)
        old = next(f for f in ma["files"] if f["source_id"] == "requirements")
        new = next(f for f in mb["files"] if f["source_id"] == "requirements")
        self.assertEqual(old["logical_id"], new["logical_id"])
        self.assertNotEqual(old["evidence_id"], new["evidence_id"])
        self.assertEqual(mb["delta"]["modified"], [new["logical_id"]])

    def test_same_basename_different_paths_distinct_identity(self):
        p = self.sources / "requirements" / "nested" / "requirements.md"
        p.parent.mkdir(); p.write_text("Different content\n")
        run, m = self.run_inventory()
        reqs = [f for f in m["files"] if f["source_id"] == "requirements"]
        self.assertEqual(len(reqs), 2)
        self.assertNotEqual(reqs[0]["logical_id"], reqs[1]["logical_id"])

    def test_removed_file_delta(self):
        extra = self.sources / "requirements" / "extra.md"; extra.write_text("Extra\n")
        a, ma = self.run_inventory("one")
        extra.unlink()
        b, mb = self.run_inventory("two", baseline=a)
        self.assertEqual(len(mb["delta"]["removed"]), 1)

    def test_changed_scope_not_false_deletion(self):
        a, ma = self.run_inventory("one")
        self.cfg["global_exclude"].append("**/irrelevant/**"); self.save_config()
        b, mb = self.run_inventory("two", baseline=a)
        self.assertFalse(mb["delta"]["compatible"])
        self.assertEqual(mb["delta"]["removed"], [])
        self.assertIn("scope_changed", {x["code"] for x in mb["issues"]})

    def test_provenance_change_is_a_modification(self):
        a, ma = self.run_inventory("one")
        p = self.project / "config" / "source-provenance.json"
        data = read_json(p); data["entries"][0]["origin"]["revision"] = "new provenance label"
        p.write_text(json.dumps(data))
        b, mb = self.run_inventory("two", baseline=a)
        self.assertTrue(mb["delta"]["compatible"])
        self.assertEqual(len(mb["delta"]["modified"]), 1)

    def test_missing_source_blocks_run(self):
        shutil.rmtree(self.sources / "meetings")
        run, m = self.run_inventory()
        self.assertEqual(m["status"], "blocked")
        with self.assertRaises(KBError): check_run(run)

    def test_unsupported_included_file_blocks_run(self):
        self.cfg["sources"][0]["include"] = ["**/*"]; self.save_config()
        (self.sources / "requirements" / "opaque.bin").write_bytes(b"not supported")
        run, m = self.run_inventory()
        self.assertEqual(m["status"], "blocked")

    def test_invalid_utf8_blocks_without_replacement(self):
        (self.sources / "requirements" / "bad.md").write_bytes(b"\xff\xfe")
        run, m = self.run_inventory()
        self.assertEqual(m["status"], "blocked")

    def test_nul_bytes_block(self):
        (self.sources / "requirements" / "bad.md").write_bytes(b"text\x00binary")
        run, m = self.run_inventory()
        self.assertEqual(m["status"], "blocked")

    def test_empty_file_explicit_warning(self):
        (self.sources / "requirements" / "empty.md").write_text("")
        run, m = self.run_inventory()
        self.assertIn("empty_file", {i["code"] for i in m["issues"]})

    def test_file_budget(self):
        run, m = self.run_inventory(max_file_bytes=10)
        self.assertEqual(m["status"], "blocked")

    def test_total_budget(self):
        run, m = self.run_inventory(max_total_bytes=50)
        self.assertEqual(m["status"], "blocked")

    def test_file_count_budget(self):
        run, m = self.run_inventory(max_files=2)
        self.assertEqual(m["status"], "blocked")
        self.assertEqual(len(m["files"]), 2)

    def test_symlink_file_blocked(self):
        (self.sources / "requirements" / "linked.md").symlink_to(self.sources / "meetings" / "meeting.md")
        run, m = self.run_inventory()
        self.assertEqual(m["status"], "blocked")

    def test_symlink_directory_not_followed(self):
        (self.sources / "requirements" / "linked").symlink_to(self.sources / "meetings", target_is_directory=True)
        run, m = self.run_inventory()
        self.assertEqual(m["status"], "blocked")
        self.assertEqual(len(m["files"]), 5)

    def test_output_symlink_rejected(self):
        (self.project / "knowledge").symlink_to(self.sources / "requirements", target_is_directory=True)
        with self.assertRaises(KBError): self.run_inventory()

    def test_run_id_traversal_rejected(self):
        with self.assertRaises(KBError): self.run_inventory("../../escape")

    def test_existing_run_not_overwritten(self):
        self.run_inventory()
        with self.assertRaises(KBError): self.run_inventory()

    def test_manifest_tamper_detected(self):
        run, m = self.run_inventory()
        with (run / "manifest.json").open("a") as out: out.write(" ")
        with self.assertRaises(KBError): check_run(run)

    def test_snapshot_tamper_detected(self):
        run, m = self.run_inventory()
        (run / m["files"][0]["snapshot_path"]).write_text("tampered")
        with self.assertRaises(KBError): check_run(run)

    def test_configuration_snapshot_tamper_detected(self):
        run, m = self.run_inventory()
        (run / "project.snapshot.json").write_text("{}")
        with self.assertRaises(KBError): check_run(run)

    def test_full_synthetic_records_pass(self):
        run, m, records, path = self.full_run()
        report = check_run(run, path, stage2=True, live=True)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["record_count"], 5)
        self.assertGreater(report["citation_count"], 5)

    def test_quote_must_match_exactly(self):
        self.assert_bad_record(lambda d: d["records"][0]["evidence"][0].update(quote="Invented quote"))

    def test_out_of_bounds_citation(self):
        self.assert_bad_record(lambda d: d["records"][0]["evidence"][0].update(end_line=9999))

    def test_boolean_is_not_a_line_number(self):
        self.assert_bad_record(lambda d: d["records"][0]["evidence"][0].update(start_line=True))

    def test_cross_run_records_rejected(self):
        self.assert_bad_record(lambda d: d.update(run_id="another-run"))

    def test_cross_project_records_rejected(self):
        self.assert_bad_record(lambda d: d.update(project_id="another-project"))

    def test_stale_evidence_rejected(self):
        self.assert_bad_record(lambda d: d["records"][0]["evidence"][0].update(evidence_id="E-" + "0" * 24))

    def test_duplicate_record_id_rejected(self):
        self.assert_bad_record(lambda d: d["records"].append(copy.deepcopy(d["records"][0])))

    def test_dangling_relation_rejected(self):
        self.assert_bad_record(lambda d: d["records"][0]["relations"].append({"type": "depends_on", "target": "REQ-999"}))

    def test_self_relation_rejected(self):
        self.assert_bad_record(lambda d: d["records"][0]["relations"].append({"type": "depends_on", "target": "REQ-001"}))

    def test_duplicate_relation_rejected(self):
        self.assert_bad_record(lambda d: d["records"][3]["relations"].append(copy.deepcopy(d["records"][3]["relations"][0])))

    def test_unknown_record_field_rejected(self):
        self.assert_bad_record(lambda d: d["records"][0].update(auto_approved=True))

    def test_coverage_must_include_all_inputs(self):
        self.assert_bad_record(lambda d: d["coverage"].pop())

    def test_used_coverage_must_match_citations(self):
        self.assert_bad_record(lambda d: d["coverage"][0].update(disposition="reviewed_no_record"))

    def test_uncertainty_requires_open_question(self):
        self.assert_bad_record(lambda d: d["records"][3].update(open_questions=[]))

    def test_uncertainty_not_promoted_to_fact(self):
        self.assert_bad_record(lambda d: d["records"][3].update(epistemic_status="observed"))

    def test_investigation_scope_is_enforced(self):
        self.assert_bad_record(lambda d: d["records"][4]["investigation"].update(scope=[d["coverage"][0]["evidence_id"]]))

    def test_investigation_needs_details(self):
        self.assert_bad_record(lambda d: d["records"][4].update(investigation=None))

    def test_stage2_reports_missing_relations_without_failing(self):
        run, m, records, path = self.full_run()
        for r in records["records"]:
            r["relations"] = []
        self.save_records(path, records)
        report = check_run(run, path, stage2=True)
        self.assertFalse(report["stage2_milestone"]["met"])
        self.assertFalse(report["stage2_milestone"]["has_relation"])

    def test_stage2_reports_missing_record_kinds_without_failing(self):
        run, m, records, path = self.full_run()
        decision = next(r for r in records["records"] if r["kind"] == "decision")
        eid = decision["evidence"][0]["evidence_id"]
        records["records"].remove(decision)
        next(c for c in records["coverage"] if c["evidence_id"] == eid)["disposition"] = "reviewed_no_record"
        self.save_records(path, records)
        report = check_run(run, path, stage2=True)
        self.assertEqual(report["stage2_milestone"]["missing_record_kinds"], ["decision"])
        self.assertTrue(check_run(run, path, stage2=True)["status"] == "passed")

    def test_source_edits_do_not_rewrite_snapshots(self):
        run, m, records, path = self.full_run()
        (self.sources / "requirements" / "requirements.md").write_text("Changed source\n")
        check_run(run, path, stage2=True)
        with self.assertRaises(KBError): check_run(run, path, live=True)

    def test_packet_budgets_and_complete_line_coverage(self):
        run, m = self.run_inventory()
        index = build_packets(run, max_chars=1000)
        for f in m["files"]:
            spans = [p for p in index["packets"] if p["evidence_id"] == f["evidence_id"]]
            seen = []
            for p in spans:
                seen.extend(range(p["start_line"], p["end_line"] + 1))
                self.assertLessEqual(p["chars"], 1000)
                self.assertEqual(len((run / p["path"]).read_text()), p["chars"])
            self.assertEqual(seen, list(range(1, f["line_count"] + 1)))

    def test_packet_long_line_not_silently_truncated(self):
        (self.sources / "requirements" / "long.md").write_text("X" * 1200 + "\n")
        run, m = self.run_inventory()
        with self.assertRaises(KBError): build_packets(run, max_chars=1000)
        self.assertEqual(list((run / "packets").iterdir()), [])

    def test_packet_selection_declares_omissions(self):
        run, m = self.run_inventory()
        index = build_packets(run, selected=[m["files"][0]["evidence_id"]])
        self.assertEqual(len(index["unselected_evidence_ids"]), 4)

    def test_packet_output_not_overwritten(self):
        run, m = self.run_inventory(); build_packets(run)
        with self.assertRaises(KBError): build_packets(run)

    def test_source_files_unchanged_by_local_pipeline(self):
        before = {p.relative_to(self.sources): sha(p.read_bytes()) for p in self.sources.rglob("*") if p.is_file()}
        run, m, records, path = self.full_run(); build_packets(run); check_run(run, path, stage2=True)
        after = {p.relative_to(self.sources): sha(p.read_bytes()) for p in self.sources.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_publication_requires_explicit_flag(self):
        run, m, records, path = self.full_run(); review, _ = self.approved_review(run)
        with self.assertRaises(KBError): publish(self.config, run, review)

    def test_pending_review_cannot_publish(self):
        run, m, records, path = self.full_run()
        review = run / "review.json"; write_json_new(review, prepare_review(self.config, run))
        with self.assertRaises(KBError): publish(self.config, run, review, True)

    def test_review_becomes_stale_after_record_edit(self):
        run, m, records, path = self.full_run(); review, _ = self.approved_review(run)
        records["records"][0]["title"] += " (edited)"; self.save_records(path, records)
        with self.assertRaises(KBError): publish(self.config, run, review, True)

    def test_review_cannot_approve_subset(self):
        run, m, records, path = self.full_run(); rp, r = self.approved_review(run)
        r["approved_record_ids"].pop(); rp.write_text(json.dumps(r))
        with self.assertRaises(KBError): publish(self.config, run, rp, True)

    def test_review_checks_must_be_complete(self):
        run, m, records, path = self.full_run(); rp, r = self.approved_review(run)
        r["checks"]["privacy_checked"] = False; rp.write_text(json.dumps(r))
        with self.assertRaises(KBError): publish(self.config, run, rp, True)

    def test_provenance_warning_needs_acknowledgement(self):
        (self.project / "config" / "source-provenance.json").unlink()
        run, m, records, path = self.full_run(); rp, r = self.approved_review(run)
        r["acknowledged_warnings"] = {}; rp.write_text(json.dumps(r))
        with self.assertRaises(KBError): publish(self.config, run, rp, True)

    def test_stale_previous_release_rejected(self):
        run, m, records, path = self.full_run(); rp, r = self.approved_review(run)
        r["previous_release_id"] = "not-current"; rp.write_text(json.dumps(r))
        with self.assertRaises(KBError): publish(self.config, run, rp, True)

    def test_successful_publish_self_contained_and_immutable(self):
        run, m, records, path = self.full_run(); rp, r = self.approved_review(run)
        release = publish(self.config, run, rp, True)
        self.assertTrue((release / "project-map.mmd").exists())
        check_run(release, release / "records.json", stage2=True)
        current = read_json(self.project / "knowledge" / "approved" / "CURRENT.json")
        self.assertEqual(current["run_id"], m["run_id"])
        with self.assertRaises(KBError): publish(self.config, run, rp, True)

    def test_record_removal_requires_exact_acknowledgement(self):
        a, ma, da, pa = self.full_run("one"); rp, _ = self.approved_review(a); publish(self.config, a, rp, True)
        b, mb, db, pb = self.full_run("two")
        db["records"] = [r for r in db["records"] if r["id"] != "REQ-002"]
        self.save_records(pb, db)
        rp, r = self.approved_review(b)
        self.assertEqual(r["removed_record_ids"], ["REQ-002"])
        r["removed_record_ids"] = []; rp.write_text(json.dumps(r))
        with self.assertRaises(KBError): publish(self.config, b, rp, True)

    def test_publish_lock_does_not_get_deleted_by_contender(self):
        run, m, records, path = self.full_run(); rp, _ = self.approved_review(run)
        lock = self.project / "knowledge" / "approved" / ".publish.lock"
        lock.parent.mkdir(parents=True); lock.write_text("another publisher")
        with self.assertRaises(KBError): publish(self.config, run, rp, True)
        self.assertTrue(lock.exists())

    def test_tampered_current_release_blocks_next_publish(self):
        a, ma, da, pa = self.full_run("one"); rp, _ = self.approved_review(a); release = publish(self.config, a, rp, True)
        (release / "records.json").write_text("{}")
        b, mb, db, pb = self.full_run("two")
        with self.assertRaises(KBError): prepare_review(self.config, b)

    def test_duplicate_json_keys_rejected(self):
        self.config.write_text('{"schema_version":"0.1","schema_version":"0.2"}')
        with self.assertRaises(KBError): read_json(self.config)

    def test_unknown_schema_version_rejected(self):
        self.cfg["schema_version"] = "0.2"; self.save_config()
        with self.assertRaises(KBError): load_project(self.config)

    def test_missing_provenance_not_invented(self):
        (self.project / "config" / "source-provenance.json").unlink()
        run, m = self.run_inventory()
        self.assertTrue(all(f["provenance"] is None for f in m["files"]))
        self.assertIn("provenance_missing", {i["code"] for i in m["issues"]})

    def test_mermaid_labels_escape_active_syntax(self):
        value = mermaid_label('x"] --> injected["<script>#quot;')
        self.assertNotIn('"', value)
        self.assertNotIn('<script>', value)
        self.assertIn('#35;quot;', value)


    def test_incomplete_inventory_not_false_deletion(self):
        a, ma = self.run_inventory("one")
        shutil.rmtree(self.sources / "meetings")
        b, mb = self.run_inventory("two", baseline=a)
        self.assertEqual(mb["status"], "blocked")
        self.assertFalse(mb["delta"]["compatible"])
        self.assertEqual(mb["delta"]["removed"], [])
        self.assertIn("inventory_incomplete_delta_unavailable", {i["code"] for i in mb["issues"]})

    def test_deferred_review_blocks_stage2(self):
        run, m, records, path = self.full_run()
        decision = next(r for r in records["records"] if r["kind"] == "decision")
        evidence_id = decision["evidence"][0]["evidence_id"]
        records["records"].remove(decision)
        next(c for c in records["coverage"] if c["evidence_id"] == evidence_id)["disposition"] = "deferred"
        self.save_records(path, records)
        check_run(run, path, stage2=False)
        with self.assertRaises(KBError): check_run(run, path, stage2=True)

    def test_citation_newline_and_utf8_bom_contract(self):
        original = self.sources / "requirements" / "requirements.md"
        text = original.read_text()
        original.write_bytes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))
        run, m, records, path = self.full_run()
        check_run(run, path, stage2=True)
        evidence = next(f for f in m["files"] if f["source_id"] == "requirements")
        self.assertEqual((run / evidence["snapshot_path"]).read_bytes(), original.read_bytes())

    def test_source_symlink_root_rejected(self):
        link = self.root / "linked-root"
        link.symlink_to(self.sources / "requirements", target_is_directory=True)
        self.cfg["sources"][0]["path"] = str(link); self.save_config()
        with self.assertRaises(KBError): self.run_inventory()

    def test_review_symlink_rejected(self):
        run, m, records, path = self.full_run(); rp, _ = self.approved_review(run)
        link = self.root / "linked-review.json"; link.symlink_to(rp)
        with self.assertRaises(KBError): publish(self.config, run, link, True)

    def test_live_check_does_not_claim_to_detect_new_files(self):
        run, m, records, path = self.full_run()
        (self.sources / "requirements" / "new.md").write_text("New requirement after capture\n")
        report = check_run(run, path, live=True)
        self.assertTrue(any("does not discover newly added" in x for x in report["limitations"]))
        second, newer = self.run_inventory("two", baseline=run)
        self.assertEqual(len(newer["delta"]["added"]), 1)


    def test_total_budget_stops_capture_without_error_flood(self):
        for i in range(150):
            (self.sources / "architecture" / f"file-{i:03d}.md").write_text("one bounded fixture\n")
        run, m = self.run_inventory(max_files=1)
        self.assertEqual(m["status"], "blocked")
        self.assertLess(len(m["issues"]), 12)
        self.assertEqual(len(m["files"]), 1)

if __name__ == "__main__":
    unittest.main()
