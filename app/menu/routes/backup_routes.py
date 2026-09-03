from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from datetime import datetime
import subprocess
import os
import json
from pathlib import Path
from typing import List

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


@router.post("/create")
async def create_backup(
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

        tar_cmd = ['tar', '-czf', str(archive_path), '-C', str(BACKUP_DIR), backup_name]
        tar_result = subprocess.run(tar_cmd, capture_output=True, text=True, timeout=60)

        if tar_result.returncode != 0:
            raise Exception(f"Archive creation failed: {tar_result.stderr}")

        subprocess.run(['rm', '-rf', str(backup_dir)])

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

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Backup timeout - database too large")
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
        file_path = BACKUP_DIR / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Backup not found")

        if not filename.endswith('.tar.gz'):
            raise HTTPException(status_code=400, detail="Invalid backup file")

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
async def public_download_backup(filename: str):
    """Download a backup file without authentication"""
    try:
        file_path = BACKUP_DIR / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Backup not found")

        if not filename.endswith('.tar.gz'):
            raise HTTPException(status_code=400, detail="Invalid backup file")

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
        file_path = BACKUP_DIR / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Backup not found")

        file_path.unlink()

        return {
            "success": True,
            "message": f"Backup '{filename}' deleted successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restore/{filename}")
async def restore_backup(filename: str, username: str = Depends(verify_token)):
    """Restore database from a JSON backup (Supabase)"""
    try:
        file_path = BACKUP_DIR / filename

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Backup not found")

        extract_dir = BACKUP_DIR / "temp_restore"
        extract_dir.mkdir(exist_ok=True)

        tar_cmd = ['tar', '-xzf', str(file_path), '-C', str(extract_dir)]
        subprocess.run(tar_cmd, check=True, timeout=60)

        backup_dirs = list(extract_dir.glob("ceraldi_backup_*"))
        if not backup_dirs:
            raise Exception("No backup directory found in archive")

        backup_dir = backup_dirs[0]

        # Ripristina in ordine inverso di dipendenza (figli prima dei genitori per il delete,
        # genitori prima dei figli per l'insert)
        delete_order = list(reversed(BACKUP_TABLES))
        insert_order = BACKUP_TABLES

        for table in delete_order:
            _delete_all_rows(table)

        for table in insert_order:
            json_path = backup_dir / f"{table}.json"
            if not json_path.exists():
                continue
            with open(json_path) as f:
                rows = json.load(f)
            if rows:
                supabase.table(table).insert(rows).execute()

        subprocess.run(['rm', '-rf', str(extract_dir)])

        return {
            "success": True,
            "message": "Database restored successfully",
            "restored_by": username
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Restore timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")
