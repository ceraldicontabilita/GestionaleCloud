"""Censimento doppioni: elenca, rinomina soltanto, mai cancella o sposta."""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.services import drive_cartella_unica as cu
from app.services import drive_censimento_doppioni as cen


def run(coro):
    return asyncio.run(coro)


class _Esegui:
    def __init__(self, valore):
        self.valore = valore

    def execute(self):
        return self.valore


class Drive:
    """Albero in memoria: rinominare e' l'unica scrittura permessa."""

    def __init__(self):
        self.nodi = {}
        self.rinomine = []

    def cartella(self, fid, nome, parent):
        self.nodi[fid] = {"id": fid, "name": nome, "mimeType": cu.CARTELLA_MIME, "parent": parent}

    def file(self, fid, nome, parent, md5, size=10, creato="2026-01-01T00:00:00Z", mime="application/pdf"):
        self.nodi[fid] = {"id": fid, "name": nome, "mimeType": mime, "parent": parent,
                          "md5Checksum": md5, "size": str(size), "createdTime": creato}

    def files(self):
        return self

    def list(self, q, **_):
        parent = q.split("'")[1]
        return _Esegui({"files": [{k: v for k, v in n.items() if k != "parent"}
                                  for n in self.nodi.values() if n["parent"] == parent]})

    def get(self, fileId, **_):
        n = self.nodi[fileId]
        return _Esegui({"id": fileId, "name": n["name"], "md5Checksum": n.get("md5Checksum"),
                        "size": n.get("size"), "trashed": False})

    def update(self, fileId, body=None, **kw):
        if set(body or {}) != {"name"} or kw.get("addParents") or kw.get("removeParents"):
            raise AssertionError("il censimento puo' solo rinominare")
        self.nodi[fileId]["name"] = body["name"]
        self.rinomine.append((fileId, body["name"]))
        return _Esegui({"id": fileId, "name": body["name"]})

    def delete(self, **_):
        raise AssertionError("il censimento non cancella")


@pytest.fixture
def drive(monkeypatch):
    d = Drive()
    d.cartella("dati", "DATI SOCIETA CERALDI", "radice")
    d.cartella("el", "ELABORATE", "dati")
    d.cartella("foto", "FOTO E IMMAGINI", "radice")
    d.file("orig", "fattura.pdf", "el", "m1", creato="2026-03-01T00:00:00Z")
    d.file("copia1", "fattura (2).pdf", "dati", "m1", creato="2026-01-01T00:00:00Z")
    d.file("copia2", "altro nome.pdf", "radice", "m1")
    d.file("unico", "cedolino.pdf", "dati", "m2")
    d.file("stesso_nome", "fattura.pdf", "dati", "m3")          # stesso nome, contenuto diverso
    d.file("ini", "desktop.ini", "foto", "m4")
    d.file("vuoto", "nota.txt", "dati", "m5", size=0)
    d.file("gdoc", "Appunti", "dati", None, mime="application/vnd.google-apps.document")
    monkeypatch.setenv("DRIVE_SIMULAZIONE_RADICE", "radice")
    monkeypatch.setattr(cu, "_service", lambda: d)
    return d


def _righe(db):
    return {r["file_id"]: r for r in run(db[cen.REGISTRO].find({}, {"_id": 0}).to_list(None))}


def test_censisci_elenca_senza_toccare_drive(drive, monkeypatch):
    monkeypatch.setenv("DRIVE_CENSIMENTO_DOPPIONI", "censisci")
    db = AsyncMongoMockClient()["t"]
    esito = run(cen.giro(db))
    assert esito["censiti"] == 8 and esito["duplicato"] == 2 and esito["tecnico"] == 2
    righe = _righe(db)
    # Resta quello gia' archiviato in ELABORATE, anche se piu' recente.
    assert righe["orig"]["ruolo"] == "originale" and righe["orig"]["copie"] == 2
    assert righe["copia1"]["originale_id"] == "orig" and righe["copia2"]["ruolo"] == "duplicato"
    assert righe["stesso_nome"]["ruolo"] == "unico"            # il nome non basta
    assert righe["gdoc"]["ruolo"] == "unico"
    assert righe["ini"]["ruolo"] == "tecnico" and righe["vuoto"]["ruolo"] == "tecnico"
    assert run(cen.giro(db)) == {"saltato": "fase censito, modalita censisci"}
    assert drive.rinomine == []


def test_marca_rinomina_solo_copie_e_tecnici_una_volta(drive, monkeypatch):
    monkeypatch.setenv("DRIVE_CENSIMENTO_DOPPIONI", "marca")
    db = AsyncMongoMockClient()["t"]
    run(cen.giro(db))                                           # censimento
    assert run(cen.giro(db))["marcati"] == 4
    nomi = {fid: n["name"] for fid, n in drive.nodi.items()}
    assert nomi["copia1"] == "DUPLICATO DA ELIMINARE - fattura (2).pdf"
    assert nomi["copia2"] == "DUPLICATO DA ELIMINARE - altro nome.pdf"
    assert nomi["ini"] == "FILE TECNICO DA ELIMINARE - desktop.ini"
    assert nomi["orig"] == "fattura.pdf" and nomi["unico"] == "cedolino.pdf"
    assert run(cen.giro(db)) == {"marcati": 0, "errori": 0, "lotto": 0}
    assert len(drive.rinomine) == 4
    stato = run(db["sistema_stato"].find_one({"chiave": cen.CHIAVE_STATO}, {"_id": 0}))
    assert stato["fase"] == "completato" and stato["marcati"] == 4


def test_copia_cambiata_dopo_il_censimento_non_si_rinomina(drive, monkeypatch):
    monkeypatch.setenv("DRIVE_CENSIMENTO_DOPPIONI", "marca")
    db = AsyncMongoMockClient()["t"]
    run(cen.giro(db))
    drive.nodi["copia1"]["md5Checksum"] = "cambiato"
    run(cen.giro(db))
    assert drive.nodi["copia1"]["name"] == "fattura (2).pdf"
    assert _righe(db)["copia1"]["marcatura"]["esito"] == "saltato"


def test_spento_non_fa_nulla(drive, monkeypatch):
    monkeypatch.delenv("DRIVE_CENSIMENTO_DOPPIONI", raising=False)
    assert "saltato" in run(cen.giro(AsyncMongoMockClient()["t"]))


def test_lo_smistatore_non_prende_i_file_marcati():
    class Lista:
        def __init__(self):
            self.q = None

        def files(self):
            return self

        def list(self, q, **_):
            self.q = q
            return _Esegui({"files": []})

    lista = Lista()
    cu._elenca(lista, "cartella", "id", 10, True)
    assert "not name contains 'DUPLICATO DA ELIMINARE -'" in lista.q
    assert "not name contains 'FILE TECNICO DA ELIMINARE -'" in lista.q


def test_elenco_riservato_all_admin():
    from app.routers.documenti import router
    from app.utils.ruoli import richiedi_admin

    for percorso in ("/drive-doppioni", "/drive-doppioni.csv"):
        rotta = next(r for r in router.routes if r.path == percorso)
        assert richiedi_admin in [d.call for d in rotta.dependant.dependencies]
