"""
Servizio di Integrazione AI Parser
Integra il parser AI con i flussi di upload esistenti:
- Upload XML fatture
- Download documenti da email
- Upload manuale PDF
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from app.services.ai_document_parser import (
    parse_document_with_ai,
    parse_fattura_ai,
    parse_f24_ai, 
    parse_busta_paga_ai,
    convert_ai_fattura_to_db_format,
    convert_ai_busta_paga_to_dipendente_update
)

logger = logging.getLogger(__name__)


async def process_document_with_ai(
    db,
    document_id: str,
    pdf_data: bytes,
    document_type: str = "auto",
    collection: str = "documents_inbox"
) -> Dict[str, Any]:
    """
    Processa un documento con AI e aggiorna il database.
    
    Args:
        db: Database connection
        document_id: ID del documento nella collezione
        pdf_data: Contenuto PDF in bytes
        document_type: "auto", "fattura", "f24", "busta_paga"
        collection: Collezione di origine del documento
        
    Returns:
        Risultato del parsing con aggiornamenti effettuati
    """
    result = {
        "success": False,
        "document_id": document_id,
        "ai_parsed": False,
        "updates": {},
        "errors": []
    }
    
    try:
        # Esegui parsing AI
        parsed = await parse_document_with_ai(
            file_bytes=pdf_data,
            document_type=document_type
        )
        
        if not parsed.get("success"):
            result["errors"].append(parsed.get("error", "Parsing fallito"))
            # Salva comunque lo stato di errore
            await db[collection].update_one(
                {"id": document_id},
                {"$set": {
                    "ai_parsing_attempted": True,
                    "ai_parsing_error": parsed.get("error"),
                    "ai_parsing_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            return result
        
        result["ai_parsed"] = True
        result["parsed_data"] = parsed
        detected_type = parsed.get("detected_type") or parsed.get("tipo_documento")
        
        # Aggiorna il documento con i dati estratti
        update_data = {
            "ai_parsed": True,
            "ai_parsed_at": datetime.now(timezone.utc).isoformat(),
            "ai_parsed_type": detected_type,
            "ai_parsed_data": parsed,
            "ai_confidence": "high" if parsed.get("success") else "low"
        }
        
        # Aggiungi dati specifici per tipo
        if detected_type == "fattura":
            fornitore = parsed.get("fornitore", {})
            update_data.update({
                "fornitore_nome": fornitore.get("denominazione"),
                "fornitore_piva": fornitore.get("partita_iva"),
                "numero_documento": parsed.get("numero_fattura"),
                "data_documento": parsed.get("data_fattura"),
                "importo_totale": parsed.get("totali", {}).get("totale_fattura"),
                "imponibile": parsed.get("totali", {}).get("imponibile"),
                "iva": parsed.get("totali", {}).get("iva")
            })
            
            # Applica Learning Machine per classificazione
            fornitore_nome = fornitore.get("denominazione", "")
            if fornitore_nome:
                keyword_doc = await db["fornitori_keywords"].find_one(
                    {"fornitore_nome": {"$regex": fornitore_nome[:30], "$options": "i"}},
                    {"_id": 0}
                )
                if keyword_doc:
                    update_data["centro_costo_suggerito"] = keyword_doc.get("centro_costo_suggerito")
                    update_data["centro_costo_nome"] = keyword_doc.get("centro_costo_nome")
                    update_data["classificazione_automatica"] = True
                else:
                    update_data["classificazione_automatica"] = False
                    update_data["needs_review"] = True  # Segna per revisione
                    
        elif detected_type == "f24":
            update_data.update({
                "codice_fiscale": parsed.get("codice_fiscale"),
                "ragione_sociale": parsed.get("ragione_sociale"),
                "data_pagamento": parsed.get("data_pagamento"),
                "totale_versato": parsed.get("totali", {}).get("totale_debito"),
                "tributi": parsed.get("sezione_erario", [])
            })
            
        elif detected_type == "busta_paga":
            dipendente = parsed.get("dipendente", {})
            netto = parsed.get("netto", {})
            periodo = parsed.get("periodo", {})
            
            update_data.update({
                "dipendente_nome": f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}".strip(),
                "dipendente_cf": dipendente.get("codice_fiscale"),
                "periodo_mese": periodo.get("mese"),
                "periodo_anno": periodo.get("anno"),
                "netto_pagato": netto.get("netto_pagato"),
                "lordo_totale": parsed.get("retribuzione", {}).get("lordo_totale")
            })
            
            # Cerca dipendente e aggiorna progressivi automaticamente
            cf = dipendente.get("codice_fiscale")
            if cf:
                dip_db = await db["employees"].find_one(
                    {"codice_fiscale": cf},
                    {"_id": 0, "id": 1, "nome": 1, "cognome": 1}
                )
                if dip_db:
                    update_data["dipendente_id"] = dip_db.get("id")
                    
                    # Aggiorna automaticamente i progressivi del dipendente
                    progressivi_update = convert_ai_busta_paga_to_dipendente_update(parsed)
                    
                    await db["employees"].update_one(
                        {"id": dip_db["id"]},
                        {"$set": {
                            "progressivi": progressivi_update["progressivi"],
                            "tfr_accantonato": progressivi_update["tfr"]["fondo_accantonato"],
                            "ultimo_cedolino": progressivi_update["ultimo_cedolino"],
                            "retribuzione_corrente": progressivi_update["retribuzione"],
                            "progressivi_aggiornati_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    update_data["dipendente_aggiornato"] = True
                    logger.info(f"✅ Aggiornati progressivi dipendente {dip_db.get('nome')} {dip_db.get('cognome')}")
        
        # Aggiorna documento nel database
        await db[collection].update_one(
            {"id": document_id},
            {"$set": update_data}
        )
        
        # === SALVA NELLE COLLECTION SPECIFICHE ===
        try:
            if detected_type == "fattura" and parsed.get("fornitore", {}).get("partita_iva"):
                # Salva in invoices se non esiste già
                existing = await db["invoices"].find_one({
                    "supplier_vat": parsed["fornitore"]["partita_iva"],
                    "invoice_number": parsed.get("numero_fattura"),
                    "invoice_date": parsed.get("data_fattura")
                })
                if not existing:
                    fattura_db = convert_ai_fattura_to_db_format(parsed)
                    fattura_db["id"] = f"email_{document_id}"
                    fattura_db["source"] = "email_parser"
                    fattura_db["documents_inbox_id"] = document_id
                    fattura_db["created_at"] = datetime.now(timezone.utc).isoformat()
                    await db["invoices"].insert_one(fattura_db)
                    result["saved_to"] = "invoices"
                    logger.info(f"📄 Fattura salvata in invoices: {parsed.get('numero_fattura')}")
            
            elif detected_type == "busta_paga" and update_data.get("dipendente_id"):
                # Salva in cedolini se non esiste già
                mese = parsed.get("periodo", {}).get("mese")
                anno = parsed.get("periodo", {}).get("anno")
                dip_id = update_data.get("dipendente_id")
                
                existing = await db["cedolini"].find_one({
                    "dipendente_id": dip_id,
                    "mese": mese,
                    "anno": anno
                })
                if not existing and mese and anno:
                    cedolino_db = {
                        "id": f"email_{document_id}",
                        "dipendente_id": dip_id,
                        "employee_id": dip_id,
                        "dipendente_nome": update_data.get("dipendente_nome"),
                        "mese": mese,
                        "anno": anno,
                        "lordo": parsed.get("retribuzione", {}).get("lordo_totale", 0),
                        "netto": parsed.get("netto", {}).get("netto_pagato", 0),
                        "ferie_residue": parsed.get("progressivi", {}).get("ferie_residue", 0),
                        "rol_residui": parsed.get("progressivi", {}).get("rol_residui", 0),
                        "permessi_residui": parsed.get("progressivi", {}).get("permessi_residui", 0),
                        "source": "email_parser",
                        "documents_inbox_id": document_id,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    await db["cedolini"].insert_one(cedolino_db)
                    result["saved_to"] = "cedolini"
                    logger.info(f"📋 Cedolino salvato: {update_data.get('dipendente_nome')} {mese}/{anno}")
            
            elif detected_type == "f24" and parsed.get("totali", {}).get("totale_debito"):
                # Salva in quietanze_f24 se non esiste
                existing = await db["quietanze_f24"].find_one({
                    "codice_fiscale": parsed.get("codice_fiscale"),
                    "data_pagamento": parsed.get("data_pagamento")
                })
                if not existing:
                    f24_db = {
                        "id": f"email_{document_id}",
                        "codice_fiscale": parsed.get("codice_fiscale"),
                        "ragione_sociale": parsed.get("ragione_sociale"),
                        "data_pagamento": parsed.get("data_pagamento"),
                        "totale_versato": parsed.get("totali", {}).get("totale_debito", 0),
                        "tributi": parsed.get("sezione_erario", []),
                        "source": "email_parser",
                        "documents_inbox_id": document_id,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    await db["quietanze_f24"].insert_one(f24_db)
                    result["saved_to"] = "quietanze_f24"
                    logger.info(f"🧾 F24 salvato: {parsed.get('data_pagamento')}")
        except Exception as e:
            logger.warning(f"Errore salvataggio in collection specifica: {e}")
        
        result["success"] = True
        result["updates"] = update_data
        result["detected_type"] = detected_type
        
        return result
        
    except Exception as e:
        logger.error(f"Errore process_document_with_ai: {e}")
        result["errors"].append(str(e))
        return result


async def process_email_documents_batch(
    db,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Processa batch di documenti scaricati da email che non sono ancora stati parsati con AI.
    """
    results = {
        "processed": 0,
        "success": 0,
        "failed": 0,
        "by_type": {},
        "errors": []
    }
    
    import base64
    
    # Trova documenti non ancora processati con AI
    docs = await db["documents_inbox"].find({
        "ai_parsed": {"$ne": True},
        "pdf_data": {"$exists": True}
    }).limit(limit).to_list(limit)
    
    logger.info(f"Trovati {len(docs)} documenti da processare con AI")
    
    for doc in docs:
        try:
            # Decodifica PDF da base64
            pdf_data = base64.b64decode(doc.get("pdf_data", ""))
            
            if not pdf_data:
                continue
            
            # Determina tipo documento dalla categoria email
            category = doc.get("category", "altro")
            doc_type = "auto"
            if category == "fattura":
                doc_type = "fattura"
            elif category == "f24" or category == "quietanza":
                doc_type = "f24"
            elif category == "busta_paga":
                doc_type = "busta_paga"
            
            # Processa con AI
            result = await process_document_with_ai(
                db=db,
                document_id=doc["id"],
                pdf_data=pdf_data,
                document_type=doc_type,
                collection="documents_inbox"
            )
            
            results["processed"] += 1
            
            if result.get("success"):
                results["success"] += 1
                detected = result.get("detected_type", "altro")
                results["by_type"][detected] = results["by_type"].get(detected, 0) + 1
            else:
                results["failed"] += 1
                if result.get("errors"):
                    results["errors"].append({
                        "document_id": doc["id"],
                        "filename": doc.get("filename"),
                        "error": result["errors"][0] if result["errors"] else "Unknown"
                    })
                    
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "document_id": doc.get("id"),
                "filename": doc.get("filename"),
                "error": str(e)
            })
    
    return results


async def get_documents_for_review(
    db,
    collection: str = "documents_inbox",
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Ottiene documenti che richiedono revisione manuale:
    - Non classificati automaticamente
    - Parsing fallito
    - Bassa confidenza
    """
    docs = await db[collection].find({
        "$or": [
            {"needs_review": True},
            {"classificazione_automatica": False, "ai_parsed": True},
            {"ai_confidence": "low"},
            {"ai_parsing_error": {"$exists": True}}
        ]
    }, {"_id": 0, "pdf_data": 0}).sort("ai_parsed_at", -1).limit(limit).to_list(limit)
    
    return docs


async def mark_document_reviewed(
    db,
    document_id: str,
    collection: str = "documents_inbox",
    centro_costo_id: str = None,
    centro_costo_nome: str = None,
    notes: str = None
) -> Dict[str, Any]:
    """
    Segna un documento come revisionato e applica classificazione manuale.
    """
    update_data = {
        "needs_review": False,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_manually": True
    }
    
    if centro_costo_id:
        update_data["centro_costo_id"] = centro_costo_id
        update_data["centro_costo_nome"] = centro_costo_nome
        update_data["classificazione_manuale"] = True
        
    if notes:
        update_data["review_notes"] = notes
    
    result = await db[collection].update_one(
        {"id": document_id},
        {"$set": update_data}
    )
    
    return {
        "success": result.modified_count > 0,
        "document_id": document_id
    }
