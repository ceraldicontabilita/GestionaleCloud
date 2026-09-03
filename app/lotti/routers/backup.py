"""
backup.py — Backup e restore del database Gestionale.

Backup:
  - dump gzip-JSON pure-Python di tutte le collezioni in BACKUP_DIR (/tmp su Render)
  - Nome file: Gestionale_YYYY-MM-DD_HHMM.gz
  - Rotazione: mantiene gli ultimi 7 backup
  - Ogni notte alle 02:30 (scheduler)

Restore:
  - Seleziona un backup dalla lista
  - Prima del restore crea automaticamente un backup di sicurezza
  - restore pure-Python: per ogni collezione drop + reinsert

Endpoint:
  POST /api/backup/esegui          — backup immediato
  GET  /api/backup/lista           — lista backup disponibili
  GET  /api/backup/stato           — stato ultimo backup
  POST /api/backup/ripristina/{f}  — restore da file specificato
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse, StreamingResponse
from bson import json_util
from datetime import datetime, timezone
import os, glob, logging, re, json, gzip
from app.lotti.db import database as _db, DB_NAME
from app.lotti.auth import require_admin

router = APIRouter(prefix="/backup", tags=["Backup"])
# Su Render il filesystem è di sola lettura tranne /tmp: il default /var/backups
# dava "Permission denied". Si usa /tmp (sovrascrivibile con env BACKUP_DIR).
BACKUP_DIR = os.environ.get("BACKUP_DIR", "/tmp/backups/ceraldi/db")
MAX_BACKUPS = 7
LOG = logging.getLogger("backup")

@router.get("/export-json")
async def export_json_backup(_admin=Depends(require_admin)):
    """
    Scarica un dump JSON del database.
    Restituisce un file .json con tutte le collezioni principali.
    """
    collezioni = sorted(
        c for c in await _db.list_collection_names() if not c.startswith("system.")
    )
    meta = {
        "db": DB_NAME,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "version": "3.0",
        "formato": "MongoDB Extended JSON",
        "collezioni": collezioni,
    }
    filename = f"backup_{DB_NAME}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.json"

    async def genera():
        # Extended JSON conserva ObjectId, date e foto binarie. Lo streaming
        # evita di caricare l'intero database nella memoria del servizio.
        yield ('{"_meta":' + json.dumps(meta, ensure_ascii=False)).encode("utf-8")
        for coll_name in collezioni:
            yield ("," + json.dumps(coll_name) + ":[").encode("utf-8")
            primo = True
            async for doc in _db[coll_name].find({}).batch_size(250):
                if not primo:
                    yield b","
                primo = False
                yield json_util.dumps(doc, ensure_ascii=False).encode("utf-8")
            yield b"]"
        yield b"}"

    return StreamingResponse(
        genera(),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def esegui_backup_async() -> dict:
    """Backup pure-Python in STREAMING: scrive il dump gzip-JSON di TUTTE le
    collezioni direttamente sul file, una collezione alla volta e un documento
    alla volta. Memoria di picco = un documento (NON l'intero DB), per non
    saturare i 512MB di Render. Niente mongodump. Rotazione MAX_BACKUPS.

    Formato: oggetto JSON {"_meta": {...}, "<collezione>": [doc, ...], ...}
    identico a prima, così il restore via json.loads resta compatibile."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    start = datetime.now(timezone.utc)
    filename = f"{DB_NAME}_{start.strftime('%Y-%m-%d_%H%M')}.json.gz"
    filepath = os.path.join(BACKUP_DIR, filename)

    try:
        collezioni = sorted(
            c for c in await _db.list_collection_names() if not c.startswith("system.")
        )
    except Exception as e:
        raise RuntimeError(f"Impossibile elencare le collezioni: {e}")

    meta = {
        "db": DB_NAME,
        "exported_at": start.isoformat(),
        "version": "2.1",
        "tipo": "json-gzip-stream",
        "collezioni": collezioni,
    }

    totale_doc = 0
    # Scrittura streaming AMMORTIZZATA (fix 02/07/2026): la memoria era già a
    # posto (un documento alla volta), ma json.dumps+gzip giravano DENTRO
    # l'event loop: su ~119k documenti la CPU del free tier restava occupata
    # ~45s di fila e TUTTE le API rispondevano 502 (verificato live l'1/07).
    # Ora: i documenti si accumulano in blocchi da 500, la serializzazione+
    # compressione del blocco gira in un THREAD (asyncio.to_thread) e tra un
    # blocco e l'altro l'event loop respira (sleep breve) — le API restano
    # reattive per tutta la durata del backup.
    import asyncio as _aio

    def _scrivi_blocco(fh, items):
        # serializzazione + compressione nel thread: l'event loop non le vede
        fh.write("".join(
            pref + json_util.dumps(d, ensure_ascii=False) for pref, d in items
        ))

    with gzip.open(filepath, "wt", encoding="utf-8") as fh:
        fh.write("{")
        fh.write('"_meta":')
        fh.write(json.dumps(meta, ensure_ascii=False, default=str))
        for coll_name in collezioni:
            fh.write(",")
            fh.write(json.dumps(coll_name))
            fh.write(":[")
            primo = True
            try:
                cursor = _db[coll_name].find({}).batch_size(500)
                blocco = []
                async for doc in cursor:
                    blocco.append(("" if primo else ",", doc))
                    primo = False
                    totale_doc += 1
                    if len(blocco) >= 500:
                        await _aio.to_thread(_scrivi_blocco, fh, blocco)
                        blocco = []
                        await _aio.sleep(0.05)  # aria alle altre richieste
                if blocco:
                    await _aio.to_thread(_scrivi_blocco, fh, blocco)
            except Exception as e:
                LOG.warning(f"[BACKUP] collezione {coll_name} parziale: {e}")
            fh.write("]")
        fh.write("}")

    size_mb = round(os.path.getsize(filepath) / 1024 / 1024, 2)
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()

    # Rotazione: tiene solo gli ultimi MAX_BACKUPS
    tutti = sorted(glob.glob(os.path.join(BACKUP_DIR, f"{DB_NAME}_*.gz")))
    eliminati = []
    while len(tutti) > MAX_BACKUPS:
        vecchio = tutti.pop(0)
        try:
            os.remove(vecchio)
            eliminati.append(os.path.basename(vecchio))
        except OSError:
            pass

    LOG.info(f"[BACKUP] {filename} - {size_mb} MB - {totale_doc} doc - {elapsed:.1f}s")
    return {
        "success": True,
        "file": filename,
        "percorso": filepath,
        "dimensione": f"{size_mb} MB",
        "documenti": totale_doc,
        "collezioni": len(collezioni),
        "durata_s": round(elapsed, 1),
        "eliminati": eliminati,
        "timestamp": start.isoformat(),
    }


# ── POST /api/backup/esegui ───────────────────────────────────────────────────
@router.post("/esegui")
async def backup_manuale(_admin=Depends(require_admin)):
    """Esegue un backup immediato del database."""
    try:
        return await esegui_backup_async()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /api/backup/lista ─────────────────────────────────────────────────────
@router.get("/lista")
async def lista_backup():
    """Elenca tutti i backup disponibili con dimensione e data."""
    # makedirs puo fallire per permessi sul filesystem (es. Render): non deve
    # mandare in 500 la semplice lista. Se la dir non esiste/non e accessibile,
    # restituiamo lista vuota (come fa /stato).
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
    except OSError:
        pass
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, f"{DB_NAME}_*.gz")), reverse=True)
    result = []
    for f in files:
        try:
            stat = os.stat(f)
        except OSError:
            continue
        result.append(
            {
                "file": os.path.basename(f),
                "dimensione": f"{round(stat.st_size / 1024 / 1024, 2)} MB",
                "data": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "size_bytes": stat.st_size,
            }
        )
    return {
        "totale": len(result),
        "max_keep": MAX_BACKUPS,
        "backup": result,
    }


# ── GET /api/backup/stato ─────────────────────────────────────────────────────
@router.get("/stato")
async def stato_backup():
    """Ritorna lo stato dell'ultimo backup."""
    files = sorted(glob.glob(os.path.join(BACKUP_DIR, f"{DB_NAME}_*.gz")), reverse=True)
    if not files:
        return {"ultimo_backup": None, "stato": "nessun_backup"}
    ultimo = files[0]
    stat = os.stat(ultimo)
    return {
        "stato": "ok",
        "ultimo_backup": os.path.basename(ultimo),
        "dimensione": f"{round(stat.st_size / 1024 / 1024, 2)} MB",
        "data": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "totale_backup": len(files),
    }


# ── POST /api/backup/ripristina/{filename} ────────────────────────────────────
@router.post("/ripristina/{filename}")
async def ripristina_backup(filename: str, _admin=Depends(require_admin)):
    """
    Ripristina il database da un backup specifico.
    Flusso atomico:
      1. Valida il nome file
      2. Crea backup di sicurezza del DB attuale
      3. restore pure-Python (drop + reinsert per collezione)
      4. Ritorna esito dettagliato
    """
    # Validazione: accetta sia i vecchi .gz che i nuovi .json.gz
    if not re.match(r"^Gestionale_[\d_]+(?:\.json)?\.gz$", filename):
        raise HTTPException(status_code=400, detail="Nome file non valido")

    filepath = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Backup non trovato: {filename}")

    # 1. Backup di sicurezza PRIMA del restore
    try:
        backup_sicurezza = await esegui_backup_async()
        LOG.info(f"[RESTORE] Backup pre-restore: {backup_sicurezza['file']}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Impossibile creare backup di sicurezza: {e}")

    # 2. Carica il dump JSON-gzip
    try:
        with gzip.open(filepath, "rb") as fh:
            dump = json_util.loads(fh.read().decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup illeggibile: {e}")

    # 3. Restore pure-Python: per ogni collezione drop + reinsert (niente mongorestore)
    start = datetime.now(timezone.utc)
    ripristinate = {}
    for coll_name, docs in dump.items():
        if coll_name == "_meta" or not isinstance(docs, list):
            continue
        try:
            await _db[coll_name].delete_many({})
            # Inserimento a blocchi: evita un unico insert_many gigante in RAM.
            for i in range(0, len(docs), 1000):
                blocco = docs[i:i + 1000]
                if blocco:
                    await _db[coll_name].insert_many(blocco)
            ripristinate[coll_name] = len(docs)
        except Exception as e:
            ripristinate[coll_name] = f"errore: {str(e)[:80]}"
    elapsed = round((datetime.now(timezone.utc) - start).total_seconds(), 1)
    LOG.info(f"[RESTORE] Completato: {filename} in {elapsed}s")

    return {
        "success": True,
        "backup_ripristinato": filename,
        "backup_sicurezza": backup_sicurezza["file"],
        "collezioni_ripristinate": ripristinate,
        "durata_s": elapsed,
        "messaggio": (
            f"Database ripristinato da {filename}. "
            f"Backup di sicurezza salvato: {backup_sicurezza['file']}"
        ),
    }


# ── GET /api/backup/download/{filename} ──────────────────────────────────────
@router.get("/download/{filename}")
async def download_backup(filename: str, _admin=Depends(require_admin)):
    """Scarica un file di backup specifico come download diretto."""
    if not re.match(r"^Gestionale_[\d_]+(?:\.json)?\.gz$", filename):
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
