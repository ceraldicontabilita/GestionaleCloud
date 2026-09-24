from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from datetime import datetime
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
]

# Tabelle con id intero (le altre hanno id testo)
INTEGER_ID_TABLES = {"menu_categories", "menu_subcategories", "menu_products"}


# Solo archivi nati da create_backup: niente nomi arbitrari su disco.
_NOME_BACKUP = re.compile(r"^ceraldi_backup_\d{8}_\d{6}\.tar\.gz$")


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


def _delete_all_rows(table: str):
    if table in INTEGER_ID_TABLES:
        supabase.table(table).delete().neq("id", -1).execute()
    else:
        supabase.table(table).delete().neq("id", "___none___").execute()


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
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"ceraldi_backup_{timestamp}"
        backup_dir = BACKUP_DIR / backup_name
        backup_dir.mkdir(exist_ok=True)

        for table in BACKUP_TABLES:
            rows = supabase.table(table).select("*").execute().data
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
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")


@router.get("/list")
async def list_backups(username: str = Depends(verify_token)):
    """List all available backups"""
    try:
        backups = []
        for file_path in BACKUP_DIR.glob("*.tar.gz"):
            backup_info = BackupInfo(file_path.name, file_path)
            backups.append({
                "filename": backup_info.filename,
                "size": backup_info.size,
                "created_at": backup_info.created_at
            })

        backups.sort(key=lambda x: x["created_at"], reverse=True)

        return {
            "backups": backups,
            "total": len(backups)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{filename}")
async def download_backup(filename: str, username: str = Depends(verify_token)):
    """Download a backup file"""
    try:
        file_path = _file_backup(filename)

        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type='application/gzip'
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/public-download/{filename}")
async def public_download_backup(filename: str, _username: str = Depends(verify_token)):
    """Legacy URL retained for clients, but downloads are always authenticated."""
    try:
        file_path = _file_backup(filename)

        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type='application/gzip'
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete/{filename}")
async def delete_backup(filename: str, username: str = Depends(verify_token)):
    """Delete a backup file"""
    try:
        file_path = _file_backup(filename)
        file_path.unlink()

        return {
            "success": True,
            "message": f"Backup '{filename}' deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restore/{filename}")
def restore_backup(filename: str, username: str = Depends(verify_token)):
    """Restore database from a JSON backup (Supabase).

    L'archivio si legge e si controlla tutto PRIMA di cancellare: prima le
    tabelle venivano svuotate e solo dopo si scopriva un archivio illeggibile.
    """
    file_path = _file_backup(filename)
    try:
        tabelle = _leggi_archivio(file_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Restore failed: {str(e)}")

    try:
        # Figli prima dei genitori per il delete, genitori prima dei figli per l'insert
        for table in reversed(BACKUP_TABLES):
            _delete_all_rows(table)
        for table in BACKUP_TABLES:
            rows = tabelle.get(table)
            if rows:
                supabase.table(table).insert(rows).execute()

        return {
            "success": True,
            "message": "Database restored successfully",
            "restored_by": username
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")
