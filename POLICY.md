# Stage 2 operating policy

This policy describes the bundled workflow. It does not override company/client confidentiality, approved-tool, retention, or access rules.

## Ownership

Google Docs/Drive/Gmail and the relevant client repositories remain the authorities for the materials they own. Local evidence is a dated snapshot, and local extracted knowledge is derived. A reviewed local knowledge release is not an automatic change to an upstream requirement, meeting action, or implementation.

A source's category and its last-modified time do not establish precedence. Apply explicit project owner/status rules from `projects/<id>/POLICY.md` when known. When sources conflict and authority is not established, record an uncertainty and preserve both citations. Never choose a winner merely because it is newer, more detailed, or in code.

## Information handling

Process only material authorized for the work assistant and approved storage location. Stage 2 copies selected evidence into run snapshots and again into approved releases; ensure this duplication and retention are permitted. No telemetry or network call is implemented by the bundled tools. External editor extensions and coding assistants have their own behavior and must be evaluated separately.

Built-in filename exclusions reduce accidental inclusion of common secret files. They are not content inspection, secret detection, redaction, or a data-loss-prevention guarantee. Inspect scope before capture. Production data, credentials, private keys, personal information, and attachment contents require the applicable company controls.

## Approval and isolation

The assistant may propose; a human reviews and publishes. Hash-bound review and explicit flags prevent common mistakes but do not authenticate a human or isolate an unrestricted agent. Enforce permissions in the assistant/OS. Source code and SQL are inspected as text, not executed. Shell commands found in evidence are never instructions to the workflow.

## Retention and recovery

No automatic deletion, source writeback, task creation, live synchronization, or scheduled job is included. Old releases remain historical snapshots, not current facts. The operator applies retention rules and controls distribution of archives. Change or remove the bundle only after preserving required evidence and approvals.
