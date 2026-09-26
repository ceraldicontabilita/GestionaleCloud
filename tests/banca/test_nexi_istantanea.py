"""La Prima Nota Banca legge l'ultima verifica Nexi salvata, non la ricalcola a ogni apertura."""
import asyncio

import app.services.alert_engine as alert_engine
from app.services import nexi_carta
from app.services.archivio_documenti_memoria import ArchivioDocumenti


def _senza_avvisi(monkeypatch):
    async def genera(*a, **k):
        return {"id": "a"}

    async def risolvi(*a, **k):
        return 0

    monkeypatch.setattr(alert_engine, "genera_alert", genera)
    monkeypatch.setattr(alert_engine, "risolvi_alert", risolvi)


def _db_con_addebiti():
    db = ArchivioDocumenti("test")

    async def semina():
        await db["estratto_conto_movimenti"].insert_many([
            {"id": "e25", "data": "2025-11-05", "tipo": "uscita", "importo": 80.0,
             "descrizione": "ADDEBITO SDD NEXI"},
            {"id": "e26a", "data": "2026-04-05", "tipo": "uscita", "importo": 320.5,
             "descrizione": "ADDEBITO SDD NEXI"},
            {"id": "e26b", "data": "2026-05-05", "tipo": "uscita", "importo": 10.0,
             "descrizione": "ADDEBITO SDD NEXI"},
            {"id": "c1", "data": "2026-04-10", "tipo": "carta_credito", "banca": "Nexi", "importo": 10.0},
        ])

    asyncio.run(semina())
    return db


def test_la_verifica_di_un_anno_dall_istantanea_e_quella_calcolata(monkeypatch):
    _senza_avvisi(monkeypatch)
    diretta = asyncio.run(nexi_carta.verifica_addebiti_nexi(_db_con_addebiti(), anno=2026))
    tutti = asyncio.run(nexi_carta.verifica_addebiti_nexi(_db_con_addebiti()))
    ricavata = nexi_carta.filtra_verifica_per_anno(tutti, 2026)
    assert ricavata["dettagli"] == diretta["dettagli"]
    for chiave in ("addebiti_trovati", "estratti_mancanti", "riconciliati", "non_quadrano"):
        assert ricavata[chiave] == diretta[chiave], chiave
    assert ricavata["addebiti_trovati"] == 2
    # I duplicati non si attribuiscono a un anno: vuoto, non inventato.
    assert ricavata["duplicati_ignorati"] is None


def test_la_lettura_usa_l_istantanea_e_non_ricalcola(monkeypatch):
    _senza_avvisi(monkeypatch)
    db = _db_con_addebiti()
    prima = asyncio.run(nexi_carta.leggi_verifica_nexi(db, anno=2026))
    assert prima["addebiti_trovati"] == 2 and prima["calcolata_at"]

    chiamate = []

    async def verifica_contata(*a, **k):
        chiamate.append(1)
        return {}

    monkeypatch.setattr(nexi_carta, "verifica_addebiti_nexi", verifica_contata)
    seconda = asyncio.run(nexi_carta.leggi_verifica_nexi(db, anno=2026))
    assert chiamate == []
    assert seconda["dettagli"] == prima["dettagli"]
    assert seconda["calcolata_at"] == prima["calcolata_at"]
