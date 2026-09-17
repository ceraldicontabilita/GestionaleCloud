"""Contratti del provider OpenAI della chat.

I test non chiamano la rete e non contengono chiavi reali: verificano solo la
selezione provider, l'adattamento degli strumenti e il fallback sicuro quando
il client restituisce testo.
"""
import asyncio
import sys
import types

from app.services import chat_ai_engine as chat


def test_openai_env_e_preferito_ad_anthropic(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic")
    info = asyncio.run(chat.risolvi_provider())
    assert info["provider"] == "openai"
    assert info["source"] == "env"
    assert info["api_key"] == "sk-test-openai"


def test_openai_schema_riusa_tutti_gli_executor():
    schema = chat._openai_tools_schema()
    names = {item["function"]["name"] for item in schema}
    assert "componi_risposta" in names
    assert names - {"componi_risposta"} <= set(chat._TOOL_EXECUTORS)
    assert all(item["type"] == "function" for item in schema)


def test_openai_loop_non_scrive_e_accetta_risposta_testuale(monkeypatch):
    class _Message:
        content = "Risposta di prova basata sui dati consultabili."
        tool_calls = None

    class _Completions:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=_Message())])

    completions = _Completions()
    fake_module = types.ModuleType("openai")
    fake_module.AsyncOpenAI = lambda api_key: types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=completions)
    )
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    result = asyncio.run(chat._rispondi_openai(
        "Qual e' la situazione?", "session-test", db=None, api_key="sk-test"
    ))

    assert result["risposta_testuale"].startswith("Risposta di prova")
    assert result["motore"] == "ai"
    assert completions.calls[0]["model"] == "gpt-test"
    assert completions.calls[0]["tools"]
