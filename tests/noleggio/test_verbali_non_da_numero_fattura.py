"""Un numero di fattura non e' un verbale.

69 dei 105 «verbali» in archivio erano numeri di fattura Arval: il pattern
generico `[A-Z]\\d{10,}` girava anche su `invoice_number`, e tutti e 105
puntavano a fatture non piu' esistenti. Ora il numero della fattura non
entra nel testo, il pattern generico vale solo accanto a «verbale»,
«sanzione» o «violazione», e si leggono solo le fatture attive.
"""
import asyncio

from app.constants.stati_verbale import (
    FILTRO_STATO_APERTO,
    STATO_QUARANTENA,
    e_aperto,
    e_chiuso,
)
from app.database import Database
from app.routers import noleggio, verbali_riconciliazione
from app.routers.verbali_riconciliazione import extract_verbale_from_description
from app.services.archivio_documenti_memoria import ArchivioDocumenti
from app.services.verbali_fattura_linker import cerca_fattura_per_verbale


def test_codice_generico_solo_accanto_a_una_parola_di_multa():
    assert extract_verbale_from_description("Canone mensile A25111540620") is None
    assert extract_verbale_from_description("Rif. B12345678901 noleggio") is None
    assert extract_verbale_from_description(
        "Rinotifica sanzione amministrativa A25111540620 Comune di Napoli"
    ) == "A25111540620"
    assert extract_verbale_from_description(
        "Spese violazione CdS Nr: A251115406"
    ) == "A251115406"
    assert extract_verbale_from_description("Verbale N. 12345/2026") == "12345"
    # «Verbale del …» non e' un numero
    assert extract_verbale_from_description("Verbale del mese") is None


def test_scan_fatture_ignora_numero_fattura_e_fatture_archiviate(monkeypatch):
    db = ArchivioDocumenti()

    async def scenario():
        await db["invoices"].insert_many([
            # Numero fattura Arval con la forma di un verbale: non e' un verbale
            {"id": "FT-1", "invoice_number": "A25111540620", "supplier_name": "ARVAL SERVICE LEASE",
             "status": "imported", "linee": [{"descrizione": "Canone di noleggio settembre"}]},
            # Copia archiviata con un verbale vero in riga: non si legge
            {"id": "FT-2", "invoice_number": "A25111540621", "supplier_name": "ARVAL SERVICE LEASE",
             "status": "archived",
             "linee": [{"descrizione": "Rinotifica verbale B12345678901"}]},
            # Fattura attiva con un verbale vero
            {"id": "FT-3", "invoice_number": "A25111540622", "supplier_name": "ARVAL SERVICE LEASE",
             "status": "imported",
             "linee": [{"descrizione": "Spese notifica sanzione B99999999999"}]},
        ])
        await verbali_riconciliazione.scan_fatture_per_verbali()
        return await db["verbali_noleggio"].find({}, {"_id": 0}).to_list(None)

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    verbali = asyncio.run(scenario())
    assert [(v["numero_verbale"], v["fattura_id"]) for v in verbali] == [("B99999999999", "FT-3")]


def test_linker_legge_solo_fatture_attive():
    async def scenario():
        db = ArchivioDocumenti()
        await db["invoices"].insert_many([
            {"id": "FT-ARCH", "supplier_name": "LEASYS", "status": "archiviata",
             "linee": [{"descrizione": "Verbale B12345678901"}]},
        ])
        prima = await cerca_fattura_per_verbale(db, "B12345678901")
        await db["invoices"].insert_one(
            {"id": "FT-VIVA", "supplier_name": "LEASYS", "status": "imported",
             "linee": [{"descrizione": "Verbale B12345678901"}]},
        )
        dopo = await cerca_fattura_per_verbale(db, "B12345678901")
        return prima, dopo

    prima, dopo = asyncio.run(scenario())
    assert prima is None
    assert dopo["fattura_id"] == "FT-VIVA"


def test_quarantena_non_e_ne_aperto_ne_pagato_ma_chiuso():
    assert not e_aperto(STATO_QUARANTENA)
    assert STATO_QUARANTENA not in FILTRO_STATO_APERTO["stato"]["$in"]
    assert e_chiuso(STATO_QUARANTENA)
    assert e_chiuso("PAGATO") and e_chiuso("riconciliato") and e_chiuso("chiuso")
    assert not e_chiuso("fattura_ricevuta")


def test_cruscotto_noleggio_usa_vocabolario_unico_e_fatture_attive(monkeypatch):
    db = ArchivioDocumenti()
    piva_ald = next(iter(noleggio.FORNITORI_NOLEGGIO.values()))

    async def scenario():
        await db[noleggio.COLLECTION_VERBALI_POSTA].insert_many([
            {"numero_verbale": "V-PAGATO", "stato": "riconciliato"},
            {"numero_verbale": "V-QUAR", "stato": STATO_QUARANTENA},
            {"numero_verbale": "V-APERTO", "stato": "fattura_ricevuta"},
        ])
        await db["invoices"].insert_many([
            {"id": "I-1", "supplier_vat": piva_ald, "invoice_date": "2026-03-01",
             "total_amount": 10, "status": "imported"},
            {"id": "I-1-copia", "supplier_vat": piva_ald, "invoice_date": "2026-03-01",
             "total_amount": 10, "status": "archived"},
        ])

        async def nessuna(anno=None):
            return {"fatture": []}

        monkeypatch.setattr(noleggio, "get_fatture_non_associate", nessuna)
        return await noleggio.get_riepilogo_controlli(anno=2026, offset=0, limit=10)

    monkeypatch.setattr(noleggio.Database, "get_db", staticmethod(lambda: db))
    risultato = asyncio.run(scenario())
    aperti = [v["numero_verbale"] for v in risultato["verbali_aperti"]["items"]]
    assert aperti == ["V-APERTO"]
    assert risultato["pagamenti_non_riconciliati"]["count"] == 1
