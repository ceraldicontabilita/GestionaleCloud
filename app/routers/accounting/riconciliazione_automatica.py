"""
Riconciliazione Automatica v3 - Sistema di match automatico tra estratto conto e documenti.

REGOLE FONDAMENTALI:
1. Se TROVO match in estratto conto banca → posso mettere "Bonifico" o "Assegno N.XXX"
2. Se NON TROVO in estratto conto → NON posso mettere "Bonifico"
3. Devo rispettare il metodo di pagamento del fornitore (Cassa, Bonifico, etc.)
4. Match ESATTO per importo (±0.05€) o match parziale (pagamento rate)
5. Fuzzy matching per nome fornitore
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import uuid
import logging
import re

from app.database import Database, Collections
from app.models.stati import STATI_PAGATI

# Fuzzy matching per nomi fornitori
try:
    from rapidfuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False

logger = logging.getLogger(__name__)
router = APIRouter()

COLLECTION_ESTRATTO_CONTO = "estratto_conto_movimenti"
COLLECTION_PRIMA_NOTA_CASSA = "prima_nota_cassa"
COLLECTION_OPERAZIONI_DA_CONFERMARE = "operazioni_da_confermare"
COLLECTION_SUPPLIERS = "suppliers"
COLLECTION_ASSEGNI = "assegni"

# Importi commissioni bancarie da ignorare
IMPORTI_COMMISSIONI = [0.75, 1.00, 1.10, 1.50, 2.00, 2.50, 3.00]


def is_commissione(desc: str, imp: float) -> bool:
    """Verifica se è una commissione bancaria da ignorare."""
    desc_upper = (desc or "").upper()
    imp_abs = abs(imp)
    
    if any(kw in desc_upper for kw in ['COMMISSIONI', 'COMM.', 'SPESE TENUTA', 'CANONE', 'BOLLO', 'IMPOSTA']):
        return True
    
    if any(abs(imp_abs - c) < 0.01 for c in IMPORTI_COMMISSIONI) and imp_abs <= 3.00:
        return True
    
    return False


def match_fornitore_descrizione(fornitore: str, descrizione: str, fuzzy_threshold: int = 80) -> int:
    """
    Verifica se il nome fornitore è presente nella descrizione dell'estratto conto.
    Usa fuzzy matching per gestire variazioni nel nome.
    
    Returns:
        - 0: Nessun match
        - 1: Match parziale (fuzzy)
        - 2: Match esatto (parole esatte trovate)
    """
    if not fornitore or not descrizione:
        return 0
    
    desc_upper = descrizione.upper()
    fornitore_upper = fornitore.upper()
    
    # Rimuovi forme giuridiche comuni per il confronto
    forme_giuridiche = ['S.R.L.', 'SRL', 'S.P.A.', 'SPA', 'S.A.S.', 'SAS', 'S.N.C.', 'SNC', 'DI', 'DI.', 'SOCIETA', 'SOCIETÀ']
    fornitore_clean = fornitore_upper
    for fg in forme_giuridiche:
        fornitore_clean = fornitore_clean.replace(fg, '')
    
    # Pulisci anche la descrizione
    desc_clean = desc_upper
    for fg in forme_giuridiche:
        desc_clean = desc_clean.replace(fg, '')
    
    # Estrai parole significative (>3 caratteri)
    parole_fornitore = [p.strip() for p in fornitore_clean.split() if len(p.strip()) > 3]
    
    if not parole_fornitore:
        return 0
    
    # === 1. Match esatto: cerca parole del fornitore nella descrizione ===
    matches_esatti = sum(1 for p in parole_fornitore if p in desc_upper)
    
    # Match se almeno il 50% delle parole o almeno 1 parola significativa
    if matches_esatti >= max(1, len(parole_fornitore) // 2):
        return 2  # Match esatto
    
    # === 2. Fuzzy matching (se disponibile) ===
    if FUZZY_AVAILABLE:
        # Estrai possibili nomi dalla descrizione (sequenze di parole maiuscole)
        possibili_nomi = re.findall(r'[A-Z][A-Z\s\.\']{3,}(?:S\.?R\.?L\.?|S\.?P\.?A\.?)?', desc_upper)
        
        for possibile_nome in possibili_nomi:
            # Calcola similarità tra il fornitore e ogni possibile nome estratto
            score = fuzz.ratio(fornitore_clean.strip(), possibile_nome.strip())
            if score >= fuzzy_threshold:
                return 1  # Match fuzzy
            
            # Prova anche partial_ratio per match parziali (es. "CERALDI" in "CERALDI GROUP")
            partial_score = fuzz.partial_ratio(fornitore_clean.strip(), possibile_nome.strip())
            if partial_score >= 90:  # Soglia alta per partial
                return 1
            
            # Token set ratio: gestisce parole in ordine diverso
            token_score = fuzz.token_set_ratio(fornitore_clean.strip(), possibile_nome.strip())
            if token_score >= fuzzy_threshold:
                return 1
    
    return 0


def match_numero_fattura_descrizione(numero_fattura: str, descrizione: str) -> bool:
    """
    Verifica se il numero fattura è presente nella descrizione dell'estratto conto.
    """
    if not numero_fattura or not descrizione:
        return False
    
    desc_upper = descrizione.upper()
    num_clean = numero_fattura.strip().upper()
    
    # Rimuovi prefissi comuni (FT, FAT, etc.) e separatori
    num_clean = re.sub(r'^(FT|FAT|FATT|INV|N\.?|NR\.?)[\s\-/]*', '', num_clean)
    # Rimuovi anno e separatori (es. 2024/001234 -> 001234)
    num_clean = re.sub(r'^\d{4}[\s\-/]+', '', num_clean)
    
    # Cerca il numero nella descrizione
    if num_clean and num_clean in desc_upper:
        return True
    
    # Cerca anche senza zeri iniziali
    num_no_zeros = num_clean.lstrip('0')
    if num_no_zeros and len(num_no_zeros) >= 3 and num_no_zeros in desc_upper:
        return True
    
    # Estrai solo numeri dal numero fattura originale
    solo_numeri = re.sub(r'[^\d]', '', numero_fattura)
    if solo_numeri and len(solo_numeri) >= 4 and solo_numeri in desc_upper:
        return True
    
    return False


def extract_invoice_number(descrizione: str) -> Optional[str]:
    """Estrae numero fattura dalla descrizione estratto conto."""
    if not descrizione:
        return None
    
    desc_upper = descrizione.upper()
    
    patterns = [
        r'(?:FAT(?:TURA)?|FT|FATT)[\s\.\-:]*N?[\s\.\-:]*(\d+[\/-]?\d*)',
        r'(?:SALDO|PAG(?:AMENTO)?)\s+(?:FAT(?:TURA)?|FT)\s*N?[\s\.\-:]*(\d+[\/-]?\d*)',
        r'RIF\.?\s*[:\s]*(\d{3,}[\/-]?\d*)',
        r'(?:N|NR|NUM)\.?\s*(\d{3,}[\/-]?\d*)',
        r'[\s\-](\d{4,})(?:\s|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, desc_upper)
        if match:
            num = match.group(1).strip()
            if len(num) <= 8 and not (len(num) == 8 and num.startswith('20')):
                return num
    
    return None


def extract_assegno_number(descrizione: str) -> Optional[str]:
    """Estrae numero assegno dalla descrizione."""
    if not descrizione:
        return None
    
    patterns = [
        r'(?:VOSTRO\s+)?ASSEGNO\s+N\.?\s*(\d+)',
        r'ASS\.?\s+N\.?\s*(\d+)',
        r'CHQ\.?\s*(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, descrizione.upper())
        if match:
            return match.group(1).strip()
    
    return None


def extract_supplier_name(descrizione: str) -> Optional[str]:
    """Estrae nome fornitore dalla descrizione."""
    if not descrizione:
        return None
    
    desc_upper = descrizione.upper()
    
    patterns = [
        r'(?:BENEF(?:ICIARIO)?|A FAVORE DI|VERSO|PER|FAVORE)[\s:]+([A-Z][A-Z\s\.\']+(?:S\.?R\.?L\.?|S\.?P\.?A\.?|S\.?A\.?S\.?|S\.?N\.?C\.?)?)',
        r'([A-Z][A-Z\s\']+(?:S\.?R\.?L\.?|S\.?P\.?A\.?))',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, desc_upper)
        if match:
            name = match.group(1).strip()
            if len(name) > 3:
                return name
    
    return None


@router.post("/riconcilia-estratto-conto")
async def riconcilia_estratto_conto() -> Dict[str, Any]:
    """
    Riconciliazione automatica con logica corretta:
    
    REGOLE:
    1. Cerca match ESATTO per importo (±0.05€)
    2. Se trova in EC → metodo = Bonifico o Assegno
    3. Se NON trova in EC → NON può mettere Bonifico
    4. Rispetta metodo fornitore se definito
    """
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    results = {
        "movimenti_analizzati": 0,
        "riconciliati_fatture": 0,
        "riconciliati_assegni": 0,
        "riconciliati_f24": 0,
        "riconciliati_pos": 0,
        "riconciliati_versamenti": 0,
        "commissioni_ignorate": 0,
        "dubbi": 0,
        "non_trovati": 0,
        "errors": []
    }
    
    # Carica movimenti EC non riconciliati
    movimenti_ec = await db[COLLECTION_ESTRATTO_CONTO].find({
        "riconciliato": {"$ne": True}
    }, {"_id": 0}).to_list(5000)
    
    results["movimenti_analizzati"] = len(movimenti_ec)
    
    for mov in movimenti_ec:
        try:
            mov_id = mov.get("id")
            importo = abs(float(mov.get("importo", 0)))
            data_ec = mov.get("data", "")
            descrizione = mov.get("descrizione_originale", "") or mov.get("descrizione", "")
            tipo = mov.get("tipo", "")  # "entrata" o "uscita"
            
            if importo == 0:
                continue
            
            # === IGNORA COMMISSIONI ===
            if is_commissione(descrizione, importo):
                await db[COLLECTION_ESTRATTO_CONTO].update_one(
                    {"id": mov_id},
                    {"$set": {
                        "riconciliato": True,
                        "tipo_riconciliazione": "commissione_ignorata",
                        "updated_at": now
                    }}
                )
                results["commissioni_ignorate"] += 1
                continue
            
            match_found = False
            match_type = None
            match_details = {}
            
            # === 1. CERCA FATTURE (per USCITE) ===
            if tipo == "uscita" and not match_found:
                num_fattura_ec = extract_invoice_number(descrizione)
                num_assegno = extract_assegno_number(descrizione)
                supplier_name_ec = extract_supplier_name(descrizione)
                
                # RICERCA MIGLIORATA: 
                # 1. Match esatto importo (±0.05€)
                # 2. Match parziale importo (pagamento rate - 10% tolleranza)
                
                # Query per fatture candidate (importo esatto O importo parziale)
                fatture_candidate = await db[Collections.INVOICES].find({
                    "$and": [
                        {"pagato": {"$ne": True}},
                        {"$or": [
                            # Match esatto
                            {"importo_totale": {"$gte": importo - 0.05, "$lte": importo + 0.05}},
                            {"total_amount": {"$gte": importo - 0.05, "$lte": importo + 0.05}},
                            # Match parziale (il pagamento è circa 50-200% della fattura)
                            {"importo_totale": {"$gte": importo * 0.5, "$lte": importo * 2}},
                            {"total_amount": {"$gte": importo * 0.5, "$lte": importo * 2}}
                        ]}
                    ]
                }, {"_id": 0}).to_list(50)
                
                # Calcola score per ogni fattura
                fatture_scored = []
                for f in fatture_candidate:
                    score = 0
                    fornitore_fatt = f.get("cedente_denominazione") or f.get("supplier_name") or ""
                    numero_fatt = f.get("numero_fattura") or f.get("invoice_number") or ""
                    data_fatt = f.get("data") or f.get("invoice_date") or ""
                    data_scadenza = f.get("data_scadenza") or ""
                    
                    # Score 1: Importo esatto (+10) vs importo parziale (+3)
                    imp_fatt = f.get("importo_totale") or f.get("total_amount") or 0
                    if abs(imp_fatt - importo) <= 0.05:
                        score += 10  # Match esatto
                    elif abs(imp_fatt - importo) <= imp_fatt * 0.1:  # ±10%
                        score += 5  # Match quasi esatto
                    else:
                        score += 2  # Match parziale (possibile rata)
                    
                    # Score 2: Match fornitore nella descrizione EC (con fuzzy)
                    fornitore_match = match_fornitore_descrizione(fornitore_fatt, descrizione)
                    if fornitore_match == 2:
                        score += 5  # Match esatto
                    elif fornitore_match == 1:
                        score += 3  # Match fuzzy
                    
                    # Score 3: Match numero fattura nella descrizione EC
                    if match_numero_fattura_descrizione(numero_fatt, descrizione):
                        score += 5
                    
                    # Score 4: Numero fattura estratto da EC corrisponde
                    if num_fattura_ec and numero_fatt:
                        num_fatt_clean = re.sub(r'^(FT|FAT|FATT|INV|N\.?|NR\.?)\s*', '', numero_fatt.upper())
                        if num_fattura_ec in num_fatt_clean or num_fatt_clean in num_fattura_ec:
                            score += 5
                    
                    # Score 5: Data movimento vicina a data scadenza (+2)
                    if data_ec and data_scadenza:
                        try:
                            dt_ec = datetime.fromisoformat(data_ec.replace('Z', '+00:00')) if isinstance(data_ec, str) else data_ec
                            dt_scad = datetime.fromisoformat(data_scadenza.replace('Z', '+00:00')) if isinstance(data_scadenza, str) else data_scadenza
                            diff_days = abs((dt_ec - dt_scad).days)
                            if diff_days <= 7:
                                score += 2
                        except Exception:
                            pass
                    
                    fatture_scored.append((f, score))
                
                # Ordina per score decrescente
                fatture_scored.sort(key=lambda x: x[1], reverse=True)
                
                # Se c'è una fattura con score >= 15 (importo + fornitore + numero) → match sicuro
                if fatture_scored and fatture_scored[0][1] >= 15:
                    fattura = fatture_scored[0][0]
                    match_found = True
                    match_type = "fattura_match_completo"
                    
                    metodo_pagamento = "Bonifico"
                    if num_assegno:
                        metodo_pagamento = f"Assegno N.{num_assegno}"
                        await db[COLLECTION_ASSEGNI].update_one(
                            {"numero": num_assegno},
                            {"$set": {
                                "numero": num_assegno,
                                "importo": importo,
                                "data_emissione": data_ec,
                                "fattura_id": str(fattura.get("_id", fattura.get("id"))),
                                "fornitore": fattura.get("cedente_denominazione") or fattura.get("supplier_name"),
                                "stato": "incassato",
                                "updated_at": now
                            }},
                            upsert=True
                        )
                        results["riconciliati_assegni"] += 1
                    
                    await db[Collections.INVOICES].update_one(
                        {"_id": fattura["_id"]},
                        {"$set": {
                            "pagato": True,
                            "paid": True,
                            "metodo_pagamento": metodo_pagamento,
                            "in_banca": True,
                            "data_pagamento": data_ec,
                            "riconciliato_con_ec": mov_id,
                            "riconciliato_automaticamente": True,
                            "match_score": fatture_scored[0][1],
                            "updated_at": now
                        }}
                    )
                    
                    match_details = {
                        "fattura_id": str(fattura.get("_id")),
                        "numero_fattura": fattura.get("numero_fattura") or fattura.get("invoice_number"),
                        "fornitore": fattura.get("cedente_denominazione") or fattura.get("supplier_name"),
                        "metodo_pagamento": metodo_pagamento,
                        "match_score": fatture_scored[0][1],
                        "match_type": "importo+fornitore+numero"
                    }
                    results["riconciliati_fatture"] += 1
                
                # Se score >= 10 ma < 15 (solo importo + un altro criterio) → match con confidenza media
                elif fatture_scored and fatture_scored[0][1] >= 10 and fatture_scored[0][1] < 15:
                    # Se c'è una sola fattura con questo score → riconcilia
                    fatture_buone = [f for f, s in fatture_scored if s >= 10]
                    
                    if len(fatture_buone) == 1:
                        fattura = fatture_buone[0]
                        match_found = True
                        match_type = "fattura_match_parziale"
                        
                        metodo_pagamento = "Bonifico"
                        if num_assegno:
                            metodo_pagamento = f"Assegno N.{num_assegno}"
                        
                        await db[Collections.INVOICES].update_one(
                            {"_id": fattura["_id"]},
                            {"$set": {
                                "pagato": True,
                                "paid": True,
                                "metodo_pagamento": metodo_pagamento,
                                "in_banca": True,
                                "data_pagamento": data_ec,
                                "riconciliato_con_ec": mov_id,
                                "riconciliato_automaticamente": True,
                                "match_score": fatture_scored[0][1],
                                "updated_at": now
                            }}
                        )
                        
                        match_details = {
                            "fattura_id": str(fattura.get("_id")),
                            "numero_fattura": fattura.get("numero_fattura") or fattura.get("invoice_number"),
                            "fornitore": fattura.get("cedente_denominazione") or fattura.get("supplier_name"),
                            "metodo_pagamento": metodo_pagamento,
                            "match_score": fatture_scored[0][1]
                        }
                        results["riconciliati_fatture"] += 1
                    else:
                        # Più fatture con score simile → operazione da confermare
                        fatture_ordinate = sorted(
                            [f for f, s in fatture_scored if s >= 10],
                            key=lambda f: f.get("data", f.get("invoice_date", "1900-01-01")),
                            reverse=True
                        )
                        
                        operazione = {
                            "id": str(uuid.uuid4()),
                            "tipo": "riconciliazione_dubbio",
                            "movimento_ec_id": mov_id,
                            "data": data_ec,
                            "importo": importo,
                            "descrizione": descrizione,
                            "tipo_movimento": tipo,
                            "match_type": "fatture_multiple",
                            "confidence": "medio",
                            "dettagli": {
                                "fatture_candidate": [
                                    {
                                        "id": str(f.get("_id", f.get("id"))),
                                        "numero": f.get("numero_fattura") or f.get("invoice_number"),
                                        "fornitore": f.get("cedente_denominazione") or f.get("supplier_name"),
                                        "importo": f.get("importo_totale") or f.get("total_amount"),
                                        "data": f.get("data") or f.get("invoice_date"),
                                        "score": next((s for ff, s in fatture_scored if ff == f), 0)
                                    }
                                    for f in fatture_ordinate[:10]
                                ],
                                "motivo_dubbio": f"Trovate {len(fatture_ordinate)} fatture con match parziale"
                            },
                            "stato": "da_confermare",
                            "created_at": now
                        }
                        
                        await db[COLLECTION_OPERAZIONI_DA_CONFERMARE].insert_one(operazione.copy())
                        results["dubbi"] += 1
                
                # Se solo importo esatto (score = 10) e UNA sola fattura → riconcilia
                elif fatture_scored and fatture_scored[0][1] == 10:
                    fatture_esatte = [f for f, s in fatture_scored if s == 10]
                    
                    if len(fatture_esatte) == 1:
                        fattura = fatture_esatte[0]
                        match_found = True
                        match_type = "fattura_solo_importo"
                        
                        metodo_pagamento = "Bonifico"
                        if num_assegno:
                            metodo_pagamento = f"Assegno N.{num_assegno}"
                        
                        await db[Collections.INVOICES].update_one(
                            {"_id": fattura["_id"]},
                            {"$set": {
                                "pagato": True,
                                "paid": True,
                                "metodo_pagamento": metodo_pagamento,
                                "in_banca": True,
                                "data_pagamento": data_ec,
                                "riconciliato_con_ec": mov_id,
                                "riconciliato_automaticamente": True,
                                "match_score": 10,
                                "updated_at": now
                            }}
                        )
                        
                        match_details = {
                            "fattura_id": str(fattura.get("_id")),
                            "numero_fattura": fattura.get("numero_fattura") or fattura.get("invoice_number"),
                            "fornitore": fattura.get("cedente_denominazione") or fattura.get("supplier_name"),
                            "metodo_pagamento": metodo_pagamento,
                            "match_score": 10,
                            "match_type": "solo_importo"
                        }
                        results["riconciliati_fatture"] += 1
                        
                    elif len(fatture_esatte) > 1:
                        # Più fatture solo con importo → operazione da confermare (bassa confidenza)
                        fatture_ordinate = sorted(
                            fatture_esatte,
                            key=lambda f: f.get("data", f.get("invoice_date", "1900-01-01")),
                            reverse=True
                        )
                        
                        operazione = {
                            "id": str(uuid.uuid4()),
                            "tipo": "riconciliazione_dubbio",
                            "movimento_ec_id": mov_id,
                            "data": data_ec,
                            "importo": importo,
                            "descrizione": descrizione,
                            "tipo_movimento": tipo,
                            "match_type": "fatture_multiple",
                            "confidence": "basso",
                            "dettagli": {
                                "fatture_candidate": [
                                    {
                                        "id": str(f.get("_id", f.get("id"))),
                                        "numero": f.get("numero_fattura") or f.get("invoice_number"),
                                        "fornitore": f.get("cedente_denominazione") or f.get("supplier_name"),
                                        "importo": f.get("importo_totale") or f.get("total_amount"),
                                        "data": f.get("data") or f.get("invoice_date")
                                    }
                                    for f in fatture_ordinate[:10]
                                ],
                                "motivo_dubbio": f"Trovate {len(fatture_esatte)} fatture con stesso importo (match solo importo)"
                            },
                            "stato": "da_confermare",
                            "created_at": now
                        }
                        
                        await db[COLLECTION_OPERAZIONI_DA_CONFERMARE].insert_one(operazione.copy())
                        results["dubbi"] += 1
            
            # === 2. CERCA F24 (per USCITE) ===
            if tipo == "uscita" and not match_found and "F24" in descrizione.upper():
                f24 = await db["f24_unificato"].find_one({
                    "totale": {"$gte": importo - 0.05, "$lte": importo + 0.05},
                    "riconciliato": {"$ne": True}
                })
                
                if f24:
                    match_found = True
                    match_type = "f24"
                    
                    await db["f24_unificato"].update_one(
                        {"_id": f24["_id"]},
                        {"$set": {
                            "riconciliato": True,
                            "pagato": True,
                            "in_banca": True,
                            "data_pagamento": data_ec,
                            "riconciliato_automaticamente": True,
                            "updated_at": now
                        }}
                    )
                    
                    match_details = {
                        "f24_id": str(f24.get("_id")),
                        "periodo": f24.get("periodo_riferimento"),
                        "importo_f24": f24.get("totale")
                    }
                    results["riconciliati_f24"] += 1
            
            # === 3. CERCA POS (per ENTRATE - accrediti) ===
            if tipo == "entrata" and not match_found:
                desc_upper = descrizione.upper()
                if any(kw in desc_upper for kw in ['POS', 'NEXI', 'SUMUP', 'CARTE', 'BANCOMAT']):
                    # Logica POS: Lun-Gio +1g, Ven-Dom → Lunedì
                    try:
                        dt_acc = datetime.strptime(data_ec, "%Y-%m-%d")
                        weekday = dt_acc.weekday()
                        
                        if weekday == 0:  # Lunedì → cerca Ven+Sab+Dom
                            date_weekend = [
                                (dt_acc - timedelta(days=3)).strftime("%Y-%m-%d"),
                                (dt_acc - timedelta(days=2)).strftime("%Y-%m-%d"),
                                (dt_acc - timedelta(days=1)).strftime("%Y-%m-%d"),
                            ]
                            
                            pos_weekend = await db[COLLECTION_PRIMA_NOTA_CASSA].find({
                                "data": {"$in": date_weekend},
                                "categoria": "POS",
                                "riconciliato": {"$ne": True}
                            }, {"_id": 0}).to_list(10)
                            
                            somma_pos = sum(p.get("importo", 0) for p in pos_weekend)
                            
                            if abs(somma_pos - importo) <= 1:
                                match_found = True
                                match_type = "pos_weekend"
                                
                                for p in pos_weekend:
                                    await db[COLLECTION_PRIMA_NOTA_CASSA].update_one(
                                        {"id": p["id"]},
                                        {"$set": {
                                            "riconciliato": True,
                                            "in_banca": True,
                                            "riconciliato_con_ec": mov_id,
                                            "updated_at": now
                                        }}
                                    )
                                
                                match_details = {"date_pos": date_weekend, "importo_totale": somma_pos}
                                results["riconciliati_pos"] += 1
                        else:
                            # Lun-Gio → cerca giorno precedente
                            data_pos = (dt_acc - timedelta(days=1)).strftime("%Y-%m-%d")
                            
                            pos = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({
                                "data": data_pos,
                                "categoria": "POS",
                                "importo": {"$gte": importo - 1, "$lte": importo + 1},
                                "riconciliato": {"$ne": True}
                            })
                            
                            if pos:
                                match_found = True
                                match_type = "pos_giornaliero"
                                
                                await db[COLLECTION_PRIMA_NOTA_CASSA].update_one(
                                    {"id": pos["id"]},
                                    {"$set": {
                                        "riconciliato": True,
                                        "in_banca": True,
                                        "riconciliato_con_ec": mov_id,
                                        "updated_at": now
                                    }}
                                )
                                
                                match_details = {"data_pos": data_pos, "importo_pos": pos.get("importo")}
                                results["riconciliati_pos"] += 1
                    except Exception:
                        pass
            
            # === 4. CERCA VERSAMENTI (per ENTRATE) ===
            if tipo == "entrata" and not match_found:
                if any(kw in descrizione.upper() for kw in ['VERS', 'VERSAMENTO', 'CONTANTI']):
                    versamento = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({
                        "data": data_ec,
                        "categoria": "Versamento",
                        "importo": {"$gte": importo - 0.05, "$lte": importo + 0.05},
                        "riconciliato": {"$ne": True}
                    })
                    
                    if versamento:
                        match_found = True
                        match_type = "versamento"
                        
                        await db[COLLECTION_PRIMA_NOTA_CASSA].update_one(
                            {"id": versamento["id"]},
                            {"$set": {
                                "riconciliato": True,
                                "in_banca": True,
                                "riconciliato_con_ec": mov_id,
                                "updated_at": now
                            }}
                        )
                        
                        match_details = {"versamento_id": versamento.get("id"), "importo": versamento.get("importo")}
                        results["riconciliati_versamenti"] += 1
            
            # === AGGIORNA EC ===
            if match_found:
                await db[COLLECTION_ESTRATTO_CONTO].update_one(
                    {"id": mov_id},
                    {"$set": {
                        "riconciliato": True,
                        "riconciliato_automaticamente": True,
                        "tipo_riconciliazione": match_type,
                        "dettagli_riconciliazione": match_details,
                        "updated_at": now
                    }}
                )
            else:
                results["non_trovati"] += 1
                
        except Exception as e:
            results["errors"].append({"id": mov.get("id"), "error": str(e)})
    
    totale_riconciliati = (
        results["riconciliati_fatture"] +
        results["riconciliati_assegni"] +
        results["riconciliati_f24"] +
        results["riconciliati_pos"] +
        results["riconciliati_versamenti"]
    )
    
    return {
        "success": True,
        "message": f"Riconciliati {totale_riconciliati} movimenti, {results['dubbi']} da confermare",
        "totale_riconciliati": totale_riconciliati,
        **results
    }


@router.get("/stats-riconciliazione")
async def get_stats_riconciliazione() -> Dict[str, Any]:
    """Statistiche riconciliazione."""
    db = Database.get_db()
    
    ec_totali = await db[COLLECTION_ESTRATTO_CONTO].count_documents({})
    ec_riconciliati = await db[COLLECTION_ESTRATTO_CONTO].count_documents({"riconciliato": True})
    ec_auto = await db[COLLECTION_ESTRATTO_CONTO].count_documents({"riconciliato_automaticamente": True})
    
    odc_totali = await db[COLLECTION_OPERAZIONI_DA_CONFERMARE].count_documents({"stato": "da_confermare"})
    fatture_auto = await db[Collections.INVOICES].count_documents({"riconciliato_automaticamente": True})
    fatture_in_banca = await db[Collections.INVOICES].count_documents({"in_banca": True})
    
    return {
        "estratto_conto": {
            "totali": ec_totali,
            "riconciliati": ec_riconciliati,
            "automatici": ec_auto,
            "percentuale": round(ec_riconciliati / ec_totali * 100, 1) if ec_totali > 0 else 0
        },
        "operazioni_da_confermare": odc_totali,
        "fatture_riconciliate_auto": fatture_auto,
        "fatture_in_banca": fatture_in_banca
    }


@router.delete("/reset-riconciliazione")
async def reset_riconciliazione() -> Dict[str, Any]:
    """Reset completo riconciliazione."""
    db = Database.get_db()
    
    r1 = await db[COLLECTION_OPERAZIONI_DA_CONFERMARE].delete_many({})
    
    r2 = await db[COLLECTION_ESTRATTO_CONTO].update_many(
        {},
        {"$unset": {
            "riconciliato": "",
            "riconciliato_automaticamente": "",
            "tipo_riconciliazione": "",
            "dettagli_riconciliazione": ""
        }}
    )
    
    # Reset anche flag sulle fatture
    r3 = await db[Collections.INVOICES].update_many(
        {"riconciliato_automaticamente": True},
        {"$unset": {
            "riconciliato_con_ec": "",
            "riconciliato_automaticamente": ""
        }}
    )
    
    return {
        "success": True,
        "operazioni_eliminate": r1.deleted_count,
        "movimenti_resettati": r2.modified_count,
        "fatture_resettate": r3.modified_count
    }


@router.post("/conferma-operazione/{operazione_id}")
async def conferma_operazione(
    operazione_id: str,
    fattura_id: Optional[str] = None,
    azione: str = "conferma"
) -> Dict[str, Any]:
    """Conferma/rifiuta operazione dubbia."""
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    operazione = await db[COLLECTION_OPERAZIONI_DA_CONFERMARE].find_one({"id": operazione_id})
    if not operazione:
        raise HTTPException(status_code=404, detail="Operazione non trovata")
    
    if azione == "conferma" and fattura_id:
        # Aggiorna fattura come pagata - TROVATA IN BANCA
        await db[Collections.INVOICES].update_one(
            {"$or": [{"id": fattura_id}, {"_id": fattura_id}]},
            {"$set": {
                "pagato": True,
                "paid": True,
                "metodo_pagamento": "Bonifico",
                "in_banca": True,
                "data_pagamento": operazione["data"],
                "riconciliato_con_ec": operazione["movimento_ec_id"],
                "updated_at": now
            }}
        )
        
        # Aggiorna EC
        await db[COLLECTION_ESTRATTO_CONTO].update_one(
            {"id": operazione["movimento_ec_id"]},
            {"$set": {
                "riconciliato": True,
                "riconciliato_manualmente": True,
                "updated_at": now
            }}
        )
        
        await db[COLLECTION_OPERAZIONI_DA_CONFERMARE].update_one(
            {"id": operazione_id},
            {"$set": {"stato": "confermato", "fattura_confermata": fattura_id, "updated_at": now}}
        )
        
        return {"success": True, "message": "Confermato - Fattura pagata via Banca"}
    
    elif azione in ["rifiuta", "ignora"]:
        await db[COLLECTION_OPERAZIONI_DA_CONFERMARE].update_one(
            {"id": operazione_id},
            {"$set": {"stato": azione, "updated_at": now}}
        )
        return {"success": True, "message": f"Operazione {azione}ta"}
    
    raise HTTPException(status_code=400, detail="Azione non valida")


@router.get("/operazioni-dubbi")
async def get_operazioni_dubbi(limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    """Lista operazioni dubbie."""
    db = Database.get_db()
    
    operazioni = await db[COLLECTION_OPERAZIONI_DA_CONFERMARE].find(
        {"stato": "da_confermare"},
        {"_id": 0}
    ).sort("created_at", -1).skip(offset).limit(limit).to_list(limit)
    
    totale = await db[COLLECTION_OPERAZIONI_DA_CONFERMARE].count_documents({"stato": "da_confermare"})
    
    return {"operazioni": operazioni, "totale": totale}


@router.post("/correggi-metodi-pagamento")
async def correggi_metodi_pagamento() -> Dict[str, Any]:
    """
    BONIFICA COMPLETA: Corregge i metodi di pagamento errati.
    
    REGOLE APPLICATE:
    1. Se metodo="Bonifico" o "Assegno" ma in_banca=false → ERRORE
       - Resetta pagato=false, status="imported"
       - Applica metodo fornitore se definito, altrimenti rimuovi metodo
    
    2. Se pagato=true ma in_banca=false E metodo="Bonifico/Assegno" → ERRORE
       - Stesso trattamento sopra
    
    3. Se fornitore ha metodo definito (es. "Cassa") → rispettalo
    """
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    results = {
        "bancario_errati": 0,
        "assegno_errati": 0,
        "metodo_fornitore_applicato": 0,
        "metodo_rimosso": 0,
        "totale_corrette": 0
    }
    
    # CASO 1: Fatture con metodo bancario (bonifico, banca, sepa) ma senza in_banca=true
    # Case-insensitive per catturare tutte le varianti
    fatture_bancarie = await db[Collections.INVOICES].find({
        "metodo_pagamento": {"$regex": "^(bonifico|banca|sepa)$", "$options": "i"},
        "in_banca": {"$ne": True}
    }, {"_id": 0}).to_list(5000)
    
    # CASO 2: Fatture con "Assegno" (qualsiasi variante) ma senza in_banca=true
    fatture_assegno = await db[Collections.INVOICES].find({
        "metodo_pagamento": {"$regex": "^assegno", "$options": "i"},
        "in_banca": {"$ne": True}
    }, {"_id": 0}).to_list(5000)
    
    fatture_errate = fatture_bancarie + fatture_assegno
    
    for fattura in fatture_errate:
        piva = fattura.get("cedente_partita_iva") or fattura.get("supplier_vat")
        metodo_attuale = fattura.get("metodo_pagamento", "")
        
        # Cerca metodo default del fornitore
        supplier = None
        metodo_fornitore = None
        if piva:
            supplier = await db[COLLECTION_SUPPLIERS].find_one({"vat_number": piva})
            if supplier:
                metodo_fornitore = supplier.get("metodo_pagamento")
        
        # Prepara update
        update_set = {
            "updated_at": now,
            "pagato": False,
            "paid": False,
            "status": "imported",
            "bonifica_applicata": now,
            "bonifica_motivo": f"metodo '{metodo_attuale}' non valido senza corrispondenza in estratto conto"
        }
        
        update_unset = {
            "riconciliato_con_ec": "",
            "riconciliato_automaticamente": ""
        }
        
        if metodo_fornitore and metodo_fornitore.lower() not in ["bonifico", "assegno"]:
            # Fornitore ha metodo diverso (es. Cassa) → usa quello
            update_set["metodo_pagamento"] = metodo_fornitore
            results["metodo_fornitore_applicato"] += 1
        else:
            # Rimuovi metodo pagamento
            update_unset["metodo_pagamento"] = ""
            results["metodo_rimosso"] += 1
        
        await db[Collections.INVOICES].update_one(
            {"_id": fattura["_id"]},
            {"$set": update_set, "$unset": update_unset}
        )
        
        if metodo_attuale.lower() in ["bonifico", "banca", "sepa"]:
            results["bancario_errati"] += 1
        elif "assegno" in metodo_attuale.lower():
            results["assegno_errati"] += 1
        
        results["totale_corrette"] += 1
    
    return {
        "success": True,
        "message": f"Bonifica completata: {results['totale_corrette']} fatture corrette",
        **results,
        "dettaglio": {
            "regola": "Se metodo=Bonifico/Assegno ma in_banca=false → errore logico → reset a stato iniziale",
            "azione": "pagato=false, status=imported, metodo=fornitore_default o rimosso"
        }
    }


@router.post("/assegna-metodi-aruba")
async def assegna_metodi_aruba_auto() -> Dict[str, Any]:
    """
    Assegna automaticamente i metodi di pagamento alle fatture Aruba
    confrontandole con l'estratto conto.
    
    LOGICA:
    1. Se la fattura è NELL'estratto conto → assegna "bonifico" o "assegno" (in base a descrizione)
    2. Se la fattura NON è nell'estratto E l'estratto è recente (< 7 giorni dalla fattura) → assegna "cassa"
    3. Se l'estratto è vecchio rispetto alla fattura → lascia "sospesa" (da ricontrollare al prossimo upload)
    
    Rispetta sempre il metodo pagamento del fornitore se configurato.
    """
    db = Database.get_db()
    now = datetime.now(timezone.utc)
    
    results = {
        "fatture_analizzate": 0,
        "assegnate_bonifico": 0,
        "assegnate_assegno": 0,
        "assegnate_cassa": 0,
        "lasciate_sospese": 0,
        "gia_pagate": 0,
        "metodo_fornitore_applicato": 0,
        "errori": []
    }
    
    # 1. Trova l'ultimo estratto conto caricato
    ultimo_ec = await db[COLLECTION_ESTRATTO_CONTO].find_one(
        {},
        sort=[("data", -1)],
        projection={"data": 1}
    )
    
    data_ultimo_ec = None
    if ultimo_ec:
        try:
            data_ultimo_ec = datetime.strptime(ultimo_ec["data"][:10], "%Y-%m-%d")
        except Exception:
            pass
    
    # 2. Carica tutti i movimenti estratto conto per match veloce
    movimenti_ec = await db[COLLECTION_ESTRATTO_CONTO].find(
        {},
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "descrizione": 1, "numero_assegno": 1}
    ).to_list(10000)
    
    # 3. Carica dizionario fornitori per metodi pagamento
    fornitori_dict = {}
    fornitori_cursor = await db[COLLECTION_SUPPLIERS].find(
        {},
        {"_id": 0, "partita_iva": 1, "vat_number": 1, "metodo_pagamento": 1}
    ).to_list(10000)
    for f in fornitori_cursor:
        piva = f.get("partita_iva") or f.get("vat_number")
        if piva:
            fornitori_dict[piva] = f.get("metodo_pagamento", "")
    
    # 4. Carica fatture non pagate
    fatture = await db[Collections.INVOICES].find({
        "$or": [
            {"pagato": {"$ne": True}},
            {"stato_pagamento": {"$nin": STATI_PAGATI}},
            {"status": {"$nin": STATI_PAGATI}}
        ]
    }).to_list(5000)
    
    results["fatture_analizzate"] = len(fatture)
    
    for fattura in fatture:
        try:
            fattura_id = fattura.get("id") or str(fattura.get("_id"))
            importo_fattura = abs(float(fattura.get("total_amount", 0) or fattura.get("importo_totale", 0) or 0))
            data_fattura_str = fattura.get("invoice_date") or fattura.get("data_fattura", "")
            fornitore = fattura.get("supplier_name") or fattura.get("cedente_denominazione", "")
            fornitore_piva = fattura.get("supplier_vat") or fattura.get("cedente_piva", "")
            numero_fattura = fattura.get("invoice_number") or fattura.get("numero_fattura", "")
            
            if not importo_fattura or importo_fattura <= 0:
                continue
            
            # Metodo fornitore (fonte di verità)
            metodo_fornitore = fornitori_dict.get(fornitore_piva, "").lower()
            
            # Se il fornitore ha metodo configurato come cassa/contanti, usa quello
            if metodo_fornitore in ["contanti", "cassa", "cash", "contante"]:
                await db[Collections.INVOICES].update_one(
                    {"_id": fattura["_id"]},
                    {"$set": {
                        "metodo_pagamento": "cassa",
                        "assegnazione_auto": True,
                        "assegnazione_motivo": "metodo_fornitore",
                        "updated_at": now.isoformat()
                    }}
                )
                results["metodo_fornitore_applicato"] += 1
                results["assegnate_cassa"] += 1
                continue
            
            # Cerca match nell'estratto conto
            match_trovato = None
            tipo_match = None
            
            for mov in movimenti_ec:
                importo_mov = abs(float(mov.get("importo", 0)))
                desc_mov = mov.get("descrizione", "").upper()
                
                # Match per importo (±0.05€)
                if abs(importo_mov - importo_fattura) <= 0.05:
                    # Verifica anche match fornitore o numero fattura
                    match_fornitore = match_fornitore_descrizione(fornitore, desc_mov)
                    match_numero = match_numero_fattura_descrizione(numero_fattura, desc_mov)
                    
                    if match_fornitore > 0 or match_numero:
                        match_trovato = mov
                        # Verifica se è un assegno
                        num_assegno = mov.get("numero_assegno") or extract_assegno_number(desc_mov)
                        if num_assegno or "ASSEGNO" in desc_mov:
                            tipo_match = "assegno"
                        else:
                            tipo_match = "bonifico"
                        break
            
            if match_trovato:
                # Trovato nell'estratto conto → assegna bonifico o assegno
                metodo_assegnato = tipo_match
                await db[Collections.INVOICES].update_one(
                    {"_id": fattura["_id"]},
                    {"$set": {
                        "metodo_pagamento": metodo_assegnato,
                        "riconciliato_con_ec": match_trovato.get("id"),
                        "assegnazione_auto": True,
                        "assegnazione_motivo": f"trovato_ec_{tipo_match}",
                        "updated_at": now.isoformat()
                    }}
                )
                if tipo_match == "assegno":
                    results["assegnate_assegno"] += 1
                else:
                    results["assegnate_bonifico"] += 1
            else:
                # NON trovato nell'estratto conto
                # Verifica quanto è vecchio l'estratto rispetto alla fattura
                try:
                    data_fattura = datetime.strptime(data_fattura_str[:10], "%Y-%m-%d")
                except Exception:
                    data_fattura = now
                
                if data_ultimo_ec:
                    giorni_differenza = (data_fattura - data_ultimo_ec).days
                    
                    if giorni_differenza <= 7:
                        # Estratto recente, fattura non trovata → probabilmente cassa
                        await db[Collections.INVOICES].update_one(
                            {"_id": fattura["_id"]},
                            {"$set": {
                                "metodo_pagamento": "cassa",
                                "assegnazione_auto": True,
                                "assegnazione_motivo": "non_in_ec_recente",
                                "updated_at": now.isoformat()
                            }}
                        )
                        results["assegnate_cassa"] += 1
                    else:
                        # Estratto vecchio → lascia sospesa
                        await db[Collections.INVOICES].update_one(
                            {"_id": fattura["_id"]},
                            {"$set": {
                                "stato_riconciliazione": "sospesa",
                                "assegnazione_motivo": "ec_troppo_vecchio",
                                "updated_at": now.isoformat()
                            }}
                        )
                        results["lasciate_sospese"] += 1
                else:
                    # Nessun estratto conto caricato → sospendi
                    results["lasciate_sospese"] += 1
                    
        except Exception as e:
            results["errori"].append(f"Fattura {fattura_id}: {str(e)}")
    
    return {
        "success": True,
        "message": f"Assegnazione completata: {results['assegnate_bonifico'] + results['assegnate_assegno'] + results['assegnate_cassa']} metodi assegnati",
        "data_ultimo_estratto_conto": data_ultimo_ec.strftime("%Y-%m-%d") if data_ultimo_ec else None,
        **results
    }


@router.get("/stato-riconciliazione-aruba")
async def get_stato_riconciliazione_aruba() -> Dict[str, Any]:
    """
    Restituisce lo stato attuale della riconciliazione per le fatture Aruba.
    Include statistiche e data ultimo estratto conto.
    """
    db = Database.get_db()
    
    # Data ultimo estratto conto
    ultimo_ec = await db[COLLECTION_ESTRATTO_CONTO].find_one(
        {},
        sort=[("data", -1)],
        projection={"data": 1, "created_at": 1}
    )
    
    # Statistiche fatture
    stats = {
        "totale_da_confermare": 0,
        "bonifico": 0,
        "assegno": 0,
        "cassa": 0,
        "sospese": 0,
        "pagate": 0
    }
    
    pipeline = [
        {
            "$group": {
                "_id": {
                    "metodo": "$metodo_pagamento",
                    "pagato": "$pagato",
                    "sospesa": "$stato_riconciliazione"
                },
                "count": {"$sum": 1},
                "totale": {"$sum": {"$toDouble": {"$ifNull": ["$total_amount", 0]}}}
            }
        }
    ]
    
    agg_results = await db[Collections.INVOICES].aggregate(pipeline).to_list(100)
    
    for agg in agg_results:
        metodo = (agg["_id"].get("metodo") or "").lower()
        pagato = agg["_id"].get("pagato")
        sospesa = agg["_id"].get("sospesa")
        count = agg["count"]
        
        if pagato:
            stats["pagate"] += count
        elif sospesa == "sospesa":
            stats["sospese"] += count
        elif metodo in ["bonifico", "banca", "sepa"]:
            stats["bonifico"] += count
        elif "assegno" in metodo:
            stats["assegno"] += count
        elif metodo in ["cassa", "contanti", "cash"]:
            stats["cassa"] += count
        else:
            stats["totale_da_confermare"] += count
    
    return {
        "ultimo_estratto_conto": {
            "data": ultimo_ec.get("data") if ultimo_ec else None,
            "caricato_il": ultimo_ec.get("created_at") if ultimo_ec else None
        },
        "statistiche": stats,
        "prossimo_refresh_consigliato": "Carica nuovo estratto conto per aggiornare le fatture sospese"
    }
