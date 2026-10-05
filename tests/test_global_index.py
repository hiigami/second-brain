"""Synthetic approved-release lookup; no real projects, approvals, or disclosures."""
import json
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from kb_common import KBError, json_sha, read_json, sha, utc_now
from kb_index import build_index, check_index, query_index
from kb_inventory import inventory
from kb_publish import prepare_review, publish


class GlobalIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.configs = {}
        self.sources = {}
        self.releases = {}
        for pid in ("home", "demob"):
            self.make_project(pid)
            self.releases[pid] = self.release(pid, "one")
        self.registry_path = self.root / "registry.json"
        self.registry = {"schema_version": "1.1", "projects": [
            {"id": pid, "name": f"Synthetic {pid}", "aliases": [], "information_domain": "team-a",
             "owns_paths": [{"source_id": "notes", "pattern": "**/*.md"}]}
            for pid in self.configs], "disclosures": []}
        self.save(self.registry_path, self.registry)
        self.output = self.root / "shared-index.json"
        self.access_path = self.root / "index-access.json"
        self.access = {"schema_version": "1.0", "information_domain": "team-a",
                       "project_ids": ["home", "demob"], "output_path": str(self.output),
                       "authorized_by": "Synthetic operator", "authorized_at": utc_now(),
                       "reason": "Synthetic authorization for whole approved-release visibility and this output location."}
        self.save(self.access_path, self.access)

    def save(self, path, data):
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def make_project(self, pid):
        source = self.root / "sources" / pid
        source.mkdir(parents=True)
        (source / "notes.md").write_text(
            f"2026-09-25: SYNTH-{pid} request submitted.\n"
            "Review remains proposed; effective date 2027-01-01.\n"
            "Event date is not stated for pending approval.\n", encoding="utf-8")
        config = self.root / "projects" / pid / "config/project.json"
        config.parent.mkdir(parents=True)
        self.save(config, {"schema_version": "0.1", "project": {"id": pid, "name": pid, "description": "Synthetic"},
                           "sources": [{"id": "notes", "type": "requirements", "path": str(source),
                                        "include": ["**/*"], "exclude": []}], "global_exclude": [],
                           "knowledge": {"path": "knowledge", "approved": "knowledge/approved"},
                           "runs": {"path": "runs"}})
        self.configs[pid] = config
        self.sources[pid] = source
        return config

    def candidate(self, pid, run_id, status="observed", extra=False, documents=False):
        run, manifest = inventory(self.configs[pid], run_id, documents=documents)
        file = manifest["files"][0]
        segment = read_json(run / "segments.snapshot.json")["segments"][0]
        lines = (run / file["snapshot_path"]).read_text(encoding="utf-8").splitlines()
        def citation(start, end):
            return {"evidence_id": file["evidence_id"], "segment_id": segment["segment_id"],
                    "representation_sha256": segment["representation_sha256"],
                    "start_line": start, "end_line": end, "quote": "\n".join(lines[start - 1:end])}
        cite = citation(segment["line_start"], segment["line_end"])
        record = {"id": "REQ-001", "kind": "requirement", "title": f"SYNTH-{pid} request",
                  "statement": f"The synthetic {pid} source describes a request and proposed review.",
                  "epistemic_status": status, "evidence": [cite], "relations": [], "open_questions": [],
                  "investigation": None, "events": []}
        if not documents:
            record["events"] = [
                {"id": "EVT-001", "statement": "Request submitted", "evidence_refs": [0],
                 "event_date": {"status": "known", "value": "2026-09-25", "precision": "day", "basis": "explicit_text"}},
                {"id": "EVT-002", "statement": "Review remains proposed", "evidence_refs": [0],
                 "event_date": {"status": "unknown", "basis": "not_stated", "note": "Approval event date is not stated."},
                 "effective_date": {"status": "known", "value": "2027-01-01", "precision": "day", "basis": "explicit_text"}}]
        records = {"schema_version": "0.4", "project_id": pid, "run_id": run_id,
                   "coverage": [{"evidence_id": file["evidence_id"], "disposition": "used", "note": "Synthetic source cited."}],
                   "segment_coverage": [{"segment_id": s["segment_id"], "disposition": "used" if s == segment else "reviewed_no_record",
                                         "note": "Synthetic full source read."}
                                        for s in read_json(run / "segments.snapshot.json")["segments"]],
                   "records": [record]}
        if extra:
            extra_record = dict(record, id="REQ-002", title="Synthetic review proposal", epistemic_status="proposal", events=[],
                                statement="The source keeps review proposed.")
            records["records"].append(extra_record)
        self.save(run / "proposals/records.json", records)
        return run, records

    def synthetic_publish(self, pid, run):
        review = prepare_review(self.configs[pid], run)
        review.update(decision="approve", reviewer="Synthetic test operator", reviewed_at=utc_now(),
                      notes="UNIT TEST ONLY. Not real human approval.")
        review["checks"] = dict.fromkeys(review["checks"], True)
        review["acknowledged_warnings"] = review["warning_summary"]["counts"]
        review["triage_acknowledged"] = True
        review["segment_triage_acknowledged"] = True
        self.save(run / "review.json", review)
        return publish(self.configs[pid], run, run / "review.json", human_approved=True)

    def release(self, pid, run_id, **kwargs):
        run, _ = self.candidate(pid, run_id, **kwargs)
        return self.synthetic_publish(pid, run)

    def build(self, history=False, configs=None):
        return build_index(self.access_path, self.registry_path,
                           configs if configs is not None else list(self.configs.values()), history)

    def query(self, **kwargs):
        return query_index(self.access_path, self.registry_path, list(self.configs.values()), **kwargs)

    def test_same_local_ids_remain_qualified_and_rebuild_is_byte_identical(self):
        data = self.build()
        self.assertEqual({e["key"] for e in data["entries"]}, {"home:one:REQ-001", "demob:one:REQ-001"})
        self.assertEqual({e["record_id"] for e in data["entries"]}, {"REQ-001"})
        before = self.output.read_bytes()
        before_stat = self.output.stat().st_mtime_ns
        self.assertEqual(self.build(configs=list(reversed(list(self.configs.values())))), data)
        self.assertEqual(self.output.read_bytes(), before)
        self.assertEqual(self.output.stat().st_mtime_ns, before_stat)
        self.assertEqual(check_index(self.access_path, self.registry_path, list(self.configs.values()))["status"], "passed")

    def test_provenance_resolves_to_exact_frozen_quote_and_original_record(self):
        data = self.build()
        for entry in data["entries"]:
            source = read_json(Path(entry["record_path"]))["records"][entry["record_index"]]
            self.assertEqual(source, entry["record"])
            link = entry["evidence_links"][0]
            lines = Path(link["snapshot_path"]).read_text(encoding="utf-8").splitlines()
            self.assertEqual("\n".join(lines[link["start_line"] - 1:link["end_line"]]), source["evidence"][0]["quote"])
            self.assertEqual(sha(Path(link["snapshot_path"]).read_bytes()), link["original_sha256"])
            self.assertEqual(link["segment_id"], source["evidence"][0]["segment_id"])
            self.assertEqual(link["original_locator"], "notes.md")
        project = data["projects"][0]
        self.assertEqual(project["information_domain"], "team-a")
        self.assertEqual(project["ownership_references"], [{"source_id": "notes", "pattern": "**/*.md"}])

    def test_supported_dates_and_proposal_status_survive_without_business_approval(self):
        self.release("home", "two", status="proposal")
        self.build()
        results = self.query(project_id="home")["results"]
        entry = results[0]["entry"]
        self.assertEqual(entry["review_status"], "human_reviewed_snapshot")
        self.assertEqual(entry["record"]["epistemic_status"], "proposal")
        self.assertEqual(entry["record"]["events"][1]["event_date"]["status"], "unknown")
        self.assertEqual(entry["record"]["events"][1]["effective_date"]["value"], "2027-01-01")
        self.assertEqual(self.query(epistemic_status="observed")["total_matches"], 1)
        self.assertEqual(self.query(text="request", limit=1)["total_matches"], 2)
        self.assertEqual(len(self.query(text="request", limit=1)["results"]), 1)
        self.assertEqual(self.query(text="NO SUCH CLAIM")["results"], [])

    def test_current_and_historical_results_follow_exact_selected_releases(self):
        self.build(history=True)
        self.release("home", "two")
        with self.assertRaisesRegex(KBError, "stale"):
            self.query()
        data = self.build(history=True)
        self.assertEqual(len(data["releases"]), 3)
        self.assertEqual({r["entry"]["key"] for r in self.query()["results"]}, {"home:two:REQ-001", "demob:one:REQ-001"})
        self.assertEqual({r["entry"]["key"] for r in self.query(view="historical")["results"]}, {"home:one:REQ-001"})
        self.assertEqual(self.query(view="all")["total_matches"], 3)

    def test_historical_query_requires_explicit_history_build(self):
        self.build()
        with self.assertRaisesRegex(KBError, "include-history"):
            self.query(view="historical")
        for kwargs in ({"view": "unknown"}, {"limit": 0}, {"kind": "unsupported"}, {"epistemic_status": "approved"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(KBError):
                self.query(**kwargs)

    def test_missing_approved_project_refuses_partial_index(self):
        self.make_project("missing")
        self.registry["projects"].append({"id": "missing", "name": "Missing release", "aliases": [],
                                           "information_domain": "team-a", "owns_paths": []})
        self.save(self.registry_path, self.registry)
        self.access["project_ids"].append("missing")
        self.save(self.access_path, self.access)
        with self.assertRaises((KBError, OSError)):
            self.build()
        self.assertFalse(self.output.exists())

    def test_removed_record_and_rollback_do_not_rewrite_approved_knowledge(self):
        first = self.release("home", "two", extra=True)
        pointer = first.parent / "CURRENT.json"
        previous_pointer = pointer.read_bytes()
        old_records = (first / "records.json").read_bytes()
        self.build(history=True)
        self.release("home", "three")
        with self.assertRaisesRegex(KBError, "stale"):
            self.query()
        self.build(history=True)
        self.assertEqual(self.query(project_id="home")["total_matches"], 1)
        self.assertIn("REQ-002", {r["entry"]["record_id"] for r in self.query(view="historical", project_id="home")["results"]})
        pointer.write_bytes(previous_pointer)  # Synthetic selection of an already-approved snapshot.
        with self.assertRaisesRegex(KBError, "stale"):
            self.query()
        self.build(history=True)
        self.assertEqual(self.query(project_id="home")["total_matches"], 2)
        self.assertEqual((first / "records.json").read_bytes(), old_records)
        self.output.unlink()
        self.assertTrue(pointer.is_file())
        self.assertEqual((first / "records.json").read_bytes(), old_records)

    def test_unauthorized_and_cross_domain_projects_are_rejected_before_release_read(self):
        self.access["project_ids"] = ["home"]
        self.save(self.access_path, self.access)
        with patch("kb_index.load_approved_release", side_effect=AssertionError("Unauthorized approved read")):
            with self.assertRaisesRegex(KBError, "access set"):
                self.build()
        self.access["project_ids"] = ["home", "demob"]
        self.save(self.access_path, self.access)
        self.registry["projects"][1]["information_domain"] = "team-b"
        self.save(self.registry_path, self.registry)
        with patch("kb_index.load_approved_release", side_effect=AssertionError("Different-domain read")):
            with self.assertRaisesRegex(KBError, "different-domain"):
                self.build()
        self.assertFalse(self.output.exists())

    def test_revoked_access_prevents_query_and_explicit_rebuild_drops_old_project(self):
        self.build()
        self.access["project_ids"] = ["demob"]
        self.save(self.access_path, self.access)
        with self.assertRaises(KBError):
            self.query()
        with self.assertRaisesRegex(KBError, "stale"):
            query_index(self.access_path, self.registry_path, [self.configs["demob"]])
        data = self.build(configs=[self.configs["demob"]])
        self.assertEqual({e["project_id"] for e in data["entries"]}, {"demob"})
        with self.assertRaisesRegex(KBError, "access set"):
            query_index(self.access_path, self.registry_path, [self.configs["demob"]], project_id="home")

    def test_candidates_and_intake_artifacts_are_not_indexed(self):
        run, records = self.candidate("home", "unpublished")
        records["records"][0]["title"] = "UNPUBLISHED SECRET MARKER"
        self.save(run / "proposals/records.json", records)
        ledger = self.configs["home"].parent.parent / "knowledge/referral-intake.json"
        ledger.write_text("PENDING REFERRAL SECRET MARKER", encoding="utf-8")
        self.build(history=True)
        self.assertNotIn("SECRET MARKER", self.output.read_text())
        self.assertEqual(self.query(text="SECRET")["results"], [])

    def test_pending_origin_referrals_do_not_become_target_facts(self):
        from tests.test_cross_project import ReferralIntakeTests
        fixture = ReferralIntakeTests("test_acceptance_without_capture_authorization_stays_blocked")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.prepare_origin()
        access = dict(self.access, project_ids=["home"], output_path=str(fixture.root / "index.json"))
        access_path = fixture.root / "access.json"
        self.save(access_path, access)
        data = build_index(access_path, fixture.registry_path, [fixture.config])
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(data["entries"][0]["record"]["epistemic_status"], "proposal")
        self.assertNotIn("REF-002", Path(access["output_path"]).read_text())
        self.assertNotIn("Módulo Demo remains proposed.", Path(access["output_path"]).read_text())

    def test_tampered_index_is_rejected_even_if_its_digest_is_recomputed(self):
        data = self.build()
        data["entries"][0]["record"]["statement"] = "Fabricated indexed claim"
        self.save(self.output, data)
        with self.assertRaisesRegex(KBError, "digest"):
            self.query()
        data["generation_id"] = "IDX-" + json_sha({k: v for k, v in data.items() if k != "generation_id"})[:24]
        self.save(self.output, data)
        with self.assertRaisesRegex(KBError, "differs"):
            self.query()
        self.build()
        self.assertNotIn("Fabricated", self.output.read_text())

    def test_tampered_or_unavailable_release_blocks_query_and_preserves_prior_index(self):
        self.build()
        before = self.output.read_bytes()
        path = self.releases["home"] / "records.json"
        path.write_text("{}", encoding="utf-8")
        with self.assertRaises(KBError):
            self.query()
        with self.assertRaises(KBError):
            self.build()
        self.assertEqual(self.output.read_bytes(), before)
        self.assertFalse(self.output.with_name(f".{self.output.name}.lock").exists())

    def test_inaccessible_approved_snapshot_does_not_return_cached_results(self):
        self.build()
        manifest = read_json(self.releases["home"] / "manifest.json")
        (self.releases["home"] / manifest["files"][0]["snapshot_path"]).unlink()
        with self.assertRaises((KBError, OSError)):
            self.query()

    def test_historical_release_and_publication_trace_tampering_are_detected(self):
        self.release("home", "two")
        self.build(history=True)
        path = self.releases["home"] / "review.json"
        review = read_json(path)
        review["reviewer"] = "Changed synthetic historical reviewer"
        self.save(path, review)
        with self.assertRaisesRegex(KBError, "publication trace"):
            self.query(view="historical")
        with self.assertRaisesRegex(KBError, "publication trace"):
            self.build(history=True)

    def test_output_cannot_overlap_sources_workspaces_policies_or_engine(self):
        protected = [self.sources["home"] / "index.json",
                     self.configs["home"].parent.parent / "knowledge/approved/index.json",
                     self.configs["home"], self.access_path, self.registry_path, ROOT / "index.json"]
        for path in protected:
            with self.subTest(path=path):
                self.access["output_path"] = str(path)
                self.save(self.access_path, self.access)
                with self.assertRaises(KBError):
                    self.build()

    def test_external_source_scope_and_unrelated_output_files_are_protected(self):
        source = self.root / "expanded-source"
        source.mkdir()
        self.save(self.configs["home"].parent / "source-scope.json", {
            "schema_version": "1.0", "project_id": "home", "sources": [
                {"id": "data", "type": "data", "path": str(source), "include": ["**/*.csv"], "exclude": []}]})
        self.access["output_path"] = str(source / "index.json")
        self.save(self.access_path, self.access)
        with self.assertRaisesRegex(KBError, "source root"):
            self.build()
        self.access["output_path"] = str(self.output)
        self.save(self.access_path, self.access)
        self.save(self.output, {"unrelated": "Keep this file"})
        before = self.output.read_bytes()
        with self.assertRaises(KBError):
            self.build()
        self.assertEqual(self.output.read_bytes(), before)

    def test_index_lock_and_publication_lock_refuse_concurrent_work(self):
        lock = self.output.with_name(f".{self.output.name}.lock")
        lock.write_text("Synthetic active index build", encoding="utf-8")
        with self.assertRaisesRegex(KBError, "overwrite"):
            self.build()
        self.assertTrue(lock.exists())
        lock.unlink()
        self.build()
        publish_lock = self.releases["home"].parent / ".publish.lock"
        publish_lock.write_text("Synthetic active publication", encoding="utf-8")
        with self.assertRaisesRegex(KBError, "Publication is in progress"):
            self.query()

    def test_symlink_outputs_and_sources_cannot_bypass_scope(self):
        target = self.root / "unrelated.json"
        target.write_text("Keep these bytes", encoding="utf-8")
        self.output.symlink_to(target)
        with self.assertRaisesRegex(KBError, "Symlink"):
            self.build()
        self.assertEqual(target.read_text(), "Keep these bytes")
        self.output.unlink()
        self.build()
        file = read_json(self.releases["home"] / "manifest.json")["files"][0]
        snapshot = self.releases["home"] / file["snapshot_path"]
        snapshot.unlink()
        snapshot.symlink_to(self.sources["home"] / "notes.md")
        with self.assertRaisesRegex(KBError, "Symlink"):
            self.query()

    def test_pointer_change_during_build_aborts_without_new_output(self):
        from kb_index import load_approved_release
        pointer = self.releases["home"].parent / "CURRENT.json"
        def alter(config, run_id=None):
            release = load_approved_release(config, run_id)
            if release["project_id"] == "home":
                current = read_json(pointer)
                current["published_at"] = "2026-10-04T00:00:00+00:00"
                self.save(pointer, current)
            return release
        with patch("kb_index.load_approved_release", side_effect=alter):
            with self.assertRaisesRegex(KBError, "CURRENT changed"):
                self.build()
        self.assertFalse(self.output.exists())

    def test_access_change_during_build_aborts_without_replacing_prior_index(self):
        from kb_index import _evidence_links
        self.build()
        before = self.output.read_bytes()
        def revoke(release, record):
            links = _evidence_links(release, record)
            self.access["reason"] = "Changed synthetic authorization"
            self.save(self.access_path, self.access)
            return links
        with patch("kb_index._evidence_links", side_effect=revoke):
            with self.assertRaisesRegex(KBError, "access or registry changed"):
                self.build()
        self.assertEqual(self.output.read_bytes(), before)

    def test_source_scope_change_during_build_cannot_turn_index_output_into_source(self):
        from kb_index import _evidence_links
        output = self.root / "shared/index.json"
        self.access["output_path"] = str(output)
        self.save(self.access_path, self.access)
        def change_scope(release, record):
            links = _evidence_links(release, record)
            self.save(self.configs["home"].parent / "source-scope.json", {
                "schema_version": "1.0", "project_id": "home", "sources": [
                    {"id": "data", "type": "data", "path": str(output.parent), "include": ["**/*.csv"], "exclude": []}]})
            return links
        with patch("kb_index._evidence_links", side_effect=change_scope):
            with self.assertRaisesRegex(KBError, "source scope"):
                self.build()
        self.assertFalse(output.exists())

    def test_operator_cli_build_check_and_query_use_the_same_access_contract(self):
        from kb_index import main
        common = ["--access", str(self.access_path), "--registry", str(self.registry_path)]
        for config in self.configs.values():
            common += ["--project-config", str(config)]
        results = []
        for command in (["build", "--include-history"], ["check"], ["query", "--text", "request", "--limit", "1"]):
            stream = io.StringIO()
            with patch.object(sys, "argv", ["kb_index.py", *command, *common]), redirect_stdout(stream):
                self.assertEqual(main(), 0)
            results.append(json.loads(stream.getvalue()))
        self.assertEqual(results[0]["status"], "built")
        self.assertEqual(results[1]["status"], "passed")
        self.assertEqual(results[2]["total_matches"], 2)
        self.assertEqual(len(results[2]["results"]), 1)

    def test_document_evidence_preserves_original_derived_and_locator_links(self):
        source = self.sources["home"]
        (source / "notes.md").unlink()
        (source / "notes.html").write_text("<p>Synthetic home request remains proposed.</p>", encoding="utf-8")
        release = self.release("home", "html", documents=True, status="proposal")
        data = self.build()
        entry = next(e for e in data["entries"] if e["project_id"] == "home")
        link = entry["evidence_links"][0]
        manifest_file = read_json(release / "manifest.json")["files"][0]
        self.assertEqual(link["representation_sha256"], manifest_file["representation"]["identity_sha256"])
        self.assertTrue(Path(link["original_snapshot_path"]).is_file())
        self.assertTrue(Path(link["metadata_path"]).is_file())
        self.assertNotEqual(link["snapshot_path"], link["original_snapshot_path"])
        self.assertIsNotNone(link["original_locator"])

    def test_investigation_finding_evidence_is_linked_without_replacing_parent_refs(self):
        run, data = self.candidate("home", "investigation")
        record = data["records"][0]
        cite = record["evidence"][0]
        record.update(id="INV-001", kind="investigation", epistemic_status="interpretation", events=[],
                      investigation={"question": "What does the complete synthetic source state?", "scope": [cite["evidence_id"]],
                                     "method": "Static inspection only.", "findings": [
                                         {"claim": "The source describes a request and proposed review.", "evidence": [cite]}],
                                     "limitations": ["Synthetic source only; no runtime verification."],
                                     "next_action": "Human reviewer should assess the proposed review."})
        self.save(run / "proposals/records.json", data)
        self.synthetic_publish("home", run)
        indexed = self.build()
        entry = next(e for e in indexed["entries"] if e["project_id"] == "home")
        self.assertEqual([link["role"] for link in entry["evidence_links"]], ["record", "finding"])
        self.assertEqual(entry["evidence_links"][1]["finding_index"], 0)
        self.assertEqual(entry["record"]["investigation"], record["investigation"])

    def test_older_file_level_records_do_not_claim_segment_or_event_review(self):
        run, data = self.candidate("home", "file-level")
        data["schema_version"] = "0.1"
        data.pop("segment_coverage")
        for record in data["records"]:
            record.pop("events")
            for cite in record["evidence"]:
                cite.pop("segment_id")
                cite.pop("representation_sha256")
        self.save(run / "proposals/records.json", data)
        self.synthetic_publish("home", run)
        index = self.build()
        entry = next(e for e in index["entries"] if e["project_id"] == "home")
        self.assertEqual(entry["record_schema_version"], "0.1")
        self.assertNotIn("events", entry["record"])
        self.assertIsNone(entry["evidence_links"][0]["segment_id"])
        self.assertIsNone(entry["evidence_links"][0]["original_locator"])


if __name__ == "__main__":
    unittest.main()
