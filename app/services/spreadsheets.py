"""Lettura dei fogli di calcolo (Excel) caricati come documenti.

Claude non legge nativamente i file .xls/.xlsx: li convertiamo in una
rappresentazione testuale (un blocco per foglio, righe tab-separate) che viene
passata al modello come "document" di tipo testo. Le dipendenze di parsing
(openpyxl per xlsx, xlrd per il vecchio xls) sono importate in modo lazy così
che l'assenza di una libreria non comprometta il resto dell'applicazione.
"""

from __future__ import annotations

import io
from pathlib import Path

# MIME tipici dei fogli di calcolo Excel.
_SPREADSHEET_MIMES = {
    "application/vnd.ms-excel",  # .xls
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/vnd.ms-excel.sheet.macroenabled.12",  # .xlsm
    "application/excel",
    "application/x-excel",
    "application/x-msexcel",
}

# Estensione → MIME, per normalizzare il content_type quando il browser invia
# un valore generico (octet-stream) o vuoto.
_EXTENSION_MIMES = {
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroenabled.12",
}

# Firme binarie: OLE2 (vecchi .xls) e ZIP (formato Office Open XML, .xlsx/.xlsm).
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP_MAGIC = b"PK\x03\x04"

# Limiti prudenti per non generare payload enormi verso il modello.
_MAX_ROWS_PER_SHEET = 2000
_MAX_COLS = 64
_MAX_TEXT_CHARS = 200_000


def normalize_mime(filename: str | None, content_type: str | None) -> str:
    """Restituisce un MIME affidabile: se il content_type è generico/assente lo
    deduce dall'estensione del file (utile per .xlsx, spesso inviato come
    octet-stream da alcuni browser)."""
    ct = (content_type or "").strip().lower()
    if ct and ct not in ("application/octet-stream", "binary/octet-stream"):
        return ct
    ext = Path((filename or "").replace("\\", "/")).suffix.lower()
    return _EXTENSION_MIMES.get(ext, ct or "application/octet-stream")


def is_spreadsheet(mime_type: str | None, data: bytes | None = None) -> bool:
    """True se il file è (verosimilmente) un foglio di calcolo Excel."""
    mt = (mime_type or "").lower()
    if mt in _SPREADSHEET_MIMES:
        return True
    if data and data[:8] == _OLE2_MAGIC:
        return True
    return False


def spreadsheet_to_text(data: bytes, mime_type: str | None = None) -> str:
    """Converte un foglio di calcolo in testo leggibile dal modello. Tenta
    prima il formato Office Open XML (xlsx/xlsm via openpyxl) e poi il vecchio
    xls (xlrd). In caso di errore restituisce una nota esplicita."""
    mt = (mime_type or "").lower()
    is_zip = data[: len(_ZIP_MAGIC)] == _ZIP_MAGIC
    is_ole2 = data[:8] == _OLE2_MAGIC

    order = []
    if is_zip or "openxml" in mt or "macroenabled" in mt:
        order = [_xlsx_to_text, _xls_to_text]
    elif is_ole2 or mt == "application/vnd.ms-excel":
        order = [_xls_to_text, _xlsx_to_text]
    else:
        order = [_xlsx_to_text, _xls_to_text]

    for parser in order:
        try:
            text = parser(data)
            if text and text.strip():
                return text[:_MAX_TEXT_CHARS]
        except Exception:
            continue
    return (
        "[Impossibile leggere il foglio di calcolo: formato non riconosciuto o "
        "libreria di lettura non disponibile.]"
    )


def _format_rows(title: str, rows) -> str:
    """Rende un foglio come blocco testuale: titolo + righe tab-separate."""
    out_lines = [f"# Foglio: {title}"]
    count = 0
    for row in rows:
        if count >= _MAX_ROWS_PER_SHEET:
            out_lines.append("… (righe successive omesse)")
            break
        cells = ["" if c is None else str(c) for c in list(row)[:_MAX_COLS]]
        if not any(c.strip() for c in cells):
            continue  # salta righe completamente vuote
        out_lines.append("\t".join(cells))
        count += 1
    return "\n".join(out_lines)


def _xlsx_to_text(data: bytes) -> str:
    import openpyxl  # import lazy: dipendenza opzionale

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    blocks = [
        _format_rows(ws.title, ws.iter_rows(values_only=True)) for ws in wb.worksheets
    ]
    wb.close()
    return "\n\n".join(blocks)


def _xls_to_text(data: bytes) -> str:
    import xlrd  # import lazy: dipendenza opzionale

    book = xlrd.open_workbook(file_contents=data)
    blocks = []
    for sheet in book.sheets():
        rows = (sheet.row_values(r) for r in range(sheet.nrows))
        blocks.append(_format_rows(sheet.name, rows))
    return "\n\n".join(blocks)
