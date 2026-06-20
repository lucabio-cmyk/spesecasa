"""Test del supporto ai fogli di calcolo (upload Excel) e della distinzione
bollette/condominio nella dashboard. Livello smoke: niente DB."""

import io


def _make_xlsx() -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Spese"
    ws.append(["Data", "Descrizione", "Importo"])
    ws.append(["2025-01-10", "Farmacia", 23.50])
    ws.append([None, None, None])  # riga vuota: deve essere saltata
    ws.append(["2025-02-03", "Supermercato", 81.20])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_normalize_mime_from_extension():
    from app.services.spreadsheets import normalize_mime

    # browser che invia octet-stream: deduciamo dall'estensione
    mt = normalize_mime("estratto.xlsx", "application/octet-stream")
    assert mt == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert normalize_mime("vecchio.xls", "") == "application/vnd.ms-excel"
    # content_type valido: lo si conserva
    assert normalize_mime("foto.png", "image/png") == "image/png"


def test_is_spreadsheet_detection():
    from app.services.spreadsheets import is_spreadsheet

    assert is_spreadsheet("application/vnd.ms-excel") is True
    assert is_spreadsheet(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ) is True
    assert is_spreadsheet("application/pdf") is False
    assert is_spreadsheet("image/png") is False


def test_xlsx_converted_to_text():
    from app.services.spreadsheets import spreadsheet_to_text

    text = spreadsheet_to_text(
        _make_xlsx(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert "Foglio: Spese" in text
    assert "Farmacia" in text
    assert "Supermercato" in text
    # le righe completamente vuote non compaiono come righe a sé
    assert "\n\t\t\n" not in text


def test_file_to_content_block_handles_spreadsheet():
    from app.agent.tools import file_to_content_block

    block = file_to_content_block(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        _make_xlsx(),
    )
    assert block["type"] == "document"
    assert block["source"]["type"] == "text"
    assert "Farmacia" in block["source"]["data"]


def test_overview_splits_utilities_and_condominio():
    """Verifica che lo split utenze/condominio usi UtilityType.CONDOMINIO."""
    import inspect

    from app.services import bills as bills_service

    src = inspect.getsource(bills_service.overview)
    assert "condo_total" in src
    assert "utilities_total" in src
    assert "CONDOMINIO" in src
