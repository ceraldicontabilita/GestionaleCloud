"""P1 §6.8 — cash.py come ADAPTER verso la canonica `prima_nota_cassa`
(Collections.CASH_MOVEMENTS = "prima_nota_cassa"): il movimento cassa creato dal
vecchio endpoint /api/cash scrive ANCHE i campi canonici italiani (tipo/importo/data/
status/anno), così è visto dal saldo Prima Nota. Nessuna doppia scrittura su altra
collezione."""
import asyncio
from datetime import date

from app.services.cash_service import CashService
from app.models.cash import CashMovementCreate


class _FakeRepo:
    def __init__(self):
        self.creato = None

    async def create(self, doc):
        self.creato = dict(doc)
        return "movimento-1"


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_create_movement_scrive_campi_canonici():
    repo = _FakeRepo()
    svc = CashService(repo, corrispettivo_repo=object())
    dati = CashMovementCreate(
        date=date(2026, 3, 15), time="10:30", type="entrata", amount=120.0,
        description="Incasso bar", category="Corrispettivi",
    )
    mid = _run(svc.create_movement(dati, user_id="u1"))
    assert mid == "movimento-1"
    doc = repo.creato
    # campi canonici prima_nota_cassa (letti dal saldo)
    assert doc["tipo"] == "entrata"
    assert doc["importo"] == 120.0
    assert doc["data"] == "2026-03-15"
    assert doc["status"] == "attivo"
    assert doc["anno"] == 2026
    assert doc["categoria"] == "Corrispettivi"
    assert doc["descrizione"] == "Incasso bar"
    assert doc["fonte"] == "cash_adapter"
    # campi originali inglesi mantenuti (retro-compatibilità)
    assert doc["type"] == "entrata" and doc["amount"] == 120.0
