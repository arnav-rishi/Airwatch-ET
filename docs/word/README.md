# Word (.docx) versions

Microsoft Word copies of the technical documentation, with every Mermaid diagram
rendered to an embedded image so they display without a Markdown viewer.

| File | Source |
|---|---|
| `TECHNICAL_DOCUMENT.docx` | [`../TECHNICAL_DOCUMENT.md`](../TECHNICAL_DOCUMENT.md) — full plain-English technical doc, 13 diagrams |
| `ARCHITECTURE.docx` | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) — architecture + sequence diagrams, 6 diagrams |

These are generated files. If you change the source Markdown, regenerate them
rather than editing the `.docx` by hand:

```bash
python scripts/build_word_docs.py
```

The generator renders the diagrams with `@mermaid-js/mermaid-cli` (via `npx`,
which downloads a headless Chromium the first time) and builds the Word file with
`python-docx`. Both are the only extra requirements; no Word install is needed.
