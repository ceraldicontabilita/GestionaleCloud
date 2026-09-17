"""Report ufficiale "Fatture ricevute": e' un indice di controllo, non una fattura.

Questi test proteggono la regola vincolante: il report misura quali XML
mancano, ma non deve MAI creare una fattura contabile senza XML.
"""
import asyncio
import io

import pandas as pd
import pytest
from app.services.sheets_document_store import MemorySheetsClient

from app.services import fatture_report_ae as report_ae


def _run(awaitable):
    return asyncio.run(awaitable)


def _db():
    return MemorySheetsClient()["report_ae_test"]


def _riga(
    numero="1/2026",
    nome_file="IT01234567890_00001.xml",
    sdi="1234567890",
    data="2026-03-15",
    fornitore="LEASYS S.p.A.",
    piva="06714021000",
    metodo="MP02 - Assegno",
    totale=1220.0,
    netto=1220.0,
    **extra,
):
    riga = {
        "Numero": numero,
        "Nome file": nome_file,
        "ID SdI": sdi,
        "Data documento": data,
        "Fornitore": fornitore,
        "P.IVA": piva,
        "Metodo di pagamento": metodo,
        "Totale documento": totale,
        "Netto a pagare": netto,
    }
    riga.update(extra)
    return riga


def _xlsx(righe) -> bytes:
    buffer = io.BytesIO()
    pd.DataFrame(righe).to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


# --- Riconoscimento del formato -------------------------------------------

def test_riconosce_il_report_ufficiale():
    assert report_ae.report_headers_match(_xlsx([_riga()]), "report.xlsx") is True


def test_non_scambia_un_foglio_qualsiasi_per_il_report():
    estraneo = _xlsx([{"Data": "2026-01-01", "Descrizione": "bonifico", "Importo": 10}])
    assert report_ae.report_headers_match(estraneo, "estratto.xlsx") is False


def test_foglio_incompleto_viene_rifiutato_con_messaggio_esplicito():
    parziale = _riga()
    parziale.pop("Netto a pagare")
    with pytest.raises(ValueError) as exc:
        report_ae._read_report(_xlsx([parziale]), "report.xlsx")
    assert "Netto a pagare" in str(exc.value)


def test_il_report_viene_riconosciuto_dall_upload_automatico():
    """L'utente carica il file senza dichiararne il tipo: lo deve capire il sistema."""
    from app.routers.documenti import detect_document_type

    assert detect_document_type(
        "Fatture ricevute.xlsx", _xlsx([_riga()]),
    ) == "report_fatture_ricevute"


def test_un_estratto_conto_non_viene_scambiato_per_il_report():
    from app.routers.documenti import detect_document_type

    estratto = _xlsx([{"Data": "2026-01-01", "Descrizione": "bonifico", "Importo": 10}])
    assert detect_document_type("estratto.xlsx", estratto) != "report_fatture_ricevute"


# --- Regola cardine: nessuna fattura inventata ----------------------------

def test_il_report_non_crea_mai_fatture_contabili():
    db = _db()
    esito = _run(report_ae.importa_report_fatture_ricevute(
        db, _xlsx([_riga(), _riga(numero="2/2026", sdi="222", nome_file="b.xml")]),
        "report.xlsx",
    ))

    assert esito["rows"] == 2
    assert esito["xml_missing"] == 2
    # La collezione canonica resta intatta: nessun XML, nessuna fattura.
    assert _run(db["invoices"].count_documents({})) == 0
    assert _run(db[report_ae.COLLECTION_REPORT].count_documents({})) == 2


def test_le_righe_indicizzate_restano_marcate_come_prive_di_xml():
    db = _db()
    _run(report_ae.importa_report_fatture_ricevute(db, _xlsx([_riga()]), "r.xlsx"))

    riga = _run(db[report_ae.COLLECTION_REPORT].find_one({}))
    assert riga["xml_presente"] is False
    assert riga["invoice_id"] is None
    assert riga["source"] == "agenzia_entrate_report_fatture_ricevute"


# --- Aggancio all'XML canonico quando esiste ------------------------------

def test_aggancia_la_fattura_canonica_per_nome_file():
    db = _db()
    _run(db["invoices"].insert_one({
        "id": "inv-1",
        "filename": "IT01234567890_00001.xml",
        "invoice_number": "1/2026",
        "invoice_date": "2026-03-15",
        "supplier_vat": "06714021000",
    }))

    esito = _run(report_ae.importa_report_fatture_ricevute(db, _xlsx([_riga()]), "r.xlsx"))

    assert esito["xml_present"] == 1
    assert esito["xml_missing"] == 0
    riga = _run(db[report_ae.COLLECTION_REPORT].find_one({}))
    assert riga["xml_presente"] is True
    assert riga["invoice_id"] == "inv-1"


def test_aggancia_per_identita_naturale_quando_il_nome_file_differisce():
    """P.IVA + numero + data: il nome del file sul portale puo' non coincidere."""
    db = _db()
    _run(db["invoices"].insert_one({
        "id": "inv-2",
        "filename": "scaricata_da_drive.xml",
        "invoice_number": "1 / 2026",  # spaziatura diversa, stessa fattura
        "invoice_date": "2026-03-15T00:00:00",
        "supplier_vat": "IT06714021000",
    }))

    esito = _run(report_ae.importa_report_fatture_ricevute(db, _xlsx([_riga()]), "r.xlsx"))

    assert esito["xml_present"] == 1
    assert _run(db[report_ae.COLLECTION_REPORT].find_one({}))["invoice_id"] == "inv-2"


def test_una_fattura_cancellata_non_conta_come_xml_presente():
    db = _db()
    _run(db["invoices"].insert_one({
        "id": "inv-del",
        "filename": "IT01234567890_00001.xml",
        "entity_status": "deleted",
    }))

    esito = _run(report_ae.importa_report_fatture_ricevute(db, _xlsx([_riga()]), "r.xlsx"))

    assert esito["xml_present"] == 0
    assert esito["xml_missing"] == 1


# --- Idempotenza: reimportare non duplica ---------------------------------

def test_reimportare_lo_stesso_report_non_duplica_le_righe():
    db = _db()
    contenuto = _xlsx([_riga(), _riga(numero="2/2026", sdi="222", nome_file="b.xml")])

    primo = _run(report_ae.importa_report_fatture_ricevute(db, contenuto, "r.xlsx"))
    secondo = _run(report_ae.importa_report_fatture_ricevute(db, contenuto, "r.xlsx"))

    assert primo["imported"] == 2 and primo["updated"] == 0
    assert secondo["imported"] == 0 and secondo["updated"] == 2
    assert _run(db[report_ae.COLLECTION_REPORT].count_documents({})) == 2


def test_reimportare_aggiorna_lo_stato_senza_perdere_la_data_di_creazione():
    db = _db()
    _run(report_ae.importa_report_fatture_ricevute(db, _xlsx([_riga()]), "r.xlsx"))
    creato_at = _run(db[report_ae.COLLECTION_REPORT].find_one({}))["created_at"]

    # Nel frattempo l'XML canonico viene acquisito.
    _run(db["invoices"].insert_one({
        "id": "inv-tardivo",
        "filename": "IT01234567890_00001.xml",
    }))
    _run(report_ae.importa_report_fatture_ricevute(db, _xlsx([_riga()]), "r.xlsx"))

    riga = _run(db[report_ae.COLLECTION_REPORT].find_one({}))
    assert riga["created_at"] == creato_at
    assert riga["xml_presente"] is True
    assert riga["invoice_id"] == "inv-tardivo"


# --- Righe non valide: scartate, mai indovinate ---------------------------

def test_le_righe_senza_identificativo_sono_scartate_non_indovinate():
    db = _db()
    righe = [
        _riga(),
        _riga(numero="", sdi="", nome_file="vuota.xml"),        # senza numero
        _riga(numero="3/2026", data="", sdi="", piva="333"),     # senza data
    ]

    esito = _run(report_ae.importa_report_fatture_ricevute(db, _xlsx(righe), "r.xlsx"))

    assert esito["rows"] == 1
    assert esito["invalid"] == 2
    assert esito["success"] is False
    assert esito["partial"] is True
    assert _run(db[report_ae.COLLECTION_REPORT].count_documents({})) == 1
    assert all(d["status"] == "invalid" for d in esito["details"])


def test_una_riga_senza_piva_resta_valida_se_ha_lo_sdi():
    db = _db()
    esito = _run(report_ae.importa_report_fatture_ricevute(
        db, _xlsx([_riga(piva="", sdi="99887766")]), "r.xlsx",
    ))
    assert esito["rows"] == 1
    assert esito["invalid"] == 0


# --- Formati italiani ------------------------------------------------------

def test_legge_importi_e_date_in_formato_italiano():
    db = _db()
    _run(report_ae.importa_report_fatture_ricevute(db, _xlsx([_riga(
        data="15/03/2026",
        totale="1.234,56",
        netto="1.234,56",
        **{"Totale imponibile": "1.012,00", "Totale IVA": "222,56"},
    )]), "r.xlsx"))

    riga = _run(db[report_ae.COLLECTION_REPORT].find_one({}))
    assert riga["totale_documento"] == 1234.56
    assert riga["netto_pagare"] == 1234.56
    assert riga["imponibile"] == 1012.00
    assert riga["data_documento"] == "2026-03-15"
    assert riga["anno"] == 2026


@pytest.mark.parametrize(
    ("esportata", "attesa"),
    [
        ("03/04/2026", "2026-04-03"),   # 3 aprile, non 4 marzo
        ("01/12/2026", "2026-12-01"),   # 1 dicembre, non 12 gennaio
        ("15/03/2026", "2026-03-15"),   # non ambigua
        ("2026-03-15", "2026-03-15"),   # ISO: resta invariata
    ],
)
def test_le_date_ambigue_sono_lette_come_italiane(esportata, attesa):
    """gg/mm/aaaa: leggerle all'americana sposterebbe il periodo IVA."""
    assert report_ae._date(esportata) == attesa


def test_una_data_ambigua_aggancia_comunque_l_xml_canonico():
    db = _db()
    _run(db["invoices"].insert_one({
        "id": "inv-dicembre",
        "filename": "altro-nome.xml",
        "invoice_number": "1/2026",
        "invoice_date": "2026-12-01",
        "supplier_vat": "06714021000",
    }))

    esito = _run(report_ae.importa_report_fatture_ricevute(
        db, _xlsx([_riga(data="01/12/2026")]), "r.xlsx",
    ))

    assert esito["xml_present"] == 1
    riga = _run(db[report_ae.COLLECTION_REPORT].find_one({}))
    assert riga["data_documento"] == "2026-12-01"
    assert riga["invoice_id"] == "inv-dicembre"


def test_marca_lo_strumento_assegno_dichiarato_nel_report():
    db = _db()
    _run(report_ae.importa_report_fatture_ricevute(db, _xlsx([
        _riga(metodo="MP02 - Assegno"),
        _riga(numero="9/2026", sdi="999", nome_file="c.xml", metodo="MP05 - Bonifico"),
    ]), "r.xlsx"))

    assegno = _run(db[report_ae.COLLECTION_REPORT].find_one({"numero_fattura": "1/2026"}))
    bonifico = _run(db[report_ae.COLLECTION_REPORT].find_one({"numero_fattura": "9/2026"}))
    assert assegno["modalita_pagamento_xml"] == "MP02"
    assert bonifico["modalita_pagamento_xml"] == ""


# --- Tracciabilita' dell'import -------------------------------------------

def test_registra_hash_e_riepilogo_dell_import():
    db = _db()
    contenuto = _xlsx([_riga()])
    _run(report_ae.importa_report_fatture_ricevute(db, contenuto, "Fatture ricevute.xlsx"))

    log = _run(db["fatture_report_ae_imports"].find_one({}))
    assert log["filename"] == "Fatture ricevute.xlsx"
    assert log["rows"] == 1
    assert log["xml_missing"] == 1
    assert len(log["source_hash"]) == 64  # sha256 del file originale

    riga = _run(db[report_ae.COLLECTION_REPORT].find_one({}))
    assert riga["source_hash"] == log["source_hash"]
    assert riga["source_report_filename"] == "Fatture ricevute.xlsx"
