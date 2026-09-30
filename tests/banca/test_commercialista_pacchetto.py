"""Area Commercialista: periodo, documenti del pacchetto, invio in un'unica email.

Il commercialista sceglie il periodo (mese, trimestre, anno o dal/al) e cosa inviare:
ogni documento e' costruito dal server dalla fonte canonica, senza inventare numeri
(una fonte guasta e' «Non disponibile», una senza righe «Vuota», una con un buco
«Incompleta»), e parte in UNA email con un allegato per documento.
"""
import asyncio
import io
import zipfile
from datetime import date

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.hr.services import email_smtp
from app.routers import commercialista as mod
from app.services import commercialista_pacchetto as pk
from app.services import f24_controllo_incrociato as reg
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.commercialista_pdf import csv_voce, pdf_voce
from app.utils.dependencies import get_current_admin_user

SETTEMBRE = pk.intervallo_periodo(2026, 9)


def _run(coro):
    return asyncio.run(coro)


def _riempi(db, collezione, documenti):
    _run(db[collezione].insert_many([dict(d) for d in documenti]))


@pytest.fixture
def db(monkeypatch):
    archivio = ClientArchivioMemoria()["commercialista-pacchetto"]
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: archivio))
    return archivio


@pytest.fixture
def hr(monkeypatch):
    from app.hr.database import Database as DatabaseHR

    archivio = AsyncMongoMockClient()["hr_pacchetto"]
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: archivio))
    return archivio


# ---------------------------------------------------------------------------
# Periodo
# ---------------------------------------------------------------------------

def test_periodo_da_anno_e_mese():
    p = pk.intervallo_periodo(2026, 9)
    assert (p.dal, p.al, p.etichetta) == ("2026-09-01", "2026-09-30", "Settembre 2026")
    assert pk.intervallo_periodo(2028, 2).al == "2028-02-29"


def test_mese_zero_resta_anno_intero():
    p = pk.intervallo_periodo(2026, 0)
    assert (p.dal, p.al, p.etichetta) == ("2026-01-01", "2026-12-31", "Intero anno 2026")


def test_periodo_da_dal_al_e_riconosce_mese_trimestre_anno():
    assert pk.intervallo_periodo(dal="2026-09-01", al="2026-09-30").etichetta == "Settembre 2026"
    assert pk.intervallo_periodo(dal="2026-07-01", al="2026-09-30").etichetta == "3° trimestre 2026"
    assert pk.intervallo_periodo(dal="2026-01-01", al="2026-12-31").etichetta == "Intero anno 2026"
    libero = pk.intervallo_periodo(dal="2026-08-15", al="2026-09-05")
    assert libero.etichetta == "dal 15/08/2026 al 05/09/2026"
    assert [m for m in libero.mesi()] == [(2026, 8), (2026, 9)]


def test_dal_al_hanno_la_precedenza_su_anno_mese():
    assert pk.intervallo_periodo(2020, 1, "2026-09-01", "2026-09-30").dal == "2026-09-01"


@pytest.mark.parametrize("args", [
    {"dal": "2026-09-10"},                                   # manca al
    {"dal": "2026-09-30", "al": "2026-09-01"},               # invertite
    {"dal": "2026-09-01", "al": "2028-09-01"},               # troppo lungo
    {"dal": "01/09/2026", "al": "30/09/2026"},               # non e' ISO
    {"anno": 2026, "mese": 13},
    {},
])
def test_periodo_non_valido(args):
    with pytest.raises(ValueError):
        pk.intervallo_periodo(**args)


def test_la_rotta_risponde_400_su_un_periodo_non_valido(db):
    with pytest.raises(HTTPException) as exc:
        _run(mod.get_prima_nota_cassa_mensile(2026, 9, "2026-09-30", "2026-09-01"))
    assert exc.value.status_code == 400


def test_filtro_include_l_ultimo_giorno_anche_con_l_ora():
    p = pk.intervallo_periodo(2026, 9)
    assert p.contiene("2026-09-30T23:59:00Z") and not p.contiene("2026-10-01")
    assert p.filtro("data") == {"data": {"$gte": "2026-09-01", "$lte": "2026-09-30~"}}


def test_cassa_e_fatture_cassa_con_dal_al(db):
    _riempi(db, "prima_nota_cassa", [
        {"id": "C1", "data": "2026-08-20", "tipo": "entrata", "importo": 10.0},
        {"id": "C2", "data": "2026-09-02", "tipo": "entrata", "importo": 100.0, "categoria": "Corrispettivi"},
        {"id": "C3", "data": "2026-09-30T10:00:00", "tipo": "uscita", "importo": 30.0, "fattura_id": "F1"},
        {"id": "C4", "data": "2026-10-01", "tipo": "uscita", "importo": 5.0},
    ])
    _riempi(db, "invoices", [{"id": "F1", "invoice_number": "1/A", "invoice_date": "2026-08-25",
                              "supplier_name": "Forno", "total_amount": 30.0}])
    esito = _run(mod.get_prima_nota_cassa_mensile(2026, 0, "2026-08-15", "2026-09-30"))
    assert esito["totale_movimenti"] == 3 and esito["totale_entrate"] == 110.0
    assert esito["totale_uscite"] == 30.0 and esito["saldo"] == 80.0
    assert (esito["dal"], esito["al"]) == ("2026-08-15", "2026-09-30")
    fatture = _run(mod.get_fatture_pagate_cassa(2026, 0, "2026-09-01", "2026-09-30"))
    assert fatture["totale_fatture"] == 1 and fatture["totale_importo"] == 30.0


def test_le_rotte_per_mese_restano_compatibili(db):
    _riempi(db, "prima_nota_cassa", [{"id": "C1", "data": "2026-09-02", "tipo": "entrata", "importo": 10.0}])
    assert _run(mod.get_prima_nota_cassa_mensile(2026, 9))["totale_movimenti"] == 1
    assert _run(mod.get_prima_nota_cassa_mensile(2026, 3))["totale_movimenti"] == 0


# ---------------------------------------------------------------------------
# Voci: piene e vuote
# ---------------------------------------------------------------------------

def _voce(db, nome, periodo=SETTEMBRE, **opz):
    return _run(pk.costruisci_voce(db, nome, periodo, opz))


def test_prima_nota_cassa_piena_e_vuota(db):
    _riempi(db, "prima_nota_cassa", [
        {"id": "C1", "data": "2026-09-02", "tipo": "entrata", "importo": 100.5, "descrizione": "Incasso"},
        {"id": "C2", "data": "2026-09-03", "tipo": "uscita", "importo": 20, "descrizione": "Latte"},
    ])
    v = _voce(db, "prima_nota_cassa")
    assert (v["stato"], v["conteggio"], v["totale"]) == (pk.STATO_PRONTO, 2, "80,50")
    assert v["sezioni"][0]["righe"][0][:4] == ["02/09/2026", "Incasso", "", "100,50"]
    vuota = _voce(db, "prima_nota_cassa", pk.intervallo_periodo(2026, 3))
    assert (vuota["stato"], vuota["conteggio"], vuota["totale"]) == (pk.STATO_VUOTO, 0, None)


def test_banca_distingue_ufficiale_da_provvisorio_e_dice_se_l_estratto_non_copre(db):
    _riempi(db, "estratto_conto_movimenti", [
        {"id": "E1", "data": "2026-09-02", "importo": -30.0, "tipo": "uscita",
         "descrizione_originale": "BONIFICO A ROSSI", "evidenza_bancaria_ufficiale": True},
        {"id": "E2", "data": "2026-09-05", "importo": 50.0, "tipo": "entrata", "descrizione": "POS"},
        # un'altra carta: non e' il conto della banca
        {"id": "E3", "data": "2026-09-06", "importo": -9.0, "tipo": "uscita", "conto_contabile": "19.01.05"},
        {"id": "E4", "data": "2026-10-02", "importo": -1.0, "tipo": "uscita"},
    ])
    v = _voce(db, "banca")
    assert v["conteggio"] == 2 and v["totale"] == "20,00"
    assert v["stato"] == pk.STATO_INCOMPLETO
    assert "1 movimenti su 2 non sono ancora nell'estratto conto ufficiale" in v["motivo"]
    assert "copre solo dal 02/09/2026 al 06/09/2026" in v["motivo"]   # stessa lettura del controllo di completezza
    stati = [r[5] for r in v["sezioni"][0]["righe"]]
    assert stati == ["Ufficiale", "Provvisorio"]
    assert _voce(db, "banca", pk.intervallo_periodo(2026, 1))["stato"] == pk.STATO_VUOTO


def test_paypal_esclude_le_conversioni_e_non_inventa_gli_importi_in_valuta(db):
    _riempi(db, "paypal_transactions", [
        {"transaction_id": "T1", "data": "2026-09-03", "lordo": -25.0, "currency": "EUR",
         "nome_controparte": "Amazon", "descrizione": "Ordine"},
        {"transaction_id": "T2", "data": "2026-09-04", "lordo": 40.0, "currency": "EUR",
         "nome_controparte": "Cliente"},
        {"transaction_id": "T3", "data": "2026-09-05", "lordo": -12.0, "currency": "USD",
         "nome_controparte": "Servizio Web", "tipo": "T0006"},
        {"transaction_id": "T4", "data": "2026-08-30", "lordo": -99.0, "currency": "EUR"},
    ])
    v = _voce(db, "paypal")
    assert v["conteggio"] == 3
    assert v["totale"] == "15,00"   # 40 - 25: il pagamento in dollari senza conversione non entra
    assert v["stato"] == pk.STATO_INCOMPLETO
    assert "1 movimenti in valuta estera senza conversione" in v["motivo"]
    assert _voce(db, "paypal", pk.intervallo_periodo(2026, 1))["stato"] == pk.STATO_VUOTO


def test_sumup_movimenti_payout_e_vendite(db):
    from app.services.sumup_sync import COLL_TRANSAZIONI

    _riempi(db, "sumup_conto_movimenti", [
        {"id": "S1", "data": "2026-09-02", "riferimento": "Payout", "entrata": "100.00", "uscita": "0",
         "commissione": "0", "saldo": "100.00"},
        {"id": "S2", "data": "2026-09-03", "riferimento": "Bonifico", "entrata": "0", "uscita": "40.00",
         "commissione": "0.50", "saldo": "60.00"},
    ])
    _riempi(db, "sumup_payouts", [{"payout_id": "P1", "data": "2026-09-02", "netto": 100.0,
                                   "commissione_api": 1.5, "stato": "SUCCESSFUL"}])
    _riempi(db, COLL_TRANSAZIONI, [
        {"id": "V1", "data": "2026-09-01", "tipo": "PAYMENT", "stato": "SUCCESSFUL", "importo": 101.5},
        {"id": "V2", "data": "2026-09-01", "tipo": "PAYMENT", "stato": "FAILED", "importo": 50.0},
    ])
    v = _voce(db, "sumup")
    assert v["stato"] == pk.STATO_PRONTO and v["conteggio"] == 3
    assert v["totale"] == "60,00"
    assert ["Vendite SumUp del periodo (1)", "101,50"] in v["riepilogo"]
    assert v["sezioni"][1]["righe"] == [["02/09/2026", "P1", "100,00", "1,50", "SUCCESSFUL"]]
    assert _voce(db, "sumup", pk.intervallo_periodo(2026, 1))["stato"] == pk.STATO_VUOTO


def test_sumup_solo_payout_senza_estratto_e_incompleto(db):
    _riempi(db, "sumup_payouts", [{"payout_id": "P1", "data": "2026-09-02", "netto": 100.0}])
    v = _voce(db, "sumup")
    assert v["stato"] == pk.STATO_INCOMPLETO and "Estratto conto SumUp non caricato" in v["motivo"]


def test_bonifici_collegano_fattura_o_dipendente_e_non_mostrano_l_iban_intero(db):
    _riempi(db, "invoices", [{"id": 7, "invoice_number": "77/A", "invoice_date": "2026-08-30"}])
    _riempi(db, "bonifici_transfers", [
        {"id": "B1", "data": "2026-09-03", "importo": 122.0, "cro_trn": "CRO1", "causale": "Fatt 77/A",
         "beneficiario": {"nome": "FORNO SRL", "iban": "IT60X0542811101000000123456"},
         "fattura_ids": ["7"], "riconciliato": True, "pdf_data": "AAAA" * 100},
        {"id": "B2", "data": "2026-09-04", "importo": 900.0, "beneficiario": {"nome": "MARIO ROSSI"},
         "dipendente_nome": "Mario Rossi", "salario_associato": True},
        {"id": "B3", "data": "2026-09-05", "importo": 10.0, "beneficiario": {"nome": "SCONOSCIUTO"}},
        {"id": "B4", "data": "2026-07-05", "importo": 5.0, "beneficiario": {"nome": "FUORI"}},
    ])
    v = _voce(db, "bonifici")
    righe = v["sezioni"][0]["righe"]
    assert v["conteggio"] == 3 and v["totale"] == "1.032,00"
    assert righe[0][2] == "****3456" and "IT60X0542811101000000123456" not in str(righe)
    assert righe[0][5] == "Fattura 77/A" and righe[0][7] == "In banca"
    assert righe[1][5] == "Stipendio Mario Rossi" and righe[2][5] == pk.DA_COLLEGARE
    assert v["stato"] == pk.STATO_INCOMPLETO and "1 bonifici senza fattura o dipendente collegato" in v["motivo"]
    assert _voce(db, "bonifici", pk.intervallo_periodo(2026, 1))["stato"] == pk.STATO_VUOTO


def test_corrispettivi_sommano_le_chiusure_del_giorno_e_dicono_quali_mancano(db):
    _riempi(db, "corrispettivi", [
        {"id": "R1", "data": "2026-09-01", "totale": 200.0, "pagato_contanti": 120.0, "pagato_elettronico": 80.0,
         "totale_iva": 18.0, "imponibile": 182.0, "stato": "definitivo_xml"},
        {"id": "R2", "data": "2026-09-01", "totale": 50.0, "pagato_contanti": 50.0, "pagato_pos": 0,
         "totale_iva": 4.5, "imponibile": 45.5, "stato": "definitivo_xml"},
        {"id": "R3", "data": "2026-09-02", "totale": 10.0, "status": "deleted"},
    ])
    v = _voce(db, "corrispettivi", pk.intervallo_periodo(dal="2026-09-01", al="2026-09-02"))
    assert v["conteggio"] == 1
    assert v["sezioni"][0]["righe"][0] == ["01/09/2026", "170,00", "80,00", "0,00", "250,00", "227,50", "22,50"]
    assert v["totale"] == "250,00"
    assert v["stato"] == pk.STATO_INCOMPLETO and "Mancano" in v["motivo"]
    assert _voce(db, "corrispettivi", pk.intervallo_periodo(2026, 1))["conteggio"] == 0


def test_fatture_ricevute_per_metodo_con_note_di_credito_e_metodo_mancante(db):
    _riempi(db, "invoices", [
        {"id": "F1", "invoice_number": "1", "invoice_date": "2026-09-02", "supplier_name": "Alfa",
         "total_amount": 100.0, "metodo_pagamento": "bonifico", "stato_pagamento": "pagata"},
        {"id": "F2", "invoice_number": "2", "invoice_date": "2026-09-05", "supplier_name": "Beta",
         "total_amount": 40.0, "metodo_pagamento": "cassa"},
        {"id": "F3", "invoice_number": "NC3", "invoice_date": "2026-09-06", "supplier_name": "Alfa",
         "total_amount": 10.0, "tipo_documento": "TD04", "metodo_pagamento": "bonifico"},
        {"id": "F4", "invoice_number": "4", "invoice_date": "2026-09-07", "supplier_name": "Gamma",
         "total_amount": 5.0, "metodo_pagamento": "sospesa"},
        {"id": "F5", "invoice_number": "5", "invoice_date": "2026-09-08", "supplier_name": "Copia",
         "total_amount": 999.0, "status": "archived"},
    ])
    v = _voce(db, "fatture_ricevute")
    assert v["conteggio"] == 4 and v["totale"] == "135,00"
    assert ["Bonifico: 2 fatture", "90,00"] in v["riepilogo"]
    assert ["Cassa: 1 fatture", "40,00"] in v["riepilogo"]
    assert ["Da configurare: 1 fatture", "5,00"] in v["riepilogo"]
    pagamenti = {r[1]: r[4] for r in v["sezioni"][0]["righe"]}
    assert pagamenti["1"] == "Pagata"
    assert v["stato"] == pk.STATO_INCOMPLETO and "1 fatture senza metodo" in v["motivo"]
    assert _voce(db, "fatture_ricevute", pk.intervallo_periodo(2026, 1))["stato"] == pk.STATO_VUOTO


def test_f24_dal_registro_unico(db, monkeypatch):
    modello = {"id": "F24-1", "file_name": "f24_giugno.pdf", "status": "da_pagare",
               "dati_generali": {"data_versamento": "2024-06-17"}, "totali": {"saldo_netto": "1000.00"},
               "sezione_erario": [{"codice_tributo": "2003", "anno": "2024", "importo_debito": "1000.00"}]}
    quietanza = {"id": "Q-1", "filename": "quietanza.pdf", "data_pagamento": "2024-06-17",
                 "protocollo_telematico": "24061712345678901", "saldo": "1000.00", "f24_associati": [],
                 "sezione_erario": [{"codice_tributo": "2003", "anno": "2024", "importo_debito": "1000.00"}]}

    async def _carica(_db):
        return {"f24": [modello], "quietanze": [reg._quietanza_legacy(quietanza)], "movimenti": [],
                "quietanze_per_f24": {}, "movimenti_per_f24": {}, "conteggi": {}}

    monkeypatch.setattr(reg, "carica_registro", _carica)
    v = _voce(db, "f24", pk.intervallo_periodo(2024, 6))
    assert v["stato"] == pk.STATO_PRONTO and v["conteggio"] == 2
    tipi = {r[2] for r in v["sezioni"][0]["righe"]}
    assert tipi == {"Quietanza", "Modello del commercialista"}
    assert all("2003" in r[3] for r in v["sezioni"][0]["righe"])
    assert _voce(db, "f24", pk.intervallo_periodo(2024, 1))["stato"] == pk.STATO_VUOTO


def test_stipendi_mostrano_il_netto_solo_se_verificato_e_mai_l_iban(db):
    from app.constants.stati_netto import NETTO_NON_PRESENTE_O_NON_LEGGIBILE, NETTO_VERIFICATO_DA_CEDOLINO

    _riempi(db, "cedolini", [
        {"id": "C1", "anno": 2026, "mese": 9, "nome_dipendente": "ROSSI MARIO", "lordo": 1500.0, "netto": 1200.0,
         "stato_netto": NETTO_VERIFICATO_DA_CEDOLINO, "pagato": True, "codice_fiscale": "RSSMRA80A01F839X"},
        {"id": "C2", "anno": "2026", "mese": "9", "nome_dipendente": "BIANCHI ANNA", "lordo": 1000.0, "netto": 0.0,
         "stato_netto": NETTO_NON_PRESENTE_O_NON_LEGGIBILE},
        {"id": "C3", "anno": 2026, "mese": 8, "nome_dipendente": "FUORI PERIODO", "lordo": 1.0},
    ])
    _riempi(db, "bonifici_transfers", [
        {"id": "B1", "data": "2026-09-27", "importo": 1200.0, "dipendente_nome": "Mario Rossi", "cro_trn": "CRO9",
         "beneficiario": {"nome": "ROSSI", "iban": "IT60X0542811101000000123456"}, "riconciliato": True},
    ])
    v = _voce(db, "stipendi")
    buste, bonifici = v["sezioni"]
    assert v["conteggio"] == 3 and v["totale"] == "1.200,00"
    assert [r[4] for r in buste["righe"]] == ["Da verificare", "1.200,00"] or \
        sorted(r[4] for r in buste["righe"]) == ["1.200,00", "Da verificare"]
    assert "RSSMRA80A01F839X" not in str(v) and "IT60X" not in str(v)
    assert bonifici["righe"] == [["27/09/2026", "Mario Rossi", "CRO9", "1.200,00", "In banca"]]
    assert v["stato"] == pk.STATO_INCOMPLETO and "1 buste con netto non verificato" in v["motivo"]
    assert _voce(db, "stipendi", pk.intervallo_periodo(2026, 1))["stato"] == pk.STATO_VUOTO


def test_carnet_senza_beneficiario_e_con_da_collegare(db):
    _riempi(db, "assegni", [
        {"id": "A1", "numero": "1234567801", "stato": "emesso", "importo": 100.0, "data_emissione": "2026-09-03",
         "beneficiario": "ROSSI SRL"},
        {"id": "A2", "numero": "1234567802", "stato": "emesso", "importo": 50.0, "data_emissione": "2026-09-04"},
        {"id": "A3", "numero": "1234567803", "stato": "vuoto", "importo": 0},
    ])
    v = _voce(db, "carnet_assegni")
    sez = v["sezioni"][0]
    assert "Beneficiario" not in sez["colonne"]
    assert sez["colonne"] == ["N. assegno", "Data", "Fornitore", "N. fattura", "Data fattura", "Importo", "Stato"]
    assert v["conteggio"] == 2 and v["totale"] == "150,00"
    assert sez["righe"][0][2] == "ROSSI SRL"         # il beneficiario e' il ripiego del fornitore
    assert sez["righe"][0][3:5] == [pk.DA_COLLEGARE, pk.DA_COLLEGARE]
    assert sez["righe"][1][2] == pk.DA_COLLEGARE
    assert v["stato"] == pk.STATO_INCOMPLETO and "2 assegni senza fattura collegata" in v["motivo"]
    # nulla e' stato collegato da qui
    assert _run(db["assegni"].find_one({"id": "A2"})).get("fatture_collegate") in (None, [])
    scelti = _voce(db, "carnet_assegni", pk.intervallo_periodo(2026, 1), carnet_ids=["12345678"])
    assert scelti["conteggio"] == 2    # i carnet scelti a mano valgono per numero (dell anno della lista assegni), non per data di emissione
    assert _voce(db, "carnet_assegni", pk.intervallo_periodo(2026, 1))["stato"] == pk.STATO_VUOTO


def test_un_guasto_della_fonte_e_non_disponibile_col_motivo(db, monkeypatch):
    async def rotta(_db, _p, _opz):
        raise RuntimeError("giu")

    monkeypatch.setitem(pk.VOCI, "banca", ("Banca (conto BPM)", rotta))
    v = _voce(db, "banca")
    assert v["stato"] == pk.STATO_NON_DISPONIBILE and v["motivo"] == "Fonte non leggibile (RuntimeError)"


# ---------------------------------------------------------------------------
# Presenze (HR)
# ---------------------------------------------------------------------------

def _hr_con_presenze(hr, anno=2026, mese=9):
    _run(hr.dipendenti.insert_many([
        {"id": "d1", "nome": "Mario", "cognome": "Rossi", "stato": "attivo", "attivo": True},
        {"id": "d2", "nome": "Luca", "cognome": "Cessato", "stato": "cessato", "data_cessazione": "2025-01-31"},
    ]))
    _run(hr.presenze_cloud.insert_many([
        {"id": "p1", "dipendente_id": "d1", "data": f"{anno}-{mese:02d}-01", "stato": "presente", "giustificativo": "P"},
        {"id": "p2", "dipendente_id": "d1", "data": f"{anno}-{mese:02d}-02", "stato": "assente", "giustificativo": "M",
         "note": "Protocollo INPS 123"},
    ]))


def test_presenze_da_inviare_poi_gia_inviato_dal_registro_unico(db, hr):
    from app.hr.services import presenze_consulente as pc

    assert _voce(db, "presenze")["stato"] == pk.STATO_VUOTO      # HR non ha niente per settembre
    _hr_con_presenze(hr)
    v = _voce(db, "presenze")
    assert v["stato"] == pk.STATO_DA_INVIARE and v["conteggio"] == 1
    assert v["mesi"][0]["etichetta"] == "Settembre 2026" and v["mesi"][0]["inviato_il"] is None

    # un invio dalla pagina HR e' lo stesso registro: qui compare come «Già inviato»
    _run(pc.registra_invio(2026, 9, "c@esempio.it", n_dipendenti=1, con_pdf=True, origine="hr"))
    v = _voce(db, "presenze")
    assert v["stato"] == pk.STATO_GIA_INVIATO and v["motivo"].startswith("Già inviato il ")
    assert v["mesi"][0]["destinatario"] == "c@esempio.it"


def test_un_invio_presenze_fallito_non_conta_come_inviato(db, hr):
    from app.hr.services import presenze_consulente as pc

    _hr_con_presenze(hr)
    _run(pc.registra_invio(2026, 9, "c@esempio.it", n_dipendenti=1, con_pdf=False, origine="erp",
                           esito=pc.ESITO_ERRORE, errore="SMTPException"))
    assert _voce(db, "presenze")["stato"] == pk.STATO_DA_INVIARE


def test_il_foglio_presenze_e_quello_della_griglia_hr(hr):
    from app.hr.services import presenze_consulente as pc

    _hr_con_presenze(hr)
    foglio = _run(pc.righe_presenze_mese(2026, 9, oggi=date(2026, 9, 10)))
    assert foglio["giorni"] == 30 and [r["nome"] for r in foglio["righe"]] == ["Rossi Mario"]  # il cessato non c'e'
    celle = foglio["righe"][0]["celle"]
    assert celle[0] == "P" and celle[1] == "M" and celle[2] == ""
    assert foglio["righe"][0]["note"][1] == "Protocollo INPS 123"
    assert pc.ha_presenze(foglio["righe"])


def test_un_giorno_futuro_non_e_mai_presente():
    from app.hr.services.presenze_consulente import codice_giorno

    presenza = {"stato": "presente", "giustificativo": "P"}
    assert codice_giorno(date(2026, 9, 20), "d1", presenza=presenza, ferie=[], turno_nome=None,
                         oggi=date(2026, 9, 10)) is None
    assert codice_giorno(date(2026, 9, 5), "d1", presenza=presenza, ferie=[], turno_nome=None,
                         oggi=date(2026, 9, 10)) == "P"
    ferie = [{"dipendente_id": "d1", "tipo": "Permesso", "data_inizio": "2026-09-05", "data_fine": "2026-09-06"}]
    assert codice_giorno(date(2026, 9, 5), "d1", presenza=None, ferie=ferie, turno_nome=None,
                         oggi=date(2026, 9, 10)) == "PE"
    assert codice_giorno(date(2026, 9, 5), "d1", presenza=None, ferie=[], turno_nome="Riposo",
                         oggi=date(2026, 9, 10)) == "RS"


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def test_il_pdf_di_una_voce_si_genera_e_il_csv_ha_le_stesse_righe(db):
    _riempi(db, "prima_nota_cassa", [
        {"id": f"C{i}", "data": "2026-09-02", "tipo": "entrata", "importo": 10.0 + i, "descrizione": f"Incasso {i}"}
        for i in range(60)])
    v = _voce(db, "prima_nota_cassa")
    pdf = pdf_voce(v, SETTEMBRE.etichetta, SETTEMBRE.dal, SETTEMBRE.al)
    assert pdf.startswith(b"%PDF") and len(pdf) > 1500
    righe = csv_voce(v).strip().splitlines()
    assert righe[0] == "Data;Descrizione;Categoria;Entrate;Uscite" and len(righe) == 61
    assert pdf_voce(_voce(db, "prima_nota_cassa", pk.intervallo_periodo(2026, 1)),
                    "Gennaio 2026", "2026-01-01", "2026-01-31").startswith(b"%PDF")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@pytest.fixture
def invii(monkeypatch):
    """Cattura l'email invece di spedirla."""
    spediti = []
    monkeypatch.setattr(email_smtp, "credenziali_smtp",
                        lambda: {"host": "h", "port": 465, "user": "u@esempio.it", "password": "x"})

    def _finto(cred, destinatario, oggetto, corpo, allegati=None, html=False):
        spediti.append({"a": destinatario, "oggetto": oggetto, "corpo": corpo, "allegati": list(allegati or []),
                        "html": html})

    monkeypatch.setattr(email_smtp, "_invia_via_smtp", _finto)
    return spediti


def _client(admin=True):
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/commercialista")

    async def _ok():
        if not admin:
            raise HTTPException(status_code=403, detail="Admin access required")
        return {"id": "1", "role": "admin"}

    app.dependency_overrides[get_current_admin_user] = _ok
    return TestClient(app)


def _dati_base(db):
    _riempi(db, "prima_nota_cassa", [
        {"id": "C1", "data": "2026-09-02", "tipo": "entrata", "importo": 100.0, "descrizione": "Incasso"}])
    _riempi(db, "estratto_conto_movimenti", [
        {"id": "E1", "data": "2026-09-02", "importo": -30.0, "tipo": "uscita", "descrizione": "BONIFICO",
         "evidenza_bancaria_ufficiale": True}])


CORPO = {"dal": "2026-09-01", "al": "2026-09-30", "voci": ["prima_nota_cassa", "banca", "paypal"]}


def test_invia_pacchetto_una_email_con_un_allegato_per_voce_e_il_registro(db, invii):
    _dati_base(db)
    esito = _client().post("/api/commercialista/invia-pacchetto", json={**CORPO, "email": "c@esempio.it"})
    assert esito.status_code == 200, esito.text
    dati = esito.json()
    assert dati["success"] and dati["allegati"] == 2
    assert len(invii) == 1                                       # UNA sola email
    email = invii[0]
    assert email["a"] == "c@esempio.it" and email["html"] is True
    assert email["oggetto"] == "Documenti per il commercialista - Settembre 2026"
    nomi = [a[3] for a in email["allegati"]]
    assert nomi == ["Prima_Nota_Cassa_2026-09-01_2026-09-30.pdf", "Banca_conto_BPM_2026-09-01_2026-09-30.pdf"]
    assert all(a[0].startswith(b"%PDF") for a in email["allegati"])
    assert "Prima Nota Cassa" in email["corpo"] and "Settembre 2026" in email["corpo"]
    per_voce = {e["voce"]: e for e in dati["esiti"]}
    assert per_voce["prima_nota_cassa"]["esito"] == "allegata"
    assert per_voce["paypal"]["esito"] == "saltata" and per_voce["paypal"]["motivo"]      # vuota: lo dice

    registro = _run(db["commercialista_invii"].find({}, {"_id": 0}).to_list(10))
    assert len(registro) == 1
    riga = registro[0]
    assert riga["esito"] == "inviato" and riga["destinatario"] == "c@esempio.it"
    assert (riga["dal"], riga["al"]) == ("2026-09-01", "2026-09-30")
    assert riga["voci_inviate"] == ["prima_nota_cassa", "banca"] and riga["id"] and riga["created_at"]
    # un mese intero con la Prima Nota Cassa chiude anche l'avviso del vecchio registro
    assert _run(db["commercialista_log"].count_documents({"tipo": "prima_nota_cassa", "mese": 9})) == 1


def test_destinatario_dalla_configurazione_se_non_scritto(db, invii):
    _dati_base(db)
    _riempi(db, "commercialista_config", [{"email": "config@esempio.it"}])
    assert _client().post("/api/commercialista/invia-pacchetto", json=CORPO).status_code == 200
    assert invii[0]["a"] == "config@esempio.it"


def test_solo_admin(db, invii):
    _dati_base(db)
    assert _client(admin=False).post("/api/commercialista/invia-pacchetto", json=CORPO).status_code == 403
    assert invii == []


@pytest.mark.parametrize("corpo", [
    {"dal": "2026-09-01", "al": "2026-09-30", "voci": []},
    {"dal": "2026-09-01", "al": "2026-09-30"},
    {"dal": "2026-09-01", "al": "2026-09-30", "voci": ["inventata"]},
])
def test_422_su_voci_vuote_o_sconosciute(db, invii, corpo):
    assert _client().post("/api/commercialista/invia-pacchetto", json=corpo).status_code == 422
    assert invii == []


def test_422_se_tutte_le_voci_scelte_sono_vuote(db, invii):
    r = _client().post("/api/commercialista/invia-pacchetto", json={**CORPO, "voci": ["paypal", "sumup"]})
    assert r.status_code == 422 and "vuote" in r.json()["detail"]
    assert invii == [] and _run(db["commercialista_invii"].count_documents({})) == 0


def test_400_su_un_periodo_non_valido(db, invii):
    r = _client().post("/api/commercialista/invia-pacchetto", json={**CORPO, "dal": "2026-09-30", "al": "2026-09-01"})
    assert r.status_code == 400


def test_invio_fallito_si_registra_col_solo_nome_dell_errore(db, monkeypatch, invii):
    _dati_base(db)

    def _rotto(*_a, **_k):
        raise ConnectionRefusedError("password segreta nel messaggio")

    monkeypatch.setattr(email_smtp, "_invia_via_smtp", _rotto)
    r = _client().post("/api/commercialista/invia-pacchetto", json=CORPO)
    assert r.status_code == 502 and "ConnectionRefusedError" in r.json()["detail"]
    assert "segreta" not in r.text
    riga = _run(db["commercialista_invii"].find({}, {"_id": 0}).to_list(5))[0]
    assert riga["esito"] == "errore" and riga["errore"] == "ConnectionRefusedError"
    assert riga["voci_inviate"] == [] and "segreta" not in str(riga)
    assert _run(db["commercialista_log"].count_documents({})) == 0


def test_senza_credenziali_email_risponde_503(db, monkeypatch):
    _dati_base(db)
    monkeypatch.setattr(email_smtp, "credenziali_smtp", lambda: None)
    assert _client().post("/api/commercialista/invia-pacchetto", json=CORPO).status_code == 503


def test_le_presenze_gia_inviate_non_ripartono_in_silenzio(db, hr, invii):
    from app.hr.services import presenze_consulente as pc

    _hr_con_presenze(hr)
    _dati_base(db)
    corpo = {**CORPO, "voci": ["prima_nota_cassa", "presenze"]}

    r = _client().post("/api/commercialista/invia-pacchetto", json=corpo)
    assert r.status_code == 200
    nomi = [a[3] for a in invii[0]["allegati"]]
    assert "presenze_2026_09.pdf" in nomi and "presenze_2026_09.csv" in nomi
    # lo stesso registro che legge la pagina HR
    registrati = _run(pc.invii_presenze(2026, 9))
    assert len(registrati) == 1 and registrati[0]["origine"] == "erp" and registrati[0]["n_dipendenti"] == 1

    # secondo invio senza «Rinvia»: le presenze si saltano e lo dicono
    r = _client().post("/api/commercialista/invia-pacchetto", json=corpo)
    esiti = {e["voce"]: e for e in r.json()["esiti"]}
    assert esiti["presenze"]["esito"] == "saltata" and "Rinvia" in esiti["presenze"]["motivo"]
    assert [a[3] for a in invii[1]["allegati"]] == ["Prima_Nota_Cassa_2026-09-01_2026-09-30.pdf"]
    assert len(_run(pc.invii_presenze(2026, 9))) == 1

    # con la conferma esplicita ripartono e il registro ne conta due
    r = _client().post("/api/commercialista/invia-pacchetto", json={**corpo, "presenze_rinvia": True})
    assert r.status_code == 200 and any(a[3].endswith(".csv") for a in invii[2]["allegati"])
    assert len(_run(pc.invii_presenze(2026, 9))) == 2


def test_solo_presenze_gia_inviate_e_422(db, hr, invii):
    from app.hr.services import presenze_consulente as pc

    _hr_con_presenze(hr)
    _run(pc.registra_invio(2026, 9, "c@esempio.it", n_dipendenti=1, con_pdf=True, origine="hr"))
    r = _client().post("/api/commercialista/invia-pacchetto", json={**CORPO, "voci": ["presenze"]})
    assert r.status_code == 422 and invii == []


def test_pacchetto_riassume_ogni_voce_con_ultimo_invio(db, hr, invii):
    _dati_base(db)
    _client().post("/api/commercialista/invia-pacchetto", json={**CORPO, "voci": ["prima_nota_cassa"]})
    r = _client().get("/api/commercialista/pacchetto", params={"dal": "2026-09-01", "al": "2026-09-30"})
    assert r.status_code == 200
    dati = r.json()
    voci = {v["voce"]: v for v in dati["voci"]}
    assert list(voci) == list(pk.VOCI)                           # tutte le schede, nell'ordine della pagina
    assert dati["periodo"]["etichetta"] == "Settembre 2026" and dati["smtp_configurato"] is True
    assert voci["prima_nota_cassa"]["stato"] == "pronto" and voci["prima_nota_cassa"]["totale"] == "100,00"
    assert voci["prima_nota_cassa"]["ultimo_invio"]["data"]
    assert voci["banca"]["ultimo_invio"] is None and voci["paypal"]["stato"] == "vuoto"
    assert "sezioni" not in voci["banca"]
    # un altro periodo non vede quell'invio
    altro = _client().get("/api/commercialista/pacchetto", params={"anno": 2026, "mese": 3}).json()
    assert {v["voce"]: v for v in altro["voci"]}["prima_nota_cassa"]["ultimo_invio"] is None


def test_l_ultimo_invio_riconosce_anche_il_vecchio_registro(db, hr):
    _dati_base(db)
    _riempi(db, "commercialista_log", [{"tipo": "fatture_cassa", "anno": 2026, "mese": 9, "email": "c@esempio.it",
                                        "data_invio": "2026-09-28T10:00:00+00:00", "success": True}])
    dati = _client().get("/api/commercialista/pacchetto", params={"anno": 2026, "mese": 9}).json()
    assert {v["voce"]: v for v in dati["voci"]}["fatture_cassa"]["ultimo_invio"]["data"].startswith("2026-09-28")


def test_scarica_una_voce_in_pdf_e_le_presenze_in_zip(db, hr):
    _dati_base(db)
    _hr_con_presenze(hr)
    r = _client().get("/api/commercialista/voce/prima_nota_cassa/scarica", params={"dal": "2026-09-01", "al": "2026-09-30"})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert "Prima_Nota_Cassa_2026-09-01_2026-09-30.pdf" in r.headers["content-disposition"]
    assert _client().get("/api/commercialista/voce/paypal/scarica", params={"anno": 2026, "mese": 9}).status_code == 404
    assert _client().get("/api/commercialista/voce/inventata/scarica", params={"anno": 2026, "mese": 9}).status_code == 422
    z = _client().get("/api/commercialista/voce/presenze/scarica", params={"anno": 2026, "mese": 9})
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    assert sorted(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == ["presenze_2026_09.csv", "presenze_2026_09.pdf"]


def test_voce_completa_e_registro_degli_invii(db, invii):
    _dati_base(db)
    r = _client().get("/api/commercialista/voce/banca", params={"dal": "2026-09-01", "al": "2026-09-30"})
    assert r.status_code == 200 and r.json()["sezioni"][0]["righe"][0][0] == "02/09/2026"
    _client().post("/api/commercialista/invia-pacchetto", json={**CORPO, "voci": ["banca"]})
    elenco = _client().get("/api/commercialista/invii").json()
    assert elenco["totale"] == 1 and elenco["invii"][0]["voci_inviate"] == ["banca"]
