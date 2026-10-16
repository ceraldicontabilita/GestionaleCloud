"""Checklist commercialista: dati esistenti, incompleti e mancanti."""
import asyncio

from app.services.checklist_commercialista import ESISTENTE, INCOMPLETO, MANCANTE, genera_checklist
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(setup=None):
    async def scenario():
        db = ClientArchivioMemoria()["checklist-commercialista"]
        if setup:
            await setup(db)
        return await genera_checklist(db, 2026, dal="2026-01-01", al="2026-12-31")
    return asyncio.run(scenario())


def _item(result, key):
    return next(item for item in result["items"] if item["key"] == key)


def test_senza_fonti_chiede_i_documenti_mancanti():
    result = _run()
    assert _item(result, "dichiarazioni")["stato"] == MANCANTE
    assert _item(result, "f24")["stato"] == MANCANTE
    assert result["riepilogo"][MANCANTE] > 0


def test_f24_solo_modello_e_incompleto_non_pagato():
    async def setup(db):
        await db["f24_unificato"].insert_one({"id": "f1", "anno": 2026})
    result = _run(setup)
    f24 = _item(result, "f24")
    assert f24["stato"] == INCOMPLETO
    assert f24["parti"] == {"presenti": 1, "totali": 2}
    assert "prove distinte" in f24["nota"]


def test_f24_modello_e_quietanza_sono_esistenti():
    async def setup(db):
        await db["f24_unificato"].insert_one({"id": "f1", "anno": 2026})
        await db["quietanze_f24"].insert_one({"id": "q1", "anno": 2026})
    result = _run(setup)
    assert _item(result, "f24")["stato"] == ESISTENTE


def test_drive_da_verificare_non_diventa_dato_esistente():
    async def setup(db):
        await db["drive_cartella_unica"].insert_one({
            "id": "d1", "nome": "Dichiarazione redditi 2026.pdf",
            "tipo": "dichiarazione_fiscale", "cartella": "DA VERIFICARE", "esito": "errore",
        })
    result = _run(setup)
    item = _item(result, "dichiarazioni")
    assert item["stato"] == INCOMPLETO
    assert any(f["tipo"] == "attenzione" for f in item["fonti"])
