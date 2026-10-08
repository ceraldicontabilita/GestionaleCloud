"""
backup.py — Backup e ripristino dell'archivio di Lotti.

Backup (``esegui_backup_async``, anche ogni notte alle 02:30):
  - dump gzip di Extended JSON di tutte le collezioni, scritto in streaming su
    un file di appoggio temporaneo;
  - il file va su Supabase (``servizi/backup_archivio``: parti verificate in
    ``gestionale.blobs``, manifesto con SHA-256 e conteggi per collezione);
    il file di appoggio si cancella. Un backup che non si rilegge identico
    non esiste;
  - rotazione: restano gli ultimi ``MAX_BACKUPS`` backup verificati.

Ripristino (``/ripristina/{file}``), in tre fasi:
  1. ``dry_run`` (predefinito): per ogni collezione quanti documenti ci sono,
     quanti ne porta il backup e quanti ne sparirebbero. Nessuna scrittura;
  2. backup di sicurezza dello stato attuale, **verificato**: se non riesce il
     ripristino non parte;
  3. sostituzione per id: prima si scrivono i documenti del backup, poi si
     tolgono per id quelli che il backup non ha. Una collezione non resta mai
     vuota a metà strada; per tornare indietro si ripristina il backup di
     sicurezza.

La collezione ``backup_registro`` (l'elenco dei backup) non si salva e non si
ripristina: un ripristino non deve far dimenticare i backup fatti dopo.

Endpoint (tutti amministratore):
  POST /api/backup/esegui
  GET  /api/backup/lista
  GET  /api/backup/stato
  POST /api/backup/ripristina/{f}?dry_run=true|false&conferma=<f>
  GET  /api/backup/download/{f}
  GET  /api/backup/export-json
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from bson import json_util
from datetime import datetime, timezone
import os, logging, re, json, gzip, tempfile
from app.lotti.db import database as _db, DB_NAME
from app.lotti.auth import require_admin
from app.lotti.servizi import backup_archivio

router = APIRouter(prefix="/backup", tags=["Backup"])
MAX_BACKUPS = backup_archivio.MAX_BACKUPS
REGISTRO = backup_archivio.REGISTRO
LOG = logging.getLogger("backup")
# Appoggio locale del solo backup in corso: si cancella a fine giro.
APPOGGIO_DIR = tempfile.gettempdir()


def _nome_valido(filename: str) -> bool:
    return bool(re.match(r"^" + re.escape(DB_NAME) + r"_\d{4}-\d{2}-\d{2}_\d{4,6}(?:-\d{1,3})?\.json\.gz$", filename))


def _rimuovi(percorso: str) -> None:
    try:
        os.remove(percorso)
    except OSError:
        pass


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


async def _scrivi_dump(filepath: str, meta: dict, collezioni: list) -> tuple:
    """Dump in streaming (un blocco da 500 documenti alla volta, serializzato
    in un thread: l'event loop resta libero e le API rispondono)."""
    import asyncio as _aio

    def _scrivi_blocco(fh, items):
        fh.write("".join(
            pref + json_util.dumps(d, ensure_ascii=False) for pref, d in items
        ))

    conteggi: dict = {}
    fallite: list = []
    with gzip.open(filepath, "wt", encoding="utf-8") as fh:
        fh.write("{")
        fh.write('"_meta":')
        fh.write(json.dumps(meta, ensure_ascii=False, default=str))
        for coll_name in collezioni:
            fh.write(",")
            fh.write(json.dumps(coll_name))
            fh.write(":[")
            primo = True
            n = 0
            try:
                cursor = _db[coll_name].find({}).batch_size(500)
                blocco = []
                async for doc in cursor:
                    blocco.append(("" if primo else ",", doc))
                    primo = False
                    n += 1
                    if len(blocco) >= 500:
                        await _aio.to_thread(_scrivi_blocco, fh, blocco)
                        blocco = []
                        await _aio.sleep(0.05)  # aria alle altre richieste
                if blocco:
                    await _aio.to_thread(_scrivi_blocco, fh, blocco)
            except Exception as e:
                fallite.append(coll_name)
                LOG.warning("[BACKUP] collezione %s parziale: %s: %s", coll_name, type(e).__name__, e)
            conteggi[coll_name] = n
            fh.write("]")
        fh.write("}")
    return conteggi, fallite


async def _registro() -> list:
    righe = await _db[REGISTRO].find({}, {"_id": 0}).to_list(None)
    return sorted(righe, key=lambda r: str(r.get("creato_at") or ""), reverse=True)


async def _ruota() -> list:
    """Tiene gli ultimi MAX_BACKUPS verificati; gli altri si tolgono per chiave."""
    eliminati = []
    for vecchio in (await _registro())[MAX_BACKUPS:]:
        try:
            await backup_archivio.elimina(vecchio)
            await _db[REGISTRO].delete_one({"id": vecchio["id"]})
            eliminati.append(vecchio["nome"])
        except Exception as e:
            LOG.error("[BACKUP] rotazione di %s non riuscita: %s %s", vecchio.get("nome"), type(e).__name__, e)
    return eliminati


async def esegui_backup_async() -> dict:
    """Backup completo su Supabase, verificato. Solleva se non è persistente."""
    start = datetime.now(timezone.utc)
    base = f"{DB_NAME}_{start.strftime('%Y-%m-%d_%H%M%S')}"
    filename = f"{base}.json.gz"
    # Due backup nello stesso secondo (ripristino subito dopo un backup) non
    # devono condividere nome, parti e riga di registro.
    n = 1
    while await _db[REGISTRO].find_one({"id": filename}, {"_id": 1}):
        n += 1
        filename = f"{base}-{n}.json.gz"
    filepath = os.path.join(APPOGGIO_DIR, filename)

    try:
        collezioni = sorted(
            c for c in await _db.list_collection_names()
            if not c.startswith("system.") and c != REGISTRO
        )
    except Exception as e:
        raise RuntimeError(f"Impossibile elencare le collezioni: {type(e).__name__}: {e}") from e

    meta = {
        "db": DB_NAME,
        "exported_at": start.isoformat(),
        "version": "2.2",
        "tipo": "json-gzip-stream",
        "collezioni": collezioni,
    }
    try:
        conteggi, fallite = await _scrivi_dump(filepath, meta, collezioni)
        if fallite:
            # Un backup incompleto non si archivia e non si ripristina.
            return {
                "success": False, "parziale": True, "collezioni_fallite": fallite,
                "file": filename, "timestamp": start.isoformat(),
                "messaggio": "Backup incompleto: non archiviato",
            }
        totale_doc = sum(conteggi.values())
        manifesto = await backup_archivio.salva(filename, filepath, {
            "creato_at": start.isoformat(),
            "documenti": totale_doc,
            "collezioni": len(collezioni),
            "conteggi": conteggi,
        })
    finally:
        _rimuovi(filepath)

    await _db[REGISTRO].insert_one({"id": filename, **manifesto})
    eliminati = await _ruota()
    size_mb = round(manifesto["bytes"] / 1024 / 1024, 2)
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    LOG.info("[BACKUP] %s - %s MB - %s doc - %s parti verificate - %.1fs",
             filename, size_mb, totale_doc, len(manifesto["parti"]), elapsed)
    return {
        "success": True,
        "verificato": True,
        "parziale": False,
        "collezioni_fallite": [],
        "file": filename,
        "sha256": manifesto["sha256"],
        "parti": len(manifesto["parti"]),
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
        LOG.error("[BACKUP] manuale fallito: %s %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail=f"Backup non riuscito: {type(e).__name__}") from e


def _voce(r: dict) -> dict:
    return {
        "file": r.get("nome"),
        "dimensione": f"{round(int(r.get('bytes') or 0) / 1024 / 1024, 2)} MB",
        "data": r.get("creato_at"),
        "size_bytes": r.get("bytes"),
        "sha256": r.get("sha256"),
        "verificato": bool(r.get("verificato")),
        "verificato_at": r.get("verificato_at"),
        "documenti": r.get("documenti"),
        "archivio": "supabase",
    }


# ── GET /api/backup/lista ─────────────────────────────────────────────────────
@router.get("/lista")
async def lista_backup(_admin=Depends(require_admin)):
    """Elenca i backup archiviati su Supabase, il più recente per primo."""
    righe = await _registro()
    return {"totale": len(righe), "max_keep": MAX_BACKUPS, "backup": [_voce(r) for r in righe]}


# ── GET /api/backup/stato ─────────────────────────────────────────────────────
@router.get("/stato")
async def stato_backup(_admin=Depends(require_admin)):
    """Ritorna lo stato dell'ultimo backup."""
    righe = await _registro()
    if not righe:
        return {"ultimo_backup": None, "stato": "nessun_backup"}
    ultimo = _voce(righe[0])
    return {
        "stato": "ok" if ultimo["verificato"] else "non_verificato",
        "ultimo_backup": ultimo["file"],
        "dimensione": ultimo["dimensione"],
        "data": ultimo["data"],
        "verificato": ultimo["verificato"],
        "archivio": "supabase",
        "totale_backup": len(righe),
    }


async def _manifesto(filename: str) -> dict:
    if not _nome_valido(filename):
        raise HTTPException(status_code=400, detail="Nome file non valido")
    manifesto = await _db[REGISTRO].find_one({"id": filename}, {"_id": 0})
    if not manifesto:
        raise HTTPException(status_code=404, detail=f"Backup non trovato: {filename}")
    return manifesto


async def _sostituisci_collezione(coll_name: str, docs: list) -> dict:
    """Scrive i documenti del backup, poi toglie per id quelli che non ha."""
    from app.lotti.supabase_document_store import PersistentCollection

    coll = _db[coll_name]
    if isinstance(coll, PersistentCollection):
        return await coll.sostituisci_per_id(docs)
    ids = [d["_id"] for d in docs]
    for d in docs:
        await coll.replace_one({"_id": d["_id"]}, d, upsert=True)
    rimossi = await coll.delete_many({"_id": {"$nin": ids}})
    return {"scritti": len(docs), "rimossi": rimossi.deleted_count}


# ── POST /api/backup/ripristina/{filename} ────────────────────────────────────
@router.post("/ripristina/{filename}")
async def ripristina_backup(
    filename: str,
    dry_run: bool = Query(True, description="Simulazione: solo conteggi, nessuna scrittura"),
    conferma: str = Query(None, description="Per ripristinare davvero: ripetere il nome del file"),
    _admin=Depends(require_admin),
):
    """Ripristino in tre fasi: simulazione, backup di sicurezza verificato,
    sostituzione per id. Senza ``dry_run=false`` e ``conferma`` uguale al nome
    del file non scrive nulla."""
    manifesto = await _manifesto(filename)
    appoggio = os.path.join(APPOGGIO_DIR, f"ripristino_{filename}")
    try:
        await backup_archivio.ricomponi(manifesto, appoggio)
        with gzip.open(appoggio, "rb") as fh:
            dump = json_util.loads(fh.read().decode("utf-8"))
    except backup_archivio.BackupNonPersistente as e:
        raise HTTPException(status_code=409, detail=f"Backup non integro: {e}") from e
    except Exception as e:
        LOG.error("[RESTORE] %s illeggibile: %s %s", filename, type(e).__name__, e)
        raise HTTPException(status_code=500, detail="Backup illeggibile") from e
    finally:
        _rimuovi(appoggio)

    dati = {c: docs for c, docs in dump.items()
            if c not in ("_meta", REGISTRO) and isinstance(docs, list)}
    piano = {}
    for coll_name, docs in sorted(dati.items()):
        attuali = {str(d["_id"]) for d in await _db[coll_name].find({}, {"_id": 1}).to_list(None)}
        nel_backup = {str(d.get("_id")) for d in docs}
        piano[coll_name] = {
            "attuali": len(attuali),
            "nel_backup": len(docs),
            "da_togliere": len(attuali - nel_backup),
            "da_aggiungere": len(nel_backup - attuali),
        }
    esistenti = set(await _db.list_collection_names()) - {REGISTRO}
    non_toccate = sorted(c for c in esistenti - set(dati) if not c.startswith("system."))
    riepilogo = {
        "backup": filename,
        "creato_at": manifesto.get("creato_at"),
        "sha256": manifesto.get("sha256"),
        "collezioni": piano,
        "collezioni_non_nel_backup": non_toccate,
        "documenti_da_togliere": sum(v["da_togliere"] for v in piano.values()),
    }
    if dry_run:
        return {"dry_run": True, **riepilogo}
    if conferma != filename:
        raise HTTPException(status_code=400, detail="Per ripristinare ripeti il nome del file in «conferma»")

    try:
        sicurezza = await esegui_backup_async()
    except Exception as e:
        LOG.error("[RESTORE] backup di sicurezza fallito: %s %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail="Backup di sicurezza non riuscito: ripristino annullato") from e
    if not (sicurezza.get("success") and sicurezza.get("verificato")):
        raise HTTPException(status_code=500, detail="Backup di sicurezza non verificato: ripristino annullato")

    start = datetime.now(timezone.utc)
    esiti, errori = {}, {}
    for coll_name, docs in sorted(dati.items()):
        try:
            esiti[coll_name] = await _sostituisci_collezione(coll_name, docs)
        except Exception as e:
            errori[coll_name] = type(e).__name__
            LOG.error("[RESTORE] %s: %s %s", coll_name, type(e).__name__, e)
    elapsed = round((datetime.now(timezone.utc) - start).total_seconds(), 1)
    LOG.info("[RESTORE] %s in %ss, errori: %s", filename, elapsed, sorted(errori))
    return {
        "dry_run": False,
        "success": not errori,
        "collezioni_con_errore": sorted(errori),
        "backup_ripristinato": filename,
        "backup_sicurezza": sicurezza["file"],
        "collezioni_ripristinate": esiti,
        "durata_s": elapsed,
        "piano": riepilogo,
        "messaggio": (
            f"Ripristinato {filename}. Per tornare indietro: ripristina {sicurezza['file']}."
        ),
    }


# ── GET /api/backup/download/{filename} ──────────────────────────────────────
@router.get("/download/{filename}")
async def download_backup(filename: str, _admin=Depends(require_admin)):
    """Scarica un backup: ricomposto dalle parti e verificato con l'impronta."""
    manifesto = await _manifesto(filename)
    appoggio = os.path.join(APPOGGIO_DIR, f"download_{filename}")
    try:
        await backup_archivio.ricomponi(manifesto, appoggio)
    except backup_archivio.BackupNonPersistente as e:
        _rimuovi(appoggio)
        raise HTTPException(status_code=409, detail=f"Backup non integro: {e}") from e
    return FileResponse(
        path=appoggio,
        filename=filename,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        background=BackgroundTask(_rimuovi, appoggio),
    )
