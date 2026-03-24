"""
Employees Payroll Router - Gestione dipendenti e buste paga.
Refactored from public_api.py
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Body
from typing import Dict, Any, List
from datetime import datetime, timezone
import uuid
import tempfile
import os
import logging
import sys

# Aggiungi path per il parser multi-template
sys.path.insert(0, '/app')

from app.database import Database, Collections
from app.parsers.payslip_parser_simple import parse_payslip_simple

# Import del nuovo parser multi-template
try:
    from app.parsers.busta_paga_multi_template import parse_busta_paga_from_bytes, extract_summary
    HAS_MULTI_TEMPLATE_PARSER = True
except ImportError:
    HAS_MULTI_TEMPLATE_PARSER = False

logger = logging.getLogger(__name__)
router = APIRouter()


# ============== EMPLOYEES ==============

@router.get("")
async def list_employees(skip: int = 0, limit: int = 10000) -> List[Dict[str, Any]]:
    """Lista dipendenti con ultimi dati busta paga. OTTIMIZZATO con aggregazione."""
    db = Database.get_db()
    
    # Prima carica tutti i dipendenti
    employees = await db[Collections.EMPLOYEES].find({}, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    
    if not employees:
        return []
    
    # Estrai tutti i codici fiscali
    codici_fiscali = [emp.get("codice_fiscale") for emp in employees if emp.get("codice_fiscale")]
    
    # Query SINGOLA per ottenere l'ultimo cedolino di ogni dipendente
    if codici_fiscali:
        pipeline = [
            {"$match": {"codice_fiscale": {"$in": codici_fiscali}}},
            {"$sort": {"anno": -1, "mese": -1}},
            {"$group": {
                "_id": "$codice_fiscale",
                "netto_mese": {"$first": "$netto_mese"},
                "retribuzione_netta": {"$first": "$retribuzione_netta"},
                "lordo": {"$first": "$lordo"},
                "retribuzione_lorda": {"$first": "$retribuzione_lorda"},
                "ore_lavorate": {"$first": "$ore_lavorate"},
                "ore_ordinarie": {"$first": "$ore_ordinarie"},
                "periodo": {"$first": "$periodo"},
                "mese": {"$first": "$mese"},
                "anno": {"$first": "$anno"},
                "qualifica": {"$first": "$qualifica"}
            }}
        ]
        
        cedolini_map = {}
        async for doc in db["cedolini"].aggregate(pipeline):
            cedolini_map[doc["_id"]] = doc
    else:
        cedolini_map = {}
    
    # Arricchisci dipendenti con dati cedolini
    for emp in employees:
        cf = emp.get("codice_fiscale")
        if cf and cf in cedolini_map:
            latest = cedolini_map[cf]
            emp["netto"] = latest.get("netto_mese") or latest.get("retribuzione_netta", 0)
            emp["lordo"] = latest.get("lordo") or latest.get("retribuzione_lorda", 0)
            emp["ore_ordinarie"] = latest.get("ore_lavorate") or latest.get("ore_ordinarie", 0)
            
            # Handle mese/anno
            mese_val = latest.get('mese', 0)
            anno_val = latest.get('anno', 0)
            try:
                mese_int = int(mese_val) if mese_val else 0
                anno_int = int(anno_val) if anno_val else 0
                fallback_periodo = f"{mese_int:02d}/{anno_int}"
            except (ValueError, TypeError):
                fallback_periodo = f"{mese_val}/{anno_val}"
            emp["ultimo_periodo"] = latest.get("periodo") or fallback_periodo
            
            if not emp.get("role") or emp.get("role") == "-":
                emp["role"] = latest.get("qualifica") or emp.get("role", "")
        
        if not emp.get("nome_completo"):
            emp["nome_completo"] = emp.get("name") if emp.get("name") and emp.get("name") != emp.get("ultimo_periodo") else None
        if emp.get("nome_completo"):
            emp["name"] = emp["nome_completo"]
    
    return employees


@router.post("")
async def create_employee(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea dipendente."""
    db = Database.get_db()
    
    # Parse nome/cognome se presenti
    nome = data.get("nome", "")
    cognome = data.get("cognome", "")
    nome_completo = data.get("nome_completo", data.get("name", ""))
    if not nome_completo and (nome or cognome):
        nome_completo = f"{nome} {cognome}".strip()
    
    employee = {
        "id": str(uuid.uuid4()),
        "name": data.get("name", nome_completo),
        "nome": nome,
        "cognome": cognome,
        "nome_completo": nome_completo,
        "codice_fiscale": data.get("codice_fiscale", ""),
        "email": data.get("email", ""),
        "telefono": data.get("telefono", ""),
        "role": data.get("role", ""),
        "mansione": data.get("mansione", data.get("role", "")),
        "salary": data.get("salary", 0),
        "contract_type": data.get("contract_type", "dipendente"),
        "iban": data.get("iban", ""),
        "giorni_lavoro": data.get("giorni_lavoro", ["lun", "mar", "mer", "gio", "ven", "sab"]),  # Default Lun-Sab
        "in_carico": data.get("in_carico", True),
        "status": "attivo" if data.get("in_carico", True) else "cessato",
        "hire_date": data.get("hire_date", datetime.now(timezone.utc).isoformat()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Check for duplicate CF
    if employee["codice_fiscale"]:
        existing = await db[Collections.EMPLOYEES].find_one({"codice_fiscale": employee["codice_fiscale"]})
        if existing:
            raise HTTPException(status_code=409, detail="Dipendente con questo codice fiscale già esistente")
    
    await db[Collections.EMPLOYEES].insert_one(employee.copy())
    employee.pop("_id", None)
    return employee



@router.put("/{employee_id}")
async def update_employee(employee_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiorna dipendente."""
    db = Database.get_db()
    
    # Remove immutable fields
    data.pop("id", None)
    data.pop("created_at", None)
    data.pop("_id", None)
    
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db[Collections.EMPLOYEES].update_one(
        {"$or": [{"id": employee_id}, {"codice_fiscale": employee_id}]},
        {"$set": data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    return {"success": True, "message": "Dipendente aggiornato"}



@router.delete("/{employee_id}")
async def delete_employee(employee_id: str) -> Dict[str, Any]:
    """Elimina dipendente."""
    db = Database.get_db()
    result = await db[Collections.EMPLOYEES].delete_one({"id": employee_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    return {"success": True, "deleted_id": employee_id}


@router.delete("/all/confirm")
async def delete_all_employees() -> Dict[str, Any]:
    """Elimina tutti i dipendenti."""
    db = Database.get_db()
    result = await db[Collections.EMPLOYEES].delete_many({})
    return {"success": True, "deleted_count": result.deleted_count}


# ============== PAYSLIPS (BUSTE PAGA) ==============
# NOTA: Unificato con collection "cedolini" per evitare duplicazione dati

@router.get("/payslips")
async def list_payslips(skip: int = 0, limit: int = 10000) -> List[Dict[str, Any]]:
    """Lista buste paga (unificato con cedolini)."""
    db = Database.get_db()
    # Legge da cedolini (collection unificata)
    return await db["cedolini"].find({}, {"_id": 0}).sort([("anno", -1), ("mese", -1)]).skip(skip).limit(limit).to_list(limit)


@router.get("/payslips/{codice_fiscale}")
async def get_payslips_by_employee(codice_fiscale: str) -> List[Dict[str, Any]]:
    """Buste paga per dipendente (unificato con cedolini)."""
    db = Database.get_db()
    return await db["cedolini"].find({"codice_fiscale": codice_fiscale}, {"_id": 0}).sort([("anno", -1), ("mese", -1)]).to_list(1000)


@router.delete("/payslips/all/confirm")
async def delete_all_payslips() -> Dict[str, Any]:
    """Elimina tutte le buste paga (dalla collection cedolini)."""
    db = Database.get_db()
    result = await db["cedolini"].delete_many({})
    return {"success": True, "deleted_count": result.deleted_count}


# ============== UPLOAD PDF BUSTE PAGA ==============

@router.post("/paghe/upload-pdf")
async def upload_payslip_pdf(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Upload buste paga con parser semplificato.

    Estrae SOLO: nome dipendente, periodo (mese/anno), importo netto.
    Salva il PDF allegato al cedolino per visualizzazione futura.

    Supporta:
    - PDF singolo
    - Archivio ZIP/RAR contenente PDF (utile per upload massivo)
    """
    filename = (file.filename or "").lower()
    if not (filename.endswith('.pdf') or filename.endswith('.zip') or filename.endswith('.rar')):
        raise HTTPException(status_code=400, detail="Il file deve essere PDF, ZIP o RAR")
    
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="File vuoto")

        # Lista di tuple: (pdf_bytes, original_filename)
        pdf_files = []
        tmp_dir = None

        # Prepara lista PDF da parsificare
        if filename.endswith('.pdf'):
            pdf_files = [(content, file.filename or "cedolino.pdf")]
        else:
            import zipfile
            import glob
            import subprocess

            tmp_dir = tempfile.TemporaryDirectory()
            archive_path = os.path.join(tmp_dir.name, file.filename or 'archivio')
            with open(archive_path, 'wb') as f:
                f.write(content)

            if filename.endswith('.zip'):
                with zipfile.ZipFile(archive_path) as zf:
                    zf.extractall(tmp_dir.name)
            else:
                # RAR: usa bsdtar (libarchive)
                subprocess.run(['bsdtar', '-xf', archive_path, '-C', tmp_dir.name], check=True)

            pdf_paths = glob.glob(os.path.join(tmp_dir.name, '**', '*.pdf'), recursive=True)
            for p in pdf_paths:
                with open(p, 'rb') as pf:
                    pdf_files.append((pf.read(), os.path.basename(p)))

        # Estrai payslips da tutti i PDF raccolti
        # Prima usa il parser multi-template (più completo), poi fallback al parser semplice
        payslips = []
        parse_errors = []  # Traccia errori per report
        
        for pdf_bytes, pdf_filename in pdf_files:
            parsed_data = None
            parse_method = "unknown"
            
            # Prova prima con il parser multi-template
            if HAS_MULTI_TEMPLATE_PARSER:
                try:
                    from app.parsers.busta_paga_multi_template import parse_busta_paga_from_bytes, extract_summary
                    result = parse_busta_paga_from_bytes(pdf_bytes)
                    
                    if result.get("parse_success"):
                        summary = extract_summary(result)
                        parsed_data = {
                            "nome_completo": summary.get("dipendente_nome"),
                            "codice_fiscale": summary.get("codice_fiscale"),
                            "mese": summary.get("mese"),
                            "anno": summary.get("anno"),
                            "periodo": f"{summary.get('mese', '?')}/{summary.get('anno', '?')}",
                            "retribuzione_netta": summary.get("netto"),
                            "lordo": summary.get("lordo"),
                            "trattenute": summary.get("trattenute"),
                            "ore_lavorate": summary.get("ore_lavorate"),
                            "giorni_lavorati": summary.get("giorni_lavorati"),
                            "inps_dipendente": summary.get("inps_dipendente"),
                            "irpef": summary.get("irpef"),
                            "tfr_quota": summary.get("tfr_quota"),
                            "ferie_residuo": summary.get("ferie_residuo"),
                            "permessi_residuo": summary.get("permessi_residuo"),
                            "template": result.get("template"),
                            "tipo_cedolino": result.get("tipo_cedolino"),
                            "_pdf_bytes": pdf_bytes,
                            "_pdf_filename": pdf_filename,
                            "_parse_method": "multi_template"
                        }
                        parse_method = "multi_template"
                        logger.info(f"Parsed {pdf_filename} con multi-template: {result.get('template')}")
                except Exception as e:
                    logger.warning(f"Errore parser multi-template per {pdf_filename}: {e}")
            
            # Fallback al parser semplice se multi-template fallisce
            if not parsed_data:
                extracted = parse_payslip_simple(pdf_bytes)
                if extracted and len(extracted) >= 1 and not extracted[0].get('error'):
                    for payslip in extracted:
                        payslip['_pdf_bytes'] = pdf_bytes
                        payslip['_pdf_filename'] = pdf_filename
                        payslip['_parse_method'] = "simple"
                    payslips.extend(extracted)
                    parse_method = "simple"
                else:
                    error_msg = extracted[0].get('error') if extracted else "Parse fallito"
                    parse_errors.append({
                        "filename": pdf_filename,
                        "error": error_msg
                    })
                    logger.warning(f"Errore parsing {pdf_filename}: {error_msg}")
                    continue
            else:
                payslips.append(parsed_data)

        # cleanup temp directory
        if tmp_dir is not None:
            try:
                tmp_dir.cleanup()
            except Exception:
                pass
        
        if not payslips:
            error_detail = "Nessuna busta paga trovata"
            if parse_errors:
                error_detail += f". Errori: {parse_errors[:5]}"
            raise HTTPException(status_code=400, detail=error_detail)
        
        if len(payslips) == 1 and payslips[0].get("error"):
            raise HTTPException(status_code=400, detail=payslips[0]["error"])
        
        db = Database.get_db()
        results = {"success": [], "duplicates": [], "errors": [], "total": len(payslips), "imported": 0, "skipped_duplicates": 0, "failed": 0}
        
        for payslip in payslips:
            try:
                cf = payslip.get("codice_fiscale", "")
                nome = payslip.get("nome_completo") or f"{payslip.get('cognome', '')} {payslip.get('nome', '')}".strip()
                periodo = payslip.get("periodo", "")
                
                # Se manca il CF, prova a cercarlo nell'anagrafica tramite nome
                existing = None
                emp_id = None
                is_new = False
                
                if cf:
                    # Cerca per CF
                    existing = await db[Collections.EMPLOYEES].find_one({"codice_fiscale": cf}, {"_id": 0, "id": 1, "nome_completo": 1, "codice_fiscale": 1})
                
                if not existing and nome:
                    # Fallback: cerca per nome simile
                    nome_upper = nome.upper().strip()
                    # Cerca con fuzzy match sul nome
                    all_employees = await db[Collections.EMPLOYEES].find({}, {"_id": 0, "id": 1, "nome_completo": 1, "codice_fiscale": 1, "cognome": 1, "nome": 1}).to_list(500)
                    
                    for emp in all_employees:
                        emp_nome_completo = (emp.get("nome_completo") or "").upper().strip()
                        emp_cognome = (emp.get("cognome") or "").upper().strip()
                        emp_nome = (emp.get("nome") or "").upper().strip()
                        
                        # Match esatto sul nome completo
                        if emp_nome_completo and emp_nome_completo == nome_upper:
                            existing = emp
                            cf = emp.get("codice_fiscale", cf)
                            logger.info(f"Match dipendente per nome completo: {nome} -> CF: {cf}")
                            break
                        
                        # Match su cognome + nome separati
                        emp_full = f"{emp_cognome} {emp_nome}".strip()
                        if emp_full and emp_full == nome_upper:
                            existing = emp
                            cf = emp.get("codice_fiscale", cf)
                            logger.info(f"Match dipendente per cognome+nome: {nome} -> CF: {cf}")
                            break
                        
                        # Match parziale (contiene)
                        if emp_nome_completo and nome_upper in emp_nome_completo:
                            existing = emp
                            cf = emp.get("codice_fiscale", cf)
                            logger.info(f"Match parziale dipendente: {nome} -> {emp_nome_completo} -> CF: {cf}")
                            break
                
                if not cf and not existing:
                    results["errors"].append({"nome": nome or "?", "error": "CF mancante e dipendente non trovato in anagrafica"})
                    results["failed"] += 1
                    continue
                
                periodo = payslip.get("periodo", "")
                
                # Se abbiamo già trovato il dipendente, usa quello
                if existing:
                    emp_id = existing.get("id")
                    update = {}
                    # Aggiorna nome_completo se mancante o era un periodo
                    existing_name = existing.get("nome_completo", "")
                    if nome and (not existing_name or any(m in str(existing_name).lower() for m in ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"])):
                        update["nome_completo"] = nome
                        update["name"] = nome
                    if payslip.get("qualifica"):
                        update["qualifica"] = payslip["qualifica"]
                    if payslip.get("matricola"):
                        update["matricola"] = payslip["matricola"]
                    if update:
                        await db[Collections.EMPLOYEES].update_one({"id": emp_id}, {"$set": update})
                    is_new = False
                else:
                    # Crea nuovo dipendente
                    emp_id = str(uuid.uuid4())
                    new_employee_doc = {
                        "id": emp_id, "nome_completo": nome, "matricola": payslip.get("matricola", ""),
                        "codice_fiscale": cf, "qualifica": payslip.get("qualifica", ""),
                        "status": "active", "source": "pdf_upload", "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    await db[Collections.EMPLOYEES].insert_one(new_employee_doc.copy())
                    is_new = True
                
                # Check duplicate payslip - ora usa cedolini
                # Estrai mese e anno dal periodo
                mese_num = None
                anno_num = None
                periodo = payslip.get("periodo", "")
                if periodo and "/" in periodo:
                    parts = periodo.split("/")
                    if len(parts) == 2:
                        try:
                            mese_num = int(parts[0])
                            anno_num = int(parts[1])
                        except Exception:
                            pass
                
                # Controlla duplicato in cedolini (collection unificata)
                if cf and mese_num and anno_num:
                    existing_cedolino = await db["cedolini"].find_one({
                        "codice_fiscale": cf,
                        "mese": mese_num,
                        "anno": anno_num
                    }, {"_id": 1})
                    if existing_cedolino:
                        results["duplicates"].append({"nome": nome, "periodo": periodo})
                        results["skipped_duplicates"] += 1
                        continue
                
                payslip_id = str(uuid.uuid4())
                mese = payslip.get("mese", "") or (str(mese_num) if mese_num else "")
                anno = payslip.get("anno", "") or (str(anno_num) if anno_num else "")

                # Importo netto (minimale): prendiamo SOLO il netto finale
                importo_busta = float(payslip.get("retribuzione_netta") or 0)
                importo_lordo = float(payslip.get("lordo") or 0)
                
                # Allegato PDF: salviamo i byte originali del file caricato
                import base64
                pdf_b64 = None
                pdf_filename = payslip.get("_pdf_filename")
                pdf_bytes = payslip.get("_pdf_bytes")
                
                if pdf_bytes:
                    pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
                elif filename.endswith('.pdf'):
                    pdf_b64 = base64.b64encode(content).decode('utf-8')
                    pdf_filename = file.filename

                # Save in cedolini (collection unificata) con tutti i dati estratti
                # Controlla duplicati per CF + mese + anno prima di inserire
                dup_check = None
                if cf and mese and anno:
                    dup_check = await db["cedolini"].find_one({
                        "codice_fiscale": cf,
                        "mese": int(mese) if mese else None,
                        "anno": int(anno) if anno else None
                    })
                if dup_check:
                    logger.info(f"Cedolino già presente per CF={cf} mese={mese}/{anno}, skip")
                    continue
                cedolino_doc = {
                    "id": payslip_id,
                    "dipendente_id": emp_id,
                    "codice_fiscale": cf,
                    "dipendente_nome": nome,
                    "nome_dipendente": nome,  # Retrocompatibilità
                    "mese": int(mese) if mese else None,
                    "anno": int(anno) if anno else None,
                    "periodo": periodo,
                    # Dati estratti dal parser multi-template
                    "lordo": importo_lordo,
                    "netto": importo_busta,
                    "netto_mese": importo_busta,
                    "totale_trattenute": float(payslip.get("trattenute") or 0),
                    "ore_lavorate": float(payslip.get("ore_lavorate") or 0),
                    "giorni_lavorati": int(payslip.get("giorni_lavorati") or 0) if payslip.get("giorni_lavorati") else None,
                    "inps_dipendente": float(payslip.get("inps_dipendente") or 0),
                    "irpef": float(payslip.get("irpef") or 0),
                    "tfr_quota": float(payslip.get("tfr_quota") or 0),
                    "ferie_residuo": payslip.get("ferie_residuo"),
                    "permessi_residuo": payslip.get("permessi_residuo"),
                    # Metadata
                    "template_rilevato": payslip.get("template"),
                    "tipo_cedolino": payslip.get("tipo_cedolino", "mensile"),
                    "parse_method": payslip.get("_parse_method", "unknown"),
                    "acconto": float(payslip.get("acconto", 0) or 0),
                    "differenza": float(payslip.get("differenza", 0) or 0),
                    "source": "pdf_upload",
                    "filename": pdf_filename or file.filename,
                    "pdf_filename": pdf_filename,
                    "pdf_data": pdf_b64,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    # Flag per cedolini problematici
                    "parse_success": importo_lordo > 0 or importo_busta != 0,
                    "needs_review": importo_lordo == 0 and importo_busta == 0
                }
                await db["cedolini"].insert_one(cedolino_doc.copy())
                
                # === AUTOMAZIONE PRIMA NOTA SALARI ===
                # Crea automaticamente una scrittura in prima_nota_salari per ogni cedolino caricato
                prima_nota_creata = False
                if importo_busta != 0 and anno and mese:  # Anche netto negativo (es. SOS)
                    try:
                        import calendar
                        anno_int = int(anno)
                        mese_int = int(mese)
                        ultimo_giorno = calendar.monthrange(anno_int, mese_int)[1]
                        data_pagamento = f"{anno_int}-{mese_int:02d}-{ultimo_giorno:02d}"
                    except (ValueError, TypeError):
                        data_pagamento = f"{anno}-{str(mese).zfill(2)}-28"
                    
                    # Verifica se esiste già un movimento salari per questo dipendente/periodo
                    existing_salario = await db["prima_nota_salari"].find_one({
                        "$or": [
                            {"codice_fiscale": cf, "mese": int(mese), "anno": int(anno)},
                            {"dipendente": nome.upper() if nome else "", "mese": int(mese), "anno": int(anno)}
                        ]
                    })
                    
                    if existing_salario:
                        # Collega il cedolino al movimento esistente
                        await db["prima_nota_salari"].update_one(
                            {"id": existing_salario["id"]},
                            {"$set": {
                                "cedolino_id": payslip_id,
                                "importo_busta": importo_busta,
                                "codice_fiscale": cf,
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }}
                        )
                        logger.info(f"Prima Nota Salari collegata: {nome} ({periodo})")
                        prima_nota_creata = True
                    else:
                        # Crea nuovo movimento in attesa di riconciliazione
                        # Segue la struttura esistente della collection prima_nota_salari
                        mese_nomi = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", 
                                    "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", 
                                    "Novembre", "Dicembre"]
                        mese_nome = mese_nomi[int(mese)] if mese and int(mese) <= 12 else ""
                        
                        movimento_salario = {
                            "id": str(uuid.uuid4()),
                            "dipendente": nome.upper() if nome else "",
                            "codice_fiscale": cf,
                            "cedolino_id": payslip_id,
                            "anno": int(anno),
                            "mese": int(mese),
                            "mese_nome": mese_nome,
                            "importo_busta": importo_busta,
                            "importo_bonifico": 0,  # Da riconciliare con pagamento bancario
                            "saldo": importo_busta,  # Saldo = importo_busta - importo_bonifico
                            "progressivo": 0,
                            "riconciliato": False,  # In attesa di riconciliazione
                            "source": "cedolino_upload",
                            "imported_at": datetime.now(timezone.utc).isoformat()
                        }
                        await db["prima_nota_salari"].insert_one(movimento_salario.copy())
                        logger.info(f"Prima Nota Salari CREATA: €{importo_busta} per {nome} ({periodo})")
                        prima_nota_creata = True
                
                results["success"].append({"nome": nome, "periodo": periodo, "netto": importo_busta, "is_new": is_new, "prima_nota": prima_nota_creata})
                results["imported"] += 1
                
            except Exception as e:
                logger.error(f"Errore payslip: {e}")
                results["errors"].append({"nome": payslip.get("nome_completo", "?"), "error": str(e)})
                results["failed"] += 1
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ============== CEDOLINI DA RIVEDERE ==============

@router.get("/cedolini/da-rivedere")
async def get_cedolini_da_rivedere():
    """
    Restituisce i cedolini che necessitano revisione manuale:
    - lordo = 0 e netto = 0 (parsing completamente fallito)
    - needs_review = True
    - parse_success = False
    """
    db = Database.get_db()
    
    cedolini = await db["cedolini"].find({
        "$or": [
            {"needs_review": True},
            {"parse_success": False},
            {"$and": [
                {"lordo": {"$in": [0, None]}},
                {"netto": {"$in": [0, None]}}
            ]}
        ]
    }, {
        "_id": 0,
        "pdf_data": 0  # Escludi PDF per performance
    }).sort([("anno", -1), ("mese", -1)]).to_list(500)
    
    return {
        "count": len(cedolini),
        "cedolini": cedolini
    }


@router.get("/cedolini/statistiche-parsing")
async def get_statistiche_parsing():
    """
    Restituisce statistiche sui cedolini parsati:
    - Per template
    - Per anno
    - Con/senza lordo
    - Con/senza errori
    """
    db = Database.get_db()
    
    # Totali
    totale = await db["cedolini"].count_documents({})
    con_pdf = await db["cedolini"].count_documents({"pdf_data": {"$exists": True, "$ne": None}})
    con_lordo = await db["cedolini"].count_documents({"lordo": {"$gt": 0}})
    con_lordo_zero = await db["cedolini"].count_documents({"lordo": 0})
    senza_lordo = await db["cedolini"].count_documents({"$or": [{"lordo": None}, {"lordo": {"$exists": False}}]})
    con_ore = await db["cedolini"].count_documents({"ore_lavorate": {"$gt": 0}})
    da_rivedere = await db["cedolini"].count_documents({
        "$or": [
            {"needs_review": True},
            {"parse_success": False},
            {"$and": [{"lordo": {"$in": [0, None]}}, {"netto": {"$in": [0, None]}}]}
        ]
    })
    
    # Per template
    pipeline_template = [
        {"$group": {"_id": "$template_rilevato", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    per_template = await db["cedolini"].aggregate(pipeline_template).to_list(10)
    
    # Per anno
    pipeline_anno = [
        {"$group": {"_id": "$anno", "count": {"$sum": 1}, "con_lordo": {"$sum": {"$cond": [{"$gt": ["$lordo", 0]}, 1, 0]}}}},
        {"$sort": {"_id": 1}}
    ]
    per_anno = await db["cedolini"].aggregate(pipeline_anno).to_list(20)
    
    return {
        "totale": totale,
        "con_pdf": con_pdf,
        "con_lordo": con_lordo,
        "con_lordo_zero": con_lordo_zero,
        "senza_lordo": senza_lordo,
        "con_ore_lavorate": con_ore,
        "da_rivedere": da_rivedere,
        "per_template": {r["_id"] or "sconosciuto": r["count"] for r in per_template},
        "per_anno": {str(r["_id"]): {"totale": r["count"], "con_lordo": r["con_lordo"]} for r in per_anno if r["_id"]}
    }


@router.post("/cedolini/{cedolino_id}/segna-revisionato")
async def segna_cedolino_revisionato(cedolino_id: str, dati: Dict[str, Any] = Body(...)):
    """
    Aggiorna un cedolino dopo revisione manuale.
    Permette di inserire lordo, netto e altri dati mancanti.
    """
    db = Database.get_db()
    
    # Trova il cedolino
    cedolino = await db["cedolini"].find_one({"id": cedolino_id})
    if not cedolino:
        raise HTTPException(status_code=404, detail="Cedolino non trovato")
    
    # Prepara update
    update_data = {
        "needs_review": False,
        "parse_success": True,
        "revised_at": datetime.now(timezone.utc).isoformat(),
        "revised_manually": True
    }
    
    # Aggiorna campi forniti
    allowed_fields = ["lordo", "netto", "ore_lavorate", "giorni_lavorati", 
                      "inps_dipendente", "irpef", "tfr_quota", "ferie_residuo", 
                      "permessi_residuo", "tipo_cedolino", "note"]
    
    for field in allowed_fields:
        if field in dati and dati[field] is not None:
            update_data[field] = dati[field]
    
    result = await db["cedolini"].update_one(
        {"id": cedolino_id},
        {"$set": update_data}
    )
    
    return {
        "success": result.modified_count > 0,
        "cedolino_id": cedolino_id,
        "updated_fields": list(update_data.keys())
    }

