"""Bonifiche automatiche del job bancario corto: solo per id, col motivo,
idempotenti, esito in `sistema_stato`. Niente si cancella."""
import asyncio
from pathlib import Path

from app.services.archivio_documenti_memoria import ArchivioDocumenti
from app.services.bonifiche_automatiche import (
    CHIAVE_STATO,
    MOTIVO_FATTURE_SENZA_SCADENZA,
    esegui_bonifiche,
    numero_derivato_da_fattura,
)

RADICE = Path(__file__).resolve().parents[2]


def _alert(aid, codice, entita, created="2026-09-01T00:00:00", stato="aperto"):
    return {"id": aid, "codice": codice, "entita_id": entita, "stato": stato,
            "created_at": created, "risolto": stato != "aperto"}


async def _prepara(db):
    await db["alerts"].insert_many([
        _alert("A-FAT-1", "FAT_DA_PAGARE_SCADUTA", "inv-1"),
        _alert("A-FAT-2", "FAT_DA_PAGARE_SCADUTA", "inv-2"),
        # movimento riconciliato: si chiude
        _alert("A-RIC-1", "RIC_NON_RICONCILIATO", "MOV-OK"),
        # movimento non riconciliato con un doppione: resta il piu' vecchio
        _alert("A-RIC-2", "RIC_MATCH_AMBIGUO", "MOV-KO", created="2026-09-01T00:00:00"),
        _alert("A-RIC-3", "RIC_MATCH_AMBIGUO", "MOV-KO", created="2026-09-02T00:00:00"),
        # movimento della carta SumUp, riconciliato: collezione dall'id
        _alert("A-RIC-4", "RIC_NON_RICONCILIATO", "sumup_conto:X1"),
        _alert("A-DOC-1", "DOC_NON_CLASSIFICATO", "doc-cedolino"),
        _alert("A-DOC-2", "DOC_NON_CLASSIFICATO", "doc-altro"),
        _alert("A-ALTRO", "F24_SCADUTO", "f24-1"),
    ])
    await db["estratto_conto_movimenti"].insert_many([
        {"id": "MOV-OK", "riconciliato": True},
        {"id": "MOV-KO", "riconciliato": False},
    ])
    await db["sumup_conto_movimenti"].insert_one({"id": "sumup_conto:X1", "riconciliato": True})
    await db["documents_inbox"].insert_many([
        {"id": "doc-cedolino", "category": "cedolini"},
        {"id": "doc-altro", "category": "altro"},
    ])
    await db["invoices"].insert_many([
        {"id": "FT-ARVAL", "invoice_number": "A25111540620", "status": "imported"},
        {"id": "FT-ARCH", "invoice_number": "X1", "status": "archived"},
        {"id": "FT-VIVA", "invoice_number": "9001", "status": "imported"},
    ])
    await db["verbali_noleggio"].insert_many([
        # numero del verbale = numero della fattura collegata
        {"_id": "v1", "numero_verbale": "A25111540620", "stato": "fattura_ricevuta",
         "fattura_id": "FT-ARVAL"},
        # fattura collegata che non esiste piu'
        {"_id": "v2", "numero_verbale": "B12345678901", "stato": "fattura_ricevuta",
         "fattura_id": "FT-SPARITA"},
        # fattura archiviata
        {"_id": "v3", "numero_verbale": "B99999999999", "stato": "fattura_ricevuta",
         "fattura_associata_id": "FT-ARCH"},
        # verbale vero, fattura attiva e numero diverso: resta
        {"_id": "v4", "numero_verbale": "V777", "stato": "fattura_ricevuta",
         "fattura_id": "FT-VIVA"},
        # numero della fattura ma con prove proprie (PEC): decide una persona
        {"_id": "v5", "numero_verbale": "A25111540620", "stato": "salvato",
         "fattura_id": "FT-ARVAL", "upec_id": "PEC-1"},
        # ripristinato a mano: non torna in quarantena
        {"_id": "v6", "numero_verbale": "A25111540620", "stato": "fattura_ricevuta",
         "fattura_id": "FT-ARVAL", "quarantena_revocata": True},
    ])


def test_bonifiche_chiudono_e_mettono_in_quarantena_solo_il_dovuto():
    async def scenario():
        db = ArchivioDocumenti()
        await _prepara(db)
        primo = await esegui_bonifiche(db)
        secondo = await esegui_bonifiche(db)
        alert = {a["id"]: a for a in await db["alerts"].find({}, {"_id": 0}).to_list(None)}
        verbali = {v["_id"]: v for v in await db["verbali_noleggio"].find({}).to_list(None)}
        stato = await db["sistema_stato"].find_one({"chiave": CHIAVE_STATO}, {"_id": 0})
        return primo, secondo, alert, verbali, stato

    primo, secondo, alert, verbali, stato = asyncio.run(scenario())

    # 1. scadenze fatture fornitore
    for aid in ("A-FAT-1", "A-FAT-2"):
        assert alert[aid]["stato"] == "risolto"
        assert alert[aid]["motivo_chiusura"] == MOTIVO_FATTURE_SENZA_SCADENZA
    # 2. RIC_*: riconciliati e doppioni chiusi, l'originale resta aperto
    assert alert["A-RIC-1"]["stato"] == "risolto"
    assert alert["A-RIC-4"]["stato"] == "risolto"
    assert alert["A-RIC-2"]["stato"] == "aperto"
    assert alert["A-RIC-3"]["stato"] == "risolto"
    assert "A-RIC-2" in alert["A-RIC-3"]["motivo_chiusura"]
    # 3. documenti con categoria
    assert alert["A-DOC-1"]["stato"] == "risolto"
    assert alert["A-DOC-2"]["stato"] == "aperto"
    # nessun altro codice toccato
    assert alert["A-ALTRO"]["stato"] == "aperto"
    # 4. verbali: quarantena col motivo, nessuno cancellato
    assert len(verbali) == 6
    assert verbali["v1"]["stato"] == "quarantena"
    assert verbali["v1"]["stato_precedente"] == "fattura_ricevuta"
    assert "A25111540620" in verbali["v1"]["motivo_quarantena"]
    # fattura sparita o archiviata: si ricollega, non si nasconde
    for vid in ("v2", "v3", "v4", "v6"):
        assert verbali[vid]["stato"] == "fattura_ricevuta"
    assert verbali["v5"]["stato"] == "salvato"

    assert primo["conteggi"]["verbali_da_fattura"]["quarantena"] == 1
    assert primo["conteggi"]["verbali_da_fattura"]["con_prove_proprie"] == 1
    assert primo["conteggi"]["verbali_da_fattura"]["da_ricollegare"] == 2
    assert primo["conteggi"]["alert_movimenti"] == {
        "aperti": 4, "doppioni_chiusi": 1, "riconciliati_chiusi": 2,
    }
    # idempotente: il secondo giro non tocca niente
    assert secondo["conteggi"]["fatture_senza_scadenza"]["chiusi"] == 0
    assert secondo["conteggi"]["alert_movimenti"]["doppioni_chiusi"] == 0
    assert secondo["conteggi"]["alert_movimenti"]["riconciliati_chiusi"] == 0
    assert secondo["conteggi"]["documenti_classificati"]["chiusi"] == 0
    assert secondo["conteggi"]["verbali_da_fattura"]["quarantena"] == 0
    assert stato["conteggi"] == secondo["conteggi"] and stato["errori"] == {}


def test_numero_derivato_da_fattura():
    assert numero_derivato_da_fattura("A25111540620", ["A25111540620"]) == "A25111540620"
    assert numero_derivato_da_fattura("A25111540620", ["FT A25111540620/2026"])
    assert numero_derivato_da_fattura("V777", ["9001"]) is None
    assert numero_derivato_da_fattura("", ["9001"]) is None


def test_la_bonifica_e_agganciata_al_job_bancario_corto():
    testo = (RADICE / "app/scheduler.py").read_text(encoding="utf-8")
    inizio = testo.index("async def _banca_versamenti_proiezione_job")
    fine = testo.index("async def _automazioni_prima_nota_job")
    assert "esegui_bonifiche(db)" in testo[inizio:fine]


def test_il_numero_di_fattura_con_gli_spazi_si_ripulisce_una_volta():
    """Societa' Duegi scrive «  13719»: in archivio il numero resta cercabile."""
    from app.services.bonifiche_automatiche import numeri_fattura_senza_spazi

    async def scenario():
        db = ArchivioDocumenti()
        await db["invoices"].insert_many([
            {"id": "f-duegi", "invoice_number": " 13719"},
            {"id": "f-ok", "invoice_number": "1/7653"},
        ])
        primo = await numeri_fattura_senza_spazi(db)
        duegi = await db["invoices"].find_one({"id": "f-duegi"})
        secondo = await numeri_fattura_senza_spazi(db)
        return primo, duegi, secondo

    primo, duegi, secondo = asyncio.run(scenario())
    assert primo == {"fatture": 1} and secondo == {"fatture": 0}
    assert (duegi["invoice_number"], duegi["invoice_number_originale"]) == ("13719", " 13719")


def test_l_import_legge_il_numero_senza_spazi():
    from app.parsers.fattura_elettronica_parser import parse_fattura_xml
    from tests.fiscale.test_fattura_passiva_regole_5_9 import XML

    con_spazio = XML.replace("<Numero>F-99</Numero>", "<Numero>  F-99 </Numero>")
    assert parse_fattura_xml(con_spazio)["invoice_number"] == "F-99"


def test_la_fattura_pagata_con_assegno_si_allinea_alla_banca():
    """Stato fermo a «in attesa banca» e data della fattura: si allineano all'addebito."""
    from app.services.bonifiche_automatiche import fatture_pagate_con_assegno

    async def scenario():
        db = ArchivioDocumenti()
        await db["invoices"].insert_many([
            {"id": "f-una", "total_amount": 646.72, "stato_pagamento": "in_attesa_banca",
             "pagato": True, "paid": False, "data_pagamento": "2026-04-07"},
            {"id": "f-due-a", "total_amount": 91.2, "stato": "da_pagare"},
            {"id": "f-due-b", "total_amount": 439.1, "stato": "da_pagare"},
            {"id": "f-parziale", "total_amount": 1000.0, "stato": "da_pagare"},
            {"id": "f-provvisoria", "total_amount": 50.0, "stato": "da_pagare"},
        ])
        await db["assegni"].insert_many([
            {"id": "a1", "stato": "incassato", "evidenza_bancaria_ufficiale": True,
             "movimento_estratto_conto_id": "m1", "data_incasso": "2026-04-17",
             "importo": 646.72, "fattura_id": "f-una"},
            {"id": "a2", "stato": "incassato", "evidenza_bancaria_ufficiale": True,
             "movimento_estratto_conto_id": "m2", "data_incasso": "2026-05-14", "importo": 530.3,
             "fatture_collegate": [{"fattura_id": "f-due-a", "quota": 91.2},
                                   {"fattura_id": "f-due-b", "quota": 439.1}]},
            {"id": "a3", "stato": "incassato", "evidenza_bancaria_ufficiale": True,
             "movimento_estratto_conto_id": "m3", "data_incasso": "2026-05-20",
             "importo": 400.0, "fattura_id": "f-parziale"},
            {"id": "a4", "stato": "incassato", "evidenza_bancaria_ufficiale": False,
             "movimento_estratto_conto_id": "m4", "data_incasso": "2026-05-21",
             "importo": 50.0, "fattura_id": "f-provvisoria"},
        ])
        primo = await fatture_pagate_con_assegno(db)
        secondo = await fatture_pagate_con_assegno(db)
        fatture = {f["id"]: f for f in await db["invoices"].find({}, {"_id": 0}).to_list(None)}
        return primo, secondo, fatture

    primo, secondo, fatture = asyncio.run(scenario())
    assert primo == {"fatture": 3, "totale_diverso": 1}
    assert secondo == {"fatture": 0, "totale_diverso": 1}
    una = fatture["f-una"]
    assert (una["stato_pagamento"], una["paid"], una["data_pagamento"]) == ("pagata", True, "2026-04-17")
    assert fatture["f-due-b"]["stato"] == "pagata"
    assert fatture["f-parziale"]["stato"] == "da_pagare"
    assert fatture["f-provvisoria"]["stato"] == "da_pagare"
    assert "metodo_pagamento" not in una
