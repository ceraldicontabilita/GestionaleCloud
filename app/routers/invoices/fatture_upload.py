"""
Fatture XML Upload Router - Gestione upload fatture elettroniche.
Supporta upload singolo XML, multiplo XML e file ZIP.
Include popolamento automatico tracciabilità HACCP.
Include riconciliazione automatica con estratto conto per numeri assegni.
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import uuid
import logging
import zipfile
import io
import re

from pymongo.errors import DuplicateKeyError

from app.database import Database, Collections
from app.parsers.fattura_elettronica_parser import parse_fattura_xml
from app.utils.warehouse_helpers import auto_populate_warehouse_from_invoice
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


async def ensure_supplier_exists(db, parsed_invoice: Dict[str, Any], session=None) -> Dict[str, Any]:
    """
    Verifica se il fornitore esiste. Se sì, aggiorna i campi anagrafici mancanti.
    Se non esiste, lo crea automaticamente con i dati dalla fattura XML.

    session: sessione Mongo opzionale, per partecipare a una transazione del
    chiamante (es. process_fattura_to_db). None per gli altri chiamanti.
    """
    supplier_vat = parsed_invoice.get("supplier_vat") or ""
    supplier_name = parsed_invoice.get("supplier_name") or "Fornitore Sconosciuto"

    result = {
        "supplier_exists": False,
        "supplier_created": False,
        "supplier_updated": False,
        "alert_created": False,
        "supplier_id": None,
        "metodo_pagamento": None
    }

    if not supplier_vat:
        return result

    # Cerca fornitore per P.IVA (supporta sia 'piva' che 'partita_iva' come field name)
    existing = await db[Collections.SUPPLIERS].find_one(
        {"$or": [
            {"partita_iva": supplier_vat},
            {"piva": supplier_vat}
        ]},
        {"_id": 0},
        session=session
    )

    # Se non trovato per P.IVA, cerca per denominazione/nome
    if not existing and supplier_name:
        import re as _re
        safe_name = _re.escape(supplier_name[:30])
        existing = await db[Collections.SUPPLIERS].find_one(
            {"$or": [
                {"nome": {"$regex": f"^{safe_name}", "$options": "i"}},
                {"ragione_sociale": {"$regex": f"^{safe_name}", "$options": "i"}},
                {"denominazione": {"$regex": f"^{safe_name}", "$options": "i"}}
            ]},
            {"_id": 0},
            session=session
        )

    fornitore_data = parsed_invoice.get("fornitore") or {}

    if existing:
        result["supplier_exists"] = True
        result["supplier_id"] = existing.get("id")
        result["metodo_pagamento"] = existing.get("metodo_pagamento")

        # Aggiorna SEMPRE i campi anagrafici mancanti (non sovrascrive quelli già compilati)
        update_data = {}
        field_map = {
            "partita_iva": supplier_vat,
            "piva": supplier_vat,
            "nome": supplier_name,
            "ragione_sociale": existing.get("ragione_sociale") or supplier_name,
            "codice_fiscale": fornitore_data.get("codice_fiscale") or existing.get("codice_fiscale") or supplier_vat,
            "indirizzo": fornitore_data.get("indirizzo") or existing.get("indirizzo") or "",
            "cap": fornitore_data.get("cap") or existing.get("cap") or "",
            "comune": fornitore_data.get("comune") or existing.get("comune") or "",
            "provincia": fornitore_data.get("provincia") or existing.get("provincia") or "",
            "nazione": fornitore_data.get("nazione") or existing.get("nazione") or "IT",
        }
        for field, value in field_map.items():
            if value and not existing.get(field):
                update_data[field] = value

        if update_data:
            update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            update_data["dati_incompleti"] = False
            await db[Collections.SUPPLIERS].update_one(
                {"id": existing["id"]},
                {"$set": update_data},
                session=session
            )
            result["supplier_updated"] = True
            logger.info(f"Fornitore {supplier_name} aggiornato con dati XML: {list(update_data.keys())}")

        return result

    # Fornitore non esiste — CREA
    new_supplier = {
        "id": str(uuid.uuid4()),
        "nome": supplier_name,
        "ragione_sociale": supplier_name,
        "partita_iva": supplier_vat,
        "piva": supplier_vat,
        "codice_fiscale": fornitore_data.get("codice_fiscale") or supplier_vat,
        "indirizzo": fornitore_data.get("indirizzo") or "",
        "cap": fornitore_data.get("cap") or "",
        "comune": fornitore_data.get("comune") or "",
        "provincia": fornitore_data.get("provincia") or "",
        "nazione": fornitore_data.get("nazione") or "IT",
        "metodo_pagamento": None,
        "giorni_pagamento": 30,
        "iban": "",
        "fatture_count": 1,
        "source": "auto_from_invoice",
        "dati_incompleti": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Creato automaticamente da fattura — configurare metodo pagamento"
    }

    await db[Collections.SUPPLIERS].insert_one(new_supplier.copy(), session=session)
    result["supplier_created"] = True
    result["supplier_id"] = new_supplier["id"]
    logger.info(f"Nuovo fornitore creato: {supplier_name} (P.IVA: {supplier_vat})")

    # Alert per configurare il metodo di pagamento
    alert = {
        "id": str(uuid.uuid4()),
        "tipo": "fornitore_senza_metodo_pagamento",
        "titolo": f"Configura metodo pagamento per {supplier_name}",
        "messaggio": f"{supplier_name} (P.IVA: {supplier_vat}) creato da fattura. Configura il metodo di pagamento.",
        "fornitore_id": new_supplier["id"],
        "fornitore_piva": supplier_vat,
        "fornitore_nome": supplier_name,
        "priorita": "alta",
        "letto": False,
        "risolto": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "link": f"/fornitori?piva={supplier_vat}"
    }
    await db["alerts"].insert_one(alert.copy(), session=session)
    result["alert_created"] = True

    return result


async def process_fattura_to_db(db, parsed: Dict[str, Any], filename: str = "upload.xml") -> Dict[str, Any]:
    """
    Processa e salva una fattura parsata nel database.
    Usata da documenti.py per l'import automatico.

    Fornitore, fattura e (se generata) prima nota vengono scritti in
    un'unica transazione Mongo: se un passaggio fallisce a metà, tutto viene
    annullato invece di lasciare stato incoerente (es. fornitore creato ma
    fattura mai salvata, o prima nota orfana senza il link sulla fattura).
    Il client di test in sandbox (mongomock) non supporta le sessioni: in
    quel caso si procede senza transazione, come prima.

    Args:
        db: Database connection
        parsed: Dati fattura parsati da parse_fattura_xml
        filename: Nome file originale

    Returns:
        Dict con dati fattura salvata
    """
    if parsed.get("error"):
        raise HTTPException(status_code=400, detail=parsed["error"])

    invoice_key = generate_invoice_key(
        parsed.get("invoice_number", ""),
        parsed.get("supplier_vat", ""),
        parsed.get("invoice_date", "")
    )

    duplicate_detail = (
        f"Fattura duplicata: {parsed.get('invoice_number')} del fornitore "
        f"{parsed.get('supplier_name', 'N/A')} esiste già"
    )

    async def _do_import(session) -> Dict[str, Any]:
        # Controlla duplicati (l'indice unico su invoice_key resta la
        # garanzia ultima contro una race fra due transazioni concorrenti)
        existing = await db[Collections.INVOICES].find_one(
            {"invoice_key": invoice_key}, session=session
        )
        if existing:
            raise HTTPException(status_code=409, detail=duplicate_detail)

        # Assicura che il fornitore esista
        supplier_result = await ensure_supplier_exists(db, parsed, session=session)
        supplier_id = supplier_result.get("supplier_id")
        # REGOLA: metodo pagamento SOLO dal fornitore. Se non definito → sospesa (provvisorio)
        metodo_pagamento = supplier_result.get("metodo_pagamento") or "sospesa"

        # Calcola data scadenza
        data_fattura_str = parsed.get("invoice_date", "")
        data_scadenza = None
        if data_fattura_str:
            try:
                data_fattura = datetime.strptime(data_fattura_str, "%Y-%m-%d")
                data_scadenza = (data_fattura + timedelta(days=30)).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        # Crea documento fattura
        invoice = {
            "id": str(uuid.uuid4()),
            "invoice_key": invoice_key,
            "supplier_id": supplier_id,
            "invoice_number": parsed.get("invoice_number", ""),
            "invoice_date": parsed.get("invoice_date", ""),
            "data_scadenza": data_scadenza,
            "tipo_documento": parsed.get("tipo_documento", ""),
            "supplier_name": parsed.get("supplier_name", ""),
            "supplier_vat": parsed.get("supplier_vat", ""),
            "total_amount": parsed.get("total_amount", 0),
            "imponibile": parsed.get("imponibile", 0),
            "iva": parsed.get("iva", 0),
            "divisa": parsed.get("divisa", "EUR"),
            "fornitore": parsed.get("fornitore", {}),
            "cliente": parsed.get("cliente", {}),
            "linee": parsed.get("linee", []),
            "riepilogo_iva": parsed.get("riepilogo_iva", []),
            "metodo_pagamento": metodo_pagamento,
            "status": "imported",
            "source": "xml_upload",
            "filename": filename,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "cedente_piva": parsed.get("supplier_vat", ""),
            "cedente_denominazione": parsed.get("supplier_name", ""),
            "numero_fattura": parsed.get("invoice_number", ""),
            "data_fattura": parsed.get("invoice_date", ""),
            "importo_totale": parsed.get("total_amount", 0),
            "anno": int(parsed.get("invoice_date", "2024")[:4]) if parsed.get("invoice_date") else 2024,
            "causali": parsed.get("causali", []),
            "dati_fatture_collegate": parsed.get("dati_fatture_collegate", []),
            "dati_ordine_acquisto": parsed.get("dati_ordine_acquisto", []),
            "tipo_documento_desc": parsed.get("tipo_documento_desc", ""),
        }

        await db[Collections.INVOICES].insert_one(invoice.copy(), session=session)
        invoice.pop("_id", None)

        logger.info(f"Fattura importata: {invoice.get('invoice_number')} - {invoice.get('supplier_name')}")

        # AUTO-REGISTRA in Prima Nota
        # 1. Se contanti → sempre in cassa
        # 2. Se banca/assegno/rid/carta → cerca prima nell'estratto conto, se trovato registra
        # 3. Se misto/sconosciuto → provvisorio
        if metodo_pagamento and metodo_pagamento not in ['misto', '']:
            import uuid as _uuid
            pn_id = str(_uuid.uuid4())
            is_cassa = metodo_pagamento in ['contanti', 'cassa']

            if is_cassa:
                # Contanti → sempre in cassa
                pn_collection = "prima_nota_cassa"
                registra = True
            else:
                # Banca → cerca nell'estratto conto prima di registrare
                importo_fatt = invoice.get("total_amount", 0)
                nome_forn = (invoice.get("supplier_name", "") or "").upper()[:10]
                ec_query = {"importo": {"$gte": importo_fatt - 1, "$lte": importo_fatt + 1}, "tipo": "uscita"}
                if nome_forn and len(nome_forn) > 3:
                    ec_query["descrizione"] = {"$regex": nome_forn[:8], "$options": "i"}
                ec_match = await db["estratto_conto_movimenti"].find_one(ec_query, session=session)

                if ec_match:
                    pn_collection = "prima_nota_banca"
                    registra = True
                    logger.info(f"  → Pagamento trovato in EC: {ec_match.get('descrizione', '')[:40]}")
                else:
                    # Non trovato in EC → provvisorio
                    registra = False
                    logger.info(f"  → Pagamento NON trovato in EC → provvisorio")

            if registra:
                await db[pn_collection].insert_one({
                    "id": pn_id,
                    "data": invoice.get("invoice_date", ""),
                    "tipo": "uscita",
                    "categoria": "Fatture",
                    "descrizione": f"Fatt. {invoice.get('invoice_number','')} - {invoice.get('supplier_name','')[:30]}",
                    "importo": invoice.get("total_amount", 0),
                    "fattura_id": invoice["id"],
                    "riferimento": f"FATT-{invoice['id']}",
                    "source": "auto_import",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }, session=session)

                prima_nota_update = {
                    "prima_nota_id": pn_id,
                    "prima_nota_tipo": "cassa" if is_cassa else "banca",
                    "prima_nota_cassa_id": pn_id if is_cassa else None,
                    "prima_nota_banca_id": pn_id if not is_cassa else None,
                    "stato_pagamento": "pagata",
                }
                await db[Collections.INVOICES].update_one(
                    {"id": invoice["id"]},
                    {"$set": prima_nota_update},
                    session=session
                )
                # Rispecchia l'update anche sul dict in memoria: altrimenti il
                # valore restituito dalla funzione resta disallineato dal DB
                # (l'invoice salvata risulterebbe "provvisoria" nella risposta
                # anche quando è stata correttamente auto-registrata).
                invoice.update(prima_nota_update)
                logger.info(f"  → Auto-registrata in {'CASSA' if is_cassa else 'BANCA'} (metodo: {metodo_pagamento})")

        return {"invoice": invoice, "supplier_id": supplier_id, "supplier_result": supplier_result}

    try:
        session = await db.client.start_session()
    except NotImplementedError:
        # Client di test senza supporto sessioni (es. mongomock) → nessuna transazione
        session = None

    try:
        if session is not None:
            async with session:
                outcome = await session.with_transaction(_do_import)
        else:
            outcome = await _do_import(None)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=duplicate_detail)

    invoice = outcome["invoice"]
    supplier_id = outcome["supplier_id"]
    supplier_result = outcome["supplier_result"]
    metodo_pagamento = invoice.get("metodo_pagamento")
    data_scadenza = invoice.get("data_scadenza")

    # --- EVENT BUS: propaga evento fattura creata (upload manuale) ---
    # Fuori dalla transazione per design: è già gestita come fail-safe/
    # best-effort (try/except sotto) e non deve bloccare né essere
    # annullata se l'import principale (già commesso) è andato a buon fine.
    # Attiva i 4 handler su FATTURA_CREATED: crea_partita, alert_fornitore,
    # audit, righe_magazzino. Fail-safe per non bloccare l'import.
    try:
        from app.services.event_bus import propagate_event, EventTypes
        fornitore_data = invoice.get("fornitore") or {}
        await propagate_event(EventTypes.FATTURA_CREATED, {
            "fattura_id": invoice["id"],
            "numero_documento": invoice.get("invoice_number", ""),
            "tipo_documento": invoice.get("tipo_documento", "TD01"),
            "importo_totale": invoice.get("total_amount", 0),
            "fornitore_id": supplier_id,
            "fornitore_ragione_sociale": invoice.get("supplier_name", ""),
            "fornitore_nuovo": supplier_result.get("nuovo", False),
            "fornitore_iban": fornitore_data.get("iban") if isinstance(fornitore_data, dict) else None,
            "metodo_pagamento": metodo_pagamento,
            "data_documento": invoice.get("invoice_date", ""),
            "data_scadenza": data_scadenza,
            "stato": invoice.get("status", "imported"),
            "pagato": invoice.get("stato_pagamento") == "pagata",
            "righe_linee": invoice.get("linee", []),
        }, db, source_module="fatture_upload_manuale")
    except Exception:
        logger.exception("Errore propagazione evento fattura.created (upload manuale)")

    return invoice


async def find_check_numbers_for_invoice(db, importo: float, data_fattura: str, fornitore: str) -> Optional[Dict[str, Any]]:
    """
    Cerca nell'estratto conto i numeri degli assegni che corrispondono all'importo della fattura.
    
    Returns:
        Dict con numeri assegni trovati o None
    """
    try:
        if not importo or importo <= 0:
            return None
        
        # Tolleranza importo
        importo_min = importo - 1.0
        importo_max = importo + 1.0
        
        # Range date (90 giorni prima e dopo la data fattura)
        data_min = None
        data_max = None
        if data_fattura:
            try:
                data_doc = datetime.strptime(data_fattura, "%Y-%m-%d")
                data_min = (data_doc - timedelta(days=90)).strftime("%Y-%m-%d")
                data_max = (data_doc + timedelta(days=90)).strftime("%Y-%m-%d")
            except Exception:
                pass
        
        # Cerca match singolo per importo
        query = {
            "tipo": "uscita",
            "descrizione": {"$regex": "assegno", "$options": "i"},
            "$or": [
                {"importo": {"$gte": importo_min, "$lte": importo_max}},
                {"importo": {"$gte": -importo_max, "$lte": -importo_min}}
            ]
        }
        if data_min and data_max:
            query["data"] = {"$gte": data_min, "$lte": data_max}
        
        match = await db["estratto_conto_movimenti"].find_one(query, {"_id": 0})
        
        if match:
            # Estrai numero assegno dalla descrizione
            descrizione = match.get("descrizione", "")
            numero_assegno = None
            
            patterns = [
                r'NUM:\s*(\d+)',
                r'ASSEGNO\s*N\.?\s*(\d+)',
                r'ASS\.?\s*N?\.?\s*(\d+)',
            ]
            for pattern in patterns:
                m = re.search(pattern, descrizione, re.IGNORECASE)
                if m:
                    numero_assegno = m.group(1)
                    break
            
            if numero_assegno:
                return {
                    "tipo": "singolo",
                    "numero_assegno": numero_assegno,
                    "descrizione": descrizione,
                    "data": match.get("data"),
                    "importo": abs(match.get("importo", 0))
                }
        
        # Se non trovato singolo, cerca combinazione assegni multipli
        from itertools import combinations
        
        query_multi = {
            "descrizione": {"$regex": "assegno", "$options": "i"}
        }
        if data_min and data_max:
            query_multi["data"] = {"$gte": data_min, "$lte": data_max}
        
        assegni = await db["estratto_conto_movimenti"].find(query_multi, {"_id": 0}).limit(50).to_list(50)
        
        if len(assegni) >= 2:
            for num in [2, 3, 4]:
                for combo in combinations(assegni, num):
                    somma = sum(abs(a.get("importo", 0)) for a in combo)
                    if importo_min <= somma <= importo_max:
                        numeri = []
                        for a in combo:
                            for pattern in patterns:
                                m = re.search(pattern, a.get("descrizione", ""), re.IGNORECASE)
                                if m:
                                    numeri.append(m.group(1))
                                    break
                        
                        if numeri:
                            return {
                                "tipo": "multiplo",
                                "numeri_assegni": numeri,
                                "numero_assegno": ", ".join(numeri),
                                "num_assegni": len(combo),
                                "somma": somma
                            }
        
        return None
        
    except Exception as e:
        logger.error(f"Errore ricerca assegni per fattura: {e}")
        return None


async def riconcilia_con_estratto_conto(db, importo: float, data_fattura: str, fornitore: str, numero_fattura: str = None) -> Dict[str, Any]:
    """
    Cerca riconciliazione nell'estratto conto (bonifici, assegni, qualsiasi movimento).
    
    REGOLE DI MATCH (in ordine di priorità):
    1. Importo + Nome fornitore/beneficiario (MATCH FORTE)
    2. Importo + Numero fattura in causale (MATCH FORTE)  
    3. Solo importo esatto con tolleranza minima (MATCH DEBOLE)
    
    NOTE: La DATA NON È un criterio obbligatorio perché un bonifico può essere:
    - Contestuale alla fattura
    - Differito rispetto alla fattura
    - In anticipo rispetto alla data fattura
    
    Returns:
        Dict con info riconciliazione o {"trovato": False}
    """
    result = {
        "trovato": False,
        "metodo_suggerito": None,
        "movimento_banca_id": None,
        "data_pagamento": None,
        "descrizione_banca": None,
        "match_tipo": None,
        "match_score": 0
    }
    
    try:
        if not importo or importo <= 0:
            return result
        
        # Tolleranza importo: ±1€ o ±1% (usa il maggiore)
        tolleranza = max(1.0, importo * 0.01)
        importo_min = importo - tolleranza
        importo_max = importo + tolleranza
        
        # Normalizza nome fornitore per ricerca (estrai parole significative)
        fornitore_words = []
        if fornitore:
            # Rimuovi forme societarie e parole comuni
            fornitore_clean = re.sub(
                r'(S\.?R\.?L\.?|S\.?P\.?A\.?|S\.?N\.?C\.?|S\.?A\.?S\.?|DI|DEL|DELLA|IL|LA|LO|GLI|LE|UN|UNA|E|ED|\d+)', 
                '', 
                fornitore, 
                flags=re.IGNORECASE
            )
            fornitore_words = [w.strip() for w in fornitore_clean.split() if len(w.strip()) > 2]
        
        # Query base: cerca movimenti in uscita con importo compatibile
        # NON filtrare per data - lascia che il match avvenga su altri criteri
        query = {
            "tipo": "uscita",
            "$or": [
                {"importo": {"$gte": importo_min, "$lte": importo_max}},
                {"importo": {"$gte": -importo_max, "$lte": -importo_min}}  # Importi negativi
            ],
            # Escludi movimenti già riconciliati
            "riconciliato": {"$ne": True}
        }
        
        # Cerca nell'estratto conto (senza limite di data)
        movimenti = await db["estratto_conto_movimenti"].find(query, {"_id": 0}).limit(50).to_list(50)
        
        best_match = None
        best_score = 0
        
        for mov in movimenti:
            descrizione = (mov.get("descrizione", "") or "").upper()
            causale = (mov.get("causale", "") or "").upper()
            beneficiario = (mov.get("beneficiario", "") or "").upper()
            testo_ricerca = f"{descrizione} {causale} {beneficiario}"
            
            score = 0
            match_reasons = []
            
            # 1. Match per nome fornitore (PESO: 50 punti)
            if fornitore_words:
                matches_found = 0
                for word in fornitore_words[:4]:  # Max 4 parole significative
                    if word.upper() in testo_ricerca:
                        matches_found += 1
                if matches_found > 0:
                    # Più parole matchano, più alto il punteggio
                    score += 25 + (matches_found * 10)
                    match_reasons.append(f"fornitore({matches_found} parole)")
            
            # 2. Match per numero fattura in causale (PESO: 40 punti)
            if numero_fattura:
                # Normalizza numero fattura (rimuovi spazi, slash)
                num_clean = numero_fattura.replace(" ", "").replace("/", "").upper()
                if num_clean in testo_ricerca.replace(" ", "").replace("/", ""):
                    score += 40
                    match_reasons.append("numero_fattura")
            
            # 3. Match per importo esatto (PESO: 30 punti)
            importo_mov = abs(mov.get("importo", 0))
            differenza = abs(importo_mov - importo)
            if differenza < 0.10:  # Quasi esatto
                score += 30
                match_reasons.append("importo_esatto")
            elif differenza < 0.50:
                score += 20
                match_reasons.append("importo_quasi")
            elif differenza < tolleranza:
                score += 10
                match_reasons.append("importo_tolleranza")
            
            # Se abbiamo un match significativo (score >= 50)
            if score >= 50 and score > best_score:
                # Determina metodo pagamento dalla descrizione
                metodo = "bonifico"  # Default
                if any(x in descrizione for x in ["BONIFICO", "BON.", "SEPA"]):
                    metodo = "bonifico"
                elif any(x in descrizione for x in ["ASSEGNO", "ASS.", "CHK"]):
                    metodo = "assegno"
                elif any(x in descrizione for x in ["PRELIEVO", "BANCOMAT", "CASH"]):
                    metodo = "cassa"
                elif any(x in descrizione for x in ["RID", "SDD", "ADDEBITO"]):
                    metodo = "rid"
                
                best_match = {
                    "trovato": True,
                    "metodo_suggerito": metodo,
                    "movimento_banca_id": mov.get("id"),
                    "data_pagamento": mov.get("data"),
                    "descrizione_banca": descrizione[:100],
                    "importo_banca": importo_mov,
                    "match_tipo": " + ".join(match_reasons),
                    "match_score": score
                }
                best_score = score
        
        if best_match:
            return best_match
        
        return result
        
    except Exception as e:
        logger.error(f"Errore riconciliazione estratto conto: {e}")
        return result


def generate_invoice_key(invoice_number: str, supplier_vat: str, invoice_date: str) -> str:
    """Genera chiave univoca per fattura: numero_piva_data"""
    key = f"{invoice_number}_{supplier_vat}_{invoice_date}"
    return key.replace(" ", "").replace("/", "-").upper()


def extract_xml_from_zip(zip_content: bytes, zip_filename: str = "archive.zip") -> List[Dict[str, Any]]:
    """
    Estrae tutti i file XML da un archivio ZIP.
    Supporta ZIP annidati (ZIP dentro ZIP).
    
    Returns:
        Lista di dict con {"filename": str, "content": bytes}
    """
    xml_files = []
    
    try:
        with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zf:
            for name in zf.namelist():
                # Salta directory
                if name.endswith('/'):
                    continue
                
                try:
                    file_content = zf.read(name)
                    
                    if name.lower().endswith('.xml'):
                        # File XML trovato
                        xml_files.append({
                            "filename": f"{zip_filename}/{name}",
                            "content": file_content
                        })
                    elif name.lower().endswith('.zip'):
                        # ZIP annidato - estrai ricorsivamente
                        nested_xmls = extract_xml_from_zip(file_content, f"{zip_filename}/{name}")
                        xml_files.extend(nested_xmls)
                except Exception as e:
                    logger.warning(f"Errore estrazione {name}: {str(e)}")
                    continue
    except zipfile.BadZipFile:
        raise ValueError(f"File ZIP corrotto o non valido: {zip_filename}")
    
    return xml_files


@router.post("/upload-xml")
@handle_errors
async def upload_fattura_xml(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Upload e parse di una singola fattura elettronica XML."""
    if not file.filename.endswith('.xml'):
        raise HTTPException(status_code=400, detail="Il file deve essere in formato XML")
    
    try:
        content = await file.read()
        xml_content = content.decode('utf-8')
        parsed = parse_fattura_xml(xml_content)
        
        if parsed.get("error"):
            raise HTTPException(status_code=400, detail=parsed["error"])
        
        db = Database.get_db()
        
        invoice_key = generate_invoice_key(
            parsed.get("invoice_number", ""),
            parsed.get("supplier_vat", ""),
            parsed.get("invoice_date", "")
        )
        
        existing = await db[Collections.INVOICES].find_one({"invoice_key": invoice_key})
        if existing:
            raise HTTPException(
                status_code=409, 
                detail=f"Fattura già presente: {parsed.get('invoice_number')} del {parsed.get('invoice_date')}"
            )
        
        # Assicura che il fornitore esista nel database (crea se nuovo + alert)
        supplier_result = await ensure_supplier_exists(db, parsed)
        supplier_id = supplier_result.get("supplier_id")
        supplier_created = supplier_result.get("supplier_created", False)
        alert_created = supplier_result.get("alert_created", False)
        
        # Se il fornitore ha metodo_pagamento configurato, usalo. Altrimenti default a "bonifico"
        metodo_pagamento = supplier_result.get("metodo_pagamento") or "bonifico"
        
        # Recupera giorni_pagamento dal fornitore se esiste
        giorni_pagamento = 30
        if supplier_id:
            supplier_doc = await db[Collections.SUPPLIERS].find_one(
                {"id": supplier_id}, {"giorni_pagamento": 1}
            )
            if supplier_doc:
                giorni_pagamento = supplier_doc.get("giorni_pagamento", 30)
        
        # === RICONCILIAZIONE AUTOMATICA CON ESTRATTO CONTO ===
        importo_fattura = parsed.get("total_amount", 0)
        data_fattura_ricerca = parsed.get("invoice_date", "")
        fornitore_nome = parsed.get("supplier_name", "")
        
        riconciliazione = await riconcilia_con_estratto_conto(
            db, importo_fattura, data_fattura_ricerca, fornitore_nome
        )
        
        # Se trovato in banca, aggiorna metodo pagamento e stato
        riconciliato_automaticamente = False
        if riconciliazione.get("trovato"):
            metodo_suggerito = riconciliazione.get("metodo_suggerito", metodo_pagamento)
            # Solo aggiorna se diverso da quello del fornitore
            if metodo_suggerito:
                metodo_pagamento = metodo_suggerito
            riconciliato_automaticamente = True
            logger.info(f"Riconciliazione automatica per fattura {parsed.get('invoice_number')}: {metodo_pagamento}")
        
        # === RICONCILIAZIONE ASSEGNI (per dettagli aggiuntivi) ===
        numeri_assegni = None
        riconciliazione_assegni = None
        
        if metodo_pagamento and metodo_pagamento.lower() == "assegno":
            riconciliazione_assegni = await find_check_numbers_for_invoice(
                db, importo_fattura, data_fattura_ricerca, fornitore_nome
            )
            
            if riconciliazione_assegni:
                numeri_assegni = riconciliazione_assegni.get("numero_assegno")
                logger.info(f"Assegni trovati per fattura {parsed.get('invoice_number')}: {numeri_assegni}")
        
        data_fattura_str = parsed.get("invoice_date", "")
        data_scadenza = None
        if data_fattura_str:
            try:
                data_fattura = datetime.strptime(data_fattura_str, "%Y-%m-%d")
                data_scadenza = (data_fattura + timedelta(days=giorni_pagamento)).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass
        
        supplier_vat = parsed.get("supplier_vat", "")
        
        invoice = {
            "id": str(uuid.uuid4()),
            "invoice_key": invoice_key,
            "supplier_id": supplier_id,  # Link al fornitore
            "invoice_number": parsed.get("invoice_number", ""),
            "invoice_date": parsed.get("invoice_date", ""),
            "data_ricezione": parsed.get("invoice_date", ""),  # Default = data fattura, può essere aggiornato
            "data_scadenza": data_scadenza,
            "tipo_documento": parsed.get("tipo_documento", ""),
            "tipo_documento_desc": parsed.get("tipo_documento_desc", ""),
            "supplier_name": parsed.get("supplier_name", ""),
            "supplier_vat": parsed.get("supplier_vat", ""),
            "total_amount": parsed.get("total_amount", 0),
            "imponibile": parsed.get("imponibile", 0),
            "iva": parsed.get("iva", 0),
            "divisa": parsed.get("divisa", "EUR"),
            "fornitore": parsed.get("fornitore", {}),
            "cliente": parsed.get("cliente", {}),
            "linee": parsed.get("linee", []),
            "riepilogo_iva": parsed.get("riepilogo_iva", []),
            "pagamento": parsed.get("pagamento", {}),
            "causali": parsed.get("causali", []),
            "metodo_pagamento": metodo_pagamento,
            "numeri_assegni": numeri_assegni,  # Pre-compilato se trovato nell'estratto conto
            "riconciliazione_assegni": riconciliazione_assegni,  # Dettagli riconciliazione
            "riconciliato": riconciliato_automaticamente,  # Se trovato automaticamente in banca
            "riconciliazione_auto": riconciliazione if riconciliazione.get("trovato") else None,
            "pagato": riconciliato_automaticamente,  # Se riconciliato, è pagato
            "data_pagamento": riconciliazione.get("data_pagamento") if riconciliato_automaticamente else None,
            "status": "paid" if riconciliato_automaticamente else "imported",
            "source": "xml_upload",
            "filename": file.filename,
            "xml_content": xml_content,  # Salva XML per visualizzazione allegato
            "created_at": datetime.now(timezone.utc).isoformat(),
            "cedente_piva": supplier_vat,
            "cedente_denominazione": parsed.get("supplier_name", ""),
            "numero_fattura": parsed.get("invoice_number", ""),
            "data_fattura": parsed.get("invoice_date", ""),
            "importo_totale": parsed.get("total_amount", 0)
        }
        
        await db[Collections.INVOICES].insert_one(invoice.copy())
        invoice.pop("_id", None)
        
        # === ASSOCIAZIONE AUTOMATICA PDF ARCHIVIATO ===
        # Cerca se esiste un PDF in archivio da associare a questo XML
        pdf_association_result = None
        try:
            from app.services.upload_ai_processor import associate_pdf_to_xml_on_upload
            pdf_association_result = await associate_pdf_to_xml_on_upload(
                db=db,
                invoice_id=invoice["id"],
                supplier_vat=supplier_vat,
                invoice_number=parsed.get("invoice_number", ""),
                invoice_date=parsed.get("invoice_date", ""),
                total_amount=parsed.get("total_amount", 0)
            )
            if pdf_association_result and pdf_association_result.get("pdf_associated"):
                logger.info(f"📎 PDF associato automaticamente: {pdf_association_result.get('pdf_filename')}")
        except Exception as e:
            logger.debug(f"Associazione PDF non disponibile: {e}")
        
        warehouse_result = await auto_populate_warehouse_from_invoice(db, parsed, invoice["id"])

        prima_nota_result = {"cassa": None, "banca": None}
        # Registra in Prima Nota SOLO se non è stato già riconciliato automaticamente
        # O se il metodo non è misto
        if metodo_pagamento != "misto":
            try:
                from app.routers.prima_nota_module.sync import registra_pagamento_fattura
                prima_nota_result = await registra_pagamento_fattura(
                    fattura=invoice,
                    metodo_pagamento=metodo_pagamento
                )
                
                # Aggiorna fattura con riferimenti Prima Nota
                update_fields = {
                    "prima_nota_cassa_id": prima_nota_result.get("cassa"),
                    "prima_nota_banca_id": prima_nota_result.get("banca")
                }
                
                # Se già riconciliato automaticamente, mantieni lo stato
                if not riconciliato_automaticamente:
                    update_fields["pagato"] = True
                    update_fields["data_pagamento"] = datetime.now(timezone.utc).isoformat()[:10]
                    update_fields["status"] = "paid"
                
                await db[Collections.INVOICES].update_one(
                    {"id": invoice["id"]},
                    {"$set": update_fields}
                )
            except Exception as e:
                logger.warning(f"Prima nota registration failed: {e}")
        
        # === ASSOCIAZIONE AUTOMATICA FATTURA PROVVISORIA ===
        # Cerca se esiste una fattura provvisoria da email Aruba da associare
        provvisoria_associata = None
        try:
            from app.services.aruba_automation import associate_xml_to_provvisoria
            provvisoria_associata = await associate_xml_to_provvisoria(db, invoice)
            if provvisoria_associata:
                logger.info(f"📧 Fattura provvisoria associata: {provvisoria_associata.get('numero_fattura')}")
        except Exception as e:
            logger.debug(f"Associazione provvisoria non disponibile: {e}")
        
        # === AUTOMAZIONE VERBALI DA FATTURE NOLEGGIO ===
        # Se è una fattura di un noleggiatore (ALD, Leasys, etc.), cerca verbali
        verbali_result = {"verbali_trovati": 0, "verbali_creati": 0, "driver_associati": 0}
        try:
            from app.services.verbali_automation import processa_verbali_da_fattura
            verbali_result = await processa_verbali_da_fattura(db, parsed, invoice["id"])
            if verbali_result.get("verbali_trovati", 0) > 0:
                logger.info(f"🚗 Verbali trovati: {verbali_result['verbali_trovati']}, Driver associati: {verbali_result['driver_associati']}")
        except Exception as e:
            logger.warning(f"Errore automazione verbali: {e}")
        
        return {
            "success": True,
            "message": f"Fattura {parsed.get('invoice_number')} importata",
            "invoice": invoice,
            "supplier": {
                "id": supplier_id,
                "nome": parsed.get("supplier_name"),
                "created": supplier_created
            },
            "warehouse": {
                "products_created": warehouse_result.get("products_created", 0),
                "products_updated": warehouse_result.get("products_updated", 0)
            },
            "prima_nota": prima_nota_result,
            "pdf_associato": pdf_association_result.get("pdf_associated", False) if pdf_association_result else False,
            "pdf_filename": pdf_association_result.get("pdf_filename") if pdf_association_result else None,
            "provvisoria_associata": provvisoria_associata.get("id") if provvisoria_associata else None,
            "verbali": {
                "trovati": verbali_result.get("verbali_trovati", 0),
                "creati": verbali_result.get("verbali_creati", 0),
                "driver_associati": verbali_result.get("driver_associati", 0),
                "costi_dipendente": verbali_result.get("costi_dipendente_creati", 0)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore upload fattura: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_xml_bytes(db, content: bytes, filename: str, source: str = "xml_upload") -> Dict[str, Any]:
    """Pipeline CONDIVISA per importare una singola fattura XML dai suoi bytes.

    Usata sia dall'upload bulk (`/upload-xml-bulk`) sia dall'ingest Google Drive,
    per non duplicare la logica di decodifica/parse/dedup/import.

    Ritorna un dict con `status` in {"imported", "duplicate", "error"}.
    """
    # 1. Decodifica (prova più encoding)
    xml_content = None
    for enc in ('utf-8', 'utf-8-sig', 'latin-1', 'iso-8859-1'):
        try:
            xml_content = content.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if not xml_content:
        return {"status": "error", "filename": filename, "error": "Decodifica fallita"}

    # 2. Parse fattura elettronica
    parsed = parse_fattura_xml(xml_content)
    if parsed.get("error"):
        return {"status": "error", "filename": filename, "error": parsed["error"]}

    # 3. Dedup tramite invoice_key
    invoice_key = generate_invoice_key(
        parsed.get("invoice_number", ""),
        parsed.get("supplier_vat", ""),
        parsed.get("invoice_date", ""),
    )
    if await db[Collections.INVOICES].find_one({"invoice_key": invoice_key}):
        return {"status": "duplicate", "filename": filename,
                "invoice_number": parsed.get("invoice_number")}

    # 4. Fornitore (crea se nuovo) + metodo pagamento
    supplier_result = await ensure_supplier_exists(db, parsed)

    # 5. Documento fattura + insert
    invoice = {
        "id": str(uuid.uuid4()),
        "invoice_key": invoice_key,
        "supplier_id": supplier_result.get("supplier_id"),
        "invoice_number": parsed.get("invoice_number", ""),
        "invoice_date": parsed.get("invoice_date", ""),
        "supplier_name": parsed.get("supplier_name", ""),
        "supplier_vat": parsed.get("supplier_vat", ""),
        "total_amount": float(parsed.get("total_amount", 0) or 0),
        "imponibile": float(parsed.get("imponibile", 0) or 0),
        "iva": float(parsed.get("iva", 0) or 0),
        "linee": parsed.get("linee", []),
        "riepilogo_iva": parsed.get("riepilogo_iva", []),
        "metodo_pagamento": supplier_result.get("metodo_pagamento") or "bonifico",
        "status": "imported",
        "source": source,
        "filename": filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[Collections.INVOICES].insert_one(invoice.copy())

    # 6. Auto-popola magazzino (fail-safe)
    try:
        await auto_populate_warehouse_from_invoice(db, parsed, invoice["id"])
    except Exception:
        pass

    return {"status": "imported", "filename": filename,
            "invoice_number": parsed.get("invoice_number"),
            "supplier": parsed.get("supplier_name"), "id": invoice["id"]}


@router.post("/upload-xml-bulk")
@handle_errors
async def upload_fatture_xml_bulk(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    """
    Upload massivo di fatture elettroniche XML.
    Supporta:
    - File XML multipli
    - File ZIP contenenti XML (anche annidati)
    """
    if not files:
        raise HTTPException(status_code=400, detail="Nessun file caricato")
    
    results = {
        "success": [], "errors": [], "duplicates": [],
        "total": 0, "imported": 0, "failed": 0, "skipped_duplicates": 0
    }
    
    db = Database.get_db()
    
    # Raccoglie tutti i file XML (inclusi quelli estratti da ZIP)
    xml_files = []
    
    for file in files:
        filename = file.filename or "unknown"
        content = await file.read()
        
        if filename.lower().endswith('.zip'):
            # Estrai XML da ZIP
            try:
                extracted = extract_xml_from_zip(content, filename)
                xml_files.extend(extracted)
                logger.info(f"Estratti {len(extracted)} XML da {filename}")
            except Exception as e:
                results["errors"].append({"filename": filename, "error": f"Errore ZIP: {str(e)}"})
                results["failed"] += 1
        elif filename.lower().endswith('.xml'):
            xml_files.append({"filename": filename, "content": content})
        else:
            results["errors"].append({"filename": filename, "error": "Formato non supportato (solo XML o ZIP)"})
            results["failed"] += 1
    
    results["total"] = len(xml_files)
    
    # Processa tutti gli XML con la pipeline condivisa (vedi process_xml_bytes)
    for xml_file in xml_files:
        filename = xml_file["filename"]
        res = await process_xml_bytes(db, xml_file["content"], filename, source="xml_bulk_upload")
        status = res.get("status")
        if status == "imported":
            results["success"].append({
                "filename": filename,
                "invoice_number": res.get("invoice_number"),
                "supplier": res.get("supplier"),
            })
            results["imported"] += 1
        elif status == "duplicate":
            results["duplicates"].append({
                "filename": filename,
                "invoice_number": res.get("invoice_number"),
            })
            results["skipped_duplicates"] += 1
        else:
            results["errors"].append({"filename": filename, "error": res.get("error", "errore")})
            results["failed"] += 1

    return results


@router.delete("/all")
@handle_errors
async def delete_all_invoices(
    confirm: str = Query(..., description="Scrivere 'CONFERMA_ELIMINAZIONE' per procedere")
) -> Dict[str, Any]:
    """Elimina tutte le fatture. Richiede conferma esplicita."""
    if confirm != "CONFERMA_ELIMINAZIONE":
        raise HTTPException(
            status_code=400,
            detail="Conferma richiesta: passare ?confirm=CONFERMA_ELIMINAZIONE"
        )
    db = Database.get_db()
    result = await db[Collections.INVOICES].delete_many({})
    return {"deleted_count": result.deleted_count}


@router.post("/cleanup-duplicates")
@handle_errors
async def cleanup_duplicate_invoices() -> Dict[str, Any]:
    """Pulisce le fatture duplicate."""
    db = Database.get_db()
    
    pipeline = [
        {"$group": {
            "_id": {"invoice_number": "$invoice_number", "supplier_vat": "$supplier_vat", "invoice_date": "$invoice_date"},
            "count": {"$sum": 1},
            "ids": {"$push": "$id"},
            "first_id": {"$first": "$id"}
        }},
        {"$match": {"count": {"$gt": 1}}}
    ]
    
    duplicates = await db[Collections.INVOICES].aggregate(pipeline).to_list(1000)
    
    deleted_count = 0
    for dup in duplicates:
        ids_to_delete = [id for id in dup["ids"] if id != dup["first_id"]]
        result = await db[Collections.INVOICES].delete_many({"id": {"$in": ids_to_delete}})
        deleted_count += result.deleted_count
    
    return {
        "duplicate_groups_found": len(duplicates),
        "invoices_deleted": deleted_count
    }


@router.post("/sync-suppliers")
@handle_errors
async def sync_suppliers_from_invoices() -> Dict[str, Any]:
    """
    Sincronizza i fornitori dalle fatture esistenti.
    Crea nuovi fornitori per le P.IVA non presenti nel database.
    """
    db = Database.get_db()
    
    # Trova tutte le P.IVA uniche nelle fatture
    pipeline = [
        {"$match": {"supplier_vat": {"$exists": True, "$ne": ""}}},
        {"$group": {
            "_id": "$supplier_vat",
            "supplier_name": {"$first": "$supplier_name"},
            "fornitore": {"$first": "$fornitore"},
            "count": {"$sum": 1}
        }}
    ]
    
    supplier_groups = await db[Collections.INVOICES].aggregate(pipeline).to_list(5000)
    
    created = 0
    updated = 0
    skipped = 0
    
    for group in supplier_groups:
        supplier_vat = group["_id"]
        if not supplier_vat:
            continue
        
        # Cerca fornitore esistente
        existing = await db[Collections.SUPPLIERS].find_one({"partita_iva": supplier_vat})
        
        if existing:
            # Prepara aggiornamenti
            updates = {"fatture_count": group["count"], "updated_at": datetime.now(timezone.utc).isoformat()}
            
            # Aggiorna ragione_sociale se mancante
            if not existing.get("ragione_sociale") and group.get("supplier_name"):
                updates["ragione_sociale"] = group["supplier_name"]
            
            # Aggiorna dati fornitore se mancanti
            fornitore_data = group.get("fornitore") or {}
            if not existing.get("indirizzo") and fornitore_data.get("indirizzo"):
                updates["indirizzo"] = fornitore_data["indirizzo"]
            if not existing.get("cap") and fornitore_data.get("cap"):
                updates["cap"] = fornitore_data["cap"]
            if not existing.get("comune") and fornitore_data.get("comune"):
                updates["comune"] = fornitore_data["comune"]
            if not existing.get("provincia") and fornitore_data.get("provincia"):
                updates["provincia"] = fornitore_data["provincia"]
            
            await db[Collections.SUPPLIERS].update_one(
                {"partita_iva": supplier_vat},
                {"$set": updates}
            )
            updated += 1
            continue
        
        # Crea nuovo fornitore
        fornitore_data = group.get("fornitore") or {}
        
        new_supplier = {
            "id": str(uuid.uuid4()),
            "ragione_sociale": group.get("supplier_name") or "Fornitore Sconosciuto",
            "partita_iva": supplier_vat,
            "codice_fiscale": fornitore_data.get("codice_fiscale", ""),
            "indirizzo": fornitore_data.get("indirizzo", ""),
            "cap": fornitore_data.get("cap", ""),
            "comune": fornitore_data.get("comune", ""),
            "provincia": fornitore_data.get("provincia", ""),
            "nazione": fornitore_data.get("nazione", "IT"),
            "metodo_pagamento": "bonifico",
            "giorni_pagamento": 30,
            "iban": "",
            "fatture_count": group["count"],
            "source": "sync_from_invoices",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "note": f"Creato automaticamente - {group['count']} fatture trovate"
        }
        
        await db[Collections.SUPPLIERS].insert_one(new_supplier.copy())
        created += 1
        
        # Aggiorna le fatture con il supplier_id
        await db[Collections.INVOICES].update_many(
            {"supplier_vat": supplier_vat, "supplier_id": {"$exists": False}},
            {"$set": {"supplier_id": new_supplier["id"]}}
        )
    
    return {
        "success": True,
        "suppliers_created": created,
        "suppliers_updated": updated,
        "suppliers_skipped": skipped,
        "total_unique_vat": len(supplier_groups)
    }


@router.post("/repopulate-warehouse")
@handle_errors
async def repopulate_warehouse_from_invoices() -> Dict[str, Any]:
    """
    Ripopola il magazzino da tutte le fatture esistenti.
    Utile per ricostruire il catalogo prodotti dopo un reset.
    """
    db = Database.get_db()
    
    # Reset warehouse
    await db["warehouse_inventory"].delete_many({})
    await db["price_history"].delete_many({})
    
    # Ottieni tutte le fatture attive (non cancellate)
    invoices = await db[Collections.INVOICES].find({
        "$or": [
            {"entity_status": {"$ne": "deleted"}},
            {"entity_status": {"$exists": False}}
        ]
    }).to_list(10000)
    
    total_products_created = 0
    total_products_updated = 0
    total_price_records = 0
    processed_invoices = 0
    errors = []
    
    for invoice in invoices:
        try:
            # Costruisci dati nel formato atteso dal helper
            invoice_data = {
                "linee": invoice.get("linee", []),
                "fornitore": {
                    "denominazione": invoice.get("supplier_name", ""),
                    "partita_iva": invoice.get("supplier_vat", "")
                },
                "numero_fattura": invoice.get("invoice_number", ""),
                "data_fattura": invoice.get("invoice_date", "")
            }
            
            result = await auto_populate_warehouse_from_invoice(
                db, 
                invoice_data, 
                invoice.get("id", "")
            )
            
            total_products_created += result.get("products_created", 0)
            total_products_updated += result.get("products_updated", 0)
            total_price_records += result.get("price_records", 0)
            processed_invoices += 1
            
        except Exception as e:
            errors.append(f"Fattura {invoice.get('invoice_number', 'N/A')}: {str(e)}")
    
    return {
        "success": True,
        "processed_invoices": processed_invoices,
        "products_created": total_products_created,
        "products_updated": total_products_updated,
        "price_records": total_price_records,
        "errors": errors[:20] if errors else []
    }


@router.post("/categorize-movements")
@handle_errors
async def categorize_all_movements() -> Dict[str, Any]:
    """
    Categorizza tutti i movimenti esistenti (Prima Nota Cassa e Banca)
    basandosi sulla descrizione e sul fornitore.
    """
    db = Database.get_db()
    
    categories_map = {
        'acquisti_merce': ['fattura', 'merce', 'prodotti', 'acquisto', 'fornitura', 'materie prime'],
        'utenze': ['enel', 'eni', 'gas', 'luce', 'acqua', 'bolletta', 'utenz', 'telecom', 'tim', 'vodafone', 'fastweb', 'wind'],
        'affitto': ['affitto', 'canone', 'locazione', 'pigione'],
        'stipendi': ['stipendio', 'salario', 'busta paga', 'dipendent', 'paghe', 'f24'],
        'tasse': ['tasse', 'tribut', 'iva', 'irpef', 'inps', 'inail', 'agenzia entrate', 'imposta'],
        'bancari': ['commissione', 'interessi', 'bonifico', 'rid', 'addebito'],
        'assicurazioni': ['assicuraz', 'polizza', 'premio', 'unipol', 'generali', 'allianz'],
        'manutenzione': ['manutenz', 'riparaz', 'assist', 'intervento', 'tecnico'],
        'consulenze': ['consulen', 'commercialista', 'avvocato', 'notaio', 'professional'],
        'marketing': ['pubblicit', 'marketing', 'promoz', 'spot', 'social'],
        'attrezzature': ['attrezzat', 'macchin', 'strument', 'computer', 'software'],
        'carburante': ['benzina', 'gasolio', 'carburant', 'eni', 'q8', 'tamoil', 'ip'],
        'vendite': ['vendita', 'incasso', 'corrispettivo', 'scontrino', 'ricavo'],
        'altro': []
    }
    
    def categorize_description(desc: str, fornitore: str = "") -> str:
        """Determina categoria basandosi su descrizione e fornitore."""
        text = f"{desc} {fornitore}".lower()
        
        for category, keywords in categories_map.items():
            for keyword in keywords:
                if keyword in text:
                    return category
        
        return 'altro'
    
    # Processa Prima Nota Cassa
    cassa_updated = 0
    cassa_movements = await db["prima_nota_cassa"].find({}).to_list(10000)
    for mov in cassa_movements:
        desc = mov.get("descrizione", "") or mov.get("causale", "")
        fornitore = mov.get("fornitore", "")
        categoria = categorize_description(desc, fornitore)
        
        await db["prima_nota_cassa"].update_one(
            {"_id": mov["_id"]},
            {"$set": {"categoria": categoria}}
        )
        cassa_updated += 1
    
    # Processa Prima Nota Banca
    banca_updated = 0
    banca_movements = await db["prima_nota_banca"].find({}).to_list(10000)
    for mov in banca_movements:
        desc = mov.get("descrizione", "") or mov.get("causale", "")
        fornitore = mov.get("fornitore", "")
        categoria = categorize_description(desc, fornitore)
        
        await db["prima_nota_banca"].update_one(
            {"_id": mov["_id"]},
            {"$set": {"categoria": categoria}}
        )
        banca_updated += 1
    
    # Categorizza anche estratto conto
    ec_updated = 0
    ec_movements = await db["estratto_conto_movimenti"].find({}).to_list(10000)
    for mov in ec_movements:
        desc = mov.get("descrizione", "") or mov.get("causale", "")
        fornitore = mov.get("fornitore", "")
        categoria = categorize_description(desc, fornitore)
        
        await db["estratto_conto_movimenti"].update_one(
            {"_id": mov["_id"]},
            {"$set": {"categoria": categoria}}
        )
        ec_updated += 1
    
    return {
        "success": True,
        "cassa_movements_categorized": cassa_updated,
        "banca_movements_categorized": banca_updated,
        "estratto_conto_categorized": ec_updated,
        "categories_available": list(categories_map.keys())
    }


@router.get("/{invoice_id}")
@handle_errors
async def get_fattura(invoice_id: str) -> Dict[str, Any]:
    """Recupera una singola fattura per ID."""
    db = Database.get_db()
    
    invoice = await db[Collections.INVOICES].find_one(
        {"id": invoice_id},
        {"_id": 0}
    )
    
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    return invoice


@router.put("/{invoice_id}")
@handle_errors
async def update_fattura(invoice_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Aggiorna una fattura.
    Campi aggiornabili: metodo_pagamento, pagato, status, data_pagamento, numeri_assegni, note,
                        centro_costo_id, centro_costo_nome, classificazione_manuale
    """
    db = Database.get_db()
    
    # Campi aggiornabili
    allowed_fields = [
        "metodo_pagamento", "pagato", "paid", "status", "data_pagamento",
        "numeri_assegni", "note", "in_banca", "categoria_contabile", "centro_costo",
        "centro_costo_id", "centro_costo_nome", "classificazione_manuale"
    ]
    
    update_data = {k: v for k, v in data.items() if k in allowed_fields}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="Nessun campo valido da aggiornare")
    
    # Sincronizza pagato e paid
    if "pagato" in update_data:
        update_data["paid"] = update_data["pagato"]
    elif "paid" in update_data:
        update_data["pagato"] = update_data["paid"]
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db[Collections.INVOICES].update_one(
        {"id": invoice_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    return {"success": True, "message": "Fattura aggiornata", "updated_fields": list(update_data.keys())}


@router.put("/{invoice_id}/classifica")
@handle_errors
async def classifica_fattura_manuale(invoice_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Classifica manualmente una fattura assegnandola a un centro di costo.
    """
    db = Database.get_db()
    
    centro_costo_id = data.get("centro_costo_id")
    if not centro_costo_id:
        raise HTTPException(status_code=400, detail="centro_costo_id richiesto")
    
    # Recupera il nome del centro di costo
    cdc = await db["centri_costo"].find_one({"codice": centro_costo_id})
    centro_costo_nome = cdc.get("nome", centro_costo_id) if cdc else centro_costo_id
    
    update_data = {
        "centro_costo_id": centro_costo_id,
        "centro_costo_nome": centro_costo_nome,
        "classificazione_manuale": True,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db[Collections.INVOICES].update_one(
        {"id": invoice_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    return {
        "success": True, 
        "message": f"Fattura classificata come '{centro_costo_nome}'",
        "centro_costo_id": centro_costo_id,
        "centro_costo_nome": centro_costo_nome
    }


@router.put("/{invoice_id}/metodo-pagamento")
@handle_errors
async def update_metodo_pagamento(invoice_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiorna il metodo di pagamento di una fattura."""
    db = Database.get_db()
    
    metodo = data.get("metodo_pagamento")
    if not metodo:
        raise HTTPException(status_code=400, detail="Metodo pagamento richiesto")
    
    result = await db[Collections.INVOICES].update_one(
        {"id": invoice_id},
        {"$set": {"metodo_pagamento": metodo, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    return {"success": True, "message": "Metodo pagamento aggiornato"}


@router.put("/{invoice_id}/paga")
@handle_errors
async def paga_fattura(invoice_id: str) -> Dict[str, Any]:
    """
    Segna una fattura come pagata.
    Utilizza DataPropagationService per:
    - Creare movimento in Prima Nota (Cassa o Banca)
    - Aggiornare stato fattura
    - Aggiornare saldo fornitore
    """
    db = Database.get_db()
    
    # Trova la fattura
    invoice = await db[Collections.INVOICES].find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    if invoice.get("pagato") or invoice.get("status") == "paid":
        raise HTTPException(status_code=400, detail="Fattura già pagata")
    
    metodo = invoice.get("metodo_pagamento")
    if not metodo:
        raise HTTPException(status_code=400, detail="Seleziona prima un metodo di pagamento")
    
    # Usa DataPropagationService per propagare il pagamento
    from app.services.data_propagation import get_propagation_service
    
    propagation_service = get_propagation_service()
    importo = invoice.get("total_amount") or invoice.get("importo_totale") or 0
    
    result = await propagation_service.propagate_invoice_payment(
        invoice_id=invoice_id,
        payment_amount=float(importo),
        payment_method=metodo,
        payment_date=datetime.now(timezone.utc).isoformat()[:10]
    )
    
    if result.get("errors"):
        logger.warning(f"Propagation errors: {result['errors']}")
    
    return {
        "success": True,
        "message": "Fattura pagata con successo",
        "prima_nota": {
            "movement_id": result.get("movement_id"),
            "collection": result.get("movement_collection")
        },
        "payment_status": result.get("payment_status"),
        "supplier_updated": result.get("supplier_updated")
    }


@router.delete("/{invoice_id}")
@handle_errors
async def delete_invoice(
    invoice_id: str,
    force: bool = Query(False, description="Forza eliminazione anche con warning"),
    hard_delete: bool = Query(False, description="Elimina fisicamente invece di archiviare")
) -> Dict[str, Any]:
    """
    Elimina una singola fattura con validazione business rules.
    
    **Regole:**
    - Non può eliminare fatture pagate
    - Non può eliminare fatture registrate in Prima Nota (richiede force=true)
    - Fatture con movimenti magazzino richiedono force=true
    
    **CASCADE DELETE:**
    - Elimina/archivia righe dettaglio
    - Elimina/archivia Prima Nota associata
    - Elimina/archivia scadenze
    - Annulla movimenti magazzino
    - Sgancia assegni collegati
    """
    from app.services.business_rules import BusinessRules
    from app.services.cascade_operations import CascadeOperations
    
    db = Database.get_db()
    
    # Recupera fattura
    invoice = await db[Collections.INVOICES].find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    # Verifica se ha operazioni registrate
    stato_registrazione = await CascadeOperations.is_fattura_registrata(db, invoice_id)
    entita_correlate = await CascadeOperations.get_entita_correlate(db, invoice_id)
    
    # Valida eliminazione con business rules
    validation = BusinessRules.can_delete_invoice(invoice)
    
    # Aggiungi warning per entità correlate
    if entita_correlate["totale_entita"] > 0:
        validation.warnings.append(f"Verranno eliminate {entita_correlate['totale_entita']} entità correlate")
        if entita_correlate["prima_nota_banca"] > 0 or entita_correlate["prima_nota_cassa"] > 0:
            validation.warnings.append("⚠️ ATTENZIONE: Verranno eliminate registrazioni contabili (Prima Nota)")
        if entita_correlate["movimenti_magazzino"] > 0:
            validation.warnings.append("⚠️ ATTENZIONE: Verranno annullati movimenti di magazzino")
    
    if not validation.is_valid:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Eliminazione non consentita",
                "errors": validation.errors,
                "entita_correlate": entita_correlate
            }
        )
    
    # Se ci sono warning e non è forzata, richiedi conferma (DOPPIA CONFERMA)
    if (validation.warnings or stato_registrazione["registrata"]) and not force:
        return {
            "status": "warning",
            "message": "Eliminazione richiede conferma",
            "warnings": validation.warnings,
            "stato_registrazione": stato_registrazione,
            "entita_correlate": entita_correlate,
            "require_force": True,
            "nota": "Usa force=true per confermare l'eliminazione"
        }
    
    # Esegui CASCADE DELETE
    risultato_cascade = await CascadeOperations.delete_fattura_cascade(db, invoice_id, hard_delete=hard_delete)
    
    return {
        "success": True,
        "message": "Fattura eliminata" + (" (hard delete)" if hard_delete else " (archiviata)"),
        "invoice_id": invoice_id,
        "cascade_result": risultato_cascade
    }




@router.get("/{invoice_id}/entita-correlate")
@handle_errors
async def get_entita_correlate_fattura(invoice_id: str) -> Dict[str, Any]:
    """
    Restituisce tutte le entità correlate a una fattura.
    Utile per mostrare all'utente cosa verrà modificato/eliminato.
    """
    from app.services.cascade_operations import CascadeOperations
    
    db = Database.get_db()
    
    invoice = await db[Collections.INVOICES].find_one({"id": invoice_id})
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    stato = await CascadeOperations.is_fattura_registrata(db, invoice_id)
    entita = await CascadeOperations.get_entita_correlate(db, invoice_id)
    
    return {
        "fattura_id": invoice_id,
        "numero_documento": invoice.get("invoice_number") or invoice.get("numero_documento"),
        "fornitore": invoice.get("supplier_name") or invoice.get("fornitore_ragione_sociale"),
        "importo": invoice.get("total_amount") or invoice.get("importo_totale"),
        "stato_registrazione": stato,
        "entita_correlate": entita,
        "eliminabile": not stato["dettagli"]["ha_pagamenti"],
        "richiede_conferma": stato["registrata"]
    }




@router.post("/recalculate-iva")
@handle_errors
async def recalculate_iva_all_invoices() -> Dict[str, Any]:
    """
    Ricalcola IVA e imponibile per tutte le fatture.
    Aggiunge data_ricezione se mancante.
    Usa i dati dal riepilogo_iva se disponibili.
    """
    db = Database.get_db()
    
    # Tipi documento Note Credito
    NOTE_CREDITO_TYPES = ["TD04", "TD08"]
    
    updated_count = 0
    errors = []
    
    # Trova tutte le fatture
    cursor = db[Collections.INVOICES].find({}, {"_id": 0})
    fatture = await cursor.to_list(10000)
    
    for f in fatture:
        try:
            updates = {}
            
            # Aggiungi data_ricezione se mancante (default = invoice_date)
            if not f.get('data_ricezione'):
                updates['data_ricezione'] = f.get('invoice_date', '')
            
            # Ricalcola IVA/imponibile dal riepilogo_iva se presente
            riepilogo = f.get('riepilogo_iva', [])
            if riepilogo:
                imponibile_calc = 0
                iva_calc = 0
                for r in riepilogo:
                    try:
                        imponibile_calc += float(r.get('imponibile', 0) or 0)
                        iva_calc += float(r.get('imposta', 0) or 0)
                    except (ValueError, TypeError):
                        pass
                
                # Aggiorna solo se i valori calcolati sono diversi da 0
                if imponibile_calc > 0:
                    current_imponibile = float(f.get('imponibile', 0) or 0)
                    if abs(current_imponibile - imponibile_calc) > 0.01:
                        updates['imponibile'] = round(imponibile_calc, 2)
                
                if iva_calc > 0:
                    current_iva = float(f.get('iva', 0) or 0)
                    if abs(current_iva - iva_calc) > 0.01:
                        updates['iva'] = round(iva_calc, 2)
            else:
                # Se non c'è riepilogo_iva, calcola IVA dal totale (22%)
                total = float(f.get('total_amount', 0) or 0)
                if total > 0:
                    current_iva = float(f.get('iva', 0) or 0)
                    current_imponibile = float(f.get('imponibile', 0) or 0)
                    
                    if current_iva == 0:
                        iva_stimata = round(total - (total / 1.22), 2)
                        updates['iva'] = iva_stimata
                        updates['iva_stimata'] = True  # Flag per indicare che è stimata
                    
                    if current_imponibile == 0:
                        imponibile_stimato = round(total / 1.22, 2)
                        updates['imponibile'] = imponibile_stimato
            
            # Applica aggiornamenti
            if updates:
                updates['updated_at'] = datetime.now(timezone.utc).isoformat()
                await db[Collections.INVOICES].update_one(
                    {"id": f['id']},
                    {"$set": updates}
                )
                updated_count += 1
                
        except Exception as e:
            errors.append(f"Errore fattura {f.get('invoice_number', 'N/A')}: {str(e)}")
    
    return {
        "success": True,
        "fatture_analizzate": len(fatture),
        "fatture_aggiornate": updated_count,
        "errors": errors[:20] if errors else []
    }
