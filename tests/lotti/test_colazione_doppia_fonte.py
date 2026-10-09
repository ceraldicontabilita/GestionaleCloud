import asyncio

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import colazione as col
from app.lotti.servizi import lotto_acquaviva as la

RICETTA = "8e21c0a8-4103-5119-9c9b-0b33f6da2b2a"


def _db(monkeypatch, nome):
    db = AsyncMongoMockClient()[nome]
    monkeypatch.setattr(col, "db", db)
    monkeypatch.setattr(la, "db", db)
    return db


async def _prepara(db):
    await db.colazione_coppie.insert_one({
        "id": "c1", "nome": "Graffa Napoletana", "ricetta_id": RICETTA,
        "acquaviva_ids": ["906fcfa8"], "acquaviva_nome": "Ciambella maxi zuccherata 100 g"})
    await db.colazione_template.insert_one({
        "nome": "Estiva", "items": [{"prodotto_id": RICETTA, "prodotto_nome": "Graffa Napoletana",
                                      "pezzi": 6, "attivo": True}]})
    await db.fatture.insert_one({
        "id": "f1", "numero_fattura": "923284", "data_fattura": "16/12/2025",
        "fornitore": "Dolciaria Acquaviva S.p.A."})


def test_senza_scelta_non_registra(monkeypatch):
    db = _db(monkeypatch, "col_df_1")

    async def prova():
        await _prepara(db)
        r = await col.registra_colazione({"nome": "Estiva"})
        assert r["prodotti_registrati"] == 0 and "Scegli prima" in r["errori"][0]["errore"]
        assert await db.vendite_banco.count_documents({}) == 0
    asyncio.run(prova())


def test_acquaviva_crea_lotto_da_fattura_e_nostra_produzione_il_lotto_normale(monkeypatch):
    db = _db(monkeypatch, "col_df_2")

    async def prova():
        await _prepara(db)
        await col.scegli_fonte({"coppia_id": "c1", "fonte": "acquaviva"})
        r = await col.registra_colazione({"nome": "Estiva"})
        reg = r["registrati"][0]
        assert reg["nome"] == "Ciambella maxi zuccherata 100 g" and reg["origine_prodotto"] == "acquaviva"
        assert reg["lotto_id"].startswith("CIAMBELLA-MAXI-ZUCCHERATA-") and reg["lotto_id"].endswith("-923284")
        assert (await db.lotti_fornitori.find_one({"numero_lotto": reg["lotto_id"]}))["origine"] == "automatico_acquaviva"
        await col.scegli_fonte({"coppia_id": "c1", "fonte": "casa"})
        r2 = await col.registra_colazione({"nome": "Estiva"})
        reg2 = r2["registrati"][0]
        assert reg2["nome"] == "Graffa Napoletana" and reg2["lotto_id"].startswith("COL-") and reg2["origine_prodotto"] == "casa"
    asyncio.run(prova())


def test_fonte_non_valida_e_coppia_sconosciuta(monkeypatch):
    db = _db(monkeypatch, "col_df_3")

    async def prova():
        await _prepara(db)
        with pytest.raises(HTTPException) as e1:
            await col.scegli_fonte({"coppia_id": "c1", "fonte": "boh"})
        assert e1.value.status_code == 400
        with pytest.raises(HTTPException) as e2:
            await col.scegli_fonte({"coppia_id": "zz", "fonte": "casa"})
        assert e2.value.status_code == 404
    asyncio.run(prova())
