# Verify a candidate without self-approving it

Read the candidate, current-run evidence in context, project policy, and checker output. Re-examine high-risk claims rather than merely rewriting them. A second pass by the same model is not an independent judge.

Check support/entailment, source-status handling, conflicts, omissions, direction of relations, investigation scope, and whether any coverage entry overstates what was read (reviewed_no_record must mean read in full; triage belongs in triaged_out with its method). Go through every semantic_hints entry in the checker report: single-line citations, pending language in decision quotes, and decisions resting only on AI-generated summaries. A matching quote can still be irrelevant or misleading. Do not infer business approval from the local record's existence.

For records 0.4, compare each event statement, event date, effective date, precision, conflict alternative, and relative anchor with the exact cited lines and surrounding context. Confirm that an email header dates the message rather than every event mentioned in it, and that a file/capture timestamp has not been promoted into business chronology. Unknowns and overlapping intervals must remain unresolved where evidence does not settle them. A checker-passed date is only structurally valid.

Run kb_check.py against the candidate, adding --stage2 for the final pilot gate. Write a bounded list of actual issues with record/evidence ids in proposals/semantic-review.md. Recommend ready-for-human-review or changes-required and explain unresolved judgment gaps.

Do not edit evaluator code, schema, source snapshots, manifests, review files, or approved knowledge. Do not invoke publication. After at most two failed repair attempts, preserve the errors and stop for human judgment rather than weakening the contract.
