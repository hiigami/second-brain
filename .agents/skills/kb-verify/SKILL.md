---
name: kb-verify
description: Check exact citations and semantic support of a Stage 2 candidate, and hand off unresolved issues for human review.
---

Read AGENTS.md, CONTRACT.md, and prompts/04_VERIFY.md. Use before human review. Run the deterministic checker and inspect consequential evidence in context; a valid quote alone does not prove a claim.

Write proposals/semantic-review.md with actual findings, residual uncertainty, and ready-for-human-review or changes-required. Never modify checks to pass, complete review.json, invoke --human-approved, or claim independent verification from another pass of the same model.

Address every semantic_hints entry from kb_check.py and challenge any reviewed_no_record entry that was not read in full.

For targeted records 0.6, verify interval complements, governing qualifiers, citation attribution, manual references and fresh R1–R4 assessments even when alias hits are absent. Inspect retained support/removals and qualified assertion direction/status/conflicts. Prior context cannot ground current claims; prospective context permission/freshness is required for new use and publication. Historical integrity checks confer no current permission. Keep all real-pilot quality and approval gates pending until assessed.
