"""Fase 0 (PROMPT_CLAUDE_CODE_FASE_0.md): endpoint che scrivevano scritture
contabili automatiche non provate ora rifiutano la richiesta con 409, senza
eseguire alcuna logica successiva. Un test per punto del prompt.
"""
import asyncio

import pytest
from fastapi import HTTPException


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_punto1_auto_conferma_provvisori_per_metodo_disattivato():
    from app.routers.prima_nota_module import sync as mod

    with pytest.raises(HTTPException) as exc_info:
        _run(mod.auto_conferma_provvisori_per_metodo(anno=2026))

    assert exc_info.value.status_code == 409


def test_punto7_rebuild_prima_nota_disattivato():
    from app.routers.invoices import corrispettivi as mod

    with pytest.raises(HTTPException) as exc_info:
        _run(mod.rebuild_prima_nota(anno=2026, _admin={}))

    assert exc_info.value.status_code == 409


def test_punto10_rapido_paga_fattura_disattivato():
    from app.routers import rapido as mod

    with pytest.raises(HTTPException) as exc_info:
        _run(mod.rapido_paga_fattura(invoice_id="FT-1", metodo_pagamento="cassa", importo=100))

    assert exc_info.value.status_code == 409
