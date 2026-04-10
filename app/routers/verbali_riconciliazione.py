"""
Gestione Verbali Noleggio - Sistema di Riconciliazione Completo

Flusso:
1. VERBALE (multa) → arriva via email o trovato su parabrezza
2. FATTURA NOLEGGIATORE → contiene numero verbale + spese notifica
3. PAGAMENTO → in banca/estratto conto
4. RICONCILIAZIONE → collega tutto: Verbale + Fattura + Pagamento + Veicolo + Driver

Stati del Verbale:
- da_scaricare: Trovato in posta, PDF da scaricare
- salvato: PDF scaricato, in attesa
- fattura_ricevuta: Fattura noleggiatore associata
- pagato: Pagamento trovato in estratto conto
- riconciliato: Tutto collegato
"""

from fastapi import APIRouter, HTTPException, Query, File, UploadFile
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
import re
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


# ===== UTILITY FUNCTIONS =====

def extract_verbale_from_description(description: str) -> Optional[str]:
    """Estrae il numero verbale dalla descrizione fattura."""
    if not description:
        return None
    
    # Pattern comuni per numeri verbale
    patterns = [
        r'Verbale\s*(?:Nr|N\.?|Numero)?[:\s]*([A-Z0-9]+)',
        r'N\.\s*Verbale[:\s]*([A-Z0-9]+)',
        r'verbale[:\s]+([A-Z]\d{8,})',
        r'([A-Z]\d{10,})',  # Pattern generico tipo A25111540620
        r'([B]\d{10,})',    # Pattern B + 10 cifre
        r'Nr[:\s]*([A-Z]\d{8,})',  # Nr: A25111540620
        r'Numero[:\s]*([A-Z]\d{8,})',  # Numero: A25111540620
    ]
    
    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    return None


def extract_targa_from_description(description: str) -> Optional[str]:
    """Estrae la targa dalla descrizione fattura."""
    if not description:
        return None
    
    # Pattern per targhe italiane
    patterns = [
        r'TARGA[:\s]*([A-Z]{2}\d{3}[A-Z]{2})',  # TARGA: GE911SC
        r'targa[:\s]*([A-Z]{2}\d{3}[A-Z]{2})',
        r'([A-Z]{2}\d{3}[A-Z]{2})',  # Pattern generico targa
    ]
    
    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    return None


def serialize_doc(doc: dict) -> dict:
    """Serializza documento MongoDB per JSON."""
    if doc is None:
        return None
    result = {}
    for k, v in doc.items():
        if k == '_id':
            result['id'] = str(v)
        elif isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


# ===== ENDPOINTS =====

@router.get("/dashboard")
@handle_errors
async def get_verbali_dashboard() -> Dict[str, Any]:
    """Dashboard riassuntiva dello stato verbali."""
    db = Database.get_db()
    
    try:
        # Conta verbali per stato - USA PROIEZIONE per evitare di caricare PDF
        pipeline = [
            {"$project": {"stato": 1, "importo": 1}},  # Solo campi necessari
            {"$group": {
                "_id": "$stato",
                "count": {"$sum": 1},
                "totale_importo": {"$sum": {"$toDouble": {"$ifNull": ["$importo", 0]}}}
            }}
        ]
        stati = await db["verbali_noleggio"].aggregate(pipeline).to_list(100)
        
        per_stato = {}
        totale_verbali = 0
        totale_importo = 0
        for s in stati:
            stato = s["_id"] or "sconosciuto"
            per_stato[stato] = {"count": s["count"], "importo": round(s["totale_importo"], 2)}
            totale_verbali += s["count"]
            totale_importo += s["totale_importo"]
        
        # Verbali da riconciliare - solo count
        da_riconciliare = await db["verbali_noleggio"].count_documents({
            "$or": [
                {"stato": "fattura_ricevuta", "pagamento_id": {"$exists": False}},
                {"stato": "pagato", "fattura_id": {"$exists": False}},
                {"stato": "salvato"}
            ]
        })
        
        # Ultimi 5 verbali - ESCLUDI campi pesanti (pdf_content, pdf_base64, etc)
        projection = {
            "_id": 1,
            "id": 1,
            "numero_verbale": 1,
            "targa": 1,
            "importo": 1,
            "stato": 1,
            "data_violazione": 1,
            "created_at": 1
        }
        ultimi = await db["verbali_noleggio"].find({}, projection).sort("created_at", -1).limit(5).to_list(5)
        
        return {
            "success": True,
            "riepilogo": {
                "totale_verbali": totale_verbali,
                "totale_importo": round(totale_importo, 2),
                "da_riconciliare": da_riconciliare,
                "per_stato": per_stato
            },
            "ultimi_verbali": [serialize_doc(v) for v in ultimi]
        }
    except Exception as e:
        logger.error(f"Errore dashboard verbali: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lista")
@handle_errors
async def get_lista_verbali(
    stato: Optional[str] = Query(None, description="Filtra per stato"),
    targa: Optional[str] = Query(None, description="Filtra per targa veicolo"),
    da_riconciliare: bool = Query(False, description="Solo verbali da riconciliare"),
    ordinamento: str = Query("data_verbale", description="Ordinamento: data_verbale, numero_verbale, created_at")
) -> Dict[str, Any]:
    """Lista verbali con filtri e ordinamento. OTTIMIZZATO per escludere PDF."""
    db = Database.get_db()
    
    try:
        query = {}
        
        if stato:
            query["stato"] = stato
        
        if targa:
            query["targa"] = {"$regex": targa, "$options": "i"}
        
        if da_riconciliare:
            query["$or"] = [
                {"stato": "fattura_ricevuta", "pagamento_id": {"$exists": False}},
                {"stato": "pagato", "fattura_id": {"$exists": False}},
                {"stato": "salvato"}
            ]
        
        # PROIEZIONE: escludi campi pesanti (PDF base64)
        projection = {
            "_id": 1,
            "id": 1,
            "numero_verbale": 1,
            "targa": 1,
            "importo": 1,
            "stato": 1,
            "data_verbale": 1,
            "data_violazione": 1,
            "scadenza_pagamento": 1,
            "driver": 1,
            "driver_nome": 1,
            "driver_id": 1,
            "veicolo_id": 1,
            "fattura_id": 1,
            "fattura_numero": 1,
            "numero_fattura": 1,
            "fornitore": 1,
            "pagamento_id": 1,
            "data_pagamento": 1,
            "quietanza_ricevuta": 1,
            "stato_pagamento": 1,
            "metodo_pagamento": 1,
            "note": 1,
            "source": 1,
            "created_at": 1,
            "updated_at": 1
            # ESCLUDI: pdf_content, pdf_base64, email_body, attachment_content, pdf_quietanza, etc.
        }
        
        # Ordinamento configurabile
        sort_field = ordinamento if ordinamento in ("data_verbale", "numero_verbale", "created_at") else "data_verbale"
        sort_dir = 1 if sort_field == "numero_verbale" else -1
        
        verbali = await db["verbali_noleggio"].find(query, projection).sort(sort_field, sort_dir).to_list(500)
        
        # Normalizza driver_nome e fattura_numero
        for v in verbali:
            if not v.get("driver_nome") and v.get("driver"):
                v["driver_nome"] = v["driver"]
            if not v.get("fattura_numero") and v.get("numero_fattura"):
                v["fattura_numero"] = v["numero_fattura"]
        
        return {
            "success": True,
            "verbali": [serialize_doc(v) for v in verbali],
            "totale": len(verbali)
        }
    except Exception as e:
        logger.error(f"Errore lista verbali: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/associa-fattura")
@handle_errors
async def associa_verbale_fattura(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Associa un verbale a una fattura del noleggiatore.
    
    Il numero verbale nella descrizione fattura viene usato per collegare:
    Verbale → Fattura → Veicolo → Driver
    """
    db = Database.get_db()
    
    try:
        numero_verbale = data.get("numero_verbale")
        fattura_id = data.get("fattura_id")
        fattura_numero = data.get("fattura_numero")
        
        if not numero_verbale:
            raise HTTPException(status_code=400, detail="Numero verbale richiesto")
        
        # Trova il verbale
        verbale = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})
        
        if not verbale:
            # Crea nuovo record verbale dalla fattura
            verbale = {
                "numero_verbale": numero_verbale,
                "stato": "fattura_ricevuta",
                "created_at": datetime.now(timezone.utc)
            }
        
        # Aggiorna con info fattura
        update_data = {
            "fattura_id": fattura_id,
            "fattura_numero": fattura_numero,
            "stato": "fattura_ricevuta" if verbale.get("stato") != "pagato" else "riconciliato",
            "updated_at": datetime.now(timezone.utc)
        }
        
        # Se la fattura ha info veicolo/driver, aggiornale
        if data.get("targa"):
            update_data["targa"] = data["targa"]
        if data.get("driver_id"):
            update_data["driver_id"] = data["driver_id"]
        if data.get("importo_notifica"):
            update_data["importo_notifica"] = data["importo_notifica"]
        
        if verbale.get("_id"):
            await db["verbali_noleggio"].update_one(
                {"_id": verbale["_id"]},
                {"$set": update_data}
            )
        else:
            verbale.update(update_data)
            result = await db["verbali_noleggio"].insert_one(verbale)
            verbale["_id"] = result.inserted_id
        
        # Se il verbale era già pagato, ora è riconciliato
        if verbale.get("pagamento_id"):
            await db["verbali_noleggio"].update_one(
                {"numero_verbale": numero_verbale},
                {"$set": {"stato": "riconciliato"}}
            )
        
        return {
            "success": True,
            "message": f"Verbale {numero_verbale} associato a fattura {fattura_numero}",
            "verbale": serialize_doc(verbale)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore associazione verbale-fattura: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/registra-pagamento")
@handle_errors
async def registra_pagamento_verbale(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Registra il pagamento di un verbale (da estratto conto).
    
    Scenario A: Pago prima, fattura dopo → stato = pagato
    Scenario B: Fattura già presente → stato = riconciliato
    """
    db = Database.get_db()
    
    try:
        numero_verbale = data.get("numero_verbale")
        importo_pagato = data.get("importo")
        data_pagamento = data.get("data_pagamento")
        movimento_id = data.get("movimento_id")  # ID del movimento in prima nota
        
        if not numero_verbale:
            raise HTTPException(status_code=400, detail="Numero verbale richiesto")
        
        # Trova il verbale
        verbale = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})
        
        if not verbale:
            # Scenario A: Pago prima che arrivi la fattura
            verbale = {
                "numero_verbale": numero_verbale,
                "stato": "pagato",
                "importo": importo_pagato,
                "data_pagamento": data_pagamento,
                "pagamento_id": movimento_id,
                "created_at": datetime.now(timezone.utc)
            }
            result = await db["verbali_noleggio"].insert_one(verbale)
            verbale["_id"] = result.inserted_id
            message = f"Verbale {numero_verbale} registrato come pagato (in attesa fattura)"
        else:
            # Verbale esistente - aggiorna pagamento
            nuovo_stato = "riconciliato" if verbale.get("fattura_id") else "pagato"
            
            await db["verbali_noleggio"].update_one(
                {"numero_verbale": numero_verbale},
                {"$set": {
                    "importo": importo_pagato,
                    "data_pagamento": data_pagamento,
                    "pagamento_id": movimento_id,
                    "stato": nuovo_stato,
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            message = f"Verbale {numero_verbale} {'riconciliato' if nuovo_stato == 'riconciliato' else 'pagato'}"
        
        return {
            "success": True,
            "message": message,
            "verbale": serialize_doc(verbale)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore registrazione pagamento: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan-fatture-verbali")
@handle_errors
async def scan_fatture_per_verbali() -> Dict[str, Any]:
    """
    Scansiona tutte le fatture dei noleggiatori per estrarre numeri verbale
    e creare associazioni automatiche.
    """
    db = Database.get_db()
    
    try:
        # Fornitori noleggio tipici (se vuoto cerca in tutte le fatture)
        fornitori_noleggio = ["ALD", "LEASYS", "ARVAL", "LEASEPLAN", "ALPHABET"]
        
        # Trova fatture dei noleggiatori E tutte quelle con numeri verbale
        fatture = await db["invoices"].find({
            "$or": [
                {"supplier_name": {"$regex": "|".join(fornitori_noleggio), "$options": "i"}},
                {"fornitore": {"$regex": "|".join(fornitori_noleggio), "$options": "i"}},
                # Cerca anche nelle fatture con pattern verbale nei testi
                {"descrizione": {"$regex": r"[AB]\d{8,12}", "$options": "i"}},
                {"body": {"$regex": r"[AB]\d{8,12}", "$options": "i"}},
                {"note": {"$regex": r"[AB]\d{8,12}", "$options": "i"}},
                {"oggetto": {"$regex": r"[AB]\d{8,12}", "$options": "i"}},
            ]
        }).to_list(5000)
        
        verbali_trovati = 0
        associazioni_create = 0
        
        for fattura in fatture:
            # Costruisci testo completo della fattura cercando in tutti i campi
            campi_testo = [
                fattura.get("descrizione", "") or "",
                fattura.get("body", "") or "",
                fattura.get("note", "") or "",
                fattura.get("notes", "") or "",
                fattura.get("oggetto", "") or "",
                fattura.get("subject", "") or "",
                fattura.get("invoice_number", "") or "",
            ]
            # Aggiungi tutti gli items
            items = fattura.get("items", [])
            for item in items:
                campi_testo.append(item.get("descrizione", "") or item.get("description", "") or "")
            
            testo_completo = " ".join(campi_testo)
            
            # Cerca numero verbale nel testo completo
            numero_verbale = extract_verbale_from_description(testo_completo)
            
            if numero_verbale:
                verbali_trovati += 1
                
                # Verifica se esiste già l'associazione
                existing = await db["verbali_noleggio"].find_one({
                    "numero_verbale": numero_verbale,
                    "fattura_id": str(fattura.get("_id"))
                })
                
                if not existing:
                    # Crea o aggiorna verbale
                    verbale_doc = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})
                    
                    update_data = {
                        "fattura_id": str(fattura.get("_id")),
                        "fattura_numero": fattura.get("invoice_number"),
                        "fornitore": fattura.get("supplier_name") or fattura.get("fornitore"),
                        "targa": fattura.get("targa"),
                        "updated_at": datetime.now(timezone.utc)
                    }
                    
                    if verbale_doc:
                        # Aggiorna esistente
                        nuovo_stato = "riconciliato" if verbale_doc.get("pagamento_id") else "fattura_ricevuta"
                        update_data["stato"] = nuovo_stato
                        await db["verbali_noleggio"].update_one(
                            {"numero_verbale": numero_verbale},
                            {"$set": update_data}
                        )
                    else:
                        # Crea nuovo
                        update_data["numero_verbale"] = numero_verbale
                        update_data["stato"] = "fattura_ricevuta"
                        update_data["created_at"] = datetime.now(timezone.utc)
                        await db["verbali_noleggio"].insert_one(update_data)
                    
                    associazioni_create += 1
        
        return {
            "success": True,
            "fatture_analizzate": len(fatture),
            "verbali_trovati": verbali_trovati,
            "associazioni_create": associazioni_create
        }
    except Exception as e:
        logger.error(f"Errore scan fatture verbali: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/riconcilia/{numero_verbale}")
@handle_errors
async def riconcilia_verbale(numero_verbale: str) -> Dict[str, Any]:
    """
    Tenta riconciliazione automatica di un verbale.
    
    Cerca:
    1. Fattura con numero verbale nella descrizione
    2. Pagamento in estratto conto
    3. Veicolo associato
    4. Driver assegnato al veicolo
    """
    db = Database.get_db()
    
    try:
        verbale = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})
        
        if not verbale:
            raise HTTPException(status_code=404, detail="Verbale non trovato")
        
        updates = {}
        messages = []
        
        # 1. Cerca fattura se non presente
        if not verbale.get("fattura_id"):
            fattura = await db["invoices"].find_one({
                "$or": [
                    {"descrizione": {"$regex": numero_verbale, "$options": "i"}},
                    {"body": {"$regex": numero_verbale, "$options": "i"}},
                    {"note": {"$regex": numero_verbale, "$options": "i"}},
                    {"notes": {"$regex": numero_verbale, "$options": "i"}},
                    {"oggetto": {"$regex": numero_verbale, "$options": "i"}},
                    {"subject": {"$regex": numero_verbale, "$options": "i"}},
                    {"items.descrizione": {"$regex": numero_verbale, "$options": "i"}},
                    {"items.description": {"$regex": numero_verbale, "$options": "i"}}
                ]
            })
            
            if fattura:
                updates["fattura_id"] = str(fattura["_id"])
                updates["fattura_numero"] = fattura.get("invoice_number")
                updates["fornitore"] = fattura.get("supplier_name") or fattura.get("fornitore")
                messages.append(f"Fattura trovata: {fattura.get('invoice_number')}")
        
        # 2. Cerca targa se non presente
        targa = verbale.get("targa") or updates.get("targa")
        if not targa:
            # Cerca in verbali_noleggio_completi
            completo = await db["verbali_noleggio_completi"].find_one({"numero_verbale": numero_verbale})
            if completo and completo.get("targa"):
                targa = completo["targa"]
                updates["targa"] = targa
                messages.append(f"Targa trovata: {targa}")
        
        # 3. Cerca veicolo e driver
        if targa:
            veicolo = await db["veicoli_noleggio"].find_one({"targa": targa})
            if veicolo:
                updates["veicolo_id"] = str(veicolo["_id"])
                if veicolo.get("driver_id"):
                    updates["driver_id"] = veicolo["driver_id"]
                    
                    # Trova nome driver
                    driver = await db["dipendenti"].find_one({"_id": ObjectId(veicolo["driver_id"])})
                    if driver:
                        updates["driver_nome"] = f"{driver.get('nome', '')} {driver.get('cognome', '')}"
                        messages.append(f"Driver: {updates['driver_nome']}")
        
        # 4. Determina nuovo stato
        has_fattura = verbale.get("fattura_id") or updates.get("fattura_id")
        has_pagamento = verbale.get("pagamento_id")
        
        if has_fattura and has_pagamento:
            updates["stato"] = "riconciliato"
        elif has_fattura:
            updates["stato"] = "fattura_ricevuta"
        elif has_pagamento:
            updates["stato"] = "pagato"
        
        # Applica updates
        if updates:
            updates["updated_at"] = datetime.now(timezone.utc)
            await db["verbali_noleggio"].update_one(
                {"numero_verbale": numero_verbale},
                {"$set": updates}
            )
        
        # Ricarica verbale aggiornato
        verbale = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})
        
        return {
            "success": True,
            "numero_verbale": numero_verbale,
            "stato": verbale.get("stato"),
            "azioni": messages,
            "verbale": serialize_doc(verbale)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore riconciliazione verbale: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collega-driver-massivo")
@handle_errors
async def collega_driver_massivo() -> Dict[str, Any]:
    """
    Collega automaticamente i verbali ai driver con strategia multi-livello:
    
    1. Targa → veicolo_noleggio → driver_id
    2. Targa → storico_assegnazioni_veicoli (driver alla data violazione)
    3. Targa → contratti_noleggio → intestatario/driver
    4. Targa → employees (veicolo_assegnato)
    5. Descrizione verbale → estrae nome/cognome → dipendente
    """
    db = Database.get_db()
    
    try:
        # Trova verbali con targa ma senza driver
        verbali = await db["verbali_noleggio"].find({
            "targa": {"$exists": True, "$nin": [None, ""]},
            "$or": [
                {"driver_id": {"$exists": False}},
                {"driver_id": None},
                {"driver_id": ""}
            ]
        }).to_list(1000)
        
        collegati = 0
        strategie_usate = {"veicolo": 0, "storico": 0, "contratto": 0, "dipendente": 0, "descrizione": 0}
        non_trovati = []
        
        for verbale in verbali:
            targa = (verbale.get("targa") or "").upper()
            data_violazione = verbale.get("data_violazione") or verbale.get("data_verbale")
            numero = verbale.get("numero_verbale", "?")
            
            if not targa:
                continue
            
            driver_id = None
            driver_nome = None
            strategia = None
            
            # === STRATEGIA 1: veicolo_noleggio → driver ===
            veicolo = await db["veicoli_noleggio"].find_one({"targa": targa})
            if veicolo:
                if veicolo.get("driver_id"):
                    driver_id = veicolo["driver_id"]
                    driver_nome = veicolo.get("driver") or veicolo.get("driver_nome")
                    strategia = "veicolo"
                elif veicolo.get("driver"):
                    driver_nome = veicolo["driver"]
                    strategia = "veicolo"
            
            # === STRATEGIA 2: storico assegnazioni (driver alla data della violazione) ===
            if not driver_id and not driver_nome:
                query_storico = {"targa": targa}
                if data_violazione:
                    query_storico["$or"] = [
                        {"data_inizio": {"$lte": data_violazione}, "data_fine": {"$gte": data_violazione}},
                        {"data_inizio": {"$lte": data_violazione}, "data_fine": {"$exists": False}},
                    ]
                
                storico = await db["storico_assegnazioni_veicoli"].find_one(
                    query_storico,
                    sort=[("data_inizio", -1)]
                )
                if storico and (storico.get("driver_id") or storico.get("driver")):
                    driver_id = storico.get("driver_id")
                    driver_nome = storico.get("driver") or storico.get("driver_nome")
                    strategia = "storico"
            
            # === STRATEGIA 3: contratti noleggio ===
            if not driver_id and not driver_nome:
                contratto = await db["contratti_noleggio"].find_one(
                    {"$or": [{"targa": targa}, {"targhe": targa}]}
                )
                if contratto and (contratto.get("driver") or contratto.get("intestatario")):
                    driver_nome = contratto.get("driver") or contratto.get("intestatario")
                    driver_id = contratto.get("driver_id")
                    strategia = "contratto"
            
            # === STRATEGIA 4: dipendenti con veicolo assegnato ===
            if not driver_id and not driver_nome:
                dipendente = await db["dipendenti"].find_one({
                    "$or": [
                        {"veicolo_targa": targa},
                        {"targa_assegnata": targa},
                        {"auto_aziendale": {"$regex": targa, "$options": "i"}}
                    ]
                })
                if not dipendente:
                    dipendente = await db["dipendenti"].find_one({
                        "$or": [
                            {"veicolo_targa": targa},
                            {"targa_assegnata": targa}
                        ]
                    })
                
                if dipendente:
                    driver_id = dipendente.get("id") or str(dipendente.get("_id"))
                    driver_nome = (
                        dipendente.get("nome_completo") or
                        f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}".strip()
                    )
                    strategia = "dipendente"
            
            # === STRATEGIA 5: cerca nome nella descrizione del verbale ===
            if not driver_id and not driver_nome:
                desc = (verbale.get("descrizione") or verbale.get("note") or "").upper()
                if desc:
                    # Prendi tutti i dipendenti attivi e cerca nome/cognome nel testo
                    all_dip = await db["dipendenti"].find(
                        {"stato": {"$ne": "cessato"}},
                        {"_id": 0, "id": 1, "cognome": 1, "nome": 1, "nome_completo": 1}
                    ).to_list(200)
                    
                    for dip in all_dip:
                        cognome = (dip.get("cognome") or "").upper()
                        if cognome and len(cognome) > 2 and cognome in desc:
                            driver_id = dip.get("id")
                            driver_nome = dip.get("nome_completo") or f"{dip.get('nome', '')} {cognome}"
                            strategia = "descrizione"
                            break
            
            # === APPLICA RISULTATO ===
            if driver_id or driver_nome:
                update_data = {"updated_at": datetime.now(timezone.utc)}
                if driver_id:
                    update_data["driver_id"] = driver_id
                if driver_nome:
                    update_data["driver_nome"] = driver_nome.strip()
                    update_data["driver"] = driver_nome.strip()
                
                await db["verbali_noleggio"].update_one(
                    {"_id": verbale["_id"]},
                    {"$set": update_data}
                )
                collegati += 1
                if strategia:
                    strategie_usate[strategia] = strategie_usate.get(strategia, 0) + 1
            else:
                non_trovati.append({
                    "numero": numero,
                    "targa": targa,
                    "data": data_violazione
                })
        
        return {
            "success": True,
            "verbali_analizzati": len(verbali),
            "collegati_a_driver": collegati,
            "strategie": strategie_usate,
            "non_trovati": non_trovati[:30],
            "non_trovati_count": len(non_trovati)
        }
    except Exception as e:
        logger.error(f"Errore collegamento driver massivo: {e}")
        raise HTTPException(status_code=500, detail=str(e))




@router.get("/per-driver/{driver_id}")
@handle_errors
async def get_verbali_per_driver(driver_id: str) -> Dict[str, Any]:
    """Lista verbali associati a un driver specifico."""
    db = Database.get_db()
    
    try:
        verbali = await db["verbali_noleggio"].find({"driver_id": driver_id}).sort("created_at", -1).to_list(100)
        
        # Calcola totali
        totale_verbali = sum(v.get("importo", 0) or 0 for v in verbali)
        totale_notifiche = sum(v.get("importo_notifica", 0) or 0 for v in verbali)
        
        return {
            "success": True,
            "driver_id": driver_id,
            "verbali": [serialize_doc(v) for v in verbali],
            "totale": len(verbali),
            "totale_verbali": round(totale_verbali, 2),
            "totale_notifiche": round(totale_notifiche, 2)
        }
    except Exception as e:
        logger.error(f"Errore verbali per driver: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/per-veicolo/{targa}")
@handle_errors
async def get_verbali_per_veicolo(targa: str) -> Dict[str, Any]:
    """Lista verbali associati a un veicolo specifico."""
    db = Database.get_db()
    
    try:
        verbali = await db["verbali_noleggio"].find({"targa": targa.upper()}).sort("created_at", -1).to_list(100)
        
        return {
            "success": True,
            "targa": targa.upper(),
            "verbali": [serialize_doc(v) for v in verbali],
            "totale": len(verbali)
        }
    except Exception as e:
        logger.error(f"Errore verbali per veicolo: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ===== AUTOMAZIONE VERBALI =====

async def associa_verbale_completo(db, verbale_doc: dict) -> dict:
    """
    Funzione di automazione che viene chiamata ogni volta che un verbale viene trovato/creato.
    
    Associa automaticamente:
    1. Driver (da targa -> veicolo -> driver)
    2. Veicolo (da targa)
    3. Contratto (da veicolo)
    4. Cliente/Codice (da veicolo)
    5. Crea scrittura in Prima Nota se c'è un pagamento
    
    Returns: verbale aggiornato con tutte le associazioni
    """
    numero_verbale = verbale_doc.get("numero_verbale")
    if not numero_verbale:
        return verbale_doc
    
    updates = {}
    log_messages = []
    
    # === 1. TROVA TARGA ===
    targa = verbale_doc.get("targa")
    
    if not targa:
        # Cerca in verbali_noleggio_completi
        completo = await db["verbali_noleggio_completi"].find_one({"numero_verbale": numero_verbale})
        if completo and completo.get("targa"):
            targa = completo["targa"].upper()
            updates["targa"] = targa
            log_messages.append(f"Targa trovata da completi: {targa}")
        
        # Cerca nella descrizione del verbale stesso
        if not targa and verbale_doc.get("descrizione"):
            extracted = extract_targa_from_description(verbale_doc["descrizione"])
            if extracted:
                targa = extracted.upper()
                updates["targa"] = targa
                log_messages.append(f"Targa estratta da descrizione: {targa}")
    
    # === 2. TROVA VEICOLO DA TARGA ===
    if targa:
        veicolo = await db["veicoli_noleggio"].find_one({"targa": targa.upper()})
        
        if veicolo:
            updates["veicolo_id"] = veicolo.get("id") or str(veicolo.get("_id"))
            updates["modello"] = veicolo.get("modello")
            updates["marca"] = veicolo.get("marca")
            log_messages.append(f"Veicolo trovato: {veicolo.get('marca')} {veicolo.get('modello')}")
            
            # === 3. TROVA CONTRATTO ===
            if veicolo.get("contratto"):
                updates["contratto"] = veicolo["contratto"]
                log_messages.append(f"Contratto: {veicolo['contratto']}")
            
            # === 4. TROVA CODICE CLIENTE ===
            if veicolo.get("codice_cliente"):
                updates["codice_cliente"] = veicolo["codice_cliente"]
                log_messages.append(f"Codice cliente: {veicolo['codice_cliente']}")
            
            # === 5. TROVA DRIVER ===
            if veicolo.get("driver_id"):
                updates["driver_id"] = veicolo["driver_id"]
                
                # Trova nome driver da dipendenti o dal veicolo stesso
                if veicolo.get("driver"):
                    updates["driver"] = veicolo["driver"]
                    updates["driver_nome"] = veicolo["driver"]
                    log_messages.append(f"Driver: {veicolo['driver']}")
                else:
                    # Cerca in dipendenti
                    try:
                        dipendente = await db["dipendenti"].find_one({"id": veicolo["driver_id"]})
                        if dipendente:
                            nome_completo = f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}".strip()
                            updates["driver"] = nome_completo
                            updates["driver_nome"] = nome_completo
                            log_messages.append(f"Driver da dipendenti: {nome_completo}")
                    except Exception:
                        pass
            elif veicolo.get("driver"):
                # Driver come stringa nel veicolo
                updates["driver"] = veicolo["driver"]
                updates["driver_nome"] = veicolo["driver"]
                log_messages.append(f"Driver: {veicolo['driver']}")
    
    # === 6. CERCA DATI DA FATTURA ASSOCIATA ===
    if verbale_doc.get("fattura_id") or updates.get("fattura_id"):
        fattura_id = verbale_doc.get("fattura_id") or updates.get("fattura_id")
        try:
            from bson import ObjectId
            from bson.errors import InvalidId
            fattura = await db["invoices"].find_one({"_id": ObjectId(fattura_id)})
            if not fattura:
                fattura = await db["invoices"].find_one({"id": fattura_id})
            
            if fattura:
                if not updates.get("fornitore") and fattura.get("supplier_name"):
                    updates["fornitore"] = fattura["supplier_name"]
                if not updates.get("fornitore_piva") and fattura.get("supplier_vat"):
                    updates["fornitore_piva"] = fattura["supplier_vat"]
        except Exception as e:
            logger.warning(f"Errore recupero fattura {fattura_id}: {e}")
    
    # === 7. DETERMINA STATO ===
    has_fattura = verbale_doc.get("fattura_id") or updates.get("fattura_id")
    has_pagamento = verbale_doc.get("pagamento_id") or verbale_doc.get("movimento_banca_id")
    has_driver = verbale_doc.get("driver_id") or updates.get("driver_id")
    
    if has_fattura and has_pagamento and has_driver:
        updates["stato"] = "riconciliato"
        updates["riconciliato"] = True
    elif has_fattura and has_pagamento:
        updates["stato"] = "pagato"
    elif has_fattura:
        updates["stato"] = "fattura_ricevuta"
    elif has_driver or targa:
        updates["stato"] = "identificato"
    
    # === 8. APPLICA UPDATES ===
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc)
        await db["verbali_noleggio"].update_one(
            {"numero_verbale": numero_verbale},
            {"$set": updates}
        )
        logger.info(f"Verbale {numero_verbale} aggiornato: {', '.join(log_messages)}")
    
    # Restituisci verbale aggiornato
    verbale_aggiornato = await db["verbali_noleggio"].find_one(
        {"numero_verbale": numero_verbale},
        {"_id": 0}
    )
    
    return verbale_aggiornato or verbale_doc


@router.post("/automazione-completa")
@handle_errors
async def esegui_automazione_completa() -> Dict[str, Any]:
    """
    Esegue l'automazione completa su tutti i verbali esistenti.
    
    Per ogni verbale:
    1. Associa targa
    2. Trova veicolo
    3. Trova driver
    4. Trova contratto
    5. Trova codice cliente
    6. Aggiorna stato
    """
    db = Database.get_db()
    
    try:
        # Prendi tutti i verbali
        verbali = await db["verbali_noleggio"].find({}).to_list(1000)
        
        risultati = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "verbali_processati": 0,
            "driver_associati": 0,
            "veicoli_associati": 0,
            "contratti_associati": 0,
            "riconciliati": 0,
            "errori": []
        }
        
        for verbale in verbali:
            try:
                aveva_driver = bool(verbale.get("driver_id"))
                aveva_veicolo = bool(verbale.get("veicolo_id"))
                aveva_contratto = bool(verbale.get("contratto"))
                era_riconciliato = verbale.get("stato") == "riconciliato"
                
                # Esegui automazione
                aggiornato = await associa_verbale_completo(db, verbale)
                
                risultati["verbali_processati"] += 1
                
                if not aveva_driver and aggiornato.get("driver_id"):
                    risultati["driver_associati"] += 1
                if not aveva_veicolo and aggiornato.get("veicolo_id"):
                    risultati["veicoli_associati"] += 1
                if not aveva_contratto and aggiornato.get("contratto"):
                    risultati["contratti_associati"] += 1
                if not era_riconciliato and aggiornato.get("stato") == "riconciliato":
                    risultati["riconciliati"] += 1
                    
            except Exception as e:
                risultati["errori"].append(f"{verbale.get('numero_verbale')}: {str(e)}")
        
        return {
            "success": True,
            **risultati
        }
    except Exception as e:
        logger.error(f"Errore automazione completa: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/crea-prima-nota-verbale/{numero_verbale}")
@handle_errors
async def crea_prima_nota_verbale(numero_verbale: str) -> Dict[str, Any]:
    """
    Crea una scrittura in Prima Nota per un verbale.
    
    Se il verbale ha un pagamento associato, crea il movimento in prima_nota_cassa o prima_nota_banca.
    """
    db = Database.get_db()
    
    try:
        verbale = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})
        
        if not verbale:
            raise HTTPException(status_code=404, detail="Verbale non trovato")
        
        importo = verbale.get("importo") or 0
        if not importo:
            return {
                "success": False,
                "message": "Verbale senza importo - impossibile creare Prima Nota"
            }
        
        # Verifica se esiste già un movimento
        if verbale.get("movimento_banca_id") or verbale.get("movimento_cassa_id"):
            return {
                "success": False,
                "message": "Movimento Prima Nota già esistente per questo verbale"
            }
        
        import uuid
        
        # Crea movimento in prima_nota_cassa (default per verbali pagati in contanti/carta)
        movimento = {
            "id": str(uuid.uuid4()),
            "data": verbale.get("data_pagamento") or verbale.get("data_verbale") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "tipo": "uscita",
            "importo": float(importo),
            "descrizione": f"Verbale {numero_verbale} - {verbale.get('driver_nome', 'N/D')} - Targa {verbale.get('targa', 'N/D')}",
            "categoria": "Verbali/Multe",
            "verbale_id": numero_verbale,
            "targa": verbale.get("targa"),
            "driver_id": verbale.get("driver_id"),
            "driver_nome": verbale.get("driver_nome"),
            "fornitore": verbale.get("fornitore"),
            "source": "verbale_automazione",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Inserisci in prima_nota_cassa
        await db["prima_nota_cassa"].insert_one(movimento.copy())
        
        # Aggiorna verbale con riferimento al movimento
        await db["verbali_noleggio"].update_one(
            {"numero_verbale": numero_verbale},
            {"$set": {
                "movimento_cassa_id": movimento["id"],
                "stato": "riconciliato" if verbale.get("fattura_id") else "pagato",
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        
        logger.info(f"Prima Nota creata per verbale {numero_verbale}: €{importo}")
        
        return {
            "success": True,
            "message": f"Movimento Prima Nota creato per verbale {numero_verbale}",
            "movimento_id": movimento["id"],
            "importo": importo
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore creazione Prima Nota verbale: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== ENDPOINT GESTIONE PENDING E SCAN EMAIL =====

@router.get("/pending-status")
@handle_errors
async def get_pending_status() -> Dict[str, Any]:
    """
    Restituisce lo stato delle cose sospese da completare.
    
    Utile per capire quanti verbali hanno bisogno di:
    - Quietanza di pagamento
    - PDF allegato
    - Fattura associata
    """
    db = Database.get_db()
    
    try:
        # Conta verbali per stato
        stati = await db["verbali_noleggio"].aggregate([
            {"$group": {"_id": "$stato", "count": {"$sum": 1}}}
        ]).to_list(20)
        
        stati_dict = {s["_id"]: s["count"] for s in stati if s["_id"]}
        
        # Conta senza quietanza (da pagare)
        senza_quietanza = await db["verbali_noleggio"].count_documents({
            "stato": {"$in": ["da_pagare", "DA_PAGARE", "identificato", "fattura_ricevuta"]},
            "$or": [
                {"quietanza_ricevuta": {"$exists": False}},
                {"quietanza_ricevuta": False}
            ]
        })
        
        # Conta senza PDF
        senza_pdf = await db["verbali_noleggio"].count_documents({
            "$or": [
                {"pdf_data": {"$exists": False}},
                {"pdf_data": None},
                {"pdf_data": ""}
            ]
        })
        
        # Conta senza fattura
        senza_fattura = await db["verbali_noleggio"].count_documents({
            "$or": [
                {"fattura_id": {"$exists": False}},
                {"fattura_id": None}
            ]
        })
        
        # Conta senza driver
        senza_driver = await db["verbali_noleggio"].count_documents({
            "$or": [
                {"driver_id": {"$exists": False}},
                {"driver_id": None}
            ]
        })
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "totale_verbali": sum(stati_dict.values()),
            "per_stato": stati_dict,
            "da_completare": {
                "senza_quietanza": senza_quietanza,
                "senza_pdf": senza_pdf,
                "senza_fattura": senza_fattura,
                "senza_driver": senza_driver
            },
            "priorita_scan": [
                f"{senza_quietanza} verbali attendono quietanza",
                f"{senza_pdf} verbali senza PDF allegato",
                f"{senza_driver} verbali senza driver associato"
            ]
        }
    except Exception as e:
        logger.error(f"Errore get pending status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/per-dipendente/{driver_id}")
@handle_errors
async def get_verbali_per_dipendente(driver_id: str) -> Dict[str, Any]:
    """
    Restituisce tutti i verbali associati a un dipendente.
    
    Per ogni verbale include:
    - Numero verbale
    - Targa
    - Data
    - Importo
    - Stato (pagato/da pagare/riconciliato)
    - Link al PDF (se disponibile)
    """
    db = Database.get_db()
    
    try:
        # Cerca verbali per driver_id
        verbali = await db["verbali_noleggio"].find(
            {"driver_id": driver_id},
            {"_id": 0, "pdf_data": 0}  # Esclude PDF per performance
        ).sort("data_verbale", -1).to_list(500)
        
        # Se non trova, cerca per nome driver
        if not verbali:
            # Trova il nome del driver
            dipendente = await db["dipendenti"].find_one({"id": driver_id})
            if dipendente:
                nome = f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}".strip().upper()
                verbali = await db["verbali_noleggio"].find(
                    {"$or": [
                        {"driver": nome},
                        {"driver_nome": nome}
                    ]},
                    {"_id": 0, "pdf_data": 0}
                ).sort("data_verbale", -1).to_list(500)
        
        # Calcola totali
        totale_importo = sum(v.get("importo") or v.get("importo_rinotifica") or 0 for v in verbali)
        da_pagare = [v for v in verbali if v.get("stato") in ["da_pagare", "DA_PAGARE", "identificato", "fattura_ricevuta"]]
        pagati = [v for v in verbali if v.get("stato") in ["pagato", "PAGATO", "riconciliato", "RICONCILIATO"]]
        
        totale_da_pagare = sum(v.get("importo") or v.get("importo_rinotifica") or 0 for v in da_pagare)
        totale_pagati = sum(v.get("importo") or v.get("importo_rinotifica") or 0 for v in pagati)
        
        # Aggiungi flag has_pdf per ogni verbale
        for v in verbali:
            v["has_pdf"] = bool(v.get("pdf_allegati") or v.get("cartella_email"))
        
        return {
            "driver_id": driver_id,
            "totale_verbali": len(verbali),
            "totale_importo": totale_importo,
            "da_pagare": {
                "count": len(da_pagare),
                "importo": totale_da_pagare
            },
            "pagati": {
                "count": len(pagati),
                "importo": totale_pagati
            },
            "verbali": verbali
        }
    except Exception as e:
        logger.error(f"Errore get verbali per dipendente: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/per-targa/{targa}")
@handle_errors
async def get_verbali_per_targa(targa: str) -> Dict[str, Any]:
    """
    Restituisce tutti i verbali associati a una targa.
    """
    db = Database.get_db()
    
    try:
        verbali = await db["verbali_noleggio"].find(
            {"targa": targa.upper()},
            {"_id": 0, "pdf_data": 0}
        ).sort("data_verbale", -1).to_list(500)
        
        totale_importo = sum(v.get("importo") or v.get("importo_rinotifica") or 0 for v in verbali)
        
        return {
            "targa": targa.upper(),
            "totale_verbali": len(verbali),
            "totale_importo": totale_importo,
            "verbali": verbali
        }
    except Exception as e:
        logger.error(f"Errore get verbali per targa: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{numero_verbale}/pdf")
@handle_errors
async def get_verbale_pdf(numero_verbale: str):
    """
    Restituisce il PDF di un verbale specifico.
    """
    from fastapi.responses import Response
    import base64
    
    db = Database.get_db()
    
    try:
        verbale = await db["verbali_noleggio"].find_one(
            {"numero_verbale": numero_verbale},
            {"pdf_data": 1, "pdf_allegati": 1}
        )
        
        if not verbale:
            raise HTTPException(status_code=404, detail="Verbale non trovato")
        
        pdf_data = verbale.get("pdf_data")
        
        if not pdf_data:
            # Prova a cercare in pdf_allegati
            pdf_allegati = verbale.get("pdf_allegati", [])
            if pdf_allegati and isinstance(pdf_allegati, list) and len(pdf_allegati) > 0:
                pdf_data = pdf_allegati[0].get("data")
        
        if not pdf_data:
            raise HTTPException(status_code=404, detail="PDF non disponibile per questo verbale")
        
        # Decodifica base64 se necessario
        if isinstance(pdf_data, str):
            pdf_bytes = base64.b64decode(pdf_data)
        else:
            pdf_bytes = pdf_data
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename=verbale_{numero_verbale}.pdf"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore get verbale PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/registra-quietanza/{numero_verbale}")
@handle_errors
async def registra_quietanza(numero_verbale: str, quietanza_data: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Registra una quietanza di pagamento per un verbale.
    
    Chiamato quando si trova una quietanza (PayPal, bonifico, ricevuta) nelle email.
    Aggiorna lo stato del verbale a "pagato" o "riconciliato".
    """
    db = Database.get_db()
    
    try:
        verbale = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})
        
        if not verbale:
            raise HTTPException(status_code=404, detail="Verbale non trovato")
        
        # Prepara update
        update_data = {
            "quietanza_ricevuta": True,
            "data_quietanza": datetime.now(timezone.utc).isoformat(),
            "stato_pagamento": "pagato",
            "updated_at": datetime.now(timezone.utc)
        }
        
        # Se ha fattura, è riconciliato
        if verbale.get("fattura_id"):
            update_data["stato"] = "riconciliato"
            update_data["riconciliato"] = True
        else:
            update_data["stato"] = "pagato"
        
        # Aggiungi dati quietanza se forniti
        if quietanza_data:
            if quietanza_data.get("metodo"):
                update_data["metodo_pagamento"] = quietanza_data["metodo"]  # PayPal, bonifico, etc.
            if quietanza_data.get("data_pagamento"):
                update_data["data_pagamento"] = quietanza_data["data_pagamento"]
            if quietanza_data.get("riferimento"):
                update_data["riferimento_pagamento"] = quietanza_data["riferimento"]
            if quietanza_data.get("pdf_data"):
                update_data["quietanza_pdf"] = quietanza_data["pdf_data"]
        
        await db["verbali_noleggio"].update_one(
            {"numero_verbale": numero_verbale},
            {"$set": update_data}
        )
        
        logger.info(f"✅ Quietanza registrata per verbale {numero_verbale}")
        
        return {
            "success": True,
            "message": f"Quietanza registrata per verbale {numero_verbale}",
            "nuovo_stato": update_data.get("stato")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore registrazione quietanza: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ===== SCAN EMAIL VERBALI =====

@router.post("/scan-email")
@handle_errors
async def scan_email_verbali(days_back: int = 365) -> Dict[str, Any]:
    """
    Esegue lo scan email per verbali con logica di priorità.
    
    LOGICA:
    1. FASE 1 - Cerca documenti per completare verbali SOSPESI
       - Quietanze per verbali "da_pagare"
       - PDF per verbali senza allegato
       
    2. FASE 2 - Aggiungi nuovi verbali trovati
    
    Args:
        days_back: Quanti giorni indietro cercare (default 365 = 1 anno)
    
    Returns:
        Risultati dello scan con statistiche
    """
    db = Database.get_db()
    
    try:
        from app.services.verbali_email_scanner import esegui_scan_verbali_email
        
        logger.info(f"🚀 Avvio scan email verbali (ultimi {days_back} giorni)...")
        risultato = await esegui_scan_verbali_email(db, days_back)
        
        return risultato
    except ImportError as e:
        logger.error(f"Modulo scanner non disponibile: {e}")
        return {
            "success": False,
            "error": "Modulo scanner email non disponibile",
            "detail": str(e)
        }
    except Exception as e:
        logger.error(f"Errore scan email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan-email-storico")
@handle_errors
async def scan_email_storico() -> Dict[str, Any]:
    """
    Esegue lo scan email COMPLETO dal 2018 ad oggi.
    
    ATTENZIONE: Operazione lunga! Può richiedere diversi minuti.
    Usare per la prima sincronizzazione o per recuperare tutto lo storico.
    """
    db = Database.get_db()
    
    try:
        from app.services.verbali_email_scanner import esegui_scan_verbali_email
        
        # Calcola giorni dal 2018
        from datetime import datetime
        days_from_2018 = (datetime.now() - datetime(2018, 1, 1)).days
        
        logger.info(f"🚀 Avvio scan email STORICO dal 2018 ({days_from_2018} giorni)...")
        risultato = await esegui_scan_verbali_email(db, days_from_2018)
        
        return {
            **risultato,
            "note": f"Scan storico dal 2018: {days_from_2018} giorni analizzati"
        }
    except Exception as e:
        logger.error(f"Errore scan storico: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan-verbale/{numero_verbale}")
@handle_errors
async def scan_singolo_verbale(numero_verbale: str) -> Dict[str, Any]:
    """
    Scansiona le email per trovare quietanza/PDF di un verbale specifico.
    
    Cerca nella cartella dedicata al verbale e in INBOX.
    """
    db = Database.get_db()
    
    try:
        from app.services.verbali_email_scanner import VerbaliEmailScanner
        
        scanner = VerbaliEmailScanner(db)
        
        if not scanner.connect():
            raise HTTPException(status_code=500, detail="Connessione email fallita")
        
        try:
            # Cerca quietanza
            quietanza_trovata = await scanner.cerca_quietanza_per_verbale(numero_verbale)
            
            # Cerca PDF se non presente
            pdf_trovato = await scanner.cerca_pdf_per_verbale(numero_verbale)
            
            # Aggiorna verbale
            verbale = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})
            
            return {
                "success": True,
                "numero_verbale": numero_verbale,
                "quietanza_trovata": quietanza_trovata,
                "pdf_trovato": pdf_trovato,
                "stato_attuale": verbale.get("stato") if verbale else "non_trovato",
                "message": f"Scan completato per {numero_verbale}"
            }
        finally:
            scanner.disconnect()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore scan verbale {numero_verbale}: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/riconcilia-estratto-conto-paypal")
@handle_errors
async def riconcilia_estratto_conto_paypal(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Importa estratto conto PayPal e riconcilia i pagamenti con i verbali.
    
    Formato file atteso: CSV con colonne Data, Descrizione, Importo
    Cerca verbali pagati nelle stesse date e li riconcilia.
    """
    db = Database.get_db()
    
    try:
        import csv
        import io
        
        content = await file.read()
        content_str = content.decode('utf-8', errors='replace')
        
        reader = csv.DictReader(io.StringIO(content_str))
        
        risultato = {
            "righe_processate": 0,
            "verbali_riconciliati": 0,
            "verbali_non_trovati": 0,
            "dettagli": []
        }
        
        for row in reader:
            risultato["righe_processate"] += 1
            
            # Cerca riferimenti a verbali o comuni
            descrizione = row.get("Descrizione", "") or row.get("Description", "") or ""
            data = row.get("Data", "") or row.get("Date", "") or ""
            importo = row.get("Importo", "") or row.get("Amount", "") or row.get("Netto", "") or ""
            
            # Cerca numero verbale nella descrizione
            import re
            verbale_match = re.search(r'([ABCDEFGHIJKLMNOPQRSTUVWXYZ]\d{10,12})', descrizione)
            
            if verbale_match:
                numero_verbale = verbale_match.group(1)
                
                # Cerca verbale
                verbale = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})
                
                if verbale:
                    # Riconcilia
                    await db["verbali_noleggio"].update_one(
                        {"numero_verbale": numero_verbale},
                        {"$set": {
                            "stato": "riconciliato",
                            "riconciliato": True,
                            "movimento_paypal": {
                                "data": data,
                                "descrizione": descrizione,
                                "importo": importo
                            },
                            "documenti.estratto_conto_riconciliato": True,
                            "pagamento.riconciliato_estratto_conto": True,
                            "in_attesa": [],
                            "updated_at": datetime.now(timezone.utc)
                        }}
                    )
                    risultato["verbali_riconciliati"] += 1
                    risultato["dettagli"].append({
                        "verbale": numero_verbale,
                        "importo": importo,
                        "stato": "riconciliato"
                    })
                else:
                    risultato["verbali_non_trovati"] += 1
            else:
                # Cerca per descrizione (es. "Comune di Napoli")
                if "comune" in descrizione.lower():
                    # Cerca verbali pagati in quella data
                    verbali = await db["verbali_noleggio"].find({
                        "pagamento.data": {"$regex": data[:10] if data else ""},
                        "pagamento.riconciliato_estratto_conto": {"$ne": True}
                    }).to_list(10)
                    
                    for v in verbali:
                        await db["verbali_noleggio"].update_one(
                            {"numero_verbale": v["numero_verbale"]},
                            {"$set": {
                                "stato": "riconciliato" if v.get("fattura_id") else "pagato",
                                "movimento_paypal": {
                                    "data": data,
                                    "descrizione": descrizione,
                                    "importo": importo
                                },
                                "documenti.estratto_conto_riconciliato": True,
                                "pagamento.riconciliato_estratto_conto": True,
                                "updated_at": datetime.now(timezone.utc)
                            }}
                        )
                        risultato["verbali_riconciliati"] += 1
        
        return {
            "success": True,
            **risultato
        }
    except Exception as e:
        logger.error(f"Errore riconciliazione estratto conto: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dettaglio-completo/{numero_verbale}")
@handle_errors
async def get_dettaglio_completo_verbale(numero_verbale: str) -> Dict[str, Any]:
    """
    Restituisce tutti i dettagli e documenti di un verbale.
    
    Include:
    - Dati verbale
    - PDF verbale (link)
    - Quietanza pagamento
    - Fattura ri-notifica
    - Stato riconciliazione
    """
    db = Database.get_db()
    
    try:
        verbale = await db["verbali_noleggio"].find_one(
            {"numero_verbale": numero_verbale},
            {"_id": 0}
        )
        
        if not verbale:
            raise HTTPException(status_code=404, detail="Verbale non trovato")
        
        # Costruisci riepilogo documenti
        documenti = verbale.get("documenti", {})
        
        checklist = {
            "pdf_verbale": bool(verbale.get("pdf_data") or verbale.get("pdf_filename") or documenti.get("pdf_verbale")),
            "targa_identificata": bool(verbale.get("targa")),
            "driver_associato": bool(verbale.get("driver_id") or verbale.get("driver")),
            "veicolo_associato": bool(verbale.get("veicolo_id")),
            "pagamento_effettuato": verbale.get("stato") not in ["da_scaricare", "salvato", "identificato", "da_pagare"],
            "quietanza_salvata": bool(verbale.get("quietanza_ricevuta") or documenti.get("quietanza_pagamento")),
            "fattura_rinotifica": bool(verbale.get("fattura_id") or documenti.get("fattura_rinotifica")),
            "estratto_conto_riconciliato": bool(documenti.get("estratto_conto_riconciliato") or verbale.get("pagamento", {}).get("riconciliato_estratto_conto"))
        }
        
        completamento = sum(checklist.values()) / len(checklist) * 100
        
        # Rimuovi pdf_data dalla risposta (troppo grande)
        verbale_response = {k: v for k, v in verbale.items() if k != "pdf_data"}
        verbale_response["has_pdf"] = bool(verbale.get("pdf_data"))
        
        return {
            "verbale": verbale_response,
            "checklist_riconciliazione": checklist,
            "percentuale_completamento": round(completamento, 1),
            "in_attesa": verbale.get("in_attesa", []),
            "prossimo_passo": _get_prossimo_passo(checklist)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore dettaglio verbale: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_prossimo_passo(checklist: Dict[str, bool]) -> str:
    """Determina il prossimo passo per completare il verbale."""
    if not checklist["pdf_verbale"]:
        return "Scaricare PDF verbale"
    if not checklist["targa_identificata"]:
        return "Identificare targa"
    if not checklist["driver_associato"]:
        return "Associare driver"
    if not checklist["pagamento_effettuato"]:
        return "Pagare verbale"
    if not checklist["quietanza_salvata"]:
        return "Salvare quietanza pagamento"
    if not checklist["fattura_rinotifica"]:
        return "Attendere fattura ri-notifica dal noleggiatore"
    if not checklist["estratto_conto_riconciliato"]:
        return "Riconciliare con estratto conto PayPal"
    return "✅ Verbale completamente riconciliato"


@router.get("/scheduler-status")
@handle_errors
async def get_scheduler_status() -> Dict[str, Any]:
    """
    Verifica lo stato dello scheduler automatico per lo scan verbali.
    """
    try:
        from app.scheduler import scheduler
        
        jobs = []
        for job in scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        
        # Trova il job dei verbali
        verbali_job = next((j for j in jobs if "verbali" in j["id"].lower()), None)
        
        return {
            "scheduler_running": scheduler.running,
            "verbali_scan_job": verbali_job,
            "all_jobs": jobs,
            "note": "Lo scan verbali email viene eseguito automaticamente ogni ora"
        }
    except Exception as e:
        return {
            "scheduler_running": False,
            "error": str(e),
            "note": "Scheduler non disponibile"
        }



# ===== SCAN PAGOPA QUIETANZE =====

@router.post("/scan-pagopa")
@handle_errors
async def scan_pagopa_quietanze(days_back: int = 365) -> Dict[str, Any]:
    """
    Scansiona Gmail per email PagoPA dai 3 mittenti ufficiali:
    - partenopay@ext.comune.napoli.it
    - noreply-checkout@ricevute.pagopa.it
    - notifica.pl.napoli@pec.it

    Cerca il numero verbale nel CORPO dell'email, salva il PDF allegato
    o genera un PDF dal corpo se non presente, e aggiorna il verbale in DB.
    """
    db = Database.get_db()
    try:
        from app.services.pagopa_scanner import scan_pagopa_email
        risultato = await scan_pagopa_email(db, days_back=days_back)
        return risultato
    except Exception as e:
        logger.error(f"Errore scan PagoPA: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quietanze-verbale/{numero_verbale}")
@handle_errors
async def get_quietanze_verbale(numero_verbale: str) -> Dict[str, Any]:
    """
    Restituisce tutte le quietanze PagoPA trovate per un dato verbale.
    """
    db = Database.get_db()
    cursor = db["quietanze_verbali"].find(
        {"verbale_numero": numero_verbale.upper()},
        {"_id": 0, "pdf_base64": 0}  # Escludi il PDF dalla risposta JSON
    ).sort("salvata_at", -1)
    quietanze = await cursor.to_list(length=50)
    return {
        "verbale": numero_verbale.upper(),
        "quietanze": quietanze,
        "totale": len(quietanze),
    }


@router.get("/quietanze-verbale/{numero_verbale}/pdf")
@handle_errors
async def download_quietanza_pdf(numero_verbale: str):
    """
    Scarica il PDF della quietanza PagoPA per un verbale.
    """
    from fastapi.responses import Response as FastAPIResponse
    db = Database.get_db()
    q = await db["quietanze_verbali"].find_one(
        {"verbale_numero": numero_verbale.upper(), "pdf_base64": {"$exists": True}},
        {"_id": 0},
    )
    if not q or not q.get("pdf_base64"):
        raise HTTPException(404, "Nessun PDF disponibile per questo verbale")
    import base64
    pdf_bytes = base64.b64decode(q["pdf_base64"])
    filename = q.get("pdf_filename", f"quietanza_{numero_verbale}.pdf")
    return FastAPIResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )
