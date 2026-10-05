# Stage 1 → Stage 2 source-fidelity handoff

Stage 2 consumes approved local evidence. It does not fetch Gmail, Google Drive, Docs, comments, attachments, repositories, or production databases. It does not implement or certify any Google export API. No credentials or connectors are needed for the bundled demonstration.

Before relying on a source, establish its origin, retrieval time, revision where available, owner/status where relevant, and known preservation limits. For Google material, explicitly check whether the chosen representation preserves relevant tabs, comments, suggestions, tables, and referenced attachments. A readable export alone does not establish those properties.

## Optional metadata sidecar

`projects/<id>/config/source-provenance.json` maps a source id plus relative file path to origin metadata. Its independent schema is `src/second_brain/schemas/source-provenance.schema.json`; it does not change the frozen project.json shape. Use `templates/source-provenance.json` only as a structural example.

Unknown ids, URLs, or revisions remain null. A capture timestamp must describe the actual capture and include a timezone. The origin's feature flags are preserved, not_preserved, unknown, or not_applicable. Preserve limitations as statements rather than leaving a misleading appearance of completeness. This metadata is operator/importer-supplied; inventory does not verify it against Google or Git.

For a repository, an actual commit id can be recorded in `revision` when verified. A file-level working-tree capture is not proof of a clean checkout, a full repository snapshot, or cross-file atomic consistency. Do not invent a commit id from the date or folder name. When no metadata exists, the tool reports missing provenance or unrecorded repository revision rather than filling fields speculatively.

## Missing fidelity behavior

Missing metadata produces warnings; unsupported/unreadable eligible content blocks capture. A human may approve a narrowly qualified derived knowledge snapshot while preserving provenance uncertainty. They must not approve a claim whose answer materially depends on unavailable comments, suggestions, attachments, revisions, or code.

Do not call a meeting proposal an accepted change unless authority/status evidence supports that conclusion. Do not turn an unresolved comment into the document author's position. Do not confuse source modifications with new business approvals.

This bundle creates no tasks and writes nothing back to Google. Workspace Studio intake and task-promotion integration remain Stage 3 work.
