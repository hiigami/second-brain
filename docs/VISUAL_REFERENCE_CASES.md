# Synthetic visual reference cases

These fixtures provide construction oracles for the approved-assistant probe.
They are **not human-accepted visual references**. Establish rendered appearance
and material legibility through human comparison before scoring. No saved GLM
visual-access result is available, so Patch G/R2/R3 acceptance remains pending.
Use [the review template](../templates/VISUAL_CAPABILITY_REVIEW.md) to retain the
exact response, access mechanism, original hash, and comparison per case.

The [local visual-review workflow](LOCAL_VISUAL_REVIEW.md) prepares these originals
and raster previews for human comparison even while GLM is unavailable. Its
unmeasured assessment template is not a saved capability result or human score.

| Case | Original fixture | SHA-256 |
| --- | --- | --- |
| Pixel access and false metadata | `tests/fixtures/patch_g_visual_probe.png` | `a8ffc81510acb41982d03a12bab8a9c694097e3c7ff76baee4dbff7513d03840` |
| Ambiguous vector and missing asset | `tests/fixtures/patch_g_diagram.svg` | `1d0290f9d6734903186f47a4426bdb689803385d08489e12330a5afd4ae8e262` |
| Dense mixed HTML with ER/state diagrams | `tests/fixtures/patch_g_dense_visual.html` | `8a69fd7971f2c0a4ed5e6c723f8fded85b8df88a372746bc48cdbac1f99ec0ec` |

Keep this oracle out of the assistant's probe input. Ask it to inspect the
original through its approved local mechanism, report what it can establish,
and preserve uncertainty. Do not fetch remote resources or execute source
scripts to fill missing content.

The pixel fixture's construction uses a 64×32 canvas, red left half, blue right
half, and a yellow square at x=28–35/y=12–19. Its PNG annotation falsely says
the image is wholly green. Correct metadata extraction alone cannot pass
pixel access; compare the actual visible regions and the contradiction.

The ambiguous SVG has source labels Supplier, Invoice, and low-opacity `1:N`;
its description says one-to-one, and it refers to an unavailable external
image. Arrow styling, contrast, and label legibility require rendered
inspection. Source attributes cannot prove that a label or arrowhead is
visible. Do not turn its caption or source cardinality into a verified
visual relationship.

The dense HTML adds a positive construction case for all six requested R2
content families: an ER diagram; entity/relationship definitions; an
integration-specific SQL query; tracked model changes; a state diagram;
and values with units/status context. Source geometry specifies a Customer
to Order arrow with `1:N`, and a draft to active arrow labeled approve.
Tables contain Order.total, decimal, sample value 10.20 USD, v2, and date
2026-09-01. The heading, relationships, field, changes, diagrams, and date
are proposed or pending. Human rendering must confirm appearance and
legibility before those construction expectations become visual references.

Adapter tests verify preservation of those material source strings and two
explicit inline-SVG fidelity gaps. They do not infer edges or certify the
rendered diagrams. A bounded packet/capture test is not a successful GLM
perception test or an agreed real-document extraction threshold.

After capability testing, select authorized representative Office/PDF
embedded figures, cropped/illegible images, contradictory captions, and
mixed HTML exports. Record their original hashes and material denominators
in separate completed review artifacts. The synthetic cases do not waive
that representative fidelity assessment or real-project pilot measurements.
