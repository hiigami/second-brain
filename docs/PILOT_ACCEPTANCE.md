# Real Stage 2 pilot acceptance

## Targeted ingestion and context cohort (pending real authorization)

Use the same human-labeled claims and tasks for baseline and revised workflows,
with fixed GLM behavior. Include mixed-project sources, aliases and implicit
references, shared components, missing qualifiers, proposals, contradictions,
changed selected dependencies and retained prior claims. Agree thresholds before
results; no authorized real cohort or thresholds exist in this checkout.

Attribution precision = correctly admitted home claims / all admitted home claims;
recall = correctly admitted home claims / labeled relevant home claims. Count
uncertain attribution and unavailable evidence separately. Unrelated exposure =
unnecessary packet characters / all exposed packet characters; report retained
storage bytes separately. Context recall = retrieved needed qualified facts /
labeled needed facts. Retention/conflict coverage = retained supported claims or
represented material conflicts / labeled expected claims or conflicts. Count lost
qualifiers and unsupported promotion per assessed claim. Record answer usefulness
with predefined task criteria, review minutes and preparation latency separately
from model/runtime and scoped-export effort. Require zero unauthorized capture or
disclosure, fabricated evidence, silent proposal promotion and unintended removal.
Synthetic checks and human judgments on dummy cases do not establish real
usefulness; that remains pending.

## Learn from synthetic corrections without changing past results

Use entirely invented inputs when real-work material cannot be retained. Preserve
each complete submission and its bound reference, checks and human judgments.
Return corrections to general instructions and worked examples, then assess a
fresh first response on different dummy evidence before claiming that the prompt
changes improve first-response quality. A corrected answer on familiar evidence
shows repairability; it does not establish general reliability or real usefulness.

For a synthetic correction review, an operator can honor an explicit request to
review only changed or affected cases:

1. Compare all three submitted files. Map changed claims and their dependencies
   to cases, including nested explanations and whole-output checks. An unchanged
   record may still depend on a changed premise. Recheck affected answers even if
   their supporting record IDs did not change.
2. Retain a prior human decision only when its criterion, evidence and relevant
   meaning are unchanged. Preserve the original review identity, input hashes,
   decision and reason. Label it retained, not newly reviewed. If uncertain about
   impact, request a fresh judgment.
3. Present one affected case at a time: criterion, changed wording, exact source
   context, proposed outcome and reason. Supporting IDs identify records that
   contribute to the answer; routing cases may need none. An assistant suggestion
   is not a human judgment. Record partial, fail and unreviewed separately.
4. Obtain final acknowledgment covering both new and retained judgments, and a
   new active-review time estimate. Report the two case counts separately; a
   five-case review is not directly comparable with a sixteen-case review time.

This synthetic procedure does not waive publication review or allow reuse of an
old approval on changed candidate bytes. Keep whole-output support review in
scope, including substantive claims in the semantic note. Record editorial
history defects separately when they do not change evidence-derived claims;
never exempt a claim merely because it is in a review note.

Correct an incomplete answer-key excerpt in a new reference version. Include
date lines and qualifiers needed to understand the expected answer, while keeping
pass criteria explicit. Document the exact old/new range and quotation, verify
the new quote against the same frozen source, and create fresh bindings for any
future evaluation. Do not rewrite a completed review's reference hash, relabel
past outcomes or feed the private answer key to GLM. The
[worked examples](../prompts/05_WORKED_EXAMPLES.md) illustrate the date-context gap.

### Transfer the instruction revision being evaluated

Before a fresh test, record the model-input bundle's file list and hash, together
with hashes of the included prompts and referenced examples. Include the intended
working-tree versions even when they are uncommitted; commit status alone does not
show which instructions the model received. Keep the private answer key, human
review and scores outside the model-input bundle. Confirm whether the model used
the extracted bundle or a separate checkout before attributing a failure to stale
instructions.

After improving prompts, prepare a new bundle for the next fresh test and verify
its instruction bytes against the intended revision. Preserve previous bundles,
submissions and completed evaluations. A current repository edit does not update
an already transferred archive, and an old archive must not be rewritten to imply
that the model received newer guidance.

### Fresh-02 synthetic lesson checkpoint

The 2026-10-18 LumenKit dummy-file test used the extracted `fresh-02` input bundle,
which contained the then-current improved prompts and examples. Its first
response had 12 Pass, 2 Partial and 2 Fail decisions, plus a structural attribution
failure. Correction 01 passed the structural check and reached 16 Pass decisions:
11 changed/affected cases were reviewed and five unchanged decisions retained with
explicit human acknowledgment. The original results remain historical.

The recurring meeting-date mistake therefore reflects incomplete application of
supplied guidance, not evidence that the updated prompts were absent. The next
instruction revision adds concrete citation-occurrence maps, a date-subject
counterexample, foreign-proposal content preservation, and final-file checks for
review-note counts and source qualifications. These are hypotheses for improving
future first responses; the corrected result does not validate the new prompts.

The full first-response review took an estimated 10 active guided minutes; the
focused correction review took eight. Their different scope does not establish a
speed improvement. GLM-reported helper execution remains unverified without the
execution records; the operator's successful official check verifies the returned
structure within its scope, not the model's earlier actions. A new first response
on different dummy evidence is needed to assess transfer of these lessons.

### Fresh-03 synthetic lesson checkpoint

The CedarPress `fresh-03` first response, reviewed on 2026-10-18, received 13 Pass,
2 Partial and 1 Fail decisions. The official structural check failed on a stale
referral binding. Inspection also confirmed a manual reference without its
matching assessment: the submitted `mentions_sha256` was the manifest hash, and
describing the manual reference as R4/unresolved did not create an assessment row.

Correction 01, finalized on 2026-10-21, passed the official check and reached
16 Pass decisions. Seven changed or affected cases were reviewed individually;
nine prior Pass decisions were retained with explicit final human acknowledgment.
The full first-response review took an estimated 13 active guided minutes and the
focused correction review about five. The different review scopes do not establish
a speed improvement. GLM's undelivered helper logs remain unverified; the later
operator checks establish the delivered files' structure within their scope.

This instruction revision turns the observed gaps into explicit checks and
[worked examples](../prompts/05_WORKED_EXAMPLES.md):

- Use the correct raw-byte or canonical-JSON input for each referral digest, and
  require exactly one assessment for every scanned and computed manual ID.
- State what a numeric input counts and explain both sides of a strict boundary;
  distinguish a parent citation's constant value from a finding's comparison.
- Supply structured support for factual premises inside questions, including
  descriptions of untrusted pasted instructions.
- Reconcile file, segment and interval coverage notes with actual citing records,
  and check the revised records with their matching referrals file.

Existing guidance about source-specific qualifications and accurate review notes
still applies: implementation not established does not mean implementation absent,
and a blanket assurance must match the final arrays. The preserved audit is under
`projects/synthetic-glm-benchmark-20261018-fresh03/project/runs/fresh-03/work/pilot/reviews/`,
with separate `first-response-01/` and `after-correction-01/` finalization receipts.
These document repairability on the same evidence. They do not validate this new
instruction revision. Evaluate a fresh first response on different invented
evidence with the fixed GLM configuration and a newly bound instruction bundle;
keep the private reference and completed reviews out of the model input.

## Pilot selection

Choose one project with a manageable source set and one concrete question, for example: “What is the current requirement, what evidence records the decision, and does this small code/schema slice reveal a discrepancy?” Prefer material with a known historical ambiguity or an existing Claude analysis so that utility can be assessed.

The pilot must be small enough for human review of every included source. The inventory budgets are upper safety limits, not a target. Do not onboard every repository before the first small pilot earns expansion.

## Tooling gate

The inventory is ready, every snapshot passes integrity checks, every cited quote/range exists, every relationship resolves, coverage is complete, one investigation has finite scope, and publication requires the exact human approval. Run the bundled regression suite on the user's host. Resolve any local path/permission problems before real data is captured.

## Semantic and usefulness gate

Review each substantive claim in context. Reject fabricated evidence, unsupported approvals/owners, hidden contradictions, or conclusions that extend beyond the inspected code/schema. Important omissions must be recorded; a tidy map is not success if it conceals an unresolved requirement. Judge whether the bundle makes it easier to retrieve a past decision and its rationale than the user's current process.

Use `templates/PILOT_SCORECARD.md` to record counts and findings. Recommended acceptance for the first pilot: no fabricated citations, no silently promoted proposals, no unresolved critical support/authority errors, and all materially relevant known disagreements represented. These are proposed pilot criteria, not statistically established quality guarantees.

## Compare with the prior Claude analysis

Do not rerun Claude solely to satisfy the demo. When an existing analysis is available and authorized, compare it against the same evidence snapshot and question. Record differences in source scope, dates, and access; mismatched scopes are not a fair head-to-head comparison.

Use a human-reviewed set of important claims/decisions/uncertainties as the reference. Compare unsupported claims, important omissions, correctly surfaced disagreements, exact citation usability, human correction effort, and answer usefulness. Count manual effort separately from local script runtime. Do not infer a performance improvement from a single polished example or from structural checks alone.

Only escalate a material, unresolved judgment to the limited Claude budget when the expected value justifies it and the work material is authorized for that tool. A second model's answer still requires source grounding.

## Requirements v2 capability cohorts

The [delivery plan](REQUIREMENTS_V2_DELIVERY_PLAN.md) adds formats, mixed-content extraction, chronology, review usability, and cross-project routing in bounded increments. These are proposed capabilities. Select and record the cohort being assessed; a pilot of existing text evidence does not establish image extraction or cross-project readiness. Preserve the original small-question and full-review requirements above.

Before evaluating a cohort, identify a human-reviewed reference set: required facts/elements, known ambiguity, relevant exclusions, source locations, and expected outcomes. Record the denominator for extraction and omission measures and agree acceptance thresholds before seeing results. Keep synthetic regression cases separate from real-project usefulness evidence.

| Capability | Evidence required for acceptance |
| --- | --- |
| Categories and formats | Every category/format claimed by the cohort has positive and negative examples, predefined minimum extraction levels, material reference elements, and accuracy/fidelity criteria. Profiles disclose limits but capture-only support cannot satisfy required extraction. Unsupported material cannot silently count as processed. |
| Dense mixed documents | The reference HTML example covers ER diagrams, entity definitions/relationships, integration SQL, model changes, state diagrams, and relevant values. Compare extracted elements and context against the original; record missing or invented elements. |
| Chronology | The same supported events retain equivalent chronology under shuffled ingestion, including multiple events per document, timezones, unknown dates, and conflicting dates. Test across source categories. |
| Review usability | A reviewer locates each seeded material issue, sees why it matters, opens the source context, and identifies the required action from the report. Measure navigation, correction, and approval effort separately. |
| Cross-project routing | An authorized two-project example preserves home relevance, handles ambiguity and duplicate referrals, and completes target accept/decline/defer. No target claim becomes approved automatically. |
| Global lookup | Results resolve to exact approved project/record/release identities within permitted access; candidates, stale selections, and historical releases are distinguishable. |

Zero fabricated citations, silently promoted proposals, unauthorized disclosures, or unresolved critical support/fidelity errors remain required. Quantitative extraction and review-effort targets require agreement for the selected cohort; do not substitute an invented universal accuracy percentage. Missing measurements stay unmeasured. An unavailable capability remains pending rather than being waived by a narrower successful pilot.

## Go / revise / stop for the selected cohort

Go: the local pipeline passes, semantic issues are resolved or accurately represented, the owner finds the bundle useful, and the review effort is acceptable.

Revise: adjust a narrow prompt, source scope, or record convention; rerun on a fresh snapshot and preserve the prior result. Do not weaken deterministic checks to improve a score.

Stop or block: unresolved information-handling violations, missing critical source fidelity, fabricated authority, or a pilot scope too broad to review. Record the exact blocker; do not silently call Stage 2 complete.
