# ADR 007: Capture DOCX annotations with explicit unknowns

Status: accepted for the authorized development increment (2026-10-06), following
the user's requested architect review before implementation. Representative
Word-export fidelity review and business approval remain separate human actions.

## Context

The DOCX adapter previously omitted comment parts with an ancillary-content
warning. The user needs comment text, recorded dates, replies and resolved state.
python-docx 1.2 exposes classic comments and their block content, but does not
provide public thread/resolution APIs. Modern annotations use additional OOXML
parts. These annotation fields do not establish a business decision or its date.

## Decision

Keep safe ZIP/XML preflight and use a dedicated `kb_docx_comments` helper to
validate internal relationship-selected parts and join metadata before traversal.
Use python-docx for existing paragraph/table/hyperlink text traversal. There is
one writer and no new dependency, provider, network call or project-config key.

Emit a JSON metadata segment and body segments for each original comment in
source order. Locators name the actual part and raw comment ID. Existing
`unclassified` segments and exact-line citations suffice; evidence/record/project
schemas and the engine version remain unchanged. Raw author/initials/date values
are recorded source strings, not verified people or business event dates.

Join `commentEx` on the associated comment's **last** paragraph `w14:paraId`.
`paraIdParent` supplies a reply edge. Matching `done` uses all ST_OnOff forms;
omission in a matching entry defaults to false, while absent metadata yields null.
Preserve the raw flag and its basis; never propagate parent state to replies.
Validate one-to-one paragraph/durable-ID joins for modern fields. Retain raw
`dateUtc` separately, with UTC semantics supplied by its definition; an omitted
suffix is preserved. Classic timezone-free dates gain no timezone. The supported
lexical profile is a four-digit-year ISO date-time with a valid calendar/time and
optional offset. Every `resolved_at` is null: no supported attribute establishes
resolution time or history.

An intelligent follow-up placeholder retains metadata while its body is ignored
and disclosed as unavailable. Its attribute is prohibited on linked replies.
Unknown extensions, unsupported text-bearing wrappers and unlinked parts get
explicit unavailable issues. Anchor markers retain IDs and deterministic node or
paragraph locations; missing/ambiguous targets are gaps, with no invented target
text. Replies need not have their own main-document anchor.

Apply iterative node/depth preflight before recursive body traversal, bounded
maps and linear cycle detection. Duplicate IDs, ambiguous joins, dangling/cyclic
parents, malformed supported fields and budgets produce specific extraction
failures. Never accept partial output after such failures. External links remain
inert. Existing tracked-change/content-control and visual/layout restrictions
remain in force, including in nonstandard comment-part locations.

## Alternatives considered

- Using `Comment.text` alone loses tables and does not expose modern thread state.
- Treating absent metadata as open/root invents information.
- Using comment dates as resolution dates invents history.
- Office conversion adds an unnecessary dependency and still needs fidelity review.
- Expanding record schemas would mix annotation capture with business interpretation.

## Consequences and rollout

The evidence representation changes, so the adapter becomes 0.7.0. The checker
continues accepting frozen 0.6.2 capture policies and checks their bound bytes
without regeneration. Cross-version deltas are incomparable. Captured comments
become available for exact citations, but author identity, annotation intent,
business approval, reactions and complete revision history remain unproven.
Existing runs and approved knowledge are not rewritten.

## Validation

Use synthetic classic/modern comments, missing/empty fields, multiline content,
tables, hyperlinks, boolean forms, last-paragraph reply joins, custom part paths,
placeholder suppression, invalid metadata, unknown wrappers/extensions, inert
links and budget exhaustion. Exercise comment-only inventory, checker, packets,
exact segment citations, historical captures and packaged workers outside the
checkout. Synthetic tests do not establish real Word-export interoperability;
compare an authorized representative export with its original before claiming
fidelity. Actual executed results are in [VALIDATION_REPORT.md](../../../VALIDATION_REPORT.md).

## Sources and related artifacts

- [python-docx comments](https://python-docx.readthedocs.io/en/stable/api/comments.html)
- [Microsoft CT_CommentEx](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-docx/9660dacc-2ceb-4352-87d2-42ba1184f522)
- [Microsoft CT_CommentId](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-docx/9c360cd7-653f-4d82-82be-7bda2488c0c1)
- [Microsoft CT_CommentExtensible](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-docx/a7b57225-42e5-43e7-8d98-d90eabf3ca25)
- [Open XML SDK part definitions](https://github.com/dotnet/Open-XML-SDK/tree/main/data/parts)
- [CONTRACT.md](../../../CONTRACT.md), [configuration reference](../../CONFIG_REFERENCE.md)
