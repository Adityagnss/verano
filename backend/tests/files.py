"""
Builders for the files the ingestion tests upload: the same rows written as CSV, XLSX,
JSON and JSONL; Excel-style CSV exports (Windows-1252, UTF-8 with BOM, semicolons);
reference documents (PDF, DOCX, TXT, MD); and deliberately malicious files: an XML
entity bomb inside an XLSX, zip bombs inside an XLSX and a DOCX, and an oversized PDF.
Everything is generated at test time, so no binary fixtures live in the repository.
"""

import csv
import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import docx
from openpyxl import Workbook

BOMB_PART_BYTES = 60_000_000
XML_BOMB = """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="inlineStr"><is><t>&lol3;</t></is></c></row>
</sheetData></worksheet>"""


def rows_file(rows: list[dict[str, Any]], file_format: str) -> bytes:
    columns = list(dict.fromkeys(key for row in rows for key in row))
    return WRITERS[file_format](rows, columns)


def _csv(rows: list[dict[str, Any]], columns: list[str], delimiter: str = ",") -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, delimiter=delimiter, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _xlsx(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Cases")
    sheet.append(columns)
    for row in rows:
        sheet.append([row.get(column) for column in columns])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


WRITERS: dict[str, Callable[[list[dict[str, Any]], list[str]], bytes]] = {
    "csv": lambda rows, columns: _csv(rows, columns).encode(),
    "xlsx": _xlsx,
    "json": lambda rows, _: json.dumps(rows, ensure_ascii=False).encode(),
    "jsonl": lambda rows, _: "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode(),
}


def excel_csv(rows: list[dict[str, Any]], encoding: str, delimiter: str) -> bytes:
    columns = list(dict.fromkeys(key for row in rows for key in row))
    return _csv(rows, columns, delimiter).encode(encoding)


def _replace_part(source: bytes, part: str, write: Any) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as original, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as copy:
        for entry in original.infolist():
            if entry.filename == part:
                with copy.open(part, "w", force_zip64=True) as handle:
                    write(handle)
            else:
                copy.writestr(entry, original.read(entry.filename))
    return output.getvalue()


def _write_zeros(handle: Any) -> None:
    chunk = b" " * 1_000_000
    for _ in range(BOMB_PART_BYTES // len(chunk)):
        handle.write(chunk)


def xlsx_with_xml_bomb() -> bytes:
    plain = _xlsx([{"ticket": "hi"}], ["ticket"])
    return _replace_part(plain, "xl/worksheets/sheet1.xml", lambda handle: handle.write(XML_BOMB.encode()))


def xlsx_zip_bomb() -> bytes:
    return _replace_part(_xlsx([{"ticket": "hi"}], ["ticket"]), "xl/worksheets/sheet1.xml", _write_zeros)


def docx_file(blocks: list[tuple[str, str]]) -> bytes:
    document = docx.Document()
    for style, text in blocks:
        if style == "heading":
            document.add_heading(text, level=1)
        else:
            document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def docx_zip_bomb() -> bytes:
    return _replace_part(docx_file([("paragraph", "hello")]), "word/document.xml", _write_zeros)


def pdf_file(pages: list[str]) -> bytes:
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", ""]
    kids = []
    for index, text in enumerate(pages):
        page_id, content_id = 4 + 2 * index, 5 + 2 * index
        kids.append(f"{page_id} 0 R")
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        objects += [
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R "
            "/Resources << /Font << /F1 3 0 R >> >> >>",
            f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        ]
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>"
    objects.insert(2, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    body, offsets = b"%PDF-1.4\n", []
    for number, content in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n{content}\nendobj\n".encode()
    xref = len(body)
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    body += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    body += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return body


def write(tmp: Path, name: str, content: bytes) -> Path:
    path = tmp / name
    path.write_bytes(content)
    return path
