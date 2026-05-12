# FreeNotes `.freenotes` Outline Format

FreeNotes exports are ZIP containers. The package usually contains one top-level `*.frnote/` directory.

Important members:

- `document.dat`: protobuf wire-format document model containing page records and outline records.
- `index.db`: SQLite FTS index containing extracted PDF text and OCR/text-object indexes.
- `PDFs/*.pdf`: embedded source PDF.
- `FNPages/*.dat`: per-page annotations and handwriting.

Reverse-engineered `document.dat` structure:

```text
top-level field 4 = document/page container

container field 1 = page record
  field 1 = FreeNotes page_id
  field 3 = pageIndex, zero-based internal page index; absent means 0
  field 4.2 = embedded PDF file id
  field 4.3 = embedded PDF page index for some records
  field 6 = annotation FNPages id, when present
  field 8 = OCR id, when present

container field 4 = outline record
  field 1 = outline_id
  field 2 = parent_outline_id
  field 3 = target FreeNotes page_id
  field 4 = title
  field 7 = 1 for root outline record

container field 5 = observed footer/version marker
```

Hierarchy is encoded by `parent_outline_id`. Root is normally `kRootOutlineID`.

Safe write strategy:

1. Parse `document.dat` with a protobuf wire parser.
2. Build `page_id_by_index` from page records.
3. Build existing outline paths from `parent_outline_id`.
4. Insert new `container field 4` outline messages before the existing `container field 5`.
5. Repack the ZIP and run `zip -T` or `unzip -t`.

Do not edit the embedded PDF outline unless the user explicitly asks for PDF bookmarks instead of FreeNotes app outlines.

## TOC Extraction Sources

Preferred order:

1. `index.db` table `FDPdfIndex_18_0_0_content`, when the embedded PDF has a text layer or FreeNotes indexed the text.
2. OCR fallback: extract the embedded PDF, render TOC pages with `mutool draw`, then OCR each rendered image.

The script defaults to `--source auto`: use index text when it produces at least `--min-entries` entries, otherwise use OCR.

OCR notes:

- Default OCR backend is Tesseract.
- Chinese scanned PDFs need Chinese language data such as `chi_sim`; English-only Tesseract installs will not reliably read Chinese directories.
- `--ocr-command` can integrate another OCR backend. It receives `{image}`, `{lang}`, `{dpi}`, and `{psm}` placeholders and must print recognized text to stdout.

## LLM Curation Boundary

The Python parser is intentionally heuristic. It is acceptable for clean text-layer PDFs, but OCR can introduce broken punctuation, missing dots, merged lines, split Chinese numerals, or wrong page numbers.

For OCR or noisy text:

1. Export raw text with `--raw-out`.
2. Let the model reconstruct a clean hierarchical outline JSON from the raw text and any rendered TOC page evidence.
3. Show the cleaned tree to the user for confirmation.
4. Only then run `apply-outline`.

The writeback script assumes `entries` are semantically correct. It should not decide chapter semantics beyond deterministic parent assignment by `level`.
