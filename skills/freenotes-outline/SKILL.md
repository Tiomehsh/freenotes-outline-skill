---
name: freenotes-outline
description: Inspect and batch-edit FreeNotes exported note packages (`.freenotes`, usually ZIP containers with `.frnote/document.dat`). Use when Codex needs to understand FreeNotes file structure, extract a PDF table of contents, add hierarchical outline/bookmark entries, verify outline parent-child relationships, or safely patch FreeNotes outlines with backups.
---

# FreeNotes Outline

## Workflow

Use the bundled `scripts/freenotes_outline.py` for deterministic handling of FreeNotes outline data. Resolve the script path relative to this `SKILL.md`; do not hand-edit `document.dat`.

1. Inspect the package:

```bash
python3 <skill-dir>/scripts/freenotes_outline.py inspect NOTE.freenotes
```

2. Extract raw TOC text plus a candidate table of contents. Default `--source auto` reads the embedded PDF text index first, then falls back to OCR if too few entries are found. Use FreeNotes internal PDF page indexes for `--toc-pages`; for many PDF exports, the visible PDF page is `pageIndex + 1`.

```bash
python3 <skill-dir>/scripts/freenotes_outline.py extract-toc NOTE.freenotes --toc-pages 1-4 --viewer-offset 1 --out /tmp/outline.json --raw-out /tmp/toc_raw.txt --print-tree
```

For scanned/image-only PDFs, force OCR. Tesseract requires the relevant language data, for example `chi_sim+eng` for Simplified Chinese plus English. If Tesseract language data is unavailable, pass a custom OCR command that prints recognized text to stdout.

```bash
python3 <skill-dir>/scripts/freenotes_outline.py extract-toc NOTE.freenotes --toc-pages 1-4 --source ocr --ocr-lang chi_sim+eng --out /tmp/outline.json --raw-out /tmp/toc_raw.txt --print-tree
```

3. Use model judgment to curate the TOC before writing. Treat the script's parsed `entries` as a draft, especially after OCR. Read `/tmp/toc_raw.txt` and `/tmp/outline.json`, repair OCR mistakes, infer hierarchy, remove duplicated headers/footers, normalize titles, and resolve page-number ambiguity. If OCR output is noisy, rebuild `entries` manually instead of trusting the parser.

Required JSON shape for curated entries:

```json
{
  "format": "freenotes-outline-v1",
  "entries": [
    {"level": 1, "title": "Chapter", "toc_page": 5, "viewer_page": 6},
    {"level": 2, "title": "Section", "toc_page": 5, "viewer_page": 6}
  ]
}
```

4. Show the curated tree to the user and confirm page-offset assumptions before writing. If the directory says page `N` but the viewer lands on `N+1`, usually apply with `--page-index-offset 0` because FreeNotes target page IDs are keyed by zero-based `pageIndex`.

5. Dry-run the patch:

```bash
python3 <skill-dir>/scripts/freenotes_outline.py apply-outline NOTE.freenotes --outline /tmp/outline.json --dry-run
```

6. Apply only after confirmation. Keep backup enabled unless the user explicitly refuses it.

```bash
python3 <skill-dir>/scripts/freenotes_outline.py apply-outline NOTE.freenotes --outline /tmp/outline.json --backup
```

7. Verify the package and outline tree:

```bash
python3 <skill-dir>/scripts/freenotes_outline.py verify NOTE.freenotes --print-tree
```

## Rules

- Always create or confirm a backup before modifying a `.freenotes` file.
- Reuse existing outline paths instead of duplicating them.
- Treat outline targets as FreeNotes page IDs, not raw page numbers.
- Keep the user-facing distinction clear: `toc_page` is the page printed in the PDF directory; `viewer_page` is for display; `pageIndex` is the FreeNotes internal target index.
- If the PDF is image-only, use `extract-toc --source ocr`; if OCR quality is low, ask the user to confirm or patch `/tmp/outline.json` before applying.
- If extraction has OCR mistakes or ambiguous nesting, write the extracted JSON, patch it manually with `apply_patch`, then apply.
- Never insert raw OCR output directly. The model must curate noisy OCR into clean `entries` first; the Python script is for extraction, deterministic writeback, and validation, not semantic TOC reconstruction.

## Format Notes

For implementation details and current reverse-engineered fields, read `references/freenotes-format.md` only when needed.
