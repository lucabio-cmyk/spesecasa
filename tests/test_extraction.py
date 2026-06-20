"""Test dell'estrazione documentale arricchita e della rilettura degli originali
(read_document). Livello smoke: niente DB, verifica schemi tool, helper e prompt."""


def test_read_document_tool_exposed():
    from app.agent.tools import TOOLS

    tool = next((t for t in TOOLS if t.get("name") == "read_document"), None)
    assert tool is not None
    # document_id opzionale (durante l'upload si rilegge il documento corrente)
    assert "document_id" in tool["input_schema"]["properties"]
    assert "required" not in tool["input_schema"]


def test_file_to_content_block_picks_right_type():
    from app.agent.tools import file_to_content_block

    pdf = file_to_content_block("application/pdf", b"data")
    assert pdf["type"] == "document"
    img = file_to_content_block("image/png", b"data")
    assert img["type"] == "image"
    # fallback prudente per mime sconosciuti
    other = file_to_content_block("application/octet-stream", b"data")
    assert other["type"] == "document"


def test_save_document_schema_has_richer_fields():
    from app.agent.tools import TOOLS

    tool = next(t for t in TOOLS if t["name"] == "save_document")
    props = tool["input_schema"]["properties"]
    expected = {
        "issuer_vat",
        "recipient_name",
        "recipient_fiscal_code",
        "taxable_amount",
        "vat_amount",
        "currency",
        "due_date",
        "payment_traceability",
        "tags",
        "details",
    }
    assert expected <= set(props)
    assert props["details"]["type"] == "object"


def test_expense_tools_have_unit_price_and_details():
    from app.agent.tools import TOOLS

    add = next(t for t in TOOLS if t["name"] == "add_expenses")
    line_props = add["input_schema"]["properties"]["lines"]["items"]["properties"]
    assert {"unit_price", "details"} <= set(line_props)

    rec = next(t for t in TOOLS if t["name"] == "record_expense")
    assert {"unit_price", "details"} <= set(rec["input_schema"]["properties"])


def test_document_model_has_new_columns():
    from app.models.document import Document

    for col in (
        "issuer_vat",
        "recipient_name",
        "recipient_fiscal_code",
        "taxable_amount",
        "vat_amount",
        "currency",
        "due_date",
        "payment_traceability",
        "tags",
        "details",
    ):
        assert hasattr(Document, col)


def test_expense_model_has_new_columns():
    from app.models.expense import Expense

    assert hasattr(Expense, "unit_price")
    assert hasattr(Expense, "details")


def test_document_out_exposes_new_fields():
    from app.schemas.document import DocumentOut

    fields = set(DocumentOut.model_fields)
    assert {"issuer_vat", "taxable_amount", "vat_amount", "due_date", "tags", "details"} <= fields


def test_expense_out_exposes_new_fields():
    from app.schemas.expense import ExpenseOut

    fields = set(ExpenseOut.model_fields)
    assert {"unit_price", "details"} <= fields


def test_system_prompt_covers_richer_extraction_and_reread():
    from app.agent.system_prompt import SYSTEM_PROMPT

    for kw in ("read_document", "RILETTURA", "details", "tags", "tracciabilità"):
        assert kw in SYSTEM_PROMPT
