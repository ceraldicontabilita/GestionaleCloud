"""La risposta dell'AI si aspetta fuori dal loop del server.

``send_message`` era ``async`` ma chiamava l'SDK sincrono: 13-38 s di attesa
(import compreso) in cui nemmeno ``/api/health`` rispondeva, e Render
riavviava l'istanza.
"""
import asyncio
import time
from types import SimpleNamespace

from app.services.anthropic_llm_client import LlmChat, UserMessage


def test_la_chiamata_all_ai_non_ferma_il_loop(monkeypatch):
    def crea(**_kwargs):
        time.sleep(0.4)
        return SimpleNamespace(content=[SimpleNamespace(text="ok")])

    cliente = SimpleNamespace(messages=SimpleNamespace(create=crea))
    monkeypatch.setattr(LlmChat, "_cliente", lambda self: cliente)

    async def scenario():
        battiti = 0

        async def battito():
            nonlocal battiti
            while True:
                await asyncio.sleep(0.02)
                battiti += 1

        tic = asyncio.create_task(battito())
        risposta = await LlmChat(api_key="x").send_message(UserMessage(content="ciao"))
        tic.cancel()
        return risposta, battiti

    risposta, battiti = asyncio.run(scenario())
    assert risposta == "ok"
    assert battiti >= 5


def test_creare_la_chat_non_importa_l_sdk():
    """L'import dell'SDK avviene nel thread della chiamata, non sul loop."""
    chat = LlmChat(api_key="x")
    assert chat._client is None
