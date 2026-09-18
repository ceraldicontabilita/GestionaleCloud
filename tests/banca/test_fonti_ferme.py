"""18/09/2026: Prima Nota banca mostrava solo attese SumUp «da verificare» e
un saldo a -186.866,90. Nessuna logica rotta: dal 24/08 non arrivava piu'
nessun documento e il sistema non lo diceva. Qui il silenzio diventa avviso."""
import asyncio
from datetime import date

from app.services import fonti_ferme
from app.services.sheets_document_store import MemorySheetsClient


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db(nome="fonti"):
    return MemorySheetsClient()[nome]


def _popola(db, estratto="2026-08-24", corrispettivi="2026-08-24", pos="2026-07-31"):
    async def scenario():
        if estratto:
            await db["estratto_conto_movimenti"].insert_one(
                {"id": "ec-1", "data": estratto, "importo": 10.0})
        if corrispettivi:
            await db["corrispettivi"].insert_one({"id": "co-1", "data": corrispettivi})
        if pos:
            await db["pos_terminal_transactions"].insert_one({"id": "pt-1", "data": pos})
    _run(scenario())


def test_avvisa_su_ogni_fonte_ferma_con_giorni_e_ultima_data():
    db = _db("ferme")
    _popola(db)
    esito = _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 18)))

    assert esito["controllate"] == 3
    ferme = {r["fonte"]: r for r in esito["ferme"]}
    assert set(ferme) == {"estratto_conto", "corrispettivi", "pos_numia"}
    assert ferme["estratto_conto"]["giorni"] == 25
    assert ferme["estratto_conto"]["ultima_data"] == "2026-08-24"
    assert ferme["pos_numia"]["giorni"] == 49

    alerts = _run(db["alerts"].find({"codice": "FONTE_CONTABILE_FERMA"}).to_list(10))
    assert len(alerts) == 3
    estratto = next(a for a in alerts if a["entita_id"] == "estratto_conto")
    assert estratto["stato"] == "aperto"
    assert "25 giorni" in estratto["dettaglio"] and "24/08/2026" in estratto["dettaglio"]
    # la conseguenza e' scritta nell'avviso: dice perche' la pagina e' vuota
    assert "versamento" in estratto["dettaglio"]


def test_non_avvisa_finche_il_ritardo_e_nella_norma_e_non_duplica():
    db = _db("recenti")
    _popola(db, estratto="2026-09-15", corrispettivi="2026-09-16", pos="2026-09-14")
    primo = _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 18)))
    assert primo["ferme"] == []
    assert _run(db["alerts"].count_documents({})) == 0

    # una fonte si ferma: l'avviso nasce una volta sola anche a piu' giri
    db2 = _db("doppioni")
    _popola(db2)
    _run(fonti_ferme.controlla_fonti_ferme(db2, oggi=date(2026, 9, 18)))
    _run(fonti_ferme.controlla_fonti_ferme(db2, oggi=date(2026, 9, 18)))
    assert _run(db2["alerts"].count_documents(
        {"codice": "FONTE_CONTABILE_FERMA", "entita_id": "estratto_conto"})) == 1


def test_quando_la_fonte_riparte_l_avviso_si_chiude():
    db = _db("ripresa")
    _popola(db)
    _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 18)))

    _run(db["estratto_conto_movimenti"].insert_one(
        {"id": "ec-2", "data": "2026-09-17", "importo": 5.0}))
    esito = _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 18)))

    assert "estratto_conto" in esito["riprese"]
    assert {r["fonte"] for r in esito["ferme"]} == {"corrispettivi", "pos_numia"}
    alert = _run(db["alerts"].find_one(
        {"codice": "FONTE_CONTABILE_FERMA", "entita_id": "estratto_conto"}))
    assert alert["stato"] == "risolto" and alert["resolved_by"] == "fonte_ripartita"


def test_fonte_vuota_non_diventa_un_avviso_inventato():
    """Una collezione vuota non prova che la fonte si sia fermata: potrebbe
    non essere mai partita. Si dichiara, non si allarma."""
    db = _db("vuota")
    _popola(db, estratto=None, corrispettivi="2026-09-17", pos=None)
    esito = _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 18)))

    assert set(esito["vuote"]) == {"estratto_conto", "pos_numia"}
    assert esito["ferme"] == []
    assert _run(db["alerts"].count_documents({})) == 0


def test_stato_fonti_espone_giorni_e_conseguenza_per_la_pagina():
    db = _db("stato")
    _popola(db)
    righe = {r["fonte"]: r for r in _run(fonti_ferme.stato_fonti(db, oggi=date(2026, 9, 18)))}

    assert righe["estratto_conto"]["ferma"] is True
    assert righe["estratto_conto"]["giorni_fermi"] == 25
    assert righe["estratto_conto"]["etichetta"] == "Estratto conto bancario"
    assert righe["corrispettivi"]["conseguenza"]
