# Work Second Brain — Stage 2 engine

**Engine version:** 0.4.0 · **Project configuration:** frozen `project.json` v0.1 · **Records:** 0.5 routing-aware (0.1–0.4 readable) · **Review:** 0.4 for routed runs, 0.3 otherwise · **Runtime:** Python 3.14 through `uv`

Start with [START_HERE.md](START_HERE.md). [VALIDATION_REPORT.md](VALIDATION_REPORT.md) records the last actual test run and its limits.

This is a local Python implementation of the first connected project-knowledge workflow: scope external evidence → freeze it → prepare bounded GLM input → extract and reconcile proposed records → verify → human review → immutable release with generated views (record pages, project map, open questions, records by requirement code, changes since the previous release).

It is not a new multi-agent framework, a graph database, a Google importer, or a replacement for Google Workspace. It does not change your fixed GLM-5.3-flash model or reasoning effort. The GLM steps are performed through your existing approved coding assistant; the scripts make no model or network calls.

## Navigation

| Need | Start here |
| --- | --- |
| Use the engine | [START_HERE.md](START_HERE.md) |
| Engineering review and improvement plan | [docs/ANALYSIS_AND_IMPROVEMENT_PLAN.md](docs/ANALYSIS_AND_IMPROVEMENT_PLAN.md) |
| What was recovered versus newly designed | [docs/DECISIONS_AND_GAPS.md](docs/DECISIONS_AND_GAPS.md) |
| Agent behavior and boundaries | [AGENTS.md](AGENTS.md) |
| Operational sequence | [WORKFLOW.md](WORKFLOW.md) |
| Record, evidence, and review contracts | [CONTRACT.md](CONTRACT.md) |
| Configuration and glob rules | [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) |
| Stage 1 export fidelity | [docs/SOURCE_FIDELITY.md](docs/SOURCE_FIDELITY.md) |
| Real-pilot acceptance and Claude comparison | [docs/PILOT_ACCEPTANCE.md](docs/PILOT_ACCEPTANCE.md) |
| Recovery from errors | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| Paste into the work coding assistant | [prompts/00_START_STAGE2.md](prompts/00_START_STAGE2.md) |
| Reference command menu | [commands.sh](commands.sh) |

This checkout has no configured project workspace. An operator creates `projects/<id>/config/project.json` with `tools/kb_init.py` and verifies its approved source paths before capture. Project runs and knowledge are git-ignored for confidentiality, so back them up through a company-approved location. Synthetic fixtures used by the tests live in `tests/fixtures/`.

The packaged command menu is `uv run --locked second-brain --help`, also available through `uv run --locked python -P -m second_brain`. For example, `second-brain check` accepts the same arguments as `tools/kb_check.py`; the existing scripts remain compatibility entry points. Runtime modules and current/legacy schemas live together under `src/second_brain/` and are included in the wheel. Installed `init` requires `--workspace`; installed `sync-skills` requires `--engine` pointing to the checkout; installed `reset-project` requires `--projects-root` and retains its confirmation gates. See [the CLI reference](docs/CONFIG_REFERENCE.md#packaged-commands).

With `--documents`, HTML and EML now produce inert, located evidence: markup/MIME structure is retained, while scripts, remote resources, visuals, and attachment content remain explicit fidelity gaps. Without that flag, HTML keeps its raw-text path. See [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) for exact limits.

Patch G adds structural `.svg`/`.png` capture and locators for embedded Office/PDF visuals. The original bytes are frozen, but the adapter does not read PNG pixels or verify rendered diagram meaning; material visuals need [human comparison](docs/VISUAL_FIDELITY_REVIEW.md). Visual-fidelity acceptance remains open.

Adapter 0.6.0 also validates PNG compressed scanlines before accepting a capture. The [synthetic visual-access probe](docs/VISUAL_CAPABILITY_PROBE.md) is ready for the approved work assistant; its result and representative fidelity review are still pending.

The [visual reference catalog](docs/VISUAL_REFERENCE_CASES.md) pins synthetic originals, including dense HTML with ER and state diagrams. The [review template](templates/VISUAL_CAPABILITY_REVIEW.md) records actual access and human comparisons; no GLM visual capability or human acceptance is claimed from parser tests.

While GLM is unavailable, `second-brain visual-review prepare/verify/assess/export` can produce local raster previews, retain explicit gaps, and bind a human comparison/transcription to original hashes. Use the optional uv `visual` extra and the [local review workflow](docs/LOCAL_VISUAL_REVIEW.md). This separate operator workflow leaves evidence capture and approval gates unchanged; GLM visual capability acceptance remains pending.

Adapter 0.7.0 captures DOCX comment text, recorded authors/dates, reply links and current resolved flags with `--documents`. Missing status and resolution time remain unknown; annotations do not establish business approval. LibreOffice is unnecessary. See [the supported fields and fidelity limits](docs/CONFIG_REFERENCE.md).

CSV remains raw text unless `--documents --csv-representation structured` is selected; `--csv-header first-row` is an explicit declaration. HTML tables now expose citable rows with source-stated column context. These row structures preserve text for review without deciding model relationships or status.

Records 0.4 can attach several evidence-linked events to one record, with event and effective dates kept separate from document/capture time. Unknown and conflicting dates remain explicit. Approved records 0.4 releases generate `timeline.md`; packet builds generate `document-navigation.md` from frozen document dates. Neither view assigns authority or active business state. See [ADR 003](docs/architecture/adr/003-evidence-linked-event-dates.md).

`kb_publish.py --prepare` now generates a pre-approval `review-report.md` with record changes, frozen quote context, unresolved issues, triaged inputs, and individual warning occurrences. Review 0.3 binds its exact bytes; the report never approves a claim or checks the human review boxes.

Patch K adds a separate, operator-maintained project registry and `kb_mentions.py` for explicit same-domain alias candidates in frozen evidence. Patch L adds reviewed R1–R4 assessments and pending segment referrals: records 0.5 and review 0.4 bind the proposal and frozen scan; an explicit source-path disclosure grant plus human review is required before publication generates an origin outbox. Patch M adds `kb_referrals.py` for repeatable target discovery, human accept/decline/defer, scoped capture proposals, lifecycle history, and linkage to independently approved target records. Acceptance requires separate capture authorization; the target still captures, checks, reviews, and publishes its own evidence. No real projects were registered in this checkout. See [configuration and CLI reference](docs/CONFIG_REFERENCE.md) and [ADR 004](docs/architecture/adr/004-reviewed-target-intake.md).

Patch N adds `kb_index.py build/check/query` for explicitly authorized approved-release lookup. A separate access file names the projects, information domain, and reviewed external output destination. The rebuildable index separates current/history, qualifies record ids by project/release, preserves statuses and dates, and links exact frozen evidence. Queries check fresh access and source bindings; pending candidates/referrals are excluded. See [CLI reference](docs/CONFIG_REFERENCE.md) and [ADR 005](docs/architecture/adr/005-derived-approved-release-index.md). No real index or index authorization was created here.

**Important:** a passed checker proves structural consistency and snapshot integrity, not that a model correctly interpreted the source or that the business owner approved a requirement. Human review remains necessary. Read [POLICY.md](POLICY.md) before using company material.
