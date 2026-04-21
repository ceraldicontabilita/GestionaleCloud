"""
Fatture Module - Import XML singoli e multipli.
"""
import logging
from fastapi import HTTPException, UploadFile, File
from typing import Dict, Any, List
from datetime import datetime, timezone
import uuid
import zipfile
import io

from app.database import Database
from app.parsers.fattura_elettronica_parser import parse_fattura_xml
from app.routers.fatture_module.ciclo_utils import (
    crea_scadenza_pagamento,
    processa_carico_magazzino
)
from .common import COL_FORNITORI, COL_FATTURE_RICEVUTE
from .helpers import get_or_create_fornitore, check_duplicato, salva_dettaglio_righe, salva_allegato_pdf

logger = logging.getLogger(__name__)


async def import_fattura_xml(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Importa una singola fattura XML."""
    db = Database.get_db()
    
    try:
        content = await file.read()
        xml_content = None
        for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
            try:
                xml_content = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if xml_content is None:
            xml_content = content.decode('utf-8', errors='replace')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Errore lettura file: {str(e)}")
    
    parsed = parse_fattura_xml(xml_content)
    
    if parsed.get("error"):
        raise HTTPException(status_code=400, detail=f"Errore parsing XML: {parsed['error']}")
    
    partita_iva = parsed.get("supplier_vat", "")
    numero_doc = parsed.get("invoice_number", "")
    
    duplicato = await check_duplicato(db, partita_iva, numero_doc)
    metodo_manuale_esistente = None
    
    if duplicato:
        if duplicato.get("metodo_pagamento_modificato_manualmente"):
            metodo_manuale_esistente = duplicato.get("metodo_pagamento")
        
        if duplicato.get("source") == "email" or duplicato.get("is_bozza_email"):
            await db[COL_FATTURE_RICEVUTE].delete_one({"id": duplicato["id"]})
        else:
            await db[COL_FATTURE_RICEVUTE].update_one(
                {"id": duplicato["id"]},
                {"$set": {"raw_xml": parsed.get("raw_xml"), "updated_at": datetime.now(timezone.utc).isoformat(), "reimported": True}}
            )
            return {"success": True, "message": f"Fattura {numero_doc} già presente - dati aggiornati", "azione": "aggiornato", "fattura_id": duplicato["id"]}
    
    fornitore_result = await get_or_create_fornitore(db, parsed)
    if fornitore_result.get("error"):
        raise HTTPException(status_code=400, detail=fornitore_result["error"])
    
    fornitore_db = await db[COL_FORNITORI].find_one(
        {"partita_iva": partita_iva}, 
        {"_id": 0, "esclude_magazzino": 1, "metodo_pagamento": 1, "metodo_pagamento_predefinito": 1, "iban": 1}
    )
    
    metodo_pagamento_finale = None
    if metodo_manuale_esistente:
        metodo_pagamento_finale = metodo_manuale_esistente
    elif fornitore_db:
        metodo_pagamento_finale = fornitore_db.get("metodo_pagamento_predefinito") or fornitore_db.get("metodo_pagamento") or "da_configurare"
    else:
        metodo_pagamento_finale = "da_configurare"
    
    fornitore_obj = {
        "id": fornitore_result.get("fornitore_id"),
        "partita_iva": partita_iva,
        "ragione_sociale": fornitore_result.get("ragione_sociale"),
        "esclude_magazzino": fornitore_db.get("esclude_magazzino", True) if fornitore_db else True,
        "metodo_pagamento": metodo_pagamento_finale,
        "iban": fornitore_db.get("iban") if fornitore_db else None
    }
    
    warnings = []
    if not metodo_pagamento_finale or metodo_pagamento_finale in ["", "da_configurare", None]:
        warnings.append(f"Fornitore senza metodo pagamento: {fornitore_result.get('ragione_sociale', '')}")
    
    metodi_bancari = ["bonifico", "banca", "sepa", "rid", "sdd", "assegno", "misto"]
    if metodo_pagamento_finale and metodo_pagamento_finale.lower() in metodi_bancari and not fornitore_obj.get("iban"):
        warnings.append(f"Fornitore senza IBAN (metodo: {metodo_pagamento_finale})")
    
    totali_coerenti = parsed.get("totali_coerenti", True)
    stato = "importata" if totali_coerenti else "anomala"
    
    fattura_id = str(uuid.uuid4())
    fattura = {
        "id": fattura_id,
        "tipo": "passiva",
        "numero_documento": numero_doc,
        "data_documento": parsed.get("invoice_date", ""),
        "tipo_documento": parsed.get("tipo_documento", "TD01"),
        "tipo_documento_desc": parsed.get("tipo_documento_desc", "Fattura"),
        "divisa": parsed.get("divisa", "EUR"),
        "importo_totale": parsed.get("total_amount", 0),
        "imponibile": parsed.get("imponibile", 0),
        "iva": parsed.get("iva", 0),
        "somma_righe": parsed.get("somma_righe", 0),
        "fornitore_id": fornitore_result.get("fornitore_id"),
        "fornitore_partita_iva": partita_iva,
        "fornitore_ragione_sociale": fornitore_result.get("ragione_sociale"),
        "fornitore_nuovo": fornitore_result.get("nuovo", False),
        "fornitore": parsed.get("fornitore", {}),
        "cliente": parsed.get("cliente", {}),
        "pagamento": parsed.get("pagamento", {}),
        "metodo_pagamento": metodo_pagamento_finale,
        "metodo_pagamento_modificato_manualmente": bool(metodo_manuale_esistente),
        "provvisorio": True,
        "riconciliato": False,
        "pagato": False,
        "data_pagamento": None,
        "stato": stato,
        "totali_coerenti": totali_coerenti,
        "differenza_totali": parsed.get("differenza_totali", 0),
        "has_pdf": parsed.get("has_pdf", False),
        "num_righe": len(parsed.get("linee", [])),
        "num_allegati": len(parsed.get("allegati", [])),
        "is_bozza_email": False,
        "causali": parsed.get("causali", []),
        "riepilogo_iva": parsed.get("riepilogo_iva", []),
        "filename": file.filename,
        "xml_content": xml_content,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db[COL_FATTURE_RICEVUTE].insert_one(fattura.copy())
    
    # Trigger B: verbali da fattura XML noleggio (non bloccante)
    try:
        from app.services.verbali_fattura_trigger import processa_fattura_per_verbali
        await processa_fattura_per_verbali(db, fattura)
    except Exception:
        logger.exception("Errore trigger verbali da fattura")
    
    # F: Gestione Note di Credito TD04/TD08 — storna fattura originale
    NOTE_CREDITO = ["TD04", "TD08"]
    tipo_documento_nc = parsed.get("tipo_documento", "TD01")
    if tipo_documento_nc in NOTE_CREDITO:
        rif_numero = parsed.get("dati_generali", {}).get("numero_fattura_riferimento")
        if rif_numero and partita_iva:
            fattura_orig = await db[COL_FATTURE_RICEVUTE].find_one({
                "$or": [
                    {"numero_documento": rif_numero, "fornitore_partita_iva": partita_iva},
                    {"invoice_number": rif_numero, "supplier_vat": partita_iva}
                ]
            })
            if fattura_orig:
                importo_nc = float(parsed.get("total_amount", 0))
                importo_orig = float(fattura_orig.get("importo_totale") or fattura_orig.get("total_amount", 0))
                await db[COL_FATTURE_RICEVUTE].update_one(
                    {"id": fattura_orig["id"]},
                    {"$set": {"ha_nota_credito": True,
                              "importo_stornato": importo_nc,
                              "importo_residuo": round(importo_orig - importo_nc, 2),
                              "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
                await db["scadenziario_fornitori"].update_many(
                    {"fattura_id": fattura_orig["id"], "pagato": {"$ne": True}},
                    {"$inc": {"importo": -importo_nc}}
                )
    
    num_righe = await salva_dettaglio_righe(db, fattura_id, parsed.get("linee", []))
    
    allegati_salvati = []
    for allegato in parsed.get("allegati", []):
        allegato_id = await salva_allegato_pdf(db, fattura_id, allegato)
        if allegato_id:
            allegati_salvati.append(allegato_id)
    
    risultato_integrazione = {}
    
    try:
        mag_result = await processa_carico_magazzino(db, fattura_id, fornitore_obj, parsed.get("linee", []), parsed.get("invoice_date", ""), numero_doc)
        risultato_integrazione["magazzino"] = mag_result
    except Exception as e:
        risultato_integrazione["magazzino"] = {"error": str(e)}
    
    # ── AUTO-ROUTING: se il fornitore ha un metodo di pagamento riconoscibile,
    # crea subito il movimento in prima_nota_cassa o prima_nota_banca.
    # Evita il passaggio manuale per Amazon, bonifici, carte, SEPA, ecc.
    from .metodo_pagamento import normalizza_metodo_pagamento
    dest = normalizza_metodo_pagamento(metodo_pagamento_finale)
    if dest in ("cassa", "banca"):
        try:
            importo_f = float(parsed.get("total_amount", 0))
            if importo_f > 0:
                movimento_id = str(uuid.uuid4())
                target_coll = "prima_nota_cassa" if dest == "cassa" else "prima_nota_banca"
                data_pag = parsed.get("invoice_date", "")
                movimento = {
                    "id": movimento_id,
                    "data": data_pag,
                    "descrizione": f"Pagamento Fatt. {numero_doc} - {fornitore_result.get('ragione_sociale', 'Fornitore')}",
                    "causale": "Pagamento fattura fornitore",
                    "importo": importo_f,
                    "tipo": "uscita",
                    "categoria": "fornitori",
                    "stato": "confermato",
                    "fattura_id": fattura_id,
                    "fattura_collegata": fattura_id,
                    "fattura_numero": numero_doc,
                    "fornitore": fornitore_result.get("ragione_sociale", "Fornitore"),
                    "fornitore_piva": partita_iva,
                    "metodo_pagamento": dest,
                    "metodo_pagamento_originale": metodo_pagamento_finale,
                    "provvisorio": False,
                    "riconciliato": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source": "auto_import_da_fornitore",
                }
                await db[target_coll].insert_one(movimento)
                await db[COL_FATTURE_RICEVUTE].update_one(
                    {"id": fattura_id},
                    {"$set": {
                        "pagato": True, "stato": "pagata", "stato_pagamento": "pagata",
                        "data_pagamento": data_pag,
                        "metodo_pagamento": dest,
                        "metodo_pagamento_effettivo": dest,
                        "metodo_pagamento_originale": metodo_pagamento_finale,
                        "provvisorio": False,
                        ("prima_nota_cassa_id" if dest == "cassa" else "prima_nota_banca_id"): movimento_id,
                    }}
                )
                risultato_integrazione["prima_nota"] = {"status": "auto_confermato", "collection": target_coll, "movimento_id": movimento_id}
            else:
                risultato_integrazione["prima_nota"] = {"status": "skip_importo_zero"}
        except Exception as e:
            risultato_integrazione["prima_nota"] = {"status": "errore_auto_routing", "error": str(e)}
    else:
        risultato_integrazione["prima_nota"] = {"status": "in_attesa_conferma", "message": "Metodo pagamento fornitore non definito o assegno: conferma manuale richiesta"}
    
    try:
        scadenza_id = await crea_scadenza_pagamento(db, fattura_id, fattura, fornitore_obj)
        risultato_integrazione["scadenziario"] = {"scadenza_id": scadenza_id, "status": "ok"}
        risultato_integrazione["riconciliazione"] = {"automatica": False, "message": "In attesa conferma"}
    except Exception as e:
        risultato_integrazione["scadenziario"] = {"error": str(e)}
    
    await db[COL_FATTURE_RICEVUTE].update_one(
        {"id": fattura_id},
        {"$set": {"integrazione_completata": False, "stato_riconciliazione": "in_attesa_conferma", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    # ── EVENTO: pubblica sul Bus per scatenare tutti gli handler automatici ──
    try:
        from app.core.event_bus import bus
        evento_payload = {
            "fattura_id":      fattura_id,
            "numero_documento": numero_doc,
            "data_documento":  parsed.get("invoice_date", ""),
            "importo_totale":  parsed.get("total_amount", 0),
            "imponibile":      parsed.get("imponibile", 0),
            "iva":             parsed.get("iva", 0),
            "metodo_pagamento": metodo_pagamento_finale or "da_configurare",
            "fornitore":       fornitore_obj,
            "righe":           parsed.get("linee", []),
            "stato":           stato,
        }
        await bus.publish("fattura.importata", payload=evento_payload, db=db)
    except Exception as e:
        logger.warning(f"[ImportXML] Event Bus non disponibile: {e}")

    return {
        "success": True,
        "fattura_id": fattura_id,
        "numero_documento": numero_doc,
        "data_documento": parsed.get("invoice_date"),
        "importo_totale": parsed.get("total_amount"),
        "fornitore": {"partita_iva": partita_iva, "ragione_sociale": fornitore_result.get("ragione_sociale"), "nuovo": fornitore_result.get("nuovo")},
        "stato": stato,
        "totali_coerenti": totali_coerenti,
        "righe_salvate": num_righe,
        "allegati_salvati": len(allegati_salvati),
        "has_pdf": parsed.get("has_pdf", False),
        "integrazione": risultato_integrazione,
        "warnings": warnings if warnings else None
    }


async def import_fatture_xml_multipli(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    """Importa multiple fatture XML."""
    db = Database.get_db()
    
    risultati = {
        "totale": len(files),
        "importate": 0,
        "duplicate": 0,
        "errori": 0,
        "fornitori_nuovi": 0,
        "anomale": 0,
        "dettagli": []
    }
    
    for file in files:
        try:
            content = await file.read()
            xml_content = None
            for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
                try:
                    xml_content = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if xml_content is None:
                xml_content = content.decode('utf-8', errors='replace')
            
            parsed = parse_fattura_xml(xml_content)
            
            if parsed.get("error"):
                risultati["errori"] += 1
                risultati["dettagli"].append({"filename": file.filename, "status": "errore", "error": parsed["error"]})
                continue
            
            partita_iva = parsed.get("supplier_vat", "")
            numero_doc = parsed.get("invoice_number", "")
            
            duplicato = await check_duplicato(db, partita_iva, numero_doc)
            if duplicato and not (duplicato.get("source") == "email" or duplicato.get("is_bozza_email")):
                risultati["duplicate"] += 1
                risultati["dettagli"].append({"filename": file.filename, "status": "duplicato", "numero": numero_doc})
                continue
            
            if duplicato:
                await db[COL_FATTURE_RICEVUTE].delete_one({"id": duplicato["id"]})
            
            fornitore_result = await get_or_create_fornitore(db, parsed)
            if fornitore_result.get("nuovo"):
                risultati["fornitori_nuovi"] += 1
            
            fornitore_db = await db[COL_FORNITORI].find_one({"partita_iva": partita_iva}, {"_id": 0, "metodo_pagamento": 1, "iban": 1, "esclude_magazzino": 1})
            metodo_pagamento = fornitore_db.get("metodo_pagamento", "da_configurare") if fornitore_db else "da_configurare"
            
            totali_coerenti = parsed.get("totali_coerenti", True)
            stato = "importata" if totali_coerenti else "anomala"
            if not totali_coerenti:
                risultati["anomale"] += 1
            
            fattura_id = str(uuid.uuid4())
            fattura = {
                "id": fattura_id,
                "tipo": "passiva",
                "numero_documento": numero_doc,
                "data_documento": parsed.get("invoice_date", ""),
                "tipo_documento": parsed.get("tipo_documento", "TD01"),
                "importo_totale": parsed.get("total_amount", 0),
                "imponibile": parsed.get("imponibile", 0),
                "iva": parsed.get("iva", 0),
                "fornitore_id": fornitore_result.get("fornitore_id"),
                "fornitore_partita_iva": partita_iva,
                "fornitore_ragione_sociale": fornitore_result.get("ragione_sociale"),
                "fornitore": parsed.get("fornitore", {}),
                "cliente": parsed.get("cliente", {}),
                "metodo_pagamento": metodo_pagamento,
                "provvisorio": True,
                "riconciliato": False,
                "pagato": False,
                "stato": stato,
                "totali_coerenti": totali_coerenti,
                "has_pdf": parsed.get("has_pdf", False),
                "num_righe": len(parsed.get("linee", [])),
                "filename": file.filename,
                "xml_content": xml_content,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db[COL_FATTURE_RICEVUTE].insert_one(fattura.copy())
            await salva_dettaglio_righe(db, fattura_id, parsed.get("linee", []))
            
            for allegato in parsed.get("allegati", []):
                await salva_allegato_pdf(db, fattura_id, allegato)
            
            risultati["importate"] += 1
            risultati["dettagli"].append({
                "filename": file.filename,
                "status": "importata",
                "fattura_id": fattura_id,
                "numero": numero_doc,
                "importo": parsed.get("total_amount", 0),
                "fornitore": fornitore_result.get("ragione_sociale")
            })
            
        except Exception as e:
            risultati["errori"] += 1
            risultati["dettagli"].append({"filename": file.filename, "status": "errore", "error": str(e)})
    
    return risultati


async def import_fatture_zip(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Importa fatture XML da un file ZIP."""
    db = Database.get_db()
    
    if not file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="Il file deve essere uno ZIP")
    
    content = await file.read()
    
    risultati = {
        "totale": 0,
        "importate": 0,
        "duplicate": 0,
        "errori": 0,
        "dettagli": []
    }
    
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            xml_files = [f for f in zf.namelist() if f.lower().endswith('.xml') and not f.startswith('__MACOSX')]
            risultati["totale"] = len(xml_files)
            
            for filename in xml_files:
                try:
                    xml_content = None
                    file_content = zf.read(filename)
                    
                    for encoding in ['utf-8', 'latin-1', 'iso-8859-1']:
                        try:
                            xml_content = file_content.decode(encoding)
                            break
                        except UnicodeDecodeError:
                            continue
                    
                    if not xml_content:
                        xml_content = file_content.decode('utf-8', errors='replace')
                    
                    parsed = parse_fattura_xml(xml_content)
                    
                    if parsed.get("error"):
                        risultati["errori"] += 1
                        risultati["dettagli"].append({"filename": filename, "status": "errore", "error": parsed["error"]})
                        continue
                    
                    partita_iva = parsed.get("supplier_vat", "")
                    numero_doc = parsed.get("invoice_number", "")
                    
                    duplicato = await check_duplicato(db, partita_iva, numero_doc)
                    if duplicato:
                        risultati["duplicate"] += 1
                        risultati["dettagli"].append({"filename": filename, "status": "duplicato"})
                        continue
                    
                    fornitore_result = await get_or_create_fornitore(db, parsed)
                    fornitore_db = await db[COL_FORNITORI].find_one({"partita_iva": partita_iva}, {"_id": 0, "metodo_pagamento": 1})
                    metodo_pagamento = fornitore_db.get("metodo_pagamento", "da_configurare") if fornitore_db else "da_configurare"
                    
                    fattura_id = str(uuid.uuid4())
                    fattura = {
                        "id": fattura_id,
                        "tipo": "passiva",
                        "numero_documento": numero_doc,
                        "data_documento": parsed.get("invoice_date", ""),
                        "importo_totale": parsed.get("total_amount", 0),
                        "fornitore_id": fornitore_result.get("fornitore_id"),
                        "fornitore_partita_iva": partita_iva,
                        "fornitore_ragione_sociale": fornitore_result.get("ragione_sociale"),
                        "metodo_pagamento": metodo_pagamento,
                        "provvisorio": True,
                        "riconciliato": False,
                        "pagato": False,
                        "stato": "importata",
                        "filename": filename,
                        "source": "zip_import",
                        "xml_content": xml_content,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    await db[COL_FATTURE_RICEVUTE].insert_one(fattura.copy())
                    await salva_dettaglio_righe(db, fattura_id, parsed.get("linee", []))
                    
                    risultati["importate"] += 1
                    risultati["dettagli"].append({
                        "filename": filename,
                        "status": "importata",
                        "fattura_id": fattura_id,
                        "numero": numero_doc
                    })
                    
                except Exception as e:
                    risultati["errori"] += 1
                    risultati["dettagli"].append({"filename": filename, "status": "errore", "error": str(e)})
                    
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="File ZIP non valido")
    
    return risultati
