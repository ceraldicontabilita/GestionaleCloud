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
    importa_estratto_sumup,
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
    # «Cilatte fattura 397» la prende la regola delle fatture citate in causale.
    assert primo["fatture_abbinate"] + primo["fatture_citate_abbinate"] == 1
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
    assert secondo["fatture_abbinate"] + secondo["fatture_citate_abbinate"] == 0
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


def test_esito_dell_abbinamento_resta_in_sistema_stato():
    from app.services.sumup_conto import CHIAVE_STATO_ABBINAMENTO

    db = ClientArchivioMemoria()["stato_abbinamento"]

    async def scenario():
        await abbina_movimenti_sumup(db)
        return await db["sistema_stato"].find_one({"chiave": CHIAVE_STATO_ABBINAMENTO})

    stato = asyncio.run(scenario())
    assert stato["terminato_at"]
    assert stato["esito"]["movimenti"] == 0


def test_estratto_gia_presente_riaccoda_l_abbinamento():
    """Il ramo di Documenti > Import accoda l'abbinamento anche senza righe nuove."""
    import inspect

    from app.routers import documenti

    sorgente = inspect.getsource(documenti)
    inizio = sorgente.index("elif tipo_rilevato == 'estratto_conto_sumup':")
    ramo = sorgente[inizio:sorgente.index("elif tipo_rilevato", inizio + 10)]
    assert "accoda_abbinamento(db)" in ramo
    assert 'if sumup_result.get("nuovi")' not in ramo


# --- Rimborso finanziamento soci: la causale vince sul nome ------------------

IBAN_SOCIO = "IT10C0503403406000000005459"
INTESTAZIONE_CSV = (
    "Data transazione,Codice transazione,Tipo transazione,Riferimento,Causale pagamento,"
    "Stato,Importo di fatturazione in uscita,Importo di fatturazione in entrata,"
    "Valuta della carta,Importo transazione in uscita,Importo transazione in entrata,"
    "Valuta della transazione,Tasso di cambio,Commissione,Saldo disponibile"
)


def _socio_dipendente(db):
    async def semina():
        await db["dipendenti"].insert_one({
            "id": "dip-vc", "nome": "Vincenzo", "cognome": "Ceraldi",
            "nome_completo": "CERALDI VINCENZO",
        })
        await db["prima_nota_salari"].insert_one({
            "id": "sal-vc", "dipendente_id": "dip-vc", "dipendente_nome": "CERALDI VINCENZO",
            "anno": 2026, "mese": 8, "importo_busta": 2074.00, "importo_bonifico": 0,
            "riconciliato": False,
        })
    asyncio.run(semina())


def _rimborso(causale):
    riga = _movimento("C9RIMB0001", "2026-09-02", "1500.00",
                      "Vincenzo Ceraldi IT10C0503403406 000000005459", causale, IBAN_SOCIO)
    return {**riga, **campi_bancari(riga)}


def test_rimborso_finanziamento_al_socio_non_e_uno_stipendio():
    db = ClientArchivioMemoria()["rimborso_socio"]
    _socio_dipendente(db)

    async def scenario():
        await db[COLL_MOVIMENTI].insert_one(_rimborso("Rimborso finanziamento infruttifero"))
        esito = await abbina_movimenti_sumup(db)
        busta = await db["prima_nota_salari"].find_one({"id": "sal-vc"})
        banca = await db["prima_nota_banca"].find({}, {"_id": 0}).to_list(None)
        soci = await db["finanziamenti_soci_movimenti"].find({}, {"_id": 0}).to_list(None)
        return esito, busta, banca, soci

    esito, busta, banca, soci = asyncio.run(scenario())
    assert esito["stipendi_abbinati"] == 0
    assert busta["importo_bonifico"] == 0
    assert [r["categoria"] for r in banca] == ["Finanziamento soci"]
    assert banca[0]["conto_contabile"] == "19.01.05"
    assert [(s["tipo"], s["importo"]) for s in soci] == [("rimborso", 1500.0)]


def test_causale_intera_dal_csv_stacca_il_rimborso_dalla_busta():
    """Il PDF aveva spezzato «finanziame nto»: il bonifico era finito sulla
    busta. Il CSV porta il testo intero, e il giro successivo ripara."""
    db = ClientArchivioMemoria()["rimborso_socio_riparato"]
    _socio_dipendente(db)

    async def scenario():
        await db[COLL_MOVIMENTI].insert_one(_rimborso("Rimborso finanziame nto infruttifero"))
        prima = await abbina_movimenti_sumup(db)
        busta_prima = await db["prima_nota_salari"].find_one({"id": "sal-vc"})
        csv = "\n".join([
            INTESTAZIONE_CSV,
            "02/09/26, 15:34,C9RIMB0001,Bonifico bancario in uscita,"
            f"Vincenzo Ceraldi {IBAN_SOCIO},Rimborso finanziamento infruttifero,Approvato,"
            "1500.00,0.00,EUR,1500.00,0.00,EUR,1.00,0.00,500.00",
        ]).encode()
        importato = await importa_estratto_sumup(db, "Resoconto.csv", csv)
        dopo = await abbina_movimenti_sumup(db)
        busta = await db["prima_nota_salari"].find_one({"id": "sal-vc"})
        movimento = await db[COLL_MOVIMENTI].find_one({"id": "sumup_conto:C9RIMB0001"})
        banca = await db["prima_nota_banca"].find(
            {"status": {"$nin": ["deleted", "archived"]}}, {"_id": 0},
        ).to_list(None)
        return prima, busta_prima, importato, dopo, busta, movimento, banca

    prima, busta_prima, importato, dopo, busta, movimento, banca = asyncio.run(scenario())
    assert prima["stipendi_abbinati"] == 1 and busta_prima["importo_bonifico"] == 1500.0
    assert importato["testi_corretti"] == 1
    assert movimento["causale"] == "Rimborso finanziamento infruttifero"
    assert dopo["rimborsi_soci_staccati"] == [
        {"movimento_id": "sumup_conto:C9RIMB0001", "stipendio_id": "sal-vc"},
    ]
    assert busta["importo_bonifico"] == 0 and busta["riconciliato"] is False
    assert movimento["stipendio_id"] is None
    # Stessa riga di Prima Nota, ora rimborso soci: nessuna seconda uscita.
    assert len(banca) == 1
    assert banca[0]["categoria"] == "Finanziamento soci"
    assert banca[0]["riclassificata_da"] == "Stipendi"
    assert banca[0]["conto_contropartita"] == "31.03.15"


def test_competenza_dichiarata_dal_titolare_vince_sulla_causale():
    """«paga ottobre 2026» pagato l'11/09 con l'importo esatto della busta di
    agosto: il titolare dice che e' agosto, e il motore gli da' ragione."""
    db = ClientArchivioMemoria()["competenza_dichiarata"]

    async def scenario():
        await db["dipendenti"].insert_one({
            "id": "dip-fi", "nome": "Francesco", "cognome": "Iazzetta",
            "nome_completo": "IAZZETTA FRANCESCO",
        })
        await db["prima_nota_salari"].insert_one({
            "id": "sal-fi", "dipendente_id": "dip-fi", "dipendente_nome": "IAZZETTA FRANCESCO",
            "anno": 2026, "mese": 8, "importo_busta": 1379.00, "importo_bonifico": 0,
            "riconciliato": False,
        })
        riga = _movimento("CDK4E4ZMZW", "2026-09-11", "1379.00",
                          "Francesco Iazzetta IT84X0305801604100572599347",
                          "iazzetta francesco paga ottobre 2026")
        await db[COLL_MOVIMENTI].insert_one({**riga, **campi_bancari(riga)})
        prima = await abbina_movimenti_sumup(db)
        await db[COLL_MOVIMENTI].update_one(
            {"id": "sumup_conto:CDK4E4ZMZW"}, {"$set": {"competenza_dichiarata": "08/2026"}},
        )
        dopo = await abbina_movimenti_sumup(db)
        busta = await db["prima_nota_salari"].find_one({"id": "sal-fi"})
        return prima, dopo, busta

    prima, dopo, busta = asyncio.run(scenario())
    assert prima["stipendi_abbinati"] == 0
    assert dopo["stipendi_abbinati"] == 1
    assert busta["riconciliato"] is True
    assert busta["movimenti_bancari_ids"] == ["sumup_conto:CDK4E4ZMZW"]
