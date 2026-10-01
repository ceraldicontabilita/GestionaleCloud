"""DRV-04: un endpoint solo per aprire l'originale (`/api/originale`).

Ogni sorgente ha la sua prova: payload sul record, archivio dei blob, Drive
per id, protocollo personale con SHA-256, e il caso che manca (404 con
`code`, `message`, `details`, `correlation_id`: mai un 200 vuoto). Chi non e'
autenticato non apre niente. I vecchi indirizzi sono alias che rimandano
all'endpoint canonico.
"""
import asyncio
import base64
import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import originale_documento as svc
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

PDF = b"%PDF-1.4 originale di prova"
XML = b'<?xml version="1.0" encoding="UTF-8"?><p:FatturaElettronica/>'


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _b64(dati: bytes) -> str:
    return base64.b64encode(dati).decode("ascii")


@pytest.fixture
def ambiente(monkeypatch):
    """App con il solo router `originale`, archivio in memoria, admin finto."""
    from app.database import Database
    from app.routers import originale
    from app.utils.dependencies import get_current_admin_user

    db = ClientArchivioMemoria()["originale-test"]
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(originale.router, prefix="/api/originale")
    app.dependency_overrides[get_current_admin_user] = lambda: {"role": "admin"}

    def inserisci(collezione, riga):
        _run(db[collezione].insert_one(riga))

    return app, inserisci, db


def _client(app):
    return TestClient(app)


# ── sorgenti ──────────────────────────────────────────────────────────────

def test_payload_sul_record_quietanza_f24(ambiente):
    app, inserisci, _ = ambiente
    inserisci("quietanze_f24", {"id": "q1", "file_name": "quietanza.pdf", "pdf_data": _b64(PDF)})
    with _client(app) as client:
        res = client.get("/api/originale/quietanza/q1")
    assert res.status_code == 200 and res.content == PDF
    assert res.headers["content-type"] == "application/pdf"
    assert res.headers["x-originale-fonte"] == "payload"
    assert res.headers["x-originale-sha256"] == hashlib.sha256(PDF).hexdigest()
    assert 'filename="quietanza.pdf"' in res.headers["content-disposition"]
    assert res.headers["content-disposition"].startswith("inline")


def test_f24_cerca_prima_il_modello_poi_la_quietanza(ambiente):
    app, inserisci, _ = ambiente
    inserisci("f24_unificato", {"id": "m1", "pdf_data": _b64(PDF)})
    inserisci("quietanze_f24", {"id": "q9", "pdf_data": _b64(PDF + b"-q")})
    with _client(app) as client:
        assert client.get("/api/originale/f24/m1").content == PDF
        assert client.get("/api/originale/f24/q9").content == PDF + b"-q"


def test_drive_per_id_sul_record_cedolino(ambiente, monkeypatch):
    app, inserisci, _ = ambiente
    inserisci("cedolini", {"id": "c1", "filename": "busta.pdf", "drive_file_id": "DRIVE-1", "drive_md5": "m"})
    visti = []

    async def finto(file_id, md5=None):
        visti.append((file_id, md5))
        return PDF

    import app.services.drive_download as drive_download
    monkeypatch.setattr(drive_download, "scarica_originale", finto)
    with _client(app) as client:
        res = client.get("/api/originale/cedolino/c1")
    assert res.status_code == 200 and res.content == PDF
    assert visti == [("DRIVE-1", "m")]


def test_blob_key_si_legge_dall_archivio_dei_blob(ambiente, monkeypatch):
    app, inserisci, _ = ambiente
    inserisci("cartelle_pagamento", {"id": "k1", "nome": "cartella.pdf", "blob_key": "cartella-pagamento:k1"})

    class Archivio:
        persistent = True

        async def get(self, chiave):
            return _b64(PDF) if chiave == "cartella-pagamento:k1" else None

    import app.services.cartelle_pagamento as cartelle
    monkeypatch.setattr(cartelle, "_archivio", lambda: Archivio())
    with _client(app) as client:
        res = client.get("/api/originale/cartella/k1")
    assert res.status_code == 200 and res.content == PDF


def test_documento_in_documents_inbox_e_in_documenti_non_associati(ambiente):
    app, inserisci, _ = ambiente
    inserisci("documents_inbox", {"id": "d1", "filename": "a.pdf", "pdf_data": _b64(PDF)})
    inserisci("documenti_non_associati", {"id": "d2", "filename": "b.png", "pdf_data": _b64(b"\x89PNG\r\n\x1a\nxx")})
    with _client(app) as client:
        assert client.get("/api/originale/documento/d1").content == PDF
        immagine = client.get("/api/originale/documento/d2")
    assert immagine.headers["content-type"] == "image/png"


def test_busta_firmata_p7m_restituisce_il_pdf_interno(ambiente):
    app, inserisci, _ = ambiente
    firmato = b"\x30\x82binario" + PDF + b"\n%%EOF" + b"coda-firma"
    inserisci("documenti_non_associati", {"id": "p7", "filename": "atto.pdf.p7m", "pdf_data": _b64(firmato)})
    with _client(app) as client:
        res = client.get("/api/originale/documento/p7")
    assert res.status_code == 200 and res.content.startswith(b"%PDF") and res.content.endswith(b"%%EOF")
    assert 'filename="atto.pdf"' in res.headers["content-disposition"]


def test_fattura_emessa_xml_e_scarica_come_allegato(ambiente):
    app, inserisci, _ = ambiente
    inserisci("fatture_emesse", {"id": "e1", "numero_fattura": "12/2026", "data_fattura": "2026-03-01",
                                 "xml_raw": XML.decode()})
    with _client(app) as client:
        res = client.get("/api/originale/fattura_emessa/e1?scarica=true")
    assert res.status_code == 200 and res.headers["content-type"].startswith("application/xml")
    assert res.headers["content-disposition"].startswith("attachment")
    assert "fattura_emessa_12-2026" in res.headers["content-disposition"]


def test_verbale_indice_secondo_pdf(ambiente):
    app, inserisci, _ = ambiente
    inserisci("verbali_noleggio", {"id": "v1", "numero_verbale": "A/123", "pdf_allegati": [
        {"filename": "verbale.pdf", "content_base64": _b64(PDF)},
        {"filename": "quietanza.pdf", "content_base64": _b64(PDF + b"-2")},
    ]})
    with _client(app) as client:
        assert client.get("/api/originale/verbale/A/123").content == PDF
        assert client.get("/api/originale/verbale/A/123?indice=1").content == PDF + b"-2"
        mancante = client.get("/api/originale/verbale/A/123?indice=7")
    assert mancante.status_code == 404 and mancante.json()["code"] == "ORIGINALE_NON_DISPONIBILE"


def test_estratto_atto_e_bonifico(ambiente, monkeypatch):
    app, inserisci, _ = ambiente
    inserisci("estratto_conto_nexi", {"id": "n1", "filename": "nexi.pdf", "pdf_data": _b64(PDF)})
    inserisci("bonifici_transfers", {"id": "b1", "source_file": "bonifico.pdf", "pdf_data": _b64(PDF)})
    inserisci("bonifici_transfers", {"id": "b2", "source_file": "da-posta.pdf"})
    inserisci("bonifici_email_attachments", {"id": "x", "filename": "da-posta.pdf", "pdf_data": _b64(PDF + b"-p")})
    with _client(app) as client:
        assert client.get("/api/originale/estratto/n1").content == PDF
        assert client.get("/api/originale/bonifico/b1").content == PDF
        assert client.get("/api/originale/bonifico/b2").content == PDF + b"-p"


# ── il caso che manca ─────────────────────────────────────────────────────

def test_originale_mancante_e_un_404_chiaro_mai_un_200_vuoto(ambiente):
    app, inserisci, _ = ambiente
    inserisci("quietanze_f24", {"id": "vuota", "file_name": "x.pdf"})
    inserisci("cedolini", {"id": "senza", "filename": "y.pdf"})
    with _client(app) as client:
        for tipo, ident in (("quietanza", "vuota"), ("cedolino", "senza")):
            res = client.get(f"/api/originale/{tipo}/{ident}")
            corpo = res.json()
            assert res.status_code == 404 and res.content != b""
            assert corpo["code"] == "ORIGINALE_NON_DISPONIBILE"
            assert corpo["message"].startswith("Originale non disponibile")
            assert corpo["details"]["id"] == ident and corpo["details"]["provato"]
            assert corpo["correlation_id"]


def test_documento_inesistente_tipo_non_valido_e_id_vuoto(ambiente):
    app, _, _ = ambiente
    with _client(app) as client:
        assert client.get("/api/originale/quietanza/non-esiste").json()["code"] == "DOCUMENTO_NON_TROVATO"
        non_valido = client.get("/api/originale/tipo-inventato/1")
        assert non_valido.status_code == 400 and non_valido.json()["code"] == "TIPO_ORIGINALE_NON_VALIDO"
        assert "quietanza" in non_valido.json()["details"]["ammessi"]
        assert client.get("/api/originale").status_code == 400


# ── per id Drive e per impronta ───────────────────────────────────────────

def test_drive_id_della_cartella_unica(ambiente, monkeypatch):
    app, _, _ = ambiente
    import app.services.drive_cartella_unica as cu

    async def originale(db, drive_file_id=None, sha256=None):
        return {"nome": "doc.pdf", "mime": "application/pdf", "contenuto": PDF} if drive_file_id == "OK" else None

    monkeypatch.setattr(cu, "originale", originale)
    import app.services.drive_protocollo as protocollo

    async def nessuno(_id):
        return None

    monkeypatch.setattr(protocollo, "documento", nessuno)
    with _client(app) as client:
        res = client.get("/api/originale?drive_id=OK")
        assert res.status_code == 200 and res.content == PDF and res.headers["x-originale-fonte"] == "drive"
        mancante = client.get("/api/originale?drive_id=ALTRO")
    assert mancante.status_code == 404 and mancante.json()["code"] == "ORIGINALE_NON_DISPONIBILE"
    assert "cartella_unica:ELABORATE" in mancante.json()["details"]["provato"]


def test_drive_id_noto_solo_al_protocollo_drive(ambiente, monkeypatch):
    app, _, _ = ambiente
    import app.services.drive_cartella_unica as cu
    import app.services.drive_download as dd
    import app.services.drive_protocollo as protocollo

    async def non_in_elaborate(db, drive_file_id=None, sha256=None):
        return None

    async def riga(drive_id):
        return {"document_id": drive_id, "filename": "inventario.pdf", "md5": "a" * 32, "status": "ATTIVO"} if drive_id == "INV" else None

    async def scarica(file_id, md5=None):
        return PDF if file_id == "INV" else b""

    monkeypatch.setattr(cu, "originale", non_in_elaborate)
    monkeypatch.setattr(protocollo, "documento", riga)
    monkeypatch.setattr(dd, "scarica_originale", scarica)
    with _client(app) as client:
        assert client.get("/api/originale?drive_id=INV").content == PDF
        # un id che nessun registro conosce non si scarica mai da Drive
        assert client.get("/api/originale?drive_id=QUALUNQUE").status_code == 404


def test_per_impronta_ricalcola_lo_sha256(ambiente, monkeypatch):
    app, inserisci, _ = ambiente
    import app.services.drive_cartella_unica as cu

    async def nessuno(db, drive_file_id=None, sha256=None):
        return None

    monkeypatch.setattr(cu, "originale", nessuno)
    giusto = hashlib.sha256(PDF).hexdigest()
    inserisci("documents_inbox", {"id": "d1", "filename": "a.pdf", "sha256": giusto, "pdf_data": _b64(PDF)})
    sbagliato = hashlib.sha256(b"altro").hexdigest()
    inserisci("documents_inbox", {"id": "d2", "filename": "b.pdf", "sha256": sbagliato, "pdf_data": _b64(PDF)})
    with _client(app) as client:
        assert client.get(f"/api/originale?sha256={giusto}").content == PDF
        assert client.get(f"/api/originale?sha256={sbagliato}").status_code == 404
        assert client.get("/api/originale?sha256=abc").status_code == 400


# ── protocollo personale ──────────────────────────────────────────────────

def test_protocollo_si_apre_solo_con_lo_sha256_registrato(ambiente, monkeypatch):
    app, inserisci, _ = ambiente
    import app.services.drive_download as dd

    sha = hashlib.sha256(PDF).hexdigest()
    inserisci("protocollo_personale", {"id": "2023/000123", "nome_file": "tari.pdf", "sha256": sha, "drive_file_id": "PP1"})
    inserisci("protocollo_personale", {"id": "2023/000124", "nome_file": "senza.pdf", "drive_file_id": "PP2"})
    inserisci("protocollo_personale", {"id": "2023/000125", "nome_file": "diverso.pdf", "sha256": sha, "drive_file_id": "PP3"})

    async def scarica(file_id, md5=None):
        return {"PP1": PDF, "PP2": PDF, "PP3": PDF + b"manomesso"}[file_id]

    monkeypatch.setattr(dd, "scarica_originale", scarica)
    with _client(app) as client:
        ok = client.get("/api/originale/protocollo/2023/000123")
        assert ok.status_code == 200 and ok.content == PDF and 'filename="tari.pdf"' in ok.headers["content-disposition"]
        senza = client.get("/api/originale/protocollo/2023/000124")
        assert senza.status_code == 404 and "sha256_non_registrato" in senza.json()["details"]["provato"]
        diverso = client.get("/api/originale/protocollo/2023/000125")
        assert diverso.status_code == 409 and diverso.json()["code"] == "ORIGINALE_NON_CORRISPONDENTE"
        assert client.get("/api/originale/protocollo/2023/999999").json()["code"] == "DOCUMENTO_NON_TROVATO"


def test_protocollo_senza_drive_si_apre_dal_documento_con_lo_stesso_sha256(ambiente, monkeypatch):
    app, inserisci, _ = ambiente
    import app.services.drive_cartella_unica as cu

    async def nessuno(db, drive_file_id=None, sha256=None):
        return None

    monkeypatch.setattr(cu, "originale", nessuno)
    sha = hashlib.sha256(PDF).hexdigest()
    inserisci("protocollo_personale", {"id": "2024/000007", "nome_file": "verbale.pdf", "sha256": sha})
    inserisci("documents_inbox", {"id": "d1", "filename": "interno.pdf", "sha256": sha, "pdf_data": _b64(PDF)})
    with _client(app) as client:
        res = client.get("/api/originale/protocollo/2024/000007")
    assert res.status_code == 200 and res.content == PDF
    assert 'filename="verbale.pdf"' in res.headers["content-disposition"]


# ── autenticazione e alias ────────────────────────────────────────────────

def test_senza_login_o_senza_ruolo_admin_non_si_apre_niente(ambiente):
    app, inserisci, _ = ambiente
    inserisci("quietanze_f24", {"id": "q1", "pdf_data": _b64(PDF)})
    app.dependency_overrides.clear()
    with _client(app) as client:
        assert client.get("/api/originale/quietanza/q1").status_code in (401, 403)
        assert client.get("/api/originale?drive_id=x").status_code in (401, 403)

    from app.utils.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {"role": "operatore", "user_id": "u"}
    with _client(app) as client:
        assert client.get("/api/originale/quietanza/q1").status_code == 403


def test_il_percorso_con_barre_e_l_url_canonico_coincidono():
    assert svc.url_originale("verbale", "A/123", indice=1) == "/api/originale/verbale/A%2F123?indice=1"
    assert svc.url_originale("quietanza", "q 1") == "/api/originale/quietanza/q%201"


def test_gli_alias_rimandano_all_endpoint_canonico(monkeypatch):
    from app.routers import documenti, fiscal_control
    from app.routers.f24 import f24_public, f24_riconciliazione
    from app.routers.bonifici_module import transfers

    casi = [
        (asyncio.run(f24_public.get_f24_pdf("m1")), "/api/originale/f24/m1"),
        (asyncio.run(f24_riconciliazione.get_f24_pdf("m2")), "/api/originale/f24/m2"),
        (asyncio.run(documenti.download_documento("d1")), "/api/originale/documento/d1?scarica=true"),
        (asyncio.run(fiscal_control.document_content("f1", _admin={})), "/api/originale/documento_fiscale/f1"),
        (asyncio.run(transfers.get_bonifico_pdf("b1")), "/api/originale/bonifico/b1"),
    ]
    for risposta, atteso in casi:
        assert risposta.status_code == 307 and risposta.headers["location"] == atteso


def test_gli_indirizzi_di_apertura_eliminati_non_esistono_piu():
    from app.main import app

    percorsi = {getattr(r, "path", "") for r in app.routes}
    for eliminato in ("/api/download", "/api/documenti/originale", "/api/cedolini/{cedolino_id}/pdf",
                      "/api/pagopa/ricevute/{ricevuta_id}/pdf", "/api/documenti-non-associati/pdf/{documento_id}",
                      "/api/verbali-noleggio/pdf/{numero_verbale:path}",
                      "/api/documenti/atti-giudiziari/{atto_id}/file",
                      "/api/estratto-conto-movimenti/originali/{voce_id}/file",
                      "/api/invoices/emesse/{invoice_id}/xml",
                      "/api/fatture-ricevute/fattura/{fattura_id}/xml-originale"):
        assert eliminato not in percorsi
    assert "/api/originale/{tipo}/{ident:path}" in percorsi
    # gli alias dei link gia' in circolazione restano
    for alias in ("/api/f24-public/pdf/{f24_id}", "/api/documenti/documento/{doc_id}/download",
                  "/api/fiscal/documents/{document_id}/content"):
        assert alias in percorsi
