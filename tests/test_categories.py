"""Test delle categorie merceologiche personalizzate (creabili dall'agente o
dall'utente). Livello smoke: niente DB, verifica la logica pura, gli schemi
degli strumenti e la registrazione di endpoint/tool."""


def test_normalize_name_collapses_and_lowercases():
    from app.services.categories import normalize_name

    assert normalize_name("  Abbigliamento   Bimbi ") == "abbigliamento bimbi"
    assert normalize_name("TRASPORTI") == "trasporti"
    assert normalize_name(None) == ""
    assert normalize_name("   ") == ""


def test_normalize_name_truncates_to_100():
    from app.services.categories import normalize_name

    assert len(normalize_name("a" * 200)) == 100


def test_validate_name_rules():
    from app.services.categories import validate_name

    assert validate_name("abbigliamento")[1] is None
    assert validate_name("a")[1] is not None  # troppo corto
    assert validate_name("123")[1] is not None  # senza lettere
    assert validate_name("  ")[1] is not None


def test_is_builtin_and_builtin_catalog():
    from app.enums import SENSITIVE_CATEGORIES
    from app.services.categories import builtin_categories, is_builtin

    assert is_builtin("Bevande") is True
    assert is_builtin("abbigliamento") is False
    cats = builtin_categories()
    names = {c["name"] for c in cats}
    assert "farmaci" in names and "bevande" in names
    farmaci = next(c for c in cats if c["name"] == "farmaci")
    assert farmaci["sensitive"] is True
    assert farmaci["builtin"] is True
    # I farmaci sono marcati sensibili coerentemente con l'enum.
    assert "farmaci" in SENSITIVE_CATEGORIES


def test_clean_examples_filters_and_caps():
    from app.services.categories import _clean_examples

    assert _clean_examples(None) is None
    assert _clean_examples(["", "  "]) is None
    assert _clean_examples([" scarpe ", "giacca"]) == ["scarpe", "giacca"]
    assert len(_clean_examples([str(i) + "x" for i in range(50)])) == 20


def test_builtin_category_info_covers_all_builtins():
    from app.enums import MERCHANDISE_CATEGORIES, MERCHANDISE_CATEGORY_INFO

    for name in MERCHANDISE_CATEGORIES:
        assert name in MERCHANDISE_CATEGORY_INFO, f"manca descrizione per {name}"


def test_create_expense_category_tool_exposed():
    from app.agent.tools import TOOLS

    tool = next(t for t in TOOLS if t["name"] == "create_expense_category")
    assert tool["input_schema"]["required"] == ["name"]
    props = tool["input_schema"]["properties"]
    assert {"name", "description", "examples"} <= set(props)


def test_expense_tools_use_free_category_not_enum():
    from app.agent.tools import TOOLS

    for tool_name in ("add_expenses", "record_expense"):
        tool = next(t for t in TOOLS if t["name"] == tool_name)
        if tool_name == "add_expenses":
            cat = tool["input_schema"]["properties"]["lines"]["items"]["properties"]["merch_category"]
        else:
            cat = tool["input_schema"]["properties"]["merch_category"]
        assert cat["type"] == "string"
        assert "enum" not in cat


def test_category_endpoints_registered():
    from app.api import household

    paths = {getattr(r, "path", None) for r in household.router.routes}
    assert "/household/categories" in paths
    assert "/household/categories/{category_id}" in paths


def test_system_prompt_mentions_category_creation():
    from app.agent.system_prompt import SYSTEM_PROMPT

    assert "create_expense_category" in SYSTEM_PROMPT
    assert "CATEGORIE NOTE" in SYSTEM_PROMPT


def test_migration_chain_includes_categories():
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parent.parent
        / "alembic" / "versions" / "0006_custom_categories.py"
    )
    spec = importlib.util.spec_from_file_location("mig_0006", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.down_revision == "0005_condo_units"
    assert mod.revision == "0006_custom_categories"
