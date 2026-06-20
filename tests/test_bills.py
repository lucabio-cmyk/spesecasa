"""Test della feature bollette/spese di casa (riconoscimento, costi, amministrazione).
Livello smoke: niente DB, verifica enum, schemi tool e mapping."""

from datetime import date


def test_utility_and_status_enums():
    from app.enums import BillStatus, DocumentType, UtilityType

    assert "bolletta" in [d.value for d in DocumentType]
    assert {"energia_elettrica", "gas", "acqua", "rifiuti"} <= {u.value for u in UtilityType}
    assert {"da_pagare", "pagata", "scaduta"} <= {s.value for s in BillStatus}


def test_bill_tools_exposed():
    from app.agent.tools import TOOLS

    names = {t.get("name") for t in TOOLS}
    assert {"save_bill", "record_bill", "query_bills"} <= names


def test_query_bills_schema_uses_enum():
    from app.agent.tools import TOOLS
    from app.enums import UtilityType

    tool = next(t for t in TOOLS if t["name"] == "query_bills")
    enum = tool["input_schema"]["properties"]["utility_type"]["enum"]
    assert set(enum) == {u.value for u in UtilityType}


def test_system_prompt_covers_bills():
    from app.agent.system_prompt import SYSTEM_PROMPT

    for kw in ("BOLLETTE", "save_bill", "scadenz", "consumo", "query_bills"):
        assert kw in SYSTEM_PROMPT


def test_default_units_for_metered_utilities():
    from app.enums import UTILITY_DEFAULT_UNIT

    assert UTILITY_DEFAULT_UNIT["energia_elettrica"] == "kWh"
    assert UTILITY_DEFAULT_UNIT["gas"] == "Smc"
    assert UTILITY_DEFAULT_UNIT["acqua"] == "m³"


def test_expense_management_tools_exposed():
    from app.agent.tools import TOOLS

    names = {t.get("name") for t in TOOLS}
    assert {"find_expenses", "delete_expense"} <= names


def test_delete_expense_requires_id():
    from app.agent.tools import TOOLS

    tool = next(t for t in TOOLS if t["name"] == "delete_expense")
    assert tool["input_schema"]["required"] == ["expense_id"]


def test_system_prompt_covers_deletion():
    from app.agent.system_prompt import SYSTEM_PROMPT

    for kw in ("CANCELLAZIONE", "find_expenses", "delete_expense", "IRREVERSIBILE"):
        assert kw in SYSTEM_PROMPT


def test_fiscal_year_derivation_prefers_period_end():
    from app.api.bills import _derive_fiscal_year
    from app.models.bill import Bill

    b = Bill(period_end=date(2025, 3, 1), issue_date=date(2024, 12, 1))
    assert _derive_fiscal_year(b) == 2025

    b2 = Bill(due_date=date(2026, 1, 15))
    assert _derive_fiscal_year(b2) == 2026
