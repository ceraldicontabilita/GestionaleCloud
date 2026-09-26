import gzip
import asyncio

from bson import json_util
from mongomock_motor import AsyncMongoMockClient

import pytest
from fastapi import HTTPException

from app.lotti.routers import backup
from app.lotti.servizi import backup_archivio
from app.services.blob_store import MemoryBlobStore


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


class _ArchivioProva(MemoryBlobStore):
    persistent = True


def _prepara(monkeypatch, tmp_path):
    database = AsyncMongoMockClient()["Gestionale_Test"]
    archivio = _ArchivioProva()
    monkeypatch.setattr(backup, "_db", database)
    monkeypatch.setattr(backup, "APPOGGIO_DIR", str(tmp_path))
    monkeypatch.setattr(backup, "DB_NAME", "Gestionale")
    monkeypatch.setattr(backup_archivio, "archivio", lambda: archivio)
    monkeypatch.setattr(backup_archivio, "PARTE_BYTES", 64)  # più parti anche su un file piccolo
    return database, archivio


def _leggi_backup(nome, tmp_path, database):
    manifesto = run(database[backup.REGISTRO].find_one({"id": nome}, {"_id": 0}))
    destinazione = str(tmp_path / ("letto_" + nome))
    run(backup_archivio.ricomponi(manifesto, destinazione))
    with gzip.open(destinazione, "rt", encoding="utf-8") as fh:
        return json_util.loads(fh.read())


def test_backup_gzip_conserva_foto_ripristinabile(monkeypatch, tmp_path):
    database, archivio = _prepara(monkeypatch, tmp_path)
    run(database.foto_files.insert_one({"_id": "foto-x", "data": b"abc"}))
    esito = run(backup.esegui_backup_async())
    assert esito["success"] and esito["verificato"] and esito["parti"] > 1
    # Il file di appoggio non resta sul disco: il backup vive nell'archivio.
    assert not (tmp_path / esito["file"]).exists()
    dump = _leggi_backup(esito["file"], tmp_path, database)
    assert dump["foto_files"][0]["_id"] == "foto-x"
    assert dump["foto_files"][0]["data"] == b"abc"
    assert backup.REGISTRO not in dump


def test_backup_rifiutato_se_archivio_non_persistente(monkeypatch, tmp_path):
    database, _ = _prepara(monkeypatch, tmp_path)
    monkeypatch.setattr(backup_archivio, "archivio", lambda: MemoryBlobStore())
    run(database.lotti.insert_one({"_id": "l1"}))
    with pytest.raises(backup_archivio.BackupNonPersistente):
        run(backup.esegui_backup_async())
    assert run(database[backup.REGISTRO].count_documents({})) == 0


def test_parte_alterata_non_si_ripristina(monkeypatch, tmp_path):
    database, archivio = _prepara(monkeypatch, tmp_path)
    run(database.lotti.insert_one({"_id": "l1", "nome": "x" * 300}))
    esito = run(backup.esegui_backup_async())
    manifesto = run(database[backup.REGISTRO].find_one({"id": esito["file"]}, {"_id": 0}))
    archivio._data[manifesto["parti"][0]["chiave"]] = "QUxURVJBVE8="
    with pytest.raises(backup_archivio.BackupNonPersistente):
        run(backup_archivio.ricomponi(manifesto, str(tmp_path / "x.gz")))


def test_ripristino_simula_poi_sostituisce_per_id(monkeypatch, tmp_path):
    database, _ = _prepara(monkeypatch, tmp_path)
    run(database.lotti.insert_many([{"_id": "a", "v": 1}, {"_id": "b", "v": 1}]))
    esito = run(backup.esegui_backup_async())
    nome = esito["file"]
    # Dopo il backup: "a" cambia, "b" sparisce, "c" nasce.
    run(database.lotti.update_one({"_id": "a"}, {"$set": {"v": 2}}))
    run(database.lotti.delete_one({"_id": "b"}))
    run(database.lotti.insert_one({"_id": "c", "v": 9}))

    simulazione = run(backup.ripristina_backup(nome, dry_run=True, conferma=None, _admin={}))
    assert simulazione["dry_run"] is True
    assert simulazione["collezioni"]["lotti"] == {
        "attuali": 2, "nel_backup": 2, "da_togliere": 1, "da_aggiungere": 1}
    assert run(database.lotti.find_one({"_id": "a"}))["v"] == 2  # nulla scritto

    with pytest.raises(HTTPException) as senza_conferma:
        run(backup.ripristina_backup(nome, dry_run=False, conferma="altro", _admin={}))
    assert senza_conferma.value.status_code == 400

    fatto = run(backup.ripristina_backup(nome, dry_run=False, conferma=nome, _admin={}))
    assert fatto["success"] is True
    docs = {d["_id"]: d["v"] for d in run(database.lotti.find({}).to_list(None))}
    assert docs == {"a": 1, "b": 1}
    # Il backup di sicurezza esiste, è verificato ed è un altro file.
    assert fatto["backup_sicurezza"] != nome
    sicurezza = run(database[backup.REGISTRO].find_one({"id": fatto["backup_sicurezza"]}))
    assert sicurezza["verificato"] is True
    # Il registro dei backup non è stato toccato dal ripristino.
    assert run(database[backup.REGISTRO].count_documents({})) == 2


def test_ripristino_annullato_se_backup_di_sicurezza_fallisce(monkeypatch, tmp_path):
    database, _ = _prepara(monkeypatch, tmp_path)
    run(database.lotti.insert_one({"_id": "a", "v": 1}))
    nome = run(backup.esegui_backup_async())["file"]
    run(database.lotti.update_one({"_id": "a"}, {"$set": {"v": 2}}))

    async def rotto():
        raise RuntimeError("archivio giù")
    monkeypatch.setattr(backup, "esegui_backup_async", rotto)
    with pytest.raises(HTTPException) as err:
        run(backup.ripristina_backup(nome, dry_run=False, conferma=nome, _admin={}))
    assert err.value.status_code == 500
    assert run(database.lotti.find_one({"_id": "a"}))["v"] == 2


def test_nome_file_reale_accettato():
    assert backup._nome_valido("Gestionale_2026-09-26_023000.json.gz")
    assert backup._nome_valido("Gestionale_2026-09-26_0230.json.gz")
    assert not backup._nome_valido("../Gestionale_2026-09-26_0230.json.gz")


def test_rotazione_tiene_gli_ultimi(monkeypatch, tmp_path):
    database, archivio = _prepara(monkeypatch, tmp_path)
    monkeypatch.setattr(backup, "MAX_BACKUPS", 2)
    run(database.lotti.insert_one({"_id": "a"}))
    for i in range(3):
        run(database[backup.REGISTRO].insert_one({
            "id": f"Gestionale_2026-01-0{i + 1}_0230.json.gz", "nome": f"Gestionale_2026-01-0{i + 1}_0230.json.gz",
            "creato_at": f"2026-01-0{i + 1}T02:30:00+00:00", "parti": [], "verificato": True}))
    esito = run(backup.esegui_backup_async())
    assert sorted(esito["eliminati"]) == ["Gestionale_2026-01-01_0230.json.gz", "Gestionale_2026-01-02_0230.json.gz"]
    assert run(database[backup.REGISTRO].count_documents({})) == 2
