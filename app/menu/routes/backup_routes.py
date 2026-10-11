from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from anyio import from_thread
from app.database import Database
from app.services.blob_store import blob_store_per_runtime
from app.services.verified_backup_archive import salva_file, ricomponi_file, elimina_file
from starlette.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from datetime import datetime
from uuid import uuid4
from starlette.background import BackgroundTask
import json
import re
import shutil
import tarfile
from pathlib import Path

from app.menu.supabase_client import supabase

router = APIRouter(prefix="/api/backup", tags=["Database Backup"])

# Get JWT verification
from app.menu.routes.qrcode_routes import verify_token

BACKUP_DIR = Path("/tmp/backups")
BACKUP_DIR.mkdir(exist_ok=True)

# Tabelle dell'app Menu su Supabase incluse nel backup (le tabelle lotti_* non sono toccate)
BACKUP_TABLES = [
    "menu_categories",
    "menu_subcategories",
    "menu_products",
    "menu_allergens",
    "menu_qrcode_config",
    "menu_orders",
    "menu_warehouse_items",
    "menu_warehouse_movements",
    "menu_allergeni_esclusioni",
    "menu_sale",
]

# Solo archivi nati da create_backup: niente nomi arbitrari su disco.
_NOME_BACKUP = re.compile(r"^ceraldi_backup_\d{8}_\d{6}(?:_\d{6})?\.tar\.gz$")


def _file_backup(filename: str) -> Path:
    if not _NOME_BACKUP.match(filename or ""):
        raise HTTPException(status_code=400, detail="Invalid backup file")
    file_path = BACKUP_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    return file_path


def _archivia(cartella: Path, archivio: Path) -> None:
    with tarfile.open(archivio, "w:gz") as tar:
        tar.add(cartella, arcname=cartella.name)


def _leggi_archivio(archivio: Path) -> dict:
    """Legge le tabelle dall'archivio senza estrarre file su disco.

    Accetta solo `<cartella>/<tabella>.json` delle tabelle note: niente
    percorsi assoluti o `..` (tar slip) e niente tabelle estranee.
    """
    tabelle = {}
    with tarfile.open(archivio, "r:gz") as tar:
        for membro in tar.getmembers():
            if not membro.isfile():
                continue
            parti = Path(membro.name).parts
            if len(parti) != 2 or not parti[0].startswith("ceraldi_backup_"):
                continue
            tabella = Path(parti[1]).stem
            if tabella not in BACKUP_TABLES or not parti[1].endswith(".json"):
                continue
            with tar.extractfile(membro) as f:
                righe = json.load(f)
            if not isinstance(righe, list):
                raise ValueError(f"{tabella}: contenuto non valido")
            tabelle[tabella] = righe
    if not tabelle:
        raise ValueError("No backup directory found in archive")
    return tabelle



class BackupInfo:
    def __init__(self, filename: str, path: Path):
        self.filename = filename
        self.path = path
        self.size = path.stat().st_size if path.exists() else 0
        self.created_at = datetime.fromtimestamp(path.stat().st_mtime).isoformat() if path.exists() else None


# Le chiamate a Supabase e la compressione sono sincrone: con `def` FastAPI le
# esegue in un thread; con `async def` fermavano il server per tutti.
@router.post("/create")
def create_backup(
    background_tasks: BackgroundTasks,
    username: str = Depends(verify_token)
):
    """Crea un dump JSON di tutte le tabelle dell'app (Supabase)."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_name = f"ceraldi_backup_{timestamp}"
        backup_dir = BACKUP_DIR / backup_name
        backup_dir.mkdir(exist_ok=True)

        snapshot = supabase.rpc("gc_export_menu_backup", {}).execute().data
        if not isinstance(snapshot, dict) or set(snapshot) != set(BACKUP_TABLES):
            raise ValueError("Snapshot Menu incompleta")
        for table, rows in snapshot.items():
            with open(backup_dir / f"{table}.json", "w") as f:
                json.dump(rows, f, default=str)

        # Crea archivio tar.gz
        archive_name = f"{backup_name}.tar.gz"
        archive_path = BACKUP_DIR / archive_name

        try:
            _archivia(backup_dir, archive_path)
        finally:
            shutil.rmtree(backup_dir, ignore_errors=True)

        backup_info = BackupInfo(archive_name, archive_path)
        from_thread.run(_salva_persistente, archive_name, archive_path, username)

        return {
            "success": True,
            "message": "Backup created successfully",
            "backup": {
                "filename": backup_info.filename,
                "size": backup_info.size,
                "created_at": backup_info.created_at,
                "created_by": username
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}") from e


REGISTRO = "menu_backup_registro"


def _store():
    return blob_store_per_runtime(Database.get_db())


async def _salva_persistente(filename, path, username):
    manifesto = await salva_file(filename, path, {"created_by": username},
                                 store=_store(), namespace="menu")
    await Database.get_db()[REGISTRO].update_one({"id": filename},
        {"$set": {"id": filename, **manifesto}}, upsert=True)
    return manifesto


async def _file_persistente(filename):
    if not _NOME_BACKUP.fullmatch(filename or ""):
        raise HTTPException(status_code=400, detail="Invalid backup file")
    manifesto = await Database.get_db()[REGISTRO].find_one({"id": filename}, {"_id": 0})
    if manifesto:
        path = BACKUP_DIR / f"{uuid4().hex}_{filename}"
        # Rilettura verificata anche con un file locale: /tmp e' solo una cache.
        await ricomponi_file(manifesto, str(path), store=_store())
        return path
    return _file_backup(filename)  # vecchi export locali ancora scaricabili


@router.get("/list")
async def list_backups(username: str = Depends(verify_token)):
    righe = await Database.get_db()[REGISTRO].find({}, {"_id": 0}).to_list(None)
    backups = [{"filename": m["id"], "size": m["bytes"],
                "created_at": m["verificato_at"], "verificato": m["verificato"],
                "persistente": True} for m in righe]
    return {"backups": sorted(backups, key=lambda m:m["created_at"], reverse=True), "total": len(backups)}


@router.get("/download/{filename}")
async def download_backup(filename: str, username: str = Depends(verify_token)):
    path = await _file_persistente(filename)
    cleanup = BackgroundTask(path.unlink, missing_ok=True) if path.name != filename else None
    return FileResponse(str(path), filename=filename, media_type="application/gzip", background=cleanup, headers={"Cache-Control": "private, no-store"})


@router.get("/public-download/{filename}")
async def public_download_backup(filename: str, _username: str = Depends(verify_token)):
    return await download_backup(filename, username=_username)


@router.delete("/delete/{filename}")
async def delete_backup(filename: str, username: str = Depends(verify_token)):
    if not _NOME_BACKUP.fullmatch(filename or ""):
        raise HTTPException(status_code=400, detail="Invalid backup file")
    manifesto = await Database.get_db()[REGISTRO].find_one({"id": filename}, {"_id": 0})
    if manifesto:
        await elimina_file(manifesto, store=_store(), namespace="menu")
        await Database.get_db()[REGISTRO].delete_one({"id": filename})
    elif not (BACKUP_DIR / filename).exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    (BACKUP_DIR / filename).unlink(missing_ok=True)
    return {"success": True, "message": "Backup deleted"}


@router.post("/restore/{filename}")
def restore_backup(filename: str, username: str = Depends(verify_token), dry_run: bool = Query(False)):
    """Restore database from a JSON backup (Supabase).

    L'archivio si legge e si controlla tutto PRIMA di cancellare: prima le
    tabelle venivano svuotate e solo dopo si scopriva un archivio illeggibile.
    """
    file_path = from_thread.run(_file_persistente, filename) if Database.db is not None else _file_backup(filename)
    try:
        tabelle = _leggi_archivio(file_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Restore failed: {str(e)}") from e
    finally:
        if file_path.name != filename:
            file_path.unlink(missing_ok=True)

    if set(tabelle) != set(BACKUP_TABLES):
        raise HTTPException(status_code=400, detail="Backup incompleto: nessuna tabella e' stata modificata")
    try:
        # Una sola RPC SQL: ogni errore annulla tutte le tabelle. Nessun delete
        # eseguito tramite richieste HTTP indipendenti.
        result = supabase.rpc("gc_restore_menu_backup", {"p_tables": tabelle,
                              "p_dry_run": dry_run is True}).execute().data
        return {"success": True, "dry_run": dry_run is True,
                "message": "Backup verificato" if dry_run is True else "Database restored successfully",
                "restored_by": username, "result": result}
    except Exception as e:
        raise HTTPException(status_code=409, detail="Ripristino non confermato: nessuna modifica parziale") from e
