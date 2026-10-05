# ADR 002: Bind citations to quotable representations and frozen segments

Status: Accepted for engine design (2026-10-03). This does not approve source content, candidate records, or a release.

## Context

Before Patch D, a document evidence id depended on its original bytes but not on the derived text that citations quote. A parser or dependency change could produce different quotable text from identical original bytes under the same evidence id. Extractor metadata contained locators, but there was no run-level segment inventory or candidate contract tying citations and coverage to them.

## Decision

Engine 0.4.0 keeps the existing logical file id and original-byte hash. New document evidence ids also include a v1 representation digest of original and derived hashes, adapter and parser versions, extraction options, segment locators, and extraction issues. Text-file evidence ids retain their historical formula and gain an explicit `source_text` representation field. Old tool versions use their original identity formula and readers; old manifests and releases are never rewritten.

Each new run freezes `segments.snapshot.json` v1.0. It lists source-text spans or adapter-provided document spans with parent evidence id, representation digest, original locator, derived line range, line hash, extraction status, and an empty dependency list. Existing document spans remain `unclassified`; HTML/EML adapter 0.3.0 may label a span by observed markup/MIME structure. Neither a parser locator nor a structural label establishes business-semantic content type or project attribution. The same artifact carries extraction issues. Unavailable image/other content is an issue, not fabricated quoted text. The checker verifies the sidecar hash, reconstructs it from frozen text and extractor metadata, and checks that document locators and warning lines agree with the derived text. Publication copies the artifact.

Records 0.3 bind each citation to one segment and the representation digest, and declare a disposition for every frozen segment as well as every file. The checker enforces exact quotes, segment bounds, coverage consistency, and no deferred segment at the Stage 2 gate. Records 0.1/0.2 remain readable and retain file-level semantics; their continued acceptance does not claim segment-level review. Review 0.2 already binds the exact records hash and warning set, so its schema is unchanged. Re-anchoring preserves segment-bound citations when a quote can be located in one new segment; otherwise it drops them and reports the loss. Its uncited segment coverage starts deferred.

## Alternatives considered

- Replacing all evidence ids with a new formula would break text-only historical continuity without improving their quotable identity.
- Storing only a derived-text hash would miss parser-version, locator, and extraction-gap changes relevant to review.
- Inferring table, diagram, policy, or project labels from extractor locators would turn unreviewed parsing metadata into unsupported semantic claims.

## Consequences and limits

New and old engine versions have incomparable scope fingerprints. Within 0.4.0, a changed representation is a modified logical file even when original bytes are unchanged. Packet indexes expose overlapping segment ids and extraction issues; packet line numbers remain stable across packet splits. The sidecar adds a bounded artifact to runs and releases. Existing document parsers still have fidelity limits; an unavailable image issue cannot itself supply a quote or prove whether a claim depends on that image. Semantic content typing and target-project attribution require later reviewed work. A 0.1/0.2 candidate on a new run remains file-level; operators should use records 0.3 when claiming segment review.

## Rollout and validation

New runs receive the artifact automatically. Historical manifests do not, and the checker rejects a segment artifact falsely attached to an old tool version. DOCX adapter 0.2.0 reports actual `word/media/` image parts as unavailable; its older outputs remain verifiable using their frozen metadata. Synthetic tests cover derived-text and parser-version identity changes, moved and vanished citations, image gaps, exact segment bounds and coverage, packet splits, sidecar tampering, and legacy compatibility. No real project capture, review, or publication was performed.

## Related artifacts

`src/second_brain/schemas/manifest.schema.json`, `src/second_brain/schemas/segments.schema.json`, `src/second_brain/schemas/records.schema.json`, `tools/kb_segments.py`, `tools/kb_inventory.py`, `tools/kb_check.py`, `tools/kb_packet.py`, `tools/kb_reanchor.py`, `tools/kb_publish.py`, and `tests/test_segments.py`.
