"""AV3-09: ricostruzione dei verbali dal PDF, collegamento unico, date e identificativi."""

import asyncio
import base64

import pytest
from fastapi.testclient import TestClient

from app.services import verbali_document_import as vdi
from app.services import verbali_ricostruzione as mod
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.verbali_collegamento_fattura import (
    campi_da_fattura, fattura_id_del_verbale, fattura_numero_del_verbale,
)
from app.services.verbali_evidence import data_evento_verbale, data_violazione_verbale


def _run(coro):
    return asyncio.run(coro)


def _pdf(tag: bytes) -> str:
    return base64.b64encode(b"%PDF-1.4 " + tag).decode("ascii")


TESTI = {
    b"%PDF-1.4 copia-A": ("Verbale n. A24110662140 - cronologico Registro n. 20240160976 "
                          "data verbale 15/03/2024 In data 14/03/2024 Targa GG782PN Totale 57,05"),
    b"%PDF-1.4 copia-barre": "Verbale n. 111/V/2025 Targa AB123CD in data 02/05/2025 Totale 80,00",
    b"%PDF-1.4 copia-B": "Verbale n. B25110000001 Targa ZZ999ZZ in data 01/06/2025 Totale 41,00",
    b"%PDF-1.4 copia-senza": "Comunicazione generica senza numero",
}


@pytest.fixture(autouse=True)
def _testo_dei_pdf(monkeypatch):
    monkeypatch.setattr(vdi, "_extract_text", lambda content: TESTI.get(content, ""))
    # I byte segnaposto non sono PDF reali. Anche il lettore delle ricevute
    # resta isolato: questi casi verificano verbali, non parsing/OCR PagoPA.
    monkeypatch.setattr("app.services.pagopa_receipts.parse_receipt_pdf", lambda content, **kwargs: {})


def _db(nome="t"):
    return ClientArchivioMemoria()[nome]


def _pec(db, riga_id, tag, numero="VERB-abc12345"):
    _run(db["verbali_noleggio"].insert_one({
        "id": riga_id, "numero_verbale": numero, "source": "gmail_scan", "stato": "salvato",
        "pdf_filename": "COPIACONFORMEPEC_1.pdf", "pdf_hash": "h-" + riga_id, "pdf_data": _pdf(tag),
    }))


def _verbale(db, riga_id, numero, **campi):
    _run(db["verbali_noleggio"].insert_one(
        {"id": riga_id, "numero_verbale": numero, "source": "documenti_upload_auto",
         "origine": "VERBALE_ORIGINALE", "stato": "aperto", **campi}))


def _riga(db, riga_id):
    return _run(db["verbali_noleggio"].find_one({"id": riga_id}, {"_id": 0}))


# ── anteprima e idempotenza ─────────────────────────────────────────────────────────────

def test_anteprima_non_scrive_e_conta():
    db = _db("anteprima")
    _verbale(db, "v1", "A24110662140")
    _pec(db, "p1", b"copia-A")
    prima = _riga(db, "v1")

    esito = _run(mod.ricostruisci_verbali_da_pdf(db))

    assert esito["dry_run"] is True
    assert esito["pec_su_verbale_vero"] == 1
    assert esito["da_completare"] == 1
    assert esito["campi_da_riempire"].get("targa") == 1 and esito["campi_da_riempire"].get("importo") == 1
    assert esito["scritti"] == 0 and esito["da_fare"] == 1
    assert _riga(db, "v1") == prima      # nessuna scrittura


def test_applicazione_riempie_solo_i_campi_vuoti_e_il_secondo_giro_e_zero():
    db = _db("idempotenza")
    _verbale(db, "v1", "A24110662140", importo=57.05)   # importo gia' uguale: non si tocca
    _pec(db, "p1", b"copia-A")

    primo = _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False))
    verbale = _riga(db, "v1")

    assert primo["scritti"] == 1
    assert verbale["targa"] == "GG782PN"
    assert verbale["data_violazione"] == "2024-03-14"
    assert verbale["importo"] == 57.05

    secondo = _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False))
    assert secondo["da_fare"] == 0 and secondo["scritti"] == 0


def test_conflitto_di_importo_e_un_candidato_mai_applicato():
    db = _db("conflitto")
    _verbale(db, "v1", "A24110662140", importo=100.0)
    _pec(db, "p1", b"copia-A")

    esito = _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False))

    assert esito["conflitti"] == 1
    assert esito["elenco_conflitti"][0]["campo"] == "importo"
    assert _riga(db, "v1")["importo"] == 100.0


def test_due_verbali_con_lo_stesso_numero_sono_ambigui_e_non_si_toccano():
    db = _db("ambiguo")
    _verbale(db, "v1", "A24110662140")
    _verbale(db, "v2", "A24110662140")
    _pec(db, "p1", b"copia-A")

    esito = _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False))

    assert esito["pec_ambigue"] == 1 and esito["pec_su_verbale_vero"] == 0
    assert "targa" not in _riga(db, "v1") and "targa" not in _riga(db, "v2")


def test_per_solo_importo_non_si_identifica_nulla():
    db = _db("solo-importo")
    _verbale(db, "v1", "A99999999999", importo=57.05)      # stesso importo della copia, altro numero
    _pec(db, "p1", b"copia-A")

    esito = _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False))

    assert esito["pec_su_verbale_vero"] == 0
    assert "targa" not in _riga(db, "v1")


def test_numero_con_barre_si_legge_e_aggancia_il_verbale_vero():
    assert vdi._extract_numero("Verbale n. 111/V/2025 del 12/03/2025") == "111/V/2025"
    assert vdi._extract_numero("Verbale di accertamento n. 2025/000123") == "2025/000123"
    assert vdi._extract_numero("verbale 12/03/2025 redatto") is None   # una data non e' un numero
    assert vdi.normalizza_numero_verbale("  vv / 26990019358 ") == "VV/26990019358"
    db = _db("barre")
    _verbale(db, "v1", "111/V/2025")
    _pec(db, "p1", b"copia-barre")

    esito = _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False))

    assert esito["pec_su_verbale_vero"] == 1
    assert _riga(db, "v1")["targa"] == "AB123CD"


def test_iuv_e_sempre_testo_e_non_perde_lo_zero_iniziale():
    assert vdi.normalizza_iuv("02000600005080318") == "02000600005080318"
    assert vdi.normalizza_iuv(" 3020 0060 0005 0803 18 ") == "302000600005080318"
    assert vdi.normalizza_iuv(2000600005080318) is None          # int: lo zero e' perso, non si indovina
    assert vdi.normalizza_iuv(3.02e17) is None                   # float: mai
    assert vdi.normalizza_iuv("ABC") is None


def test_pec_senza_verbale_vero_resta_candidata_e_si_apre_solo_su_richiesta():
    db = _db("da-creare")
    _pec(db, "p1", b"copia-B")

    anteprima = _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False))
    assert anteprima["pec_da_creare"] == 1 and anteprima["creati"] == 0
    assert anteprima["da_fare"] == 0
    assert _run(db["verbali_noleggio"].count_documents({})) == 1   # la riga VERB- resta, nessuno nuovo

    creati = _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False, crea_da_pec=True))
    assert creati["creati"] == 1
    assert _run(db["verbali_noleggio"].count_documents({"numero_verbale": "B25110000001"})) == 1
    assert _run(db["verbali_noleggio"].count_documents({"numero_verbale": "VERB-abc12345"})) == 1  # mai cancellata

    terzo = _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False, crea_da_pec=True))
    assert terzo["creati"] == 0 and terzo["pec_da_creare"] == 0 and terzo["pec_su_verbale_vero"] == 1
    assert terzo["da_fare"] == 0


def test_pdf_senza_numero_e_incompleto_non_inventa_un_verbale():
    db = _db("senza-numero")
    _pec(db, "p1", b"copia-senza")

    esito = _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False, crea_da_pec=True))

    assert esito["pec_incomplete"] == 1 and esito["creati"] == 0
    assert _run(db["verbali_noleggio"].count_documents({})) == 1


def test_verbale_senza_originale_si_dichiara_e_non_si_ricostruisce_da_niente():
    db = _db("senza-originale")
    _verbale(db, "v1", "A24110662140")

    esito = _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False))

    assert esito["senza_originale"] == 1 and esito["con_originale"] == 0
    assert esito["veicoli_noleggio_vuota"] is True
    assert "targa" not in _riga(db, "v1")


def test_quarantena_e_righe_pec_non_si_cancellano():
    db = _db("quarantena")
    _pec(db, "p1", b"copia-A")
    _run(db["verbali_noleggio"].insert_one({"id": "q1", "numero_verbale": "X1", "stato": "quarantena"}))

    _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False, crea_da_pec=True))

    assert _run(db["verbali_noleggio"].count_documents({"id": "q1"})) == 1
    assert _run(db["verbali_noleggio"].count_documents({"id": "p1"})) == 1


def test_nessuna_scrittura_contabile():
    db = _db("contabilita")
    _verbale(db, "v1", "A24110662140")
    _pec(db, "p1", b"copia-A")

    _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False, crea_da_pec=True))

    for collezione in ("prima_nota", "prima_nota_banca", "movimenti_contabili", "pagamenti",
                       "estratto_conto_movimenti", "scritture_contabili"):
        assert _run(db[collezione].count_documents({})) == 0


# ── un solo collegamento verbale -> fattura ──────────────────────────────────────────────

def test_collegamento_legacy_si_porta_sui_campi_canonici_e_le_copie_si_tolgono():
    db = _db("collegamento")
    _verbale(db, "v1", "A24110662140", fattura_associata_id="F1", fattura_associata_numero="FT/1",
             fattura_associata_data="2025-01-01", fattura_associata_fornitore="X",
             fattura_associata_importo=10, numero_fattura="FT/1")

    anteprima = _run(mod.ricostruisci_verbali_da_pdf(db))
    assert anteprima["collegamento_da_riportare"] == 1 and "fattura_id" not in _riga(db, "v1")

    _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False))
    riga = _riga(db, "v1")
    assert riga["fattura_id"] == "F1" and riga["fattura_numero"] == "FT/1"
    assert not any(k.startswith("fattura_associata_") for k in riga)
    assert _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False))["da_fare"] == 0


def test_collegamento_divergente_non_si_tocca():
    db = _db("divergente")
    _verbale(db, "v1", "A24110662140", fattura_id="F1", fattura_associata_id="F2")

    esito = _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False))

    assert esito["collegamento_divergente"] == 1
    riga = _riga(db, "v1")
    assert riga["fattura_id"] == "F1" and riga["fattura_associata_id"] == "F2"


def test_campi_del_collegamento_sono_solo_fattura_id_numero_e_provenienza():
    campi = campi_da_fattura({"id": "F9", "invoice_number": "77/A"}, regola="numero_in_riga_fattura")
    assert set(campi) == {"fattura_id", "fattura_numero", "fattura_collegamento"}
    assert fattura_id_del_verbale({"fattura_associata_id": "F3"}) == "F3"
    assert fattura_numero_del_verbale({"numero_fattura": "1"}) == "1"
    assert fattura_id_del_verbale({"fattura_id": "A", "fattura_associata_id": "B"}) == "A"


def test_linker_scrive_un_solo_collegamento(monkeypatch):
    from app.services import verbali_fattura_linker as linker

    db = _db("linker")
    _verbale(db, "v1", "B12345678901")

    async def trovata(_db, _numero):
        return {"fattura_id": "F1", "numero_fattura": "9/B", "data_fattura": "2025-01-01",
                "fornitore": "ALD", "importo_fattura": 10}
    monkeypatch.setattr(linker, "cerca_fattura_per_verbale", trovata)

    esito = _run(linker.collega_verbali_a_fatture(db))
    riga = _riga(db, "v1")

    assert esito["collegati"] == 1
    assert riga["fattura_id"] == "F1" and riga["fattura_numero"] == "9/B"
    assert not any(k.startswith("fattura_associata_") for k in riga) and "numero_fattura" not in riga
    assert _run(linker.collega_verbali_a_fatture(db))["collegati"] == 0   # secondo giro: 0


# ── data della violazione e driver alla data ─────────────────────────────────────────────

def test_data_violazione_unica_con_alias_legacy():
    assert data_violazione_verbale({"data_violazione": "2025-03-14T10:00:00"}) == "2025-03-14"
    assert data_violazione_verbale({"data_infrazione": "2024-01-02"}) == "2024-01-02"
    assert data_violazione_verbale({"data_verbale": "2025-03-15"}) is None      # altra data
    assert data_evento_verbale({"data_verbale": "2025-03-15"}) == ("2025-03-15", "data_verbale")
    assert data_evento_verbale({"data_violazione": "2025-03-14", "data_verbale": "2025-03-15"}) == ("2025-03-14", "violazione")
    assert data_evento_verbale({}) == (None, "assente")


def test_data_infrazione_legacy_si_riporta_su_data_violazione():
    db = _db("infrazione")
    _verbale(db, "v1", "A24110662140", data_infrazione="2025-03-14")
    _verbale(db, "v2", "A24110662141", data_infrazione="2025-03-14", data_violazione="2025-03-14")
    _verbale(db, "v3", "A24110662142", data_infrazione="2025-03-01", data_violazione="2025-03-14")

    esito = _run(mod.ricostruisci_verbali_da_pdf(db, dry_run=False))

    assert _riga(db, "v1")["data_violazione"] == "2025-03-14" and "data_infrazione" not in _riga(db, "v1")
    assert "data_infrazione" not in _riga(db, "v2")
    assert "data_infrazione" in _riga(db, "v3")          # date diverse: conflitto, non si sceglie
    assert esito["conflitti"] == 1


def test_estrazione_della_data_violazione_non_prende_la_data_del_verbale():
    assert vdi._extract_violation_date("data verbale 15/03/2024") is None
    assert vdi._extract_violation_date("Data violazione: 14/03/2024 ore 10") == "2024-03-14"
    assert vdi._extract_violation_date("commessa il 14/03/2024") == "2024-03-14"
    # La dicitura degli avvisi PagoPA: «TARGA: … - DATA: 20/01/2025 VERBALE N.: …» e' il giorno del fatto.
    assert vdi._extract_violation_date("Violazione CdS - TARGA: GG782PN - DATA: 20/01/2025 VERBALE N.: A1") == "2025-01-20"


def test_driver_alla_data_e_uno_solo_lo_storico_del_veicolo():
    db = _db("driver")
    _run(db["veicoli_noleggio"].insert_one({
        "id": "car", "targa": "GG782PN", "driver_id": "oggi",
        "assegnazioni": [{"driver_id": "ieri", "driver": "A", "dal": "2024-01-01", "al": "2024-12-31"},
                         {"driver_id": "oggi", "driver": "B", "dal": "2025-01-01", "al": None}],
    }))
    ctx = _run(vdi._vehicle_context(db, "GG782PN", "2024-03-14"))
    assert ctx["driver_id"] == "ieri"
    assert _run(db["storico_assegnazioni_veicoli"].count_documents({})) == 0   # nessun secondo sistema


def test_l_importazione_conserva_l_originale_sul_verbale_senza_doppia_copia():
    from app.services.verbali_pdf_service import collect_verbale_pdfs

    db = _db("originale")
    contenuto = b"%PDF-1.4 copia-B"
    _run(db["documents_inbox"].insert_one({
        "id": "doc-1", "filename": "v.pdf", "pdf_data": base64.b64encode(contenuto).decode("ascii"),
        "file_hash": __import__("hashlib").sha256(contenuto).hexdigest()}))

    esito = _run(vdi.process_verbale_document(db, document_id="doc-1", content=contenuto, filename="v.pdf"))
    verbale = _riga(db, esito["verbale_id"])

    assert verbale["pdf_hash"] == __import__("hashlib").sha256(contenuto).hexdigest()
    assert base64.b64decode(verbale["pdf_data"]) == contenuto and verbale["pdf_size"] == len(contenuto)
    completo = _run(db["verbali_noleggio"].find_one({"id": esito["verbale_id"]}))
    pdfs = _run(collect_verbale_pdfs(db, completo))
    assert len(pdfs) == 1                      # verbale e inbox hanno la stessa impronta: una copia


# ── endpoint admin ───────────────────────────────────────────────────────────────────────

def _client(monkeypatch, db):
    from fastapi import FastAPI

    from app.database import Database
    from app.routers import verbali_noleggio as router
    from app.utils.dependencies import get_current_admin_user

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "a", "role": "admin"}
    return TestClient(app)


def _attendi(client):
    for _ in range(200):
        stato = client.get("/api/verbali-noleggio/ricostruisci-da-pdf/stato").json()
        if stato.get("stato") == "completato":
            return stato
    raise AssertionError("ricostruzione non terminata")


def test_endpoint_dry_run_per_difetto_poi_applicazione_in_sottofondo(monkeypatch):
    db = _db("endpoint")
    _verbale(db, "v1", "A24110662140")
    _pec(db, "p1", b"copia-A")
    with _client(monkeypatch, db) as client:
        prova = client.post("/api/verbali-noleggio/ricostruisci-da-pdf")
        assert prova.status_code == 200 and prova.json()["avviato"] is True and prova.json()["dry_run"] is True
        stato = _attendi(client)
        assert stato["esito"]["dry_run"] is True and stato["esito"]["da_fare"] == 1
        assert "targa" not in _riga(db, "v1")

        vero = client.post("/api/verbali-noleggio/ricostruisci-da-pdf", params={"dry_run": "false"})
        assert vero.json()["dry_run"] is False
        stato = _attendi(client)
        assert stato["esito"]["scritti"] == 1
        assert _riga(db, "v1")["targa"] == "GG782PN"


def test_endpoint_ricostruzione_e_upload_quietanza_solo_admin():
    from app.routers import verbali_noleggio as router
    from app.routers import verbali_noleggio_api as api
    from app.utils.dependencies import get_current_admin_user

    for modulo, prefissi in ((router, ("/api/verbali-noleggio/ricostruisci-da-pdf",)), (api, ("/{verbale_id}/upload-quietanza",))):
        trovate = [r for r in modulo.router.routes if r.path.startswith(prefissi[0])]
        assert trovate
        for rotta in trovate:
            assert any(d.call is get_current_admin_user for d in rotta.dependant.dependencies), rotta.path
