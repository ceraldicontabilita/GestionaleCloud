"""Compatibilita upload fiscale, delegata alla pipeline unica di Documenti."""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.config import settings
from app.database import Database
from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService
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
    admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    if categoria != "automatica" and categoria not in CATEGORIE:
        raise HTTPException(400, f"Categoria non valida. Ammesse: {', '.join(CATEGORIE)}")
    content = await file.read()
    if not content:
        raise HTTPException(400, "File vuoto")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Sono ammessi solo PDF")
    actor = admin.get("user_id") if isinstance(admin, dict) else "direct-test"
    try:
        result = await FiscalDocumentIngestionService(Database.get_db()).ingest(
            content=content, filename=file.filename or "documento.pdf",
            source="upload_automatico" if categoria == "automatica" else "upload_manuale",
            category_hint=None if categoria == "automatica" else categoria,
            source_metadata={"periodo": periodo, "note": note,
                             "uploaded_by": actor,
                             "declared_category": None if categoria == "automatica" else categoria},
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db = Database.get_db()
    inbox = await db[COLL].find_one(
        {"company_id": settings.FISCAL_COMPANY_ID, "sha256": result["sha256"]},
        {"_id": 0, "id": 1},
    )
    if not inbox:
        raise HTTPException(409, "Versione fiscale senza documento nell'archivio Documenti")
    return {"success": True, "duplicate": result["status"] == "duplicate",
            "id": inbox["id"], "categoria": categoria,
            "fiscal_document_id": result["document_id"],
            "download_url": f"/api/documenti/documento/{inbox['id']}/download"}


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
