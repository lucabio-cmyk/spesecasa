"""Test del retry resiliente sulle chiamate Anthropic (gestione 529 Overloaded).

Non richiede il pacchetto `anthropic`: la rilevabilità degli errori transitori è
duck-typed (status_code / nome classe), così il wrapper è testabile in isolamento.
"""

import asyncio

import pytest

from app.services import llm


class _FakeOverloaded(Exception):
    """Simula anthropic.APIStatusError 529 (overloaded_error)."""

    status_code = 529


class _FakeBadRequest(Exception):
    """Simula un 400: NON deve essere ritentato."""

    status_code = 400


class APIConnectionError(Exception):
    """Stesso nome dell'eccezione SDK: deve essere riconosciuta come transitoria."""


class _FakeClient:
    def __init__(self, errors: list[Exception], result="ok"):
        self._errors = list(errors)
        self._result = result
        self.calls = 0
        self.messages = self  # client.messages.create -> self.create

    async def create(self, **kwargs):
        self.calls += 1
        if self._errors:
            raise self._errors.pop(0)
        return self._result


def test_is_overloaded_detects_529():
    assert llm.is_overloaded(_FakeOverloaded()) is True
    assert llm.is_overloaded(_FakeBadRequest()) is False


def test_is_retryable_classification():
    assert llm.is_retryable(_FakeOverloaded()) is True
    assert llm.is_retryable(APIConnectionError()) is True
    assert llm.is_retryable(_FakeBadRequest()) is False


def test_retries_then_succeeds(monkeypatch):
    # Niente attese reali nei test.
    async def _no_sleep(*_):
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(llm.settings, "anthropic_retry_attempts", 5)
    client = _FakeClient([_FakeOverloaded(), _FakeOverloaded()], result="done")
    out = asyncio.run(llm.create_message(client, model="x"))
    assert out == "done"
    assert client.calls == 3  # due fallimenti + successo


def test_non_retryable_raises_immediately(monkeypatch):
    async def _no_sleep(*_):
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", _no_sleep)
    client = _FakeClient([_FakeBadRequest()])
    with pytest.raises(_FakeBadRequest):
        asyncio.run(llm.create_message(client, model="x"))
    assert client.calls == 1  # nessun retry


def test_exhausts_attempts_and_raises(monkeypatch):
    async def _no_sleep(*_):
        return None

    monkeypatch.setattr(llm.asyncio, "sleep", _no_sleep)
    monkeypatch.setattr(llm.settings, "anthropic_retry_attempts", 3)
    client = _FakeClient([_FakeOverloaded()] * 5)
    with pytest.raises(_FakeOverloaded):
        asyncio.run(llm.create_message(client, model="x"))
    assert client.calls == 3  # tentativi esauriti
