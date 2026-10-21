# Advance visual review while GLM is unavailable

The local `visual-review` command prepares previews and records human comparison
without invoking a model. It advances the rendering and human-reference portions
of Patch G/R2/R3. A verified viewing mechanism and a blind probe in the approved
GLM-5.3-flash assistant remain pending until that assistant is available. A parser
test, a renderer, or a human transcription cannot prove GLM visual access.

## Prepare a synthetic review packet

The command requires Linux or macOS, Python 3.14, and the optional uv extra.
Both platforms use native atomic no-replace rename and enforce CPU, file-size
and wall-clock limits. Linux also imposes a 512 MiB address-space cap; macOS
omits that cap because the interpreter's virtual size can already exceed it.
The macOS packet records this limitation. Tighter inherited resource limits
remain in force on both platforms. Verification accepts either recognized
producer limitation profile on either platform; assessment and export retain
the limitations recorded in the packet. Unknown or incomplete profiles are
rejected. SVG also needs a usable native
Cairo library; missing renderers produce explicit unavailable issues. PDF rendering
requires an explicitly selected trusted local Poppler `pdftoppm` executable.
There is no automatic installation or document conversion at runtime.

```sh
uv sync --locked --extra visual
uv run --locked --extra visual second-brain visual-review prepare \
  --source tests/fixtures/patch_g_visual_probe.png \
  --source tests/fixtures/patch_g_diagram.svg \
  --source tests/fixtures/patch_g_dense_visual.html \
  --out /tmp/second-brain-visual-review
uv run --locked --extra visual second-brain visual-review verify \
  --packet /tmp/second-brain-visual-review
```

These commands require a fresh output directory and an existing parent. Choose
a new output name for a later packet; preparation never overwrites one. The
paths must contain no symlinks, including parent directories. On macOS, use
`/private/tmp` instead of `/tmp` in these examples; for a system temporary path
under `/var`, select its canonical `/private/var` path. Do not resolve an
untrusted source symlink to bypass the source-path guard. The synthetic
preparation/verification commands were exercised locally on Linux; native
macOS verification remains pending. Review the
actual packet, not just command success. Open `index.html` locally for its PNG
previews, read `review.md`, and inspect the exact original bytes separately with
a trusted viewer. Originals are copied into inert `originals/*.bin` files; their
filenames, original paths, hashes and byte counts remain in `packet.json`.
If a viewer needs the original extension, copy the exact bytes to a separate
review location with that extension and verify the hash; keep the sealed packet
unchanged. Use an approved viewer that disables active content and remote loading.
Without an appropriate original-viewing method, mark fidelity unresolved.

For selected authorized real originals, repeat `--source /authorized/input.svg`
or another supported extension. Inside a configured project, output must be a
fresh child of its configured `runs/<run>/work/`; frozen evidence, proposals and
configured approved knowledge are excluded. This command does not select or
authorize source scope, modify manifests, or establish a frozen evidence id.
Its source/asset ids are packet-local ids, not citation evidence ids. Snapshot
files renamed to inert `.txt` or `.bin` are not automatically reclassified.

PNG/JPEG previews decode pixels and discard image annotations. SVG previews
exclude active/unsupported content and refuse all file/network/data resource
fetches, retaining explicit gaps for those changes. Internal fragment references
remain permitted. HTML yields inline SVG and embedded PNG/JPEG previews only;
text, tables, CSS and whole-page fidelity require separate original comparison.
Office ZIP media receive part locators, but placement, crops, shapes, charts,
text, and page layout remain unavailable. A separately reviewed PDF export can
be selected as another source; the tool does not assert equivalence to its Office
original. Legacy `.ppt` conversion is not performed.

For PDF, add `--pdftoppm /usr/bin/pdftoppm` only if that path is the trusted
executable on your machine. Its bytes/version are recorded. Rasterized page
previews include the page rendering, including nested content handled by Poppler;
they do not become semantic records or replace existing PDF segment inventory.
Limits include eight sources, 25 MiB each/32 MiB total originals, 100 visual items,
20 PDF pages, eight million input raster pixels, 1600-pixel preview dimensions,
64 MiB packet content, and a 90-second worker timeout. Content beyond a renderer
limit remains unavailable or causes preparation to fail; it is not silently
accepted as complete. Sanitization and worker budgets are defense in depth,
not a general hostile-file sandbox. System fonts/renderers may affect appearance;
the exact generated PNG hashes bind the reviewed version.

## Record actual human comparison

Copy `assessment.template.json` to a separate location outside the sealed packet.
The template intentionally contains no reviewer, score or acceptance. A human
enters their name, timezone-bearing `reviewed_at`, and `inventory_confirmed: true`
only after identifying **every material element** in each original. Comparing a
preview with itself does not establish fidelity. Use the [reference catalog](VISUAL_REFERENCE_CASES.md)
and [fidelity rubric](VISUAL_FIDELITY_REVIEW.md) for dimensions to inspect: labels,
edges, arrow direction, cardinality, status qualifiers, values/units, occlusion,
missing content, and legibility.

For each item, list bounded elements with a unique `id`, a disposition (`match`,
`omission`, `unsupported`, `unavailable`, or `unresolved`), `observation`, `note`,
and a `region` `[x, y, width, height]` in preview pixels or `null` when no preview
region can be located. A match requires a rendered preview, nonempty observation
and region. Inventory omitted/unavailable material too; do not omit it from the
denominator. Each gap requires `acknowledged_unavailable` or `unresolved` plus a
note. The command cannot clear a rendering gap, verify human identity, establish
that the material inventory is complete, or judge the observation's meaning.

The following commands are conditional on that **human-completed** JSON; the
automated tests exercise them only with synthetic test declarations:

```sh
uv run --locked --extra visual second-brain visual-review assess \
  --packet /tmp/second-brain-visual-review \
  --assessment /tmp/visual-assessment.completed.json
uv run --locked --extra visual second-brain visual-review export \
  --packet /tmp/second-brain-visual-review \
  --assessment /tmp/visual-assessment.completed.json \
  --out /tmp/second-brain-reviewed-transcription
```

Assessment reports counts and `matched_elements / declared_elements`; omissions,
unknowns and unavailable elements stay in the denominator. No elements means
no score. Any non-match, retained gap, or zero-element review yields
`needs_attention`; there is no automatic pass threshold or approval. A fraction
of 1 alone cannot establish faithful page layout or complete material inventory.

Export creates `transcription.md`, the completed assessment and `provenance.json`
in a fresh directory. It keeps source/asset/preview hashes, original locators,
pixel regions, human declarations and gaps. The text is a separate human-authored
observation source, not a replacement for its original. An operator must authorize
its scope, capture it in a fresh run, cite that run's real evidence ids/lines,
retain provenance and uncertainties, and perform normal semantic/human review
before publication. This tool never approves, captures or publishes that export.

When GLM returns, run the [blind capability probes](VISUAL_CAPABILITY_PROBE.md)
using the same original hashes. Keep the construction oracle and human reference
answers outside the probe input. Record the actual viewing mechanism and response
in the [capability review](../templates/VISUAL_CAPABILITY_REVIEW.md), then compare
with human references and representative authorized documents. Until then,
human visual review can progress while GLM visual acceptance remains unverified.
