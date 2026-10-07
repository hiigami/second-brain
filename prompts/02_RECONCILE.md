# Reconcile without erasing disagreements

Inputs: candidate records, manifest/packets, applicable project authority policy, and optionally the prior approved record snapshot.

Targeted runs distinguish analysis-only investigation from complete project refresh.
An analysis cannot publish a replacement snapshot. Review the reconciliation
checklist/report for retained, revised, removed, unsupported and unresolved claims.
Revalidate retained meaning with current-run evidence; propose removals explicitly
for human judgment. Scope narrowing is not deletion or retirement.

The operator may use `reanchor --citation-only` for routed records 0.5/0.6. These
are exact-quote suggestions, with routing/aliases/assertions cleared and attribution
pending. Reassess every alias/manual reference and disclosure; do not reuse an old
routing approval. Records 0.6 qualified assertions remain owned by this project,
carry exact parent evidence indexes and semantic status, and never modify target
knowledge. Preserve unavailable/historical references, opposing assertions and
supersession cycles. Dates and release order cannot determine applicability.

Deduplicate equivalent claims without merging distinct requirements. Retain stable record ids for unchanged meanings. Reanchor retained knowledge to evidence available in the current run: the operator runs tools/kb_reanchor.py, which writes RUN_DIR/work/reanchored-records.json and reanchor-report.json. Read every moved, ambiguous, or changed-file citation in context; re-extract records the report lists as dropped instead of silently omitting them. A newer source or code implementation does not automatically supersede a requirement.

For records 0.4, review every retained event id and its `event_date`/`effective_date` after re-anchoring. The report lists dropped event ids when date support disappears; re-extract or keep the event absent with an explicit unresolved question. A later capture does not make an event later. Do not turn overlapping date ranges or conflicting alternatives into a total chronology, and do not treat a later effective date as proof of approval or supersession.

Records 0.5 routing cannot be carried forward by the re-anchor tool. Re-run the mention scan for the current frozen run, then reassess every hit, home `cross_project` link, pending referral, exact quote, and operator-maintained disclosure grant. Preserve R1/R2/R3/R4 distinctions and pending status; do not move an R2 target-only statement into home records or decide on a target owner's behalf. Produce a complete current-run `proposals/referrals.json` alongside the complete records snapshot. An alias match is a lead, not proof of relevance or permission to disclose.

For each material conflict, preserve both evidence sides, state what is unresolved, and name the missing authority/decision evidence. Never invent the missing owner. Add only defensible, directional relationships. Do not create edges simply to connect the entire map.

Distinguish data-source deletion, changed capture scope, inaccessible source, and changed content. Delta information does not automatically invalidate or reapprove a claim. A complete candidate snapshot omits old records only deliberately; human review will expose their removed ids.

Produce a coherent complete proposals/records.json with all current-run coverage entries. Leave unresolved issues explicit. The result is still a proposal, not approved knowledge.
