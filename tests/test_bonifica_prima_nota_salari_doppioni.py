"""PR 14 (audit 03/09/2026 §5): doppioni di ``prima_nota_salari``.

Nessuna rete: ``MemorySheetsClient`` sostituisce Supabase/Postgres con la
stessa API async usata in produzione.
"""
import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.services.bonifica_prima_nota_salari_doppioni import esegui


def _run(coro):
    return asyncio.run(coro)


def _db(nome):
    return MemorySheetsClient()[nome]


async def _popola_dipendente(db, *, id_, nome, cognome, cf):
    await db["dipendenti"].insert_one({
        "id": id_, "nome": nome, "cognome": cognome,
        "nome_completo": f"{cognome} {nome}", "codice_fiscale": cf,
    })


def test_doppio_certo_stesso_importo_viene_marcato_non_cancellato():
    """Ceraldi Valerio 05/2026: busta (indice_cedolini_drive, senza CF) e
    stipendio (cedolino_v2, con CF) scrivono lo stesso netto 2.000,00 — lo
    stesso caso reale trovato nell'audit."""
    async def scenario():
        db = _db("doppio_certo")
        await _popola_dipendente(
            db, id_="dip-1", nome="VALERIO", cognome="CERALDI", cf="CRLVLR88H14F839O",
        )
        await db["prima_nota_salari"].insert_one({
            "id": "pn-busta", "dipendente": "CERALDI VALERIO", "anno": 2026, "mese": 5,
            "tipo": "busta", "source": "indice_cedolini_drive",
            "importo_busta": 2000.0, "importo_bonifico": 0,
            "created_at": "2026-08-21T07:09:04Z",
        })
        await db["prima_nota_salari"].insert_one({
            "id": "pn-stipendio", "dipendente": "CERALDI VALERIO",
            "dipendente_nome": "CERALDI VALERIO", "codice_fiscale": "CRLVLR88H14F839O",
            "dipendente_id": "dip-1", "anno": 2026, "mese": 5, "tipo": "stipendio",
            "tipo_cedolino": "mensile", "source": "cedolino_v2", "cedolino_id": "ced-1",
            "importo_busta": 2000.0, "importo_bonifico": 0,
            "created_at": "2026-08-27T13:48:07Z",
        })

        analisi = await esegui(db, dry_run=True)
        assert analisi["totale_gruppi_doppioni"] == 1
        assert analisi["totale_righe_da_marcare"] == 1
        assert analisi["gruppi_doppioni"][0]["tenuta"]["id"] == "pn-stipendio"
        assert analisi["gruppi_doppioni"][0]["marcate"][0]["id"] == "pn-busta"
        # Il dry-run non scrive nulla.
        righe = [r async for r in db["prima_nota_salari"].find({})]
        assert all(r.get("entity_status") != "deleted" for r in righe)

        esito = await esegui(db, dry_run=False, actor="test")
        assert esito["righe_marcate"] == 1

        busta = await db["prima_nota_salari"].find_one({"id": "pn-busta"})
        assert busta["entity_status"] == "deleted"
        assert busta["duplicate_of"] == "pn-stipendio"
        stipendio = await db["prima_nota_salari"].find_one({"id": "pn-stipendio"})
        assert stipendio.get("entity_status") != "deleted"

        # Idempotente: un secondo giro non trova piu' nulla da marcare.
        secondo = await esegui(db, dry_run=True)
        assert secondo["totale_gruppi_doppioni"] == 0
        assert secondo["totale_righe_da_marcare"] == 0

    _run(scenario())


def test_stessa_identita_importo_diverso_non_viene_toccata():
    """Parisi Antonio 05/2026: 1.231,00 (corretto, coincide con l'HR) e
    1.129,00 (anomalia) — stessa identita' logica ma importo diverso: la
    bonifica dei doppioni non deve MAI scegliere quale tenere da sola."""
    async def scenario():
        db = _db("importo_diverso")
        await _popola_dipendente(
            db, id_="dip-2", nome="ANTONIO", cognome="PARISI", cf="PRSNTN80R12F839X",
        )
        await db["prima_nota_salari"].insert_one({
            "id": "pn-1231", "dipendente": "PARISI ANTONIO", "anno": 2026, "mese": 5,
            "tipo": "busta", "source": "indice_cedolini_drive", "importo_busta": 1231.0,
            "importo_bonifico": 0, "created_at": "2026-08-21T07:26:59Z",
        })
        await db["prima_nota_salari"].insert_one({
            "id": "pn-1129", "dipendente": "PARISI ANTONIO", "anno": 2026, "mese": 5,
            "tipo": "busta", "source": "indice_cedolini_drive", "importo_busta": 1129.0,
            "importo_bonifico": 0, "created_at": "2026-08-21T07:26:59Z",
        })

        analisi = await esegui(db, dry_run=True)
        assert analisi["totale_gruppi_doppioni"] == 0
        assert len(analisi["ambigue_importo_diverso"]) == 1
        gruppo = analisi["ambigue_importo_diverso"][0]
        assert gruppo["codice_fiscale"] == "PRSNTN80R12F839X"
        assert {r["id"] for r in gruppo["righe"]} == {"pn-1231", "pn-1129"}

        esito = await esegui(db, dry_run=False)
        assert esito["righe_marcate"] == 0
        for id_ in ("pn-1231", "pn-1129"):
            riga = await db["prima_nota_salari"].find_one({"id": id_})
            assert riga.get("entity_status") != "deleted"

    _run(scenario())


def test_backfill_importo_bonifico_zero_con_movimento_agganciato():
    """Murolo/Parisi/Pocci dicembre 2025: bonifico gia' agganciato
    (``movimenti_bancari_ids``) ma mai riallineato dopo la migrazione del
    21/08/2026 (``importo_bonifico=0``, saldo negativo pieno)."""
    async def scenario():
        db = _db("backfill_pagamento")
        await db["prima_nota_salari"].insert_one({
            "id": "pn-murolo", "dipendente": "MUROLO MARIO", "anno": 2025, "mese": 12,
            "tipo": "busta", "source": "indice_cedolini_drive", "importo_busta": 1993.0,
            "importo_bonifico": 0, "saldo": -1993.0, "riconciliato": False,
            "movimenti_bancari_ids": ["EC-1"],
        })
        await db["estratto_conto_movimenti"].insert_one({
            "id": "EC-1", "importo": -1993.0, "data": "2026-01-07",
            "descrizione_originale": "FAVORE MUROLO MARIO",
        })

        analisi = await esegui(db, dry_run=True)
        assert analisi["totale_righe_da_riallineare_pagamento"] == 1

        esito = await esegui(db, dry_run=False)
        assert esito["righe_pagamento_riallineate"] == 1
        riga = await db["prima_nota_salari"].find_one({"id": "pn-murolo"})
        assert riga["importo_bonifico"] == 1993.0
        assert riga["saldo"] == 0.0
        assert riga["riconciliato"] is True

        # Idempotente.
        secondo = await esegui(db, dry_run=True)
        assert secondo["totale_righe_da_riallineare_pagamento"] == 0

    _run(scenario())
