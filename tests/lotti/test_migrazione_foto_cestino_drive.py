import asyncio
import hashlib

from bson import Binary
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


def test_migrazione_foto_cestino_drive_e_riprendibile(monkeypatch):
    import app.lotti.routers.ricette as ricette
    from app.lotti.servizi import drive_foto_ricette

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(ricette, "db", database)
    legacy_id = "ricetta-legacy-1"
    contenuto = b"\x89PNG-legacy"
    run(database.foto_files.insert_one({
        "_id": legacy_id, "mime": "image/png", "data": Binary(contenuto),
        "filename": "legacy.png", "fonte": "upload_manuale",
    }))
    for indice in range(2):
        run(database.ricette_cestino.insert_one({
            "id": f"voce-{indice}",
            "ricetta": {
                "id": f"ricetta-{indice}",
                "nome": f"Ricetta {indice}",
                "foto_url": f"/api/foto/{legacy_id}?v=1",
            },
        }))
    run(database.ricette_cestino.insert_one({
        "id": "voce-senza-foto", "ricetta": {"id": "senza", "nome": "Senza"},
    }))

    async def folder_id(_db):
        return "cartella-ricette"

    def carica(*, ricetta_id, contenuto, mime, filename, folder_id, service=None):
        assert ricetta_id == "cestino-ricetta-0"
        assert folder_id == "cartella-ricette"
        return {"id": "drive-cestino-1", "sha256": hashlib.sha256(contenuto).hexdigest()}

    monkeypatch.setattr(drive_foto_ricette, "risolvi_folder_id", folder_id)
    monkeypatch.setattr(drive_foto_ricette, "carica", carica)

    anteprima = run(ricette.migra_foto_cestino_drive(False, 10, {}))
    assert anteprima == {
        "dry_run": True,
        "voci_da_migrare": 2,
        "foto_distinte_da_migrare": 1,
        "foto_legacy_mancanti": 0,
    }

    esito = run(ricette.migra_foto_cestino_drive(True, 10, {}))
    assert esito["foto_migrate"] == 1
    assert esito["voci_aggiornate"] == 2
    assert esito["voci_restanti"] == 0
    assert run(database.ricette_cestino_foto_backup_20260922.count_documents({})) == 3
    migrate = run(database.ricette_cestino.find(
        {"ricetta.foto_drive_id": "drive-cestino-1"}
    ).to_list(10))
    assert len(migrate) == 2
    assert all(v["ricetta"]["foto_drive_folder_id"] == "cartella-ricette" for v in migrate)

    secondo_giro = run(ricette.migra_foto_cestino_drive(True, 10, {}))
    assert secondo_giro["foto_migrate"] == 0
    assert secondo_giro["voci_aggiornate"] == 0


def test_worker_completa_tutti_i_lotti_senza_duplicare(monkeypatch):
    import app.lotti.routers.ricette as ricette

    esiti = iter([
        {
            "foto_migrate": 25,
            "voci_aggiornate": 50,
            "foto_legacy_mancanti": [],
            "voci_restanti": 7,
        },
        {
            "foto_migrate": 7,
            "voci_aggiornate": 12,
            "foto_legacy_mancanti": [],
            "voci_restanti": 0,
        },
    ])

    async def migra(applica, limite, admin):
        assert applica is True
        assert limite == 25
        assert admin == {}
        return next(esiti)

    monkeypatch.setattr(ricette, "migra_foto_cestino_drive", migra)

    risultato = run(ricette.completa_migrazione_foto_cestino_drive())
    assert risultato == {
        "foto_migrate": 32,
        "voci_aggiornate": 62,
        "giri": 2,
        "voci_restanti": 0,
    }


def test_worker_non_dichiara_successo_senza_avanzamento(monkeypatch):
    import app.lotti.routers.ricette as ricette

    async def fermo(applica, limite, admin):
        return {
            "foto_migrate": 0,
            "voci_aggiornate": 0,
            "foto_legacy_mancanti": [],
            "voci_restanti": 3,
        }

    monkeypatch.setattr(ricette, "migra_foto_cestino_drive", fermo)

    try:
        run(ricette.completa_migrazione_foto_cestino_drive())
    except RuntimeError as exc:
        assert "senza avanzamento" in str(exc)
    else:
        raise AssertionError("Il worker non deve dichiarare completata una migrazione ferma")
