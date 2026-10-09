"""Prima Nota Banca: parcelle con ritenuta e righe gia' provate dalla banca.

Casi reali (27/09/2026): FPR 105/26 di un professionista, 1.332,24 € lordi,
bonifico di 1.122,24 € (la ritenuta di 210 € va in F24). Senza la ritenuta la
fattura restava aperta per 210 €, il report del titolare la ripassava e
declassava la riga provata dalla banca a «dichiarata, in attesa di estratto».
"""
import asyncio

import pytest

from app.database import Database
from app.parsers.fattura_elettronica_parser import parse_fattura_xml
from app.routers import ritenute
from app.services import pagamenti_dichiarati_titolare as pagamenti
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.prima_nota_integrity import totale_pagabile_al_fornitore

PARCELLA_XML = """<?xml version="1.0" encoding="utf-8"?>
<p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2" versione="FPR12">
  <FatturaElettronicaHeader>
    <CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>STUDIO TEST</Denominazione></Anagrafica></DatiAnagrafici></CedentePrestatore>
    <CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>00000000000</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>CLIENTE TEST</Denominazione></Anagrafica></DatiAnagrafici></CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>2026-08-06</Data><Numero>FPR 105/26</Numero>
      <DatiRitenuta><TipoRitenuta>RT01</TipoRitenuta><ImportoRitenuta>210.00</ImportoRitenuta><AliquotaRitenuta>20.00</AliquotaRitenuta><CausalePagamento>A</CausalePagamento></DatiRitenuta>
      <ImportoTotaleDocumento>1332.24</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>Consulenza</Descrizione><PrezzoUnitario>1092.00</PrezzoUnitario><PrezzoTotale>1092.00</PrezzoTotale><AliquotaIVA>22.00</AliquotaIVA></DettaglioLinee>
      <DatiRiepilogo><AliquotaIVA>22.00</AliquotaIVA><ImponibileImporto>1092.00</ImponibileImporto><Imposta>240.24</Imposta></DatiRiepilogo>
    </DatiBeniServizi>
    <DatiPagamento><CondizioniPagamento>TP02</CondizioniPagamento><DettaglioPagamento><ModalitaPagamento>MP05</ModalitaPagamento><ImportoPagamento>1122.24</ImportoPagamento></DettaglioPagamento></DatiPagamento>
  </FatturaElettronicaBody>
</p:FatturaElettronica>"""

EC_ID = "2026-08-14_-1122.24_VOSTRA_DISPOSIZIONE_-_VSDISP"


@pytest.fixture()
def db(monkeypatch):
    database = ClientArchivioMemoria()["test_pn_banca_parcelle"]
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: database))
    return database


def _parcella(**extra):
    return {
        "id": "f-parcella", "invoice_number": "FPR 105/26", "supplier_vat": "01234567890",
        "supplier_name": "STUDIO TEST", "invoice_date": "2026-08-06",
        "total_amount": 1332.24, "tipo_documento": "TD01", "status": "imported",
        "pagamento_rate_totale": "1122.24", **extra,
    }


def test_il_parser_legge_la_ritenuta_e_il_netto_e_quello_del_bonifico():
    parsed = parse_fattura_xml(PARCELLA_XML)
    assert parsed["importo_ritenuta"] == 210.0
    fattura = _parcella(importo_ritenuta=parsed["importo_ritenuta"])
    assert totale_pagabile_al_fornitore(fattura) == 1122.24
    # Senza ritenuta documentata le rate da sole non riducono il debito.
    assert totale_pagabile_al_fornitore(_parcella()) == 1332.24


def test_il_report_non_declassa_la_riga_provata_dalla_banca(db):
    async def scenario():
        await db["invoices"].insert_one(_parcella(importo_ritenuta=210.0))
        riga_provata = {
            "id": "pn-provata", "fattura_id": "f-parcella", "riferimento": "FATT-f-parcella",
            "importo": 1122.24, "tipo": "uscita", "data": "2026-08-14",
            "source": "riconciliazione_automatica_fattura_identita",
            "estratto_conto_id": EC_ID, "movimento_bancario_id": EC_ID, "riconciliato": True,
        }
        await db["prima_nota_banca"].insert_one(dict(riga_provata))
        fattura = await db["invoices"].find_one({"id": "f-parcella"}, {"_id": 0})
        pn_id, gia_provata = await pagamenti._scrivi_banca_dichiarata(
            db, fattura, {"metodo_pagamento_titolare": "banca",
                          "data_pagamento_report": "2026-08-06"},
        )
        riga = await db["prima_nota_banca"].find_one({"id": "pn-provata"}, {"_id": 0})
        fattura = await db["invoices"].find_one({"id": "f-parcella"}, {"_id": 0})
        return pn_id, gia_provata, riga, fattura

    pn_id, gia_provata, riga, fattura = asyncio.run(scenario())
    assert pn_id == "pn-provata" and gia_provata is True
    assert riga["riconciliato"] is True
    assert riga["data"] == "2026-08-14"
    for campo in ("provvisorio", "stato", "dichiarato_titolare", "in_attesa_estratto_ufficiale"):
        assert campo not in riga
    assert fattura["in_attesa_riscontro_banca"] is False


def test_riparazione_righe_dichiarate(db):
    async def scenario():
        await db["invoices"].insert_one(_parcella(importo_ritenuta=210.0))
        await db["invoices"].insert_one(_parcella(
            id="f-altra", invoice_number="FPR 43/26", importo_ritenuta=210.0,
        ))
        # Riga provata che il vecchio giro aveva declassato.
        await db["prima_nota_banca"].insert_one({
            "id": "pn-rovinata", "fattura_id": "f-parcella", "importo": 1122.24,
            "data": "2026-08-06", "date": "2026-08-14", "data_riconciliazione": "2026-08-14",
            "estratto_conto_id": EC_ID, "dichiarato_titolare": True, "provvisorio": True,
            "canonico": False, "stato": "DA_VERIFICARE", "riconciliato": False,
            "in_attesa_estratto_ufficiale": True,
            "motivo_provvisorio": "dichiarata_dal_titolare_in_attesa_estratto_conto",
        })
        # Riga dichiarata scritta al lordo: esce il netto.
        await db["prima_nota_banca"].insert_one({
            "id": "pn-lorda", "fattura_id": "f-altra", "importo": 1332.24, "amount": 1332.24,
            "data": "2026-03-25", "dichiarato_titolare": True, "provvisorio": True,
        })
        primo = await pagamenti.ripara_righe_dichiarate(db)
        secondo = await pagamenti.ripara_righe_dichiarate(db)
        rovinata = await db["prima_nota_banca"].find_one({"id": "pn-rovinata"}, {"_id": 0})
        lorda = await db["prima_nota_banca"].find_one({"id": "pn-lorda"}, {"_id": 0})
        return primo, secondo, rovinata, lorda

    primo, secondo, rovinata, lorda = asyncio.run(scenario())
    assert primo == {"provate_ripristinate": 1, "importi_al_netto": 1}
    assert secondo == {"provate_ripristinate": 0, "importi_al_netto": 0}
    assert rovinata["riconciliato"] is True and rovinata["data"] == "2026-08-14"
    for campo in ("provvisorio", "stato", "canonico", "dichiarato_titolare",
                  "motivo_provvisorio", "in_attesa_estratto_ufficiale"):
        assert campo not in rovinata
    assert lorda["importo"] == 1122.24 and lorda["dichiarato_titolare"] is True


def test_allineamento_ritenute_una_volta_sola(db):
    async def scenario():
        await db["invoices"].insert_one(_parcella(xml_raw=PARCELLA_XML))
        primo = await ritenute.allinea_ritenute_fatture(db)
        secondo = await ritenute.allinea_ritenute_fatture(db)
        fattura = await db["invoices"].find_one({"id": "f-parcella"}, {"_id": 0})
        proiezione = await db["ritenute_acconto"].find_one({"fattura_id": "f-parcella"}, {"_id": 0})
        return primo, secondo, fattura, proiezione

    primo, secondo, fattura, proiezione = asyncio.run(scenario())
    assert primo == {"fatture": 1, "aggiornate": 1}
    assert secondo == {"saltato": "gia_allineate"}
    assert fattura["importo_ritenuta"] == 210.0
    assert proiezione["importo_cents"] == 21000


def test_riparazione_con_id_fattura_numerico(db):
    """Fatture storiche con id numerico (1776634698467): la riparazione e
    l'assorbimento le trovano lo stesso."""
    from app.services.prima_nota_integrity import assorbi_righe_dichiarate

    async def scenario():
        await db["invoices"].insert_one(_parcella(
            id=1776634698467, total_amount=3806.4, importo_ritenuta=600.0,
            pagamento_rate_totale=None,
        ))
        await db["prima_nota_banca"].insert_one({
            "id": "pn-numerica", "fattura_id": 1776634698467, "importo": 3806.4,
            "data": "2026-02-11", "dichiarato_titolare": True, "provvisorio": True,
        })
        esito = await pagamenti.ripara_righe_dichiarate(db)
        riga = await db["prima_nota_banca"].find_one({"id": "pn-numerica"}, {"_id": 0})
        toccate = await assorbi_righe_dichiarate(
            db, {"1776634698467": 3206.4}, sostituita_da="pn-banca", movimento_id="ec-1",
        )
        dopo = await db["prima_nota_banca"].find_one({"id": "pn-numerica"}, {"_id": 0})
        return esito, riga, toccate, dopo

    esito, riga, toccate, dopo = asyncio.run(scenario())
    assert esito["importi_al_netto"] == 1
    assert riga["importo"] == 3206.4
    assert toccate == 1 and dopo["status"] == "deleted"


def test_nuova_parcella_apre_avviso_ritenuta_una_volta(db, monkeypatch):
    from app.services import telegram_notifications

    messaggi = []

    async def finto_invio(testo, **_):
        messaggi.append(testo)
        return {"success": True}

    monkeypatch.setattr(telegram_notifications, "send_notification", finto_invio)

    async def scenario():
        # Pagata al professionista ad agosto: il 1040 e' quello di agosto, entro il 16/09
        # (il periodo e' il mese del pagamento, non della fattura: decisione del 02/10/2026).
        fattura = _parcella(xml_raw=PARCELLA_XML, stato="pagata", data_pagamento="2026-08-20")
        await ritenute.upsert_ritenuta_da_fattura(db, fattura)
        await ritenute.upsert_ritenuta_da_fattura(db, fattura)  # reimport
        return await db["alerts"].find({"codice": "RITENUTA_DA_VERSARE"}, {"_id": 0}).to_list(10)

    alerts = asyncio.run(scenario())
    assert len(alerts) == 1 and alerts[0]["entita_id"] == "f-parcella"
    assert "210,00 €" in alerts[0]["dettaglio"] and "1040" in alerts[0]["dettaglio"]
    assert "16/09/2026" in alerts[0]["dettaglio"]
    assert len(messaggi) == 1


def test_avviso_ritenuta_si_chiude_quando_il_1040_e_versato(db):
    async def scenario():
        await db["alerts"].insert_one({
            "id": "a1", "codice": "RITENUTA_DA_VERSARE", "entita_id": "f-parcella",
            "stato": "aperto",
        })
        await ritenute._chiudi_avviso_se_versata(
            db, {"fattura_id": "f-parcella"}, {"stato_obbligazione": "APERTA"},
        )
        ancora = await db["alerts"].find_one({"id": "a1"}, {"_id": 0})
        await ritenute._chiudi_avviso_se_versata(
            db, {"fattura_id": "f-parcella"}, {"stato_obbligazione": "VERSATA"},
        )
        chiuso = await db["alerts"].find_one({"id": "a1"}, {"_id": 0})
        return ancora, chiuso

    ancora, chiuso = asyncio.run(scenario())
    assert ancora["stato"] == "aperto"
    assert chiuso["stato"] == "risolto"


def test_bonifico_netto_abbina_la_parcella_con_id_numerico(db):
    """FPR 14/26 CARINI: id 1776634698467 numerico, bonifico di 3.206,40 €.
    Il motore d'identita' la abbina e la riga dichiarata lascia il posto."""
    from app.services import bank_payment_allocations as bpa

    async def scenario():
        await db["invoices"].insert_one({
            "id": 1776634698467, "invoice_number": "FPR 14/26",
            "supplier_name": "CARINI GIOVANNI", "supplier_vat": "01234567890",
            "invoice_date": "2026-02-11", "total_amount": 3806.4, "importo_ritenuta": 600.0,
            "status": "imported", "pagato": True, "paid": True, "stato_pagamento": "pagata",
            "in_attesa_riscontro_banca": True,
        })
        await db["prima_nota_banca"].insert_one({
            "id": "pn-dich", "fattura_id": 1776634698467, "importo": 3206.4, "tipo": "uscita",
            "data": "2026-02-11", "dichiarato_titolare": True, "provvisorio": True,
        })
        await db["estratto_conto_movimenti"].insert_one({
            "id": "m-carini", "data": "2026-02-13", "tipo": "uscita", "importo": -3206.4,
            "descrizione": "VS.DISP. RIF. MBVT14361619/00094618 FAVORE CARINI GIOVANNI",
        })
        esito = await bpa.reconcile_deterministic_invoice_allocations(db)
        dichiarata = await db["prima_nota_banca"].find_one({"id": "pn-dich"}, {"_id": 0})
        attive = await db["prima_nota_banca"].find(
            {"status": {"$ne": "deleted"}}, {"_id": 0},
        ).to_list(10)
        fattura = await db["invoices"].find_one({"id": 1776634698467}, {"_id": 0})
        return esito, dichiarata, attive, fattura

    esito, dichiarata, attive, fattura = asyncio.run(scenario())
    assert esito["allocati_identita"] == 1
    assert dichiarata["status"] == "deleted"
    assert len(attive) == 1 and attive[0]["estratto_conto_id"] == "m-carini"
    assert fattura["in_attesa_riscontro_banca"] is False
