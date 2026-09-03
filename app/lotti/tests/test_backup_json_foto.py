import gzip
import asyncio

from bson import json_util
from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers import backup


def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


def test_export_json_include_foto_binaria_e_id(monkeypatch):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    run(database.foto_files.insert_one({
        "_id": "ricetta-1", "ricetta_id": "ricetta-1",
        "mime": "image/jpeg", "data": b"\x00foto-reale\xff",
    }))
    monkeypatch.setattr(backup, "_db", database)
    risposta = run(backup.export_json_backup(_admin={"ruolo": "admin"}))
    async def leggi():
        parti = []
        async for parte in risposta.body_iterator:
            parti.append(parte.encode() if isinstance(parte, str) else parte)
        return parti
    parti = run(leggi())
    dump = json_util.loads(b"".join(parti).decode("utf-8"))
    assert dump["_meta"]["version"] == "3.0"
    assert dump["foto_files"][0]["_id"] == "ricetta-1"
    assert dump["foto_files"][0]["data"] == b"\x00foto-reale\xff"


def test_backup_gzip_conserva_foto_ripristinabile(monkeypatch, tmp_path):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    run(database.foto_files.insert_one({"_id": "foto-x", "data": b"abc"}))
    monkeypatch.setattr(backup, "_db", database)
    monkeypatch.setattr(backup, "BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr(backup, "DB_NAME", "Gestionale")
    esito = run(backup.esegui_backup_async())
    with gzip.open(tmp_path / esito["file"], "rt", encoding="utf-8") as fh:
        dump = json_util.loads(fh.read())
    assert dump["foto_files"][0]["_id"] == "foto-x"
    assert dump["foto_files"][0]["data"] == b"abc"
