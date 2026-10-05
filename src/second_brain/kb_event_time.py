"""Structural checks for evidence-linked event dates in records 0.4.

These checks validate representation and citation references, not whether a
source actually supports the event or the date assigned by a candidate author.
"""
import re
from datetime import date, datetime, time, timezone

from .kb_common import KBError


def _parse_value(value: str, precision: str):
    patterns = {
        "year": r"\d{4}",
        "month": r"\d{4}-\d{2}",
        "day": r"\d{4}-\d{2}-\d{2}",
        "minute": r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})",
        "second": r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})",
    }
    if precision not in patterns or not re.fullmatch(patterns[precision], value):
        raise KBError(f"Event date value/precision mismatch: {value!r}, {precision!r}")
    try:
        if precision == "year":
            return date(int(value), 1, 1)
        if precision == "month":
            year, month = map(int, value.split("-"))
            return date(year, month, 1)
        if precision == "day":
            return date.fromisoformat(value)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError("timezone offset required")
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise KBError(f"Invalid event date: {value!r}") from exc


def date_display_sort_key(value: str, precision: str) -> str:
    """Order by earliest stated calendar point; date-only values stay imprecise."""
    parsed = _parse_value(value, precision)
    if isinstance(parsed, datetime):
        return parsed.isoformat()
    return datetime.combine(parsed, time.min, timezone.utc).isoformat()


def event_date_label(value: dict) -> str:
    """Preserve precision, uncertainty, basis, anchors, and cited alternatives."""
    status = value["status"]
    if status == "unknown":
        return "unknown — " + value["note"]
    if status == "conflicting":
        alternatives = "; ".join(
            f"{a['value']} ({a['precision']}; citations {', '.join(str(i + 1) for i in a['evidence_refs'])})"
            for a in value["alternatives"])
        return f"conflicting: {alternatives} — {value['note']}"
    span = value["value"] + ("–" + value["end"] if "end" in value else "")
    label = f"{status}: {span} ({value['precision']}; {value['basis']})"
    if value["basis"] == "relative_to_anchor":
        label += f"; anchor {value['anchor_value']} (citation {value['anchor_ref'] + 1})"
    if "note" in value:
        label += " — " + value["note"]
    return label


def _anchor_precision(value: str) -> str:
    if len(value) == 4:
        return "year"
    if len(value) == 7:
        return "month"
    if len(value) == 10:
        return "day"
    return "second" if re.search(r"T\d{2}:\d{2}:\d{2}", value) else "minute"


def _refs(refs: list[int], available: set[int], where: str):
    if not set(refs).issubset(available):
        raise KBError(f"{where} refers to missing or unrelated record citations")


def check_time(value: dict, refs: set[int], where: str):
    """Check one event/effective date without inferring source meaning."""
    status, basis = value["status"], value["basis"]
    if status in {"known", "approximate"}:
        if basis not in {"explicit_text", "relative_to_anchor"} or not {"value", "precision"}.issubset(value) \
                or "alternatives" in value:
            raise KBError(f"{where}: known/approximate date needs one supported value and basis")
        start = _parse_value(value["value"], value["precision"])
        if "end" in value:
            end = _parse_value(value["end"], value["precision"])
            if end < start:
                raise KBError(f"{where}: date range ends before it starts")
        if status == "approximate" and not value.get("note", "").strip():
            raise KBError(f"{where}: approximate date needs a qualification note")
        if basis == "relative_to_anchor":
            if "anchor_ref" not in value or "anchor_value" not in value or not value.get("note", "").strip():
                raise KBError(f"{where}: relative date needs a supported anchor and derivation note")
            _refs([value["anchor_ref"]], refs, where + " anchor")
            _parse_value(value["anchor_value"], _anchor_precision(value["anchor_value"]))
        elif "anchor_ref" in value or "anchor_value" in value:
            raise KBError(f"{where}: explicit date cannot declare a relative anchor")
    elif status == "unknown":
        if basis != "not_stated" or not value.get("note", "").strip() \
                or any(k in value for k in ("value", "end", "precision", "anchor_ref", "anchor_value", "alternatives")):
            raise KBError(f"{where}: unknown date needs a note and no invented value")
    else:  # conflicting
        if basis != "conflicting_sources" or not value.get("note", "").strip() \
                or len(value.get("alternatives", [])) < 2 \
                or any(k in value for k in ("value", "end", "precision", "anchor_ref", "anchor_value")):
            raise KBError(f"{where}: conflicting date needs cited alternatives and a note")
        normalized = set()
        for alternative in value["alternatives"]:
            _refs(alternative["evidence_refs"], refs, where + " alternative")
            normalized.add(_parse_value(alternative["value"], alternative["precision"]))
        if len(normalized) < 2:
            raise KBError(f"{where}: conflicting alternatives repeat the same date")


def check_record_events(records: list[dict]) -> tuple[int, dict, dict]:
    """Validate event ids and links to the parent record's exact citations."""
    ids = set()
    event_status, effective_status = {}, {}
    for record in records:
        available = set(range(len(record["evidence"])))
        for event in record["events"]:
            eid = event["id"]
            if eid in ids:
                raise KBError(f"Duplicate event id: {eid}")
            ids.add(eid)
            _refs(event["evidence_refs"], available, eid)
            refs = set(event["evidence_refs"])
            check_time(event["event_date"], refs, eid + " event_date")
            status = event["event_date"]["status"]
            event_status[status] = event_status.get(status, 0) + 1
            if "effective_date" in event:
                check_time(event["effective_date"], refs, eid + " effective_date")
                status = event["effective_date"]["status"]
                effective_status[status] = effective_status.get(status, 0) + 1
    return len(ids), dict(sorted(event_status.items())), dict(sorted(effective_status.items()))
