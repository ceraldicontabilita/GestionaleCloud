"""Ricostruzione delle fatture dal registro della cartella unica: solo `fattura` in ELABORATE, riprendibile."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services import fatture_da_registro as fr


def _run(c):
    return asyncio.run(c)


def _db():
    db = AsyncMongoMockClient()["t"]
    righe = [
        {"id": "a", "drive_file_id": "A", "nome": "IT1_a.xml", "cartella": "ELABORATE", "tipo": "fattura"},
        {"id": "b", "drive_file_id": "B", "nome": "IT2_b.xml", "cartella": "ELABORATE", "tipo": "fattura"},
        {"id": "c", "drive_file_id": "C", "nome": "cedolino.pdf", "cartella": "ELABORATE", "tipo": "cedolino"},
        {"id": "d", "drive_file_id": "D", "nome": "IT3_d.xml", "cartella": "ERRORI", "tipo": "fattura"},
    ]
    for r in righe:
        _run(db[fr.REGISTRO].insert_one(dict(r)))
    return db


def test_legge_solo_le_fatture_in_elaborate():
    db = _db()
    assert _run(fr.anteprima(db)) == {"dry_run": True, "file": 2, "xml": 2}


def test_giro_importa_poi_il_secondo_giro_non_rifa_niente(monkeypatch):
    db = _db()
    visti = []

    async def scarica(drive_id, md5=None):
        return b"<xml/>"

    async def smista(nome, dati, contesto, tipo=None):
        visti.append(nome)
        return {"success": True}

    monkeypatch.setattr("app.services.drive_download.scarica_originale", scarica)
    monkeypatch.setattr("app.services.drive_cartella_unica._smista", smista)
    esito = _run(fr.giro(db))
    assert esito["completato"] and esito["contatori"]["importati"] == 2
    assert visti == ["IT1_a.xml", "IT2_b.xml"]
    assert _run(fr.giro(db)) == {"saltato": "gia' completato"}
    assert len(visti) == 2


def test_un_file_guasto_non_ferma_gli_altri(monkeypatch):
    db = _db()

    async def scarica(drive_id, md5=None):
        if drive_id == "A":
            raise OSError("drive giu")
        return b"<xml/>"

    async def smista(nome, dati, contesto, tipo=None):
        return {"success": True}

    monkeypatch.setattr("app.services.drive_download.scarica_originale", scarica)
    monkeypatch.setattr("app.services.drive_cartella_unica._smista", smista)
    esito = _run(fr.giro(db))
    assert esito["contatori"]["errori"] == 1 and esito["contatori"]["importati"] == 1


def test_spento_non_fa_niente(monkeypatch):
    monkeypatch.delenv("RICOSTRUZIONE_FATTURE_DA_REGISTRO", raising=False)
    assert "saltato" in _run(fr.giro_schedulato(_db()))
