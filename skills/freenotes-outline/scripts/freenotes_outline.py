#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile


ROOT_OUTLINE_ID = "kRootOutlineID"


@dataclass
class Field:
    num: int
    wt: int
    key_start: int
    value_start: int
    end: int
    value: object
    raw: bytes


@dataclass
class PageRecord:
    page_id: str
    page_index: int


@dataclass
class OutlineRecord:
    outline_id: str
    parent_id: str | None
    page_id: str | None
    title: str | None
    root_flag: int | None
    page_index: int | None = None


def die(message: str) -> None:
    raise SystemExit(f"error: {message}")


def read_varint(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise ValueError("truncated varint")
        b = data[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            return value, pos
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def enc_varint(value: int) -> bytes:
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def key(num: int, wt: int) -> bytes:
    return enc_varint((num << 3) | wt)


def parse_fields(data: bytes) -> list[Field]:
    fields: list[Field] = []
    pos = 0
    while pos < len(data):
        start = pos
        k, pos = read_varint(data, pos)
        num, wt = k >> 3, k & 7
        value_start = pos
        if wt == 0:
            value, pos = read_varint(data, pos)
        elif wt == 1:
            value = data[pos : pos + 8]
            pos += 8
        elif wt == 2:
            length, pos = read_varint(data, pos)
            value_start = pos
            value = data[pos : pos + length]
            pos += length
        elif wt == 5:
            value = data[pos : pos + 4]
            pos += 4
        else:
            raise ValueError(f"unsupported wire type {wt} at byte {start}")
        fields.append(Field(num, wt, start, value_start, pos, value, data[start:pos]))
    return fields


def field_varint(num: int, value: int) -> bytes:
    return key(num, 0) + enc_varint(value)


def field_str(num: int, text: str) -> bytes:
    raw = text.encode("utf-8")
    return key(num, 2) + enc_varint(len(raw)) + raw


def field_msg(num: int, msg: bytes) -> bytes:
    return key(num, 2) + enc_varint(len(msg)) + msg


def get_str(fields: list[Field], num: int) -> str | None:
    for f in fields:
        if f.num == num and f.wt == 2:
            try:
                return bytes(f.value).decode("utf-8")
            except UnicodeDecodeError:
                return None
    return None


def get_varint(fields: list[Field], num: int, default: int | None = None) -> int | None:
    for f in fields:
        if f.num == num and f.wt == 0:
            return int(f.value)
    return default


def parse_page_range(spec: str) -> list[int]:
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            left, right = part.split("-", 1)
            start, end = int(left), int(right)
            step = 1 if end >= start else -1
            pages.extend(range(start, end + step, step))
        else:
            pages.append(int(part))
    return pages


def find_member(zf: ZipFile, suffix: str) -> str:
    matches = [name for name in zf.namelist() if name.endswith(suffix)]
    if not matches:
        die(f"cannot find ZIP member ending with {suffix}")
    if len(matches) > 1:
        matches = [m for m in matches if m.count("/") == min(x.count("/") for x in matches)]
    return matches[0]


def read_document(archive: Path) -> tuple[str, bytes]:
    with ZipFile(archive, "r") as zf:
        doc_name = find_member(zf, "/document.dat")
        return doc_name, zf.read(doc_name)


def document_container(doc: bytes) -> tuple[Field, bytes, list[Field]]:
    top_fields = parse_fields(doc)
    container_field = next((f for f in top_fields if f.num == 4 and f.wt == 2), None)
    if container_field is None:
        die("document.dat has no field 4 container")
    container = bytes(container_field.value)
    return container_field, container, parse_fields(container)


def parse_document(doc: bytes) -> tuple[dict[int, PageRecord], list[OutlineRecord]]:
    _, container, container_fields = document_container(doc)
    del container
    pages: dict[int, PageRecord] = {}
    page_index_by_id: dict[str, int] = {}
    outlines: list[OutlineRecord] = []

    for f in container_fields:
        if f.num == 1 and f.wt == 2:
            sub = parse_fields(bytes(f.value))
            page_id = get_str(sub, 1)
            if not page_id:
                continue
            page_index = int(get_varint(sub, 3, 0) or 0)
            pages[page_index] = PageRecord(page_id, page_index)
            page_index_by_id[page_id] = page_index

    for f in container_fields:
        if f.num == 4 and f.wt == 2:
            sub = parse_fields(bytes(f.value))
            outline_id = get_str(sub, 1)
            if not outline_id:
                continue
            page_id = get_str(sub, 3)
            outlines.append(
                OutlineRecord(
                    outline_id=outline_id,
                    parent_id=get_str(sub, 2),
                    page_id=page_id,
                    title=get_str(sub, 4),
                    root_flag=get_varint(sub, 7),
                    page_index=page_index_by_id.get(page_id) if page_id else None,
                )
            )

    return pages, outlines


def outline_children(outlines: list[OutlineRecord]) -> dict[str | None, list[OutlineRecord]]:
    children: dict[str | None, list[OutlineRecord]] = defaultdict(list)
    for outline in outlines:
        children[outline.parent_id].append(outline)
    return children


def outline_path_map(outlines: list[OutlineRecord]) -> dict[tuple[str, ...], OutlineRecord]:
    children = outline_children(outlines)
    paths: dict[tuple[str, ...], OutlineRecord] = {}

    def walk(parent_id: str, path: tuple[str, ...]) -> None:
        for child in children.get(parent_id, []):
            if not child.title:
                continue
            child_path = path + (child.title,)
            paths[child_path] = child
            walk(child.outline_id, child_path)

    walk(ROOT_OUTLINE_ID, ())
    return paths


def print_tree(outlines: list[OutlineRecord], max_depth: int | None = None) -> None:
    children = outline_children(outlines)

    def show(parent_id: str, depth: int) -> None:
        if max_depth is not None and depth >= max_depth:
            return
        for child in children.get(parent_id, []):
            if not child.title:
                continue
            viewer = child.page_index + 1 if child.page_index is not None else None
            suffix = f" -> pageIndex={child.page_index}, viewer={viewer}"
            print(f"{'  ' * depth}- {child.title}{suffix}")
            show(child.outline_id, depth + 1)

    show(ROOT_OUTLINE_ID, 0)


def extract_index_db(archive: Path, tempdir: Path) -> Path:
    with ZipFile(archive, "r") as zf:
        index_name = find_member(zf, "/index.db")
        out = tempdir / "index.db"
        out.write_bytes(zf.read(index_name))
        return out


def read_pdf_index_pages(archive: Path, page_indexes: list[int]) -> list[tuple[int, str]]:
    with tempfile.TemporaryDirectory() as td:
        db_path = extract_index_db(archive, Path(td))
        conn = sqlite3.connect(db_path)
        try:
            placeholders = ",".join("?" for _ in page_indexes)
            rows = conn.execute(
                f"""
                select cast(c1 as integer), c3
                from FDPdfIndex_18_0_0_content
                where cast(c1 as integer) in ({placeholders})
                order by cast(c1 as integer)
                """,
                page_indexes,
            ).fetchall()
        finally:
            conn.close()
    return [(int(idx), text or "") for idx, text in rows]


def extract_embedded_pdf(archive: Path, tempdir: Path) -> Path:
    with ZipFile(archive, "r") as zf:
        pdf_members = [name for name in zf.namelist() if "/PDFs/" in name and name.lower().endswith(".pdf")]
        if not pdf_members:
            die("cannot find embedded PDF under PDFs/")
        if len(pdf_members) > 1:
            pdf_members.sort()
        pdf_path = tempdir / "embedded.pdf"
        pdf_path.write_bytes(zf.read(pdf_members[0]))
        return pdf_path


def tesseract_languages() -> set[str]:
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            check=True,
            text=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return set()
    langs = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if line and not line.startswith("List of available"):
            langs.add(line)
    return langs


def ensure_tesseract_langs(lang_spec: str) -> None:
    langs = tesseract_languages()
    if not langs:
        die("tesseract is not installed or cannot list languages; pass --ocr-command or install tesseract")
    missing = [lang for lang in re.split(r"[+ ]+", lang_spec) if lang and lang not in langs]
    if missing:
        die(
            "missing tesseract language data: "
            + ", ".join(missing)
            + f"; installed languages: {', '.join(sorted(langs))}; pass --ocr-lang or --ocr-command"
        )


def ocr_pdf_pages(
    archive: Path,
    page_indexes: list[int],
    lang: str,
    dpi: int,
    psm: int,
    ocr_command: str | None,
) -> list[tuple[int, str]]:
    with tempfile.TemporaryDirectory() as td:
        tempdir = Path(td)
        pdf_path = extract_embedded_pdf(archive, tempdir)
        if shutil.which("mutool") is None:
            die("mutool is required to render PDF pages before OCR")
        if not ocr_command:
            ensure_tesseract_langs(lang)

        rows: list[tuple[int, str]] = []
        for page_index in page_indexes:
            image_path = tempdir / f"toc_page_{page_index}.png"
            subprocess.run(
                [
                    "mutool",
                    "draw",
                    "-r",
                    str(dpi),
                    "-o",
                    str(image_path),
                    str(pdf_path),
                    str(page_index + 1),
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            if ocr_command:
                command = ocr_command.format(image=str(image_path), lang=lang, dpi=dpi, psm=psm)
                result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
                text = result.stdout
            else:
                result = subprocess.run(
                    ["tesseract", str(image_path), "stdout", "-l", lang, "--psm", str(psm)],
                    check=True,
                    text=True,
                    capture_output=True,
                )
                text = result.stdout
            rows.append((page_index, text or ""))
        return rows


def normalize_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title.strip())
    title = title.replace(" ：", "：").replace(": ", "：")
    title = title.replace("1/O", "I/O")
    return title


def parse_toc_line(line: str) -> tuple[int, str, int] | None:
    line = line.strip()
    if not line:
        return None
    page_match = re.search(r"(?P<title>.*?)(?:[.．·•…]{2,}|\s{2,}|\s+)(?P<page>\d+)\s*$", line)
    if not page_match:
        return None
    raw_title = page_match.group("title").strip(" .．·•…")
    page = int(page_match.group("page"))

    if re.match(r"^[一二三四五六七八九十]+\s*、", raw_title):
        title = re.sub(r"^[一二三四五六七八九十]+\s*、\s*", "", raw_title)
        return 1, normalize_title(title), page
    if re.match(r"^[\(（][一二三四五六七八九十]+[\)）]", raw_title):
        title = re.sub(r"^[\(（][一二三四五六七八九十]+[\)）]\s*", "", raw_title)
        return 2, normalize_title(title), page
    if re.match(r"^\d+\.", raw_title):
        title = re.sub(r"^\d+\.\s*", "", raw_title)
        return 3, normalize_title(title), page
    if re.match(r"^\d{4}\s*年真题大题", raw_title):
        return 1, normalize_title(raw_title), page
    return None


def parse_toc_rows(rows: list[tuple[int, str]], viewer_offset: int) -> list[dict]:
    raw_lines: list[str] = []
    pending_chapter: str | None = None
    skip_exact = {
        "更多资料 + QQ 群 857807137",
        "目 录",
        "免费分享",
        "word 版本等更多资料在群聊中",
        "可以自由修改，禁止转卖",
    }

    for _, content in rows:
        for raw in content.splitlines():
            line = raw.strip()
            if not line or line in skip_exact:
                continue
            if re.fullmatch(r"\d+", line):
                continue
            if re.fullmatch(r"[一二三四五六七八九十]+", line):
                pending_chapter = line
                continue
            if pending_chapter and line.startswith("、"):
                line = pending_chapter + line
                pending_chapter = None
            raw_lines.append(line)

    entries = []
    for line in raw_lines:
        parsed = parse_toc_line(line)
        if not parsed:
            continue
        level, title, toc_page = parsed
        entries.append(
            {
                "level": level,
                "title": title,
                "toc_page": toc_page,
                "viewer_page": toc_page + viewer_offset,
            }
        )
    return entries


def raw_pages(rows: list[tuple[int, str]]) -> list[dict]:
    return [{"page_index": idx, "text": text} for idx, text in rows]


def extract_toc_entries(
    archive: Path,
    toc_pages: list[int],
    viewer_offset: int,
    source: str,
    min_entries: int,
    ocr_lang: str,
    ocr_dpi: int,
    ocr_psm: int,
    ocr_command: str | None,
) -> dict:
    notes: list[str] = []
    source_used = source
    source_rows: list[tuple[int, str]] = []
    if source in {"auto", "index"}:
        index_rows = read_pdf_index_pages(archive, toc_pages)
        entries = parse_toc_rows(index_rows, viewer_offset)
        if source == "index" or len(entries) >= min_entries:
            source_used = "index"
            source_rows = index_rows
        else:
            notes.append(f"index text produced only {len(entries)} entries; falling back to OCR")
            ocr_rows = ocr_pdf_pages(archive, toc_pages, ocr_lang, ocr_dpi, ocr_psm, ocr_command)
            entries = parse_toc_rows(ocr_rows, viewer_offset)
            source_used = "ocr"
            source_rows = ocr_rows
    elif source == "ocr":
        ocr_rows = ocr_pdf_pages(archive, toc_pages, ocr_lang, ocr_dpi, ocr_psm, ocr_command)
        entries = parse_toc_rows(ocr_rows, viewer_offset)
        source_rows = ocr_rows
    else:
        die(f"unknown TOC source: {source}")

    return {
        "format": "freenotes-outline-v1",
        "source": str(archive),
        "toc_source": source_used,
        "toc_pages": toc_pages,
        "viewer_offset": viewer_offset,
        "notes": notes,
        "raw_pages": raw_pages(source_rows),
        "entries": entries,
    }


def print_extracted_tree(outline_json: dict) -> None:
    stack: dict[int, str] = {}
    for entry in outline_json.get("entries", []):
        level = int(entry["level"])
        title = entry["title"]
        toc_page = entry["toc_page"]
        viewer_page = entry.get("viewer_page")
        indent = "  " * (level - 1)
        print(f"{indent}- {title} {toc_page} -> {viewer_page}")
        stack[level] = title
        for deeper in [k for k in stack if k > level]:
            del stack[deeper]


def outline_message(outline_id: str, parent_id: str, page_id: str, title: str) -> bytes:
    return b"".join(
        [
            field_str(1, outline_id),
            field_str(2, parent_id),
            field_str(3, page_id),
            field_str(4, title),
        ]
    )


def root_outline_message() -> bytes:
    return field_str(1, ROOT_OUTLINE_ID) + field_varint(7, 1)


def load_outline_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        die(f"outline JSON not found: {path}")
    if "entries" not in data or not isinstance(data["entries"], list):
        die("outline JSON must contain an entries list")
    return data


def apply_outline(
    archive: Path,
    outline_json: dict,
    page_index_offset: int,
    backup: bool,
    dry_run: bool,
) -> dict:
    doc_name, original_doc = read_document(archive)
    container_field, container, container_fields = document_container(original_doc)
    pages, outlines = parse_document(original_doc)
    page_id_by_index = {idx: page.page_id for idx, page in pages.items()}
    path_records = outline_path_map(outlines)
    id_by_path = {path: record.outline_id for path, record in path_records.items()}

    has_root = any(o.outline_id == ROOT_OUTLINE_ID for o in outlines)
    stack_path: dict[int, tuple[str, ...]] = {0: ()}
    created: list[dict] = []
    reused: list[dict] = []
    wrapped_messages: list[bytes] = []

    if not has_root:
        wrapped_messages.append(field_msg(4, root_outline_message()))

    for raw_entry in outline_json["entries"]:
        level = int(raw_entry["level"])
        title = str(raw_entry["title"]).strip()
        toc_page = int(raw_entry["toc_page"])
        if level < 1:
            die(f"invalid outline level for {title}: {level}")
        parent_path = stack_path.get(level - 1)
        if parent_path is None:
            die(f"missing parent before level {level} entry: {title}")
        path = parent_path + (title,)
        if path in id_by_path:
            outline_id = id_by_path[path]
            reused.append({"path": list(path), "outline_id": outline_id})
        else:
            target_index = toc_page + page_index_offset
            page_id = page_id_by_index.get(target_index)
            if not page_id:
                die(f"no FreeNotes page_id for target pageIndex {target_index} ({title})")
            parent_id = id_by_path.get(parent_path, ROOT_OUTLINE_ID)
            outline_id = str(uuid.uuid4()).upper()
            id_by_path[path] = outline_id
            wrapped_messages.append(field_msg(4, outline_message(outline_id, parent_id, page_id, title)))
            created.append(
                {
                    "path": list(path),
                    "outline_id": outline_id,
                    "parent_id": parent_id,
                    "page_index": target_index,
                    "viewer_page": target_index + 1,
                }
            )
        stack_path[level] = path
        for deeper in [k for k in stack_path if k > level]:
            del stack_path[deeper]

    if dry_run:
        return {"created": created, "reused": reused, "dry_run": True}
    if not wrapped_messages:
        return {"created": created, "reused": reused, "dry_run": False, "changed": False}

    insert_at = None
    first_footer_at = None
    seen_outline = False
    for f in container_fields:
        if f.num == 5 and first_footer_at is None:
            first_footer_at = f.key_start
        if f.num == 4:
            seen_outline = True
        elif seen_outline and f.num == 5:
            insert_at = f.key_start
            break
    if insert_at is None:
        insert_at = first_footer_at if first_footer_at is not None else len(container)

    new_container = container[:insert_at] + b"".join(wrapped_messages) + container[insert_at:]
    new_doc = (
        original_doc[: container_field.key_start]
        + field_msg(4, new_container)
        + original_doc[container_field.end :]
    )
    parse_fields(new_doc)
    parse_fields(new_container)

    if backup:
        backup_path = archive.with_name(archive.name + ".bak-before-outline")
        if backup_path.exists():
            backup_path = archive.with_name(archive.name + f".bak-before-outline-{uuid.uuid4().hex[:8]}")
        shutil.copy2(archive, backup_path)
    else:
        backup_path = None

    tmp_archive = archive.with_name(archive.name + ".tmp")
    with ZipFile(archive, "r") as zin, ZipFile(tmp_archive, "w", allowZip64=True) as zout:
        for info in zin.infolist():
            data = new_doc if info.filename == doc_name else zin.read(info.filename)
            zout.writestr(info, data)
    os.replace(tmp_archive, archive)

    return {
        "created": created,
        "reused": reused,
        "dry_run": False,
        "changed": True,
        "backup": str(backup_path) if backup_path else None,
    }


def cmd_inspect(args: argparse.Namespace) -> None:
    archive = Path(args.archive)
    doc_name, doc = read_document(archive)
    pages, outlines = parse_document(doc)
    with ZipFile(archive, "r") as zf:
        names = zf.namelist()
        pdfs = [name for name in names if "/PDFs/" in name and name.lower().endswith(".pdf")]
        has_index = any(name.endswith("/index.db") for name in names)
    visible = [o for o in outlines if o.title]
    print(f"archive: {archive}")
    print(f"document: {doc_name}")
    print(f"pages: {len(pages)}")
    print(f"pdfs: {len(pdfs)}")
    print(f"index.db: {'yes' if has_index else 'no'}")
    print(f"outline records: {len(outlines)}")
    print(f"visible outlines: {len(visible)}")
    if args.print_tree:
        print_tree(outlines, max_depth=args.max_depth)


def cmd_extract_toc(args: argparse.Namespace) -> None:
    archive = Path(args.archive)
    toc_pages = parse_page_range(args.toc_pages)
    outline_json = extract_toc_entries(
        archive=archive,
        toc_pages=toc_pages,
        viewer_offset=args.viewer_offset,
        source=args.source,
        min_entries=args.min_entries,
        ocr_lang=args.ocr_lang,
        ocr_dpi=args.ocr_dpi,
        ocr_psm=args.ocr_psm,
        ocr_command=args.ocr_command,
    )
    if args.out:
        Path(args.out).write_text(json.dumps(outline_json, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote: {args.out}")
    if args.raw_out:
        with Path(args.raw_out).open("w", encoding="utf-8") as f:
            for page in outline_json.get("raw_pages", []):
                f.write(f"--- pageIndex={page['page_index']} viewer={int(page['page_index']) + 1} ---\n")
                f.write(page.get("text") or "")
                if not str(page.get("text") or "").endswith("\n"):
                    f.write("\n")
        print(f"wrote raw text: {args.raw_out}")
    print(f"toc_source: {outline_json.get('toc_source')}")
    for note in outline_json.get("notes", []):
        print(f"note: {note}")
    print(f"entries: {len(outline_json['entries'])}")
    if args.print_tree:
        print_extracted_tree(outline_json)


def cmd_apply_outline(args: argparse.Namespace) -> None:
    archive = Path(args.archive)
    outline_json = load_outline_json(Path(args.outline))
    result = apply_outline(
        archive=archive,
        outline_json=outline_json,
        page_index_offset=args.page_index_offset,
        backup=args.backup and not args.dry_run,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_verify(args: argparse.Namespace) -> None:
    archive = Path(args.archive)
    doc_name, doc = read_document(archive)
    pages, outlines = parse_document(doc)
    del doc_name
    missing = [o for o in outlines if o.title and o.page_id and o.page_index is None]
    print(f"pages: {len(pages)}")
    print(f"outline records including root: {len(outlines)}")
    print(f"visible outlines: {sum(1 for o in outlines if o.title)}")
    print(f"missing target pages: {len(missing)}")
    if missing:
        for item in missing[:20]:
            print(f"missing: {item.title} -> {item.page_id}")
    if args.print_tree:
        print_tree(outlines, max_depth=args.max_depth)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and patch FreeNotes .freenotes outlines.")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect", help="inspect package structure and existing outlines")
    inspect.add_argument("archive")
    inspect.add_argument("--print-tree", action="store_true")
    inspect.add_argument("--max-depth", type=int)
    inspect.set_defaults(func=cmd_inspect)

    extract = sub.add_parser("extract-toc", help="extract a table of contents from index.db PDF text")
    extract.add_argument("archive")
    extract.add_argument("--toc-pages", default="1-4", help="FreeNotes/PDF internal page indexes to scan")
    extract.add_argument("--viewer-offset", type=int, default=1, help="viewer_page = toc_page + viewer_offset")
    extract.add_argument("--source", choices=["auto", "index", "ocr"], default="auto")
    extract.add_argument("--min-entries", type=int, default=5, help="auto mode falls back to OCR below this count")
    extract.add_argument("--ocr-lang", default="chi_sim+eng", help="tesseract language spec for OCR fallback")
    extract.add_argument("--ocr-dpi", type=int, default=220)
    extract.add_argument("--ocr-psm", type=int, default=6)
    extract.add_argument(
        "--ocr-command",
        help="custom OCR shell command template; may use {image}, {lang}, {dpi}, {psm}; must print text to stdout",
    )
    extract.add_argument("--out", help="write outline JSON")
    extract.add_argument("--raw-out", help="write raw TOC source text for LLM cleanup")
    extract.add_argument("--print-tree", action="store_true")
    extract.set_defaults(func=cmd_extract_toc)

    apply = sub.add_parser("apply-outline", help="insert outline JSON into document.dat")
    apply.add_argument("archive")
    apply.add_argument("--outline", required=True, help="outline JSON from extract-toc or hand-edited")
    apply.add_argument("--page-index-offset", type=int, default=0, help="target pageIndex = toc_page + offset")
    apply.add_argument("--backup", action=argparse.BooleanOptionalAction, default=True)
    apply.add_argument("--dry-run", action="store_true")
    apply.set_defaults(func=cmd_apply_outline)

    verify = sub.add_parser("verify", help="verify outlines and target pages")
    verify.add_argument("archive")
    verify.add_argument("--print-tree", action="store_true")
    verify.add_argument("--max-depth", type=int)
    verify.set_defaults(func=cmd_verify)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
