"""
backup.py — Backup e restore del database haccp_ceraldi.

Backup:
  - mongodump compresso in /app/backups/db/
  - Nome file: haccp_ceraldi_YYYY-MM-DD_HHMM.gz
  - Rotazione: mantiene gli ultimi 7 backup
  - Ogni notte alle 02:30 (scheduler)

Restore:
  - Seleziona un backup dalla lista
  - Prima del restore crea automaticamente un backup di sicurezza
  - mongorestore --drop (atomico: svuota e reimporta)

Endpoint:
  POST /api/backup/esegui          — backup immediato
  GET  /api/backup/lista           — lista backup disponibili
  GET  /api/backup/stato           — stato ultimo backup
  POST /api/backup/ripristina/{f}  — restore da file specificato
"""

from fastapi import APIRouter, HTTPException
from app.routers.tracciabilita.server import db
from fastapi.responses import FileResponse
from datetime import datetime, timezone
import subprocess
import os
import glob
import logging
import re

router = APIRouter(prefix="/backup", tags=["Backup"])

BACKUP_DIR  = "/app/backups/db"
MAX_BACKUPS = 7
LOG         = logging.getLogger("backup")
DB_NAME     = os.environ.get('DB_NAME', 'azienda_erp_db')


def _esegui_backup_sync() -> dict:
    """Esegue mongodump sincrono e ritorna il risultato."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    data_oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ora_str   = datetime.now(timezone.utc).strftime("%H%M")
    filename  = f"{DB_NAME}_{data_oggi}_{ora_str}.gz"
    filepath  = os.path.join(BACKUP_DIR, filename)

    cmd = [
        "mongodump",
        f"--uri={MONGO_URL}",
        f"--db={DB_NAME}",
        "--gzip",
        f"--archive={filepath}",
    ]

    start  = datetime.now(timezone.utc)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()

    if result.returncode != 0:
        raise RuntimeError(f"mongodump fallito: {result.stderr.strip()}")

    size_mb = round(os.path.getsize(filepath) / 1024 / 1024, 2)

    # Rotazione: elimina backup più vecchi se superiamo MAX_BACKUPS
    tutti = sorted(glob.glob(os.path.join(BACKUP_DIR, f"{DB_NAME}_*.gz")))
    eliminati = []
    while len(tutti) > MAX_BACKUPS:
        vecchio = tutti.pop(0)
        os.remove(vecchio)
        eliminati.append(os.path.basename(vecchio))

    LOG.info(f"[BACKUP] {filename} — {size_mb} MB — {elapsed:.1f}s")

    return {
        "success":    True,
        "file":       filename,
        "percorso":   filepath,
        "dimensione": f"{size_mb} MB",
        "durata_s":   round(elapsed, 1),
        "eliminati":  eliminati,
        "timestamp":  start.isoformat(),
    }


async def esegui_backup_async() -> dict:
    """Wrapper asincrono per lo scheduler."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _esegui_backup_sync)


# ── POST /api/backup/esegui ───────────────────────────────────────────────────
@router.post("/esegui")
async def backup_manuale():
    """Esegue un backup immediato del database."""
    try:
        return await esegui_backup_async()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /api/backup/lista ─────────────────────────────────────────────────────
@router.get("/lista")
async def lista_backup():
    """Elenca tutti i backup disponibili con dimensione e data."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, f"{DB_NAME}_*.gz")), reverse=True)
    result = []
    for f in files:
        stat = os.stat(f)
        result.append({
            "file":       os.path.basename(f),
            "dimensione": f"{round(stat.st_size / 1024 / 1024, 2)} MB",
            "data":       datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "size_bytes": stat.st_size,
        })
    return {
        "totale":   len(result),
        "max_keep": MAX_BACKUPS,
        "backup":   result,
    }


# ── GET /api/backup/stato ─────────────────────────────────────────────────────
@router.get("/stato")
async def stato_backup():
    """Ritorna lo stato dell'ultimo backup."""
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, f"{DB_NAME}_*.gz")), reverse=True)
    if not files:
        return {"ultimo_backup": None, "stato": "nessun_backup"}
    ultimo = files[0]
    stat   = os.stat(ultimo)
    return {
        "stato":         "ok",
        "ultimo_backup": os.path.basename(ultimo),
        "dimensione":    f"{round(stat.st_size / 1024 / 1024, 2)} MB",
        "data":          datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "totale_backup": len(files),
    }


# ── POST /api/backup/ripristina/{filename} ────────────────────────────────────
@router.post("/ripristina/{filename}")
async def ripristina_backup(filename: str):
    """
    Ripristina il database da un backup specifico.
    Flusso atomico:
      1. Valida il nome file
      2. Crea backup di sicurezza del DB attuale
      3. mongorestore --drop (sovrascrive tutto)
      4. Ritorna esito dettagliato
    """
    # Validazione: solo nomi file sicuri
    if not re.match(r'^haccp_ceraldi_[\d_-]+\.gz$', filename):
        raise HTTPException(status_code=400, detail="Nome file non valido")

    filepath = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Backup non trovato: {filename}")

    # 1. Backup di sicurezza PRIMA del restore
    try:
        backup_sicurezza = _esegui_backup_sync()
        LOG.info(f"[RESTORE] Backup pre-restore: {backup_sicurezza['file']}")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Impossibile creare backup di sicurezza: {e}"
        )

    # 2. mongorestore atomico
    cmd = [
        "mongorestore",
        f"--uri={MONGO_URL}",
        f"--db={DB_NAME}",
        "--gzip",
        f"--archive={filepath}",
        "--drop",
        "--numParallelCollections=4",
    ]

    start = datetime.now(timezone.utc)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Timeout durante il restore (>10 min)")

    elapsed = round((datetime.now(timezone.utc) - start).total_seconds(), 1)

    if result.returncode != 0:
        LOG.error(f"[RESTORE] Fallito: {result.stderr}")
        raise HTTPException(
            status_code=500,
            detail=f"Restore fallito: {result.stderr.strip()[:500]}"
        )

    LOG.info(f"[RESTORE] Completato: {filename} in {elapsed}s")

    return {
        "success":             True,
        "backup_ripristinato": filename,
        "backup_sicurezza":    backup_sicurezza["file"],
        "durata_s":            elapsed,
        "messaggio": (
            f"Database ripristinato con successo da {filename}. "
            f"Backup di sicurezza salvato: {backup_sicurezza['file']}"
        ),
    }


# ── GET /api/backup/download/{filename} ──────────────────────────────────────
@router.get("/download/{filename}")
async def download_backup(filename: str):
    """Scarica un file di backup specifico come download diretto."""
    if not re.match(r'^haccp_ceraldi_[\d_-]+\.gz$', filename):
        raise HTTPException(status_code=400, detail="Nome file non valido")
    filepath = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Backup non trovato: {filename}")
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
