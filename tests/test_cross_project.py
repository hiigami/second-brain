"""Synthetic checks for the scoped project registry and mention candidates."""
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from kb_common import KBError, json_sha, read_json, sha, utc_now
from kb_check import check_run
from kb_inventory import inventory
from kb_mentions import scan_mentions
from kb_publish import current_release_records, prepare_review, publish
from kb_reanchor import reanchor


class CrossProjectMentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        source = self.root / "source"
        source.mkdir()
        self.source_file = source / "notes.md"
        self.source_file.write_text(
            "Home discusses DEMOB integration.\n"
            "Módulo Demo remains proposed.\n"
            "DEMOBX is a different token.\n"
            "Orion belongs to another information domain.\n", encoding="utf-8")
        project = self.root / "projects" / "home"
        (project / "config").mkdir(parents=True)
        self.config = project / "config" / "project.json"
        self.config.write_text(json.dumps({
            "schema_version": "0.1",
            "project": {"id": "home", "name": "Home", "description": "Synthetic workspace"},
            "sources": [{"id": "notes", "type": "requirements", "path": str(source),
                         "include": ["**/*.md"], "exclude": []}],
            "global_exclude": [],
            "knowledge": {"path": "knowledge", "approved": "knowledge/approved"},
            "runs": {"path": "runs"},
        }), encoding="utf-8")
        self.registry_path = self.root / "projects" / "registry.json"
        self.registry = {"schema_version": "1.0", "projects": [
            {"id": "home", "name": "Home", "aliases": [],
             "information_domain": "team-a", "owns_paths": []},
            {"id": "demob", "name": "Modulo Demo", "aliases": ["DEMOB"],
             "information_domain": "team-a",
             "owns_paths": [{"source_id": "repository", "pattern": "src/shared/**"}]},
            {"id": "orion", "name": "Orion", "aliases": [],
             "information_domain": "team-b", "owns_paths": []},
        ]}
        self.save_registry()
        self.run, self.manifest = inventory(self.config, "one")

    def save_registry(self):
        self.registry_path.write_text(json.dumps(self.registry), encoding="utf-8")

    def test_scan_matches_case_and_accents_with_boundaries_but_no_cross_domain_leak(self):
        report = scan_mentions(self.run, self.registry_path)
        self.assertEqual(len(report["mentions"]), 2)
        self.assertEqual([m["line"] for m in report["mentions"]], [1, 2])
        self.assertEqual([m["matched_text"] for m in report["mentions"]],
                         ["DEMOB", "Módulo Demo"])
        self.assertEqual({m["target_project_id"] for m in report["mentions"]}, {"demob"})
        self.assertEqual({m["classification"] for m in report["mentions"]},
                         {"explicit_alias_candidate"})
        self.assertEqual(report["mentions"][1]["line_text"],
                         "Módulo Demo remains proposed.")
        self.assertTrue(report["mentions"][0]["segments"])
        self.assertEqual(report["skipped_cross_domain_projects"], 1)
        self.assertEqual(report, read_json(self.run / "work" / "mentions.json"))
        self.assertEqual(scan_mentions(self.run, self.registry_path), report)

    def test_normalized_duplicate_aliases_across_projects_are_rejected(self):
        self.registry["projects"].append({
            "id": "duplicate", "name": "Duplicate", "aliases": ["Démob"],
            "information_domain": "team-a", "owns_paths": []})
        self.save_registry()
        with self.assertRaisesRegex(KBError, "alias"):
            scan_mentions(self.run, self.registry_path)
        self.assertFalse((self.run / "work" / "mentions.json").exists())

    def test_overlapping_aliases_remain_ambiguous_candidates(self):
        self.source_file.write_text("Atlas Core owns this passage.\n", encoding="utf-8")
        second_run, _ = inventory(self.config, "two")
        self.registry["projects"][1].update(name="Atlas", aliases=[])
        self.registry["projects"][2].update(name="Atlas Core", aliases=[],
                                             information_domain="team-a")
        self.save_registry()
        report = scan_mentions(second_run, self.registry_path)
        self.assertEqual({m["target_project_id"] for m in report["mentions"]},
                         {"demob", "orion"})
        self.assertEqual({m["classification"] for m in report["mentions"]},
                         {"ambiguous_alias_overlap"})

    def test_rejects_tampered_snapshot_and_changed_registry_output(self):
        original = scan_mentions(self.run, self.registry_path)
        self.registry["projects"][1]["aliases"].append("Modulo")
        self.save_registry()
        with self.assertRaisesRegex(KBError, "already exists|different"):
            scan_mentions(self.run, self.registry_path)
        self.assertEqual(read_json(self.run / "work" / "mentions.json"), original)
        frozen = self.run / self.manifest["files"][0]["snapshot_path"]
        frozen.write_text("Tampered DEMOB text.\n", encoding="utf-8")
        with self.assertRaisesRegex(KBError, "integrity|checksum"):
            scan_mentions(self.run, self.registry_path)

    def test_rejects_invalid_ownership_and_unregistered_home(self):
        self.registry["projects"][1]["owns_paths"][0]["pattern"] = "../elsewhere/**"
        self.save_registry()
        with self.assertRaises(KBError):
            scan_mentions(self.run, self.registry_path)
        self.registry["projects"][1]["owns_paths"][0]["pattern"] = "src/shared/**"
        self.registry["projects"] = self.registry["projects"][1:]
        self.save_registry()
        with self.assertRaisesRegex(KBError, "home project"):
            scan_mentions(self.run, self.registry_path)

    def test_registry_cannot_be_read_from_the_evidence_run(self):
        misplaced = self.run / "registry.json"
        misplaced.write_text(json.dumps(self.registry), encoding="utf-8")
        with self.assertRaisesRegex(KBError, "outside the evidence run"):
            scan_mentions(self.run, misplaced)

    def routed_candidate(self):
        self.registry["schema_version"] = "1.1"
        self.registry["disclosures"] = [{"from_project": "home", "to_project": "demob",
                                          "source_id": "notes", "path_pattern": "notes.md"}]
        self.save_registry()
        scan = scan_mentions(self.run, self.registry_path)
        f = self.manifest["files"][0]
        segment = read_json(self.run / "segments.snapshot.json")["segments"][0]
        lines = (self.run / f["snapshot_path"]).read_text(encoding="utf-8").splitlines()
        def citation(number):
            return {"evidence_id": f["evidence_id"], "segment_id": segment["segment_id"],
                    "representation_sha256": segment["representation_sha256"],
                    "start_line": number, "end_line": number, "quote": lines[number - 1]}
        records = {"schema_version": "0.5", "project_id": "home", "run_id": self.manifest["run_id"],
                   "coverage": [{"evidence_id": f["evidence_id"], "disposition": "used",
                                 "note": "Synthetic home requirement cited on line one."}],
                   "segment_coverage": [{"segment_id": segment["segment_id"],
                                         "disposition": "used", "note": "Synthetic mixed segment."}],
                   "records": [{"id": "REQ-001", "kind": "requirement", "title": "Home dependency",
                                "statement": "Home has a proposed DEMOB integration dependency.",
                                "epistemic_status": "proposal", "evidence": [citation(1)],
                                "relations": [], "open_questions": [], "investigation": None,
                                "events": [], "cross_project": [{"project_id": "demob",
                                                               "reason": "Shared dependency is proposed.",
                                                               "target_record": None}]}]}
        referrals = {"schema_version": "1.0", "project_id": "home", "run_id": self.manifest["run_id"],
                     "registry_sha256": json_sha(self.registry),
                     "mentions_sha256": sha((self.run / "work/mentions.json").read_bytes()),
                     "assessments": [
                         {"mention_id": scan["mentions"][0]["id"], "class": "R1",
                          "disposition": "referred", "reason": "Proposed shared dependency.",
                          "home_record_ids": ["REQ-001"], "referral_id": "REF-001"},
                         {"mention_id": scan["mentions"][1]["id"], "class": "R2",
                          "disposition": "referred", "reason": "Only target behavior is described.",
                          "home_record_ids": [], "referral_id": "REF-002"}],
                     "referrals": [
                         {"id": f"REF-00{n}", "target_project_id": "demob", "class": kind,
                          "source": citation(n), "summary": summary,
                          "why_target_cares": "Target owner should assess the proposal.",
                          "home_record_ids": homes,
                          "suggested_capture": {"source_id": "notes", "relative_path": "notes.md",
                                                "include_pattern": "notes.md"},
                          "disposition": "pending_target_review"}
                         for n, kind, summary, homes in [
                             (1, "R1", "Proposed shared dependency.", ["REQ-001"]),
                             (2, "R2", "Target-only proposal remains pending.", [])]]}
        (self.run / "proposals").mkdir(exist_ok=True)
        (self.run / "proposals/records.json").write_text(json.dumps(records), encoding="utf-8")
        (self.run / "proposals/referrals.json").write_text(json.dumps(referrals), encoding="utf-8")
        return records, referrals

    def test_routed_candidate_requires_exact_mentions_quotes_and_scope_grant(self):
        records, referrals = self.routed_candidate()
        self.assertEqual(check_run(self.run, self.run / "proposals/records.json", stage2=True)["status"], "passed")
        referrals["referrals"][1]["source"]["quote"] = "invented"
        (self.run / "proposals/referrals.json").write_text(json.dumps(referrals), encoding="utf-8")
        with self.assertRaises(KBError):
            check_run(self.run, self.run / "proposals/records.json", stage2=True)
        referrals["referrals"][1]["source"]["quote"] = "Módulo Demo remains proposed."
        self.registry["disclosures"] = []
        (self.run / "work/registry.snapshot.json").write_text(json.dumps(self.registry), encoding="utf-8")
        (self.run / "proposals/referrals.json").write_text(json.dumps(referrals), encoding="utf-8")
        with self.assertRaises(KBError):
            check_run(self.run, self.run / "proposals/records.json", stage2=True)

    def test_r2_cannot_be_home_record_and_all_mentions_need_disposition(self):
        records, referrals = self.routed_candidate()
        records["records"][0]["evidence"].append(referrals["referrals"][1]["source"])
        (self.run / "proposals/records.json").write_text(json.dumps(records), encoding="utf-8")
        with self.assertRaisesRegex(KBError, "R2|target-only"):
            check_run(self.run, self.run / "proposals/records.json", stage2=True)
        records["records"][0]["evidence"].pop()
        referrals["assessments"].pop()
        (self.run / "proposals/records.json").write_text(json.dumps(records), encoding="utf-8")
        (self.run / "proposals/referrals.json").write_text(json.dumps(referrals), encoding="utf-8")
        with self.assertRaisesRegex(KBError, "mention|assessment"):
            check_run(self.run, self.run / "proposals/records.json", stage2=True)

    def test_context_dismissal_unresolved_and_shared_component_stay_explicit(self):
        _, referrals = self.routed_candidate()
        referrals["assessments"][1].update({"class": "R3", "disposition": "dismissed",
                                           "reason": "Name-drop only; no target claim.", "referral_id": None})
        referrals["referrals"].pop()
        path = self.run / "proposals/referrals.json"
        path.write_text(json.dumps(referrals), encoding="utf-8")
        self.assertEqual(check_run(self.run, self.run / "proposals/records.json", stage2=True)["referral_count"], 1)
        referrals["assessments"][1].update({"class": "R2", "disposition": "unresolved",
                                           "reason": "Target ownership is uncertain."})
        path.write_text(json.dumps(referrals), encoding="utf-8")
        self.assertEqual(check_run(self.run, self.run / "proposals/records.json", stage2=True)["routing_unresolved_count"], 1)
        referrals["assessments"][0]["class"] = "R4"
        referrals["referrals"][0]["class"] = "R4"
        path.write_text(json.dumps(referrals), encoding="utf-8")
        self.assertEqual(check_run(self.run, self.run / "proposals/records.json", stage2=True)["status"], "passed")

    def test_referral_requires_a_matching_explicit_source_grant(self):
        _, referrals = self.routed_candidate()
        self.registry["disclosures"][0]["path_pattern"] = "different.md"
        self.save_registry()
        from kb_mentions import build_mention_report
        (self.run / "work/registry.snapshot.json").write_text(json.dumps(self.registry), encoding="utf-8")
        scan = build_mention_report(self.run, self.registry)
        (self.run / "work/mentions.json").write_text(json.dumps(scan), encoding="utf-8")
        referrals["registry_sha256"] = json_sha(self.registry)
        referrals["mentions_sha256"] = sha((self.run / "work/mentions.json").read_bytes())
        (self.run / "proposals/referrals.json").write_text(json.dumps(referrals), encoding="utf-8")
        with self.assertRaisesRegex(KBError, "disclosure grant"):
            check_run(self.run, self.run / "proposals/records.json", stage2=True)

    def test_live_registry_changes_do_not_rewrite_frozen_routing_policy(self):
        self.routed_candidate()
        self.registry["disclosures"] = []
        self.save_registry()
        self.assertEqual(check_run(self.run, self.run / "proposals/records.json", stage2=True)["status"], "passed")
        frozen = self.run / "work/registry.snapshot.json"
        data = read_json(frozen)
        data["disclosures"] = []
        frozen.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(KBError, "registry|mention"):
            check_run(self.run, self.run / "proposals/records.json", stage2=True)

    def test_synthetic_review_binds_referrals_and_publishes_origin_outbox(self):
        _, referrals = self.routed_candidate()
        review = prepare_review(self.config, self.run)
        self.assertEqual(review["schema_version"], "0.4")
        self.assertFalse(review["checks"]["cross_project_checked"])
        self.assertEqual(review["referrals_sha256"], sha((self.run / "proposals/referrals.json").read_bytes()))
        report_text = (self.run / "review-report.md").read_text(encoding="utf-8")
        self.assertIn("Cross-project routing review", report_text)
        self.assertIn("Only target behavior is described", report_text)
        self.assertFalse((self.run / "outbox.md").exists())
        review["decision"] = "approve"
        review["reviewer"] = "Synthetic reviewer"
        review["reviewed_at"] = utc_now()
        review["acknowledged_warnings"] = review["warning_summary"]["counts"]
        review["checks"] = {key: key != "cross_project_checked" for key in review["checks"]}
        review_path = self.run / "review.json"
        review_path.write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaisesRegex(KBError, "checks"):
            publish(self.config, self.run, review_path, human_approved=True)
        review["checks"]["cross_project_checked"] = True
        review_path.write_text(json.dumps(review), encoding="utf-8")
        referrals["referrals"][0]["summary"] = "Changed after review"
        (self.run / "proposals/referrals.json").write_text(json.dumps(referrals), encoding="utf-8")
        with self.assertRaisesRegex(KBError, "referral|stale"):
            publish(self.config, self.run, review_path, human_approved=True)
        referrals["referrals"][0]["summary"] = "Proposed shared dependency."
        (self.run / "proposals/referrals.json").write_text(json.dumps(referrals), encoding="utf-8")
        release = publish(self.config, self.run, review_path, human_approved=True)
        self.assertTrue((release / "referrals.json").is_file())
        self.assertIn("REF-002", (release / "outbox.md").read_text(encoding="utf-8"))
        original_referrals = (release / "referrals.json").read_bytes()
        (release / "referrals.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(KBError, "integrity"):
            current_release_records(release.parent, "home")
        (release / "referrals.json").write_bytes(original_referrals)
        (release / "outbox.md").write_text("Tampered outbox.\n", encoding="utf-8")
        with self.assertRaisesRegex(KBError, "outbox.md"):
            current_release_records(release.parent, "home")

    def test_routing_aware_release_requires_fresh_classification_on_reanchor(self):
        self.routed_candidate()
        self.source_file.write_text("A later DEMOB proposal.\n", encoding="utf-8")
        next_run, _ = inventory(self.config, "two")
        with self.assertRaisesRegex(KBError, "cannot be re-anchored"):
            reanchor(self.run, next_run)


class ReferralIntakeTests(unittest.TestCase):
    """Target intake uses published synthetic origins and independently captured targets."""

    setUp = CrossProjectMentionTests.setUp
    save_registry = CrossProjectMentionTests.save_registry
    routed_candidate = CrossProjectMentionTests.routed_candidate

    def prepare_origin(self, run_id=None, change=None, withdraw=False):
        if run_id:
            self.run, self.manifest = inventory(self.config, run_id)
        records, referrals = self.routed_candidate()
        if change:
            referrals["referrals"][1]["summary"] = change
        if withdraw:
            referrals["referrals"].pop()
            referrals["assessments"][1].update({"class": "R3", "disposition": "dismissed",
                                                  "reason": "Synthetic withdrawn routing.", "referral_id": None})
        (self.run / "proposals/referrals.json").write_text(json.dumps(referrals), encoding="utf-8")
        return self.synthetic_publish(self.config, self.run)

    def synthetic_publish(self, config, run):
        review = prepare_review(config, run)
        review.update(decision="approve", reviewer="Synthetic reviewer", reviewed_at=utc_now())
        review["acknowledged_warnings"] = review["warning_summary"]["counts"]
        review["checks"] = {key: True for key in review["checks"]}
        review["triage_acknowledged"] = True
        review["segment_triage_acknowledged"] = True
        path = run / "review.json"
        path.write_text(json.dumps(review), encoding="utf-8")
        return publish(config, run, path, human_approved=True)

    def target_config(self):
        path = self.root / "projects/demob/config/project.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        source = self.root / "target-source"
        source.mkdir(exist_ok=True)
        config = read_json(self.config)
        config["project"].update(id="demob", name="Modulo Demo")
        config["sources"][0]["path"] = str(source)
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    def discover(self):
        from kb_referrals import discover
        return discover(self.target, self.registry_path, [self.config])

    def intake(self):
        self.release = self.prepare_origin()
        self.target = self.target_config()
        return self.discover()["items"][1]

    def review(self, item, decision="accept", capture=None, reason="Synthetic target review."):
        data = {"schema_version": "1.0", "item_id": item["id"],
                "origin_review_sha256": item["origin_review_sha256"],
                "decision": decision, "reviewer": "Synthetic target reviewer",
                "reviewed_at": utc_now(), "reason": reason, "capture_authorization": capture}
        path = self.root / "intake-review.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def full_capture(self):
        return {"mode": "full_file", "path": str(self.source_file),
                "sha256": sha(self.source_file.read_bytes()),
                "reason": "Synthetic human authorizes every part of this mixed file."}

    def decide(self, path):
        from kb_referrals import decide
        return decide(self.target, self.registry_path, self.config, path)

    def target_release(self, name="target-one", capture=None, cited=True):
        config = read_json(self.target)
        path = Path(config["sources"][0]["path"]) / "captured.md"
        path.write_bytes(Path(capture["path"]).read_bytes() if capture else self.source_file.read_bytes())
        run, manifest = inventory(self.target, name)
        file = manifest["files"][0]
        segment = read_json(run / "segments.snapshot.json")["segments"][0]
        quote = path.read_text(encoding="utf-8").splitlines()
        records = {"schema_version": "0.3", "project_id": "demob", "run_id": name,
                   "coverage": [{"evidence_id": file["evidence_id"], "disposition": "used", "note": "Synthetic target capture."}],
                   "segment_coverage": [{"segment_id": segment["segment_id"], "disposition": "used", "note": "Synthetic target read."}],
                   "records": [{"id": "REQ-001", "kind": "requirement", "title": "Target proposal",
                                "statement": "Target proposal remains proposed.", "epistemic_status": "proposal",
                                "evidence": [{"evidence_id": file["evidence_id"], "segment_id": segment["segment_id"],
                                              "representation_sha256": segment["representation_sha256"],
                                              "start_line": 1, "end_line": len(quote) if cited else 1,
                                              "quote": "\n".join(quote if cited else quote[:1])}],
                                "relations": [], "open_questions": [], "investigation": None}]}
        (run / "proposals/records.json").write_text(json.dumps(records), encoding="utf-8")
        return self.synthetic_publish(self.target, run)

    def link_review(self, item, release):
        data = {"schema_version": "1.0", "item_id": item["id"], "target_run_id": release.name,
                "target_review_sha256": sha((release / "review.json").read_bytes()),
                "record_ids": ["REQ-001"], "reviewer": "Synthetic target reviewer",
                "reviewed_at": utc_now(), "reason": "Synthetic reviewed target provenance linkage."}
        path = self.root / "intake-link.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_discovery_retries_do_not_duplicate_or_rewrite_work(self):
        self.intake()
        path = self.target.parent.parent / "knowledge/referral-intake.json"
        before = path.read_bytes()
        self.assertEqual(len(self.discover()["items"]), 2)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((path.parent / "approved").exists())
        self.assertFalse((self.target.parent.parent / "runs").exists())

    def test_acceptance_without_capture_authorization_stays_blocked(self):
        item = self.intake()
        result = self.decide(self.review(item))
        self.assertEqual(result["capture_task"]["status"], "blocked_capture_authorization")
        self.assertEqual(result["capture_task"]["provenance"]["source"], item["referral"]["source"])
        self.assertFalse((self.target.parent.parent / "knowledge/approved").exists())

    def test_decline_defer_and_exact_decision_retries_preserve_audit(self):
        item = self.intake()
        decline = self.review(item, "decline", reason="Synthetic target declines relevance.")
        first = self.decide(decline)
        self.assertEqual(first["decisions"][-1]["decision"], "decline")
        self.assertIsNone(first["capture_task"])
        self.assertEqual(self.decide(decline), first)
        self.assertEqual(self.discover()["items"][1]["decisions"], first["decisions"])
        result = self.decide(self.review(item, "defer", reason="Synthetic target needs clarification."))
        self.assertEqual(len(result["decisions"]), 2)
        self.assertEqual(result["decisions"][-1]["decision"], "defer")
        with self.assertRaises(KBError):
            self.decide(self.review(item, "decline", reason=" "))

    def test_full_file_capture_requires_explicit_matching_bytes(self):
        item = self.intake()
        capture = self.full_capture()
        result = self.decide(self.review(item, capture=capture))
        self.assertEqual(result["capture_task"]["status"], "proposed_capture_reconciliation")
        capture["sha256"] = "0" * 64
        with self.assertRaisesRegex(KBError, "bytes changed"):
            self.decide(self.review(item, capture=capture))

    def test_scoped_export_is_traceable_and_cannot_hide_whole_file_copy(self):
        item = self.intake()
        path = self.root / "reviewed-export.md"
        path.write_text("Synthetic approved scoped export:\n" + item["referral"]["source"]["quote"] + "\n", encoding="utf-8")
        capture = {"mode": "scoped_export", "path": str(path), "sha256": sha(path.read_bytes()),
                   "reason": "Only this qualified target passage is authorized."}
        result = self.decide(self.review(item, capture=capture))
        self.assertEqual(result["capture_task"]["capture_authorization"], capture)
        path.write_text("Dropped pending qualifiers.\n", encoding="utf-8")
        capture["sha256"] = sha(path.read_bytes())
        with self.assertRaisesRegex(KBError, "exact referred quote"):
            self.decide(self.review(item, capture=capture))
        capture = self.full_capture()
        capture["mode"] = "scoped_export"
        with self.assertRaisesRegex(KBError, "entire original"):
            self.decide(self.review(item, capture=capture))

    def test_corrected_origin_requires_fresh_review_without_target_rewrite(self):
        old = self.intake()
        self.decide(self.review(old, capture=self.full_capture()))
        target_release = self.target_release()
        original = (target_release / "records.json").read_bytes()
        self.prepare_origin("two", change="Corrected target proposal still needs review.")
        data = self.discover()
        prior = next(i for i in data["items"] if i["id"] == old["id"])
        current = next(i for i in data["items"] if i["supersedes"] == old["id"])
        self.assertEqual(prior["source_status"], "superseded")
        self.assertEqual(prior["capture_task"]["status"], "blocked_source_superseded")
        self.assertEqual(prior["decisions"][-1]["decision"], "accept")
        self.assertEqual(current["decisions"], [])
        self.assertIsNone(current["capture_task"])
        self.assertEqual((target_release / "records.json").read_bytes(), original)
        with self.assertRaisesRegex(KBError, "stale"):
            self.decide(self.review(old, capture=self.full_capture()))

    def test_withdrawal_after_acceptance_keeps_history_and_approved_target(self):
        from kb_referrals import link_target
        old = self.intake()
        self.decide(self.review(old, capture=self.full_capture()))
        target = self.target_release()
        link_target(self.target, self.link_review(old, target))
        before = (target / "records.json").read_bytes()
        self.prepare_origin("two", withdraw=True)
        item = next(i for i in self.discover()["items"] if i["id"] == old["id"])
        self.assertEqual(item["source_status"], "withdrawn")
        self.assertEqual(item["capture_task"]["status"], "blocked_source_withdrawn")
        self.assertEqual(item["decisions"][-1]["decision"], "accept")
        self.assertEqual(item["target_links"][0]["review"]["target_run_id"], target.name)
        self.assertEqual((target / "records.json").read_bytes(), before)

    def test_live_disclosure_revocation_blocks_new_and_existing_intake(self):
        item = self.intake()
        self.registry["disclosures"] = []
        self.save_registry()
        self.assertEqual(self.discover()["items"][1]["source_status"], "unauthorized")
        with self.assertRaisesRegex(KBError, "authorize"):
            self.decide(self.review(item, capture=self.full_capture()))
        path = self.target.parent.parent / "knowledge/referral-intake.json"
        path.unlink()
        self.assertEqual(self.discover()["items"], [])

    def test_unavailable_and_unscanned_origins_are_not_withdrawals(self):
        from kb_referrals import discover
        self.intake()
        path = self.release / "referrals.json"
        before = path.read_bytes()
        path.write_text("{}", encoding="utf-8")
        self.assertEqual({i["source_status"] for i in self.discover()["items"]}, {"unavailable"})
        path.write_bytes(before)
        self.assertEqual({i["source_status"] for i in self.discover()["items"]}, {"current"})
        self.assertEqual({i["source_status"] for i in discover(self.target, self.registry_path, [])["items"]}, {"stale"})

    def test_candidate_or_unapproved_origin_is_never_discovered(self):
        self.routed_candidate()
        self.target = self.target_config()
        self.assertEqual(self.discover()["items"], [])
        self.assertEqual(self.discover()["origin_scans"], [{"project_id": "home", "status": "unavailable", "run_id": None}])
        self.release = self.synthetic_publish(self.config, self.run)
        review_path = self.release / "review.json"
        review = read_json(review_path)
        review["decision"] = "changes_requested"
        review_path.write_text(json.dumps(review), encoding="utf-8")
        pointer = self.release.parent / "CURRENT.json"
        current = read_json(pointer)
        current["review_sha256"] = sha(review_path.read_bytes())
        pointer.write_text(json.dumps(current), encoding="utf-8")
        self.assertEqual(self.discover()["items"], [])
        self.assertEqual(self.discover()["origin_scans"][0]["status"], "unavailable")

    def test_target_link_uses_own_ids_and_survives_independent_target_releases(self):
        from kb_referrals import link_target
        item = self.intake()
        self.decide(self.review(item, capture=self.full_capture()))
        first = self.target_release()
        path = self.link_review(item, first)
        linked = link_target(self.target, path)
        self.assertEqual(link_target(self.target, path), linked)
        comparison = linked["target_links"][0]["evidence_comparison"][0]
        self.assertNotEqual(comparison["evidence_id"], item["referral"]["source"]["evidence_id"])
        self.assertEqual(comparison["original_sha256"], item["source_file"]["sha256"])
        self.assertEqual(comparison["comparison"], "different_representation_or_locator")
        second = self.target_release("target-two")
        self.assertEqual(link_target(self.target, path), linked)
        self.assertEqual(self.discover()["items"][1]["target_links"][0]["review"]["target_run_id"], first.name)
        result = link_target(self.target, self.link_review(item, second))
        self.assertEqual(len(result["target_links"]), 2)

    def test_scoped_export_target_link_and_missing_target_citation(self):
        from kb_referrals import link_target
        item = self.intake()
        export = self.root / "scoped.md"
        export.write_text("Synthetic scoped export\n" + item["referral"]["source"]["quote"] + "\n", encoding="utf-8")
        capture = {"mode": "scoped_export", "path": str(export), "sha256": sha(export.read_bytes()),
                   "reason": "Synthetic approved export."}
        self.decide(self.review(item, capture=capture))
        release = self.target_release(capture=capture)
        linked = link_target(self.target, self.link_review(item, release))
        self.assertEqual(linked["target_links"][0]["evidence_comparison"][0]["comparison"], "scoped_export")
        unrelated = self.target_release("target-two", capture=capture, cited=False)
        with self.assertRaisesRegex(KBError, "own citation"):
            link_target(self.target, self.link_review(item, unrelated))

    def test_ledger_lock_symlink_and_identity_tampering_fail_closed(self):
        self.intake()
        root = self.target.parent.parent / "knowledge"
        lock = root / ".referral-intake.lock"
        lock.write_text("Synthetic concurrent operation", encoding="utf-8")
        with self.assertRaisesRegex(KBError, "overwrite"):
            self.discover()
        lock.unlink()
        ledger = root / "referral-intake.json"
        data = read_json(ledger)
        data["items"][0]["origin_run_id"] = "fake"
        ledger.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(KBError, "identity"):
            self.discover()
        ledger.unlink()
        ledger.symlink_to(self.root / "outside.json")
        with self.assertRaisesRegex(KBError, "Symlink"):
            self.discover()

    def test_source_provenance_tampering_and_stale_review_cannot_authorize_capture(self):
        item = self.intake()
        review_path = self.review(item, capture=self.full_capture())
        review = read_json(review_path)
        review["origin_review_sha256"] = "0" * 64
        review_path.write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaisesRegex(KBError, "stale"):
            self.decide(review_path)
        ledger = self.target.parent.parent / "knowledge/referral-intake.json"
        data = read_json(ledger)
        data["items"][1]["source_file"]["sha256"] = "0" * 64
        ledger.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(KBError, "stale"):
            self.decide(self.review(item, capture=self.full_capture()))

    def test_scope_and_source_changes_during_discovery_do_not_write_a_ledger(self):
        from kb_referrals import _source_file
        self.release = self.prepare_origin()
        self.target = self.target_config()
        ledger = self.target.parent.parent / "knowledge/referral-intake.json"
        def revoke(origin, referral):
            result = _source_file(origin, referral)
            self.registry["disclosures"] = []
            self.save_registry()
            return result
        with patch("kb_referrals._source_file", side_effect=revoke):
            with self.assertRaisesRegex(KBError, "Registry changed"):
                self.discover()
        self.assertFalse(ledger.exists())

        self.assertFalse(ledger.with_name(".referral-intake.lock").exists())
        self.registry["disclosures"] = [{"from_project": "home", "to_project": "demob",
                                          "source_id": "notes", "path_pattern": "notes.md"}]
        self.save_registry()
        def alter(origin, referral):
            result = _source_file(origin, referral)
            (self.release / "records.json").write_text("{}", encoding="utf-8")
            return result
        with patch("kb_referrals._source_file", side_effect=alter):
            with self.assertRaisesRegex(KBError, "Approved release changed"):
                self.discover()
        self.assertFalse(ledger.exists())

    def test_review_changed_after_pointer_validation_is_not_imported(self):
        self.release = self.prepare_origin()
        self.target = self.target_config()
        def alter_review(approved, project_id):
            result = current_release_records(approved, project_id)
            path = self.release / "review.json"
            review = read_json(path)
            review["reviewer"] = "Changed synthetic reviewer after pointer validation"
            path.write_text(json.dumps(review), encoding="utf-8")
            return result
        with patch("kb_referrals.current_release_records", side_effect=alter_review):
            data = self.discover()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["origin_scans"][0]["status"], "unavailable")

    def test_rollback_reuses_existing_item_without_cyclic_lineage(self):
        old = self.intake()
        pointer = self.release.parent / "CURRENT.json"
        original_pointer = pointer.read_bytes()
        self.decide(self.review(old, "decline", reason="Synthetic old referral declined."))
        self.prepare_origin("two", change="Synthetic correction")
        self.assertEqual(len(self.discover()["items"]), 4)
        # Synthetic selection of the previous already-approved snapshot; no new
        # approval or publication is performed by the intake tool.
        pointer.write_bytes(original_pointer)
        data = self.discover()
        self.assertEqual(len(data["items"]), 4)
        restored = next(i for i in data["items"] if i["id"] == old["id"])
        self.assertEqual(restored["source_status"], "current")
        self.assertEqual(restored["decisions"][-1]["decision"], "decline")
        self.assertEqual({i["source_status"] for i in data["items"] if i["origin_run_id"] == "two"}, {"superseded"})

    def test_different_domain_origins_are_not_opened(self):
        from kb_referrals import discover
        self.release = self.prepare_origin()
        self.target = self.target_config()
        self.registry["disclosures"] = []
        self.registry["projects"][1]["information_domain"] = "team-b"
        self.save_registry()
        with patch("kb_referrals._approved_release", side_effect=AssertionError("Unauthorized release read")):
            data = discover(self.target, self.registry_path, [self.config])
            self.assertEqual(data["items"], [])
            self.assertEqual(data["origin_scans"][0]["status"], "unauthorized")

    def test_unavailable_capture_and_nonaccepted_capture_do_not_change_decision(self):
        item = self.intake()
        capture = self.full_capture()
        self.source_file.unlink()
        with self.assertRaises(OSError):
            self.decide(self.review(item, capture=capture))
        self.assertEqual(self.discover()["items"][1]["decisions"], [])
        with self.assertRaisesRegex(KBError, "acceptance"):
            self.decide(self.review(item, "decline", capture=capture))

    def test_target_link_rejects_unpublished_or_unapproved_target(self):
        from kb_referrals import link_target
        item = self.intake()
        self.decide(self.review(item, capture=self.full_capture()))
        path = self.root / "intake-link.json"
        path.write_text(json.dumps({"schema_version": "1.0", "item_id": item["id"],
                                   "target_run_id": "missing", "target_review_sha256": "0" * 64,
                                   "record_ids": ["REQ-001"], "reviewer": "Synthetic reviewer",
                                   "reviewed_at": utc_now(), "reason": "Synthetic link attempt."}), encoding="utf-8")
        with self.assertRaises((KBError, OSError)):
            link_target(self.target, path)
        release = self.target_release()
        path = self.link_review(item, release)
        review_path = release / "review.json"
        review = read_json(review_path)
        review["checks"]["privacy_checked"] = False
        review_path.write_text(json.dumps(review), encoding="utf-8")
        pointer = release.parent / "CURRENT.json"
        current = read_json(pointer)
        current["review_sha256"] = sha(review_path.read_bytes())
        pointer.write_text(json.dumps(current), encoding="utf-8")
        with self.assertRaisesRegex(KBError, "approved"):
            link_target(self.target, path)


if __name__ == "__main__":
    unittest.main()
