"""
F24 Public Router - Endpoints F24 senza autenticazione
NOTA: Usa f24_commercialista come collezione unica per F24
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Body, Query
from fastapi.responses import Response
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
import logging
import base64

from app.database import Database
from app.db_collections import COLL_F24
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

# Collezione F24 unica
F24_COLLECTION = COLL_F24  # "f24_commercialista"


@router.get("/test")
@handle_errors
async def test_route():
    """Test route."""
    return {"status": "ok"}


@router.get("/models")
@handle_errors
async def list_f24_models(anno: int = None) -> Dict[str, Any]:
    """Lista tutti i modelli F24 - unifica quietanze e f24_unificato."""
    import time
    logger.info(f"=== /models endpoint called (anno={anno}) ===")
    t_start = time.time()
    
    db = Database.get_db()
    
    try:
        # Primary: quietanze_f24 (ha dati completi con pagamenti reali)
        q_filter = {}
        if anno:
            q_filter["data_pagamento"] = {"$regex": f"^{anno}"}
        quietanze = await db["quietanze_f24"].find(
            q_filter,
            {"_id": 0, "pdf_data": 0}
        ).sort("created_at", -1).to_list(500)
        
        # Secondary: f24_unificato (per eventuali F24 non ancora pagati)
        u_filter = {"status": {"$ne": "eliminato"}}
        if anno:
            u_filter["$or"] = [
                {"data_pagamento": {"$regex": f"^{anno}"}},
                {"data_versamento": {"$regex": f"^{anno}"}},
            ]
        f24_uni = await db[F24_COLLECTION].find(
            u_filter,
            {"_id": 0, "pdf_data": 0}
        ).sort("created_at", -1).to_list(100)
        
        # Trasforma quietanze nel formato atteso dal frontend
        f24s = []
        seen_ids = set()
        
        for q in quietanze:
            dati = q.get("dati_generali", {})
            totali = q.get("totali", {})
            data_pag = q.get("data_pagamento") or dati.get("data_pagamento")
            saldo = q.get("saldo", 0) or totali.get("saldo_netto", 0) or totali.get("totale_debito", 0)
            qid = q.get("id", "")
            if qid in seen_ids:
                continue
            seen_ids.add(qid)
            
            f24s.append({
                "id": qid,
                "tipo_modello": "F24",
                "anno": int(data_pag[:4]) if data_pag and len(data_pag) >= 4 else None,
                "data_scadenza": data_pag,
                "data_versamento": data_pag,
                "saldo_finale": saldo,
                "pagato": True,
                "contribuente": dati.get("ragione_sociale", dati.get("codice_fiscale", q.get("codice_fiscale", ""))),
                "file_name": q.get("filename"),
                "status": "pagato",
                "protocollo": q.get("protocollo_telematico", ""),
                "tributi_erario": q.get("sezione_erario", []),
                "tributi_inps": q.get("sezione_inps", []),
                "tributi_regioni": q.get("sezione_regioni", []),
                "tributi_imu": q.get("sezione_tributi_locali", []),
                "totale_debito": totali.get("totale_debito", 0),
                "totale_credito": totali.get("totale_credito", 0),
                "source": "quietanza"
            })
        
        # Aggiungi f24_unificato (solo quelli non presenti)
        for f in f24_uni:
            fid = f.get("id", "")
            if fid in seen_ids:
                continue
            seen_ids.add(fid)
            totali = f.get("totali", {})
            dati = f.get("dati_generali", {})
            data_vers = f.get("data_versamento") or f.get("data_pagamento") or dati.get("data_versamento")
            saldo = f.get("totale_versato", 0) or totali.get("saldo_netto", 0) or 0
            
            if not data_vers and not saldo:
                continue  # Skip documenti completamente vuoti
            
            f24s.append({
                "id": fid,
                "tipo_modello": "F24",
                "anno": int(data_vers[:4]) if data_vers and len(data_vers) >= 4 else None,
                "data_scadenza": data_vers,
                "data_versamento": data_vers,
                "saldo_finale": saldo,
                "pagato": f.get("status") == "pagato",
                "contribuente": dati.get("ragione_sociale", dati.get("codice_fiscale", f.get("codice_fiscale", ""))),
                "file_name": f.get("filename") or f.get("file_name"),
                "status": f.get("status"),
                "source": "f24_unificato"
            })
        
        # Sort by date desc
        f24s.sort(key=lambda x: x.get("data_scadenza") or "", reverse=True)
        
        logger.info(f"F24 models query took {time.time() - t_start:.2f}s for {len(f24s)} items (quietanze: {len(quietanze)}, f24_uni: {len(f24_uni)})")
    except Exception as e:
        logger.error(f"F24 models query error: {e}")
        f24s = []
    
    return {
        "f24s": f24s,
        "count": len(f24s),
        "totale_da_pagare": sum(f.get("saldo_finale", 0) or 0 for f in f24s if not f.get("pagato")),
        "totale_pagato": sum(f.get("saldo_finale", 0) or 0 for f in f24s if f.get("pagato"))
    }


@router.get("/scadenze-prossime")
@handle_errors
async def get_scadenze_prossime_public(
    giorni: int = 60,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Get upcoming F24 deadlines for the dashboard widget (public, no auth).
    Returns the next F24s sorted by due date with summary info.
    """
    from datetime import timezone
    
    db = Database.get_db()
    today = datetime.now(timezone.utc).date()
    
    scadenze = []
    totale_importo = 0
    
    # Get unpaid F24s dalla collezione unificata
    f24_list = await db[F24_COLLECTION].find(
        {"status": {"$nin": ["pagato", "eliminato"]}},
        {"_id": 0}
    ).to_list(500)
    
    for f24 in f24_list:
        try:
            dati = f24.get("dati_generali", {})
            totali = f24.get("totali", {})
            
            scadenza_str = dati.get("data_scadenza")
            if not scadenza_str:
                # Usa created_at come fallback
                scadenza_str = f24.get("created_at", "")[:10] if f24.get("created_at") else None
                if not scadenza_str:
                    continue
            
            if isinstance(scadenza_str, str):
                scadenza_str = scadenza_str.replace("Z", "+00:00")
                if "T" in scadenza_str:
                    scadenza = datetime.fromisoformat(scadenza_str).date()
                else:
                    try:
                        scadenza = datetime.strptime(scadenza_str, "%d/%m/%Y").date()
                    except ValueError:
                        try:
                            scadenza = datetime.strptime(scadenza_str[:10], "%Y-%m-%d").date()
                        except Exception:
                            continue
            elif isinstance(scadenza_str, datetime):
                scadenza = scadenza_str.date()
            else:
                continue
            
            giorni_mancanti = (scadenza - today).days
            
            if giorni_mancanti <= giorni:
                importo = float(totali.get("saldo_netto", 0) or 0)
                totale_importo += importo
                
                # Determina tipo dal primo codice tributo
                tipo_display = "F24"
                sezione_erario = f24.get("sezione_erario", [])
                if sezione_erario and len(sezione_erario) > 0:
                    first_code = sezione_erario[0].get("codice_tributo", "")
                    if first_code.startswith("60"):
                        tipo_display = "IVA"
                    elif first_code.startswith("10"):
                        tipo_display = "IRPEF"
                
                scadenze.append({
                    "id": f24.get("id"),
                    "tipo": tipo_display,
                    "descrizione": dati.get("ragione_sociale", f24.get("file_name", "")),
                    "importo": importo,
                    "data_scadenza": scadenza.isoformat(),
                    "giorni_mancanti": giorni_mancanti
                })
        except Exception:
            continue
    
    # Sort by date (closest first)
    scadenze.sort(key=lambda x: x["giorni_mancanti"])
    
    return {
        "scadenze": scadenze[:limit],
        "totale": len(scadenze),
        "totale_importo": totale_importo
    }


@router.post("/upload")
@handle_errors
async def upload_f24_pdf(
    file: UploadFile = File(..., description="File PDF F24")
) -> Dict[str, Any]:
    """
    Carica PDF F24 ed estrae automaticamente i dati.
    
    **Supporta:**
    - F24 Ordinario
    - F24 Semplificato
    - F24 contributi INPS
    
    Estrae: codice tributo, importo, periodo riferimento, scadenza
    Usa parser basato su coordinate PyMuPDF per maggiore affidabilità.
    """
    import tempfile
    import os
    from app.services.parser_f24 import parse_f24_commercialista
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Solo file PDF supportati")
    
    pdf_bytes = await file.read()
    
    # Salva temporaneamente il PDF per il parser
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
        tmp_file.write(pdf_bytes)
        tmp_path = tmp_file.name
    
    try:
        # Parse PDF usando il parser robusto basato su coordinate
        parsed = parse_f24_commercialista(tmp_path)
    finally:
        # Rimuovi file temporaneo
        os.unlink(tmp_path)
    
    if "error" in parsed and parsed["error"]:
        return {
            "success": False,
            "error": parsed["error"],
            "filename": file.filename
        }
    
    # Get database
    db = Database.get_db()
    
    # Convert data_versamento to data_scadenza
    data_scadenza = parsed.get("dati_generali", {}).get("data_versamento")
    
    # Converti formato tributi per compatibilità con frontend
    tributi_erario = []
    for t in parsed.get("sezione_erario", []):
        tributi_erario.append({
            "codice_tributo": t.get("codice_tributo"),
            "codice": t.get("codice_tributo"),
            "rateazione": t.get("rateazione", ""),
            "periodo_riferimento": t.get("periodo_riferimento", ""),
            "anno_riferimento": t.get("anno", ""),
            "anno": t.get("anno", ""),
            "mese": t.get("mese", ""),
            "importo_debito": t.get("importo_debito", 0),
            "importo_credito": t.get("importo_credito", 0),
            "importo": t.get("importo_debito", 0),
            "descrizione": t.get("descrizione", ""),
            "riferimento": t.get("periodo_riferimento", "")
        })
    
    tributi_inps = []
    for t in parsed.get("sezione_inps", []):
        tributi_inps.append({
            "codice_sede": t.get("codice_sede", ""),
            "causale": t.get("causale", ""),
            "causale_contributo": t.get("causale", ""),
            "matricola": t.get("matricola", ""),
            "periodo_da": t.get("mese", ""),
            "periodo_a": t.get("anno", ""),
            "periodo_riferimento": t.get("periodo_riferimento", ""),
            "importo_debito": t.get("importo_debito", 0),
            "importo_credito": t.get("importo_credito", 0),
            "importo": t.get("importo_debito", 0),
            "descrizione": t.get("descrizione", "")
        })
    
    tributi_regioni = []
    for t in parsed.get("sezione_regioni", []):
        tributi_regioni.append({
            "codice_tributo": t.get("codice_tributo"),
            "codice": t.get("codice_tributo"),
            "codice_regione": t.get("codice_regione", ""),
            "codice_ente": t.get("codice_regione", ""),
            "periodo_riferimento": t.get("periodo_riferimento", ""),
            "importo_debito": t.get("importo_debito", 0),
            "importo_credito": t.get("importo_credito", 0),
            "importo": t.get("importo_debito", 0),
            "descrizione": t.get("descrizione", "")
        })
    
    tributi_imu = []
    for t in parsed.get("sezione_tributi_locali", []):
        tributi_imu.append({
            "codice_tributo": t.get("codice_tributo"),
            "codice": t.get("codice_tributo"),
            "codice_comune": t.get("codice_comune", ""),
            "codice_ente": t.get("codice_comune", ""),
            "periodo_riferimento": t.get("periodo_riferimento", ""),
            "importo_debito": t.get("importo_debito", 0),
            "importo_credito": t.get("importo_credito", 0),
            "importo": t.get("importo_debito", 0),
            "descrizione": t.get("descrizione", "")
        })
    
    # Aggiungi anche INAIL se presente
    for t in parsed.get("sezione_inail", []):
        tributi_inps.append({
            "codice_sede": t.get("codice_sede", ""),
            "causale": "INAIL",
            "causale_contributo": t.get("causale", "INAIL"),
            "matricola": t.get("codice_ditta", ""),
            "periodo_da": "",
            "periodo_a": "",
            "periodo_riferimento": t.get("numero_riferimento", ""),
            "importo_debito": t.get("importo_debito", 0),
            "importo_credito": t.get("importo_credito", 0),
            "importo": t.get("importo_debito", 0),
            "descrizione": t.get("descrizione", "")
        })
    
    totali = parsed.get("totali", {})
    
    # Create F24 record
    f24_id = str(uuid.uuid4())
    f24_record = {
        "id": f24_id,
        "data_scadenza": data_scadenza,
        "scadenza_display": data_scadenza,
        "codice_fiscale": parsed.get("dati_generali", {}).get("codice_fiscale"),
        "contribuente": parsed.get("dati_generali", {}).get("ragione_sociale"),
        "banca": parsed.get("dati_generali", {}).get("banca"),
        "tipo_f24": parsed.get("dati_generali", {}).get("tipo_f24", "F24"),
        "tributi_erario": tributi_erario,
        "tributi_inps": tributi_inps,
        "tributi_regioni": tributi_regioni,
        "tributi_imu": tributi_imu,
        "totale_debito": totali.get("totale_debito", 0),
        "totale_credito": totali.get("totale_credito", 0),
        "saldo_finale": totali.get("saldo_finale", 0),
        "has_ravvedimento": parsed.get("has_ravvedimento", False),
        "pagato": False,
        "filename": file.filename,
        "pdf_data": base64.b64encode(pdf_bytes).decode('utf-8'),
        "source": "pdf_upload",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Check for duplicates nella collezione unificata
    existing = await db[F24_COLLECTION].find_one({
        "$or": [
            {"dati_generali.data_scadenza": data_scadenza, "totali.saldo_netto": totali.get("saldo_finale", 0)},
            {"file_name": file.filename}
        ]
    })
    
    if existing:
        raise HTTPException(status_code=409, detail="F24 già presente nel sistema")
    
    # Converto al formato f24_commercialista
    f24_doc = {
        "id": f24_id,
        "f24_key": f"{parsed.get('dati_generali', {}).get('codice_fiscale', '')}_{data_scadenza}",
        "file_name": file.filename,
        "file_path": None,  # PDF in memoria
        "dati_generali": parsed.get("dati_generali", {}),
        "sezione_erario": parsed.get("sezione_erario", []),
        "sezione_inps": parsed.get("sezione_inps", []),
        "sezione_regioni": parsed.get("sezione_regioni", []),
        "sezione_tributi_locali": parsed.get("sezione_tributi_locali", []),
        "sezione_inail": parsed.get("sezione_inail", []),
        "totali": totali,
        "has_ravvedimento": parsed.get("has_ravvedimento", False),
        "status": "da_pagare",
        "riconciliato": False,
        "pdf_data": base64.b64encode(pdf_bytes).decode('utf-8'),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Insert into database
    await db[F24_COLLECTION].insert_one(f24_doc.copy())
    
    logger.info(f"F24 importato: {f24_id} - Scadenza {data_scadenza} - €{totali.get('saldo_finale', 0):.2f}")
    
    return {
        "success": True,
        "id": f24_id,
        "scadenza": data_scadenza,
        "contribuente": parsed.get("dati_generali", {}).get("ragione_sociale"),
        "saldo_finale": totali.get("saldo_finale", 0),
        "tributi": {
            "erario": len(tributi_erario),
            "inps": len(tributi_inps),
            "regioni": len(tributi_regioni),
            "imu": len(tributi_imu)
        },
        "filename": file.filename
    }


@router.get("/pdf/{f24_id}")
@handle_errors
async def get_f24_pdf(f24_id: str):
    """Restituisce il PDF originale dell'F24."""
    db = Database.get_db()
    
    f24 = await db[F24_COLLECTION].find_one({"id": f24_id})
    
    if not f24:
        raise HTTPException(status_code=404, detail="F24 non trovato")
    
    # Architettura MongoDB-only: cerca PDF solo in pdf_data
    pdf_data = f24.get("pdf_data")
    filename = f24.get("file_name", f24.get("filename", f"F24_{f24_id}.pdf"))
    pdf_bytes = None
    
    if pdf_data:
        pdf_bytes = base64.b64decode(pdf_data)
    
    # Se non trovato, cerca in f24_models (collezione legacy con pdf_data)
    if not pdf_bytes and filename:
        models_doc = await db["f24_unificato"].find_one(
            {"filename": filename},
            {"pdf_data": 1}
        )
        if models_doc and models_doc.get("pdf_data"):
            pdf_bytes = base64.b64decode(models_doc["pdf_data"])
            # Copia pdf_data nella collezione principale per le prossime volte
            await db[F24_COLLECTION].update_one(
                {"id": f24_id},
                {"$set": {"pdf_data": models_doc["pdf_data"]}}
            )
            logger.info(f"PDF F24 recuperato da f24_models e copiato in f24_commercialista: {filename}")
    
    # Se ancora non trovato, cerca in documents_inbox
    if not pdf_bytes and filename:
        inbox_doc = await db["documents_inbox"].find_one(
            {"filename": filename},
            {"content": 1, "content_base64": 1}
        )
        if inbox_doc:
            content = inbox_doc.get("content") or inbox_doc.get("content_base64")
            if content:
                if isinstance(content, bytes):
                    pdf_bytes = content
                else:
                    pdf_bytes = base64.b64decode(content)
                # Salva pdf_data per le prossime volte
                await db[F24_COLLECTION].update_one(
                    {"id": f24_id},
                    {"$set": {"pdf_data": base64.b64encode(pdf_bytes).decode('utf-8')}}
                )
    
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="PDF non disponibile per questo F24")
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"'
        }
    )


@router.put("/models/{f24_id}/pagato")
@handle_errors
async def mark_f24_pagato(f24_id: str) -> Dict[str, str]:
    """Segna un F24 come pagato."""
    db = Database.get_db()
    
    result = await db[F24_COLLECTION].update_one(
        {"id": f24_id},
        {"$set": {"status": "pagato", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="F24 non trovato")
    
    return {"message": "F24 segnato come pagato", "id": f24_id}


@router.put("/models/{f24_id}")
@handle_errors
async def update_f24_model(f24_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiorna un modello F24."""
    db = Database.get_db()
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    # Campi modificabili (mappo al nuovo schema)
    if "data_scadenza" in data:
        update_data["dati_generali.data_scadenza"] = data["data_scadenza"]
    if "contribuente" in data:
        update_data["dati_generali.ragione_sociale"] = data["contribuente"]
    if "pagato" in data:
        update_data["status"] = "pagato" if data["pagato"] else "da_pagare"
    if "note" in data:
        update_data["note"] = data["note"]
    if "saldo_finale" in data:
        update_data["totali.saldo_netto"] = data["saldo_finale"]
    
    result = await db[F24_COLLECTION].update_one(
        {"id": f24_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="F24 non trovato")
    
    return {"message": "F24 aggiornato", "id": f24_id}


@router.delete("/models/{f24_id}")
@handle_errors
async def delete_f24_model(f24_id: str) -> Dict[str, str]:
    """Elimina un modello F24 (soft delete)."""
    db = Database.get_db()
    
    # Soft delete invece di hard delete
    result = await db[F24_COLLECTION].update_one(
        {"id": f24_id},
        {"$set": {"status": "eliminato", "eliminato_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="F24 non trovato")
    
    return {"message": "F24 eliminato", "id": f24_id}


@router.post("/upload-overwrite")
@handle_errors
async def upload_f24_pdf_overwrite(
    file: UploadFile = File(..., description="File PDF F24"),
    overwrite: bool = Query(False, description="Sovrascrivi se esiste")
) -> Dict[str, Any]:
    """
    Carica PDF F24 con opzione sovrascrivi.
    Se overwrite=True, sostituisce F24 esistenti con stessa scadenza/importo.
    Usa parser basato su coordinate PyMuPDF per maggiore affidabilità.
    """
    import tempfile
    import os
    from app.services.parser_f24 import parse_f24_commercialista
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Solo file PDF supportati")
    
    pdf_bytes = await file.read()
    
    # Salva temporaneamente il PDF per il parser
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
        tmp_file.write(pdf_bytes)
        tmp_path = tmp_file.name
    
    try:
        parsed = parse_f24_commercialista(tmp_path)
    finally:
        os.unlink(tmp_path)
    
    if "error" in parsed and parsed["error"]:
        return {
            "success": False,
            "error": parsed["error"],
            "filename": file.filename
        }
    
    db = Database.get_db()
    
    # Convert data_versamento to data_scadenza
    data_scadenza = parsed.get("dati_generali", {}).get("data_versamento")
    totali = parsed.get("totali", {})
    
    # Check for existing nella collezione unificata
    existing = await db[F24_COLLECTION].find_one({
        "$or": [
            {"dati_generali.data_scadenza": data_scadenza, "totali.saldo_netto": totali.get("saldo_finale", 0)},
            {"file_name": file.filename}
        ]
    })
    
    if existing and not overwrite:
        return {
            "success": False,
            "error": "F24 già presente. Usa overwrite=True per sovrascrivere.",
            "existing_id": existing.get("id"),
            "filename": file.filename
        }
    
    f24_id = existing.get("id") if existing else str(uuid.uuid4())
    
    # Converti formato tributi per compatibilità con frontend
    tributi_erario = []
    for t in parsed.get("sezione_erario", []):
        tributi_erario.append({
            "codice_tributo": t.get("codice_tributo"),
            "codice": t.get("codice_tributo"),
            "rateazione": t.get("rateazione", ""),
            "periodo_riferimento": t.get("periodo_riferimento", ""),
            "anno_riferimento": t.get("anno", ""),
            "anno": t.get("anno", ""),
            "mese": t.get("mese", ""),
            "importo_debito": t.get("importo_debito", 0),
            "importo_credito": t.get("importo_credito", 0),
            "importo": t.get("importo_debito", 0),
            "descrizione": t.get("descrizione", ""),
            "riferimento": t.get("periodo_riferimento", "")
        })
    
    tributi_inps = []
    for t in parsed.get("sezione_inps", []):
        tributi_inps.append({
            "codice_sede": t.get("codice_sede", ""),
            "causale": t.get("causale", ""),
            "causale_contributo": t.get("causale", ""),
            "matricola": t.get("matricola", ""),
            "periodo_da": t.get("mese", ""),
            "periodo_a": t.get("anno", ""),
            "periodo_riferimento": t.get("periodo_riferimento", ""),
            "importo_debito": t.get("importo_debito", 0),
            "importo_credito": t.get("importo_credito", 0),
            "importo": t.get("importo_debito", 0),
            "descrizione": t.get("descrizione", "")
        })
    
    # Aggiungi INAIL se presente
    for t in parsed.get("sezione_inail", []):
        tributi_inps.append({
            "codice_sede": t.get("codice_sede", ""),
            "causale": "INAIL",
            "causale_contributo": t.get("causale", "INAIL"),
            "matricola": t.get("codice_ditta", ""),
            "periodo_da": "",
            "periodo_a": "",
            "periodo_riferimento": t.get("numero_riferimento", ""),
            "importo_debito": t.get("importo_debito", 0),
            "importo_credito": t.get("importo_credito", 0),
            "importo": t.get("importo_debito", 0),
            "descrizione": t.get("descrizione", "")
        })
    
    tributi_regioni = []
    for t in parsed.get("sezione_regioni", []):
        tributi_regioni.append({
            "codice_tributo": t.get("codice_tributo"),
            "codice": t.get("codice_tributo"),
            "codice_regione": t.get("codice_regione", ""),
            "codice_ente": t.get("codice_regione", ""),
            "periodo_riferimento": t.get("periodo_riferimento", ""),
            "importo_debito": t.get("importo_debito", 0),
            "importo_credito": t.get("importo_credito", 0),
            "importo": t.get("importo_debito", 0),
            "descrizione": t.get("descrizione", "")
        })
    
    tributi_imu = []
    for t in parsed.get("sezione_tributi_locali", []):
        tributi_imu.append({
            "codice_tributo": t.get("codice_tributo"),
            "codice": t.get("codice_tributo"),
            "codice_comune": t.get("codice_comune", ""),
            "codice_ente": t.get("codice_comune", ""),
            "periodo_riferimento": t.get("periodo_riferimento", ""),
            "importo_debito": t.get("importo_debito", 0),
            "importo_credito": t.get("importo_credito", 0),
            "importo": t.get("importo_debito", 0),
            "descrizione": t.get("descrizione", "")
        })
    
    # Converto al formato f24_commercialista
    f24_doc = {
        "id": f24_id,
        "f24_key": f"{parsed.get('dati_generali', {}).get('codice_fiscale', '')}_{data_scadenza}",
        "file_name": file.filename,
        "file_path": None,
        "dati_generali": parsed.get("dati_generali", {}),
        "sezione_erario": parsed.get("sezione_erario", []),
        "sezione_inps": parsed.get("sezione_inps", []),
        "sezione_regioni": parsed.get("sezione_regioni", []),
        "sezione_tributi_locali": parsed.get("sezione_tributi_locali", []),
        "sezione_inail": parsed.get("sezione_inail", []),
        "totali": totali,
        "has_ravvedimento": parsed.get("has_ravvedimento", False),
        "status": existing.get("status", "da_pagare") if existing else "da_pagare",
        "riconciliato": existing.get("riconciliato", False) if existing else False,
        "pdf_data": base64.b64encode(pdf_bytes).decode('utf-8'),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if existing:
        await db[F24_COLLECTION].update_one(
            {"id": f24_id},
            {"$set": f24_doc}
        )
        action = "aggiornato"
    else:
        f24_doc["created_at"] = datetime.now(timezone.utc).isoformat()
        await db[F24_COLLECTION].insert_one(f24_doc.copy())
        action = "creato"
    
    logger.info(f"F24 {action}: {f24_id} - €{totali.get('saldo_netto', totali.get('saldo_finale', 0)):.2f}")
    
    return {
        "success": True,
        "action": action,
        "id": f24_id,
        "scadenza": data_scadenza,
        "saldo_finale": totali.get("saldo_netto", totali.get("saldo_finale", 0)),
        "filename": file.filename
    }

