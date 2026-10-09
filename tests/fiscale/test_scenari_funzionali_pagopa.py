"""Collaudo funzionale PagoPA: ricevute, cartelle di pagamento, natura e IUV, con PDF reali.

Scenari dell'utente (CLAUDE.md, «Ricevute di pagamento pagoPA» e «Cartella di pagamento»):
- la ricevuta si legge voce per voce e la somma deve fare il totale al centesimo;
- stesso IUV, data e importo = un solo pagamento;
- la cartella apre subito l'attesa «da pagare», senza scadenza finche' non c'e' la notifica,
  e la chiude solo la ricevuta con lo stesso IUV e lo stesso importo;
- la natura la sceglie il titolare; l'IUV e' sempre testo.
"""
import asyncio
import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import cartelle_pagamento as cp
from app.services import pagopa_receipts as modulo
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.pagopa_receipts import import_receipt, parse_receipt_pdf

def _run(coro):
    return asyncio.run(coro)


def _pdf(righe) -> bytes:
    doc = fitz.open()
    pagina = doc.new_page()
    y = 30
    for riga in righe:
        pagina.insert_text((30, y), riga, fontsize=8, fontname="helv")
        y += 12
    contenuto = doc.tobytes()
    doc.close()
    return contenuto


# Codice avviso dell'Agente della riscossione: «1» + IUV di 17 cifre. La ricevuta CBILL della banca
# riporta il codice avviso intero, la cartella lo stampa e ne ricava lo IUV.
AVVISO = "180071502664980543"
IUV = AVVISO[1:]

RIGHE_CARTELLA = [
    "Spett. AZIENDA TEST SRL", "CARTELLA DI PAGAMENTO N. 071 2026 00000001 11/000",
    "Agenzia delle entrate-Riscossione", "Totale da pagare entro 60 giorni dalla data di notifica",
    "euro 126,68", "120,80", "5,88", "126,68",
    "RUOLO EMESSO DA", "Comune di Prova Polizia Urbana", "RUOLO N. 2026/000001",
    "1", "2025", "5242 Contrav.cod.strada l.689/81", "120,80",
    "VER. 111/V/2025 31/03/2025 NOT. IL 02/06/2025 TG. AB123CD ART. 7",
    "Destinatario Cod. Fiscale 00000000000", "AJZ8Z", AVVISO,
]


def _cbill(operazione="126,68", commissione="2,85", totale="129,53", codice=AVVISO, data="11/09/2026",
           extra=()):
    return _pdf([
        "Identificativo bolletta:", "Numero bolletta:", "Importo:", "Commissioni:", "Totale:", codice,
        "8007150266", f"{operazione} EUR", f"{commissione} EUR", f"{totale} EUR", "Stato operazione:",
        "Confermata - Eseguita", "Data esecuzione:", data, "Informaz. aggiuntive:", "CBILL - pagoPA",
        "Beneficiario:", "AGENZIA DELLE ENTRATE - RISCOSSIONE", "Codice benef.:", "AJZ8Z",
        "N. versamento:", "IW3254069973", *extra])


def _db(nome):
    return ClientArchivioMemoria()[nome]


def _cartella(db):
    esito = _run(cp.registra_cartella(db, "cartella.pdf", _pdf(RIGHE_CARTELLA)))
    assert esito["success"] and esito["iuv"] == IUV
    return esito["id"]


def _stato_cartella(db, cartella_id):
    return _run(db[cp.COLL].find_one({"id": cartella_id}, {"_id": 0, "contenuto_b64": 0}))


# ── cartella di pagamento ────────────────────────────────────────────────────────────────

def test_cartella_apre_l_attesa_senza_scadenza_e_la_scadenza_nasce_solo_dalla_notifica(monkeypatch):
    """ATTESO: attesa CARTELLA_DA_PAGARE aperta, scadenza vuota; poi PUT notifica -> +60 giorni."""
    from app.database import Database
    from app.routers import pagopa as router

    db = _db("cartella-notifica")
    cartella_id = _cartella(db)
    doc = _stato_cartella(db, cartella_id)
    assert doc["expectation_type"] == "CARTELLA_DA_PAGARE" and doc["expectation_status"] == "ATTESO"
    assert doc["data_notifica"] is None and doc["scadenza"] is None

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(router.router, prefix="/api/pagopa")
    client = TestClient(app)
    assert client.put(f"/api/pagopa/cartelle/{cartella_id}/notifica",
                      json={"data_notifica": "31/13/2026"}).status_code == 400
    assert _stato_cartella(db, cartella_id)["scadenza"] is None
    ok = client.put(f"/api/pagopa/cartelle/{cartella_id}/notifica", json={"data_notifica": "2026-07-25"})
    assert ok.status_code == 200 and ok.json()["scadenza"] == "2026-09-23"


def test_ricevuta_cbill_con_codice_avviso_chiude_la_cartella_con_lo_stesso_importo():
    """ATTESO: la ricevuta CBILL cita il codice avviso (1+IUV): e' lo stesso IUV della cartella.
    Importo operazione 126,68 = totale cartella -> SODDISFATTO."""
    db = _db("cartella-chiusa")
    cartella_id = _cartella(db)
    esito = _run(import_receipt(db, content=_cbill(), filename="doc.pdf", company_id="c"))
    assert esito["success"] is True and esito["receipt"]["importo"] == 126.68
    doc = _stato_cartella(db, cartella_id)
    assert doc["expectation_status"] == "SODDISFATTO"
    assert doc["ricevuta_id"] == esito["receipt"]["id"]


def test_ricevuta_arrivata_prima_della_cartella_la_chiude_alla_registrazione():
    db = _db("cartella-dopo")
    esito = _run(import_receipt(db, content=_cbill(), filename="doc.pdf", company_id="c"))
    assert esito["success"] is True
    cartella_id = _cartella(db)
    assert _stato_cartella(db, cartella_id)["expectation_status"] == "SODDISFATTO"


def test_ricevuta_con_importo_diverso_di_un_centesimo_lascia_la_cartella_da_verificare():
    db = _db("cartella-importo")
    cartella_id = _cartella(db)
    _run(import_receipt(db, content=_cbill(operazione="126,67", totale="129,52"),
                        filename="doc.pdf", company_id="c"))
    assert _stato_cartella(db, cartella_id)["expectation_status"] == "DA_VERIFICARE"


def test_ricevuta_di_un_altro_iuv_non_tocca_la_cartella():
    db = _db("cartella-altro-iuv")
    cartella_id = _cartella(db)
    _run(import_receipt(db, content=_cbill(codice="180071502664980999"), filename="doc.pdf", company_id="c"))
    assert _stato_cartella(db, cartella_id)["expectation_status"] == "ATTESO"


# ── ricevuta: voci e totale, un solo pagamento ───────────────────────────────────────────

def test_cbill_stesso_iuv_data_e_importo_da_un_secondo_file_non_duplica():
    db = _db("ricevuta-doppia")
    primo = _run(import_receipt(db, content=_cbill(), filename="a.pdf", company_id="c"))
    secondo = _run(import_receipt(db, content=_cbill(extra=("copia scaricata dal portale",)),
                                  filename="b.pdf", company_id="c"))
    assert primo["duplicate"] is False
    assert secondo["duplicate"] is True and secondo["duplicate_motivo"] == "stesso_iuv_importo_data"
    assert _run(db["ricevute_pagopa"].count_documents({})) == 1


def test_stesso_iuv_con_un_altro_importo_o_un_altro_giorno_e_un_altro_pagamento():
    db = _db("ricevuta-due-pagamenti")
    _run(import_receipt(db, content=_cbill(), filename="a.pdf", company_id="c"))
    _run(import_receipt(db, content=_cbill(operazione="50,00", totale="52,85"), filename="b.pdf", company_id="c"))
    _run(import_receipt(db, content=_cbill(data="12/09/2026"), filename="c.pdf", company_id="c"))
    assert _run(db["ricevute_pagopa"].count_documents({})) == 3


def test_bpm_con_totale_stampato_che_non_quadra_non_e_un_pagamento():
    """ATTESO: operazione 34,90 + commissione 2,85 = 37,75; se la ricevuta stampa 37,76 la somma
    non torna: niente pagamento registrato, resta da verificare (mai «corretto» in silenzio)."""
    def ricevuta(totale):
        return _pdf(["UTENZE E SERVIZI: ADDEBITO", "CBILL - pagoPA", "CODICE IDENTIFICATIVO CBILL",
                     "301001500092427141", "IMPORTO OPERAZIONE", "34,90", "COMMISSIONI", "2,85",
                     "TOTALE ADDEBITO", totale, "CODICE TRANSAZIONE CBILL 03575825444", "11/09/2026"])

    parsed = parse_receipt_pdf(ricevuta("37,76"), "x.pdf")
    assert parsed["is_payment_receipt"] is False
    db = _db("bpm-non-quadra")
    esito = _run(import_receipt(db, content=ricevuta("37,76"), filename="x.pdf", company_id="c"))
    assert esito["success"] is False and esito["requires_review"] is True
    assert _run(db["ricevute_pagopa"].count_documents({})) == 0

    corretta = _run(import_receipt(db, content=ricevuta("37,75"), filename="y.pdf", company_id="c"))
    assert corretta["success"] is True
    assert corretta["receipt"]["bank_debit_total_cents"] == 3775


def test_mooney_con_voci_che_non_tornano_non_e_un_pagamento(monkeypatch):
    testo = ("mooney\nRICEVUTAPERL'UTENTE\nDatae0ra:01/09/202610:15\nBeneficiario:ENTETEST\n"
             "IUV:80070000000000001\nImporto: 5,88\nDiritti: 1,50\nTotale: 7,83\n"
             "PayPal ID: 1AB23456CD789012E\nPagamentoimmediatamenteassolto\n")
    monkeypatch.setattr(modulo, "_righe_ocr_per_posizione", lambda _c: testo)
    contenuto = _pdf(["RICEVUTA PER L'UTENTE", "Servizio erogato da Mooney S.p.A. Albo IMEL",
                      "Importo: 5,88", "Diritti: 1,50", "Totale: 7,83"])
    db = _db("mooney-non-quadra")
    esito = _run(import_receipt(db, content=contenuto, filename="m.pdf", company_id="c"))
    assert esito["success"] is False and esito["requires_review"] is True
    assert _run(db["ricevute_pagopa"].count_documents({})) == 0


# ── natura: la sceglie il titolare ───────────────────────────────────────────────────────

def test_la_natura_la_sceglie_il_titolare_senza_toccare_importi_ne_collegamenti(monkeypatch):
    from app.database import Database
    from app.routers import pagopa as router

    db = _db("natura")
    esito = _run(import_receipt(db, content=_cbill(), filename="a.pdf", company_id="c"))
    ricevuta = esito["receipt"]
    assert not ricevuta.get("natura")                         # la ricevuta non lo dice
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(router.router, prefix="/api/pagopa")
    client = TestClient(app)

    assert client.put(f"/api/pagopa/ricevute/{ricevuta['id']}/natura", json={"natura": "boh"}).status_code == 400
    assert client.put("/api/pagopa/ricevute/nope/natura", json={"natura": "tributo"}).status_code == 404

    assert client.put(f"/api/pagopa/ricevute/{ricevuta['id']}/natura", json={"natura": "tributo"}).status_code == 200
    assert client.put(f"/api/pagopa/ricevute/{ricevuta['id']}/natura",
                      json={"natura": "sanzione_interessi"}).status_code == 200
    salvata = _run(db["ricevute_pagopa"].find_one({"id": ricevuta["id"]}, {"_id": 0}))
    assert salvata["natura"] == "sanzione_interessi"
    assert [s["natura"] for s in salvata["storico_natura"]] == ["tributo"]
    assert salvata["importo"] == 126.68 and salvata["identificativo_bolletta"] == AVVISO
    assert salvata.get("movimento_id") == ricevuta.get("movimento_id")


def test_oneri_e_sanzioni_associano_la_ricevuta_senza_movimento_di_banca(monkeypatch):
    """Scelta del titolare 06/10/2026: oneri e sanzioni bastano a dirla «associata»; tributo no."""
    from app.database import Database
    from app.routers import pagopa as router

    db = _db("natura_associata")
    esito = _run(import_receipt(db, content=_cbill(), filename="a.pdf", company_id="c"))
    ricevuta = esito["receipt"]
    _run(db["ricevute_pagopa"].update_one({"id": ricevuta["id"]}, {"$set": {"movimento_id": None}}))
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(router.router, prefix="/api/pagopa")
    client = TestClient(app)
    url = f"/api/pagopa/ricevute/{ricevuta['id']}/natura"

    def stato():
        riga = next(r for r in client.get("/api/pagopa/ricevute").json() if r["id"] == ricevuta["id"])
        return riga["associata_per_natura"], client.get("/api/pagopa/stats").json()["ricevute_associate"]

    assert client.put(url, json={"natura": "tributo"}).json()["associata_per_natura"] is False
    assert stato() == (False, 0)
    assert client.put(url, json={"natura": "onere_pratica"}).json()["associata_per_natura"] is True
    assert stato() == (True, 1)
    assert client.put(url, json={"natura": "sanzione_interessi"}).json()["associata_per_natura"] is True
    assert stato() == (True, 1)
    assert client.put(url, json={"natura": "altro"}).json()["associata_per_natura"] is False
    assert stato() == (False, 0)


# ── IUV sempre testo ─────────────────────────────────────────────────────────────────────

def test_iuv_con_zero_iniziale_resta_testo_dal_pdf_all_archivio():
    from app.services import verbali_document_import as vdi

    iuv = "01234567890123456"
    letto = _run(vdi.leggi_documento_verbale(
        _pdf(["Avviso di pagamento", "Verbale n. A26110812778", f"IUV {iuv}", "Importo da pagare: 57,05"]),
        "avviso.pdf"))
    assert letto["iuv"] == iuv and isinstance(letto["iuv"], str)
    # un intero ha gia' perso lo zero: non si indovina; un float ha perso le cifre
    assert vdi.normalizza_iuv(1234567890123456) is None
    assert vdi.normalizza_iuv(float(iuv)) is None
    assert vdi.normalizza_iuv(iuv) == iuv

    db = _db("iuv-testo")
    _run(db["documents_inbox"].insert_one({"id": "d1"}))
    _run(vdi.process_verbale_document(
        db, document_id="d1", filename="avviso.pdf",
        content=_pdf(["Verbale n. A26110812778", f"IUV {iuv}", "Importo da pagare: 57,05"])))
    verbale = _run(db["verbali_noleggio"].find_one({}))
    assert verbale["iuv"] == iuv and isinstance(verbale["iuv"], str)


# ── ricevuta -> verbale: IUV e importo al centesimo ──────────────────────────────────────

def _mooney_ricevuta(monkeypatch, iuv="80070000000000001"):
    testo = ("mooney\nRICEVUTAPERL'UTENTE\nDatae0ra:01/09/202610:15\nBeneficiario:ENTETEST\n"
             f"IUV:{iuv}\nID Operazione:9999999\nImporto: 5,88\nDiritti: 1,50\nTotale: 7,38\n"
             "PayPal ID: 1AB23456CD789012E\nPagamentoimmediatamenteassolto\n")
    monkeypatch.setattr(modulo, "_righe_ocr_per_posizione", lambda _c: testo)
    return _pdf(["RICEVUTA PER L'UTENTE", "Servizio erogato da Mooney S.p.A. Albo IMEL",
                 "Importo: 5,88", "Diritti: 1,50", "Totale: 7,38"])


def test_ricevuta_con_lo_stesso_iuv_paga_il_verbale_solo_se_l_importo_torna_al_centesimo(monkeypatch):
    contenuto = _mooney_ricevuta(monkeypatch)
    db = _db("ricevuta-verbale")
    _run(db["verbali_noleggio"].insert_many([
        {"id": "v-ok", "numero_verbale": "A1", "iuv": "80070000000000001", "importo": 5.88, "stato": "salvato"},
    ]))
    esito = _run(import_receipt(db, content=contenuto, filename="m.pdf", company_id="c"))
    assert esito["riconciliazione_verbale"]["matched"] is True
    verbale = _run(db["verbali_noleggio"].find_one({"id": "v-ok"}))
    assert verbale["stato"] == "pagato" and verbale["pagato_documentalmente"] is True

    db2 = _db("ricevuta-verbale-centesimo")
    _run(db2["verbali_noleggio"].insert_one(
        {"id": "v-no", "numero_verbale": "A2", "iuv": "80070000000000001", "importo": 5.89, "stato": "salvato"}))
    esito = _run(import_receipt(db2, content=contenuto, filename="m.pdf", company_id="c"))
    assert esito["riconciliazione_verbale"]["matched"] is False
    assert _run(db2["verbali_noleggio"].find_one({"id": "v-no"}))["stato"] == "salvato"
