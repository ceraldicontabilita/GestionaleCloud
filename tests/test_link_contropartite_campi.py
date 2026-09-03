"""Audit del commercialista 03/09/2026 §6, PR 16 — campi di collegamento che
gli endpoint di lettura devono esporre perche' "cliccando un dato si trovi la
contropartita" (richiesta del titolare). Solo campi aggiuntivi, nessun nuovo
endpoint.
"""
import asyncio

from app.routers import f24_analisi, scadenze
from app.routers.accounting import contabilita_gestionale as cg
from app.services.riconciliazione_smart import collegamenti_movimento, semanticizza_risultato
from app.services.sheets_document_store import MemorySheetsClient


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db(nome):
    return MemorySheetsClient()[nome]


# ── Bilancio di verifica → libro giornale → documento ─────────────────────

def test_bilancio_verifica_espone_conto_cee_e_riferimenti_alla_scrittura():
    db = _db("pr16-verifica")

    async def scenario():
        await db["movimenti_contabili"].insert_one({
            "id": "S1", "anno": 2026, "data": "2026-03-10", "tipo": "fattura_acquisto",
            "numero_registrazione": 1, "descrizione": "Fattura 77/2026",
            "fonte_documento": {"tipo": "fattura", "id": "F-77", "numero": "77/2026"},
            "righe": [
                {"conto_codice": "05.01.01", "conto_nome": "Acquisto merci", "dare": 100, "avere": 0},
                {"conto_codice": "02.01.01", "conto_nome": "Debiti v/fornitori", "dare": 0, "avere": 100},
            ],
        })
        return await cg._bilancio_verifica_da_registro(db, 2026, True)

    esito = _run(scenario())
    conti = {c["codice"]: c for c in esito["conti"]}
    assert conti["05.01.01"]["codice_ufficiale"] == "55.01.07"
    assert conti["05.01.01"]["nome_ufficiale"]
    movimento = conti["02.01.01"]["movimenti"][0]
    assert movimento["scrittura_id"] == "S1"
    assert movimento["tipo"] == "fattura_acquisto"
    assert movimento["fonte_documento"] == {"tipo": "fattura", "id": "F-77", "numero": "77/2026"}


def test_libro_giornale_filtra_per_conto_operativo_o_cee(monkeypatch):
    db = _db("pr16-giornale")

    async def scenario():
        await db["movimenti_contabili"].insert_many([
            {"id": "S1", "anno": 2026, "data_documento": "2026-03-10", "numero_registrazione": 1,
             "righe": [{"conto_codice": "05.01.01", "dare": 100, "avere": 0},
                       {"conto_codice": "02.01.01", "dare": 0, "avere": 100}]},
            {"id": "S2", "anno": 2026, "data_documento": "2026-03-11", "numero_registrazione": 2,
             "righe": [{"conto_codice": "01.01.01", "dare": 50, "avere": 0},
                       {"conto_codice": "04.01.02", "dare": 0, "avere": 50}]},
        ])
        monkeypatch.setattr(cg.Database, "get_db", lambda: db)
        solo_cassa = await cg.get_libro_giornale(
            data_da="2026-01-01", data_a="2026-12-31", conto="01.01.01", limit=500,
        )
        per_cee = await cg.get_libro_giornale(
            data_da="2026-01-01", data_a="2026-12-31", conto="33.03.01", limit=500,
        )
        tutte = await cg.get_libro_giornale(data_da="2026-01-01", data_a="2026-12-31", limit=500)
        return solo_cassa, per_cee, tutte

    solo_cassa, per_cee, tutte = _run(scenario())
    assert [s["id"] for s in solo_cassa["scritture"]] == ["S2"]
    assert solo_cassa["totale_disponibile"] == 1
    assert [s["id"] for s in per_cee["scritture"]] == ["S1"]  # 02.01.01 → 33.03.01 CEE
    assert tutte["totale"] == 2


# ── Scadenza → movimento bancario che l'ha pagata ─────────────────────────

def test_movimento_da_evidenza_legge_il_formato_reale():
    assert scadenze._movimento_da_evidenza(
        "banca:EC-2026-02-17-11.68-4b86e9dd:0b440588-01cf-4fb1-bb93-ba08a4ab502d"
    ) == "EC-2026-02-17-11.68-4b86e9dd"
    assert scadenze._movimento_da_evidenza("cassa:qualcosa") is None
    assert scadenze._movimento_da_evidenza(None) is None


def test_scadenze_pagate_espongono_il_movimento_bancario_che_le_ha_pagate():
    from datetime import date

    db = _db("pr16-scadenze")
    oggi = date.today()
    anno = oggi.year

    async def scenario():
        await db["invoices"].insert_many([
            {"id": "F-pag", "invoice_number": "IT6IKYJABEI", "invoice_date": f"{anno}-02-13",
             "supplier_name": "Amazon Business EU", "total_amount": 11.68, "pagato": True,
             "stato_pagamento": "pagata", "data_pagamento": f"{anno}-02-17"},
            # aperta con scadenza (data + 30 gg) ancora futura: visibile anche senza passate
            {"id": "F-aperta", "invoice_number": "9/2026", "invoice_date": oggi.isoformat(),
             "supplier_name": "Fornitore", "total_amount": 50.0},
            {"id": "F-solo-fattura", "invoice_number": "10/2026", "invoice_date": f"{anno}-02-21",
             "supplier_name": "Fornitore", "total_amount": 70.0, "pagato": True,
             "movimento_bancario_id": "EC-2026-02-25-70.00-abc"},
        ])
        await db["scadenziario_fornitori"].insert_one({
            "id": "F-pag::0::0", "fattura_id": "F-pag", "pagato": True,
            "data_pagamento": f"{anno}-02-17", "metodo_pagamento_effettivo": "SDD/RID",
            "evidenze_pagamento": [{
                "metodo": "SDD/RID", "importo": 11.68, "data_pagamento": f"{anno}-02-17",
                "evidenza_id": "banca:EC-2026-02-17-11.68-4b86e9dd:F-pag",
            }],
        })
        con_passate = await scadenze._get_fatture_in_scadenza(db, anno, True, giorni_limite=100000)
        solo_aperte = await scadenze._get_fatture_in_scadenza(db, anno, False, giorni_limite=100000)
        return con_passate, solo_aperte

    con_passate, solo_aperte = _run(scenario())
    per_id = {s["id"]: s for s in con_passate}
    assert per_id["F-pag"]["pagata"] is True
    assert per_id["F-pag"]["movimento_bancario_id"] == "EC-2026-02-17-11.68-4b86e9dd"
    assert per_id["F-pag"]["pagamento"]["metodo"] == "SDD/RID"
    assert per_id["F-pag"]["pagamento"]["data_pagamento"] == f"{anno}-02-17"
    # ripiego: movimento scritto sulla fattura dalla riconciliazione
    assert per_id["F-solo-fattura"]["movimento_bancario_id"] == "EC-2026-02-25-70.00-abc"
    assert per_id["F-aperta"]["pagata"] is False and "pagamento" not in per_id["F-aperta"]
    assert all("_fattura" not in s for s in con_passate)
    # senza include_passate il comportamento storico non cambia: solo aperte
    assert [s["id"] for s in solo_aperte] == ["F-aperta"]


# ── F24 → quietanza / movimento bancario ──────────────────────────────────

def test_tabella_f24_espone_quietanza_e_movimento_bancario(monkeypatch):
    db = _db("pr16-f24")

    async def scenario():
        await db["f24_unificato"].insert_many([
            {"id": "f24-a", "file_name": "F24_gen.pdf", "quietanza_id": "Q-1",
             "protocollo_quietanza": "26010112345", "movimento_bancario_id": "EC-2026-02-16-1500.00-aa",
             "pagamento_verificato_banca": True, "data_pagamento_effettivo": "2026-02-16",
             "sezione_erario": [{"codice_tributo": "1001", "periodo": "01/2026", "importo_debito": 1500}]},
            {"id": "f24-b", "file_name": "F24_feb.pdf", "quietanza_id": "Q-legacy",
             "allocazioni_banca": [{"movimento_id": "EC-2026-03-16-800.00-bb", "importo": 800}],
             "sezione_erario": [{"codice_tributo": "1001", "periodo": "02/2026", "importo_debito": 800}]},
            {"id": "f24-c", "file_name": "F24_mar.pdf",
             "sezione_erario": [{"codice_tributo": "1001", "periodo": "03/2026", "importo_debito": 900}]},
        ])
        await db["fiscal_documents"].insert_one({"id": "Q-1", "category": "quietanza_f24"})
        await db["quietanze_f24"].insert_one({"id": "Q-legacy"})
        monkeypatch.setattr(f24_analisi.Database, "get_db", lambda: db)
        return await f24_analisi.tabella_analisi(anno=None)

    esito = _run(scenario())
    per_id = {r["f24_id"]: r["documento_collegato"] for r in esito["righe"]}
    assert per_id["f24-a"]["quietanza_url"] == "/api/fiscal/documents/Q-1/content"
    assert per_id["f24-a"]["quietanza_fonte"] == "fiscal_documents"
    assert per_id["f24-a"]["movimento_bancario_id"] == "EC-2026-02-16-1500.00-aa"
    assert per_id["f24-a"]["pagamento_verificato_banca"] is True
    assert per_id["f24-b"]["quietanza_url"] == "/api/f24-riconciliazione/quietanze/Q-legacy"
    assert per_id["f24-b"]["movimenti_bancari_ids"] == ["EC-2026-03-16-800.00-bb"]
    assert per_id["f24-c"] == {
        "quietanza_id": None, "protocollo_quietanza": None, "quietanza_fonte": None,
        "quietanza_url": None, "movimento_bancario_id": None, "movimenti_bancari_ids": [],
        "pagamento_verificato_banca": False, "data_pagamento_effettivo": None,
    }


# ── Movimento banca → fattura / prima nota / stipendio ────────────────────

def test_collegamenti_movimento_usa_i_campi_reali_dell_estratto_conto():
    movimento = {
        "id": "EC-2026-03-30-650.00-b0d9bbbb", "importo": -650.0, "descrizione": "BONIFICO",
        "prima_nota_banca_id": "f9fbf3b7-dd0f-484f-9656-59c723892764",
        "stipendio_id": "ec5d2fde-b9d1-43c2-be55-95c80e1ec420",
        "fattura_id": None, "fattura_ids": ["F-1", "F-2"], "riconciliato": True,
        "tipo_riconciliazione": "stipendio_nome_importo_entro_residuo", "f24_ids": ["f24-a"],
    }
    collegamenti = collegamenti_movimento(movimento)
    assert collegamenti["prima_nota_banca_id"] == "f9fbf3b7-dd0f-484f-9656-59c723892764"
    assert collegamenti["stipendio_id"] == "ec5d2fde-b9d1-43c2-be55-95c80e1ec420"
    assert collegamenti["fattura_id"] == "F-1" and collegamenti["fattura_ids"] == ["F-1", "F-2"]
    assert collegamenti["f24_ids"] == ["f24-a"] and collegamenti["riconciliato"] is True

    risultato = semanticizza_risultato({"suggerimenti": []}, movimento)
    assert risultato["collegamenti"] == collegamenti
    assert risultato["movimento_id"] == movimento["id"]

    vuoto = collegamenti_movimento({"id": "EC-x"})
    assert vuoto["fattura_id"] is None and vuoto["fattura_ids"] == [] and vuoto["f24_ids"] == []
