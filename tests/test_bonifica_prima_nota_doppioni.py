"""Bonifica dei doppioni di Prima Nota (audit 03/09/2026 §2, PR 5).

Riproduce il caso reale del 22/03/2026: corrispettivo 8eb80d64… registrato
due volte in Prima Nota Cassa (4.629,20 x 2, created_at 23/08 e 29/08).
"""
import asyncio

from app.database import Database
from app.routers.admin import bonifica_prima_nota_doppioni
from app.services import bonifica_prima_nota_doppioni as bonifica
from app.services.sheets_document_store import MemorySheetsClient

CORR_ID = "8eb80d64-12ab-4e34-b848-8935ea1114d4"


def _entrata(id_riga, created_at, matricola="99MEY026532"):
    return {
        "id": id_riga, "corrispettivo_id": CORR_ID, "data": "2026-03-22",
        "tipo": "entrata", "categoria": "Corrispettivi", "importo": 4629.20,
        "source": "corrispettivo_import", "matricola_rt": matricola,
        "created_at": created_at,
    }


def _db_con_caso_reale():
    db = MemorySheetsClient()["bonifica-doppioni"]

    async def semina():
        await db["prima_nota_cassa"].insert_many([
            _entrata("4ff24eaa", "2026-08-23T03:36:08+00:00"),
            _entrata("a52e671e", "2026-08-29T14:33:25+00:00"),
            # uscita POS singola, storica, senza gestore ne' chiave
            {"id": "pos-1", "corrispettivo_id": CORR_ID, "data": "2026-03-22",
             "tipo": "uscita", "categoria": "POS Verso Banca", "importo": 2962.30,
             "source": "corrispettivo_import", "created_at": "2026-08-23T03:36:09+00:00"},
            # riga non derivata da corrispettivo: non va toccata
            {"id": "fatt-1", "data": "2026-03-22", "tipo": "uscita",
             "categoria": "Fatture", "importo": 100.0, "source": "manuale"},
            # copia gia' marcata: non conta ne' come tenuta ne' come doppione
            {**_entrata("vecchia-cancellata", "2026-08-01T00:00:00+00:00"),
             "status": "deleted", "entity_status": "deleted"},
        ])
        await db["prima_nota_banca"].insert_many([
            {"id": "banca-1", "corrispettivo_id": CORR_ID, "data": "2026-03-22",
             "tipo": "entrata", "categoria": "Corrispettivi POS", "importo": 2962.30,
             "source": "trasferimento_pos", "gestore": "numia",
             "created_at": "2026-08-23T03:36:10+00:00"},
            {"id": "banca-2", "corrispettivo_id": CORR_ID, "data": "2026-03-22",
             "tipo": "entrata", "categoria": "Corrispettivi POS", "importo": 2962.30,
             "source": "trasferimento_pos", "gestore": None,
             "created_at": "2026-08-29T14:33:26+00:00"},
        ])
        await db["corrispettivi"].insert_one({
            "id": CORR_ID, "data": "2026-03-22", "totale": 4629.20,
            "prima_nota_cassa_id": "a52e671e", "prima_nota_id": "a52e671e",
            "prima_nota_banca_id": "banca-2",
        })

    asyncio.run(semina())
    return db


def test_dry_run_propone_la_copia_piu_recente_senza_scrivere():
    db = _db_con_caso_reale()

    esito = asyncio.run(bonifica.esegui(db, dry_run=True))

    assert esito["dry_run"] is True
    assert esito["registri"]["cassa_entrate"] == {
        "gruppi": 1, "righe_da_marcare": 1, "importo_doppio": 4629.20,
        "righe_attive": 2, "righe_senza_chiave": 2,
    }
    assert esito["registri"]["banca_crediti_pos"]["gruppi"] == 1
    assert esito["registri"]["banca_crediti_pos"]["importo_doppio"] == 2962.30
    assert esito["registri"]["cassa_uscite_pos"]["gruppi"] == 0
    assert esito["totale_righe_da_marcare"] == 2
    assert esito["totale_importo_doppio"] == round(4629.20 + 2962.30, 2)
    assert esito["righe_singole_senza_chiave"] == 1  # l'uscita POS

    coppia = next(c for c in esito["coppie"] if c["registro"] == "cassa_entrate")
    assert coppia["chiave"] == f"corr:{CORR_ID}:cassa_entrata"
    assert coppia["tenuta"]["id"] == "4ff24eaa"
    assert [m["id"] for m in coppia["marcate"]] == ["a52e671e"]
    assert not any(k.startswith("_") for k in coppia)

    # dry-run puro: nulla e' cambiato
    righe = asyncio.run(db["prima_nota_cassa"].find({"id": "a52e671e"}).to_list(None))
    assert righe[0].get("entity_status") is None
    assert asyncio.run(db["prima_nota_migrazioni_audit"].count_documents({})) == 0


def test_applica_marca_la_copia_recente_e_assegna_le_chiavi():
    db = _db_con_caso_reale()

    esito = asyncio.run(bonifica.esegui(db, dry_run=False, actor="test"))

    assert esito["dry_run"] is False
    assert esito["righe_marcate"] == {
        "cassa_entrate": 1, "cassa_uscite_pos": 0, "banca_crediti_pos": 1,
    }
    assert esito["totale_righe_marcate"] == 2

    async def leggi():
        cassa = {r["id"]: r for r in await db["prima_nota_cassa"].find({}).to_list(None)}
        banca = {r["id"]: r for r in await db["prima_nota_banca"].find({}).to_list(None)}
        corr = await db["corrispettivi"].find_one({"id": CORR_ID})
        audit = await db["prima_nota_migrazioni_audit"].find({}).to_list(None)
        return cassa, banca, corr, audit

    cassa, banca, corr, audit = asyncio.run(leggi())

    marcata = cassa["a52e671e"]
    assert marcata["entity_status"] == "deleted"
    assert marcata["status"] == "deleted"
    assert marcata["duplicate_of"] == "4ff24eaa"
    assert marcata["deleted_reason"] == "bonifica_doppioni_2026-09-03"
    assert marcata["deleted_at"]
    assert marcata["idempotency_key"] == f"corr:{CORR_ID}:cassa_entrata"

    tenuta = cassa["4ff24eaa"]
    assert tenuta.get("entity_status") is None
    assert tenuta["idempotency_key"] == f"corr:{CORR_ID}:cassa_entrata"
    # la singola uscita POS riceve la chiave con il gestore dedotto (numia)
    assert cassa["pos-1"]["idempotency_key"] == f"corr:{CORR_ID}:cassa_uscita:numia"
    assert "idempotency_key" not in cassa["fatt-1"]
    assert cassa["vecchia-cancellata"].get("duplicate_of") is None

    assert banca["banca-2"]["entity_status"] == "deleted"
    assert banca["banca-2"]["duplicate_of"] == "banca-1"
    assert banca["banca-1"]["idempotency_key"] == f"corr:{CORR_ID}:banca_credito:numia"

    # il corrispettivo non punta piu' alla copia marcata
    assert corr["prima_nota_cassa_id"] == "4ff24eaa"
    assert corr["prima_nota_id"] == "4ff24eaa"
    assert corr["prima_nota_banca_id"] == "banca-1"
    assert esito["corrispettivi_riallineati"] == 2

    assert len(audit) == 1
    assert audit[0]["migrazione"] == "bonifica_doppioni_2026-09-03"
    assert audit[0]["actor"] == "test"

    # nessuna cancellazione fisica
    assert len(cassa) == 5
    assert len(banca) == 2

    # una seconda passata non trova piu' nulla
    di_nuovo = asyncio.run(bonifica.esegui(db, dry_run=True))
    assert di_nuovo["totale_righe_da_marcare"] == 0
    assert di_nuovo["righe_singole_senza_chiave"] == 0


def test_le_letture_di_prima_nota_escludono_le_righe_marcate():
    """Le pagine filtrano ``status``; il motore contabile ``entity_status``:
    la bonifica marca entrambi, quindi nessuna lettura somma la copia."""
    db = _db_con_caso_reale()
    asyncio.run(bonifica.esegui(db, dry_run=False))

    async def somma(filtro):
        righe = await db["prima_nota_cassa"].find({
            "tipo": "entrata", "categoria": "Corrispettivi", **filtro,
        }).to_list(None)
        return round(sum(r["importo"] for r in righe), 2)

    assert asyncio.run(somma({"status": {"$nin": ["deleted", "archived"]}})) == 4629.20
    assert asyncio.run(somma({"entity_status": {"$ne": "deleted"}})) == 4629.20


def test_endpoint_admin_dry_run_e_applica(monkeypatch):
    db = _db_con_caso_reale()
    monkeypatch.setattr(Database, "db", db)

    analisi = asyncio.run(bonifica_prima_nota_doppioni(
        dry_run=True, current_user={"sub": "admin-test", "role": "admin"},
    ))
    assert analisi["dry_run"] is True
    assert analisi["totale_righe_da_marcare"] == 2

    applicata = asyncio.run(bonifica_prima_nota_doppioni(
        dry_run=False, current_user={"sub": "admin-test", "role": "admin"},
    ))
    assert applicata["dry_run"] is False
    assert applicata["totale_righe_marcate"] == 2
