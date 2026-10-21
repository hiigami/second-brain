"""Deterministic, file-bound locators for quotable source and derived text.

The inventory classifies no document semantics. Adapter locators are carried as
untrusted extraction metadata; missing-content warnings remain visible issues.
"""
import json
from pathlib import Path

from .kb_common import KBError, inside, json_sha, read_stable, sha


def build_segment_inventory(run: Path, manifest: dict) -> dict:
    """Rebuild the v1 segment inventory from verified frozen artifacts."""
    segments, issues = [], []
    seen = set()
    for f in manifest["files"]:
        representation = f["representation"]
        raw = read_stable(inside(run, f["snapshot_path"]), manifest["limits"]["max_file_bytes"])
        lines = raw.decode("utf-8-sig").splitlines()
        eid = f["evidence_id"]
        if len(lines) != f["line_count"]:
            raise KBError(f"Segment text line count mismatch: {eid}")
        if "document" in f:
            doc = f["document"]
            metadata_raw = read_stable(inside(run, doc["metadata_snapshot_path"]),
                                       manifest["limits"]["max_file_bytes"])
            try:
                metadata = json.loads(metadata_raw.decode("utf-8"))
            except (UnicodeError, ValueError) as exc:
                raise KBError(f"Segment metadata is unreadable: {eid}") from exc
            if not isinstance(metadata, dict) or not isinstance(metadata.get("segments"), list) \
                    or not isinstance(metadata.get("issues"), list):
                raise KBError(f"Segment metadata has invalid structure: {eid}")
            locations = metadata["segments"]
            if any(not isinstance(issue, dict) or not isinstance(issue.get("code"), str)
                   or not isinstance(issue.get("detail"), str) for issue in metadata["issues"]):
                raise KBError(f"Extraction issue has invalid structure: {eid}")
            warning_lines = ["# Extraction warnings (generated metadata, not source assertions)", ""]
            warning_lines.extend(json.dumps(issue, ensure_ascii=False, sort_keys=True)
                                 for issue in metadata["issues"])
            if lines[-len(warning_lines):] != warning_lines:
                raise KBError(f"Extraction warnings disagree with derived text: {eid}")
            for issue in metadata["issues"]:
                code = issue["code"]
                issues.append({"evidence_id": eid, "code": code, "detail": issue["detail"],
                               "locator": issue.get("locator"),
                               "status": "unavailable" if code in {
                                   "docx_embedded_image_not_extracted", "docx_ancillary_parts_not_extracted",
                                   "docx_comment_parts_unavailable", "docx_comment_extensions_unavailable",
                                   "docx_comment_anchor_unavailable", "docx_comment_placeholder_body_unavailable",
                                   "docx_comment_resolution_history_unavailable",
                                   "docx_comment_body_content_unavailable", "docx_comment_thread_state_unavailable",
                                   "pptx_image_not_extracted", "pptx_chart_not_extracted",
                                   "pdf_page_without_text", "pdf_embedded_image_not_extracted",
                                   "pdf_form_xobject_not_inspected", "slide_without_text",
                                   "xlsx_nonworksheet_part", "xlsx_embedded_image_not_extracted",
                                   "xlsx_chart_not_extracted", "html_visual_content_not_extracted",
                                   "html_image_not_extracted", "html_dynamic_content_unavailable",
                                   "html_active_content_not_extracted", "html_external_resource_not_fetched",
                                   "svg_visual_meaning_unavailable", "svg_external_resource_not_fetched",
                                   "svg_embedded_image_not_extracted", "svg_active_or_foreign_content_not_extracted",
                                   "svg_use_not_expanded", "svg_render_effect_not_interpreted",
                                   "png_pixels_not_interpreted",
                                   "eml_attachment_not_extracted", "eml_referenced_attachment_missing"}
                               else "review_required"})
            content_type, status = "unclassified", "extracted_needs_review"
        else:
            locations = [{"locator": f["relative_path"], "line_start": 1,
                          "line_end": len(lines)}] if lines else []
            content_type, status = "source_text", "source_text"
        prior_end = 0
        for location in locations:
            if not isinstance(location, dict) or not {"locator", "line_start", "line_end"}.issubset(location):
                raise KBError(f"Segment locator has invalid structure: {eid}")
            locator = location["locator"]
            location_type = location.get("content_type", content_type)
            if location_type not in {"source_text", "unclassified", "heading", "paragraph", "list_item",
                                     "table_cell", "table_header", "table_row", "caption", "code", "quote", "image_alt", "resource_reference", "email_header",
                                     "email_body", "email_quote", "attachment_metadata",
                                     "diagram_label", "diagram_caption", "vector_geometry",
                                     "image_region", "image_annotation", "embedded_asset"}:
                raise KBError(f"Invalid structural content type: {eid}")
            start, end = location["line_start"], location["line_end"]
            if not isinstance(locator, str) or not locator or not isinstance(start, int) \
                    or not isinstance(end, int) or start <= prior_end or end < start or end > len(lines):
                raise KBError(f"Invalid or overlapping segment locator: {eid}")
            if "document" in f and (start < 3 or lines[start - 3] !=
                                    "## Location: " + json.dumps(locator, ensure_ascii=False)):
                raise KBError(f"Segment locator disagrees with derived text: {eid}")
            prior_end = end
            line_sha = sha("\n".join(lines[start - 1:end]).encode("utf-8"))
            segment_id = "S-" + json_sha([eid, representation["identity_sha256"], locator,
                                            start, end, line_sha])[:24]
            if segment_id in seen:
                raise KBError(f"Duplicate segment identity: {segment_id}")
            seen.add(segment_id)
            segments.append({"segment_id": segment_id, "evidence_id": eid,
                             "representation_sha256": representation["identity_sha256"],
                             "content_type": location_type, "original_locator": locator,
                             "line_start": start, "line_end": end, "line_sha256": line_sha,
                             "extraction_status": status, "dependencies": []})
    return {"schema_version": "1.0", "project_id": manifest["project_id"],
            "run_id": manifest["run_id"], "segments": segments, "issues": issues}
