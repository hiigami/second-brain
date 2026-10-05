"""Shared synthetic fixtures for the offline test suite. Never real project data."""
from pathlib import Path

from kb_common import read_stable

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SOURCES = FIXTURES / "sources"
PROJECT_CONFIG = FIXTURES / "project" / "project.json"
PROVENANCE = FIXTURES / "project" / "source-provenance.json"
LEGACY_RUN = FIXTURES / "legacy-run-v0.1"


def synthetic_records(run: Path, manifest: dict, schema_version: str = "0.1") -> dict:
    files = {f["source_id"]: f for f in manifest["files"]}
    def ev(source: str, start: int, end: int) -> dict:
        f = files[source]
        lines = read_stable(run / f["snapshot_path"], 2_000_000).decode("utf-8-sig").splitlines()
        return {"evidence_id": f["evidence_id"], "start_line": start, "end_line": end,
                "quote": "\n".join(lines[start - 1:end])}
    def record(rid, kind, title, statement, status, evidence, relations=None, questions=None, investigation=None):
        return dict(id=rid, kind=kind, title=title, statement=statement, epistemic_status=status,
                    evidence=evidence, relations=relations or [], open_questions=questions or [], investigation=investigation)
    rows = [
        record("REQ-001", "requirement", "Synthetic candidate limit", "The fixture states a maximum of 10 candidates per response.", "observed", [ev("requirements", 3, 3)]),
        record("REQ-002", "requirement", "Synthetic no-results behavior", "The fixture requires an explicit no-results response.", "observed", [ev("requirements", 4, 4)]),
        record("DEC-001", "decision", "Synthetic recorded backend decision", "The architecture fixture records Azure Search as the only search backend; this does not establish any real project's decision.", "observed", [ev("architecture", 3, 4)]),
        record("UNC-001", "uncertainty", "Proposed limit conflicts with stated limit", "A Spanish meeting fixture proposes 20 candidates without approval, while the requirement fixture states 10. Approval authority is unresolved.", "unresolved", [ev("requirements", 3, 3), ev("meetings", 3, 4)], [{"type": "conflicts_with", "target": "REQ-001"}], ["Who can approve the change, and has the requirement owner accepted it?"]),
        record("INV-001", "investigation", "Trace the candidate limit in bounded code/schema fixtures", "The inspected formatter uses a limit of 10. The inspected schema defines material identity and name, not a candidate-limit setting. This static evidence cannot establish end-to-end behavior or approve 20.", "interpretation", [ev("repository", 3, 6), ev("sql", 2, 5)], [{"type": "investigates", "target": "REQ-001"}, {"type": "investigates", "target": "UNC-001"}], ["Would changing the limit affect pagination, performance, or other callers?"],
               {"question": "Can the proposed candidate-limit change be justified using only the scoped code and schema fixtures?",
                "scope": [files[s]["evidence_id"] for s in ["requirements", "meetings", "sql", "repository"]],
                "method": "Static inspection of the frozen lines only. No SQL or repository code was executed.",
                "findings": [
                    {"claim": "The formatter slices candidates using MAX_RESULTS = 10.", "evidence": [ev("repository", 3, 6)]},
                    {"claim": "The complete inspected table definition contains material_code and name; it does not define a candidate-limit setting.", "evidence": [ev("sql", 2, 5)]},
                    {"claim": "The proposal explicitly remains unapproved.", "evidence": [ev("meetings", 3, 4)]}],
                "limitations": ["Synthetic fixtures only; no production system or complete repository was inspected.", "Static inspection does not verify performance, authorization, data contents, or runtime integration."],
                "next_action": "Ask the requirement owner to resolve UNC-001 before proposing an implementation change."})]
    return {"schema_version": schema_version, "project_id": manifest["project_id"], "run_id": manifest["run_id"],
            "coverage": [{"evidence_id": f["evidence_id"], "disposition": "used", "note": "Synthetic expected-output example; not an LLM extraction or human review."} for f in manifest["files"]], "records": rows}
