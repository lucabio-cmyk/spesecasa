"""Test delle analisi avanzate (andamento mensile, top esercenti, confronto
anni, insight automatici). Livello smoke: niente DB, verifica la logica pura e
la registrazione degli endpoint."""


def test_pct_change_handles_zero_base():
    from app.services.stats import _pct_change

    assert _pct_change(150, 100) == 50.0
    assert _pct_change(50, 100) == -50.0
    assert _pct_change(100, 0) is None
    assert _pct_change(0, 0) is None


def test_month_labels_cover_year():
    from app.services.stats import MONTH_LABELS

    assert len(MONTH_LABELS) == 13  # indice 0 segnaposto + 12 mesi
    assert MONTH_LABELS[1] == "Gen"
    assert MONTH_LABELS[12] == "Dic"


def _empty_upcoming():
    return {"overdue": [], "due_soon": [], "open_count": 0, "open_total": 0.0}


def test_insights_flags_spending_increase():
    from app.services.stats import _compute_insights

    comparison = {
        "year": 2026,
        "previous_year": 2025,
        "current_total": 1200.0,
        "previous_total": 1000.0,
        "delta": 200.0,
        "delta_pct": 20.0,
        "by_category": [
            {"category": "bevande", "current": 400.0, "previous": 200.0,
             "delta": 200.0, "delta_pct": 100.0},
        ],
    }
    overview = {"deductible_total": 0, "to_review": 0}
    categories = [{"category": "bevande", "total": 400.0, "count": 5}]
    fiscal = []
    insights = _compute_insights(2026, overview, comparison, categories, fiscal, _empty_upcoming())

    titles = " ".join(i["title"] for i in insights)
    assert "aumento" in titles
    assert any(i["severity"] == "warning" for i in insights)
    # La voce cresciuta di più viene segnalata.
    assert "bevande" in titles.lower()


def test_insights_flags_overdue_bills_and_fiscal():
    from app.services.stats import _compute_insights

    comparison = {
        "year": 2026, "previous_year": 2025,
        "current_total": 500.0, "previous_total": 500.0, "delta": 0.0,
        "delta_pct": 0.0, "by_category": [],
    }
    overview = {"deductible_total": 320.0, "to_review": 2}
    categories = [{"category": "farmaci", "total": 320.0, "count": 3}]
    fiscal = [{"classification": "da_verificare", "total": 80.0, "count": 1}]
    upcoming = {
        "overdue": [{"total_amount": 90.0}],
        "due_soon": [], "open_count": 1, "open_total": 90.0,
    }
    insights = _compute_insights(2026, overview, comparison, categories, fiscal, upcoming)
    sev = {i["severity"] for i in insights}
    titles = " ".join(i["title"] for i in insights).lower()
    assert "positive" in sev  # potenziale agevolabile
    assert "scadut" in titles  # bolletta scaduta
    assert "verificare" in titles  # classificazione da verificare
    assert "rivedere" in titles  # documenti da rivedere


def test_insights_never_empty():
    from app.services.stats import _compute_insights

    comparison = {"year": 2026, "previous_year": 2025, "current_total": 0.0,
                  "previous_total": 0.0, "delta": 0.0, "delta_pct": None,
                  "by_category": []}
    insights = _compute_insights(2026, {"deductible_total": 0, "to_review": 0},
                                 comparison, [], [], _empty_upcoming())
    assert len(insights) >= 1


def test_new_stats_endpoints_registered():
    from app.api import bills, stats

    stats_paths = {getattr(r, "path", None) for r in stats.router.routes}
    assert {"/stats/monthly", "/stats/top-merchants", "/stats/compare",
            "/stats/insights"} <= stats_paths
    bills_paths = {getattr(r, "path", None) for r in bills.router.routes}
    assert "/bills/monthly" in bills_paths


def test_bills_cost_analysis_exposes_comparison_helpers():
    from app.services.bills import _pct_change, cost_analysis, monthly  # noqa: F401

    assert _pct_change(120, 100) == 20.0
    assert _pct_change(10, 0) is None


def test_get_insights_tool_exposed():
    from app.agent.tools import TOOLS

    names = {t["name"] for t in TOOLS}
    assert "get_insights" in names


def test_query_expenses_tool_has_analysis_flags():
    from app.agent.tools import TOOLS

    tool = next(t for t in TOOLS if t["name"] == "query_expenses")
    props = tool["input_schema"]["properties"]
    assert {"include_monthly", "include_top_merchants", "include_comparison"} <= set(props)


def test_system_prompt_mentions_insights():
    from app.agent.system_prompt import SYSTEM_PROMPT

    assert "get_insights" in SYSTEM_PROMPT
