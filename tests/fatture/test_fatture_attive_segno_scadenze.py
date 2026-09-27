"""Fatture attive, segno delle note di credito, niente scadenze inventate.

Collaudo sui dati del 27/09/2026: in `invoices` ogni fattura 2026 esiste due
volte (563 copie `archived`, 706 `imported`, 249 senza `status`). Chi leggeva
l'archivio senza il filtro «fattura attiva» contava due volte; chi calcolava
«pagata» a mano perdeva le 639 fatture con il solo `stato = "pagata"`; chi
sommava le note di credito le aggiungeva al debito invece di toglierle; e
tre pagine inventavano una scadenza (`data + 30`, o la data della fattura)
per fatture che non ne hanno. Ogni test qui riproduce un caso di quelli.
"""
import asyncio
import re
from pathlib import Path

import pytest

from app.constants.metodi_pagamento import METODI_NON_CONFIGURATI
from app.database import Database
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.fattura_attiva import (
    FILTRO_FATTURA_ATTIVA,
    e_fattura_attiva,
    importo_documento_con_segno,
    importo_pagabile_con_segno,
)

RADICE = Path(__file__).resolve().parents[2]
PIVA_FORNITORE = "04518411212"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def db(monkeypatch, request):
    database = ClientArchivioMemoria()[f"attive-{request.node.name}"]
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: database))
    return database


def _fatture_fornitore():
    """Quattro righe come in produzione: attiva aperta, attiva pagata (solo
    `stato`), copia archiviata della aperta, nota di credito aperta."""
    base = {"supplier_vat": PIVA_FORNITORE, "supplier_name": "Fornitore Srl"}
    return [
        {**base, "id": "F1", "invoice_number": "1/26", "invoice_date": "2026-03-10",
         "total_amount": 100.0, "imponibile": 82.0, "iva": 18.0,
         "tipo_documento": "TD01", "status": "imported",
         "stato_pagamento": "da_pagare", "data_scadenza": "2026-04-09"},
        {**base, "id": "F2", "invoice_number": "2/26", "invoice_date": "2026-05-10",
         "total_amount": 200.0, "imponibile": 164.0, "iva": 36.0,
         "tipo_documento": "TD01", "stato": "pagata"},
        {**base, "id": "F1-arch", "invoice_number": "1/26", "invoice_date": "2026-03-10",
         "total_amount": 100.0, "tipo_documento": "TD01", "status": "archived"},
        {**base, "id": "NC1", "invoice_number": "NC1/26", "invoice_date": "2026-06-01",
         "total_amount": 30.0, "imponibile": 24.6, "iva": 5.4,
         "tipo_documento": "TD04"},
    ]


# ── il posto unico ─────────────────────────────────────────────────────────

def test_filtro_attivo_in_un_posto_solo():
    from app.services.fatture_report_ae import FILTRO_FATTURE_ATTIVE
    from app.services.noleggio.processors import FILTRO_FATTURA_ATTIVA as da_noleggio

    assert da_noleggio is FILTRO_FATTURA_ATTIVA
    assert FILTRO_FATTURE_ATTIVE is FILTRO_FATTURA_ATTIVA
    assert set(FILTRO_FATTURA_ATTIVA["status"]["$nin"]) == {"archived", "archiviata", "deleted"}
    assert e_fattura_attiva({"status": "imported"})
    assert e_fattura_attiva({})  # campo assente = attiva
    assert not e_fattura_attiva({"status": "archiviata"})
    assert not e_fattura_attiva({"stato_import": "collisione_identita_da_verificare"})


def test_segno_nota_credito_e_netto_ritenuta():
    assert importo_documento_con_segno({"total_amount": 30, "tipo_documento": "TD04"}) == -30
    assert importo_documento_con_segno({"total_amount": -30, "tipo_documento": "TD08"}) == -30
    # TD05 e' una nota di DEBITO: resta positiva
    assert importo_documento_con_segno({"total_amount": 30, "tipo_documento": "TD05"}) == 30
    parcella = {"total_amount": 3806.40, "importo_ritenuta": 600, "tipo_documento": "TD06"}
    assert importo_pagabile_con_segno(parcella) == 3206.40


# ── 1. lista fornitori ─────────────────────────────────────────────────────

def test_lista_fornitori_conta_solo_attive_con_segno_e_pagata_canonica(db):
    from app.routers.suppliers_module import base

    async def scenario():
        await db["fornitori"].insert_one(
            {"id": "s1", "partita_iva": PIVA_FORNITORE, "ragione_sociale": "Fornitore Srl"})
        await db["invoices"].insert_many(_fatture_fornitore())
        return await base.list_suppliers(
            skip=0, limit=500, search=None, metodo_pagamento=None, attivo=None,
            esclude_magazzino=None, stato_anagrafica=None, giorni_nuovo=90,
            prodotto=None, use_cache=False,
        )

    [fornitore] = _run(scenario())
    assert fornitore["fatture_count"] == 3              # non 4: la copia archiviata fuori
    assert fornitore["fatture_totale"] == 270.0         # 100 + 200 - 30
    assert fornitore["fatture_pagate"] == 200.0         # il solo `stato = pagata` basta
    assert fornitore["fatture_non_pagate"] == 70.0      # 100 - 30
    assert fornitore["fatture_non_pagate_count"] == 2


# ── 2. fatturato ed estratto del fornitore ─────────────────────────────────

def test_fatturato_ed_estratto_fornitore(db):
    from app.routers.suppliers_module import base

    async def scenario():
        await db["fornitori"].insert_one(
            {"id": "s1", "partita_iva": PIVA_FORNITORE, "ragione_sociale": "Fornitore Srl"})
        await db["invoices"].insert_many(_fatture_fornitore() + [
            {"id": "ND1", "supplier_vat": PIVA_FORNITORE, "invoice_number": "ND1",
             "invoice_date": "2026-07-01", "total_amount": 5.0, "tipo_documento": "TD05"},
        ])
        fatturato = await base.get_supplier_fatturato("s1", anno=2026)
        estratto = await base.get_fatture_fornitore(
            "s1", anno=None, data_da=None, data_a=None, importo_min=None,
            importo_max=None, tipo=None, limit=100, skip=0)
        solo_nc = await base.get_fatture_fornitore(
            "s1", anno=None, data_da=None, data_a=None, importo_min=None,
            importo_max=None, tipo="nota_credito", limit=100, skip=0)
        return fatturato, estratto, solo_nc

    fatturato, estratto, solo_nc = _run(scenario())
    assert fatturato["numero_fatture"] == 4
    assert fatturato["totale_fatturato"] == 275.0
    assert fatturato["fatture_pagate"] == 1 and fatturato["importo_pagato"] == 200.0
    assert fatturato["fatture_non_pagate"] == 3 and fatturato["importo_non_pagato"] == 75.0

    righe = estratto["estratto"]
    assert [r["id"] for r in righe] == ["ND1", "NC1", "F2", "F1"]  # invoice_date desc
    per_id = {r["id"]: r for r in righe}
    assert per_id["NC1"]["importo_totale"] == -30.0 and per_id["NC1"]["is_nota_credito"]
    assert per_id["ND1"]["importo_totale"] == 5.0 and not per_id["ND1"]["is_nota_credito"]
    assert per_id["F2"]["pagato"] is True
    assert estratto["totali"]["importo_totale"] == 275.0
    assert [r["id"] for r in solo_nc["estratto"]] == ["NC1"]


# ── 3-4. scadenze: le fatture fornitore non ne hanno ──────────────────────

def test_scadenze_non_generano_righe_per_fatture_fornitore(db, monkeypatch):
    from app.routers import scadenze

    monkeypatch.setattr(scadenze, "_genera_scadenze_fiscali", lambda *_a: [])

    async def scenario():
        await db["invoices"].insert_many(_fatture_fornitore())
        tutte = await scadenze.get_tutte_scadenze(
            anno=2026, mese=None, tipo=None, include_passate=True, limit=500, offset=0)
        solo_fatture = await scadenze.get_tutte_scadenze(
            anno=2026, mese=None, tipo="FATTURA", include_passate=True, limit=500, offset=0)
        prossime = await scadenze.get_prossime_scadenze(giorni=3650, limit=100)
        widget = await scadenze.get_dashboard_scadenze()
        return tutte, solo_fatture, prossime, widget

    tutte, solo_fatture, prossime, widget = _run(scenario())
    assert tutte["scadenze"] == [] and solo_fatture["scadenze"] == []
    assert prossime["scadenze"] == []
    # la fattura F1 ha una `data_scadenza` passata e stato da_pagare: non
    # accende piu' l'alert rosso
    assert "fatture" not in widget
    assert widget["totale_alert"] == 0


# ── 5. scadenzario fornitori ──────────────────────────────────────────────

def test_scadenzario_fornitori_senza_scadute(db):
    from app.routers import scadenzario_fornitori as sf

    async def scenario():
        await db["invoices"].insert_many(_fatture_fornitore())
        aperte = await sf.get_scadenzario(anno=2026, fornitore=None, stato="aperte",
                                          giorni_scadenza=None)
        scadute = await sf.get_scadenzario(anno=2026, fornitore=None, stato="scadute",
                                           giorni_scadenza=None)
        urgenti = await sf.get_scadenze_urgenti()
        return aperte, scadute, urgenti

    aperte, scadute, urgenti = _run(scenario())
    riepilogo = aperte["riepilogo"]
    assert riepilogo["totale_fatture"] == 2                  # F1 e NC1: F2 pagata, copia fuori
    assert riepilogo["totale_da_pagare"] == 70.0             # 100 - 30
    assert riepilogo["num_scadute"] == 0 and riepilogo["totale_scaduto"] == 0
    assert {f["id"] for f in aperte["da_pagare"]} == {"F1", "NC1"}
    assert scadute["riepilogo"]["totale_fatture"] == 0
    assert urgenti["num_urgenti"] == 0 and urgenti["fatture"] == []


# ── 6-7-12-13. archivio e statistiche fatture ricevute ─────────────────────

def test_statistiche_note_credito_in_negativo(db):
    from app.routers.fatture_module import crud

    async def scenario():
        await db["invoices"].insert_many(_fatture_fornitore())
        return await crud.get_statistiche(anno=2026)

    stats = _run(scenario())
    assert stats["totale_fatture"] == 3
    assert stats["importo_totale"] == 270.0
    assert stats["pagate"] == 1 and stats["importo_pagato"] == 200.0
    assert stats["fatture_anomale"] == 0  # una nota di credito negativa non e' anomala


def test_archivio_esclude_archiviate_ed_emesse(db, monkeypatch):
    from app.routers.fatture_module import crud
    from app.services import fatture_emesse

    monkeypatch.setattr(fatture_emesse.settings, "FISCAL_COMPANY_ID", "IT09999999999")

    async def scenario():
        await db["invoices"].insert_many(_fatture_fornitore() + [
            # fattura EMESSA da noi, rimasta attiva fra le ricevute
            {"id": "EM1", "supplier_vat": "09999999999", "invoice_number": "E1",
             "invoice_date": "2026-04-01", "total_amount": 50.0},
        ])
        tutte = await crud.get_archivio_fatture(
            anno=2026, mese=None, fornitore_piva=None, fornitore_nome=None,
            stato=None, search=None, limit=200, skip=0)
        pagate = await crud.get_archivio_fatture(
            anno=2026, mese=None, fornitore_piva=None, fornitore_nome=None,
            stato="pagata", search=None, limit=200, skip=0)
        importate = await crud.get_archivio_fatture(
            anno=2026, mese=None, fornitore_piva=None, fornitore_nome=None,
            stato="importata", search=None, limit=200, skip=0)
        return tutte, pagate, importate

    tutte, pagate, importate = _run(scenario())
    assert {f["id"] for f in tutte["fatture"]} == {"F1", "F2", "NC1"}
    assert {f["id"] for f in pagate["fatture"]} == {"F2"}           # il solo `stato`
    assert {f["id"] for f in importate["fatture"]} == {"F1", "NC1"}
    nc = next(f for f in tutte["fatture"] if f["id"] == "NC1")
    assert nc["importo_totale"] == -30.0


def test_normalizzatore_non_inventa_imponibile_ne_iva():
    from app.routers.fatture_module.crud import _normalizza_da_invoices

    senza = _normalizza_da_invoices({"id": "x", "total_amount": 110.0, "iva": 10.0})
    assert senza["imponibile"] is None           # non 90,16 da `totale / 1.22`
    assert senza["iva"] == 10.0                  # l'IVA vera non si sovrascrive
    assert senza["importi_da_verificare"] is True

    zero = _normalizza_da_invoices({"id": "y", "total_amount": 122.0, "imponibile": 0})
    assert zero["imponibile"] is None and zero["iva"] is None
    assert zero["importi_da_verificare"] is True

    buona = _normalizza_da_invoices(
        {"id": "z", "total_amount": 110.0, "imponibile": 100.0, "iva": 10.0})
    assert (buona["imponibile"], buona["iva"], buona["importi_da_verificare"]) == (100.0, 10.0, False)

    esente = _normalizza_da_invoices(
        {"id": "w", "total_amount": 100.0, "imponibile": 100.0, "iva": 0})
    assert esente["iva"] == 0.0 and esente["importi_da_verificare"] is False


# ── 8. «senza metodo»: un vocabolario solo, anche lato schermo ────────────

def test_vocabolario_metodo_non_configurato_uguale_in_javascript():
    testo = (RADICE / "frontend/src/utils/metodoPagamento.js").read_text(encoding="utf-8")
    m = re.search(r"export const METODI_NON_CONFIGURATI = \[(.*?)\];", testo, re.S)
    assert m, "lista non trovata nel gemello JavaScript"
    assert set(re.findall(r"'([^']*)'", m.group(1))) == set(METODI_NON_CONFIGURATI)
    pagina = (RADICE / "frontend/src/pages/ArchivioFattureRicevute.jsx").read_text(encoding="utf-8")
    assert "metodoNonConfigurato(f.fornitore_metodo_pagamento)" in pagina
    assert "m === 'misto'" not in pagina


# ── 9-10. bonifici: netto della ritenuta, niente copie archiviate ─────────

def test_bonifico_paga_il_netto_della_ritenuta():
    from app.services.payment_document_links import valuta_fattura_bonifico

    bonifico = {"importo": 3206.40, "causale": "SALDO FATTURA FPR 14/26 AVV. CARINI",
                "beneficiario": {"nome": "AVV. CARINI"}}
    parcella = {"id": "P1", "invoice_number": "FPR 14/26", "supplier_name": "AVV. CARINI",
                "total_amount": 3806.40, "importo_ritenuta": 600.0}
    esito = valuta_fattura_bonifico(bonifico, parcella)
    assert "importo_esatto" in esito["evidenze"]
    assert esito["compatibile"] is True
    assert esito["importo_fattura"] == 3206.40


def test_abbinamento_automatico_ignora_la_copia_archiviata(db):
    from app.services.bonifici_pdf_ingest import associa_transfer_a_fatture

    fattura = {"invoice_number": "FPR 14/26", "supplier_name": "AVV. CARINI",
               "total_amount": 3806.40, "importo_ritenuta": 600.0,
               "invoice_date": "2026-02-01"}
    bonifico = {"id": "B1", "importo": 3206.40,
                "causale": "SALDO FATTURA FPR 14/26 AVV. CARINI",
                "beneficiario": {"nome": "AVV. CARINI"}}

    async def scenario():
        await db["invoices"].insert_many([
            {**fattura, "id": "P1", "status": "imported"},
            {**fattura, "id": "P1-arch", "status": "archived"},
        ])
        await db["bonifici_transfers"].insert_one(dict(bonifico))
        return await associa_transfer_a_fatture(db, bonifico)

    esito = _run(scenario())
    assert esito == {"associato": True, "fattura_ids": ["P1"]}


def test_candidati_manuali_attivi_non_pagati_e_al_netto(db):
    from app.routers.bonifici_module import associazioni

    fattura = {"invoice_number": "FPR 14/26", "supplier_name": "AVV. CARINI",
               "total_amount": 3806.40, "importo_ritenuta": 600.0}

    async def scenario():
        await db["bonifici_transfers"].insert_one(
            {"id": "B1", "importo": 3206.40, "causale": "FATTURA FPR 14/26 AVV. CARINI",
             "beneficiario": {"nome": "AVV. CARINI"}})
        await db["invoices"].insert_many([
            {**fattura, "id": "P1"},
            {**fattura, "id": "P1-arch", "status": "archived"},
            {**fattura, "id": "P1-pagata", "stato": "pagata"},
        ])
        return await associazioni.get_fatture_compatibili("B1")

    esito = _run(scenario())
    assert [f["id"] for f in esito["fatture_compatibili"]] == ["P1"]
    assert esito["fatture_compatibili"][0]["importo"] == 3206.40


# ── 13. bonifici: l'anno che la pagina manda ──────────────────────────────

def test_bonifici_contatore_e_riconciliazione_per_anno(db):
    from app.routers.bonifici_module.riconciliazione import stato_riconciliazione_bonifici
    from app.routers.bonifici_module.transfers import count_transfers

    async def scenario():
        await db["bonifici_transfers"].insert_many([
            {"id": "a", "data": "2025-12-30", "importo": 10.0, "riconciliato": True},
            {"id": "b", "data": "2026-01-05", "importo": 20.0, "riconciliato": True},
            {"id": "c", "data": "2026-02-05", "importo": 30.0},
        ])
        return (await count_transfers(job_id=None, anno=2026),
                await count_transfers(job_id=None, anno=None),
                await stato_riconciliazione_bonifici(anno=2026))

    anno, tutti, stato = _run(scenario())
    assert anno == {"count": 2} and tutti == {"count": 3}
    assert stato["totale"] == 2 and stato["riconciliati"] == 1
    assert stato["importo_riconciliato"] == 20.0
    assert stato["importo_non_riconciliato"] == 30.0
