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


def test_dashboard_distinguishes_utilities_and_condominio():
    """Le bollette delle utenze e le spese condominiali sono due categorie
    distinte nella dashboard (etichette pubbliche diverse e non vuote)."""
    from app.services import stats as stats_service

    util = stats_service.BILLS_CATEGORY_UTILITIES
    condo = stats_service.BILLS_CATEGORY_CONDO
    assert util and condo and util != condo


def test_split_total_keys_condominio_separately():
    """_bills_split_total separa il condominio dalle altre utenze, attribuendo
    ogni riga all'uno o all'altro gruppo in base a UtilityType.CONDOMINIO."""
    import asyncio

    from app.enums import UtilityType
    from app.services import stats as stats_service

    # Simula il risultato della query (utility_type, somma, conteggio) senza DB.
    rows = [
        (UtilityType.ENERGIA_ELETTRICA, 100.0, 2),
        (UtilityType.GAS, 50.0, 1),
        (UtilityType.CONDOMINIO, 300.0, 3),
    ]

    class _FakeResult:
        def all(self):
            return rows

    class _FakeDB:
        async def execute(self, _stmt):
            return _FakeResult()

    util_t, util_c, condo_t, condo_c = asyncio.run(
        stats_service._bills_split_total(_FakeDB(), household_id=None)
    )
    assert (util_t, util_c) == (150.0, 3)
    assert (condo_t, condo_c) == (300.0, 3)
