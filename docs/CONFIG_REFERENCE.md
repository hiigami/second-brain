# Configuration and CLI reference

## Packaged commands

`uv run --locked second-brain --help` lists the operator commands. `uv run --locked python -P -m second_brain` provides the same dispatcher. Each command forwards its arguments to the corresponding existing tool:

| Command | Compatibility script |
| --- | --- |
| `init` | `tools/kb_init.py` |
| `inventory` | `tools/kb_inventory.py` |
| `packet` | `tools/kb_packet.py` |
| `check` | `tools/kb_check.py` |
| `reanchor` | `tools/kb_reanchor.py` |
| `publish` | `tools/kb_publish.py` |
| `mentions` | `tools/kb_mentions.py` |
| `referrals` | `tools/kb_referrals.py` |
| `index` | `tools/kb_index.py` |
| `context` | `tools/kb_context.py` |
| `run` | `tools/kb_run.py` |
| `extract-document` | `tools/kb_extract_document.py` |
| `sync-skills` | `tools/kb_sync_skills.py` |
| `reset-project` | `tools/kb_reset_project.py` |

Use `second-brain <command> --help` for the command's arguments. Dispatch does not prepare, approve, publish, or reset anything implicitly. The package contains runtime modules and all current/legacy schemas under `src/second_brain/`; historical documentation may refer to their former `tools/` and `schemas/` implementation paths. The scripts in `tools/` now forward to those modules. Document workers run through the package with Python safe-path startup (`-P`), which excludes the caller's directory from implicit module search. Use the console command or `python -P -m second_brain` when operating from an untrusted source checkout.

In a checkout, `init` retains its `projects/<id>` default. An installed distribution requires an explicit `init --workspace /approved/projects/<id>`. `sync-skills --engine /path/to/checkout` operates on that checkout's canonical and mirrored skills; the wheel does not carry assistant configuration. Installed `reset-project` requires `--projects-root /approved/projects` and preserves the project-id confirmation and additional approved-release deletion flag. These explicit roots prevent writing into an installation directory by default; they do not grant source access or human approval.

Build through the declared uv backend with `uv build --sdist --wheel --out-dir /approved/build-output`. This needs the existing build dependency to be cached or downloadable. To repeat the packaging tests against a built wheel without installing it, set `SECOND_BRAIN_TEST_WHEEL` to its absolute path and run `uv run --locked python -m unittest tests.test_packaging`. Those tests extract only the package into temporary directories and exercise its CLI, schemas, and document worker outside the checkout.

## Paths and scope

`config/project.json` is project configuration, not an instruction file. Its parent directory's parent is project-root. Relative source paths are resolved from project-root. All output paths are project-relative. A source directory may be outside the engine or elsewhere under it, but never inside or enclosing the selected project workspace. Use approved external source directories; only the test suite uses bundled synthetic fixtures (`tests/fixtures/`).

Each source has a unique id, one category, one directory path, nonempty include patterns, and zero or more excludes. Source roots cannot overlap. Output directories cannot overlap config or each other; approved must lie within knowledge. Source symlinks are not a workaround for these restrictions.

### Expanded source registration

`project.json` v0.1 keeps its five source types. To capture a data, analysis, or policy source, the operator may add `config/source-scope.json` next to it. This is a separate v1.0 contract, with the same source fields and an explicit project id:

```json
{
  "schema_version": "1.0",
  "project_id": "example",
  "sources": [
    {"id": "metrics", "type": "data", "path": "/approved/exports/metrics", "include": ["**/*.csv"], "exclude": []},
    {"id": "reviews", "type": "analysis", "path": "/approved/exports/reviews", "include": ["**/*.md"], "exclude": []},
    {"id": "rules", "type": "policy", "path": "/approved/exports/rules", "include": ["**/*.md"], "exclude": []}
  ]
}
```

The paths above are placeholders. `kb_init.py --expanded-source id:type:/absolute/path` can create the sidecar alongside a new project, which still needs at least one legacy `--source` because frozen `project.json` v0.1 requires one. For an existing project, a human edits the sidecar before a new capture. Added ids and resolved roots must not overlap base sources or each other. Inventory freezes the sidecar as `source-scope.snapshot.json`; the manifest binds its byte hash and scope fingerprint. Checking an old run uses that frozen copy, even if the live sidecar changes. A changed sidecar produces an incomparable delta. No new file extensions are enabled by registration.

Each file keeps one primary source category. These examples guide scope selection; they do not certify a file's authority or classify every passage:

| Category | Positive example | Exclude or qualify | Ambiguous example |
| --- | --- | --- | --- |
| Requirements | Stated acceptance criterion with its conditions. | A proposal is not an approved requirement. | A backlog item mixing a request and implementation notes. |
| Architecture | Component/interface design with state labels. | A diagram is not deployment proof. | A design note that also quotes policy. |
| Meetings | Dated minutes with decisions and pending items. | Attendance alone is not agreement. | An AI summary whose provenance is unclear. |
| SQL | Scoped DDL or query text with purpose. | Do not execute SQL or infer production values. | SQL embedded in a larger design document. |
| Repository | Bounded code or configuration observation. | Copied prose is not product authority. | A README describing both code and intent. |
| Data | Values with units, population, and period where supplied. | A schema is not production data. | A spreadsheet mixing values and instructions. |
| Analysis | Methods, findings, assumptions, and limits. | Repeated summaries are not independent evidence. | A notebook mixing raw data and interpretation. |
| Policy | Rule text with applicability and status. | A draft is not automatically active. | Requirements text that resembles an internal rule. |

Mixed content remains in its captured file and is reviewed in context. Semantic segment classification and fidelity assessment remain human or later-adapter work; source type never ranks authority.

### Cross-project registry and mention candidates

Patch K accepts a separate operator-maintained `projects/registry.json` v1.0 for scanning. Patch L uses registry v1.1 to add explicit source-path disclosure grants. This checkout has no registered real projects. The following **synthetic shape** illustrates two entries without changing either project's frozen `project.json` v0.1:

```json
{
  "schema_version": "1.1",
  "projects": [
    {"id": "alpha", "name": "Alpha", "aliases": ["Project Alpha"], "information_domain": "example", "owns_paths": [{"source_id": "repository", "pattern": "src/alpha/**"}]},
    {"id": "beta", "name": "Beta", "aliases": ["Project Beta"], "information_domain": "example", "owns_paths": []}
  ],
  "disclosures": [
    {"from_project": "alpha", "to_project": "beta", "source_id": "repository", "path_pattern": "src/alpha/shared-api.md"}
  ]
}
```

Names and aliases are matched after Unicode case folding and accent removal at word boundaries. Duplicate normalized names/aliases within one domain, duplicate project ids, invalid ownership/disclosure globs, unknown fields, and oversized registries are rejected. `owns_paths` names source-root anchored routing hints; the scanner does not use it to assign ownership. A human must register only projects and path-scoped disclosure grants approved for this local workspace. A shared `information_domain` is a scan filter, **not** permission to disclose content to another project. Registry v1.0 remains readable for scanning but cannot authorize a routed records 0.5 candidate.

After capture, `uv run python tools/kb_mentions.py --run <run> --registry projects/registry.json` checks sealed evidence and writes `work/mentions.json` and `work/registry.snapshot.json`. The output binds a canonical registry digest and sealed manifest digest and includes each candidate's evidence id, 1-based line, 0-based character span, exact line text, matched alias, target id, and available frozen segment locators. It excludes the home project and other domains. Overlapping aliases from different projects are marked ambiguous. An identical rerun is allowed; a changed result refuses to overwrite the existing work artifact.

For routing, author complete records 0.5 and `proposals/referrals.json` v1.0 from those frozen work artifacts. Each mention needs one R1/R2/R3/R4 assessment and an explicit disposition: referred, linked to a cited home record, dismissed as R3 with a reason, or unresolved. R2 target-only lines cannot support home records. Every pending referral cites exact segment text and its target, contextual summary/rationale, home links, and a capture hint constrained to the exact source path. The hint does **not** authorize the target to capture an entire mixed file; target intake is a separate human decision. The checker requires a matching frozen registry 1.1 disclosure grant for the destination, source id, and path. Human review 0.4 binds the exact proposal, mentions, registry, and report, and adds `cross_project_checked`. Only after that approval can publication generate an origin-release `outbox.md`; it remains pending target review. Records 0.5 re-anchoring stops for fresh classification in the next run. Alias scanning can miss implicit/unregistered references, and structural checks cannot judge semantic class or segment disclosure safety.

Engine 0.4.0 freezes `segments.snapshot.json` with source-text spans, document-extractor locators, representation digests, and extraction issues. HTML/EML adapter 0.3.0 introduced structural content types; adapter 0.4.0 adds table rows with source-stated column context and optional structured CSV. Other document spans stay `unclassified`. Neither label is a business-semantic or fidelity judgment. The packet index lists overlapping segment ids and unavailable extraction issues. Records 0.3 citations use `segment_id` and `representation_sha256`, with a disposition for every segment. Records 0.1/0.2 remain readable at file level. See [ADR 002](architecture/adr/002-quotable-representation-and-segments.md).

Records 0.4 retain that segment contract and add optional per-record event content through a required `events` array. Each event cites exact parent-record evidence by index and separates event date from an optional effective date. `known`, `approximate`, `unknown`, and `conflicting` variants keep precision, timezone offsets where applicable, source basis, anchored relative dates, and cited disagreements visible. File content dates and capture sequence do not automatically populate event dates. Older candidate/release versions remain readable; see [ADR 003](architecture/adr/003-evidence-linked-event-dates.md). Approved records 0.4/0.5 releases generate a business-event `timeline.md`; packet builds generate separate document-date navigation.

### Reviewed target intake (Patch M)

`kb_referrals.py` writes only the target's configured knowledge directory at `referral-intake.json` (contract 1.0), outside its approved subtree. It never changes `project.json`, source scope, policy, frozen runs, or approved knowledge. The three commands below are operator examples with placeholder paths; run them only for authorized project access. `--origin-config` may be repeated. No origin is inferred from a source document or ledger path.

```sh
uv run python tools/kb_referrals.py discover --config projects/target/config/project.json --registry projects/registry.json --origin-config projects/origin/config/project.json
uv run python tools/kb_referrals.py decide --config projects/target/config/project.json --registry projects/registry.json --origin-config projects/origin/config/project.json --review /approved/operator/intake-review.json
uv run python tools/kb_referrals.py link --config projects/target/config/project.json --review /approved/operator/intake-link.json
```

Discovery validates origin publication history, current-release integrity, complete approval gates, frozen routing grants, and matching live registry grants. `origin_scans` reports checked, stale, unavailable, or unauthorized origins even when no referral could be imported; an empty item list alone cannot establish that all origins were available. Exact scans do not duplicate items or decisions. `source_status` distinguishes current, superseded, withdrawn, stale (not scanned), unavailable (missing or invalid origin), and unauthorized. `supersedes` links successive source-path/referral slots for renewed review; it does not infer business precedence. Every changed current origin release requires a new intake review even if its source bytes match. Rollback reuses the earlier item and its decision history.

Supply a **human-authored** `intake-review` 1.0 JSON to `decide`. Copy `item_id` and `origin_review_sha256` from discovery, set the real reviewer and timezone-bearing review time, and explain accept, decline, or defer. This synthetic shape is not an approval:

```json
{
  "schema_version": "1.0",
  "item_id": "INT-000000000000000000000000",
  "origin_review_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "decision": "defer",
  "reviewer": "Human reviewer name",
  "reviewed_at": "2026-10-04T12:00:00-06:00",
  "reason": "Confirm authorized target capture scope before acceptance.",
  "capture_authorization": null
}
```

An accept with `capture_authorization: null` remains `blocked_capture_authorization`. Only an acceptance can carry a capture authorization object: `mode` is `full_file` or `scoped_export`, `path` is an absolute external file path, `sha256` is the actual 64-character byte digest, and `reason` records the human scope assessment. Full-file authorization must cover every included part and match the origin original hash. For mixed files without that permission, supply a reviewed UTF-8 scoped export, preserve the exact qualified quote as complete contiguous lines, and record the export hash and disclosure reason. The tool verifies bytes and quote preservation; only the human can assess additional context, fidelity, and disclosure safety. Missing/changed capture bytes block the decision. The tool never creates the export or captures it.

Accepted work appears as an embedded `capture_task` with exact origin provenance. A non-current source changes its task status to `blocked_source_<status>` while retaining the acceptance and authorization audit. The operator then registers authorized source scope, captures a target run, reconciles, checks, reviews, and publishes through the ordinary workflow. For later linkage, supply a human-authored `intake-link` 1.0 with `schema_version`, `item_id`, `target_run_id`, `target_review_sha256`, `record_ids`, `reviewer`, `reviewed_at`, and `reason`. `record_ids` are local target ids, and the review digest is the target release's actual `review.json` hash. Every linked record must have its own checked citation to the authorized bytes and referred quote. `evidence_comparison` reports scoped-export lineage or whether representation and original locator both match. Identical bytes alone do not prove equal context.

Exact review retries are idempotent and do not replay an older decision over a newer one. Decline/defer retains earlier audit entries; correction/withdrawal retains accepted decisions and target release links. Previously authorized content remains in the historical ledger after disclosure revocation; retention remains operator-controlled. A lock protects ordinary concurrent writers; detected pointer/registry/release/ledger changes abort. The bounds are 10,000 items and 16 MiB. The ledger is an audit convention, not human identity authentication or a cross-project transaction. Real-project authorization, export fidelity, routing quality, and usability remain unverified. See [ADR 004](architecture/adr/004-reviewed-target-intake.md).

### Derived approved-release lookup (Patch N)

`kb_index.py build/check/query` requires an operator-maintained `index-access` 1.0 file, a registry (1.0 or 1.1), and exactly one explicit `--project-config` for every authorized project. A shared domain or a referral grant does not authorize indexing. This increment requires whole approved-release visibility, including quoted context and evidence links; a narrower record/segment permission is insufficient. Before creating a real access file, assess project policies, destination access, storage, and retention. No real authorization or index is bundled.

This synthetic shape illustrates the access contract. Replace all placeholders and record the real authorizing operator/time/reason; it is not an authorization to use actual company material:

```json
{
  "schema_version": "1.0",
  "information_domain": "example-domain",
  "project_ids": ["example-a", "example-b"],
  "output_path": "/approved/shared-lookup/index.json",
  "authorized_by": "Human operator name",
  "authorized_at": "2026-10-04T12:00:00-06:00",
  "reason": "Record the whole-release access, context disclosure, storage and retention assessment."
}
```

The output must be a normalized absolute `.json` path outside this engine, all selected project workspaces, and every configured base/expanded source root. It cannot overwrite the access/registry files or an unrelated file. The access file stays outside `project.json`; the index neither changes governance nor edits sources, policy, configuration, runs, approvals, or current knowledge pointers. Only its own external artifact and an adjacent temporary exclusive lock are written.

These operator commands use placeholder paths and require real authorization before execution:

```sh
uv run python tools/kb_index.py build --access /approved/operator/index-access.json --registry projects/registry.json --project-config projects/example-a/config/project.json --project-config projects/example-b/config/project.json
uv run python tools/kb_index.py check --access /approved/operator/index-access.json --registry projects/registry.json --project-config projects/example-a/config/project.json --project-config projects/example-b/config/project.json
uv run python tools/kb_index.py query --access /approved/operator/index-access.json --registry projects/registry.json --project-config projects/example-a/config/project.json --project-config projects/example-b/config/project.json --text "proposed review" --epistemic-status proposal --limit 20
```

Default builds index each selected project's checked current approved release. Add `--include-history` to `build` to include releases named in publication history; `query --view historical` requires that build. `--view all` searches the saved selected set, while the default is `current`. Other query filters are `--project`, `--kind`, `--epistemic-status`, and `--text`; text terms match title, statement, open questions, and event statements without executing evidence. Limits are 1–1,000 results, default 50; the result reports total matches. Records retain `human_reviewed_snapshot` and their actual epistemic status. An approved snapshot containing a proposal or uncertainty is not approval of the underlying business change.

The artifact has `projects`, `releases`, and qualified `entries`. Project metadata retains information domain and descriptive `ownership_references`, not inferred owners. Every entry preserves the exact reviewed `record`, original record schema, selected current/historical visibility, `record_path` plus `record_index`, and `evidence_links`. A link names its parent/finding citation index, frozen text snapshot and line range, original hash, representation hash, segment/locator where available, and document original/metadata paths where applicable. Older file-level records keep null segment/locator fields and no invented event content. Pending candidates, referrals, and intake tasks are not indexed as claims. A link into frozen context requires the whole-release visibility explicitly assessed in the access file.

The deterministic `generation_id` binds canonical access/registry values, project config/expanded-scope digests, current-pointer/history hashes, selected review/record/manifest/report/work bindings, and exact derived entries. Config order does not change generation bytes. A checked query revalidates the entire authorized selection and reconstructs the expected projection before returning results. Stale policy, an independently published release, removal/rollback, inaccessible evidence, altered publication trace, or edited index content blocks results until inputs are restored or the index rebuilt. This checks separate project boundaries; it is not a cross-project transaction or a proof of business authority, semantic entailment, current active state, or complete global access.

Every selected project needs an available checked approved release; failures do not produce a partial index. Input changes detected during a build abort without replacing prior output. Report-bound reviews 0.3/0.4 are required; older review readers remain intact but unsupported history cannot be silently promoted into the index. Bounds are 1,000 releases, 10,000 entries, and 16 MiB per index. Repeated exact builds preserve bytes. Rebuild an edited derived index from authorized sources; inspect/remove a malformed or unrelated output manually rather than asking the tool to destroy it. Removing the index cannot remove project knowledge. After revocation, previously copied indexes remain subject to operator retention/deletion policy. No real retrieval quality or performance was measured. See [ADR 005](architecture/adr/005-derived-approved-release-index.md).

## Pattern dialect

Patterns are case-sensitive, anchored to the source root, with `/` separators. `*` matches within a path segment; `?` matches one character within a segment; a whole-segment `**` matches zero or more path segments. No negation, character classes, brace expansion, or gitignore precedence is implemented. Excludes always win.

| Pattern | Meaning |
| --- | --- |
| `**/*.md` | Markdown at the source root and any depth. |
| `src/**` | Everything below the top-level src directory. |
| `*.md` | Markdown only at the source root. |
| `**/build/**` | Exclude build directories at any depth. |

Global exclusions, per-source exclusions, and the built-in sensitive-filename denylist are combined. Excluded directory entries are pruned. `excluded_entries` counts discovered excluded/unselected entries, not the unknowable number of files within pruned subtrees.

## Commands

Run `uv run python tools/<tool>.py --help` for argument details.

| Tool | Main responsibility | Writes |
| --- | --- | --- |
| `kb_init.py` | Create a new project config from explicit external paths | New project workspace only |
| `kb_inventory.py` | Capture/hash scoped evidence and compare a baseline; add `--documents` to also capture `.docx`/`.pdf`/`.xlsx`/`.pptx`/`.html`/`.eml`/`.svg`/`.png` via the extractors (see `START_HERE.md`) | New run only |
| `kb_packet.py` | Generate bounded, line-numbered source packets and `document-navigation.md`; `--select`, `--select-glob`, `--grep` build a question-scoped subset plus `coverage-stub.json` | Current run's previously empty packets directory |
| `kb_visual_review.py prepare / verify / assess / export` | Prepare raster review packets and check/export explicit human observations; optional uv `visual` extra, separate from evidence capture; see [local visual review](LOCAL_VISUAL_REVIEW.md) | Fresh development directory outside the checkout or configured `runs/<run>/work/`; verification/assessment are read-only; approved knowledge excluded |
| `kb_mentions.py --run <run> --registry <path>` | Scan checked frozen text for explicit names/aliases of other registered projects in the same information domain; emit candidates only | New or byte-identical `work/mentions.json` and `work/registry.snapshot.json` in the run |
| `kb_referrals.py discover / decide / link` | Discover authorized approved referrals, record human target intake, and link independently published target evidence | Target `knowledge/referral-intake.json` only, with a temporary exclusive lock |
| `kb_index.py build / check / query` | Rebuild, validate, or search explicit authorized approved-release selections with exact record/evidence provenance | Build writes only the external access-file destination and its temporary lock; check/query are read-only |
| `kb_check.py` | Validate inventory, records, citations, and optional live bytes; report the Stage 2 milestone and semantic hints | None, unless a new report path is explicitly supplied |
| `kb_reanchor.py` | Re-anchor a previous release's records into a new run by exact quote | New `work/reanchored-records.json` and `work/reanchor-report.json` in the new run |
| `kb_publish.py --prepare` | Create a non-approved review 0.3 template, or 0.4 for routed records 0.5, and bound `review-report.md` | Current run's new review.pending.json and review-report.md |
| `kb_publish.py --human-approved` | Publish an explicitly reviewed snapshot | New approved release and CURRENT pointer |
| `kb_reset_project.py` | Operator only. Remove everything in `projects/<id>/` except `config/project.json`. Dry run unless `--confirm <project-id>`; approved releases also need `--delete-approved-releases`. | Deletes runs, knowledge, POLICY.md and other config files of that project (git-ignored data is unrecoverable) |
| `kb_sync_skills.py` | Mirror `.agents/skills` into `.claude/skills` and `.coda/skills`; `--check` reports drift | The mirror skill folders |

Default inventory budgets are 2,000,000 bytes per file, 50,000,000 bytes total, and 2,000 files. These are guardrails, not recommended pilot sizes. Raising a limit changes the comparison scope fingerprint. Default packets use a 16,000-Unicode-character budget; this does not measure tokens or model context capacity.

Successful CLI commands return 0. Contract/filesystem failures and blocked inventory return 2. Commands never silently overwrite an existing run, packet set, review template, report file, or release. Packet generation and inventory use temporary directories to avoid presenting partial output as complete.

The review report shows unchanged claims as well as complete current and previous event statements, date qualifications, and numbered supporting citations. Links to the current run's evidence remain relative so they travel with the exact report into the release. Links to prior releases use encoded absolute local file URLs so copying the report does not break them; those links depend on retaining the prior release at its recorded location. Existing approved reports are preserved. Previously prepared reports need fresh preparation and substantive review when the renderer changes; never update an approval hash to bypass that review.

## Source formats

Supported extensions are listed in `tools/kb_common.py::TEXT_EXTENSIONS`. Inputs must also pass strict UTF-8 and NUL checks; extension alone is insufficient. The allowlist includes Markdown, text, SQL, common source/configuration formats, CSV, Mermaid, and structured JSON. These formats are not parsed for domain semantics by inventory; they are preserved as text evidence.

Optionally, `kb_inventory.py --documents` additionally captures `.docx`, `.pdf`, `.xlsx`, `.pptx`, structured `.html`, and `.eml` (legacy `.ppt` only with `--allow-legacy-ppt`). Each is frozen as three artifacts: original bytes, derived UTF-8 evidence text, and an integrity-bound extraction sidecar. HTML uses bounded inert parsing; JavaScript and remote resources are never executed or fetched. EML preserves decoded headers, body variants, and quoted replies; attachments are metadata-only and their content remains unavailable unless separately authorized and captured. Charset conflicts and malformed MIME block capture; malformed HTML structure produces a review warning. The derived text is untrusted evidence at status `extracted_needs_review`, and fidelity warnings must be acknowledged in `review.json`. Without `--documents`, `.html` keeps its raw UTF-8 text path and `.eml` is unsupported. See `START_HERE.md` and `docs/TROUBLESHOOTING.md`. Dependencies are declared in `pyproject.toml`; nothing is installed at runtime.

Adapter 0.5.0 introduced `.svg` and `.png` with `--documents`. SVG parsing retains explicit XML labels, captions, vector attributes and canvas metadata; it does not render or interpret their visual meaning. Adapter 0.6.0 additionally checks PNG signature, chunk envelope/CRCs, palette and IDAT order, compressed scanline/filter structure, dimensions, and unverified `tEXt` annotations. It does not reconstruct pixel values or perform OCR. The whole canvas is the only PNG region locator. Embedded Office/PDF assets receive metadata and locators where available, but not image content; PDF XObject inventory does not traverse nested forms. All visual gaps stay visible in extraction issues. See [visual fidelity review](VISUAL_FIDELITY_REVIEW.md) and [the approved-assistant probe](VISUAL_CAPABILITY_PROBE.md); these formats have structural capture, not completed R3 visual support.

CSV remains raw UTF-8 evidence by default, including with `--documents`. To freeze a derived row representation, use `--documents --csv-representation structured` and set `--csv-delimiter`/`--csv-encoding` to the actual source encoding. Add `--csv-header first-row` only when the first record is explicitly the source's column-label row; `none` is the default, and the tool never guesses headers. Cell values remain strings, including zeros, blanks, multiline fields, and formula-like text. HTML table rows retain cell text, source-stated headers, caption, and preceding heading; spans and width mismatches warn instead of inventing alignment. Neither row format automatically asserts a model relationship or effective date. The choice is frozen in the document policy and a different choice makes baseline deltas incomparable.

Adapter 0.6.1 preserves inline HTML code within its containing assertion and `<br>` boundaries as newlines, including in HTML email bodies. After encountering a merged header or cell, it suppresses header alignment for the rest of that table and emits review warnings; it does not reconstruct the rendered grid. These extraction fixes apply to new captures only. Frozen runs retain their original adapter/representation identities, and a baseline across adapter versions remains incomparable.

Adapter 0.6.2 also suppresses resource attributes, image alt text, and content-id references inside excluded HTML content such as templates and object fallback blocks. The enclosing element retains its own references and unavailable-content warning. Historical adapter 0.6.0 and 0.6.1 captures remain verifiable without rewriting their artifacts.

Adapter 0.7.0 includes DOCX comment paragraphs, tables and hyperlink text, plus exact citable JSON metadata for recorded author/initials, `date`, reply parent, current `resolved` state and modern durable-ID/`date_utc` fields. This uses the declared python-docx and defusedxml dependencies; LibreOffice is unnecessary. Capture uses the existing `--documents` option, with no new configuration keys. Author strings are untrusted source metadata. Reply links identify which captured annotations respond to others; they do not establish agreement or approval. Missing extended metadata remains unknown. Only a valid matching extended-comment record can default an omitted resolved flag to false. Flags remain per comment, including replies.

`resolved_at` remains null: these supported DOCX parts carry no reliable resolution timestamp or audit history. Raw date strings retain their original timezone spelling. Timezone-free `date` has no inferred timezone; `date_utc` is UTC by the modern attribute's definition even without a suffix. Supported dates use a four-digit-year ISO date-time profile. Follow-up placeholder bodies, unsupported inline wrappers/extensions and missing/ambiguous anchors remain visible gaps. Extraction does not reconstruct targeted text, reactions, mention identities, deleted comments, visual layout or complete revision history. Malformed/ambiguous joins and structure/output budget exhaustion block capture. Historical 0.6.2 captures remain verifiable without regeneration, and a baseline across adapter versions is incomparable. Representative Word-export fidelity review is still pending; automated coverage is synthetic. See [ADR 007](architecture/adr/007-docx-comment-evidence.md).

A Google Docs shortcut is not its document content. With or without `--documents`, a reviewed upstream export/conversion is the source of trustworthy document content. Changing a filename to `.txt` is not an acceptable fidelity strategy. Documents with significant tables, comments, suggestions, tabs, images, or attachments may require richer Stage 1 evidence before a Stage 2 answer is trustworthy.

## Targeted run preparation

This is opt-in; existing inventory and packet calls retain legacy behavior.
`project.json` stays 0.1. Read ADRs [008](architecture/adr/008-targeted-run-scope-and-coverage.md)
and [009](architecture/adr/009-project-assertions-and-pinned-context.md) and the
machine-readable [run-request 1.0 schema](../src/second_brain/schemas/run-request.schema.json).
These examples are conditional on operator-authorized inputs; placeholder paths
are not permissions or configured projects.

An operator request names `project_id`, `purpose` (`analysis_only` or
`project_refresh`), `capture_mode`, `authorized_by`, `authorized_at` (timezone
required), `permission_reason`, exact `selection`, `packets`, `registry_path` and
`context`. Each selection names `source_id`, `relative_path`, nullable `sha256`
and nullable `provenance`. Exact membership must be inside configured include/
exclude scope. Preflight reports included paths, missing inputs and the exclusion
rule without opening source content. Every other configured path is excluded
before content reads; it does not enumerate the contents of excluded directories.

`whole_file` explicitly permits all listed bytes, including unrelated passages.
`scoped_export` permits only reviewed UTF-8 `.txt`/`.md` exports and requires their
observed SHA-256 and provenance: `original_reference`, `locator`, `reviewed_by`,
`reviewed_at`, `limitations`. Original references are audit text, never opened by
capture. The operator prepares exports and verifies fidelity; the engine cannot
infer permission from relevance. Observed hash/review metadata changes do not
invalidate ordinary deltas; membership, representation mode, intent and packet
policy/composition changes do.

`packets` always declares `composition` (union/intersection), `globs`, `terms`,
`ranges` and `max_chars` (at least 1,000). Empty selector arrays mean all explicitly
captured members. Ranges name source/path and inclusive 1-based start/end lines.
Union combines the supplied groups; intersection intersects them. Include
headings, table labels and pending/proposed qualifiers as explicit context ranges.
Omitted complements are exposed to semantic review; they are never called read.
Packet budgets use Unicode characters, not model tokens. One oversized line or
an empty resulting selection fails rather than widening/truncating input.

`registry_path` names an operator-maintained registry 1.1 containing the home
project, even with no aliases or disclosures. It grants no implicit disclosure.
`context: null` explicitly opts out of index retrieval and supports first runs.
Local prior citation suggestions remain subject to current-run revalidation.
Requested context instead names `access_path`, `registry_path`,
`project_configs` (exact authorized index set), `permission_path`, `queries`,
`max_records` (1–1,000), `max_bytes` (1,000–16,000,000), `required_keys` and
`expand_relations` (0–2). Missing/filtered required keys or required budget
failures block; optional omissions are counted. Initial retrieval fully verifies
the index and shares a generation across queries; ranking version 1 uses title,
reviewed aliases, statements/questions/events and deterministic qualified-key ties.

A separate [context-permission 1.0](../src/second_brain/schemas/context-permission.schema.json)
must authorize selected source project ids and the exact target run/release paths,
`copy_quotes`, `copy_briefing`, `retain_audit` (all true), operator/time and retention
reason. Keep this permission outside its run/release. Index output permission or
referral grants alone cannot permit these retained destinations. The bundle in
`work/context.json` freezes exact qualified records, provenance/status, queries,
budgets/omissions, permission and selected release/config/project-policy bindings.
The briefing labels it untrusted prior knowledge, never current evidence.

After the operator has prepared these inputs, the conditional commands are:

```bash
uv run --locked --no-sync second-brain run create \
  --project /approved/project/config/project.json \
  --request /approved/operator/run-request.json --run-id selected-001 --dry-run
uv run --locked --no-sync second-brain run create \
  --project /approved/project/config/project.json \
  --request /approved/operator/run-request.json --run-id selected-001
```

The second command captures and prepares only explicitly selected evidence.
Add `--baseline /approved/project/runs/previous-run` for a checked comparable
capture baseline. `inventory --request FILE --dry-run` performs scope-only
preflight; `inventory --request FILE` supports explicit no-context requests.
Requested context uses `run create` so retrieval happens before capture.

Preparation writes hash receipts in `work/preparation.json` for capture, packets,
mentions, citation suggestions, briefing/checklist and inventory/context checking.
It creates no candidate, semantic review, human approval or publication. Read
`work/assistant-briefing.md`, then follow the existing manual workflow. New
profiles require records 0.6/referrals 1.1 irrespective of alias hits. Interval
coverage must partition each existing segment, including unread complements;
review acknowledges triaged intervals through their containing segment ids.
Every citation declares attribution in parent-then-finding order. Manual registered
references supplement alias hits. Unknown attribution cannot be an observed home
claim, and R2 cannot support home knowledge. Assertions cite parent evidence and
qualified targets, retain semantic status/direction, and never update target claims.

`run create ... --resume` accepts only completed verified stages with matching
request, configuration/scope, registry, prior-release, baseline, selected-source
and output hashes. The packet receipt must cover every indexed packet and exactly
match the current packet file set; missing or unexpected outputs block resume.
It never replaces frozen context or recaptures. Interrupted
stages (including committed output without a receipt) require a new run id.
Existing capture/packet exception paths remove their temporary outputs; crash
leftovers and stale `.preparation.lock` require operator inspection. Never delete
receipts or reseal evidence to force resume. A ready resume is read-only and
preserves bytes. A continuing resume rechecks its validated receipt under the
preparation lock before any stage write. If a competing caller completed it first,
the delayed caller fails without changing that result; retry verified resume.
Analysis-only runs cannot prepare publication review or publish
through any entry point. Project refresh requires a complete checked snapshot and
explicit human-reviewed removal ids, with unavailable retained support visible.

`reanchor --citation-only` offers routed matches for records 0.5/0.6 and clears
routing/assertions/aliases; attribution and disclosures need fresh assessment.
Only matches entirely within the new run's selected passages are suggested.
`outside_selected_passages` reports excluded support without copying that citation
into the suggestion; dropped record ids still require revalidation or deliberate
human-reviewed removal. Identical quotes in selected passages remain suggestions
requiring semantic review.
`index assertions` resolves project-owned assertion views against only the
explicitly authorized index selection and displays cycles, opposing assertions,
and unavailable/historical targets. It does not merge claims or infer active state.
Only observed or interpretation assertions establish supersession cycles;
proposal and unresolved assertions remain visible with their original status.
`index query --expand-relations 0|1|2` returns ranking reasons, ties and omission
counts while respecting project/kind/status/current-history filters.

`context --run RUN --project CONFIG` and the default `check` path verify live
selected permissions/dependencies. Selected foreign changes require a new run;
unrelated index generations do not invalidate pinned selections. Prospective
review/publication checks repeat freshness before the target pointer swap.
`check --historical` and `context --run RUN` validate frozen integrity only: these
cannot authorize new use, review or publication. Historical release validation
is independent of later foreign pointers/grants. Retention after revocation stays
an operator duty. Context permission fields are audit declarations, not identity
or OS access controls, and release sets are not a cross-project transaction.

After successful human publication, rebuild any derived index explicitly. An
index refresh failure cannot roll back publication. Real capture permissions,
retention, usefulness thresholds and the labeled pilot remain pending until
operators and reviewers supply and assess them.
