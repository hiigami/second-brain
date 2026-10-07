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
Synthetic tests establish engine behavior only; real usefulness remains pending.

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
