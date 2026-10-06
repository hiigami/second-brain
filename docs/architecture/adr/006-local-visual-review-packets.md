# ADR 006: Prepare local visual-review packets independently of model access

Status: accepted for the authorized development increment (2026-10-04).
Human fidelity assessment and GLM capability acceptance remain pending.

The approved GLM-5.3-flash assistant is temporarily unavailable. Original-byte
capture and structural evidence already exist, but reviewers need accessible
visuals and a way to record fidelity observations without changing frozen runs.

Add a separate `visual-review` operator command and versioned packet/assessment
contracts. It copies selected originals, binds their bytes and rendered outputs,
records original locators and unavailable content, and creates a human-assessment
template. Packets are development artifacts or run-local `work/` artifacts,
never replacements for manifests, segment inventories, or approved knowledge.

The optional uv `visual` extra supplies CairoSVG and Pillow. SVG rendering uses
defused XML, bounded structures and output dimensions, and a renderer fetcher
that refuses every external resource. Scripts/foreign content are excluded with
explicit gaps; active HTML is never opened or executed. Inert HTML yields only
inline SVG/image previews, not a claimed browser-equivalent page. PNG decoding
creates a raster preview without trusting its text annotations. Renderer versions
and restrictions are bound to packet metadata. See the [CairoSVG documentation](https://cairosvg.org/documentation/)
and [upstream implementation](https://github.com/Kozea/CairoSVG).

PDF pages use an explicitly supplied local `pdftoppm` executable, with recorded
identity/version, fixed output bounds and timeout. Office files expose bounded
embedded image bytes and source-part/slide locators; whole Office page layout is
unavailable until an operator supplies a separately reviewed PDF export. The tool
does not invoke LibreOffice, execute macros/formulas, fetch linked resources, or
perform OCR or visual-semantic interpretation. Rendering takes place in a
short-lived safe-path worker; budgets and isolation are defense in depth, not a
general hostile-file sandbox. The initial increment required Linux resource
controls and atomic no-replace rename support. The macOS compatibility repair
uses native `renamex_np` with `RENAME_EXCL` for the same no-overwrite guarantee,
retains CPU/file-size/time limits and input/renderer budgets, and discloses that
it omits the fixed address-space cap on macOS. Linux retains that cap; both
platforms preserve tighter inherited limits. Other hosts do not create packets.
Readers accept either recognized producer limitation profile independently of
their own platform. Assessment results and exported provenance retain the
packet's bound limitations; unknown or incomplete profiles remain unsupported.
Native macOS validation remains pending; Linux tests simulate the Darwin API
and exercise symlinked temporary-directory behavior.
The Darwin binding follows Apple's [rename declarations and flags](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/stdio.h)
and [exclusive-rename regression](https://github.com/apple-oss-distributions/xnu/blob/main/tests/rename_excl.c).
Apple's [resource-limit implementation](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_resource.c)
can reject an address-space limit below current virtual-memory usage.

Human assessments bind the exact packet manifest and item set, compare material
elements with the originals, retain regions, transcriptions, omissions and
unavailable content, and record reviewer/time. Structural verification cannot
prove the observations correct or authenticate a human. An export is a new,
traceable text source requiring separate scope authorization, fresh capture,
semantic review and normal human approval. No result changes project knowledge
or closes automatic visual-support acceptance. The GLM probe can be completed
later against the same original hashes and human references.

Rejected alternatives: silently treating source XML/PNG annotations as visible
truth; running a browser on active source HTML; automatically converting Office
documents; or substituting another model/provider for the approved assistant.
Existing evidence identities, schemas, and old releases remain unchanged.
