"""
Fatture Foto + OCR Correzioni router — per Appgestionale mobile.

Tre scopi:
1) Upload foto JPEG/PNG allegata a una fattura esistente (per ricordare la cartacea)
2) Salvataggio correzioni utente OCR (diff AI↔utente) per apprendimento
3) Lettura correzioni (richiamata dall'app prima di chiamare Claude Vision)

Le foto vengono salvate su disco in app/uploads/fatture_foto/<invoice_id>/
e il path viene aggiunto al documento invoice in un array `foto_allegate`.

Le correzioni vivono nella collezione `ocr_correzioni` (unica, non per-device).

L'OCR vero e proprio resta CLIENT-SIDE nell'app Appgestionale:
l'app chiama direttamente Anthropic; qui il backend serve solo a persistere
i dati storici delle correzioni per migliorare il prompt futuro.
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Path as PathParam, Query, UploadFile, status

from app.database import Database
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================
# CONFIG
# ============================================================

FOTO_ROOT = Path(os.environ.get("FATTURE_FOTO_DIR", "app/uploads/fatture_foto"))
FOTO_ROOT.mkdir(parents=True, exist_ok=True)

MAX_FOTO_SIZE = 8 * 1024 * 1024  # 8MB per foto
ALLOWED_MIMES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic"}


# ============================================================
# 1) UPLOAD FOTO A FATTURA ESISTENTE
# ============================================================

@router.post(
    "/invoices/{invoice_id}/foto",
    status_code=status.HTTP_201_CREATED,
    summary="Allega una foto (cartacea) a una fattura esistente",
)
async def upload_foto_fattura(
    invoice_id: str = PathParam(..., description="ID della fattura in collezione invoices"),
    file: UploadFile = File(..., description="Foto JPEG/PNG/WebP, max 8MB"),
    note: Optional[str] = Form(None, description="Nota opzionale sulla foto"),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Salva la foto su disco e aggiunge il riferimento al documento invoice.
    Struttura nel doc invoice:
        foto_allegate: [
          {id, filename, mime, size, path, note, uploaded_at, uploaded_by}
        ]
    """
    db = Database.get_db()

    # Verifica esistenza fattura
    invoice = await db["invoices"].find_one({"id": invoice_id})
    if not invoice:
        # Fallback: alcune collezioni storiche usano invoice_key
        invoice = await db["invoices"].find_one({"invoice_key": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail=f"Fattura {invoice_id} non trovata")

    # Validazione file
    raw = await file.read()
    if len(raw) > MAX_FOTO_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Foto troppo grande ({len(raw)//1024} KB, max {MAX_FOTO_SIZE//1024} KB)",
        )
    mime = (file.content_type or "").lower()
    if mime not in ALLOWED_MIMES:
        raise HTTPException(
            status_code=415,
            detail=f"Tipo non supportato: {mime}. Usa jpg/png/webp/heic",
        )

    # Salva su disco in sottocartella per invoice
    invoice_key = invoice.get("id") or invoice.get("invoice_key")
    folder = FOTO_ROOT / str(invoice_key)
    folder.mkdir(parents=True, exist_ok=True)

    foto_id = str(uuid.uuid4())
    ext = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/heic": ".heic",
    }.get(mime, ".jpg")
    fname = f"{foto_id}{ext}"
    filepath = folder / fname

    try:
        filepath.write_bytes(raw)
    except OSError as e:
        logger.exception("[FATTURE_FOTO] errore scrittura file")
        raise HTTPException(status_code=500, detail=f"Scrittura file fallita: {e}")

    # Registra nel documento invoice
    foto_record = {
        "id": foto_id,
        "filename": file.filename or fname,
        "stored_as": fname,
        "mime": mime,
        "size_bytes": len(raw),
        "path": str(filepath),
        "note": (note or "").strip(),
        "uploaded_at": datetime.now(timezone.utc),
        "uploaded_by": current_user.get("email") or current_user.get("username"),
    }

    await db["invoices"].update_one(
        {"id": invoice_key} if invoice.get("id") else {"invoice_key": invoice_key},
        {"$push": {"foto_allegate": foto_record}},
    )

    logger.info(f"[FATTURE_FOTO] allegata foto {foto_id} a invoice {invoice_key} ({len(raw)} B)")

    return {
        "ok": True,
        "foto_id": foto_id,
        "invoice_id": invoice_key,
        "size_bytes": len(raw),
        "mime": mime,
    }


@router.get(
    "/invoices/{invoice_id}/foto",
    summary="Lista foto allegate a una fattura",
)
async def list_foto_fattura(
    invoice_id: str = PathParam(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    db = Database.get_db()
    invoice = await db["invoices"].find_one(
        {"$or": [{"id": invoice_id}, {"invoice_key": invoice_id}]},
        {"foto_allegate": 1, "_id": 0},
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    foto = invoice.get("foto_allegate", []) or []
    # Non restituire path assoluto del server (info privata). Costruisci URL relativa
    for f in foto:
        f["url"] = f"/api/invoices/{invoice_id}/foto/{f['id']}"
        f.pop("path", None)
    return foto


@router.get(
    "/invoices/{invoice_id}/foto/{foto_id}",
    summary="Scarica una foto specifica",
)
async def get_foto_fattura(
    invoice_id: str = PathParam(...),
    foto_id: str = PathParam(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    from fastapi.responses import FileResponse

    db = Database.get_db()
    invoice = await db["invoices"].find_one(
        {"$or": [{"id": invoice_id}, {"invoice_key": invoice_id}]},
        {"foto_allegate": 1},
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    foto = next((f for f in invoice.get("foto_allegate", []) if f.get("id") == foto_id), None)
    if not foto:
        raise HTTPException(status_code=404, detail="Foto non trovata")

    path = foto.get("path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=410, detail="File fisico non più disponibile")

    return FileResponse(path, media_type=foto.get("mime", "image/jpeg"))


@router.delete(
    "/invoices/{invoice_id}/foto/{foto_id}",
    summary="Elimina una foto (file su disco + record nel doc invoice)",
)
async def delete_foto_fattura(
    invoice_id: str = PathParam(...),
    foto_id: str = PathParam(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    db = Database.get_db()
    invoice = await db["invoices"].find_one(
        {"$or": [{"id": invoice_id}, {"invoice_key": invoice_id}]},
        {"foto_allegate": 1, "id": 1, "invoice_key": 1},
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    foto = next((f for f in invoice.get("foto_allegate", []) if f.get("id") == foto_id), None)
    if not foto:
        raise HTTPException(status_code=404, detail="Foto non trovata")

    # Rimuovi file fisico (best effort)
    path = foto.get("path")
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            logger.warning(f"[FATTURE_FOTO] impossibile eliminare file {path}")

    # Rimuovi dal documento
    key_field = "id" if invoice.get("id") else "invoice_key"
    key_val = invoice.get(key_field)
    await db["invoices"].update_one(
        {key_field: key_val},
        {"$pull": {"foto_allegate": {"id": foto_id}}},
    )

    return {"ok": True, "deleted": foto_id}


# ============================================================
# 2) OCR CORREZIONI — storage server-side per apprendimento
# ============================================================

CAMPI_OCR = ["fornitore", "numero_fattura", "importo", "data", "pagamento", "partita_iva", "iban"]


def _norm(s: str) -> str:
    """Normalizza stringa per confronti/chiavi (case/spazi/punteggiatura)."""
    return " ".join((s or "").lower().replace(".", "").replace(",", "").split())


@router.post(
    "/ocr-fatture/correzione",
    status_code=status.HTTP_201_CREATED,
    summary="Registra diff AI↔utente per apprendimento OCR",
)
async def registra_correzione_ocr(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Payload atteso:
        {
          "ai_read": {...},     # oggetto ritornato da Claude Vision
          "user_final": {...},  # oggetto che l'utente ha effettivamente salvato
          "fornitore_context": "...",
          "invoice_id": "uuid"  # opzionale
        }
    Crea un record in ocr_correzioni per ogni campo effettivamente corretto.
    """
    ai_read = payload.get("ai_read") or {}
    user_final = payload.get("user_final") or {}
    forn_ctx = (payload.get("fornitore_context") or user_final.get("fornitore") or "").strip()
    invoice_id = payload.get("invoice_id")

    if not ai_read or not user_final:
        raise HTTPException(status_code=400, detail="Mancano ai_read o user_final")

    db = Database.get_db()
    ora = datetime.now(timezone.utc)
    ts_epoch = int(ora.timestamp())
    forn_norm = _norm(forn_ctx)

    nuove = []
    for campo in CAMPI_OCR:
        ai_val = str(ai_read.get(campo, "") or "").strip()
        user_val = str(user_final.get(campo, "") or "").strip()

        if not ai_val or not user_val:
            continue
        if ai_val.lower() == user_val.lower():
            continue

        # Dedup: se esiste stessa coppia per stesso fornitore, salta
        existing = await db["ocr_correzioni"].find_one({
            "campo": campo,
            "sbagliato": ai_val,
            "corretto": user_val,
            "fornitore_norm": forn_norm,
        })
        if existing:
            continue

        doc = {
            "id": str(uuid.uuid4()),
            "campo": campo,
            "sbagliato": ai_val,
            "corretto": user_val,
            "fornitore": forn_ctx,
            "fornitore_norm": forn_norm,
            "invoice_id": invoice_id,
            "user": current_user.get("email") or current_user.get("username"),
            "ts": ora,
            "ts_epoch": ts_epoch,
        }
        await db["ocr_correzioni"].insert_one(doc.copy())
        nuove.append({"campo": campo, "da": ai_val, "a": user_val})

    return {"ok": True, "correzioni_registrate": len(nuove), "dettagli": nuove}


@router.get(
    "/ocr-fatture/correzioni",
    summary="Lista correzioni memorizzate (l'app la usa per costruire il prompt)",
)
async def list_correzioni_ocr(
    fornitore: Optional[str] = Query(None, description="Filtra per fornitore (normalizzato)"),
    campo: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    db = Database.get_db()
    query: Dict[str, Any] = {}
    if fornitore:
        query["fornitore_norm"] = _norm(fornitore)
    if campo:
        query["campo"] = campo

    rows = await db["ocr_correzioni"].find(
        query, {"_id": 0}
    ).sort("ts_epoch", -1).limit(limit).to_list(limit)
    return rows


@router.delete(
    "/ocr-fatture/correzioni/{correzione_id}",
    summary="Elimina una correzione (se sbagliata/obsoleta)",
)
async def delete_correzione_ocr(
    correzione_id: str = PathParam(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    db = Database.get_db()
    res = await db["ocr_correzioni"].delete_one({"id": correzione_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Non trovata")
    return {"ok": True, "deleted": correzione_id}


@router.get(
    "/ocr-fatture/stats",
    summary="Statistiche apprendimento OCR",
)
async def stats_ocr(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    db = Database.get_db()
    tot = await db["ocr_correzioni"].count_documents({})

    per_campo_cur = db["ocr_correzioni"].aggregate([
        {"$group": {"_id": "$campo", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ])
    per_campo = [{"campo": r["_id"], "count": r["count"]} async for r in per_campo_cur]

    top_forn_cur = db["ocr_correzioni"].aggregate([
        {"$match": {"fornitore_norm": {"$ne": ""}}},
        {"$group": {"_id": "$fornitore", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ])
    top_forn = [{"fornitore": r["_id"], "count": r["count"]} async for r in top_forn_cur]

    return {
        "totale_correzioni": tot,
        "per_campo": per_campo,
        "top_fornitori": top_forn,
    }
