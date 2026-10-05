# Handoff: native document format support for the existing Stage 2 engine

This is an implementation brief for the coding assistant that can read the user's actual `second-brain` repository. The engine source was not available as raw bytes when this adapter pack was produced. Do not treat this brief as an already-applied patch, and do not invent the current manifest field names.

## Objective

Make `.docx`, `.pdf`, `.csv`, `.xlsx`, `.pptx` and explicitly opted-in legacy `.ppt` usable as evidence in the current inventory → check → packet → review → publication workflow. Use `tools/kb_document_extractors.py` as the extraction component, not as a replacement engine.

Preserve the frozen `project.json` v0.1 structure, user source paths/IDs/types, original source immutability, existing source scopes, the empty-source compatibility fix and text/code-file behavior. Do not add model calls, cloud uploads, unattended OCR or formula execution. The work assistant stays on its existing model/reasoning configuration.

## Read before editing

Read `tools/kb_inventory.py`, `tools/kb_common.py`, `tools/kb_check.py`, `tools/kb_packet.py`, all code that reads snapshot bytes for citations/review/publication, the manifest schema, record schema and existing tests. Search for extension allowlists, `.decode`, `.read_text`, `snapshot_path`, line counting, evidence IDs, snapshot hashes, delta comparison, snapshot-copy logic and export-fidelity checks. These are search targets, not asserted current identifiers.

First run the existing suite and record the baseline. Preserve uncommitted user edits. Do not overwrite entire tools using a reconstructed version from chat.

## Extraction API

```python
from kb_document_extractors import ExtractionError, Limits, Options, extract_bytes

# Use bytes already captured safely from the original file, not another read of its live path.
extracted = extract_bytes(
    raw_bytes,
    original_basename,
    limits=Limits(),
    options=Options(),
)
text_bytes = extracted.text.encode("utf-8")
metadata = extracted.metadata
```

The API does not manage Stage 2 runs or dispatch subprocess workers. The standalone CLI provides one example of stable reads and worker execution; the integrated engine must apply its own timeout/resource policy. Do not synchronously parse arbitrary binaries without that boundary.

## Required design

Separate **original binary snapshot**, **derived text snapshot**, and **extraction metadata**. Preserve an original SHA-256, text SHA-256, extraction adapter/parser versions, source location, media type and source-segment-to-derived-line map. Keep UTF-8 text paths/semantics compatible for preexisting text-only runs.

Do not reuse a raw-file hash as a derived-text hash. Do not continue calling binary bytes UTF-8. Do not set `.encoding = utf-8` on an original PDF/PPT/XLSX object. A quote checks against the frozen derived text, then its locator identifies the original page/slide/paragraph/cell. Check that a quote is within source-content segments rather than wholly within generated warnings or labels. CSV/XLSX values are serialized within JSON lines: those wrappers are generated metadata, not direct quotations from a spreadsheet display.

If the manifest contract needs new fields, version it explicitly with backward-compatible reads for old runs. Do not silently change the meaning of old fields. Keep `project.json` v0.1 frozen; operational extraction options may be a separate policy file or explicit command options after reviewing existing configuration conventions.

Stable logical file IDs must still identify the original source path. Evidence revisions/delta compatibility must also account for extraction policy/version and derived-text changes: unchanged raw bytes do not prove unchanged evidence when the extractor changes.

At capture time, write artifacts only to the new run; never alter originals. At check time, validate both frozen hashes, sizes, encoding, segment ranges, metadata hash, required extraction status and original-format consistency. Do not re-extract to obtain “the latest” text during verification, packet creation or publication; re-extraction requires a new run.

At packet time, read frozen text, surface relevant warnings and locators, and treat all source content as untrusted data. Carry these distinctions into records, rendered views, releases and any export. Publication must retain or integrity-bind the originals and sidecars, not copy only text while implying full binary provenance.

Successful extraction is not automatic approval. Every derived document requires source-fidelity review. Missing visual semantics, comments or no-text pages must remain visible through coverage and review gates. Never auto-acknowledge the warnings or fabricate fidelity approval.

## Errors and warnings

Map `ExtractionError.code/detail` to an inventory error associated with the original `source_id` and relative path. Missing parser dependencies, inaccessible sources, corrupt/encrypted inputs, required PPT opt-in, failed conversion, tracked changes, disallowed structures, no extracted text and exhausted budgets must block, not become empty-source warnings.

An existing **empty directory** still produces the prior `empty_source_scope` warning. A completely empty **inventory** still blocks. Preserve the prior delta rule: incomplete inventories must not report uncaptured files as deleted. Do not suppress `.gitkeep` errors except through the explicitly configured exclusion.

Propagate extractor warning codes and locations into the normal review workflow. Mixed PDF documents with no-text pages must not qualify as “all content reviewed” merely because text extraction succeeded. XLSX caches remain unverified; null/missing cache is never zero. Hidden sheets/rows/columns/slides stay explicitly labeled. Track original provenance/authority separately from extraction metadata.

## Acceptance tests beyond this pack

Run the existing engine suite unchanged, then the adapter tests. Add integrated tests for every format across inventory → checker → packet → candidate citations → publication. Check raw and derived tampering independently; malformed segment maps; old ready-run reads; empty source behavior; failed parse blocking; include/exclude behavior; mixed format budgets; source changes during read; corrupt XML/ZIP; duplicate sheet/cell locators; extraction-version deltas; warning/fidelity gate enforcement; preservation of original files and release provenance.

Test a real legacy `.ppt` only with an approved converter. Report the exact OS/Python/parser/converter versions and any skipped cases. Test the user's macOS environment before claiming parity with Linux.

Completion requires a reviewed diff, versioned contract changes where needed, actual end-to-end execution evidence and a fresh pilot run. The presence of this adapter pack or its standalone green tests is not completion of native support.
