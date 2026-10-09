"""PR 14 (audit 03/09/2026 §5): doppioni di ``prima_nota_salari``.

Nessuna rete: ``ClientArchivioMemoria`` sostituisce Supabase/Postgres con la
stessa API async usata in produzione.
"""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.services.bonifica_prima_nota_salari_doppioni import esegui


def _run(coro):
    return asyncio.run(coro)


def _db(nome):
    return ClientArchivioMemoria()[nome]


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
        await db["cedolini"].insert_one({
            "id": "ced-1", "codice_fiscale": "CRLVLR88H14F839O", "anno": 2026, "mese": 5,
        })
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

        await db["cedolini"].insert_one({"id": "ced-p", "codice_fiscale": "PRSNTN80R12F839X", "anno": 2026, "mese": 5})
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


def test_attesa_senza_busta_si_ritira_per_id_e_con_pagamento_o_busta_resta():
    """Pocci 08/2026: l'attesa di 1.769,76 nasce da una busta che non esiste
    piu' ne' in cedolini ne' altrove. Senza busta e senza pagamento si ritira
    (per id, con motivo); con una busta, o con un bonifico agganciato, resta."""
    async def scenario():
        db = _db("senza_busta")
        await _popola_dipendente(db, id_="dip-2", nome="SALVATORE", cognome="POCCI", cf="PCCSVT69P30F839G")
        await _popola_dipendente(db, id_="dip-3", nome="MARIO", cognome="MUROLO", cf="MRLMRA80A01F839X")
        base = {"codice_fiscale": "PCCSVT69P30F839G", "dipendente_id": "dip-2", "importo_bonifico": 0,
                "tipo": "stipendio", "tipo_cedolino": "mensile", "source": "cedolino_v2"}
        await db["prima_nota_salari"].insert_one({
            **base, "id": "pn-fantasma", "dipendente": "POCCI SALVATORE", "anno": 2026, "mese": 8,
            "cedolino_id": "ced-sparita", "importo_busta": 1769.76})
        await db["prima_nota_salari"].insert_one({
            **base, "id": "pn-con-bonifico", "dipendente": "POCCI SALVATORE", "anno": 2026, "mese": 7,
            "cedolino_id": "ced-sparita-2", "importo_busta": 751.0, "importo_bonifico": 751.0})
        await db["prima_nota_salari"].insert_one({
            "id": "pn-con-busta", "dipendente": "MUROLO MARIO", "codice_fiscale": "MRLMRA80A01F839X",
            "dipendente_id": "dip-3", "anno": 2026, "mese": 6, "tipo": "stipendio",
            "tipo_cedolino": "mensile", "cedolino_id": "ced-ok", "importo_busta": 927.0, "importo_bonifico": 0})
        await db["cedolini"].insert_one({"id": "ced-ok", "codice_fiscale": "MRLMRA80A01F839X", "anno": 2026, "mese": 6})

        analisi = await esegui(db, dry_run=True)
        assert [v["id"] for v in analisi["attese_senza_busta"]] == ["pn-fantasma"]
        assert (await db["prima_nota_salari"].find_one({"id": "pn-fantasma"})).get("entity_status") != "deleted"

        esito = await esegui(db, dry_run=False, actor="test")
        assert esito["attese_ritirate_senza_busta"] == 1
        fantasma = await db["prima_nota_salari"].find_one({"id": "pn-fantasma"})
        assert fantasma["entity_status"] == "deleted" and fantasma["deleted_reason"]
        for ok in ("pn-con-bonifico", "pn-con-busta"):
            assert (await db["prima_nota_salari"].find_one({"id": ok})).get("entity_status") != "deleted"
        assert (await esegui(db, dry_run=True))["totale_attese_senza_busta"] == 0

    _run(scenario())


def test_attesa_senza_busta_non_tocca_righe_hr_ambigue_e_conta_solo_buste_attive():
    async def scenario():
        db = _db("senza_busta_guardie")
        await _popola_dipendente(db, id_="dip-4", nome="ANTONIO", cognome="PARISI", cf="PRSNTN80R12F839X")
        base = {"codice_fiscale": "PRSNTN80R12F839X", "dipendente_id": "dip-4", "importo_bonifico": 0,
                "tipo": "stipendio", "tipo_cedolino": "mensile", "dipendente": "PARISI ANTONIO"}
        # Riga nata dall'archivio HR: la busta vive solo li', non si ritira.
        await db["prima_nota_salari"].insert_one({**base, "id": "pn-hr", "anno": 2026, "mese": 3, "source": "hr_cedolini_sync",
                                                  "hr_cedolino_id": "hr-1", "importo_busta": 100.0})
        # Stessa identita' con importi diversi: anomalia, mai ritirata qui.
        for i, imp in (("pn-a", 1231.0), ("pn-b", 1129.0)):
            await db["prima_nota_salari"].insert_one({**base, "id": i, "anno": 2026, "mese": 5, "importo_busta": imp})
        # Busta solo "sostituito": non e' una busta viva.
        await db["prima_nota_salari"].insert_one({**base, "id": "pn-sost", "anno": 2026, "mese": 6, "importo_busta": 900.0})
        await db["cedolini"].insert_one({"id": "c-s", "codice_fiscale": "PRSNTN80R12F839X", "anno": 2026, "mese": 6,
                                         "status": "sostituito"})
        analisi = await esegui(db, dry_run=True)
        assert [v["id"] for v in analisi["attese_senza_busta"]] == ["pn-sost"]

    _run(scenario())
