"""Test della gestione condominio: unità immobiliari, addestramento agente,
analisi verbali di assemblea. Livello smoke: niente DB, verifica enum, schemi
tool, prompt e schemi Pydantic."""


def test_verbale_assemblea_doctype_exists():
    from app.enums import DocumentType

    assert "verbale_assemblea" in [d.value for d in DocumentType]


def test_list_property_units_tool_exposed():
    from app.agent.tools import TOOLS

    names = {t.get("name") for t in TOOLS}
    assert "list_property_units" in names


def test_save_bill_accepts_property_unit_and_details():
    from app.agent.tools import TOOLS

    for tool_name in ("save_bill", "record_bill"):
        tool = next(t for t in TOOLS if t["name"] == tool_name)
        props = tool["input_schema"]["properties"]
        assert "property_unit" in props
        assert "details" in props


def test_query_bills_supports_property_unit_filter():
    from app.agent.tools import TOOLS

    tool = next(t for t in TOOLS if t["name"] == "query_bills")
    assert "property_unit" in tool["input_schema"]["properties"]


def test_system_prompt_covers_condominio_and_verbali():
    from app.agent.system_prompt import SYSTEM_PROMPT

    for kw in (
        "CONDOMINIO",
        "VERBALI DI ASSEMBLEA",
        "list_property_units",
        "property_unit",
        "millesimi",
        "straordinari",
    ):
        assert kw in SYSTEM_PROMPT


def test_property_unit_model_fields():
    from app.models.property_unit import PropertyUnit

    cols = set(PropertyUnit.__table__.columns.keys())
    assert {
        "name",
        "aliases",
        "owner_name",
        "condominium_name",
        "millesimi",
        "is_primary",
        "household_id",
    } <= cols


def test_household_has_agent_instructions():
    from app.models.household import Household

    assert "agent_instructions" in Household.__table__.columns.keys()


def test_bill_links_to_property_unit():
    from app.models.bill import Bill

    cols = set(Bill.__table__.columns.keys())
    assert {"property_unit_id", "details"} <= cols


def test_property_unit_schema_roundtrip():
    from app.schemas.property_unit import PropertyUnitCreate

    u = PropertyUnitCreate(name="Casa Roma", aliases="int. 5, scala B", is_primary=True)
    assert u.name == "Casa Roma"
    assert u.is_primary is True
