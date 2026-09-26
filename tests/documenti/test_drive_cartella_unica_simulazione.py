"""Simulazione della migrazione: sola lettura, lotti riprendibili, riepilogo."""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.services import drive_cartella_unica as cu
from app.services import drive_cartella_unica_simulazione as sim


def run(coro):
    return asyncio.run(coro)


class _Esegui:
    def __init__(self, valore):
        self.valore = valore

    def execute(self):
        return self.valore


class DriveAlbero:
    """Albero in memoria; qualunque scrittura fa fallire il test."""

    def __init__(self):
        self.nodi = {}

    def cartella(self, fid, nome, parent):
        self.nodi[fid] = {"id": fid, "name": nome, "mimeType": cu.CARTELLA_MIME, "parent": parent}

    def file(self, fid, nome, parent, contenuto=b"x", mime="application/pdf", md5=None):
        self.nodi[fid] = {"id": fid, "name": nome, "mimeType": mime, "parent": parent,
                          "md5Checksum": md5 or fid, "size": str(len(contenuto)),
                          "contenuto": contenuto}

    def files(self):
        return self

    def list(self, q, **_):
        parent = q.split("'")[1]
        return _Esegui({"files": [{k: v for k, v in n.items() if k not in ("parent", "contenuto")}
                                  for n in self.nodi.values() if n["parent"] == parent]})

    def update(self, **_):
        raise AssertionError("la simulazione non deve spostare file")

    def delete(self, **_):
        raise AssertionError("la simulazione non deve cancellare file")


@pytest.fixture
def albero(monkeypatch):
    drive = DriveAlbero()
    drive.cartella("a", "01_FATTURE", "radice")
    drive.cartella("b", "2026", "a")
    drive.file("f1", "fattura.xml", "b", b"<xml/>", mime="text/xml")
    drive.file("f2", "sconosciuto.pdf", "a", b"%PDF-?")
    drive.file("f3", "copia.pdf", "radice", b"%PDF-?", md5="f2")
    drive.file("g1", "Nota", "radice", mime="application/vnd.google-apps.document")
    drive.file("t1", "appunti.txt", "radice", b"x", mime="text/plain")
    drive.cartella("unica", "DA ELABORARE", "radice")
    drive.file("u1", "gia_in_coda.pdf", "unica")
    drive.cartella("foto", "FOTO E IMMAGINI", "radice")
    drive.file("img", "torta.jpg", "foto")

    monkeypatch.setenv("DRIVE_SIMULAZIONE_RADICE", "radice")
    monkeypatch.setenv("DRIVE_SIMULAZIONE_BATCH", "2")
    monkeypatch.setenv("GOOGLE_DRIVE_DATI_FOLDER_ID", "dati")
    monkeypatch.setattr(cu, "_service", lambda: drive)
    monkeypatch.setattr(cu, "_cartelle", lambda service, root: {cu.INBOX: "unica"})
    import app.services.drive_download as dd
    monkeypatch.setattr(dd, "scarica_bytes", lambda service, fid: drive.nodi[fid]["contenuto"])

    async def esamina(db, nome, contenuto):
        if nome.endswith(".xml"):
            return {"tipo": "fattura", "esito_previsto": cu.ARCHIVIO, "gia_presente": True,
                    "anno": 2024, "fuori_anno": True}
        return {"tipo": "non_riconosciuto", "esito_previsto": cu.ERRORI,
                "motivo": "tipo di documento non riconosciuto"}

    monkeypatch.setattr(sim, "esamina", esamina)
    return drive


def test_inventario_poi_lotti_riprendibili_e_riepilogo(albero):
    db = AsyncMongoMockClient()["t"]
    assert run(sim.giro(db)) == {"inventario": 5}   # DA ELABORARE e FOTO E IMMAGINI escluse
    righe = run(db[sim.REGISTRO].find({}, {"_id": 0}).to_list(None))
    assert {r["percorso"] for r in righe} == {"/01_FATTURE/2026", "/01_FATTURE", "/"}

    assert run(sim.giro(db)) == {"letti": 2, "restanti": 3}
    assert run(sim.giro(db)) == {"letti": 2, "restanti": 1}
    assert run(sim.giro(db)) == {"letti": 1, "restanti": 0}
    assert run(sim.giro(db)) == {"saltato": "simulazione_completata"}

    r = run(sim.riepilogo(db))
    assert r["file"] == 5 and r["letti"] == 5
    assert r["per_tipo"] == {"non_riconosciuto": 2, "fattura": 1, "documento_google": 1,
                             "formato_non_gestito": 1}
    assert r["gia_presenti"] == 1 and r["copie_identiche"] == 1
    assert r["fatture_fuori_anno"] == {2024: 1}
    assert {d["nome"] for d in r["da_guardare"]} == {"sconosciuto.pdf", "copia.pdf", "Nota",
                                                    "appunti.txt"}


def test_nuova_edizione_rilegge_tutto(albero, monkeypatch):
    db = AsyncMongoMockClient()["t"]
    for _ in range(5):
        run(sim.giro(db))
    monkeypatch.setenv("DRIVE_SIMULAZIONE_EDIZIONE", "2")
    assert run(sim.giro(db)) == {"inventario": 5}
    assert run(db[sim.REGISTRO].count_documents({"stato": "da_leggere"})) == 5
    assert run(db[sim.REGISTRO].count_documents({})) == 5   # nessun doppione nel registro


def test_spenta_senza_radice(monkeypatch):
    monkeypatch.delenv("DRIVE_SIMULAZIONE_RADICE", raising=False)
    assert "saltato" in run(sim.giro(AsyncMongoMockClient()["t"]))


def test_esamina_vero_non_riconosciuto_senza_scrivere():
    db = AsyncMongoMockClient()["t"]
    esito = run(sim.esamina(db, "appunti.txt", b"lista della spesa"))
    assert esito["tipo"] == "non_riconosciuto" and esito["esito_previsto"] == cu.ERRORI
    assert run(db.list_collection_names()) == []


def test_esamina_fattura_fuori_anno_resta_su_drive(monkeypatch):
    import app.services.config_import as config_import

    async def anno(db):
        return 2026

    monkeypatch.setattr(config_import, "get_anno_importazione_attivo", anno)
    xml = b"""<?xml version="1.0"?><p:FatturaElettronica xmlns:p="ns"><FatturaElettronicaHeader>
    <CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdCodice>01234567890</IdCodice></IdFiscaleIVA>
    <Anagrafica><Denominazione>FORNITORE SRL</Denominazione></Anagrafica></DatiAnagrafici></CedentePrestatore>
    </FatturaElettronicaHeader><FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento>
    <TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>2024-05-02</Data><Numero>7</Numero>
    <ImportoTotaleDocumento>12.20</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
    </FatturaElettronicaBody></p:FatturaElettronica>"""
    db = AsyncMongoMockClient()["t"]
    esito = run(sim.esamina(db, "IT01234567890_1.xml", xml))
    assert esito["tipo"] == "fattura" and esito["anno"] == 2024 and esito["fuori_anno"] is True
    assert "resta solo su Drive" in esito["motivo"] and esito["gia_presente"] is False


def test_riepilogo_riservato_all_admin():
    from app.routers.documenti import router
    from app.utils.ruoli import richiedi_admin

    rotta = next(r for r in router.routes if r.path == "/cartella-unica/simulazione")
    assert richiedi_admin in [d.call for d in rotta.dependant.dependencies]
