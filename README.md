# FreeNotes Outline Skill

Codex skill for inspecting FreeNotes `.freenotes` packages, extracting a table of contents, and safely writing FreeNotes outline entries.

## Install

Ask Codex to install this skill from the GitHub path after the repository is published:

```text
Install https://github.com/Tiomehsh/freenotes-outline-skill/tree/main/skills/freenotes-outline
```

Or run the bundled Codex installer:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py --repo Tiomehsh/freenotes-outline-skill --path skills/freenotes-outline
```

Restart Codex after installation.

## Notes

- The skill requires Python 3.
- Text-layer PDFs are handled through FreeNotes `index.db`.
- Scanned PDFs require `mutool` and Tesseract for OCR unless a custom OCR command is supplied.
- The skill writes backups by default before modifying `.freenotes` files.
