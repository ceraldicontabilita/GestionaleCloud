"""Audit del commercialista 03/09/2026, §1 / PR 3.

Quattro assegni (0208770633 318,66; 0208770634 1.403,01; 0208770636
2.496,33; 0208770637 636,00 = 4.853,99 EUR) registrati due volte in Prima
Nota Banca per lo stesso ``estratto_conto_id`` (created_at 29/08 14:07 e
14:33: due processi con cache diverse). Qui: scrittura idempotente per
movimento (chiave ``assegno:<ec_id>:banca_uscita``) e bonifica delle coppie
gia' esistenti, esposta dallo stesso endpoint admin dei corrispettivi.
"""
import asyncio

from app.database import Database
from app.routers.admin import bonifica_prima_nota_doppioni
from app.services import bonifica_prima_nota_doppioni_assegni as bonifica
from app.services.assegni_estratto_conto import (
    _garantisci_prima_nota,
    chiave_idempotenza_assegno,
    sincronizza_assegni_da_estratto_conto,
)
from app.services.sheets_document_store import MemorySheetsClient

EC_ID = "EC-2026-01-02-1403.01-24a9b009"
ASSEGNO_ID = "103e84fe-75ab-4aad-82b4-0d66a8f0b8bf"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _movimento():
    return {
        "id": EC_ID, "data": "2026-01-02", "tipo": "uscita", "importo": 1403.01,
        "descrizione": "PRELIEVO ASSEGNO - DM 05387 CRA: 26010200167309 NUM: 0208770634",
        "riconciliato": False,
    }


def _riga_pn(id_riga, created_at):
    return {
        "id": id_riga, "tipo": "uscita", "categoria": "Assegni", "importo": 1403.01,
        "data": "2026-01-02", "assegno_id": ASSEGNO_ID, "assegno_numero": "0208770634",
        "estratto_conto_id": EC_ID, "movimento_estratto_conto_id": EC_ID,
        "source": "assegno_estratto_conto", "riconciliato": True,
        "descrizione": "Assegno n. 0208770634 - riscontro estratto conto",
        "created_at": created_at,
    }


def test_chiave_idempotenza_per_movimento_di_estratto_conto():
    assert chiave_idempotenza_assegno(EC_ID) == f"assegno:{EC_ID}:banca_uscita"
    assert chiave_idempotenza_assegno("") is None
    assert chiave_idempotenza_assegno(None) is None


def test_doppia_registrazione_stesso_movimento_lascia_una_sola_riga_attiva():
    async def scenario():
        db = MemorySheetsClient()["assegni-idempotenti"]
        await db.estratto_conto_movimenti.insert_one(_movimento())

        await sincronizza_assegni_da_estratto_conto(db)
        await sincronizza_assegni_da_estratto_conto(db)
        assegno = await db.assegni.find_one({"numero": "0208770634"}, {"_id": 0})
        # terza scrittura diretta della stessa prova bancaria
        await _garantisci_prima_nota(db, assegno, _movimento(), None, "2026-09-03T00:00:00+00:00")

        righe = await db.prima_nota_banca.find({}, {"_id": 0}).to_list(None)
        assert len(righe) == 1
        assert righe[0]["idempotency_key"] == f"assegno:{EC_ID}:banca_uscita"
        assert righe[0]["estratto_conto_id"] == EC_ID
        assert righe[0]["source"] == "assegno_estratto_conto"

    _run(scenario())


def test_riga_scritta_da_un_altro_processo_viene_riusata_per_chiave():
    """La riga esiste gia' con la sola chiave (arrivata dalla cache di un altro
    processo): non se ne crea una seconda, si aggiorna quella."""
    async def scenario():
        db = MemorySheetsClient()["assegni-altro-processo"]
        await db.prima_nota_banca.insert_one({
            "id": "riga-altro-processo", "tipo": "uscita", "categoria": "Assegni",
            "importo": 1403.01, "data": "2026-01-02", "source": "assegno_estratto_conto",
            "idempotency_key": chiave_idempotenza_assegno(EC_ID),
            "created_at": "2026-08-29T14:07:14+00:00",
        })
        assegno = {"id": ASSEGNO_ID, "numero": "0208770634", "importo": 1403.01}

        pn_id = await _garantisci_prima_nota(
            db, assegno, _movimento(), "fatt-1", "2026-09-03T00:00:00+00:00",
        )

        assert pn_id == "riga-altro-processo"
        assert await db.prima_nota_banca.count_documents({}) == 1
        riga = await db.prima_nota_banca.find_one({"id": pn_id}, {"_id": 0})
        assert riga["estratto_conto_id"] == EC_ID
        assert riga["assegno_id"] == ASSEGNO_ID
        assert riga["fattura_id"] == "fatt-1"

    _run(scenario())


def _db_con_doppione_reale():
    db = MemorySheetsClient()["bonifica-assegni"]

    async def semina():
        await db.prima_nota_banca.insert_many([
            _riga_pn("d5bdfaf8-0766-4b29-8916-af29560c44b2", "2026-08-29T14:07:14.828140+00:00"),
            _riga_pn("7b98d5da-bbf2-41ba-84dd-f234fcbb2aa9", "2026-08-29T14:33:33.327412+00:00"),
            # assegno singolo, senza chiave: riceve solo la chiave
            {**_riga_pn("singola", "2026-08-29T14:07:15+00:00"),
             "estratto_conto_id": "EC-ALTRO", "movimento_estratto_conto_id": "EC-ALTRO",
             "assegno_id": "ass-altro"},
            # riga banca di altra natura sullo stesso movimento: non e' un assegno
            {"id": "fatt-banca", "tipo": "uscita", "categoria": "Pagamenti fatture",
             "importo": 10.0, "data": "2026-01-02", "estratto_conto_id": "EC-FATT",
             "source": "riconciliazione_manual_allocations"},
        ])
        await db.assegni.insert_one({
            "id": ASSEGNO_ID, "numero": "0208770634", "importo": 1403.01,
            "prima_nota_banca_id": "7b98d5da-bbf2-41ba-84dd-f234fcbb2aa9",
        })
        await db.estratto_conto_movimenti.insert_one({
            **_movimento(), "prima_nota_banca_id": "7b98d5da-bbf2-41ba-84dd-f234fcbb2aa9",
        })

    asyncio.run(semina())
    return db


def test_bonifica_dry_run_trova_la_coppia_e_non_scrive():
    db = _db_con_doppione_reale()

    esito = asyncio.run(bonifica.esegui(db, dry_run=True))

    assert esito["dry_run"] is True
    assert esito["registri"]["banca_assegni"] == {
        "gruppi": 1, "righe_da_marcare": 1, "importo_doppio": 1403.01,
        "righe_attive": 3, "righe_senza_chiave": 3,
    }
    assert esito["totale_importo_doppio"] == 1403.01
    assert esito["righe_singole_senza_chiave"] == 1
    coppia = esito["coppie"][0]
    assert coppia["chiave"] == f"assegno:{EC_ID}:banca_uscita"
    assert coppia["assegno_numero"] == "0208770634"
    assert coppia["tenuta"]["id"] == "d5bdfaf8-0766-4b29-8916-af29560c44b2"
    assert [m["id"] for m in coppia["marcate"]] == ["7b98d5da-bbf2-41ba-84dd-f234fcbb2aa9"]
    assert not any(k.startswith("_") for k in coppia)
    righe = asyncio.run(db.prima_nota_banca.find({}, {"_id": 0}).to_list(None))
    assert all(r.get("entity_status") is None for r in righe)


def test_bonifica_applica_marca_la_copia_recente_e_riallinea_i_riferimenti():
    db = _db_con_doppione_reale()

    esito = asyncio.run(bonifica.esegui(db, dry_run=False, actor="test"))

    assert esito["righe_marcate"] == {"banca_assegni": 1}
    assert esito["chiavi_assegnate"] == 2  # tenuta + singola
    assert esito["riferimenti_riallineati"] == 2  # assegno + movimento EC

    async def leggi():
        banca = {r["id"]: r for r in await db.prima_nota_banca.find({}, {"_id": 0}).to_list(None)}
        assegno = await db.assegni.find_one({"id": ASSEGNO_ID}, {"_id": 0})
        movimento = await db.estratto_conto_movimenti.find_one({"id": EC_ID}, {"_id": 0})
        audit = await db.prima_nota_migrazioni_audit.find({}, {"_id": 0}).to_list(None)
        return banca, assegno, movimento, audit

    banca, assegno, movimento, audit = asyncio.run(leggi())
    marcata = banca["7b98d5da-bbf2-41ba-84dd-f234fcbb2aa9"]
    assert marcata["entity_status"] == "deleted" and marcata["status"] == "deleted"
    assert marcata["duplicate_of"] == "d5bdfaf8-0766-4b29-8916-af29560c44b2"
    assert marcata["deleted_reason"] == "bonifica_doppioni_assegni_2026-09-03"
    tenuta = banca["d5bdfaf8-0766-4b29-8916-af29560c44b2"]
    assert tenuta.get("entity_status") is None
    assert tenuta["idempotency_key"] == f"assegno:{EC_ID}:banca_uscita"
    assert banca["singola"]["idempotency_key"] == "assegno:EC-ALTRO:banca_uscita"
    assert "idempotency_key" not in banca["fatt-banca"]
    assert assegno["prima_nota_banca_id"] == tenuta["id"]
    assert movimento["prima_nota_banca_id"] == tenuta["id"]
    assert len(banca) == 4  # nessuna cancellazione fisica
    assert audit[0]["migrazione"] == "bonifica_doppioni_assegni_2026-09-03"

    di_nuovo = asyncio.run(bonifica.esegui(db, dry_run=True))
    assert di_nuovo["totale_righe_da_marcare"] == 0
    assert di_nuovo["righe_singole_senza_chiave"] == 0


def test_endpoint_admin_unico_copre_anche_gli_assegni(monkeypatch):
    db = _db_con_doppione_reale()
    monkeypatch.setattr(Database, "db", db)
    utente = {"sub": "admin-test", "role": "admin"}

    analisi = asyncio.run(bonifica_prima_nota_doppioni(dry_run=True, current_user=utente))
    assert set(analisi["registri"]) == {
        "cassa_entrate", "cassa_uscite_pos", "banca_crediti_pos", "banca_assegni",
    }
    assert analisi["totale_righe_da_marcare"] == 1
    assert analisi["totale_importo_doppio"] == 1403.01
    assert analisi["motivo_assegni"] == "bonifica_doppioni_assegni_2026-09-03"

    applicata = asyncio.run(bonifica_prima_nota_doppioni(dry_run=False, current_user=utente))
    assert applicata["dry_run"] is False
    assert applicata["righe_marcate"]["banca_assegni"] == 1
    assert applicata["totale_righe_marcate"] == 1
    assert applicata["riferimenti_riallineati"] == 2
