"""Bounded joins for DOCX annotation metadata, separate from business authority.

Parts have already passed the adapter's safe XML and ZIP checks. No links are
followed. Recorded dates retain their spelling; resolution history is unknown.
"""
from datetime import datetime
import json
import posixpath
import re

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"
W15 = "{http://schemas.microsoft.com/office/word/2012/wordml}"
CID = "{http://schemas.microsoft.com/office/word/2016/wordml/cid}"
CEX = "{http://schemas.microsoft.com/office/word/2018/wordml/cex}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
ROLES = {
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments": ("comments", W, "comments", "comment"),
    "http://schemas.microsoft.com/office/2011/relationships/commentsExtended": ("extended", W15, "commentsEx", "commentEx"),
    "http://schemas.microsoft.com/office/2016/09/relationships/commentsIds": ("ids", CID, "commentsIds", "commentId"),
    "http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible": ("extensible", CEX, "commentsExtensible", "commentExtensible"),
}


def prepare_comments(parts, builder, error):
    """Validate parts and thread links before python-docx traverses any bodies."""
    def fail(detail):
        raise error("docx_comment_metadata_invalid", detail)

    selected, relationship_id = {}, None
    rels = parts.get("word/_rels/document.xml.rels")
    if rels is not None:
        comment_relationships = any(r.get("Type") in ROLES for r in rels)
        if comment_relationships and (rels.tag != REL + "Relationships"
                or len({r.get("Id") for r in rels}) != len(rels)):
            fail("Invalid or ambiguous document relationships")
        seen_ids = set()
        for relationship in rels:
            kind = relationship.get("Type")
            if kind not in ROLES:
                continue
            role, namespace, root_tag, _ = ROLES[kind]
            identifier, target = relationship.get("Id"), relationship.get("Target", "")
            if not identifier or identifier in seen_ids or role in selected:
                fail("Duplicate or missing comment-part relationship identity")
            seen_ids.add(identifier)
            if relationship.tag != REL + "Relationship" or relationship.get("TargetMode", "Internal") != "Internal":
                fail("Comment parts must use internal package relationships")
            if not target or any(c in target for c in ("\\", ":", "?", "#", "%")):
                fail("Unsafe or unsupported comment-part target")
            name = posixpath.normpath(target.lstrip("/") if target.startswith("/") else "word/" + target)
            if name.startswith("../") or name not in parts or parts[name].tag != namespace + root_tag:
                fail("Missing or invalid comment-part container: " + name)
            selected[role] = (name, parts[name])
            if role == "comments":
                relationship_id = identifier
    recognized_roots = {ns + tag for _, ns, tag, _ in ROLES.values()}
    selected_names = {name for name, _ in selected.values()}
    for name, root in parts.items():
        if root.tag in recognized_roots and name not in selected_names:
            builder.warning("docx_comment_parts_unavailable", "Unlinked comment part was not interpreted", name)
    marker_tags = {W + t: t for t in ("commentReference", "commentRangeStart", "commentRangeEnd")}
    if "comments" not in selected:
        if selected:
            fail("Comment metadata has no associated comments part")
        if any(element.tag in marker_tags for element in parts["word/document.xml"].iter()):
            builder.warning("docx_comment_anchor_unavailable",
                            "Comment markers remain but no linked comments part is available; annotation content was not extracted",
                            "DOCX/part=word/document.xml")
        return {"parts": selected_names, "records": [], "relationship_id": None}

    # Iterative preflight precedes recursive paragraph/table traversal and joins.
    nodes = 0
    for name, root in [("word/document.xml", parts["word/document.xml"]), *selected.values()]:
        stack = [(root, 1)]
        while stack:
            element, depth = stack.pop()
            nodes += 1
            if nodes > builder.limits.max_structure_nodes or depth > builder.limits.max_structure_depth:
                raise error("extraction_budget_exceeded", "DOCX annotation structure exceeds node/depth limits")
            stack.extend((child, depth + 1) for child in element)

    def hex_id(value, *, durable=False):
        if value is None or not re.fullmatch(r"[0-9a-fA-F]{8}", value):
            fail("Comment paragraph/durable ID must be eight hexadecimal digits")
        if durable and not 0 < int(value, 16) < 0x7FFFFFFF:
            fail("Comment durable ID is outside the permitted range")
        return value.upper()

    def comment_id(value):
        if value is None or not re.fullmatch(r"-?[0-9]{1,18}", value):
            fail("Invalid comment ID")
        return int(value)

    def flag(value, default=False):
        if value is None:
            return default
        values = {"true": True, "1": True, "on": True, "false": False, "0": False, "off": False}
        if value not in values:
            fail("Invalid comment boolean value")
        return values[value]

    def date(value, *, utc=False):
        if value is None:
            return None
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})?", value):
            fail("Invalid recorded comment date")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            fail("Invalid recorded comment date")
        if re.search(r"[+-][0-9]{2}:[0-9]{2}$", value) and (int(value[-5:-3]) > 14
                or int(value[-2:]) > 59 or (int(value[-5:-3]) == 14 and int(value[-2:]) != 0)):
            fail("Invalid recorded comment timezone offset")
        # dateUtc's attribute definition supplies UTC even without a suffix.
        if utc and parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() != 0:
            fail("Modern comment dateUtc cannot record a nonzero UTC offset")
        return value

    def entries(role, allowed):
        if role not in selected:
            return []
        name, root = selected[role]
        _, namespace, _, child_tag = next(spec for spec in ROLES.values() if spec[0] == role)
        result = []
        for element in root:
            if element.tag != namespace + child_tag:
                if element.tag.rsplit("}", 1)[-1] == child_tag:
                    fail("Invalid comment metadata namespace")
                builder.warning("docx_comment_extensions_unavailable", "Unsupported comment extension content", name)
                continue
            if any(attribute not in {namespace + key for key in allowed} for attribute in element.attrib) or len(element):
                builder.warning("docx_comment_extensions_unavailable", "Unsupported comment extension fields/content", name)
            result.append(element)
        if root.attrib:
            builder.warning("docx_comment_extensions_unavailable", "Unsupported comment container attributes", name)
        return result

    records, by_id, by_paragraph = [], {}, {}
    name, root = selected["comments"]
    for element in root:
        if element.tag != W + "comment":
            fail("Unexpected element in comments container")
        identifier = comment_id(element.get(W + "id"))
        if identifier in by_id:
            fail("Duplicate comment ID")
        paragraphs = list(element.iter(W + "p"))
        if not paragraphs:
            fail("Comment body has no paragraph")
        paragraph = paragraphs[-1].get(W14 + "paraId")
        if paragraph is not None:
            key = hex_id(paragraph)
            if key in by_paragraph:
                fail("Ambiguous last-paragraph ID")
        if any(e.tag in {W + t for t in ("ins", "del", "moveFrom", "moveTo")} for e in element.iter()):
            raise error("tracked_changes_require_review", "Comment tracked changes require a reviewed copy")
        if any(e.tag in {W + t for t in ("sdt", "txbxContent", "altChunk")} for e in element.iter()):
            raise error("docx_structure_requires_export", "Comment content controls, text boxes or imported chunks require export")
        known_attributes = {W + t for t in ("id", "author", "initials", "date")}
        if any(attribute not in known_attributes for attribute in element.attrib):
            builder.warning("docx_comment_extensions_unavailable", "Unsupported comment attributes", name)
        supported_namespaces = (W, W14)
        if any(not e.tag.startswith(supported_namespaces) for e in element.iter()):
            builder.warning("docx_comment_extensions_unavailable", "Unsupported comment body extensions", name)
        if any(child.tag not in {W + "p", W + "tbl"} for child in element):
            builder.warning("docx_comment_body_content_unavailable", "Comment blocks outside paragraphs/tables were not extracted", name)
        text_ancestors = {W + tag for tag in ("comment", "p", "tbl", "tr", "tc", "r", "hyperlink", "t", "tab", "br", "cr")}
        stack = [(element, False)]
        while stack:
            node, unsupported = stack.pop()
            unsupported = unsupported or node.tag not in text_ancestors
            if (unsupported and node.tag == W + "t") or node.tag in {W + "instrText", W + "delText", W + "sym"}:
                builder.warning("docx_comment_body_content_unavailable", "Unsupported inline wrappers or text forms were not extracted", name)
                break
            stack.extend((child, unsupported) for child in node)
        record = {
            "comment_id": element.get(W + "id"), "author": element.get(W + "author"),
            "initials": element.get(W + "initials"), "date": date(element.get(W + "date")),
            "para_id": paragraph, "durable_id": None, "date_utc": None,
            "parent_comment_id": None, "thread_basis": "unavailable",
            "resolved": None, "done_raw": None, "status_basis": "unavailable", "resolved_at": None,
            "intelligent_placeholder": None, "intelligent_placeholder_raw": None,
            "anchors": [], "metadata_parts": {role: part for role, (part, _) in selected.items()},
        }
        records.append(record)
        by_id[identifier] = record
        if paragraph is not None:
            by_paragraph[hex_id(paragraph)] = record

    extended_seen, parents = set(), {}
    for element in entries("extended", {"paraId", "paraIdParent", "done"}):
        key = hex_id(element.get(W15 + "paraId"))
        if key in extended_seen or key not in by_paragraph:
            fail("Duplicate or dangling extended-comment paragraph ID")
        extended_seen.add(key)
        record = by_paragraph[key]
        parent = element.get(W15 + "paraIdParent")
        if parent is not None:
            parent_key = hex_id(parent)
            if parent_key not in by_paragraph or parent_key == key:
                fail("Dangling or self-referencing comment parent")
            record["parent_comment_id"] = by_paragraph[parent_key]["comment_id"]
            parents[record["comment_id"]] = record["parent_comment_id"]
        done = element.get(W15 + "done")
        record.update(resolved=flag(done), done_raw=done, thread_basis="commentEx",
                      status_basis="commentEx/done" if done is not None else "commentEx/default_done_false")
    # Each node is finalized once; long chains cannot cause quadratic work.
    finished = set()
    for identifier in parents:
        path, current = set(), identifier
        while current in parents and current not in finished:
            if current in path:
                fail("Cyclic comment reply relationships")
            path.add(current)
            current = parents[current]
        finished.update(path)

    durable_map, ids_seen = {}, set()
    for element in entries("ids", {"paraId", "durableId"}):
        key = hex_id(element.get(CID + "paraId"))
        durable = hex_id(element.get(CID + "durableId"), durable=True)
        if key in ids_seen or key not in by_paragraph or durable in durable_map:
            fail("Duplicate, dangling or ambiguous comment durable-ID join")
        ids_seen.add(key)
        record = by_paragraph[key]
        record["durable_id"] = element.get(CID + "durableId")
        durable_map[durable] = record
    modern_seen = set()
    for element in entries("extensible", {"durableId", "dateUtc", "intelligentPlaceholder"}):
        key = hex_id(element.get(CEX + "durableId"), durable=True)
        if key in modern_seen or key not in durable_map:
            fail("Duplicate or dangling extensible-comment durable ID")
        modern_seen.add(key)
        record = durable_map[key]
        placeholder = element.get(CEX + "intelligentPlaceholder")
        if placeholder is not None and record["parent_comment_id"] is not None:
            fail("Reply comments cannot have an intelligentPlaceholder attribute")
        record.update(date_utc=date(element.get(CEX + "dateUtc"), utc=True),
                      intelligent_placeholder=flag(placeholder), intelligent_placeholder_raw=placeholder)

    node_index, paragraph_index = 0, 0
    stack = [(parts["word/document.xml"], None)]
    while stack:
        marker, paragraph_locator = stack.pop()
        node_index += 1
        if marker.tag == W + "p":
            paragraph_index += 1
            paragraph_locator = f"DOCX/part=word/document.xml/paragraph={paragraph_index}"
        stack.extend((child, paragraph_locator) for child in reversed(marker))
        if marker.tag not in marker_tags:
            continue
        identifier = comment_id(marker.get(W + "id"))
        if identifier not in by_id:
            builder.warning("docx_comment_anchor_unavailable", "Comment anchor references an absent comment", "DOCX/part=word/document.xml")
            continue
        by_id[identifier]["anchors"].append({"kind": marker_tags[marker.tag], "comment_id": marker.get(W + "id"),
                                            "locator": paragraph_locator or f"DOCX/part=word/document.xml/node={node_index}"})
    for record in records:
        kinds = [a["kind"] for a in record["anchors"]]
        counts = {kind: sum(a["kind"] == kind for a in record["anchors"]) for kind in marker_tags.values()}
        if ((not record["anchors"] and record["parent_comment_id"] is None)
                or any(count > 1 for count in counts.values())
                or counts["commentRangeStart"] != counts["commentRangeEnd"]
                or (counts["commentRangeStart"] and not counts["commentReference"])
                or (counts["commentRangeStart"] and counts["commentRangeEnd"]
                    and kinds.index("commentRangeStart") > kinds.index("commentRangeEnd"))):
            builder.warning("docx_comment_anchor_unavailable", "Comment target is missing or ambiguous; no target text was inferred",
                            f"DOCX/part={name}/comment={record['comment_id']}")
    return {"parts": selected_names, "records": records, "relationship_id": relationship_id, "comment_part": name}


def emit_comments(plan, document, builder, walk, error):
    """Emit citable metadata and comment blocks through the existing builder."""
    if not plan["records"]:
        return
    part = document.part.rels[plan["relationship_id"]].target_part
    if str(part.partname).lstrip("/") != plan["comment_part"] or not hasattr(part, "comments"):
        raise error("docx_comment_metadata_invalid", "Comments part is incompatible with python-docx")
    # One pass avoids repeated python-docx linear lookups for many comments.
    comments = {comment.comment_id: comment for comment in part.comments}
    for record in plan["records"]:
        locator = f"DOCX/part={plan['comment_part']}/comment={record['comment_id']}"
        builder.add(locator + "/metadata", json.dumps(record, ensure_ascii=False, sort_keys=True))
        if record["intelligent_placeholder"]:
            builder.warning("docx_comment_placeholder_body_unavailable", "Follow-up placeholder body was intentionally ignored", locator)
        else:
            walk(comments[int(record["comment_id"])], locator + "/body")
    builder.warning("docx_comment_resolution_history_unavailable",
                    "Recorded annotation state is not business approval. DOCX provides no resolution time/history here; resolved_at remains null")
    if any(record["status_basis"] == "unavailable" for record in plan["records"]):
        builder.warning("docx_comment_thread_state_unavailable", "Some comments have no extended metadata; their reply/root classification and resolved state remain unknown")
    builder.details["docx_comment_count"] = len(plan["records"])
