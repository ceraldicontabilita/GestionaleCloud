"""Collaudo funzionale dei verbali: dal PDF al pagamento, sui dati e con i motori veri.

Ogni test e' uno scenario dell'utente (PDF reale generato con reportlab, endpoint reali con
TestClient, archivio in memoria) e dichiara l'esito ATTESO secondo CLAUDE.md
(«PartenoPay, verbali e flotta»).
"""

import asyncio
import base64
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services import verbali_document_import as vdi
from app.services import verbali_pagamento_finder as finder
from app.services import verbali_ricostruzione as ricostruzione
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    return asyncio.run(coro)


def _pdf(righe) -> bytes:
    buffer = io.BytesIO()
    pagina = canvas.Canvas(buffer, pagesize=A4)
    y = 800
    for riga in righe:
        pagina.drawString(40, y, riga)
        y -= 16
    pagina.save()
    return buffer.getvalue()


RIGHE_VERBALE = [
    "COMUNE DI NAPOLI - POLIZIA LOCALE",
    "Verbale n. A26110812778 Registro n. 20260200899 emesso in data 20/07/2026",
    "Violazione commessa il 10/04/2026 alle ore 15:25 in via Cesare Battisti",
    "Veicolo targa AB123CD",
    "Importo da pagare: 57,05 euro",
]


def _db(nome):
    return ClientArchivioMemoria()[nome]


def _veicolo(db, **extra):
    _run(db["veicoli_noleggio"].insert_one({
        "id": "car-1", "targa": "AB123CD", "driver_id": "d-oggi", "driver": "Anna Oggi",
        "assegnazioni": [
            {"driver_id": "d-aprile", "driver": "Mario Aprile", "dal": "2026-01-01", "al": "2026-06-30"},
            {"driver_id": "d-oggi", "driver": "Anna Oggi", "dal": "2026-07-01", "al": None},
        ], **extra}))


def _importa(db, righe=RIGHE_VERBALE, doc="doc-1", nome="scansione_001.pdf"):
    _run(db["documents_inbox"].insert_one({"id": doc}))
    esito = _run(vdi.process_verbale_document(
        db, document_id=doc, content=_pdf(righe), filename=nome))
    assert esito["status"] == "linked", esito
    return _run(db["verbali_noleggio"].find_one({"id": esito["verbale_id"]}, {"_id": 0}))


# ── 1.1 PDF -> verbale: i campi vengono dal contenuto, il driver dalla data dell'infrazione ──

def test_pdf_reale_numero_targa_importo_e_data_violazione_dal_contenuto():
    """ATTESO: numero, targa, importo, data_violazione letti dal PDF (nome file «scansione»);
    la data dell'atto redatto (20/07) NON e' la data dell'infrazione (10/04)."""
    db = _db("pdf-contenuto")
    verbale = _importa(db)
    assert verbale["numero_verbale"] == "A26110812778"
    assert verbale["targa"] == "AB123CD"
    assert verbale["importo"] == 57.05
    assert verbale["data_violazione"] == "2026-04-10"
    assert verbale["ora_violazione"] == "15:25"


def test_driver_e_quello_alla_data_dell_infrazione_non_quello_di_oggi():
    """ATTESO: l'auto era di Mario il 10/04, di Anna solo dal 01/07."""
    db = _db("driver-alla-data")
    _veicolo(db)
    verbale = _importa(db)
    assert verbale["driver_id"] == "d-aprile"
    assert verbale["driver"] == "Mario Aprile"
    assert verbale["driver_match_basis"] == "assegnazione_storica_alla_data"


def test_storico_che_non_copre_la_data_resta_da_assegnare_mai_il_driver_di_oggi():
    """ATTESO: infrazione del 10/04 ma lo storico parte dal 01/07 -> nessun driver, da rivedere."""
    db = _db("driver-scoperto")
    _veicolo(db, assegnazioni=[{"driver_id": "d-oggi", "driver": "Anna Oggi", "dal": "2026-07-01", "al": None}])
    verbale = _importa(db)
    assert not verbale.get("driver_id") and not verbale.get("driver")
    assert verbale["driver_requires_review"] is True


def test_due_assegnazioni_sovrapposte_alla_data_non_ne_scelgono_una():
    """ATTESO: due driver coprono il 10/04 -> candidati, nessun collegamento applicato."""
    db = _db("driver-ambiguo")
    _veicolo(db, assegnazioni=[
        {"driver_id": "d-1", "driver": "Mario", "dal": "2026-01-01", "al": "2026-06-30"},
        {"driver_id": "d-2", "driver": "Luca", "dal": "2026-04-01", "al": "2026-05-31"},
    ])
    verbale = _importa(db)
    assert not verbale.get("driver_id") and not verbale.get("driver")
    assert verbale["driver_requires_review"] is True
    assert {c["driver_id"] for c in verbale["driver_candidati"]} == {"d-1", "d-2"}


def test_due_veicoli_con_la_stessa_targa_non_ne_scelgono_uno():
    """ATTESO: targa non univoca -> nessun veicolo ne' driver collegato, i candidati si mostrano."""
    db = _db("targa-doppia")
    _veicolo(db)
    _run(db["veicoli_noleggio"].insert_one({
        "id": "car-2", "targa": "AB123CD", "driver_id": "d-x",
        "assegnazioni": [{"driver_id": "d-x", "driver": "Xavier", "dal": "2026-01-01", "al": None}]}))
    verbale = _importa(db)
    assert not verbale.get("veicolo_id") and not verbale.get("driver_id")
    assert verbale["driver_requires_review"] is True
    assert {c["veicolo_id"] for c in verbale["veicolo_candidati"]} == {"car-1", "car-2"}


def test_reimport_dello_stesso_pdf_non_duplica_il_verbale():
    db = _db("reimport")
    _importa(db)
    _run(vdi.process_verbale_document(db, document_id="doc-1", content=_pdf(RIGHE_VERBALE), filename="x.pdf"))
    assert len(_run(db["verbali_noleggio"].find({}).to_list(10))) == 1


# ── 1.2 quietanza (upload-quietanza) ────────────────────────────────────────────────────

PDF_QUIETANZA = base64.b64encode(_pdf(["Quietanza di pagamento", "Importo 57,05"])).decode()


def _client(monkeypatch, db):
    from app.database import Database
    from app.routers import verbali_noleggio_api as api
    from app.utils.dependencies import get_current_admin_user

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(api.router, prefix="/api/verbali-noleggio")
    app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "a", "role": "admin"}
    return TestClient(app)


def _verbale_db(nome, **extra):
    db = _db(nome)
    _run(db["verbali_noleggio"].insert_one({
        "id": "v1", "numero_verbale": "A26110812778", "targa": "AB123CD", "importo": 57.05,
        "stato": "aperto", "driver_id": "d1", "driver": "Mario", **extra}))
    return db


def _corpo(**extra):
    return {"importo_pagato": "57,05", "data_pagamento": "23/04/2026", "pdf_base64": PDF_QUIETANZA, **extra}


URL = "/api/verbali-noleggio/v1/upload-quietanza"


def test_quietanza_importo_diverso_di_un_centesimo_e_409_e_non_cambia_nulla(monkeypatch):
    db = _verbale_db("q-409")
    client = _client(monkeypatch, db)
    risposta = client.post(URL, json=_corpo(importo_pagato="57,04"))
    assert risposta.status_code == 409
    verbale = _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    assert verbale["stato"] == "aperto" and "quietanza_hash" not in verbale
    assert _run(db["trattenute_dipendenti"].count_documents({})) == 0
    assert _run(db["note_presenze_consulente"].count_documents({})) == 0


def test_quietanza_con_pdf_pagato_senza_pdf_in_attesa_e_poi_il_pdf_completa(monkeypatch):
    db = _verbale_db("q-attesa-poi-pdf")
    client = _client(monkeypatch, db)
    corpo = _corpo()
    pdf = corpo.pop("pdf_base64")
    assert client.post(URL, json=corpo).status_code == 200
    assert _run(db["verbali_noleggio"].find_one({"id": "v1"}))["stato"] == "pagato_attesa_quietanza"
    assert client.post(URL, json={**corpo, "pdf_base64": pdf}).status_code == 200
    verbale = _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    assert verbale["stato"] == "pagato" and verbale["pagato_documentalmente"] is True
    # una sola nota presenze e una sola trattenuta, anche dopo il secondo invio
    assert _run(db["note_presenze_consulente"].count_documents({})) == 1
    assert _run(db["trattenute_dipendenti"].count_documents({})) == 1


def test_un_secondo_invio_senza_pdf_non_declassa_una_quietanza_gia_documentata(monkeypatch):
    """ATTESO: «pagato» con PDF resta «pagato»: rimandare la sola data/importo non perde la prova."""
    db = _verbale_db("q-no-declassamento")
    client = _client(monkeypatch, db)
    assert client.post(URL, json=_corpo()).status_code == 200
    senza_pdf = _corpo()
    senza_pdf.pop("pdf_base64")
    assert client.post(URL, json=senza_pdf).status_code == 200
    verbale = _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    assert verbale["stato"] == "pagato"
    assert verbale["pagato_documentalmente"] is True and verbale["quietanza_ricevuta"] is True
    assert len(verbale["quietanza_hash"]) == 64


def test_la_quietanza_su_un_verbale_riconciliato_in_banca_non_lo_riporta_a_pagato(monkeypatch):
    """ATTESO: con prova bancaria gia' presente lo stato resta «riconciliato»."""
    db = _verbale_db("q-riconciliato", stato="riconciliato", banca_verificata=True,
                     pagato_documentalmente=True, movimento_banca_id="mov-1", ricevuta_pagopa_id="r1")
    client = _client(monkeypatch, db)
    assert client.post(URL, json=_corpo()).status_code == 200
    verbale = _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    assert verbale["stato"] == "riconciliato"
    assert verbale["banca_verificata"] is True


def test_quietanza_su_verbale_senza_driver_non_crea_nota_ne_trattenuta(monkeypatch):
    db = _db("q-senza-driver")
    _run(db["verbali_noleggio"].insert_one({
        "id": "v1", "numero_verbale": "A26110812778", "importo": 57.05, "stato": "aperto"}))
    client = _client(monkeypatch, db)
    assert client.post(URL, json=_corpo()).status_code == 200
    assert _run(db["trattenute_dipendenti"].count_documents({})) == 0
    assert _run(db["note_presenze_consulente"].count_documents({})) == 0
    assert _run(db["verbali_noleggio"].find_one({"id": "v1"}))["stato"] == "pagato"


# ── 1.3 riconcilia_verbali_strict: riferimento strutturato E importo al centesimo ───────

def _verbale_per_banca(db, **extra):
    _run(db["verbali_noleggio"].insert_one({
        "id": "v1", "numero_verbale": "A26110812778", "targa": "AB123CD", "importo": 57.05,
        "stato": "aperto", "data_verbale": "2026-04-20", **extra}))


def _movimento(db, mov_id, importo, descrizione, data="2026-05-05"):
    _run(db["estratto_conto_movimenti"].insert_one({
        "id": mov_id, "importo": importo, "descrizione": descrizione,
        "descrizione_originale": descrizione, "data": data, "data_contabile": data}))


def test_banca_con_numero_verbale_e_importo_al_centesimo_riconcilia():
    db = _db("strict-ok")
    _verbale_per_banca(db)
    _movimento(db, "m1", -57.05, "ADDEBITO SDD PAYPAL VERBALE A26110812778")
    esito = _run(finder.riconcilia_verbali_strict(db))
    assert esito["riconciliati"] == 1 and esito["riconciliati_banca"] == 1
    verbale = _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    assert verbale["banca_verificata"] is True and verbale["movimento_banca_id"] == "m1"
    # la sola banca non e' prova documentale
    assert verbale["pagato_documentalmente"] is False
    assert verbale["stato"] == "pagato_attesa_quietanza"


def test_banca_con_importo_diverso_di_un_centesimo_non_riconcilia():
    db = _db("strict-centesimo")
    _verbale_per_banca(db)
    _movimento(db, "m1", -57.06, "ADDEBITO SDD PAYPAL VERBALE A26110812778")
    esito = _run(finder.riconcilia_verbali_strict(db))
    assert esito["riconciliati"] == 0
    assert not _run(db["verbali_noleggio"].find_one({"id": "v1"})).get("banca_verificata")


def test_banca_solo_importo_senza_riferimento_non_riconcilia():
    db = _db("strict-solo-importo")
    _verbale_per_banca(db)
    _movimento(db, "m1", -57.05, "ADDEBITO SDD PAYPAL EUROPE")
    esito = _run(finder.riconcilia_verbali_strict(db))
    assert esito["riconciliati"] == 0


def test_banca_due_movimenti_candidati_non_ne_sceglie_uno():
    db = _db("strict-due")
    _verbale_per_banca(db)
    _movimento(db, "m1", -57.05, "ADDEBITO SDD PAYPAL VERBALE A26110812778")
    _movimento(db, "m2", -57.05, "ADDEBITO SDD PAYPAL VERBALE A26110812778", data="2026-05-06")
    esito = _run(finder.riconcilia_verbali_strict(db))
    assert esito["riconciliati"] == 0


def test_un_accredito_in_entrata_non_e_il_pagamento_del_verbale():
    """ATTESO: un rimborso (+57,05) che cita il numero del verbale non paga il verbale."""
    db = _db("strict-entrata")
    _verbale_per_banca(db)
    _movimento(db, "m1", 57.05, "RIMBORSO VERBALE A26110812778")
    esito = _run(finder.riconcilia_verbali_strict(db))
    assert esito["riconciliati"] == 0
    assert not _run(db["verbali_noleggio"].find_one({"id": "v1"})).get("banca_verificata")


# ── 1.4 ricostruzione dal PDF ────────────────────────────────────────────────────────────

def _riga_con_pdf(db, riga_id, numero, righe, **campi):
    contenuto = _pdf(righe)
    _run(db["verbali_noleggio"].insert_one({
        "id": riga_id, "numero_verbale": numero, "source": "documenti_upload_auto",
        "origine": "VERBALE_ORIGINALE", "stato": "aperto",
        "pdf_filename": "verbale.pdf", "pdf_hash": "h-" + riga_id,
        "pdf_data": base64.b64encode(contenuto).decode(), **campi}))


def test_ricostruzione_riempie_solo_i_vuoti_segnala_il_conflitto_e_il_secondo_giro_e_zero():
    db = _db("ricostruzione")
    _riga_con_pdf(db, "v1", "A26110812778", RIGHE_VERBALE, importo=60.0)   # importo in conflitto
    anteprima = _run(ricostruzione.ricostruisci_verbali_da_pdf(db))
    assert anteprima["scritti"] == 0 and anteprima["conflitti"] == 1
    assert "targa" not in _run(db["verbali_noleggio"].find_one({"id": "v1"}))

    primo = _run(ricostruzione.ricostruisci_verbali_da_pdf(db, dry_run=False))
    riga = _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    assert primo["scritti"] == 1
    assert riga["targa"] == "AB123CD" and riga["data_violazione"] == "2026-04-10"
    assert riga["importo"] == 60.0                      # il conflitto non si applica mai
    assert primo["elenco_conflitti"][0]["campo"] == "importo"

    secondo = _run(ricostruzione.ricostruisci_verbali_da_pdf(db, dry_run=False))
    assert secondo["da_fare"] == 0 and secondo["scritti"] == 0


# ── 1.5 riconcilia/{numero}: il driver e' quello alla data dell'INFRAZIONE ───────────────

def _db_riconcilia(nome, **verbale):
    db = _db(nome)
    _veicolo(db)
    _run(db["dipendenti"].insert_one({"id": "d-aprile", "nome": "Mario", "cognome": "Aprile"}))
    _run(db["dipendenti"].insert_one({"id": "d-oggi", "nome": "Anna", "cognome": "Oggi"}))
    _run(db["verbali_noleggio"].insert_one({
        "id": "v1", "numero_verbale": "A26110812778", "targa": "AB123CD", "importo": 57.05,
        "stato": "salvato", "data_violazione": "2026-04-10", "data_verbale": "2026-07-20", **verbale}))
    return db


@pytest.mark.parametrize("verificata", [True, False])
def test_riconcilia_propone_il_driver_alla_data_della_violazione_non_a_quella_dell_atto(monkeypatch, verificata):
    """ATTESO: infrazione 10/04 (Mario), atto redatto 20/07 (quando guida Anna): si propone Mario."""
    from app.database import Database
    from app.routers.verbali_riconciliazione import riconcilia_verbale

    db = _db_riconcilia(f"riconcilia-{verificata}", data_verbale_verificata=verificata)
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    anteprima = _run(riconcilia_verbale("A26110812778", dry_run=True))
    assert [p["target_id"] for p in anteprima["proposte"] if p["tipo"] == "DRIVER_VERBALE"] == ["d-aprile"]
    assert "driver_id" not in _run(db["verbali_noleggio"].find_one({"id": "v1"}))   # l'anteprima non scrive

    _run(riconcilia_verbale("A26110812778", dry_run=False))
    assert _run(db["verbali_noleggio"].find_one({"id": "v1"}))["driver_id"] == "d-aprile"


def test_collega_driver_massivo_con_storico_scoperto_non_applica_il_driver_di_oggi(monkeypatch):
    from app.database import Database
    from app.routers.verbali_riconciliazione import collega_driver_massivo

    db = _db("massivo-scoperto")
    _veicolo(db, assegnazioni=[{"driver_id": "d-oggi", "driver": "Anna Oggi", "dal": "2026-07-01", "al": None}])
    _run(db["verbali_noleggio"].insert_one({
        "id": "v1", "numero_verbale": "A26110812778", "targa": "AB123CD", "importo": 57.05,
        "stato": "salvato", "data_violazione": "2026-04-10"}))
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    _run(collega_driver_massivo())

    verbale = _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    assert not verbale.get("driver_id") and not verbale.get("driver")


# ── 2. PEC di notifica ───────────────────────────────────────────────────────────────────

from app.services import notifiche_pec_verbali as pec  # noqa: E402

OGGETTO_PEC = ("POSTA CERTIFICATA: Notifica di atto amministrativo relativo ad una sanzione "
               "amministrativa prevista dal codice della strada Atto 20260200899 del 20/07/2026 [upec7468533]")
MITTENTE_PEC = '"Per conto di: notifica.pl.napoli@pec.it" <posta-certificata@pec.aruba.it>'
DATA_PEC = "Thu, 23 Jul 2026 17:22:30 +0200"
COPIA_CONFORME = ["COPIA CONFORME", "Verbale n. A26110812778 - cronologico Registro n. 20260200899 "
                  "data verbale 20/07/2026", "targato AB123CD"]


def _db_pec(nome, con_verbale=True, **verbale):
    db = _db(nome)
    contenuto = base64.b64encode(_pdf(COPIA_CONFORME)).decode()
    _run(db["verbali_email_attachments"].insert_one({
        "id": "att1", "filename": "COPIACONFORMEPEC_7468533.pdf", "pdf_hash": "h1", "pdf_data": contenuto,
        "email_subject": OGGETTO_PEC, "email_from": MITTENTE_PEC, "email_date": DATA_PEC}))
    _run(db["verbali_noleggio"].insert_one(
        {"id": "orfano", "numero_verbale": "A26110812778", "source": "gmail_scan", "stato": "salvato"}))
    if con_verbale:
        _run(db["verbali_noleggio"].insert_one(
            {"id": "v1", "numero_verbale": "A26110812778", "targa": "AB123CD", "stato": "aperto",
             "source": "documenti_upload_auto", **verbale}))
    return db


def test_pec_data_notifica_e_scadenze_5_30_60_sul_verbale_vero_non_sull_orfano():
    """ATTESO: PEC del 23/07 -> data_notifica 2026-07-23; ridotto 28/07, GdP 22/08, Prefetto 21/09."""
    db = _db_pec("pec-scadenze")
    esito = _run(pec.aggancia_notifiche_pec(db, dry_run=False))
    assert esito["agganciate"] == 1 and esito["da_agganciare"] == 0
    verbale = _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    assert verbale["data_notifica"] == "2026-07-23"
    assert verbale["scadenze_ricorso"] == {
        "pagamento_ridotto": "2026-07-28", "ricorso_giudice_di_pace": "2026-08-22",
        "ricorso_prefetto": "2026-09-21"}
    assert "notifiche_pec" not in _run(db["verbali_noleggio"].find_one({"id": "orfano"}))
    assert len(_run(db["verbali_noleggio"].find({}).to_list(10))) == 2     # nessun verbale nuovo


def test_la_data_della_pec_vince_su_una_data_notifica_nata_da_una_mail_successiva():
    """ATTESO: la PEC e' la prova della notifica: se il verbale porta una data_notifica piu' tarda
    (ricezione di una mail), data_notifica e scadenze devono contare dalla PEC, non da due date diverse."""
    db = _db_pec("pec-vince", data_notifica="2026-08-10")
    _run(pec.aggancia_notifiche_pec(db, dry_run=False))
    verbale = _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    assert verbale["data_notifica"] == "2026-07-23"
    assert verbale["scadenze_ricorso"]["pagamento_ridotto"] == "2026-07-28"


def test_la_scadenza_dello_sconto_dell_attesa_si_allinea_alla_pec():
    """ATTESO: la DECISIONE_VERBALE nata senza data di notifica riceve la scadenza ridotta dalla PEC."""
    db = _db("pec-attesa")
    verbale = _importa(db)
    attesa = _run(db["workflow_expectations"].find_one(
        {"id": f"verbale:{verbale['id']}:DECISIONE_VERBALE"}))
    assert attesa["discount_deadline"] is None
    contenuto = base64.b64encode(_pdf(COPIA_CONFORME)).decode()
    _run(db["verbali_email_attachments"].insert_one({
        "id": "att1", "filename": "COPIACONFORMEPEC_7468533.pdf", "pdf_hash": "h1", "pdf_data": contenuto,
        "email_subject": OGGETTO_PEC, "email_from": MITTENTE_PEC, "email_date": DATA_PEC}))
    _run(pec.aggancia_notifiche_pec(db, dry_run=False))
    attesa = _run(db["workflow_expectations"].find_one(
        {"id": f"verbale:{verbale['id']}:DECISIONE_VERBALE"}))
    assert attesa["discount_deadline"] == "2026-07-28"


def test_pec_senza_verbale_resta_da_agganciare_e_due_verbali_con_lo_stesso_numero_non_si_toccano():
    db = _db_pec("pec-assente", con_verbale=False)
    esito = _run(pec.aggancia_notifiche_pec(db, dry_run=False))
    assert esito["da_agganciare"] == 1 and esito["agganciate"] == 0
    assert _run(db["verbali_email_attachments"].find_one({"id": "att1"}))["notifica_stato"] == "da_agganciare"

    db2 = _db_pec("pec-doppio")
    _run(db2["verbali_noleggio"].insert_one(
        {"id": "v2", "numero_verbale": "A26110812778", "stato": "aperto", "source": "documenti_upload_auto"}))
    esito = _run(pec.aggancia_notifiche_pec(db2, dry_run=False))
    assert esito["agganciate"] == 0
    assert "notifiche_pec" not in _run(db2["verbali_noleggio"].find_one({"id": "v1"}))
    assert "notifiche_pec" not in _run(db2["verbali_noleggio"].find_one({"id": "v2"}))


def test_una_riga_in_quarantena_con_lo_stesso_numero_non_blocca_l_aggancio_della_pec():
    db = _db_pec("pec-quarantena")
    _run(db["verbali_noleggio"].insert_one(
        {"id": "q1", "numero_verbale": "A26110812778", "stato": "quarantena", "source": "scan_fatture"}))
    esito = _run(pec.aggancia_notifiche_pec(db, dry_run=False))
    assert esito["agganciate"] == 1
    assert _run(db["verbali_noleggio"].find_one({"id": "v1"}))["data_notifica"] == "2026-07-23"
    assert "notifiche_pec" not in _run(db["verbali_noleggio"].find_one({"id": "q1"}))


def test_quietanza_caricata_prima_del_driver_completa_nota_e_trattenuta_al_rinvio(monkeypatch):
    """ATTESO: il verbale e' pagato ma senza driver (nessuna trattenuta); assegnato il driver, il rinvio
    della stessa quietanza crea la nota e UNA proposta di trattenuta; un ulteriore rinvio non crea altro."""
    db = _db("q-driver-dopo")
    _run(db["verbali_noleggio"].insert_one({
        "id": "v1", "numero_verbale": "A26110812778", "importo": 57.05, "stato": "aperto"}))
    client = _client(monkeypatch, db)
    assert client.post(URL, json=_corpo()).json()["duplicato"] is False
    assert _run(db["trattenute_dipendenti"].count_documents({})) == 0

    _run(db["verbali_noleggio"].update_one({"id": "v1"}, {"$set": {"driver_id": "d1", "driver": "Mario"}}))
    secondo = client.post(URL, json=_corpo()).json()
    assert secondo["duplicato"] is False
    assert _run(db["trattenute_dipendenti"].count_documents({})) == 1
    assert _run(db["note_presenze_consulente"].count_documents({})) == 1
    terzo = client.post(URL, json=_corpo()).json()
    assert terzo["duplicato"] is True
    assert _run(db["trattenute_dipendenti"].count_documents({})) == 1
    assert _run(db["note_presenze_consulente"].count_documents({})) == 1


def test_una_nota_gia_inviata_al_consulente_non_si_sposta_di_mese_al_rinvio(monkeypatch):
    db = _verbale_db("q-nota-inviata")
    client = _client(monkeypatch, db)
    assert client.post(URL, json=_corpo()).status_code == 200
    _run(db["note_presenze_consulente"].update_one(
        {"verbale_id": "v1"}, {"$set": {"inviato_consulente": True, "mese": 3, "anno": 2026}}))
    senza_pdf = _corpo()
    senza_pdf.pop("pdf_base64")
    assert client.post(URL, json=senza_pdf).status_code == 200
    nota = _run(db["note_presenze_consulente"].find_one({"verbale_id": "v1"}))
    assert (nota["mese"], nota["anno"], nota["inviato_consulente"]) == (3, 2026, True)


def test_copia_conforme_della_pec_legge_numero_targa_e_data_dell_infrazione_dal_contenuto():
    """ATTESO: «data verbale» (15/03) e' l'atto, «In data 14/03» e' l'infrazione; senza importo resta vuoto."""
    db = _db("copia-conforme")
    _veicolo(db, assegnazioni=[
        {"driver_id": "d-marzo", "driver": "Luca Marzo", "dal": "2026-03-01", "al": "2026-03-14"},
        {"driver_id": "d-dopo", "driver": "Anna Dopo", "dal": "2026-03-15", "al": None}])
    righe = ["COPIA CONFORME", "Verbale n. A24110662140 - cronologico Registro n. 20240160976 data verbale 15/03/2026",
             "In data 14/03/2026 alle ore 09:10 targato AB123CD"]
    verbale = _importa(db, righe, nome="COPIACONFORMEPEC_7468533.pdf")
    assert verbale["numero_verbale"] == "A24110662140"
    assert verbale["targa"] == "AB123CD" and verbale["data_violazione"] == "2026-03-14"
    assert verbale["driver_id"] == "d-marzo"
    assert verbale["importo"] is None
