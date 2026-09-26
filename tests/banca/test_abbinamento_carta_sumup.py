"""Bonifici partiti dalla carta SumUp: stessi motori del conto BPM.

Uno stipendio si abbina alla busta per identità del dipendente e periodo,
una fattura per identità del fornitore e importo al centesimo. L'esito si
scrive sulla collezione della carta, e la Prima Nota Banca esce da 19.01.05,
mai dal conto BPM.
"""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.sumup_conto import (
    COLL_MOVIMENTI,
    abbina_movimenti_sumup,
    campi_bancari,
    collezione_del_movimento,
)

IBAN_DIP = "IT62Q0306903487100000000123"
IBAN_FORN = "IT90R0306940315100000001363"


def _movimento(codice, data, uscita, riferimento, causale, iban=None):
    importo = f"-{uscita}"
    riga = {
        "id": f"sumup_conto:{codice}", "codice_transazione": codice, "data": data,
        "tipo_transazione": "Bonifico bancario in uscita",
        "riferimento": riferimento, "causale": causale,
        "uscita": uscita, "entrata": "0.00", "commissione": "0.00",
        "importo": importo, "segno": "uscita", "conto_contabile": "19.01.05",
        "iban_beneficiario": iban,
    }
    return riga


def test_campi_bancari_ricompongono_beneficiario_e_iban():
    riga = {
        "riferimento": "GIULIANO GUARINO IT62Q0306903487 100000000123",
        "causale": "Stipendio Agosto", "importo": "-1239.00",
        "iban_beneficiario": IBAN_DIP,
    }
    campi = campi_bancari(riga)
    assert campi["tipo"] == "uscita"
    assert campi["beneficiario"] == "GIULIANO GUARINO"
    assert campi["descrizione"] == f"GIULIANO GUARINO — {IBAN_DIP} — Stipendio Agosto"


def test_collezione_dal_identificativo():
    assert collezione_del_movimento({"id": "sumup_conto:C9X"}) == COLL_MOVIMENTI
    assert collezione_del_movimento({"id": "abc"}) == "estratto_conto_movimenti"


def test_stipendio_e_fattura_pagati_con_la_carta():
    db = ClientArchivioMemoria()["abbinamento_sumup"]

    async def scenario():
        await db["dipendenti"].insert_one({
            "id": "dip-1", "nome": "Giuliano", "cognome": "Guarino",
            "nome_completo": "Giuliano Guarino", "iban": IBAN_DIP,
        })
        await db["prima_nota_salari"].insert_one({
            "id": "sal-1", "dipendente_id": "dip-1", "dipendente_nome": "Giuliano Guarino",
            "anno": 2026, "mese": 8, "importo_busta": 1239.00, "importo_bonifico": 0,
            "riconciliato": False,
        })
        await db["invoices"].insert_one({
            "id": "fatt-1", "invoice_number": "397", "invoice_date": "2026-08-31",
            "supplier_name": "CILATTE SRL", "supplier_vat": "01234567890",
            "supplier_iban": IBAN_FORN,
            "total_amount": 590.51, "importo_residuo": 590.51, "importo_pagato": 0.0,
            "pagato": False, "stato_pagamento": "da_pagare",
        })
        for riga in (
            _movimento("C9STIP0001", "2026-09-07", "1239.00",
                       "GIULIANO GUARINO IT62Q0306903487 100000000123",
                       "Stipendio Agosto", IBAN_DIP),
            _movimento("C9FATT0001", "2026-09-14", "590.51",
                       "CILATTE SRL IT90R0306940315 100000001363",
                       "Cilatte fattura 397 del 31/08/", IBAN_FORN),
            _movimento("C9GIRO0001", "2026-09-15", "10000.00",
                       "Ceraldi Group srl IT13X0503403406 000000000001", "Giroconto"),
        ):
            await db[COLL_MOVIMENTI].insert_one(riga)

        primo = await abbina_movimenti_sumup(db)
        secondo = await abbina_movimenti_sumup(db)
        movimenti = {
            m["id"]: m for m in await db[COLL_MOVIMENTI].find({}, {"_id": 0}).to_list(None)
        }
        salario = await db["prima_nota_salari"].find_one({"id": "sal-1"})
        fattura = await db["invoices"].find_one({"id": "fatt-1"})
        banca = await db["prima_nota_banca"].find({}, {"_id": 0}).to_list(None)
        bpm = await db["estratto_conto_movimenti"].count_documents({})
        return primo, secondo, movimenti, salario, fattura, banca, bpm

    primo, secondo, movimenti, salario, fattura, banca, bpm = asyncio.run(scenario())

    assert primo["stipendi_abbinati"] == 1
    assert primo["fatture_abbinate"] == 1
    assert movimenti["sumup_conto:C9STIP0001"]["stipendio_id"] == "sal-1"
    assert salario["riconciliato"] is True
    assert "sumup_conto:C9STIP0001" in salario["movimenti_bancari_ids"]

    assert movimenti["sumup_conto:C9FATT0001"]["fattura_id"] == "fatt-1"
    assert fattura["pagato"] is True
    assert fattura["riconciliato_con_ec"] == "sumup_conto:C9FATT0001"

    # Il giroconto verso il conto BPM non e' una fattura ne' uno stipendio.
    assert not movimenti["sumup_conto:C9GIRO0001"].get("riconciliato")

    # Prima Nota Banca: tutto sul conto della carta, niente sul conto BPM.
    assert banca, "attese righe di Prima Nota Banca"
    assert {r.get("conto_contabile") for r in banca} == {"19.01.05"}
    assert bpm == 0

    # Secondo giro: niente di nuovo.
    assert secondo["stipendi_abbinati"] == 0
    assert secondo["fatture_abbinate"] == 0
    assert secondo["prima_nota_banca"]["scritte"] == 0


def test_busta_arrivata_dopo_il_bonifico_della_carta():
    """Il bonifico parte il 07/09, la busta di agosto arriva dopo: l'arrivo
    del cedolino ripassa anche la carta SumUp."""
    from app.services.reconciliation_orchestrator import on_cedolino_importato_riprocessa

    db = ClientArchivioMemoria()["busta_dopo_bonifico"]

    async def scenario():
        await db["dipendenti"].insert_one({
            "id": "dip-1", "nome": "Giuliano", "cognome": "Guarino",
            "nome_completo": "GUARINO GIULIANO",
        })
        await db[COLL_MOVIMENTI].insert_one(_movimento(
            "C9STIP0002", "2026-09-07", "1239.00",
            "GIULIANO GUARINO IT62Q0306903487 100000000123", "Stipendio Agosto", IBAN_DIP,
        ))
        prima = await abbina_movimenti_sumup(db)
        await db["prima_nota_salari"].insert_one({
            "id": "sal-2", "dipendente_id": "dip-1", "dipendente_nome": "GUARINO GIULIANO",
            "anno": 2026, "mese": 8, "importo_busta": 1239.00, "importo_bonifico": 0,
            "riconciliato": False,
        })
        esito = await on_cedolino_importato_riprocessa({"anno": 2026}, db)
        movimento = await db[COLL_MOVIMENTI].find_one({"id": "sumup_conto:C9STIP0002"})
        return prima, esito, movimento

    prima, esito, movimento = asyncio.run(scenario())
    assert prima["stipendi_abbinati"] == 0
    assert esito["carta_sumup"]["bonifici_associati"] == 1
    assert movimento["stipendio_id"] == "sal-2"


def test_stato_in_prima_nota_sumup_dopo_l_abbinamento():
    from app.routers.prima_nota_module.banca import _stato_movimento_sumup

    assert _stato_movimento_sumup({"stipendio_id": "sal-1"}) == "Stipendio abbinato alla busta"
    assert _stato_movimento_sumup({"fattura_id": "f-1"}) == "Fattura pagata"
    assert _stato_movimento_sumup({"prima_nota_banca_id": "pn-1"}) == "Registrato in Prima Nota"
    assert _stato_movimento_sumup({}) == "Da registrare"


def test_stesso_pagamento_su_carta_e_bpm_non_e_un_doppione():
    """Stesso giorno, importo e dipendente sulla carta e sul conto BPM: sono
    due operazioni, e il giro della carta non tocca la riga del BPM."""
    from app.services.proiezione_bancaria import proietta_movimenti_bancari_semantici

    db = ClientArchivioMemoria()["carta_e_bpm"]

    async def scenario():
        await db["dipendenti"].insert_one({
            "id": "dip-1", "nome": "Giuliano", "cognome": "Guarino",
            "nome_completo": "GUARINO GIULIANO", "iban": IBAN_DIP,
        })
        await db["estratto_conto_movimenti"].insert_one({
            "id": "bpm-1", "data": "2026-09-12", "tipo": "uscita", "importo": -100.0,
            "descrizione": f"VS.DISP. FAVORE GUARINO GIULIANO {IBAN_DIP} acconto",
        })
        await db[COLL_MOVIMENTI].insert_one({
            **_movimento("C9ACC00001", "2026-09-12", "100.00",
                         "GIULIANO GUARINO IT62Q0306903487 100000000123",
                         "Acconto stipendio settembre", IBAN_DIP),
            **campi_bancari({
                "riferimento": "GIULIANO GUARINO IT62Q0306903487 100000000123",
                "causale": "Acconto stipendio settembre", "importo": "-100.00",
                "iban_beneficiario": IBAN_DIP,
            }),
        })
        bpm = await proietta_movimenti_bancari_semantici(db)
        carta = await proietta_movimenti_bancari_semantici(
            db, collezione=COLL_MOVIMENTI, conto_contabile="19.01.05",
        )
        righe = await db["prima_nota_banca"].find(
            {"status": {"$nin": ["deleted", "archived"]}}, {"_id": 0},
        ).to_list(None)
        return bpm, carta, righe

    bpm, carta, righe = asyncio.run(scenario())
    assert bpm["proiettati"] == 1
    assert carta["proiettati"] == 1 and carta["doppioni_tolti"] == 0
    assert sorted(r.get("conto_contabile") for r in righe) == ["19.01.01", "19.01.05"]
