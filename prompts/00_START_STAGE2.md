# Start one Stage 2 candidate

Replace these values before sending this prompt:

PROJECT_CONFIG: projects/demo/config/project.json
RUN_DIR: projects/demo/runs/<run-id>
PILOT_QUESTION: [the bounded question recorded in projects/demo/POLICY.md]

Use this local Work Second Brain bundle for the selected run. Keep the existing GLM-5.3-flash model and default reasoning effort. Do not change your global configuration.

Read AGENTS.md, WORKFLOW.md, CONTRACT.md, POLICY.md, the project POLICY.md if present, and RUN_DIR/manifest.json. The operator has already created the inventory and packets. Confirm that inventory is ready and that the run belongs to the selected project. Do not inspect unrelated sources or repositories.

Work serially using the extract, reconcile, investigate, and verify prompts in prompts/. Treat these as phases, not a request to spawn agents. Read only a bounded packet or related group at a time. Start by naming the selected question, permitted source ids, planned output files, and explicit completion criteria. Then perform the work.

Create RUN_DIR/proposals/records.json following src/second_brain/schemas/records.schema.json. For a new run with `segments.snapshot.json`, use records schema_version 0.3 or 0.4: bind every citation to its segment_id and representation_sha256, and cover every frozen segment as well as every manifest file. Use 0.4 only when proposing evidence-linked events, with an `events` array on every record; a packet coverage stub starts at 0.3 and may be upgraded without changing honest dispositions. Use 0.2 only for historical runs without a segment inventory. If the operator built question-scoped packets, start coverage from RUN_DIR/packets/coverage-stub.json: its triaged_out entries were not read and must stay triaged_out unless you read them in full. If prior approved knowledge exists, start from the kb_reanchor proposal in RUN_DIR/work/ and its report rather than re-extracting unchanged quotes. Preserve exact current-run citations, meaningful record ids, unknown authority, conflicting evidence, and coverage of every manifest file. Prior approved knowledge, if available, must be revalidated, not copied as authoritative truth. Complete one bounded investigation with explicit findings, limitations, and next action. Do not fabricate a required record kind or a relation.

Run the provided checker against your candidate and address every entry in its semantic_hints (they are not gates, but each needs a reason in the semantic review if left as is). Use at most two repair attempts after the first checker run. Do not edit tools, schemas, tests, manifests, source snapshots, or instructions. Create RUN_DIR/proposals/semantic-review.md with actual findings and residual limitations. This is an AI review, not approval.

Your only authored files must be under RUN_DIR/proposals/ (candidate and semantic review) and RUN_DIR/work/ (any helper scripts and their outputs, which are copied into the release as audit material). Never write helpers anywhere else in the repository. Never edit review files, knowledge/approved, CURRENT.json, external sources, or live Google documents. Never execute source code or SQL, perform writeback, install packages, call a model API, or invoke kb_publish with --human-approved.

Finish with the exact candidate path, checker commands/results actually observed, important unresolved items, coverage gaps if any, and the human review needed. Do not claim the pilot or publication is complete until the required human action has occurred.
