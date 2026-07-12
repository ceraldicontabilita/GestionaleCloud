"""
Documenti fiscali caricati a mano (dichiarazione IVA, cartelle esattoriali,
avvisi bonari e simili).

L'utente carica un PDF dal gestionale → gli viene assegnato un ID, il file è
memorizzato in MongoDB (hub unico `documents_inbox`, campo `pdf_data` base64) e
poi è sempre recuperabile/scaricabile con lo stesso ID. Nessun nuovo storage:
si riusa l'hub documentale esistente e il download generico
`/api/documenti/documento/{id}/download`.

Montato sotto /api/documenti-fiscali (vedi router_registry).
"""
import base64
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Query

from app.database import Database

router = APIRouter()

COLL = "documents_inbox"

# Categorie fiscali ammesse per l'upload manuale, con etichetta leggibile.
CATEGORIE = {
    "dichiarazione_iva": "Dichiarazioni IVA",
    "cartella_esattoriale": "Cartelle Esattoriali",
    "avviso_bonario": "Avvisi Bonari",
}


@router.post("/upload")
async def upload_documento_fiscale(
    file: UploadFile = File(...),
    categoria: str = Form(...),
    periodo: Optional[str] = Form(None),   # es. "2025" o "2026-03", facoltativo
    note: Optional[str] = Form(None),
) -> Dict[str, Any]:
    """Carica un PDF fiscale e lo memorizza con un ID recuperabile.

    Ritorna id + download_url. Dedup per impronta md5: lo stesso file caricato
    due volte non crea doppioni (restituisce l'ID esistente)."""
    if categoria not in CATEGORIE:
        raise HTTPException(
            status_code=400,
            detail=f"Categoria non valida. Ammesse: {', '.join(CATEGORIE)}",
        )
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File vuoto")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Sono ammessi solo PDF")

    db = Database.get_db()
    file_hash = hashlib.md5(content).hexdigest()

    # Dedup: stesso PDF già caricato → restituisci l'ID esistente
    esistente = await db[COLL].find_one({"file_hash": file_hash}, {"_id": 0, "id": 1})
    if esistente:
        return {
            "success": True,
            "duplicate": True,
            "id": esistente["id"],
            "download_url": f"/api/documenti/documento/{esistente['id']}/download",
        }

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "filename": file.filename,
        "pdf_data": base64.b64encode(content).decode(),
        "file_hash": file_hash,
        "size_bytes": len(content),
        "category": categoria,
        "category_label": CATEGORIE[categoria],
        "tipo_documento": categoria,
        "categoria": categoria,
        "periodo": periodo,
        "note": note,
        "fonte": "upload_manuale",
        "source": "upload_manuale",
        "stato": "importato",
        "status": "nuovo",
        "processed": False,
        "xml_processed": True,   # già classificato: non passa dal routing email
        "created_at": now,
        "downloaded_at": now,
    }
    await db[COLL].insert_one(doc.copy())
    return {
        "success": True,
        "duplicate": False,
        "id": doc["id"],
        "categoria": categoria,
        "download_url": f"/api/documenti/documento/{doc['id']}/download",
    }


@router.get("/lista")
async def lista_documenti_fiscali(
    categoria: Optional[str] = Query(None, description="Filtra per categoria fiscale"),
    limit: int = Query(200, le=1000),
) -> Dict[str, Any]:
    """Elenca i documenti fiscali archiviati (senza il PDF, solo i metadati)."""
    db = Database.get_db()
    query: Dict[str, Any] = {}
    if categoria:
        if categoria not in CATEGORIE:
            raise HTTPException(status_code=400, detail="Categoria non valida")
        query["category"] = categoria
    else:
        query["category"] = {"$in": list(CATEGORIE)}

    proj = {
        "_id": 0, "id": 1, "filename": 1, "category": 1, "category_label": 1,
        "periodo": 1, "note": 1, "size_bytes": 1, "created_at": 1, "fonte": 1,
    }
    docs = await db[COLL].find(query, proj).sort("created_at", -1).to_list(limit)
    for d in docs:
        d["download_url"] = f"/api/documenti/documento/{d['id']}/download"
    return {"documenti": docs, "totale": len(docs), "categorie": CATEGORIE}
