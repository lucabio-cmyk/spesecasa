"""Test dell'integrazione dei FARMACI: categoria dedicata, ricerca del codice
AIC/minsan online (prompt) e visualizzazione riservata agli amministratori.
Livello smoke: niente DB, verifica enum, dipendenze, rotte, contesto agente e
system prompt."""

import asyncio
import inspect
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def test_farmaci_category_and_sensitive():
    from app.enums import MERCHANDISE_CATEGORIES, SENSITIVE_CATEGORIES

    assert "farmaci" in MERCHANDISE_CATEGORIES
    # distinta dalla parafarmacia da supermercato (articoli non medicinali)
    assert "parafarmacia da supermercato" in MERCHANDISE_CATEGORIES
    assert "farmaci" in SENSITIVE_CATEGORIES


def test_require_admin_dependency():
    from app.deps import require_admin
    from app.enums import UserRole

    admin = SimpleNamespace(role=UserRole.ADMIN)
    member = SimpleNamespace(role=UserRole.MEMBER)

    assert asyncio.run(require_admin(admin)) is admin
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_admin(member))
    assert exc.value.status_code == 403


def _dependency_calls(dependant):
    """Raccoglie ricorsivamente le funzioni di dipendenza di una rotta."""
    calls = []
    for dep in dependant.dependencies:
        if dep.call is not None:
            calls.append(dep.call)
        calls.extend(_dependency_calls(dep))
    return calls


def test_farmaci_endpoint_registered_and_admin_only():
    from app.api import expenses
    from app.deps import require_admin

    route = next(
        (
            r
            for r in expenses.router.routes
            if getattr(r, "path", None) == "/expenses/farmaci"
            and "GET" in getattr(r, "methods", set())
        ),
        None,
    )
    assert route is not None, "rotta GET /expenses/farmaci non registrata"
    assert require_admin in _dependency_calls(route.dependant)


def test_agent_context_has_is_admin_default_true():
    from app.agent.tools import AgentContext

    ctx = AgentContext(household_id=uuid.uuid4(), user_id=uuid.uuid4())
    assert ctx.is_admin is True
    ctx_member = AgentContext(
        household_id=uuid.uuid4(), user_id=uuid.uuid4(), is_admin=False
    )
    assert ctx_member.is_admin is False


def test_chat_runner_accepts_is_admin():
    from app.agent.runner import chat

    assert "is_admin" in inspect.signature(chat).parameters


def test_system_prompt_covers_farmaci_and_codes():
    from app.agent.system_prompt import SYSTEM_PROMPT

    for kw in (
        "FARMACI",
        "scontrino parlante",
        "AIC",
        "minsan",
        "principio_attivo",
        "web_search",
        "RISERVATEZZA",
        "AMMINISTRATORI",
    ):
        assert kw in SYSTEM_PROMPT, f"manca '{kw}' nel system prompt"


def test_find_expenses_tool_lists_farmaci_category():
    from app.agent.tools import TOOLS

    tool = next(t for t in TOOLS if t["name"] == "find_expenses")
    assert "farmaci" in tool["input_schema"]["properties"]["category"]["enum"]
