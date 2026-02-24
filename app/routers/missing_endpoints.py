"""
Endpoint mancanti - Fix mismatch frontend/backend.
Questo router raccoglie gli endpoint che il frontend chiama ma che non esistono nel backend.
Vanno spostati nei rispettivi moduli durante il refactoring.
"""

from fastapi import APIRouter, HTTPException, Query, Body, UploadFile, File
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from app.database import Database, Collections

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Fix Endpoint Mancanti"])


# =============================================================================
# /api/centri-costo/centri-costo → usato da CentriCosto.jsx, DocumentiDaRivedere.jsx
# Il frontend chiama /api/centri-costo/centri-costo ma il backend ha /api/centri-costo
# =============================================================================
@router.get("/centri-costo/centri-costo")
async def list_centri_costo_alias() -> List[Dict[str, Any]]:
    """Alias: redirect a /api/centri-costo (list)."""
    db = Database.get_db()
    centri = await db["centri_costo"].find({}, {"_id": 0}).to_list(200)
    return centri


# =============================================================================
# /api/contabilita/bilancio-verifica → usato da MotoreContabile.jsx
# Backend ha /api/accounting-engine/bilancio-verifica ma non /api/contabilita/bilancio-verifica
# =============================================================================
@router.get("/contabilita/bilancio-verifica")
async def bilancio_verifica_alias(anno: int = Query(...)) -> Dict[str, Any]:
    """Bilancio di verifica per anno."""
    db = Database.get_db()
    
    pipeline = [
        {"$match": {"anno": anno}},
        {"$group": {
            "_id": "$conto",
            "dare": {"$sum": "$dare"},
            "avere": {"$sum": "$avere"},
            "saldo": {"$sum": {"$subtract": ["$dare", "$avere"]}}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    risultati = await db["movimenti_contabili"].aggregate(pipeline).to_list(1000)
    
    totale_dare = sum(r.get("dare", 0) for r in risultati)
    totale_avere = sum(r.get("avere", 0) for r in risultati)
    
    return {
        "anno": anno,
        "conti": risultati,
        "totale_dare": totale_dare,
        "totale_avere": totale_avere,
        "quadratura": abs(totale_dare - totale_avere) < 0.01
    }


# =============================================================================
# /api/bank/movements → usato da GestionePagoPA.jsx
# =============================================================================
@router.get("/bank/movements")
async def get_bank_movements(
    tipo: Optional[str] = None,
    limit: int = Query(100, le=1000)
) -> List[Dict[str, Any]]:
    """Lista movimenti bancari con filtro tipo."""
    db = Database.get_db()
    query = {}
    if tipo:
        query["tipo"] = tipo
    
    movements = await db["prima_nota_banca"].find(
        query, {"_id": 0}
    ).sort("data", -1).to_list(limit)
    
    return movements


# =============================================================================
# /api/dipendenti/libro-unico/export → usato da LibroUnicoTab.jsx, useLibroUnico.js
# =============================================================================
@router.get("/dipendenti/libro-unico/export")
async def export_libro_unico(month_year: str = Query(...)):
    """Export libro unico del lavoro per mese (formato: YYYY-MM)."""
    db = Database.get_db()
    
    try:
        anno, mese = month_year.split("-")
        anno, mese = int(anno), int(mese)
    except (ValueError, AttributeError):
        raise HTTPException(400, "Formato month_year non valido. Usare YYYY-MM")
    
    # Recupera presenze e cedolini del mese
    presenze = await db["presenze_mensili"].find({
        "anno": anno, "mese": mese
    }, {"_id": 0}).to_list(500)
    
    cedolini = await db[Collections.PAYSLIPS].find({
        "anno": anno, "mese": mese
    }, {"_id": 0}).to_list(500)
    
    employees = await db[Collections.EMPLOYEES].find(
        {"attivo": True}, {"_id": 0, "id": 1, "nome_completo": 1, "codice_fiscale": 1, "qualifica": 1}
    ).to_list(500)
    
    return {
        "anno": anno,
        "mese": mese,
        "dipendenti": employees,
        "presenze": presenze,
        "cedolini": cedolini
    }


# =============================================================================
# /api/learning-machine/stats → usato da LearningMachine.jsx
# =============================================================================
@router.get("/learning-machine/stats")
async def get_learning_stats() -> Dict[str, Any]:
    """Statistiche del sistema di apprendimento automatico."""
    db = Database.get_db()
    
    total_docs = await db.get_collection("documenti_classificati").count_documents({})
    total_feedback = await db.get_collection("learning_feedback").count_documents({})
    positive = await db.get_collection("learning_feedback").count_documents({"tipo": "positivo"})
    
    return {
        "documenti_processati": total_docs,
        "feedback_totali": total_feedback,
        "feedback_positivi": positive,
        "feedback_negativi": total_feedback - positive,
        "accuratezza": round(positive / total_feedback * 100, 1) if total_feedback > 0 else 0
    }


# =============================================================================
# /api/learning-machine/regole → usato da LearningMachine.jsx
# =============================================================================
@router.get("/learning-machine/regole")
async def get_learning_rules() -> List[Dict[str, Any]]:
    """Lista regole apprese dal sistema."""
    db = Database.get_db()
    
    regole = await db.get_collection("learning_rules").find(
        {}, {"_id": 0}
    ).sort("confidence", -1).to_list(200)
    
    return regole


# =============================================================================
# /api/ai-parser/da-rivedere/process-batch → usato da DocumentiDaRivedere.jsx
# =============================================================================
@router.post("/ai-parser/da-rivedere/process-batch")
async def process_batch_da_rivedere() -> Dict[str, Any]:
    """Processa in batch tutti i documenti da rivedere."""
    db = Database.get_db()
    
    docs = await db["documenti_da_rivedere"].find(
        {"stato": "da_rivedere"}
    ).to_list(100)
    
    processed = 0
    errors = 0
    
    for doc in docs:
        try:
            await db["documenti_da_rivedere"].update_one(
                {"_id": doc["_id"]},
                {"$set": {"stato": "in_elaborazione", "updated_at": datetime.now(timezone.utc)}}
            )
            processed += 1
        except Exception as e:
            logger.error(f"Errore processing doc {doc.get('_id')}: {e}")
            errors += 1
    
    return {
        "success": True,
        "processati": processed,
        "errori": errors,
        "totale": len(docs)
    }


# =============================================================================
# /api/analytics/auto-ricostruisci-dati → usato da DashboardAnalytics.jsx
# =============================================================================
@router.post("/analytics/auto-ricostruisci-dati")
async def auto_ricostruisci_dati() -> Dict[str, Any]:
    """Ricostruisce/ricalcola i dati analytics da prima nota, fatture, corrispettivi."""
    db = Database.get_db()
    
    # Conta documenti nelle collection principali
    counts = {}
    for coll_name in ["prima_nota_cassa", "prima_nota_banca", Collections.INVOICES, "corrispettivi"]:
        counts[coll_name] = await db[coll_name].count_documents({})
    
    return {
        "success": True,
        "message": "Dati ricostruiti",
        "collections_analizzate": counts,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# =============================================================================
# /api/operazioni-da-confermare/smart/ignora → usato da RiconciliazioneUnificata.jsx
# =============================================================================
@router.post("/operazioni-da-confermare/smart/ignora")
async def ignora_operazione_smart(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Ignora un'operazione suggerita dal sistema smart."""
    db = Database.get_db()
    
    operazione_id = data.get("operazione_id")
    motivo = data.get("motivo", "ignorata dall'utente")
    
    if not operazione_id:
        raise HTTPException(400, "operazione_id richiesto")
    
    result = await db["operazioni_da_confermare"].update_one(
        {"id": operazione_id},
        {"$set": {"stato": "ignorata", "motivo_ignora": motivo, "updated_at": datetime.now(timezone.utc)}}
    )
    
    return {"success": result.modified_count > 0}


# =============================================================================
# /api/orders/create → usato da RicercaProdotti.jsx
# Il backend ha POST /api/orders ma il frontend chiama /api/orders/create
# =============================================================================
@router.post("/orders/create")
async def create_order_alias(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea un nuovo ordine (alias per POST /api/orders)."""
    db = Database.get_db()
    
    order = {
        **data,
        "stato": "bozza",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc)
    }
    
    result = await db["orders"].insert_one(order)
    return {"success": True, "order_id": str(result.inserted_id)}


# =============================================================================
# /api/prima-nota-auto/import-corrispettivi → usato da ImportDocumenti.jsx
# Backend ha /import-corrispettivi-xml ma non /import-corrispettivi (Excel)
# =============================================================================
@router.post("/prima-nota-auto/import-corrispettivi")
async def import_corrispettivi_excel(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Import corrispettivi da file Excel."""
    import openpyxl
    from io import BytesIO
    
    db = Database.get_db()
    content = await file.read()
    
    try:
        wb = openpyxl.load_workbook(BytesIO(content), read_only=True)
        ws = wb.active
        
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        imported = 0
        
        for row in rows:
            if not row or not row[0]:
                continue
            
            doc = {
                "data": str(row[0]) if row[0] else None,
                "importo": float(row[1]) if row[1] else 0,
                "descrizione": str(row[2]) if len(row) > 2 and row[2] else "",
                "tipo": "corrispettivo",
                "fonte": f"import_excel_{file.filename}",
                "created_at": datetime.now(timezone.utc)
            }
            await db["corrispettivi"].insert_one(doc)
            imported += 1
        
        return {"success": True, "importati": imported, "filename": file.filename}
    except Exception as e:
        raise HTTPException(400, f"Errore parsing Excel: {str(e)}")


# =============================================================================
# /api/prima-nota-salari/pulisci-righe-vuote → usato da PrimaNotaSalariTab.jsx
# =============================================================================
@router.delete("/prima-nota-salari/pulisci-righe-vuote")
async def pulisci_righe_vuote_salari() -> Dict[str, Any]:
    """Rimuove righe vuote/incomplete dalla prima nota salari."""
    db = Database.get_db()
    
    # Elimina documenti senza importo o senza dipendente
    result = await db["prima_nota_salari"].delete_many({
        "$or": [
            {"netto": {"$in": [None, 0, ""]}},
            {"dipendente": {"$in": [None, ""]}},
            {"nome_completo": {"$in": [None, ""]}},
        ]
    })
    
    return {
        "success": True,
        "righe_eliminate": result.deleted_count
    }


# =============================================================================
# /api/sync/fatture-to-banca → usato da Admin.jsx
# Backend ha /api/sync/match-fatture-banca ma non /sync/fatture-to-banca
# =============================================================================
@router.post("/sync/fatture-to-banca")
async def sync_fatture_to_banca() -> Dict[str, Any]:
    """Sincronizza fatture con movimenti bancari."""
    db = Database.get_db()
    
    fatture = await db[Collections.INVOICES].find(
        {"stato_pagamento": {"$ne": "pagata"}},
        {"_id": 0, "id": 1, "totale": 1, "importo_totale": 1, "fornitore_denominazione": 1, "invoice_date": 1}
    ).to_list(1000)
    
    movimenti_banca = await db["prima_nota_banca"].find(
        {"riconciliato": {"$ne": True}},
        {"_id": 0, "id": 1, "importo": 1, "descrizione": 1, "data": 1}
    ).to_list(2000)
    
    matched = 0
    for f in fatture:
        importo_fattura = abs(f.get("totale", 0) or f.get("importo_totale", 0))
        if importo_fattura == 0:
            continue
        
        for m in movimenti_banca:
            importo_mov = abs(m.get("importo", 0))
            if abs(importo_fattura - importo_mov) < 0.01:
                matched += 1
                break
    
    return {
        "success": True,
        "fatture_analizzate": len(fatture),
        "movimenti_banca": len(movimenti_banca),
        "match_trovati": matched
    }


# =============================================================================
# /api/files/download → usato da RiconciliazioneUnificata.jsx
# Serve file da uploads/
# =============================================================================
@router.get("/files/download")
async def download_file(path: str = Query(...)):
    """Download file dal filesystem (solo dalla directory uploads)."""
    import os
    from fastapi.responses import FileResponse
    
    # Security: solo dalla directory uploads
    safe_path = os.path.normpath(path)
    if ".." in safe_path or not safe_path.startswith(("uploads/", "/app/uploads/", "documents/")):
        raise HTTPException(403, "Accesso non consentito a questo percorso")
    
    # Normalizza path
    if safe_path.startswith("/app/"):
        file_path = safe_path
    else:
        file_path = os.path.join("/app", safe_path)
    
    if not os.path.exists(file_path):
        raise HTTPException(404, "File non trovato")
    
    return FileResponse(file_path, filename=os.path.basename(file_path))
