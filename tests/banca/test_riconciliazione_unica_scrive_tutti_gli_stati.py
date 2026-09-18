"""Audit del commercialista 03/09/2026 §1, PR 2: un solo motore fattura↔banca.

Riproduce i casi reali del report:
- Enel 2.787,08 (SDD 23/02, fattura 08/02): prima il motore storico scriveva
  Prima Nota "riconciliata" lasciando EC non riconciliato, scadenza e partita
  aperte. Ora l'abbinamento certo passa da ``persist_bank_invoice_allocations``
  e i cinque oggetti (fattura, scadenza, partita, EC, Prima Nota) + la
  relazione in ``entity_relations`` risultano coerenti, con lo stesso
  ``operation_id``;
- Fastweb 43,86 (SDD 25/03, fattura 01/04): pagamento antecedente alla
  fattura → mai automatico, proposta in ``operazioni_da_confermare``;
- bonifica dei casi storici: riga scritta dal motore storico riallineata
  con il motore canonico; fattura assente / data antecedente → proposte;
  secondo giro senza scritture.
"""
import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.services import riallinea_pagamenti_fatture as riallinea
from app.services import riconciliazione_bancaria as ric


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


ENEL_ID = "861d279d-eb50-4e9a-9ed0-faa1380e3e0a"
ENEL_EC = "EC-2026-02-23-2787.08-ba4b1d14"
FASTWEB_ID = "a1623f1f-a392-414a-8e42-288d9a49d54b"
FASTWEB_EC = "EC-2026-03-25-43.86-23e69765"


def _fattura_enel():
    return {
        "id": ENEL_ID, "invoice_number": "005410193815", "numero_fattura": "005410193815",
        "supplier_name": "Enel Energia S.p.A.", "cedente_denominazione": "Enel Energia S.p.A.",
        "supplier_vat": "15844561009", "invoice_date": "2026-02-08", "data": "2026-02-08",
        "total_amount": 2787.08, "importo_totale": 2787.08, "tipo_documento": "TD01",
    }


def _ec_enel(**extra):
    return {
        "id": ENEL_EC, "data": "2026-02-23", "tipo": "uscita", "importo": 2787.08,
        "descrizione": "SDD CORE: 2C1071107297049T ENEL ENERGIA",
        "descrizione_originale": "SDD CORE: 2C1071107297049T ENEL ENERGIA",
        "operation_id": "bank:18d15cbb91297016a32e4c532f3fde0f7ad2d22f1bb6da5bd7cb8e559593d943",
        "riconciliato": False, "livello_evidenza": "ufficiale", **extra,
    }


def _scadenza_enel():
    return {
        "id": f"{ENEL_ID}::0::0", "fattura_id": ENEL_ID, "numero_fattura": "005410193815",
        "fornitore_nome": "Enel Energia S.p.A.", "data_fattura": "2026-02-08",
        "data_scadenza": "2026-02-23", "importo_rata": 2787.08, "importo_totale": 2787.08,
        "pagato": False, "stato": "aperta", "rata_indice": 0, "blocco_indice": 0,
    }


def _partita_enel():
    return {
        "id": "pa_8d726b2b5e2f", "tipo": "fattura_fornitore", "documento_id": ENEL_ID,
        "documento_collection": "invoices", "controparte_nome": "Enel Energia S.p.A.",
        "importo_originale": 2787.08, "residuo": 2787.08, "stato": "aperta", "match_ids": [],
    }


async def _stati(db):
    fattura = await db.invoices.find_one({"id": ENEL_ID}, {"_id": 0})
    ec = await db.estratto_conto_movimenti.find_one({"id": ENEL_EC}, {"_id": 0})
    pn = await db.prima_nota_banca.find(
        {"fattura_id": ENEL_ID, "status": {"$nin": ["deleted", "archived"]}}, {"_id": 0},
    ).to_list(10)
    scadenza = await db.scadenziario_fornitori.find_one({"fattura_id": ENEL_ID}, {"_id": 0})
    partita = await db.partite_aperte.find_one({"documento_id": ENEL_ID}, {"_id": 0})
    relazioni = await db.entity_relations.find({}, {"_id": 0}).to_list(50)
    allocazioni = await db.bank_payment_allocations.find({}, {"_id": 0}).to_list(50)
    return fattura, ec, pn, scadenza, partita, relazioni, allocazioni


def _verifica_coerenza(fattura, ec, pn, scadenza, partita, relazioni, allocazioni):
    assert fattura["pagato"] is True and fattura["stato_pagamento"] == "pagata"
    assert fattura["movimento_bancario_id"] == ENEL_EC
    assert fattura["data_pagamento"] == "2026-02-23"
    assert ec["riconciliato"] is True and ec["fattura_id"] == ENEL_ID
    assert len(pn) == 1
    riga = pn[0]
    assert riga["riconciliato"] is True and riga["estratto_conto_id"] == ENEL_EC
    assert riga["categoria"] == "Fatture"
    # conti CEE (PR 7) sulla riga scritta dal motore unico
    assert riga["conto_contabile"] == "19.01.01"
    assert riga["conto_contropartita"] == "33.03.01"
    assert scadenza["pagato"] is True and scadenza["stato"] == "pagata"
    assert scadenza["evidenze_pagamento"][0]["evidenza_id"] == f"banca:{ENEL_EC}:{ENEL_ID}"
    assert partita["stato"] == "chiusa" and partita["residuo"] == 0.0
    # un solo operation_id attraversa fattura, EC, Prima Nota e allocazione
    op = ec["operation_id"]
    assert op == "bank:18d15cbb91297016a32e4c532f3fde0f7ad2d22f1bb6da5bd7cb8e559593d943"
    assert riga["operation_id"] == op and fattura["payment_operation_id"] == op
    assert len(allocazioni) == 1 and allocazioni[0]["operation_id"] == op
    assert allocazioni[0]["allocation_id"] == f"bank:{ENEL_EC}:{ENEL_ID}"
    assert fattura["prima_nota_banca_id"] == riga["id"]
    tipi = {r["relation_type"] for r in relazioni}
    assert "allocates_invoice_payment" in tipi
    assert "represented_by_prima_nota" in tipi and "posted_in_prima_nota" in tipi
    rel = next(r for r in relazioni if r["relation_type"] == "allocates_invoice_payment")
    assert rel["source"] == {"type": "bank_movement", "id": ENEL_EC}
    assert rel["target"] == {"type": "invoice", "id": ENEL_ID}
    assert rel["status"] == "confirmed"


def test_abbinamento_certo_aggiorna_i_cinque_oggetti_e_la_relazione(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["ric_unica_enel"]
        await db.invoices.insert_one(_fattura_enel())
        await db.estratto_conto_movimenti.insert_one(_ec_enel())
        await db.scadenziario_fornitori.insert_one(_scadenza_enel())
        await db.partite_aperte.insert_one(_partita_enel())
        monkeypatch.setattr(ric.Database, "get_db", staticmethod(lambda: db))

        esito = await ric.riconcilia_movimenti_banca(movimento_ids=[ENEL_EC])
        assert esito["riconciliati_fatture"] == 1, esito
        stati = await _stati(db)
        _verifica_coerenza(*stati)
        # il motore storico non scrive piu' nulla per conto suo
        assert stati[2][0]["source"] != "ric_auto_identita_unica"
        assert await db.operazioni_da_confermare.count_documents({}) == 0

        # idempotente: un secondo giro non crea una seconda riga/allocazione
        await ric.riconcilia_movimenti_banca(movimento_ids=[ENEL_EC])
        assert await db.prima_nota_banca.count_documents({}) == 1
        assert await db.bank_payment_allocations.count_documents({}) == 1

    _run(scenario())


def test_movimento_antecedente_alla_fattura_diventa_proposta(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["ric_unica_fastweb"]
        await db.invoices.insert_one({
            "id": FASTWEB_ID, "invoice_number": "M012842207", "supplier_name": "FASTWEB SpA",
            "cedente_denominazione": "FASTWEB SpA", "supplier_vat": "12878470157",
            "invoice_date": "2026-04-01", "data": "2026-04-01",
            "total_amount": 43.86, "importo_totale": 43.86, "tipo_documento": "TD01",
        })
        await db.estratto_conto_movimenti.insert_one({
            "id": FASTWEB_EC, "data": "2026-03-25", "tipo": "uscita", "importo": 43.86,
            "descrizione": "SDD CORE: FASTWEB SPA", "descrizione_originale": "SDD CORE: FASTWEB SPA",
            "riconciliato": False, "livello_evidenza": "ufficiale",
        })
        monkeypatch.setattr(ric.Database, "get_db", staticmethod(lambda: db))

        esito = await ric.riconcilia_movimenti_banca(movimento_ids=[FASTWEB_EC])

        assert esito["riconciliati_fatture"] == 0
        fattura = await db.invoices.find_one({"id": FASTWEB_ID})
        ec = await db.estratto_conto_movimenti.find_one({"id": FASTWEB_EC})
        assert not fattura.get("pagato") and not ec.get("riconciliato")
        assert await db.prima_nota_banca.count_documents({}) == 0
        proposte = await db.operazioni_da_confermare.find({}, {"_id": 0}).to_list(10)
        assert len(proposte) == 1
        assert proposte[0]["match_type"] == "pagamento_antecedente_fattura"
        assert proposte[0]["movimento_ec_id"] == FASTWEB_EC
        assert proposte[0]["dettagli"]["fatture_candidate"][0]["id"] == FASTWEB_ID
        # lo scheduler rilancia ogni 30 minuti: una sola proposta per movimento
        await ric.riconcilia_movimenti_banca(movimento_ids=[FASTWEB_EC])
        assert await db.operazioni_da_confermare.count_documents({}) == 1

    _run(scenario())


def _riga_storica(pn_id, fattura_id, ec_id, data, importo):
    """Riga scritta dal motore storico il 29/08/2026 (source ric_auto_identita_unica)."""
    return {
        "id": pn_id, "data": data, "tipo": "uscita", "importo": importo,
        "categoria": "Fatture", "descrizione": "Pagamento SDD/RID fattura",
        "source": "ric_auto_identita_unica", "fattura_id": fattura_id, "invoice_id": fattura_id,
        "estratto_conto_id": ec_id, "movimento_estratto_conto_id": ec_id,
        "riconciliato": True, "riconciliazione_automatica": True,
        "created_at": "2026-08-29T14:09:22+00:00",
    }


def _db_bonifica():
    db = MemorySheetsClient()["riallinea_pagamenti"]

    async def semina():
        # caso Enel: PN "riconciliata", EC no, scadenza e partita aperte
        await db.invoices.insert_one(_fattura_enel())
        await db.estratto_conto_movimenti.insert_one(_ec_enel())
        await db.scadenziario_fornitori.insert_one(_scadenza_enel())
        await db.partite_aperte.insert_one(_partita_enel())
        await db.prima_nota_banca.insert_one(
            _riga_storica("d9fd42e5", ENEL_ID, ENEL_EC, "2026-02-23", 2787.08))
        # caso GSM Marmi: fattura non in archivio
        await db.estratto_conto_movimenti.insert_one({
            "id": "EC-2026-03-10-793.00-20905b2d", "data": "2026-03-10", "tipo": "uscita",
            "importo": 793.0, "descrizione": "VS.DISP. FAVORE GSM MARMI SBORDONE",
            "riconciliato": True, "tipo_riconciliazione": "fattura_match_completo",
        })
        await db.prima_nota_banca.insert_one(_riga_storica(
            "22ef6809", "89231444-d243-4140-adb0-51ac412223a5",
            "EC-2026-03-10-793.00-20905b2d", "2026-03-10", 793.0))
        # caso Fastweb: pagata 7 giorni prima della fattura
        await db.invoices.insert_one({
            "id": FASTWEB_ID, "invoice_number": "M012842207", "supplier_name": "FASTWEB SpA",
            "supplier_vat": "12878470157", "invoice_date": "2026-04-01",
            "total_amount": 43.86, "tipo_documento": "TD01",
        })
        await db.estratto_conto_movimenti.insert_one({
            "id": FASTWEB_EC, "data": "2026-03-25", "tipo": "uscita", "importo": 43.86,
            "descrizione": "SDD CORE: FASTWEB SPA", "riconciliato": False,
        })
        await db.prima_nota_banca.insert_one(
            _riga_storica("af37f6fe", FASTWEB_ID, FASTWEB_EC, "2026-03-25", 43.86))
        # riga marcata dalla bonifica doppioni: non conta
        await db.prima_nota_banca.insert_one({
            **_riga_storica("vecchia", ENEL_ID, ENEL_EC, "2026-02-23", 2787.08),
            "status": "deleted", "entity_status": "deleted",
        })

    _run(semina())
    return db


def test_bonifica_dry_run_classifica_senza_scrivere():
    db = _db_bonifica()

    esito = _run(riallinea.esegui(db, dry_run=True))

    assert esito["dry_run"] is True
    assert esito["righe_esaminate"] == 3
    assert esito["riallineabili"] == 1 and esito["proposte"] == 2 and esito["coerenti"] == 0
    assert esito["motivi_proposte"] == {"fattura_assente": 1, "pagamento_antecedente_fattura": 1}
    per_id = {r["prima_nota_id"]: r for r in esito["righe"]}
    assert per_id["d9fd42e5"]["esito"] == "riallineabile"
    assert per_id["22ef6809"]["motivi"] == ["fattura_assente"]
    assert per_id["af37f6fe"]["motivi"] == ["pagamento_antecedente_fattura"]
    # nulla e' cambiato
    assert _run(db.operazioni_da_confermare.count_documents({})) == 0
    assert _run(db.bank_payment_allocations.count_documents({})) == 0
    assert not _run(db.invoices.find_one({"id": ENEL_ID})).get("pagato")


def test_bonifica_applica_riallinea_con_il_motore_canonico_ed_e_idempotente():
    db = _db_bonifica()

    esito = _run(riallinea.esegui(db, dry_run=False, actor="test"))

    assert esito["dry_run"] is False
    assert esito["riallineate"] == 1
    assert esito["proposte_create"] == 2 and esito["proposte_gia_presenti"] == 0
    assert esito["rifiutate_dal_motore"] == []
    assert esito["scritture"] == 3

    stati = _run(_stati(db))
    _verifica_coerenza(*stati)
    # la riga storica e' stata completata, non affiancata da un doppione
    assert stati[2][0]["id"] == "d9fd42e5"
    assert _run(db.prima_nota_banca.count_documents({"fattura_id": ENEL_ID, "status": {"$ne": "deleted"}})) == 1

    proposte = _run(db.operazioni_da_confermare.find({}, {"_id": 0}).to_list(10))
    assert {p["movimento_ec_id"] for p in proposte} == {"EC-2026-03-10-793.00-20905b2d", FASTWEB_EC}
    assert all(p["match_type"] == "riallineamento_pagamento_fattura" for p in proposte)
    fastweb = next(p for p in proposte if p["movimento_ec_id"] == FASTWEB_EC)
    assert fastweb["dettagli"]["motivi"] == ["pagamento_antecedente_fattura"]
    assert fastweb["dettagli"]["prima_nota_banca_id"] == "af37f6fe"
    # le righe non risolvibili restano com'erano: nessuna scrittura di stato
    assert not _run(db.invoices.find_one({"id": FASTWEB_ID})).get("pagato")
    assert _run(db.audit_log.count_documents({})) >= 0

    # secondo giro: 0 scritture
    di_nuovo = _run(riallinea.esegui(db, dry_run=False, actor="test"))
    assert di_nuovo["coerenti"] == 1 and di_nuovo["riallineabili"] == 0
    assert di_nuovo["riallineate"] == 0
    assert di_nuovo["proposte_create"] == 0 and di_nuovo["proposte_gia_presenti"] == 2
    assert di_nuovo["scritture"] == 0
    assert _run(db.operazioni_da_confermare.count_documents({})) == 2
    assert _run(db.bank_payment_allocations.count_documents({})) == 1
    assert _run(db.prima_nota_migrazioni_audit.count_documents({})) == 1


def test_analisi_all_avvio_e_solo_dry_run():
    db = _db_bonifica()
    esito = _run(riallinea.analizza_avvio(db, actor="migrazione_avvio"))
    assert esito["dry_run"] is True and esito["applicata"] is False
    assert esito["riallineabili"] == 1 and esito["proposte"] == 2
    assert _run(db.operazioni_da_confermare.count_documents({})) == 0
    assert not _run(db.invoices.find_one({"id": ENEL_ID})).get("pagato")


def test_endpoint_admin_dry_run_e_applica(monkeypatch):
    from app.database import Database
    from app.routers.admin import riallinea_pagamenti_fatture

    db = _db_bonifica()
    monkeypatch.setattr(Database, "db", db)
    utente = {"sub": "admin-test", "role": "admin"}
    analisi = _run(riallinea_pagamenti_fatture(dry_run=True, current_user=utente))
    assert analisi["dry_run"] is True and analisi["righe_esaminate"] == 3
    applicata = _run(riallinea_pagamenti_fatture(dry_run=False, current_user=utente))
    assert applicata["riallineate"] == 1 and applicata["proposte_create"] == 2
