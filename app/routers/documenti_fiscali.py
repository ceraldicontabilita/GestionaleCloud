"""Consultazione legacy e upload dichiarazioni nell'archivio canonico Drive."""
from typing import Any, Dict, Optional
from datetime import datetime, date

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
    data_presentazione: Optional[date] = Form(None), riferimento_cassetto: Optional[str] = Form(None),
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    if categoria != "automatica" and categoria not in CATEGORIE:
        raise HTTPException(400, f"Categoria non valida. Ammesse: {', '.join(CATEGORIE)}")
    content = await file.read()
    if not content:
        raise HTTPException(400, "File vuoto")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Sono ammessi solo PDF")
    import asyncio
    if categoria == 'lipe':
        from app.services.lipe_parser import parse_lipe
        preview = await asyncio.to_thread(parse_lipe, content)
        if not preview.get('anno') or not preview.get('periodi') or any(not p.get('periodo') or not p.get('quadratura_ok') for p in preview['periodi']):
            raise HTTPException(422, 'LIPE non leggibile o non quadrata: nessun dato fiscale salvato')
        if preview.get('taxpayer_id') and preview['taxpayer_id'] != settings.FISCAL_COMPANY_ID:
            raise HTTPException(422, 'Il contribuente della LIPE non corrisponde alla società')
        if periodo and str(periodo) != str(preview['anno']):
            raise HTTPException(422, 'Anno selezionato diverso dall’anno imposta stampato nella LIPE')
        periodo = str(preview['anno'])
    try:
        from app.services.drive_declaration_upload import upload_declaration
        result = await asyncio.to_thread(upload_declaration, content=content,
            filename=file.filename or "documento.pdf", category=categoria,
            filing_year=int(periodo or datetime.now().year), note=note)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    if categoria == 'lipe':
        from app.services.fiscal_document_ingestion import FiscalDocumentIngestionService
        from app.services.lipe_deposito import deposita_lipe
        db = Database.get_db()
        registered = await FiscalDocumentIngestionService(db).ingest(
            content=content, filename=file.filename or 'LIPE.pdf', source='documenti_upload', category_hint='lipe',
            expected_sha256=result['sha256'], source_metadata={
                'drive_file_id': result.get('drive_file_id'), 'drive_document_id': result.get('document_id'),
                'drive_path': result.get('drive_path'), 'tax_year': int(periodo), 'filing_year': int(periodo),
                'data_presentazione': data_presentazione.isoformat() if data_presentazione else None,
                'data_presentazione_fonte': 'conferma_titolare' if data_presentazione else None,
                'riferimento_cassetto': riferimento_cassetto,
                'original_filename': file.filename, 'uploaded_by': _admin.get('user_id') or _admin.get('email'),
            })
        result['fiscal_document_id'] = registered['document_id']
        result['lipe'] = await deposita_lipe(db, content, nome_file=file.filename or 'LIPE.pdf',
            origine='documenti_upload', drive_file_id=result.get('drive_file_id'),
            source_document_id=registered['document_id'],
            data_presentazione=data_presentazione.isoformat() if data_presentazione else None,
            riferimento_cassetto=riferimento_cassetto)
    return {**result, "categoria": categoria, "storage": "google_drive"}


@router.post("/upload-f24-commercialista")
async def upload_f24_commercialista_drive(
    file: UploadFile = File(...), anno: int = Form(...), note: Optional[str] = Form(None),
    _admin: Dict[str, Any] = Depends(get_current_admin_mfa_user),
) -> Dict[str, Any]:
    content = await file.read()
    if not content:
        raise HTTPException(400, "File vuoto")
    try:
        import asyncio
        from app.services.drive_f24_model_upload import upload_f24_accountant_model

        return await asyncio.to_thread(
            upload_f24_accountant_model, content=content,
            filename=file.filename or "f24-commercialista.pdf",
            filing_year=anno, note=note,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


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
