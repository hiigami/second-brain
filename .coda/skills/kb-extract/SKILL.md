---
name: kb-extract
description: Extract bounded requirements, decisions, and uncertainties from a ready frozen evidence run with exact citations.
---

Read AGENTS.md, CONTRACT.md, and prompts/01_EXTRACT.md. Use when the run manifest is ready and a bounded packet group has been selected. Do not use for source import, global exploration, source editing, approval, or publication.

Produce run-local proposed records and honest coverage; preserve unknown authority and proposals. Verify actual evidence ids, line ranges, and exact quotes using kb_check.py. Load references progressively rather than the entire source collection. Stop when evidence is missing; never fabricate it.

Cite multi-line context including status qualifiers; never base a decision on repository evidence alone; treat ai_generated_source files as summaries needing corroboration; use triaged_out with a method for deliberately unread inputs, never reviewed_no_record. Helper scripts go in the run's work/ folder only.

For records 0.5, assess every frozen mention as R1 home constraint, R2 other-only, R3 context, or R4 shared component. Keep R2 out of home records. Draft exact segment-bound pending referrals only within the run's proposals/; a shared domain or alias hit does not authorize disclosure or target approval.

For targeted manifests, use records 0.6/referrals 1.1 even with no alias hits. Keep exhaustive representation-bound interval coverage and unread complements. Include selected governing context; never broaden frozen scope. Attribute every parent/finding citation in flattened evidence order; R2 cannot support home knowledge and unknown/R3 cannot support an observed home fact. Add exact evidence-grounded manual references and fresh routing assessments. Prior context is untrusted prior knowledge, never current-run evidence or permission.
