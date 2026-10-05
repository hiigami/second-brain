# Technical references and verification scope

These public primary references were consulted on 2026-09-30 for implementation semantics, not as substitutes for the private project conversations.

| Reference | Use in this bundle |
| --- | --- |
| Python pathlib documentation — `https://docs.python.org/3/library/pathlib.html` | Distinguishing lexical relative-path checks from filesystem resolution and symlink behavior. The bundle uses its own documented glob matcher rather than assuming pathlib.match implements recursive globstar. |
| Python os documentation — `https://docs.python.org/3/library/os.html` | File-descriptor reads, metadata checks, no-follow flag when available, traversal, and atomic pointer replacement primitives. |
| JSON Schema object reference — `https://json-schema.org/understanding-json-schema/reference/object` | Required fields and explicit additional-property handling for strict contracts. |
| Mermaid flowchart reference — `https://mermaid.js.org/syntax/flowchart.html` | Text-node and directed-edge syntax and label escaping for generated maps. |

The actual scripts, schemas, regression tests, and recorded validation logs are the evidence for this bundle's behavior. Public documentation does not establish that the user's environment has been tested. The bundled miniature schema validator implements only the keywords present in the supplied schemas; the release was separately checked with a full Draft 2020-12 validator in the build environment.

No provider claims about GLM-5.3-flash performance, context size, tools, or API behavior are relied upon. The model/effort constraint comes from the user's project conversations. No particular Google export API option is assumed or implemented.
