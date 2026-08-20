"""Consultazione legacy e upload dichiarazioni nell'archivio canonico Drive."""
from typing import Any, Dict, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.config import settings
from app.database import Database
from app.utils.dependencies import get_current_admin_mfa_user, get_current_admin_user

router = APIRouter()
COLL = "documents_inbox"
CATEGORIE = {
    "dichiarazione_iva": "Dichiarazioni IVA",
    "lipe": "LIPE",
    "modello_770": "Modelli 770",
    "redditi_sc": "Redditi società di capitali",
    "dichiarazione_irap": "Dichiarazioni IRAP",
    "elenco_percipienti": "Elenchi percipienti",
    "cartella_esattoriale": "Cartelle Esattoriali",
    "avviso_bonario": "Avvisi Bonari",
}


@router.post("/upload")
async def upload_documento_fiscale(
    file: UploadFile = File(...), categoria: str = Form(...),
    periodo: Optional[str] = Form(None), note: Optional[str] = Form(None),
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    if categoria != "automatica" and categoria not in CATEGORIE:
        raise HTTPException(400, f"Categoria non valida. Ammesse: {', '.join(CATEGORIE)}")
    content = await file.read()
    if not content:
        raise HTTPException(400, "File vuoto")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Sono ammessi solo PDF")
    try:
        import asyncio
        from app.services.drive_declaration_upload import upload_declaration
        result = await asyncio.to_thread(upload_declaration, content=content,
            filename=file.filename or "documento.pdf", category=categoria,
            filing_year=int(periodo or datetime.now().year), note=note)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {**result, "categoria": categoria, "storage": "google_drive"}


@router.get("/lista")
async def lista_documenti_fiscali(
    categoria: Optional[str] = Query(None), limit: int = Query(200, le=1000),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    query: Dict[str, Any] = {"company_id": settings.FISCAL_COMPANY_ID,
                             "category": categoria if categoria else {"$in": list(CATEGORIE)}}
    if categoria and categoria not in CATEGORIE:
        raise HTTPException(400, "Categoria non valida")
    projection = {"_id": 0, "pdf_data": 0}
    docs = await Database.get_db()[COLL].find(query, projection).sort("created_at", -1).to_list(limit)
    for item in docs:
        item["download_url"] = f"/api/documenti/documento/{item['id']}/download"
    return {"documenti": docs, "totale": len(docs), "categorie": CATEGORIE}
