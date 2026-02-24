"""
Servizio di Processing AI Automatico per Upload Diretto
Integra il parser AI con l'upload diretto di documenti:
- F24: Parsing + salvataggio in f24_unificato
- Cedolini: Parsing + aggiornamento progressivi dipendente
- Fatture PDF: Parsing + archivio temporaneo (in attesa di XML)

Le fatture PDF vengono archiviate per evitare duplicati, poi associate
automaticamente quando arriva l'XML corrispondente.
"""
import logging
import base64
import uuid
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from app.services.ai_document_parser import (
    parse_document_with_ai,
    parse_f24_ai,
    parse_busta_paga_ai,
    parse_fattura_ai,
    convert_ai_busta_paga_to_dipendente_update
)
from app.db_collections import COLL_F24, COLL_EMPLOYEES, COLL_CEDOLINI

logger = logging.getLogger(__name__)

# Collezione per fatture PDF in attesa di associazione XML
COLL_FATTURE_PDF_ARCHIVIO = "fatture_pdf_archivio"


def calculate_file_hash(content: bytes) -> str:
    """Calcola hash MD5 per evitare duplicati."""
    return hashlib.md5(content).hexdigest()


async def process_upload_f24(
    db,
    pdf_content: bytes,
    filename: str,
    source: str = "upload_diretto"
) -> Dict[str, Any]:
    """
    Processa un F24 caricato direttamente:
    1. Parsing AI per estrarre tutti i dati
    2. Salvataggio in f24_unificato
    3. Deduplicazione basata su campi chiave
    
    Returns:
        Risultato con dati estratti e ID documento salvato
    """
    result = {
        "success": False,
        "tipo": "f24",
        "filename": filename,
        "document_id": None,
        "parsed_data": None,
        "is_duplicate": False,
        "errors": []
    }
    
    try:
        # 1. Parsing AI
        parsed = await parse_f24_ai(file_bytes=pdf_content)
        
        if not parsed.get("success"):
            result["errors"].append(parsed.get("error", "Parsing AI fallito"))
            # Salva comunque con errore per revisione manuale
            error_doc = {
                "id": str(uuid.uuid4()),
                "filename": filename,
                "pdf_data": base64.b64encode(pdf_content).decode(),
                "file_hash": calculate_file_hash(pdf_content),
                "source": source,
                "ai_error": parsed.get("error"),
                "needs_review": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db[COLL_F24].insert_one(error_doc)
            result["document_id"] = error_doc["id"]
            return result
        
        result["parsed_data"] = parsed
        
        # 2. Verifica duplicati basata su campi chiave
        # Chiave univoca: data_pagamento + codice_fiscale + totale_debito + primo_tributo
        data_pagamento = parsed.get("data_pagamento")
        codice_fiscale = parsed.get("codice_fiscale")
        totale_debito = parsed.get("totali", {}).get("totale_debito", 0)
        
        # Estrai primo tributo per identificazione più precisa
        primo_tributo = None
        for sezione in ["sezione_erario", "sezione_inps", "sezione_regioni", "sezione_imu"]:
            tributi = parsed.get(sezione, [])
            if tributi and len(tributi) > 0:
                primo_tributo = tributi[0].get("codice_tributo") or tributi[0].get("causale")
                break
        
        # Cerca duplicato - include primo_tributo se disponibile
        if data_pagamento and codice_fiscale:
            duplicate_query = {
                "data_pagamento": data_pagamento,
                "codice_fiscale": codice_fiscale
            }
            
            # Aggiungi primo_tributo alla query se disponibile per match più preciso
            if primo_tributo:
                duplicate_query["$or"] = [
                    {"parsed_data.sezione_erario.0.codice_tributo": primo_tributo},
                    {"parsed_data.sezione_inps.0.causale": primo_tributo}
                ]
            
            # Se abbiamo anche totale, aggiungi alla query con tolleranza
            if totale_debito and totale_debito > 0:
                duplicate_query["parsed_data.totali.totale_debito"] = {
                    "$gte": totale_debito - 1,
                    "$lte": totale_debito + 1
                }
            
            existing = await db[COLL_F24].find_one(duplicate_query, {"_id": 0, "id": 1, "filename": 1})
            if existing:
                result["is_duplicate"] = True
                result["duplicate_of"] = existing.get("id")
                result["duplicate_filename"] = existing.get("filename")
                result["success"] = True
                result["message"] = f"F24 duplicato: già presente come {existing.get('filename')}"
                logger.info(f"⏭️ F24 duplicato saltato: {filename} (duplicato di {existing.get('filename')})")
                return result
        
        # 3. Salva in f24_unificato
        f24_doc = {
            "id": str(uuid.uuid4()),
            "filename": filename,
            "pdf_data": base64.b64encode(pdf_content).decode(),
            "file_hash": calculate_file_hash(pdf_content),
            "source": source,
            "parsed_data": parsed,
            "tipo_documento": parsed.get("tipo_documento", "f24"),
            "data_pagamento": data_pagamento,
            "codice_fiscale": codice_fiscale,
            "ragione_sociale": parsed.get("ragione_sociale"),
            "totale_versato": totale_debito,
            "ai_parsed": True,
            "ai_parsed_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db[COLL_F24].insert_one(f24_doc)
        result["success"] = True
        result["document_id"] = f24_doc["id"]
        result["message"] = f"F24 parsato e salvato: {data_pagamento} - €{totale_debito:.2f}"
        
        logger.info(f"✅ F24 processato: {filename} -> {data_pagamento}, €{totale_debito:.2f}")
        
    except Exception as e:
        logger.error(f"Errore process_upload_f24: {e}")
        result["errors"].append(str(e))
    
    return result


async def process_upload_cedolino(
    db,
    pdf_content: bytes,
    filename: str,
    dipendente_id: Optional[str] = None,
    source: str = "upload_diretto"
) -> Dict[str, Any]:
    """
    Processa un cedolino/busta paga caricato direttamente:
    1. Parsing AI per estrarre tutti i dati
    2. Identificazione dipendente (per CF o ID fornito)
    3. Aggiornamento automatico progressivi (ferie, permessi, TFR)
    4. Salvataggio in cedolini
    
    Returns:
        Risultato con dati estratti e aggiornamenti effettuati
    """
    result = {
        "success": False,
        "tipo": "busta_paga",
        "filename": filename,
        "document_id": None,
        "dipendente_id": dipendente_id,
        "dipendente_nome": None,
        "progressivi_aggiornati": False,
        "parsed_data": None,
        "errors": []
    }
    
    try:
        # 1. Parsing AI
        parsed = await parse_busta_paga_ai(file_bytes=pdf_content)
        
        if not parsed.get("success"):
            result["errors"].append(parsed.get("error", "Parsing AI fallito"))
            # Salva comunque per revisione
            error_doc = {
                "id": str(uuid.uuid4()),
                "filename": filename,
                "pdf_data": base64.b64encode(pdf_content).decode(),
                "file_hash": calculate_file_hash(pdf_content),
                "source": source,
                "ai_error": parsed.get("error"),
                "needs_review": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db[COLL_CEDOLINI].insert_one(error_doc)
            result["document_id"] = error_doc["id"]
            return result
        
        result["parsed_data"] = parsed
        
        # 2. Identifica dipendente
        dipendente = parsed.get("dipendente", {})
        cf = dipendente.get("codice_fiscale")
        nome_completo = f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}".strip()
        periodo = parsed.get("periodo", {})
        
        # Cerca per ID fornito o per CF
        dip_db = None
        if dipendente_id:
            dip_db = await db[COLL_EMPLOYEES].find_one(
                {"id": dipendente_id},
                {"_id": 0, "id": 1, "nome": 1, "cognome": 1}
            )
        elif cf:
            dip_db = await db[COLL_EMPLOYEES].find_one(
                {"codice_fiscale": cf},
                {"_id": 0, "id": 1, "nome": 1, "cognome": 1}
            )
        
        if dip_db:
            result["dipendente_id"] = dip_db.get("id")
            result["dipendente_nome"] = f"{dip_db.get('nome', '')} {dip_db.get('cognome', '')}".strip()
            
            # 3. Verifica duplicato per dipendente/periodo
            mese = periodo.get("mese")
            anno = periodo.get("anno")
            
            if mese and anno:
                existing = await db[COLL_CEDOLINI].find_one({
                    "dipendente_id": dip_db["id"],
                    "periodo.mese": mese,
                    "periodo.anno": anno
                }, {"_id": 0, "id": 1})
                
                if existing:
                    result["is_duplicate"] = True
                    result["duplicate_of"] = existing.get("id")
                    result["success"] = True
                    result["message"] = f"Cedolino {mese}/{anno} già presente per {result['dipendente_nome']}"
                    logger.info(f"⏭️ Cedolino duplicato: {filename}")
                    return result
            
            # 4. Aggiorna progressivi dipendente
            progressivi_update = convert_ai_busta_paga_to_dipendente_update(parsed)
            
            await db[COLL_EMPLOYEES].update_one(
                {"id": dip_db["id"]},
                {"$set": {
                    "progressivi": progressivi_update["progressivi"],
                    "tfr_accantonato": progressivi_update["tfr"]["fondo_accantonato"],
                    "ultimo_cedolino": progressivi_update["ultimo_cedolino"],
                    "retribuzione_corrente": progressivi_update["retribuzione"],
                    "progressivi_aggiornati_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            result["progressivi_aggiornati"] = True
            logger.info(f"✅ Progressivi aggiornati per {result['dipendente_nome']}")
        else:
            result["dipendente_nome"] = nome_completo
            result["errors"].append(f"Dipendente non trovato nel database (CF: {cf})")
        
        # 5. Salva cedolino
        cedolino_doc = {
            "id": str(uuid.uuid4()),
            "filename": filename,
            "pdf_data": base64.b64encode(pdf_content).decode(),
            "file_hash": calculate_file_hash(pdf_content),
            "source": source,
            "dipendente_id": result.get("dipendente_id"),
            "dipendente_nome": nome_completo,
            "dipendente_cf": cf,
            "periodo": periodo,
            "netto_pagato": parsed.get("netto", {}).get("netto_pagato"),
            "lordo_totale": parsed.get("retribuzione", {}).get("lordo_totale"),
            "progressivi": parsed.get("progressivi", {}),
            "tfr": parsed.get("tfr", {}),
            "parsed_data": parsed,
            "ai_parsed": True,
            "ai_parsed_at": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db[COLL_CEDOLINI].insert_one(cedolino_doc)
        result["success"] = True
        result["document_id"] = cedolino_doc["id"]
        result["message"] = f"Cedolino {periodo.get('mese')}/{periodo.get('anno')} - {nome_completo} - €{parsed.get('netto', {}).get('netto_pagato', 0):.2f}"
        
        logger.info(f"✅ Cedolino processato: {filename}")
        
    except Exception as e:
        logger.error(f"Errore process_upload_cedolino: {e}")
        result["errors"].append(str(e))
    
    return result


async def process_upload_fattura_pdf(
    db,
    pdf_content: bytes,
    filename: str,
    source: str = "upload_diretto"
) -> Dict[str, Any]:
    """
    Processa una fattura PDF caricata direttamente:
    1. Parsing AI per estrarre i dati
    2. Verifica se esiste già XML corrispondente
    3. Se esiste XML: associa il PDF all'XML
    4. Se non esiste XML: salva in archivio temporaneo
    
    Le fatture PDF vengono archiviate per evitare duplicati.
    Quando arriva l'XML corrispondente, il PDF viene associato.
    
    Returns:
        Risultato con stato archivio o associazione
    """
    result = {
        "success": False,
        "tipo": "fattura_pdf",
        "filename": filename,
        "document_id": None,
        "parsed_data": None,
        "xml_associato": False,
        "xml_invoice_id": None,
        "archiviato": False,
        "is_duplicate": False,
        "errors": []
    }
    
    try:
        # 1. Parsing AI
        parsed = await parse_fattura_ai(file_bytes=pdf_content)
        
        if not parsed.get("success"):
            result["errors"].append(parsed.get("error", "Parsing AI fallito"))
            # Salva in archivio per revisione manuale
            error_doc = {
                "id": str(uuid.uuid4()),
                "filename": filename,
                "pdf_data": base64.b64encode(pdf_content).decode(),
                "file_hash": calculate_file_hash(pdf_content),
                "source": source,
                "ai_error": parsed.get("error"),
                "needs_review": True,
                "status": "errore_parsing",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db[COLL_FATTURE_PDF_ARCHIVIO].insert_one(error_doc)
            result["document_id"] = error_doc["id"]
            result["archiviato"] = True
            return result
        
        result["parsed_data"] = parsed
        
        # Estrai dati chiave per matching
        fornitore = parsed.get("fornitore", {})
        fornitore_piva = fornitore.get("partita_iva")
        numero_fattura = parsed.get("numero_fattura")
        data_fattura = parsed.get("data_fattura")
        totale = parsed.get("totali", {}).get("totale_fattura", 0)
        
        # 2. Verifica duplicato in archivio PDF
        file_hash = calculate_file_hash(pdf_content)
        existing_pdf = await db[COLL_FATTURE_PDF_ARCHIVIO].find_one(
            {"file_hash": file_hash},
            {"_id": 0, "id": 1, "filename": 1}
        )
        
        if existing_pdf:
            result["is_duplicate"] = True
            result["duplicate_of"] = existing_pdf.get("id")
            result["success"] = True
            result["message"] = f"PDF già archiviato: {existing_pdf.get('filename')}"
            return result
        
        # 3. Cerca XML corrispondente nella collezione invoices
        xml_match = None
        if fornitore_piva and numero_fattura:
            # Match per P.IVA + numero fattura
            xml_match = await db["invoices"].find_one({
                "supplier_vat": fornitore_piva,
                "invoice_number": numero_fattura,
                "source": {"$in": ["xml_upload", "xml_bulk_upload"]}
            }, {"_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1})
        
        if not xml_match and fornitore_piva and data_fattura and totale:
            # Match alternativo: P.IVA + data + importo (con tolleranza)
            xml_match = await db["invoices"].find_one({
                "supplier_vat": fornitore_piva,
                "invoice_date": data_fattura,
                "total_amount": {"$gte": totale - 1, "$lte": totale + 1},
                "source": {"$in": ["xml_upload", "xml_bulk_upload"]}
            }, {"_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1})
        
        if xml_match:
            # 4A. XML trovato: associa il PDF
            await db["invoices"].update_one(
                {"id": xml_match["id"]},
                {"$set": {
                    "pdf_allegato": base64.b64encode(pdf_content).decode(),
                    "pdf_filename": filename,
                    "pdf_associato_at": datetime.now(timezone.utc).isoformat(),
                    "pdf_parsed_data": parsed
                }}
            )
            
            result["success"] = True
            result["xml_associato"] = True
            result["xml_invoice_id"] = xml_match["id"]
            result["message"] = f"PDF associato a XML: Fattura {xml_match.get('invoice_number')} - {xml_match.get('supplier_name')}"
            
            logger.info(f"✅ PDF associato a XML: {filename} -> {xml_match.get('invoice_number')}")
            
        else:
            # 4B. XML non trovato: archivia in attesa
            archivio_doc = {
                "id": str(uuid.uuid4()),
                "filename": filename,
                "pdf_data": base64.b64encode(pdf_content).decode(),
                "file_hash": file_hash,
                "source": source,
                "status": "in_attesa_xml",
                "parsed_data": parsed,
                "fornitore_nome": fornitore.get("denominazione"),
                "fornitore_piva": fornitore_piva,
                "numero_fattura": numero_fattura,
                "data_fattura": data_fattura,
                "totale": totale,
                "ai_parsed": True,
                "ai_parsed_at": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db[COLL_FATTURE_PDF_ARCHIVIO].insert_one(archivio_doc)
            
            result["success"] = True
            result["archiviato"] = True
            result["document_id"] = archivio_doc["id"]
            result["message"] = f"PDF archiviato in attesa di XML: {numero_fattura} - {fornitore.get('denominazione')}"
            
            logger.info(f"📁 Fattura PDF archiviata: {filename} (in attesa di XML)")
        
    except Exception as e:
        logger.error(f"Errore process_upload_fattura_pdf: {e}")
        result["errors"].append(str(e))
    
    return result


async def associate_pdf_to_xml_on_upload(
    db,
    invoice_id: str,
    supplier_vat: str,
    invoice_number: str,
    invoice_date: str,
    total_amount: float
) -> Dict[str, Any]:
    """
    Chiamata quando viene caricato un XML per cercare PDF in archivio da associare.
    
    Args:
        invoice_id: ID della fattura XML appena caricata
        supplier_vat: P.IVA fornitore
        invoice_number: Numero fattura
        invoice_date: Data fattura
        total_amount: Importo totale
        
    Returns:
        Risultato dell'associazione
    """
    result = {
        "pdf_found": False,
        "pdf_associated": False,
        "pdf_filename": None
    }
    
    try:
        # Cerca PDF in archivio
        pdf_match = await db[COLL_FATTURE_PDF_ARCHIVIO].find_one({
            "fornitore_piva": supplier_vat,
            "numero_fattura": invoice_number,
            "status": "in_attesa_xml"
        }, {"_id": 0})
        
        if not pdf_match:
            # Prova match alternativo
            pdf_match = await db[COLL_FATTURE_PDF_ARCHIVIO].find_one({
                "fornitore_piva": supplier_vat,
                "data_fattura": invoice_date,
                "totale": {"$gte": total_amount - 1, "$lte": total_amount + 1},
                "status": "in_attesa_xml"
            }, {"_id": 0})
        
        if pdf_match:
            result["pdf_found"] = True
            result["pdf_filename"] = pdf_match.get("filename")
            
            # Associa PDF all'XML
            await db["invoices"].update_one(
                {"id": invoice_id},
                {"$set": {
                    "pdf_allegato": pdf_match.get("pdf_data"),
                    "pdf_filename": pdf_match.get("filename"),
                    "pdf_associato_at": datetime.now(timezone.utc).isoformat(),
                    "pdf_parsed_data": pdf_match.get("parsed_data")
                }}
            )
            
            # Aggiorna stato archivio
            await db[COLL_FATTURE_PDF_ARCHIVIO].update_one(
                {"id": pdf_match["id"]},
                {"$set": {
                    "status": "associato_xml",
                    "xml_invoice_id": invoice_id,
                    "associato_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            result["pdf_associated"] = True
            logger.info(f"✅ PDF archivio associato automaticamente: {pdf_match.get('filename')} -> Invoice {invoice_id}")
    
    except Exception as e:
        logger.error(f"Errore associate_pdf_to_xml_on_upload: {e}")
        result["error"] = str(e)
    
    return result


async def process_document_auto(
    db,
    pdf_content: bytes,
    filename: str,
    document_type: str = "auto",
    source: str = "upload_diretto",
    dipendente_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Entry point principale per il processing automatico su upload.
    Determina il tipo di documento e lo processa di conseguenza.
    
    Args:
        db: Database connection
        pdf_content: Contenuto PDF
        filename: Nome file
        document_type: "auto", "f24", "busta_paga", "fattura"
        source: Fonte del documento
        dipendente_id: ID dipendente (opzionale, per cedolini)
        
    Returns:
        Risultato del processing
    """
    # Se tipo auto, usa AI per detection
    if document_type == "auto":
        detection = await parse_document_with_ai(
            file_bytes=pdf_content,
            document_type="auto"
        )
        document_type = detection.get("detected_type", "fattura")
    
    # Processa in base al tipo
    if document_type == "f24":
        return await process_upload_f24(db, pdf_content, filename, source)
    elif document_type == "busta_paga":
        return await process_upload_cedolino(db, pdf_content, filename, dipendente_id, source)
    elif document_type == "fattura":
        return await process_upload_fattura_pdf(db, pdf_content, filename, source)
    else:
        return {
            "success": False,
            "tipo": document_type,
            "filename": filename,
            "errors": [f"Tipo documento non supportato: {document_type}"]
        }
