"""Fase 0 (PROMPT_CLAUDE_CODE_FASE_0.md): endpoint che scrivevano scritture
contabili automatiche non provate ora rifiutano la richiesta con 409, senza
eseguire alcuna logica successiva. Un test per punto del prompt.
"""
import asyncio
import inspect

import pytest
from fastapi import HTTPException


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_punto1_auto_conferma_provvisori_per_metodo_cancellato():
    """Non piu' spento: tolto, e con lui la rotta e il suo unico chiamante.

    Confermava un pagamento in cassa sul solo metodo dichiarato in anagrafica
    fornitore. Dal 15/09/2026 rispondeva 409 — ma non era un bottone e basta:
    `suppliers_module/base.py` lo chiamava davvero a ogni cambio di metodo, in
    un task di sfondo avvolto in `except Exception`. Il 409 finiva li' dentro e
    non lo vedeva nessuno.

    Resta `annulla_auto_conferma`, che non e' la stessa cosa: serve a disfare i
    movimenti che quella funzione aveva gia' scritto e che in archivio ci sono
    ancora.
    """
    from app.routers.prima_nota_module import sync as mod
    from app.routers.suppliers_module import base

    assert not hasattr(mod, "auto_conferma_provvisori_per_metodo")
    assert hasattr(mod, "annulla_auto_conferma"), (
        "il rollback dei movimenti gia' scritti deve restare"
    )
    assert "auto_conferma_provvisori_per_metodo" not in inspect.getsource(base)


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
