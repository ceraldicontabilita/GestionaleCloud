"""I documenti Drive del foglio «Collegamenti» si registrano sul verbale per numero, senza doppioni."""

import asyncio
import io

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.verbali_documenti_drive import collega_documenti_drive, righe_da_xlsx

ID1 = "1AbCdEfGhIjKlMnOpQrStUv"
ID2 = "1ZyXwVuTsRqPoNmLkJiHgFe"


def _run(coro):
    return asyncio.run(coro)


def _xlsx(righe, intestazione=("numero_verbale", "drive_id", "tipo", "nome_file", "sha256")):
    cartella = Workbook()
    foglio = cartella.active
    foglio.title = "Collegamenti"
    foglio.append(list(intestazione))
    for riga in righe:
        foglio.append(list(riga))
    buffer = io.BytesIO()
    cartella.save(buffer)
    return buffer.getvalue()


def _db():
    db = ClientArchivioMemoria()["drive"]
    _run(db["verbali_noleggio"].insert_one({"id": "v1", "numero_verbale": "B22122949454", "targa": "GG782PN"}))
    return db


def test_legge_per_intestazione_anche_se_le_colonne_sono_in_altro_ordine():
    contenuto = _xlsx([(ID1, "bonifico", "B22 122 949454", "b.pdf", None)],
                      intestazione=("drive_id", "tipo", "Numero verbale", "nome file", "sha256"))
    assert righe_da_xlsx(contenuto)[0]["numero_verbale"] == "B22 122 949454"


def test_collega_per_numero_senza_spazi_e_senza_doppioni():
    db = _db()
    righe = [{"numero_verbale": "b22 122949454", "drive_id": ID1, "tipo": "bonifico", "nome_file": "b.pdf"},
             {"numero_verbale": "B22122949454", "drive_id": ID2, "tipo": "verbale", "nome_file": "v.pdf"}]
    anteprima = _run(collega_documenti_drive(db, righe, dry_run=True))
    assert anteprima["collegati"] == 2 and anteprima["dry_run"] is True
    assert "documenti_drive" not in _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    scritto = _run(collega_documenti_drive(db, righe, dry_run=False, autore="admin"))
    assert scritto["collegati"] == 2 and scritto["verbali_toccati"] == 1
    secondo = _run(collega_documenti_drive(db, righe, dry_run=False))
    assert secondo["collegati"] == 0 and secondo["gia_collegati"] == 2
    doc = _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    assert [d["drive_id"] for d in doc["documenti_drive"]] == [ID1, ID2]


def test_verbale_inesistente_e_riga_non_valida_si_elencano_e_non_si_creano():
    db = _db()
    esito = _run(collega_documenti_drive(db, [
        {"numero_verbale": "X999", "drive_id": ID1, "tipo": "verbale"},
        {"numero_verbale": "B22122949454", "drive_id": "corto", "tipo": "verbale"}], dry_run=False))
    assert esito["collegati"] == 0
    assert esito["non_trovati"] == [{"numero_verbale": "X999", "documenti": 1}]
    assert len(esito["non_validi"]) == 1
    assert _run(db["verbali_noleggio"].count_documents({})) == 1


def test_endpoint_solo_admin_e_anteprima_per_difetto(monkeypatch):
    from app.database import Database
    from app.routers import verbali_noleggio as router
    from app.utils.dependencies import get_current_admin_user

    db = _db()
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(router.router)
    contenuto = _xlsx([("B22122949454", ID1, "bonifico", "b.pdf", None)])
    files = {"file": ("c.xlsx", contenuto, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    assert TestClient(app).post("/api/verbali-noleggio/documenti-drive/collega", files=files).status_code in (401, 403)
    app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "a", "role": "admin"}
    corpo = TestClient(app).post("/api/verbali-noleggio/documenti-drive/collega", files=files).json()
    assert corpo["dry_run"] is True and corpo["collegati"] == 1
    assert "documenti_drive" not in _run(db["verbali_noleggio"].find_one({"id": "v1"}))


def test_il_foglio_corregge_tipo_e_nome_di_un_file_gia_collegato():
    db = _db()
    riga = {"numero_verbale": "B22122949454", "drive_id": ID1, "tipo": "quietanza", "nome_file": "a.pdf"}
    _run(collega_documenti_drive(db, [riga], dry_run=False))
    corretta = {**riga, "tipo": "avviso_pagopa", "nome_file": "Avviso.pdf"}
    anteprima = _run(collega_documenti_drive(db, [corretta], dry_run=True))
    assert anteprima["corretti"] == 1 and anteprima["collegati"] == 0
    assert _run(db["verbali_noleggio"].find_one({"id": "v1"}))["documenti_drive"][0]["tipo"] == "quietanza"
    scritto = _run(collega_documenti_drive(db, [corretta], dry_run=False))
    assert scritto["corretti"] == 1
    voce = _run(db["verbali_noleggio"].find_one({"id": "v1"}))["documenti_drive"][0]
    assert (voce["tipo"], voce["nome"], voce["tipo_precedente"]) == ("avviso_pagopa", "Avviso.pdf", "quietanza")
    assert _run(collega_documenti_drive(db, [corretta], dry_run=False))["corretti"] == 0


def test_azione_rimuovi_scollega_il_duplicato_e_ne_conserva_la_traccia():
    db = _db()
    righe = [{"numero_verbale": "B22122949454", "drive_id": ID1, "tipo": "ricevuta", "nome_file": "email (28).pdf"},
             {"numero_verbale": "B22122949454", "drive_id": ID2, "tipo": "presa_in_carico", "nome_file": "email (29).pdf"}]
    _run(collega_documenti_drive(db, righe, dry_run=False))
    togli = [{**righe[0], "azione": "rimuovi"}]
    assert _run(collega_documenti_drive(db, togli, dry_run=True))["rimossi"] == 1
    assert len(_run(db["verbali_noleggio"].find_one({"id": "v1"}))["documenti_drive"]) == 2
    assert _run(collega_documenti_drive(db, togli, dry_run=False, autore="admin"))["rimossi"] == 1
    doc = _run(db["verbali_noleggio"].find_one({"id": "v1"}))
    assert [d["drive_id"] for d in doc["documenti_drive"]] == [ID2]
    assert doc["documenti_drive_rimossi"][0]["drive_id"] == ID1
    assert doc["documenti_drive_rimossi"][0]["motivo_rimozione"].startswith("duplicato")
    assert _run(collega_documenti_drive(db, togli, dry_run=False))["rimossi"] == 0


def test_il_foglio_legge_la_colonna_azione():
    contenuto = _xlsx([("B22122949454", ID1, "ricevuta", "e.pdf", None, "rimuovi")],
                      intestazione=("numero_verbale", "drive_id", "tipo", "nome_file", "sha256", "azione"))
    assert righe_da_xlsx(contenuto)[0]["azione"] == "rimuovi"


def test_verbale_senza_numero_si_collega_con_il_suo_id():
    db = ClientArchivioMemoria()["drive"]
    _run(db["verbali_noleggio"].insert_one({"id": "verbale_abc123", "numero_verbale": None, "iuv": "00826230000901780"}))
    righe = [{"numero_verbale": "verbale_abc123", "drive_id": ID1, "tipo": "ricevuta", "nome_file": "r.pdf"}]
    assert _run(collega_documenti_drive(db, righe, dry_run=False))["collegati"] == 1
    assert _run(collega_documenti_drive(db, righe, dry_run=False))["collegati"] == 0
    assert _run(db["verbali_noleggio"].find_one({"id": "verbale_abc123"}))["documenti_drive"][0]["drive_id"] == ID1
