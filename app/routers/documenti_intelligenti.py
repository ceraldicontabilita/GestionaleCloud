"""
Router Gestione Documenti Intelligente
Sistema unificato per classificazione automatica email e associazione ai moduli del gestionale.

Endpoint principali:
- /scan: Scansiona e classifica email
- /process: Processa documenti classificati
- /stats: Statistiche per categoria
- /cleanup: Pulizia email non rilevanti
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel

from app.database import Database
from app.services.email_classifier_service import (
    scan_and_classify_emails,
    process_classified_documents,
    get_categories_mapping,
    get_all_keywords,
    EMAIL_RULES,
    classify_email
)
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class ScanRequest(BaseModel):
    cartella: str = "INBOX"
    giorni: int = 30
    delete_unmatched: bool = False
    dry_run: bool = True


class ClassifyTestRequest(BaseModel):
    subject: str
    sender: str = ""
    body: str = ""


# ============================================================
# ENDPOINT CLASSIFICAZIONE EMAIL
# ============================================================

@router.post("/scan")
async def scan_emails(
    request: ScanRequest
) -> Dict[str, Any]:
    """
    Scansiona le email e le classifica automaticamente.
    
    - **cartella**: Cartella IMAP da scansionare (default: INBOX)
    - **giorni**: Numero di giorni da controllare (default: 30)
    - **delete_unmatched**: Se True, elimina email che non matchano (default: False)
    - **dry_run**: Se True, non esegue modifiche reali (default: True)
    """
    db = Database.get_db()
    
    risultati = await scan_and_classify_emails(
        db=db,
        cartella=request.cartella,
        giorni=request.giorni,
        delete_unmatched=request.delete_unmatched,
        dry_run=request.dry_run
    )
    
    return risultati


@router.post("/process")
async def process_documents() -> Dict[str, Any]:
    """
    Processa i documenti classificati e li associa alle sezioni del gestionale.
    """
    db = Database.get_db()
    risultati = await process_classified_documents(db)
    return risultati


@router.get("/categories")
async def get_categories() -> Dict[str, Any]:
    """
    Ritorna il mapping delle categorie alle sezioni del gestionale.
    """
    return {
        "categories": get_categories_mapping(),
        "keywords": get_all_keywords(),
        "rules_count": len(EMAIL_RULES)
    }


@router.get("/rules")
async def get_rules() -> List[Dict[str, Any]]:
    """
    Ritorna tutte le regole di classificazione.
    """
    return [
        {
            "name": rule.name,
            "keywords": rule.keywords,
            "subject_patterns": rule.subject_patterns,
            "sender_patterns": rule.sender_patterns,
            "category": rule.category,
            "gestionale_section": rule.gestionale_section,
            "collection": rule.collection,
            "action": rule.action,
            "priority": rule.priority
        }
        for rule in EMAIL_RULES
    ]


@router.post("/test-classify")
async def test_classification(request: ClassifyTestRequest) -> Dict[str, Any]:
    """
    Testa la classificazione di un'email senza salvarla.
    Utile per verificare come verrebbe classificata un'email specifica.
    """
    rule, confidence = classify_email(request.subject, request.sender, request.body)
    
    return {
        "classified": rule is not None,
        "category": rule.category if rule else None,
        "confidence": round(confidence, 2),
        "gestionale_section": rule.gestionale_section if rule else None,
        "action": rule.action if rule else None,
        "rule_name": rule.name if rule else None
    }


@router.get("/documents")
async def get_classified_documents(
    categoria: Optional[str] = Query(None, description="Filtra per categoria"),
    processed: Optional[bool] = Query(None, description="Filtra per stato processamento"),
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0)
) -> Dict[str, Any]:
    """
    Lista i documenti classificati.
    """
    db = Database.get_db()
    
    query = {}
    if categoria:
        query["tipo"] = categoria
    if processed is not None:
        query["processed"] = processed
    
    documents = await db["documents_classified"].find(
        query,
        {"pdf_base64": 0}  # Escludi PDF per performance
    ).sort("data_inserimento", -1).skip(skip).limit(limit).to_list(limit)
    
    # Converti ObjectId
    for doc in documents:
        doc["_id"] = str(doc["_id"])
    
    # Statistiche
    total = await db["documents_classified"].count_documents(query)
    
    pipeline = [
        {"$group": {"_id": "$tipo", "count": {"$sum": 1}}}
    ]
    by_category = {doc["_id"]: doc["count"] async for doc in db["documents_classified"].aggregate(pipeline)}
    
    return {
        "documents": documents,
        "total": total,
        "by_category": by_category
    }


@router.get("/stats")
async def get_classification_stats() -> Dict[str, Any]:
    """
    Statistiche complete sulla classificazione documenti.
    """
    db = Database.get_db()
    
    # Conta documenti classificati
    total_classified = await db["documents_classified"].count_documents({})
    processed = await db["documents_classified"].count_documents({"processed": True})
    
    # Per categoria
    pipeline = [
        {"$group": {
            "_id": "$tipo",
            "count": {"$sum": 1},
            "processed_count": {"$sum": {"$cond": ["$processed", 1, 0]}}
        }}
    ]
    
    by_category = {}
    async for doc in db["documents_classified"].aggregate(pipeline):
        by_category[doc["_id"]] = {
            "totale": doc["count"],
            "processati": doc["processed_count"],
            "da_processare": doc["count"] - doc["processed_count"]
        }
    
    # Mapping sezioni gestionale
    gestionale_mapping = {}
    for rule in EMAIL_RULES:
        if rule.category in by_category:
            gestionale_mapping[rule.gestionale_section] = {
                "categoria": rule.category,
                "documenti": by_category[rule.category]["totale"],
                "collection": rule.collection
            }
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "totale_classificati": total_classified,
        "processati": processed,
        "da_processare": total_classified - processed,
        "per_categoria": by_category,
        "mapping_gestionale": gestionale_mapping,
        "regole_attive": len(EMAIL_RULES)
    }


@router.delete("/cleanup-unmatched")
async def cleanup_unmatched_emails(
    cartella: str = Query("INBOX"),
    giorni: int = Query(30),
    confirm: bool = Query(False, description="Conferma eliminazione")
) -> Dict[str, Any]:
    """
    Elimina le email che non corrispondono a nessuna regola.
    
    ATTENZIONE: Operazione irreversibile!
    - Usa confirm=False per preview
    - Usa confirm=True per eliminare effettivamente
    """
    db = Database.get_db()
    
    risultati = await scan_and_classify_emails(
        db=db,
        cartella=cartella,
        giorni=giorni,
        delete_unmatched=confirm,
        dry_run=not confirm
    )
    
    return {
        "mode": "DELETE" if confirm else "PREVIEW",
        "email_da_eliminare": risultati.get("email_non_classificate", 0),
        "email_classificate": risultati.get("email_classificate", 0),
        "eliminati": risultati.get("email_da_eliminare", 0) if confirm else 0,
        "warning": "Le email sono state eliminate!" if confirm else "Usa confirm=true per eliminare"
    }


@router.post("/auto-ripara")
async def auto_ripara_documenti() -> Dict[str, Any]:
    """
    Auto-riparazione documenti classificati.
    - Riprocessa documenti con errori
    - Ricollega documenti orfani
    - Aggiorna associazioni mancanti
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "documenti_verificati": 0,
        "problemi_trovati": 0,
        "correzioni": []
    }
    
    # Trova documenti non processati o con errori
    cursor = db["documents_classified"].find({
        "$or": [
            {"processed": False},
            {"error": {"$exists": True}}
        ]
    })
    
    async for doc in cursor:
        risultati["documenti_verificati"] += 1
        
        # Tenta di riprocessare
        try:
            # Riclassifica per verificare categoria
            rule, confidence = classify_email(
                doc.get("subject", ""),
                doc.get("sender", ""),
                ""
            )
            
            if rule and rule.category != doc.get("tipo"):
                # Categoria cambiata, aggiorna
                await db["documents_classified"].update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "tipo": rule.category,
                        "gestionale_section": rule.gestionale_section,
                        "confidence": confidence,
                        "data_aggiornamento": datetime.now(timezone.utc).isoformat()
                    }}
                )
                risultati["problemi_trovati"] += 1
                risultati["correzioni"].append(f"Riclassificato: {doc.get('filename', 'N/D')} -> {rule.category}")
        
        except Exception as e:
            risultati["correzioni"].append(f"Errore: {str(e)}")
    
    return risultati


# ============================================================
# ENDPOINT ASSOCIAZIONE AUTOMATICA
# ============================================================

@router.post("/associa-tutti")
async def associa_tutti_documenti() -> Dict[str, Any]:
    """
    Associa tutti i documenti classificati alle rispettive sezioni del gestionale.
    Esegue l'azione specificata per ogni categoria.
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "associazioni": {
            "dimissioni": 0,
            "cartelle_esattoriali": 0,
            "verbali": 0,
            "bonifici": 0,
            "altri": 0
        },
        "errori": [],
        "dettagli": []
    }
    
    # Processa documenti non ancora processati
    cursor = db["documents_classified"].find({"processed": False})
    
    async for doc in cursor:
        try:
            categoria = doc.get("tipo")
            subject = doc.get("subject", "")
            filename = doc.get("filename", "")
            
            associato = False
            
            if categoria == "dimissioni":
                # Estrai CF e associa a dipendente
                import re
                match = re.search(r'([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])', (subject + filename).upper())
                if match:
                    cf = match.group(1)
                    dipendente = await db["dipendenti"].find_one({"codice_fiscale": cf})
                    if dipendente:
                        await db["dipendenti"].update_one(
                            {"_id": dipendente["_id"]},
                            {"$set": {"stato": "dimesso", "documento_dimissioni": filename}}
                        )
                        risultati["associazioni"]["dimissioni"] += 1
                        risultati["dettagli"].append(f"Dimissioni: {cf} -> {dipendente.get('cognome', '')}")
                        associato = True
            
            elif categoria == "cartelle_esattoriali":
                # Salva per commercialista
                import re
                match = re.search(r'([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])', (subject + filename).upper())
                cf = match.group(1) if match else None
                
                # Cerca anche P.IVA
                if not cf:
                    match_piva = re.search(r'\b(\d{11})\b', subject + filename)
                    cf = match_piva.group(1) if match_piva else "SCONOSCIUTO"
                
                if cf:
                    await db["documenti_commercialista"].update_one(
                        {"codice_fiscale": cf, "tipo": "cartella_esattoriale"},
                        {
                            "$setOnInsert": {"data_inserimento": datetime.now(timezone.utc).isoformat()},
                            "$push": {"documenti": {"filename": filename, "subject": subject}}
                        },
                        upsert=True
                    )
                    risultati["associazioni"]["cartelle_esattoriali"] += 1
                    associato = True
            
            elif categoria == "verbali":
                # Associa a fatture noleggio
                import re
                match = re.search(r'B(\d{10,})', subject + filename)
                if match:
                    numero_verbale = "B" + match.group(1)
                    # Cerca fattura noleggio corrispondente
                    fattura = await db["invoices"].find_one({
                        "descrizione_linee": {"$regex": numero_verbale, "$options": "i"}
                    })
                    if fattura:
                        await db["verbali_noleggio"].update_one(
                            {"numero_verbale": numero_verbale},
                            {
                                "$set": {
                                    "fattura_id": str(fattura["_id"]),
                                    "associato": True
                                }
                            },
                            upsert=True
                        )
                        risultati["associazioni"]["verbali"] += 1
                        associato = True
            
            # Marca come processato
            if associato:
                await db["documents_classified"].update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"processed": True, "data_processamento": datetime.now(timezone.utc).isoformat()}}
                )
            else:
                risultati["associazioni"]["altri"] += 1
                
        except Exception as e:
            risultati["errori"].append(f"Errore: {str(e)}")
    
    return risultati



# ============================================================
# ENDPOINT VISUALIZZAZIONE PDF
# ============================================================


@router.get("/view/{document_id}")
async def view_document_pdf(document_id: str):
    """
    Visualizza o scarica il PDF di un documento classificato.
    """
    db = Database.get_db()
    
    # Cerca il documento
    from bson import ObjectId
    from bson.errors import InvalidId
    try:
        doc = await db["documents_classified"].find_one({"_id": ObjectId(document_id)})
    except Exception:
        doc = await db["documents_classified"].find_one({"id": document_id})
    
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    # Architettura MongoDB-only: usa pdf_data
    pdf_data = doc.get("pdf_data") or doc.get("file_data")
    filename = doc.get("filename", "document.pdf")
    
    if pdf_data:
        import base64
        content = base64.b64decode(pdf_data)
        
        # Determina content type
        if filename.lower().endswith('.pdf'):
            media_type = "application/pdf"
        elif filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            media_type = "image/png" if filename.lower().endswith('.png') else "image/jpeg"
        elif filename.lower().endswith('.xml'):
            media_type = "application/xml"
        else:
            media_type = "application/octet-stream"
        
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{filename}"'}
        )
    
    raise HTTPException(status_code=404, detail=f"File non disponibile in MongoDB: {filename}")


@router.get("/download/{document_id}")
async def download_document(document_id: str):
    """
    Scarica un documento classificato.
    Architettura MongoDB-only: usa pdf_data.
    """
    db = Database.get_db()
    
    from bson import ObjectId
    from bson.errors import InvalidId
    try:
        doc = await db["documents_classified"].find_one({"_id": ObjectId(document_id)})
    except Exception:
        doc = await db["documents_classified"].find_one({"id": document_id})
    
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    pdf_data = doc.get("pdf_data") or doc.get("file_data")
    filename = doc.get("filename", "document")
    
    if not pdf_data:
        raise HTTPException(status_code=404, detail="File non disponibile in MongoDB")
    
    import base64
    content = base64.b64decode(pdf_data)
    
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

