"""PR 14 (audit 03/09/2026 §5): ``/import-salari-verificati`` non deve piu'
creare una seconda riga per una busta gia' presente da un altro canale
(``cedolino_v2``) quando il nome risolve a un CF univoco in anagrafica —
causa verificata dei doppioni di Ceraldi Valerio/Vincenzo 05/2026."""
import asyncio

from app.services.sheets_document_store import MemorySheetsClient


def _run(coro):
    return asyncio.run(coro)


def _db(nome):
    return MemorySheetsClient()[nome]


def test_upsert_su_chiave_duplicata_non_crea_una_seconda_riga(monkeypatch):
    from app.routers.accounting import prima_nota_salari as modulo

    async def scenario():
        db = _db("import_salari_verificati_upsert")
        monkeypatch.setattr(modulo.Database, "get_db", lambda: db)
        await db["dipendenti"].insert_one({
            "id": "dip-valerio", "nome": "VALERIO", "cognome": "CERALDI",
            "nome_completo": "CERALDI VALERIO", "codice_fiscale": "CRLVLR88H14F839O",
        })
        await db["prima_nota_salari"].insert_one({
            "id": "pn-stipendio", "dipendente": "CERALDI VALERIO",
            "dipendente_nome": "CERALDI VALERIO", "codice_fiscale": "CRLVLR88H14F839O",
            "dipendente_id": "dip-valerio", "anno": 2026, "mese": 5, "tipo": "stipendio",
            "tipo_cedolino": "mensile", "source": "cedolino_v2", "cedolino_id": "ced-1",
            "importo_busta": 2000.0, "importo_bonifico": 0, "saldo": -2000.0,
            "riconciliato": False,
        })

        payload = {"righe": [{
            "employee": "Ceraldi Valerio", "year": 2026, "month": 5,
            "net_amount": 2000.0, "status": "NETTO_VERIFICATO_DA_CEDOLINO",
            "source": "drive://cedolini/ceraldi-valerio-05-2026.pdf",
        }]}
        esito = await modulo.import_salari_verificati(payload)

        assert esito["created"] == 0
        assert esito["duplicates"] == 1
        righe = [r async for r in db["prima_nota_salari"].find({})]
        assert len(righe) == 1
        riga = righe[0]
        assert riga["id"] == "pn-stipendio"
        # Il pagamento gia' registrato dall'altro canale non viene mai
        # toccato da un reimport della sola documentazione del netto.
        assert riga["importo_bonifico"] == 0
        assert riga["importo_busta"] == 2000.0
        assert riga["importo_busta_documentato"] == 2000.0

    _run(scenario())


def test_upsert_non_azzera_un_bonifico_gia_registrato(monkeypatch):
    from app.routers.accounting import prima_nota_salari as modulo

    async def scenario():
        db = _db("import_salari_verificati_no_overwrite")
        monkeypatch.setattr(modulo.Database, "get_db", lambda: db)
        await db["dipendenti"].insert_one({
            "id": "dip-taiano", "nome": "LUIGI", "cognome": "TAIANO",
            "nome_completo": "TAIANO LUIGI", "codice_fiscale": "TNALGU95L10F839Y",
        })
        await db["prima_nota_salari"].insert_one({
            "id": "pn-taiano", "dipendente": "TAIANO LUIGI",
            "codice_fiscale": "TNALGU95L10F839Y", "anno": 2026, "mese": 2,
            "tipo": "busta", "source": "indice_cedolini_drive",
            "importo_busta": 802.0, "importo_busta_documentato": 802.0,
            "importo_bonifico": 320.0, "saldo": 482.0, "riconciliato": False,
        })

        payload = {"righe": [{
            "employee": "Taiano Luigi", "year": 2026, "month": 2,
            "net_amount": 802.0, "status": "NETTO_VERIFICATO_DA_CEDOLINO",
        }]}
        await modulo.import_salari_verificati(payload)

        riga = await db["prima_nota_salari"].find_one({"id": "pn-taiano"})
        assert riga["importo_bonifico"] == 320.0
        assert riga["saldo"] == 482.0

    _run(scenario())
