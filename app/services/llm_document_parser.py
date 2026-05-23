"""
LLM Document Parser — Ceraldi ERP
==================================
Usa Claude (via Anthropic API) per estrarre dati strutturati dai PDF:
- Verbali: targa, numero, importo, data, ente
- F24: codici tributo, periodi, importi, sezioni
"""

import os
import json
import re
import base64
import tempfile
import logging
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

load_dotenv("backend/.env", override=True)

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


async def _ask_gemini_with_pdf(pdf_bytes: bytes, prompt: str, filename: str = "doc.pdf") -> Optional[str]:
    """Invia un PDF a Gemini e ottieni risposta strutturata."""
    from app.services.emergent_stub import LlmChat, UserMessage, FileContentWithMimeType
    
    if not ANTHROPIC_API_KEY:
        logger.error("[LLM-PARSER] ANTHROPIC_API_KEY non configurata")
        return None
    
    # Salva PDF temporaneo
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        
        chat = LlmChat(
            api_key=ANTHROPIC_API_KEY,
            session_id=f"parser-{filename[:20]}",
            system_message="Sei un parser di documenti italiani. Rispondi SOLO con JSON valido, senza markdown."
        ).with_model("gemini", "gemini-2.5-flash")
        
        pdf_file = FileContentWithMimeType(
            file_path=tmp_path,
            mime_type="application/pdf"
        )
        
        msg = UserMessage(text=prompt, file_contents=[pdf_file])
        response = await chat.send_message(msg)
        return response
        
    except Exception as e:
        logger.error(f"[LLM-PARSER] Errore Gemini: {e}")
        return None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


async def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Estrae testo da PDF con PyMuPDF (fallback pdfplumber)."""
    text = ""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
    except Exception:
        try:
            import pdfplumber
            import io
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text += t + "\n"
        except Exception as e:
            logger.debug(f"[LLM-PARSER] Estrazione testo fallita: {e}")
    return text.strip()


# ============================================================
# PARSER VERBALI
# ============================================================

PROMPT_VERBALE = """Analizza questo verbale/multa italiano ed estrai questi dati in formato JSON:
{
  "targa": "targa del veicolo (formato XX000XX, es: GG782PN)",
  "numero_verbale": "numero identificativo del verbale",
  "data_verbale": "data del verbale in formato YYYY-MM-DD",
  "importo": numero decimale dell'importo della sanzione (solo il numero, es: 42.50),
  "ente_emittente": "nome dell'ente che ha emesso il verbale",
  "tipo_violazione": "breve descrizione della violazione",
  "luogo": "luogo dell'infrazione"
}
Se un campo non è trovabile, usa null. Rispondi SOLO con il JSON."""


async def parse_verbale_pdf(pdf_bytes: bytes, filename: str = "") -> Dict[str, Any]:
    """
    Estrae dati strutturati da un verbale PDF.
    Prima prova estrazione testo + regex, poi LLM se necessario.
    """
    result = {"success": False, "targa": None, "numero_verbale": None, 
              "importo": None, "data_verbale": None, "ente_emittente": None}
    
    # Step 1: Estrai testo
    text = await _extract_text_from_pdf(pdf_bytes)
    
    # Step 2: Regex per targa
    if text:
        targa_match = re.search(r'\b([A-Z]{2}\d{3}[A-Z]{2})\b', text, re.IGNORECASE)
        if targa_match:
            result["targa"] = targa_match.group(1).upper()
        
        # Regex per importo
        importo_match = re.search(r'(?:importo|sanzione|pagare|euro|€)\s*[:\s]*(\d+[.,]\d{2})', text, re.IGNORECASE)
        if importo_match:
            result["importo"] = float(importo_match.group(1).replace(",", "."))
        
        # Regex per data
        data_match = re.search(r'(\d{2})[/.-](\d{2})[/.-](\d{4})', text)
        if data_match:
            result["data_verbale"] = f"{data_match.group(3)}-{data_match.group(2)}-{data_match.group(1)}"
    
    # Step 3: Se manca la targa, usa LLM
    if not result["targa"]:
        llm_response = await _ask_gemini_with_pdf(pdf_bytes, PROMPT_VERBALE, filename)
        if llm_response:
            try:
                # Pulisci risposta da markdown
                clean = llm_response.strip()
                if clean.startswith("```"):
                    clean = re.sub(r'^```\w*\n?', '', clean)
                    clean = re.sub(r'\n?```$', '', clean)
                data = json.loads(clean)
                result.update({k: v for k, v in data.items() if v is not None})
                result["source"] = "llm"
            except json.JSONDecodeError:
                logger.debug(f"[LLM-PARSER] JSON non valido da Gemini: {llm_response[:200]}")
    else:
        result["source"] = "regex"
    
    result["success"] = result["targa"] is not None
    return result


# ============================================================
# PARSER F24
# ============================================================

PROMPT_F24 = """Analizza questo modello F24 italiano ed estrai i dati in formato JSON:
{
  "contribuente": {
    "codice_fiscale": "codice fiscale",
    "denominazione": "nome/ragione sociale"
  },
  "data_pagamento": "data in formato YYYY-MM-DD",
  "sezione_erario": [
    {"codice_tributo": "4 cifre", "periodo_riferimento": "MM/YYYY", "importo_debito": numero, "importo_credito": numero}
  ],
  "sezione_inps": [
    {"causale": "codice", "periodo_da": "MM/YYYY", "periodo_a": "MM/YYYY", "importo_debito": numero}
  ],
  "sezione_regioni": [
    {"codice_tributo": "4 cifre", "periodo_riferimento": "YYYY", "importo_debito": numero}
  ],
  "sezione_imu": [
    {"codice_tributo": "4 cifre", "codice_comune": "stringa", "importo_debito": numero}
  ],
  "totale_versato": numero
}
Estrai TUTTI i codici tributo. Se una sezione è vuota, usa array vuoto []. Rispondi SOLO JSON."""


async def parse_f24_pdf(pdf_bytes: bytes, filename: str = "") -> Dict[str, Any]:
    """
    Estrae dati strutturati da un F24 PDF usando LLM.
    """
    result = {"success": False, "sezione_erario": [], "sezione_inps": [], 
              "sezione_regioni": [], "sezione_imu": [], "totale_versato": 0}
    
    # Prova prima estrazione testo per dati base
    text = await _extract_text_from_pdf(pdf_bytes)
    
    # Usa LLM per parsing strutturato
    llm_response = await _ask_gemini_with_pdf(pdf_bytes, PROMPT_F24, filename)
    if llm_response:
        try:
            clean = llm_response.strip()
            if clean.startswith("```"):
                clean = re.sub(r'^```\w*\n?', '', clean)
                clean = re.sub(r'\n?```$', '', clean)
            data = json.loads(clean)
            result.update(data)
            result["success"] = True
            result["source"] = "llm"
            
            # Conta tributi trovati
            n_tributi = (len(result.get("sezione_erario", [])) + 
                        len(result.get("sezione_inps", [])) + 
                        len(result.get("sezione_regioni", [])) +
                        len(result.get("sezione_imu", [])))
            logger.info(f"[LLM-PARSER] F24 {filename}: {n_tributi} tributi estratti, totale €{result.get('totale_versato', 0)}")
        except json.JSONDecodeError:
            logger.debug(f"[LLM-PARSER] F24 JSON non valido: {llm_response[:200]}")
    
    # Fallback: regex su testo estratto
    if not result["success"] and text:
        codici = re.findall(r'\b(\d{4})\b', text)
        codici_tributo_validi = [c for c in codici if c[0] in '1234567890' and int(c) > 999]
        if codici_tributo_validi:
            result["sezione_erario"] = [{"codice_tributo": c, "importo_debito": 0} for c in codici_tributo_validi[:10]]
            result["success"] = True
            result["source"] = "regex_fallback"
    
    return result


# ============================================================
# BATCH PROCESSING
# ============================================================

async def batch_parse_verbali(db, limit: int = 50) -> Dict[str, Any]:
    """Processa verbali senza targa usando LLM."""
    stats = {"processati": 0, "targa_trovata": 0, "errori": 0, "skipped": 0}
    
    cursor = db["verbali_noleggio"].find(
        {"$or": [{"targa": None}, {"targa": ""}], "pdf_data": {"$ne": None}},
        {"_id": 0}
    ).limit(limit)
    
    # Carica veicoli per lookup
    veicoli = {}
    async for v in db["veicoli_noleggio"].find({}, {"_id": 0}):
        if v.get("targa"):
            veicoli[v["targa"].upper()] = v
    
    async for verbale in cursor:
        try:
            pdf_data = verbale.get("pdf_data")
            if not pdf_data:
                stats["skipped"] += 1
                continue
            
            pdf_bytes = base64.b64decode(pdf_data)
            parsed = await parse_verbale_pdf(pdf_bytes, verbale.get("pdf_filename", ""))
            
            if parsed.get("targa"):
                targa = parsed["targa"].upper()
                update = {"targa": targa}
                
                if parsed.get("importo"):
                    update["importo"] = parsed["importo"]
                if parsed.get("data_verbale"):
                    update["data_verbale"] = parsed["data_verbale"]
                if parsed.get("ente_emittente"):
                    update["ente_emittente"] = parsed["ente_emittente"]
                if parsed.get("numero_verbale") and verbale.get("numero_verbale", "").startswith("VERB-"):
                    update["numero_verbale"] = parsed["numero_verbale"]
                
                # Cerca driver per questa targa
                veicolo = veicoli.get(targa)
                if veicolo:
                    update["driver"] = veicolo.get("driver")
                    update["driver_id"] = veicolo.get("driver_id")
                    update["driver_cf"] = veicolo.get("driver_cf")
                    update["veicolo_marca"] = veicolo.get("marca")
                    update["veicolo_modello"] = veicolo.get("modello")
                    update["fornitore_noleggio"] = veicolo.get("fornitore_noleggio")
                
                update["stato"] = "identificato" if veicolo else "salvato"
                update["parsed_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
                
                await db["verbali_noleggio"].update_one(
                    {"id": verbale["id"]},
                    {"$set": update}
                )
                stats["targa_trovata"] += 1
                logger.info(f"[BATCH-VERBALI] {verbale.get('numero_verbale')}: targa={targa} driver={update.get('driver','?')}")
            
            stats["processati"] += 1
            
        except Exception as e:
            logger.error(f"[BATCH-VERBALI] Errore: {e}")
            stats["errori"] += 1
    
    return stats


async def batch_parse_f24(db, limit: int = 50) -> Dict[str, Any]:
    """Processa F24 PDF usando LLM per estrarre codici tributo."""
    stats = {"processati": 0, "con_tributi": 0, "errori": 0, "nuovi_f24": 0}
    
    cursor = db["f24_email_attachments"].find(
        {"pdf_data": {"$ne": None}},
        {"_id": 0}
    ).limit(limit)
    
    async for doc in cursor:
        try:
            pdf_bytes = base64.b64decode(doc["pdf_data"])
            filename = doc.get("filename", "f24.pdf")
            
            parsed = await parse_f24_pdf(pdf_bytes, filename)
            
            if parsed.get("success"):
                # Check dedup
                existing = await db["f24_commercialista"].find_one({"pdf_hash": doc.get("pdf_hash")})
                if not existing:
                    import uuid
                    from datetime import datetime, timezone
                    
                    f24_doc = {
                        "id": str(uuid.uuid4()),
                        "filename": filename,
                        "pdf_data": doc["pdf_data"],
                        "pdf_hash": doc.get("pdf_hash"),
                        "contribuente": parsed.get("contribuente", {}),
                        "data_pagamento": parsed.get("data_pagamento"),
                        "sezione_erario": parsed.get("sezione_erario", []),
                        "sezione_inps": parsed.get("sezione_inps", []),
                        "sezione_regioni": parsed.get("sezione_regioni", []),
                        "sezione_tributi_locali": parsed.get("sezione_imu", []),
                        "totale_versato": parsed.get("totale_versato", 0),
                        "status": "importato",
                        "riconciliato": False,
                        "source": "gmail_llm_parse",
                        "imported_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await db["f24_commercialista"].insert_one(f24_doc)
                    stats["nuovi_f24"] += 1
                
                stats["con_tributi"] += 1
            
            stats["processati"] += 1
            
        except Exception as e:
            logger.error(f"[BATCH-F24] Errore: {e}")
            stats["errori"] += 1
    
    return stats



async def batch_extract_importi_verbali(db, limit: int = 76) -> Dict[str, Any]:
    """
    Estrae SOLO l'importo dai verbali che hanno PDF ma importo mancante.
    Usa prima regex sul testo, poi LLM come fallback.
    Più veloce di batch_parse_verbali perché non cerca targa.
    """
    from datetime import datetime, timezone as tz
    stats = {"processati": 0, "importi_trovati": 0, "errori": 0, "skipped": 0}
    
    cursor = db["verbali_noleggio"].find(
        {
            "$or": [{"importo": None}, {"importo": 0}, {"importo": {"$exists": False}}],
            "pdf_data": {"$ne": None}
        },
        {"_id": 0}
    ).limit(limit)
    
    async for verbale in cursor:
        try:
            pdf_data = verbale.get("pdf_data")
            if not pdf_data:
                stats["skipped"] += 1
                continue
            
            pdf_bytes = base64.b64decode(pdf_data)
            importo = None
            data_verbale = None
            
            # Step 1: Estrai testo e cerca importo con regex
            text = await _extract_text_from_pdf(pdf_bytes)
            if text:
                # Pattern importo in documenti italiani
                patterns = [
                    r'(?:importo|sanzione|pagare|dovut[oa]|totale|somma)\s*(?:di)?\s*(?:euro|€)?\s*[:\s]*(\d+[.,]\d{2})',
                    r'€\s*(\d+[.,]\d{2})',
                    r'euro\s+(\d+[.,]\d{2})',
                    r'(\d+[.,]\d{2})\s*(?:euro|€)',
                    r'importo\s+ridotto[:\s]*(\d+[.,]\d{2})',
                    r'misura\s+ridotta[:\s]*(\d+[.,]\d{2})',
                ]
                for p in patterns:
                    m = re.search(p, text, re.IGNORECASE)
                    if m:
                        importo = float(m.group(1).replace(",", "."))
                        if importo > 5 and importo < 50000:  # Sanity check
                            break
                        importo = None
                
                # Cerca data
                dm = re.search(r'(\d{2})[/.-](\d{2})[/.-](\d{4})', text)
                if dm:
                    data_verbale = f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}"
            
            # Step 2: Se regex fallisce, usa LLM
            if importo is None:
                prompt = "Estrai SOLO l'importo della sanzione/multa da questo documento. Rispondi con un JSON: {\"importo\": numero, \"data\": \"YYYY-MM-DD\"}. Se non trovi importo, rispondi {\"importo\": null}."
                llm_resp = await _ask_gemini_with_pdf(pdf_bytes, prompt, verbale.get("pdf_filename", ""))
                if llm_resp:
                    try:
                        clean = llm_resp.strip()
                        if clean.startswith("```"):
                            clean = re.sub(r'^```\w*\n?', '', clean)
                            clean = re.sub(r'\n?```$', '', clean)
                        data = json.loads(clean)
                        if data.get("importo") and float(data["importo"]) > 0:
                            importo = float(data["importo"])
                        if data.get("data"):
                            data_verbale = data["data"]
                    except (json.JSONDecodeError, ValueError):
                        pass
            
            # Aggiorna verbale
            if importo is not None and importo > 0:
                update = {"importo": importo}
                if data_verbale:
                    update["data_verbale"] = data_verbale
                update["importo_parsed_at"] = datetime.now(tz.utc).isoformat()
                
                await db["verbali_noleggio"].update_one(
                    {"id": verbale["id"]},
                    {"$set": update}
                )
                stats["importi_trovati"] += 1
                logger.info(f"[BATCH-IMPORTI] {verbale.get('numero_verbale','')}: €{importo}")
            
            stats["processati"] += 1
            
        except Exception as e:
            logger.error(f"[BATCH-IMPORTI] Errore: {e}")
            stats["errori"] += 1
    
    logger.info(f"[BATCH-IMPORTI] Completato: {stats}")
    return stats



PROMPT_NUMERO_VERBALE = """Questo è un documento relativo a un verbale/multa/sanzione italiano.
Estrai SOLO il NUMERO del VERBALE (numero identificativo ufficiale del verbale, non il numero PEC o protocollo).
Il numero verbale ha tipicamente formati come:
- A25110648977 (lettera + 11 cifre)  
- T23260465978
- S22280043251
- ZL18173182511
- 0007016241 (solo cifre)
- 302000600008408304

NON usare numeri PEC, protocollo email o ID documento.
Rispondi con JSON: {"numero_verbale": "il numero trovato"}
Se non trovi il numero verbale, rispondi: {"numero_verbale": null}"""


async def batch_fix_numeri_verbali(db, limit: int = 102) -> Dict[str, Any]:
    """
    Corregge i numeri verbale PEC-xxx/DOC-xxx/RELATA-xxx estraendo 
    il vero numero dal testo del PDF o tramite LLM.
    """
    from datetime import datetime, timezone as tz
    stats = {"processati": 0, "corretti": 0, "errori": 0, "skipped": 0, "gia_ok": 0}
    
    cursor = db["verbali_noleggio"].find(
        {
            "numero_verbale": {"$regex": "^(PEC-|DOC-|RELATA-|PRERUOLO-|VERB-)"},
            "pdf_data": {"$exists": True, "$ne": ""}
        },
        {"_id": 0}
    ).limit(limit)
    
    docs = await cursor.to_list(length=limit)
    logger.info(f"[FIX-NUMERI] {len(docs)} verbali da correggere")
    
    for verbale in docs:
        try:
            pdf_data = verbale.get("pdf_data")
            if not pdf_data:
                stats["skipped"] += 1
                continue
            
            pdf_bytes = base64.b64decode(pdf_data)
            old_numero = verbale.get("numero_verbale", "")
            new_numero = None
            
            # Step 1: Estrai testo e cerca con regex
            text = await _extract_text_from_pdf(pdf_bytes)
            if text:
                # Pattern numeri verbale italiani
                patterns = [
                    # Lettera + 11-14 cifre (formato più comune)
                    r'\b([A-Z]\d{11,14})\b',
                    # Due lettere + 10-14 cifre
                    r'\b([A-Z]{2}\d{10,14})\b',
                    # Numero verbale esplicito
                    r'(?:verbale|n\.|nr\.|numero)\s*[:\s]*([A-Z0-9]{8,20})',
                    # Numero protocollo lungo (solo cifre, 12+)
                    r'\b(\d{12,18})\b',
                    # Codice obbligazione
                    r'(?:obbligazione|obbl\.?)\s*[:\s]*(\d{8,15})',
                ]
                
                for p in patterns:
                    matches = re.findall(p, text, re.IGNORECASE)
                    for m in matches:
                        candidate = m.upper().strip()
                        # Filtra falsi positivi
                        if len(candidate) >= 8 and not candidate.startswith("IT") and candidate != old_numero:
                            # Non usare P.IVA, IBAN, codici fiscali
                            if not re.match(r'^\d{11}$', candidate):  # P.IVA
                                if not re.match(r'^[A-Z]{6}\d{2}', candidate):  # CF
                                    new_numero = candidate
                                    break
                    if new_numero:
                        break
            
            # Step 2: Se regex fallisce, usa LLM
            if not new_numero:
                llm_resp = await _ask_gemini_with_pdf(pdf_bytes, PROMPT_NUMERO_VERBALE, verbale.get("pdf_filename", ""))
                if llm_resp:
                    try:
                        clean = llm_resp.strip()
                        if clean.startswith("```"):
                            clean = re.sub(r'^```\w*\n?', '', clean)
                            clean = re.sub(r'\n?```$', '', clean)
                        data = json.loads(clean)
                        if data.get("numero_verbale"):
                            candidate = str(data["numero_verbale"]).strip()
                            if len(candidate) >= 5 and candidate != old_numero:
                                new_numero = candidate
                    except (json.JSONDecodeError, ValueError):
                        pass
            
            # Aggiorna se trovato un numero migliore
            if new_numero and new_numero != old_numero:
                update = {
                    "numero_verbale": new_numero,
                    "numero_verbale_old": old_numero,
                    "numero_fixed_at": datetime.now(tz.utc).isoformat()
                }
                await db["verbali_noleggio"].update_one(
                    {"id": verbale["id"]},
                    {"$set": update}
                )
                
                # Aggiorna anche trattenute collegate
                await db["trattenute_dipendenti"].update_many(
                    {"verbale_id": verbale["id"]},
                    {"$set": {
                        "numero_verbale": new_numero,
                        "descrizione": f"Verbale {new_numero} - Targa {verbale.get('targa', '')}"
                    }}
                )
                
                stats["corretti"] += 1
                logger.info(f"[FIX-NUMERI] {old_numero} → {new_numero}")
            else:
                stats["gia_ok"] += 1
            
            stats["processati"] += 1
            
        except Exception as e:
            logger.error(f"[FIX-NUMERI] Errore {verbale.get('numero_verbale','')}: {e}")
            stats["errori"] += 1
    
    logger.info(f"[FIX-NUMERI] Completato: {stats}")
    return stats
