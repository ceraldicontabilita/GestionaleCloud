"""I movimenti «da insegnare» che la causale gia' spiega (Nexi SDD, giroconti) e le proposte per il resto."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services.categorizzazione_movimenti import categorizza_movimento_bancario as cat


def test_addebito_nexi_sdd_e_l_addebito_della_carta():
    esito = cat("ADDEBITO NEXI - SDD CORE: 8000640000050340753904 NEXI PAYMENTS S.P.A.", -482.48)
    assert esito.categoria == "Addebito carta di credito"


def test_giroconti_della_stessa_societa_non_hanno_un_fornitore():
    assert cat("BONIF. VS. FAVORE - BON.DA ceraldi group srl Giroconto NR. BONIFICO SEPA: PY0CUVS5YAGL RIF", 10000).categoria == "Giroconto"
    assert cat("BONIF. VS. FAVORE - BON.DA ceraldi group srl - Giroconto da Mastercard SumUp", 8000).categoria == "Giroconto"


def test_il_pagamento_al_comune_resta_da_decidere_non_si_indovina():
    esito = cat("VOSTRA DISPOSIZIONE - VS.DISP. RIF. MBVT30959316/00824733 FAVORE Comune di Napoli NOTPROVI", -1237.50)
    assert esito.categoria is None


def test_un_bonifico_generico_da_un_privato_non_e_un_giroconto():
    assert cat("BONIFICO A VOSTRO FAVORE DA ROSSI MARIO PER ACCONTO", 100).categoria is None


def test_proposte_nexi_giroconto_e_candidati_per_importo(monkeypatch):
    from app.database import Database
    from app.routers.bank import regole_riconoscimento as r

    db = AsyncMongoMockClient()["t"]

    async def riempi():
        await db["estratto_conto_movimenti"].insert_many([
            {"id": "N1", "data": "2026-08-17", "importo": -482.48, "tipo": "uscita",
             "descrizione": "ADDEBITO NEXI - SDD CORE: 8000640000050340753904 NEXI PAYMENTS S.P.A."},
            {"id": "C1", "data": "2026-07-31", "importo": -1237.50, "tipo": "uscita",
             "descrizione": "VOSTRA DISPOSIZIONE FAVORE Comune di Napoli NOTPROVI"},
        ])
        await db["verbali_noleggio"].insert_one({"id": "V1", "numero_verbale": "111/V/2025", "targa": "AB123CD", "importo": "1237,50"})
        await db["verbali_noleggio"].insert_one({"id": "V2", "numero_verbale": "222/V/2025", "targa": "AB123CD", "importo": "1237,51"})
        await db["cartelle_pagamento"].insert_one({"id": "cartella:1", "numero_cartella": "071 2026 1", "totale": "1237.50"})
        await db["invoices"].insert_one({"id": 7, "supplier_name": "Fornitore Prova", "invoice_number": "9", "total_amount": 1237.50})

    asyncio.run(riempi())
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    nexi = asyncio.run(r.proposte_per_movimento("N1"))
    assert nexi["riconoscimento"]["categoria"] == "Addebito carta di credito"
    assert nexi["nexi"]["periodo_spese"] == "2026-07" and nexi["nexi"]["riconciliato"] is False

    comune = asyncio.run(r.proposte_per_movimento("C1"))
    assert comune["riconoscimento"]["categoria"] is None
    assert {(c["tipo"], c["id"]) for c in comune["candidati"]} == {("verbale", "V1"), ("cartella", "cartella:1"), ("fattura", "7")}
    assert comune["classifica"] == "/riconciliazione/banca?movimento=C1"
    assert "nessun collegamento" in comune["avviso"]
