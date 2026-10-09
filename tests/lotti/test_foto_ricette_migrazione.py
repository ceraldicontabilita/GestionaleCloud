import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import drive_foto_ricette, foto_ricette_migrazione as mig, supabase_foto_ricette

CARTELLA = "cartella-ricette"


class _Get:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _Files:
    def __init__(self, meta):
        self.meta = meta

    def get(self, fileId, **_kw):
        return _Get(self.meta[fileId])


class _Service:
    def __init__(self, meta):
        self._f = _Files(meta)
        self.chiuso = False

    def files(self):
        return self._f

    def close(self):
        self.chiuso = True


def _meta(fid, mime="image/png", parents=(CARTELLA,)):
    return {"id": fid, "name": f"{fid}.png", "mimeType": mime, "size": "4",
            "parents": list(parents), "trashed": False}


def _prepara(monkeypatch, meta):
    caricate = []
    servizio = _Service(meta)
    monkeypatch.setattr(drive_foto_ricette, "build_drive_service", lambda _c: servizio)
    monkeypatch.setattr("app.services.drive_download.scarica_bytes", lambda _s, fid, **_k: b"PNG" + fid.encode())

    def carica(*, ricetta_id, contenuto, mime, filename=None):
        caricate.append(ricetta_id)
        return {"id": f"{ricetta_id}_x", "bucket": "menu-images",
                "path": f"lotti/ricette/{ricetta_id}_x.png", "sha256": "h", "filename": filename}

    monkeypatch.setattr(supabase_foto_ricette, "carica", carica)
    return caricate, servizio


async def _db(ricette):
    db = AsyncMongoMockClient()["t"]
    await db.ricette.insert_many(ricette)
    return db


def test_migra_una_volta_sola_e_conserva_url_e_id(monkeypatch):
    caricate, servizio = _prepara(monkeypatch, {"d1": _meta("d1"), "d2": _meta("d2")})

    async def scenario():
        db = await _db([
            {"id": "r1", "foto_id": "d1", "foto_drive_id": "d1", "foto_drive_folder_id": CARTELLA,
             "foto_url": "/api/foto/d1?v=1"},
            {"id": "r2", "foto_drive_id": "d2", "foto_drive_folder_id": CARTELLA, "foto_storage_path": ""},
            {"id": "r3", "foto_storage_path": "gia/su/storage.png"},  # gia' su Storage
            {"id": "r4"},  # senza foto
        ])
        primo = await mig.migra_lotto(db, limite=10)
        secondo = await mig.migra_lotto(db, limite=10)
        r1 = await db.ricette.find_one({"id": "r1"})
        return primo, secondo, r1

    primo, secondo, r1 = asyncio.run(scenario())
    assert primo["migrate"] == 2 and primo["errori"] == 0 and primo["restano"] == 0
    assert secondo["da_migrare"] == 0 and secondo["migrate"] == 0  # idempotente
    assert caricate == ["r1", "r2"]
    assert r1["foto_storage_path"].startswith("lotti/ricette/")
    assert r1["foto_url"] == "/api/foto/d1?v=1" and r1["foto_drive_id"] == "d1"
    assert servizio.chiuso


def test_lotto_limitato_e_errori_dichiarati(monkeypatch):
    caricate, _ = _prepara(monkeypatch, {
        "d1": _meta("d1"), "d2": _meta("d2", parents=("altra",)), "d3": _meta("d3", mime="application/pdf"),
    })

    async def scenario():
        db = await _db([
            {"id": f"r{i}", "foto_drive_id": f"d{i}", "foto_drive_folder_id": CARTELLA} for i in (1, 2, 3)
        ])
        return await mig.migra_lotto(db, limite=3), await db.ricette.find_one({"id": "r2"})

    esito, r2 = asyncio.run(scenario())
    assert esito["migrate"] == 1 and esito["errori"] == 2 and esito["restano"] == 2
    assert {e["ricetta_id"] for e in esito["dettaglio_errori"]} == {"r2", "r3"}
    assert not r2.get("foto_storage_path")  # il record fallito non si tocca
    assert caricate == ["r1"]


def test_leggi_foto_su_storage_rimanda_al_cdn(monkeypatch):
    from app.lotti.routers import ricette as r

    async def scenario():
        await r.db.ricette.insert_one({"id": "rx", "foto_id": "fx", "foto_storage_path": "lotti/ricette/fx.png"})
        monkeypatch.setattr(supabase_foto_ricette, "url_pubblico", lambda p: f"https://cdn.test/{p}")
        try:
            return await r.leggi_foto("fx")
        finally:
            await r.db.ricette.delete_one({"id": "rx"})

    risposta = asyncio.run(scenario())
    assert risposta.status_code == 302
    assert risposta.headers["location"] == "https://cdn.test/lotti/ricette/fx.png"
    assert "immutable" in risposta.headers["cache-control"]
