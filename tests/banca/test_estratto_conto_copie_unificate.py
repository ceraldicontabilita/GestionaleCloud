"""Lo stesso estratto conto scaricato due volte non duplica niente.

Il titolare scarica l'estratto quando vuole: quello della settimana scorsa e
quello di oggi riportano gli stessi movimenti, e il vecchio archivio li aveva
gia'. Resta una riga per movimento; due movimenti uguali nello stesso export
restano due.
"""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.doppioni_estratto_conto import (
    COLLEZIONE, COLLEZIONE_QUARANTENA, unifica_copie,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _mov(id_, fonte, data, importo, testo, **extra):
    return {"id": id_, "source_filename": fonte, "data": data, "tipo": "uscita",
            "importo": importo, "descrizione_originale": testo,
            "created_at": f"{fonte}-{id_}", **extra}


SETTIMANA = "ElencoEntrateUsciteAndamento_20-09-2026.csv"
OGGI = "ElencoEntrateUsciteAndamento_27-09-2026.csv"
STIPENDIO = "VOSTRA DISPOSIZIONE - VS.DISP. RIF. MB0B10283131/90366939 FAVORE ROSSI MARIO"
COMMISSIONE = "COMMISSIONI - COMM.SU BONIFICI"


def _scenario():
    db = ClientArchivioMemoria()["copie_ec"]

    async def prepara():
        await db[COLLEZIONE].insert_many([
            # vecchio archivio: gia' riconciliato, e' la riga da tenere
            _mov("L1", "legacy_staging_2026", "2026-09-18", 1000.0,
                 "VS.DISP. RIF. MB0B10283131/90366939 FAVORE ROSSI MARIO", riconciliato=True),
            # estratto della settimana scorsa
            _mov("S1", SETTIMANA, "2026-09-18", 1000.0, STIPENDIO, categoria="Stipendi"),
            _mov("S2", SETTIMANA, "2026-09-18", 1.10, COMMISSIONE),
            _mov("S3", SETTIMANA, "2026-09-18", 1.10, COMMISSIONE),
            # estratto di oggi: stessi movimenti, piu' uno nuovo
            _mov("O1", OGGI, "2026-09-18", 1000.0, STIPENDIO),
            _mov("O2", OGGI, "2026-09-18", 1.10, COMMISSIONE),
            _mov("O3", OGGI, "2026-09-18", 1.10, COMMISSIONE),
            _mov("O4", OGGI, "2026-09-25", 250.0, "VS.DISP. RIF. MB0B20000001/1 FAVORE BIANCHI"),
        ])
        await db["prima_nota_banca"].insert_one({
            "id": "PN-O1", "estratto_conto_id": "O1", "importo": 1000.0, "categoria": "Stipendi"})
        primo = await unifica_copie(db)
        secondo = await unifica_copie(db)
        rimasti = {m["id"]: m for m in await db[COLLEZIONE].find({}, {"_id": 0}).to_list(None)}
        quarantena = {m["id"]: m for m in await db[COLLEZIONE_QUARANTENA].find({}, {"_id": 0}).to_list(None)}
        pn = await db["prima_nota_banca"].find_one({"id": "PN-O1"}, {"_id": 0})
        return primo, secondo, rimasti, quarantena, pn

    return _run(prepara())


def test_una_riga_per_movimento_qualunque_export():
    primo, secondo, rimasti, quarantena, pn = _scenario()
    # stipendio: resta la riga riconciliata del vecchio archivio
    assert "L1" in rimasti and "S1" not in rimasti and "O1" not in rimasti
    # due commissioni uguali nello stesso export sono due operazioni: restano due
    commissioni = [m for m in rimasti.values() if m["importo"] == 1.10]
    assert len(commissioni) == 2
    # il movimento nuovo di oggi entra
    assert "O4" in rimasti
    assert primo["copie"] == 4 and len(rimasti) == 4
    # le copie non spariscono: stanno in quarantena con la riga tenuta
    assert quarantena["O1"]["duplicato_di"] == "L1"
    # la riga tenuta prende la categoria della copia
    assert rimasti["L1"]["categoria"] == "Stipendi"
    # la Prima Nota che citava la copia passa alla riga tenuta
    assert pn["estratto_conto_id"] == "L1"
    # idempotente
    assert secondo["copie"] == 0


def test_riferimenti_banca_diversi_non_sono_copie():
    db = ClientArchivioMemoria()["copie_diverse"]

    async def scenario():
        await db[COLLEZIONE].insert_many([
            _mov("A", SETTIMANA, "2026-09-18", 500.0, "VS.DISP. RIF. MB0B11111111/1 FAVORE ROSSI"),
            _mov("B", OGGI, "2026-09-18", 500.0, "VS.DISP. RIF. MB0B22222222/1 FAVORE VERDI"),
        ])
        esito = await unifica_copie(db)
        return esito, await db[COLLEZIONE].count_documents({})

    esito, quanti = _run(scenario())
    assert esito["copie"] == 0 and quanti == 2
