"""
Checks (Assegni) router - Gestione Assegni.
API per generazione, gestione e collegamento assegni.
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid
import logging

from app.database import Database
from app.models.stati import STATI_PAGATI

logger = logging.getLogger(__name__)
router = APIRouter()

# Collection name
COLLECTION_ASSEGNI = "assegni"

# Stati assegno
ASSEGNO_STATI = {
    "vuoto": {"label": "Vuoto", "color": "#9e9e9e"},
    "compilato": {"label": "Compilato", "color": "#2196f3"},
    "emesso": {"label": "Emesso", "color": "#ff9800"},
    "incassato": {"label": "Incassato", "color": "#4caf50"},
    "annullato": {"label": "Annullato", "color": "#f44336"},
    "scaduto": {"label": "Scaduto", "color": "#795548"}
}


@router.get("/stati")
async def get_assegno_stati() -> Dict[str, Any]:
    """Ritorna gli stati disponibili per gli assegni."""
    return ASSEGNO_STATI


@router.post("/genera")
async def genera_assegni(
    numero_primo: str = Body(..., description="Numero del primo assegno (es. 0208769182-11)"),
    quantita: int = Body(10, ge=1, le=100, description="Numero di assegni da generare")
) -> Dict[str, Any]:
    """
    Genera N assegni progressivi a partire dal numero fornito.
    
    Formato numero: PREFISSO-NUMERO (es. 0208769182-11)
    Genera: 0208769182-11, 0208769182-12, 0208769182-13, etc.
    """
    db = Database.get_db()
    
    # Parse del numero
    if "-" not in numero_primo:
        raise HTTPException(status_code=400, detail="Formato numero non valido. Usa formato: PREFISSO-NUMERO (es. 0208769182-11)")
    
    parts = numero_primo.rsplit("-", 1)
    prefix = parts[0]
    
    try:
        start_num = int(parts[1])
    except ValueError:
        raise HTTPException(status_code=400, detail="Il numero dopo il trattino deve essere numerico")
    
    # Verifica se alcuni numeri esistono già
    existing_numbers = []
    for i in range(quantita):
        num = f"{prefix}-{start_num + i}"
        existing = await db[COLLECTION_ASSEGNI].find_one({"numero": num})
        if existing:
            existing_numbers.append(num)
    
    if existing_numbers:
        raise HTTPException(
            status_code=400, 
            detail=f"I seguenti numeri esistono già: {', '.join(existing_numbers[:5])}{'...' if len(existing_numbers) > 5 else ''}"
        )
    
    # Genera assegni
    assegni_creati = []
    now = datetime.now(timezone.utc).isoformat()
    
    for i in range(quantita):
        numero = f"{prefix}-{start_num + i}"
        assegno = {
            "id": str(uuid.uuid4()),
            "numero": numero,
            "stato": "vuoto",
            "importo": None,
            "beneficiario": None,
            "causale": None,
            "data_emissione": None,
            "data_scadenza": None,
            "data_fattura": None,
            "numero_fattura": None,
            "fattura_collegata": None,
            "fatture_collegate": [],  # Lista di fatture (max 4)
            "fornitore_piva": None,
            "note": None,
            "created_at": now,
            "updated_at": now
        }
        await db[COLLECTION_ASSEGNI].insert_one(assegno.copy())
        assegni_creati.append(numero)
    
    return {
        "success": True,
        "message": f"Generati {quantita} assegni",
        "primo": assegni_creati[0],
        "ultimo": assegni_creati[-1],
        "numeri": assegni_creati
    }


@router.get("")
async def list_assegni(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    stato: Optional[str] = Query(None),
    fornitore_piva: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
) -> List[Dict[str, Any]]:
    """Lista assegni con filtri."""
    db = Database.get_db()
    
    # Escludi assegni eliminati (soft-delete)
    query = {"entity_status": {"$ne": "deleted"}}
    if stato:
        query["stato"] = stato
    if fornitore_piva:
        query["fornitore_piva"] = fornitore_piva
    if search:
        query["$or"] = [
            {"numero": {"$regex": search, "$options": "i"}},
            {"beneficiario": {"$regex": search, "$options": "i"}}
        ]
    
    assegni = await db[COLLECTION_ASSEGNI].find(query, {"_id": 0}).sort([
        ("stato", 1),
        ("numero", 1)
    ]).skip(skip).limit(limit).to_list(limit)
    
    return assegni


@router.get("/stats")
async def get_assegni_stats() -> Dict[str, Any]:
    """Statistiche assegni."""
    db = Database.get_db()
    
    # Escludi assegni eliminati (soft-delete)
    match_filter = {"entity_status": {"$ne": "deleted"}}
    
    pipeline = [
        {"$match": match_filter},
        {"$group": {
            "_id": "$stato",
            "count": {"$sum": 1},
            "totale": {"$sum": {"$ifNull": ["$importo", 0]}}
        }}
    ]
    
    by_stato = await db[COLLECTION_ASSEGNI].aggregate(pipeline).to_list(100)
    
    totale = await db[COLLECTION_ASSEGNI].count_documents(match_filter)
    
    return {
        "totale": totale,
        "per_stato": {item["_id"]: {"count": item["count"], "totale": item["totale"]} for item in by_stato}
    }


@router.get("/senza-associazione")
async def get_assegni_senza_associazione_v2() -> Dict[str, Any]:
    """
    Restituisce assegni che hanno importo ma nessun beneficiario/fattura associata.
    Utile per debug e verifica manuale.
    """
    db = Database.get_db()
    
    assegni = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": None},
            {"beneficiario": ""},
            {"beneficiario": "N/A"}
        ],
        "importo": {"$gt": 0}
    }, {"_id": 0}).to_list(500)
    
    # Raggruppa per importo
    from collections import defaultdict
    per_importo = defaultdict(list)
    for a in assegni:
        imp = round(a.get("importo", 0), 2)
        per_importo[imp].append(a.get("numero"))
    
    return {
        "totale": len(assegni),
        "per_importo": {f"€{k:.2f}": {"count": len(v), "numeri": v[:10]} for k, v in sorted(per_importo.items(), key=lambda x: -len(x[1]))}
    }


@router.get("/preview-combinazioni")
async def preview_combinazioni_assegni_v2(
    max_assegni: int = Query(4, ge=2, le=6)
) -> Dict[str, Any]:
    """
    🔎 PREVIEW: Mostra le possibili combinazioni di assegni che potrebbero matchare fatture.
    Non esegue modifiche, solo analisi.
    
    Utile per verificare prima di eseguire l'associazione.
    """
    from itertools import combinations
    db = Database.get_db()
    
    # Carica assegni senza beneficiario
    assegni_senza_ben = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": None},
            {"beneficiario": ""},
            {"beneficiario": "N/A"},
            {"beneficiario": "-"}
        ],
        "importo": {"$gt": 0}
    }, {"_id": 0, "numero": 1, "importo": 1}).to_list(100)
    
    # Filtra quelli non cancellati
    assegni_senza_ben = [a for a in assegni_senza_ben if a.get("entity_status") != "deleted"]
    
    if len(assegni_senza_ben) < 2:
        return {
            "assegni_senza_beneficiario": len(assegni_senza_ben),
            "combinazioni_possibili": [],
            "message": "Servono almeno 2 assegni per cercare combinazioni"
        }
    
    # Carica fatture non pagate
    fatture = await db.invoices.find({
        "$or": [
            {"status": {"$nin": STATI_PAGATI}},
            {"pagato": {"$ne": True}}
        ],
        "total_amount": {"$gt": 0}
    }, {"_id": 0, "invoice_number": 1, "supplier_name": 1, "total_amount": 1}).to_list(10000)
    
    importi_fatture = {round(float(f.get("total_amount", 0)), 2): f for f in fatture}
    
    # Cerca combinazioni
    possibili_match = []
    importi = [(a.get("numero"), round(float(a.get("importo", 0)), 2)) for a in assegni_senza_ben]
    
    for r in range(2, min(max_assegni + 1, len(importi) + 1)):
        for combo in combinations(importi, r):
            somma = round(sum(imp for _, imp in combo), 2)
            
            # Cerca fattura con questo importo (±1€)
            for delta in [0, -0.01, 0.01, -0.02, 0.02, -0.5, 0.5, -1, 1]:
                imp_cerca = round(somma + delta, 2)
                if imp_cerca in importi_fatture:
                    f = importi_fatture[imp_cerca]
                    possibili_match.append({
                        "assegni": [num for num, _ in combo],
                        "importi": [imp for _, imp in combo],
                        "somma": somma,
                        "fattura": f.get("invoice_number"),
                        "fornitore": f.get("supplier_name", "")[:40],
                        "importo_fattura": f.get("total_amount"),
                        "differenza": round(f.get("total_amount", 0) - somma, 2)
                    })
                    break
    
    return {
        "assegni_senza_beneficiario": len(assegni_senza_ben),
        "fatture_non_pagate": len(fatture),
        "combinazioni_con_match": len(possibili_match),
        "dettagli": possibili_match[:20]  # Primi 20 per non sovraccaricare
    }


@router.get("/verifica-associazioni")
async def verifica_associazioni_assegni() -> Dict[str, Any]:
    """
    Analizza tutte le associazioni assegno-fattura e identifica quelle problematiche.
    
    PROBLEMI IDENTIFICATI:
    1. Importo assegno diverso da importo fattura (oltre tolleranza ±5€)
    2. Beneficiario assegno diverso da fornitore fattura
    3. Fattura associata non esistente nel database
    4. Fattura associata già pagata
    5. Data assegno molto diversa da data fattura (>180 giorni)
    
    Returns:
        Lista di associazioni problematiche con suggerimenti di correzione
    """
    from thefuzz import fuzz
    
    db = Database.get_db()
    
    # Carica tutti gli assegni con fattura associata
    assegni = await db[COLLECTION_ASSEGNI].find(
        {"fattura_id": {"$exists": True, "$ne": None}},
        {"_id": 0}
    ).to_list(10000)
    
    # Carica tutte le fatture per lookup veloce
    fatture_cursor = await db["invoices"].find({}, {"_id": 0}).to_list(50000)
    fatture_by_id = {f.get("id"): f for f in fatture_cursor}
    
    problemi = []
    statistiche = {
        "totale_assegni_analizzati": len(assegni),
        "associazioni_corrette": 0,
        "problemi_importo": 0,
        "problemi_fornitore": 0,
        "problemi_fattura_mancante": 0,
        "problemi_fattura_pagata": 0,
        "problemi_data": 0
    }
    
    for assegno in assegni:
        assegno_id = assegno.get("id")
        fattura_id = assegno.get("fattura_id")
        numero_assegno = assegno.get("numero_assegno") or assegno.get("numero")
        importo_assegno = float(assegno.get("importo") or 0)
        beneficiario = assegno.get("beneficiario") or ""
        data_assegno = assegno.get("data_emissione") or assegno.get("data")
        
        # Cerca la fattura
        fattura = fatture_by_id.get(fattura_id)
        
        problema = {
            "assegno_id": assegno_id,
            "numero_assegno": numero_assegno,
            "importo_assegno": importo_assegno,
            "beneficiario": beneficiario,
            "data_assegno": data_assegno,
            "fattura_id": fattura_id,
            "problemi": [],
            "suggerimenti": []
        }
        
        # PROBLEMA 1: Fattura non trovata
        if not fattura:
            problema["problemi"].append("Fattura associata non trovata nel database")
            statistiche["problemi_fattura_mancante"] += 1
            
            # Suggerisci fatture con importo simile
            fatture_simili = [
                f for f in fatture_cursor 
                if abs(float(f.get("total_amount", 0) or 0) - importo_assegno) < 5
            ]
            if fatture_simili:
                problema["suggerimenti"] = [
                    {
                        "fattura_id": f.get("id"),
                        "numero": f.get("invoice_number"),
                        "fornitore": (f.get("supplier_name") or "")[:40],
                        "importo": f.get("total_amount"),
                        "match_type": "importo_simile"
                    }
                    for f in fatture_simili[:5]
                ]
            problemi.append(problema)
            continue
        
        # Dati fattura
        importo_fattura = float(fattura.get("total_amount") or fattura.get("importo_totale") or 0)
        fornitore = fattura.get("supplier_name") or fattura.get("fornitore_ragione_sociale") or ""
        data_fattura = fattura.get("invoice_date") or fattura.get("data_documento") or ""
        fattura_pagata = fattura.get("pagato") or fattura.get("status") == "paid"
        
        problema["fattura_numero"] = fattura.get("invoice_number") or fattura.get("numero_documento")
        problema["fattura_fornitore"] = fornitore
        problema["fattura_importo"] = importo_fattura
        problema["fattura_data"] = data_fattura
        problema["fattura_pagata"] = fattura_pagata
        
        ha_problemi = False
        
        # PROBLEMA 2: Importo diverso (tolleranza ±5€)
        differenza_importo = abs(importo_assegno - importo_fattura)
        if differenza_importo > 5:
            problema["problemi"].append(f"Importo differisce di €{differenza_importo:.2f}")
            problema["differenza_importo"] = differenza_importo
            statistiche["problemi_importo"] += 1
            ha_problemi = True
        
        # PROBLEMA 3: Fornitore diverso (fuzzy match < 60%)
        if beneficiario and fornitore:
            similarity = fuzz.token_set_ratio(beneficiario.upper(), fornitore.upper())
            if similarity < 60:
                problema["problemi"].append(f"Beneficiario diverso da fornitore (match: {similarity}%)")
                problema["similarity_score"] = similarity
                statistiche["problemi_fornitore"] += 1
                ha_problemi = True
        
        # PROBLEMA 4: Fattura già pagata
        if fattura_pagata:
            problema["problemi"].append("Fattura già marcata come pagata")
            statistiche["problemi_fattura_pagata"] += 1
            ha_problemi = True
        
        # PROBLEMA 5: Data molto diversa (>180 giorni)
        if data_assegno and data_fattura:
            try:
                if isinstance(data_assegno, str):
                    da = datetime.strptime(data_assegno[:10], "%Y-%m-%d")
                else:
                    da = data_assegno
                if isinstance(data_fattura, str):
                    df = datetime.strptime(data_fattura[:10], "%Y-%m-%d")
                else:
                    df = data_fattura
                giorni_differenza = abs((da - df).days)
                if giorni_differenza > 180:
                    problema["problemi"].append(f"Date differiscono di {giorni_differenza} giorni")
                    problema["giorni_differenza"] = giorni_differenza
                    statistiche["problemi_data"] += 1
                    ha_problemi = True
            except Exception:
                pass
        
        if ha_problemi:
            # Cerca fatture alternative suggerite
            suggerimenti = []
            for f in fatture_cursor:
                f_fornitore = f.get("supplier_name") or f.get("fornitore_ragione_sociale") or ""
                f_importo = float(f.get("total_amount") or f.get("importo_totale") or 0)
                f_pagata = f.get("pagato") or f.get("status") == "paid"
                
                if f_pagata or f.get("id") == fattura_id:
                    continue
                
                # Match per importo esatto o quasi
                if abs(f_importo - importo_assegno) < 2:
                    similarity = fuzz.token_set_ratio(beneficiario.upper(), f_fornitore.upper()) if beneficiario else 0
                    suggerimenti.append({
                        "fattura_id": f.get("id"),
                        "numero": f.get("invoice_number") or f.get("numero_documento"),
                        "fornitore": f_fornitore[:40],
                        "importo": f_importo,
                        "similarity": similarity,
                        "match_type": "importo_esatto" if abs(f_importo - importo_assegno) < 0.5 else "importo_simile"
                    })
            
            suggerimenti.sort(key=lambda x: x.get("similarity", 0), reverse=True)
            problema["suggerimenti"] = suggerimenti[:5]
            problemi.append(problema)
        else:
            statistiche["associazioni_corrette"] += 1
    
    return {
        "statistiche": statistiche,
        "problemi": problemi,
        "totale_problemi": len(problemi)
    }


@router.put("/correggi-associazione/{assegno_id}")
async def correggi_associazione_assegno(
    assegno_id: str,
    nuova_fattura_id: Optional[str] = Body(None, description="ID della nuova fattura da associare"),
    aggiorna_beneficiario: bool = Body(False, description="Aggiorna beneficiario dal fornitore")
) -> Dict[str, Any]:
    """
    Corregge l'associazione di un assegno con una fattura.
    """
    db = Database.get_db()
    
    assegno = await db[COLLECTION_ASSEGNI].find_one({"id": assegno_id})
    if not assegno:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    vecchia_fattura_id = assegno.get("fattura_id")
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if nuova_fattura_id:
        fattura = await db["invoices"].find_one({"id": nuova_fattura_id})
        if not fattura:
            raise HTTPException(status_code=404, detail="Fattura non trovata")
        
        update_data["fattura_id"] = nuova_fattura_id
        update_data["numero_fattura"] = fattura.get("invoice_number") or fattura.get("numero_documento")
        
        if aggiorna_beneficiario:
            update_data["beneficiario"] = fattura.get("supplier_name") or fattura.get("fornitore_ragione_sociale")
        
        if vecchia_fattura_id:
            await db["invoices"].update_one(
                {"id": vecchia_fattura_id},
                {"$set": {"pagato": False, "status": "imported", "assegno_id": None}}
            )
        
        await db["invoices"].update_one(
            {"id": nuova_fattura_id},
            {"$set": {"assegno_id": assegno_id}}
        )
        
        message = f"Associazione corretta per assegno {assegno.get('numero_assegno') or assegno.get('numero')}"
    else:
        update_data["fattura_id"] = None
        update_data["numero_fattura"] = None
        
        if vecchia_fattura_id:
            await db["invoices"].update_one(
                {"id": vecchia_fattura_id},
                {"$set": {"pagato": False, "status": "imported", "assegno_id": None}}
            )
        
        message = f"Associazione rimossa per assegno {assegno.get('numero_assegno') or assegno.get('numero')}"
    
    await db[COLLECTION_ASSEGNI].update_one({"id": assegno_id}, {"$set": update_data})
    
    return {"success": True, "message": message, "assegno_id": assegno_id, "nuova_fattura_id": nuova_fattura_id}


# === ROUTE DINAMICHE (con parametri) - DEVONO STARE DOPO LE STATICHE ===

@router.get("/{assegno_id}")
async def get_assegno(assegno_id: str) -> Dict[str, Any]:
    """Dettaglio singolo assegno."""
    db = Database.get_db()
    
    assegno = await db[COLLECTION_ASSEGNI].find_one(
        {"$or": [{"id": assegno_id}, {"numero": assegno_id}]},
        {"_id": 0}
    )
    
    if not assegno:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    return assegno


@router.put("/{assegno_id}")
async def update_assegno(
    assegno_id: str,
    data: Dict[str, Any] = Body(...)
) -> Dict[str, str]:
    """
    Aggiorna assegno (compila dati, cambia stato, etc.).
    """
    db = Database.get_db()
    
    # Rimuovi campi non modificabili
    data.pop("id", None)
    data.pop("numero", None)
    data.pop("created_at", None)
    
    # Valida stato se fornito
    if "stato" in data and data["stato"] not in ASSEGNO_STATI:
        raise HTTPException(status_code=400, detail=f"Stato non valido. Valori ammessi: {list(ASSEGNO_STATI.keys())}")
    
    # Se si compila un assegno vuoto, cambia stato automaticamente
    if data.get("importo") and data.get("beneficiario"):
        assegno = await db[COLLECTION_ASSEGNI].find_one(
            {"$or": [{"id": assegno_id}, {"numero": assegno_id}]}
        )
        if assegno and assegno.get("stato") == "vuoto":
            data["stato"] = "compilato"
    
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db[COLLECTION_ASSEGNI].update_one(
        {"$or": [{"id": assegno_id}, {"numero": assegno_id}]},
        {"$set": data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    return {"message": "Assegno aggiornato con successo"}


@router.post("/{assegno_id}/collega-fattura")
async def collega_fattura(
    assegno_id: str,
    fattura_id: str = Body(..., embed=True)
) -> Dict[str, str]:
    """
    Collega assegno a una fattura fornitore.
    """
    db = Database.get_db()
    
    # Verifica assegno
    assegno = await db[COLLECTION_ASSEGNI].find_one(
        {"$or": [{"id": assegno_id}, {"numero": assegno_id}]}
    )
    
    if not assegno:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    # Verifica fattura
    fattura = await db["invoices"].find_one({"$or": [{"id": fattura_id}, {"invoice_key": fattura_id}]})
    
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    # Aggiorna assegno
    await db[COLLECTION_ASSEGNI].update_one(
        {"_id": assegno["_id"]},
        {"$set": {
            "fattura_collegata": fattura_id,
            "fornitore_piva": fattura.get("cedente_piva"),
            "beneficiario": fattura.get("cedente_denominazione"),
            "importo": fattura.get("importo_totale"),
            "causale": f"Pagamento fattura {fattura.get('numero_fattura')} del {fattura.get('data_fattura')}",
            "stato": "compilato" if assegno.get("stato") == "vuoto" else assegno.get("stato"),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": "Assegno collegato alla fattura"}


@router.post("/{assegno_id}/emetti")
async def emetti_assegno(
    assegno_id: str,
    data_emissione: Optional[str] = Body(None)
) -> Dict[str, str]:
    """
    Emette l'assegno (cambia stato a 'emesso').
    """
    db = Database.get_db()
    
    assegno = await db[COLLECTION_ASSEGNI].find_one(
        {"$or": [{"id": assegno_id}, {"numero": assegno_id}]}
    )
    
    if not assegno:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    if assegno.get("stato") == "vuoto":
        raise HTTPException(status_code=400, detail="Impossibile emettere un assegno vuoto. Compilarlo prima.")
    
    if not data_emissione:
        data_emissione = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    await db[COLLECTION_ASSEGNI].update_one(
        {"_id": assegno["_id"]},
        {"$set": {
            "stato": "emesso",
            "data_emissione": data_emissione,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # C1: Registra movimento in prima_nota_banca all'emissione
    assegno_upd = await db[COLLECTION_ASSEGNI].find_one(
        {"$or": [{"id": assegno_id}, {"numero": assegno_id}]}, {"_id": 0}
    )
    if assegno_upd and assegno_upd.get("importo"):
        numero = assegno_upd.get("numero", assegno_id)
        parti = [f"Assegno n.{numero}"]
        if assegno_upd.get("numero_fattura"):
            parti.append(f"Fatt.{assegno_upd['numero_fattura']}")
        if assegno_upd.get("beneficiario"):
            parti.append(assegno_upd["beneficiario"][:30])
        mov = {
            "id": str(uuid.uuid4()),
            "tipo": "uscita",
            "importo": float(assegno_upd["importo"]),
            "data": data_emissione,
            "descrizione": " - ".join(parti),
            "categoria": "Addebito assegno",
            "source": "assegno_emesso",
            "riferimento_id": assegno_upd.get("id"),
            "assegno_numero": numero,
            "fattura_id": assegno_upd.get("fattura_collegata"),
            "fornitore_piva": assegno_upd.get("fornitore_piva"),
            "riconciliato": False,
            "anno": int(data_emissione[:4]),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db["prima_nota_banca"].insert_one(mov.copy())
        await db[COLLECTION_ASSEGNI].update_one(
            {"$or": [{"id": assegno_id}, {"numero": assegno_id}]},
            {"$set": {"prima_nota_banca_id": mov["id"]}}
        )
    
    return {"message": "Assegno emesso"}


@router.post("/{assegno_id}/incassa")
async def incassa_assegno(
    assegno_id: str,
    data_incasso: Optional[str] = Body(None),
    movimento_estratto_conto_id: Optional[str] = Body(None)
) -> Dict[str, Any]:
    """Segna assegno come incassato e propaga su fattura, scadenzario, prima nota."""
    db = Database.get_db()
    assegno = await db[COLLECTION_ASSEGNI].find_one(
        {"$or": [{"id": assegno_id}, {"numero": assegno_id}]}
    )
    if not assegno:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    data_incasso = data_incasso or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # 1. Aggiorna stato assegno
    await db[COLLECTION_ASSEGNI].update_one(
        {"id": assegno["id"]},
        {"$set": {"stato": "incassato", "data_incasso": data_incasso,
                  "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    # 2. Prima nota banca → riconciliata
    if assegno.get("prima_nota_banca_id"):
        await db["prima_nota_banca"].update_one(
            {"id": assegno["prima_nota_banca_id"]},
            {"$set": {"riconciliato": True, "data_riconciliazione": data_incasso,
                      "movimento_estratto_conto_id": movimento_estratto_conto_id,
                      "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    # 3. Fattura → pagata
    if assegno.get("fattura_collegata"):
        fid = assegno["fattura_collegata"]
        await db["invoices"].update_one(
            {"id": fid},
            {"$set": {"pagato": True, "data_pagamento": data_incasso,
                      "metodo_pagamento_effettivo": "assegno",
                      "assegno_numero": assegno.get("numero"),
                      "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        # 4. Scadenzario → chiuso
        await db["scadenziario_fornitori"].update_many(
            {"fattura_id": fid, "pagato": {"$ne": True}},
            {"$set": {"pagato": True, "data_pagamento": data_incasso,
                      "metodo_pagamento": "assegno",
                      "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    # 5. Estratto conto → riconciliato
    if movimento_estratto_conto_id:
        await db["estratto_conto_movimenti"].update_one(
            {"id": movimento_estratto_conto_id},
            {"$set": {"riconciliato": True, "riconciliato_con": "assegno",
                      "assegno_id": assegno["id"],
                      "riconciliato_at": datetime.now(timezone.utc).isoformat()}}
        )
    return {"message": "Assegno incassato",
            "fattura_chiusa": bool(assegno.get("fattura_collegata")),
            "prima_nota_riconciliata": bool(assegno.get("prima_nota_banca_id"))}


@router.post("/{assegno_id}/annulla")
async def annulla_assegno(assegno_id: str) -> Dict[str, str]:
    """Annulla assegno."""
    db = Database.get_db()
    
    result = await db[COLLECTION_ASSEGNI].update_one(
        {"$or": [{"id": assegno_id}, {"numero": assegno_id}]},
        {"$set": {
            "stato": "annullato",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    return {"message": "Assegno annullato"}


@router.delete("/{assegno_id}")
async def delete_assegno(
    assegno_id: str,
    force: bool = Query(False, description="Forza eliminazione")
) -> Dict[str, Any]:
    """
    Elimina un singolo assegno con validazione.
    
    **Regole:**
    - Non può eliminare assegni emessi o incassati
    - Non può eliminare assegni collegati a fatture
    """
    from app.services.business_rules import BusinessRules, EntityStatus
    from datetime import timezone
    
    db = Database.get_db()
    
    assegno = await db[COLLECTION_ASSEGNI].find_one({"id": assegno_id})
    if not assegno:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    validation = BusinessRules.can_delete_assegno(assegno)
    
    if not validation.is_valid:
        raise HTTPException(
            status_code=400,
            detail={"message": "Eliminazione non consentita", "errors": validation.errors}
        )
    
    # Soft-delete
    await db[COLLECTION_ASSEGNI].update_one(
        {"id": assegno_id},
        {"$set": {
            "entity_status": EntityStatus.DELETED.value,
            "deleted_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"success": True, "message": "Assegno eliminato"}


@router.delete("/clear-generated")
async def clear_generated_assegni(stato: str = Query("vuoto")) -> Dict[str, Any]:
    """
    Elimina tutti gli assegni con un determinato stato.
    Default: elimina solo quelli vuoti.
    """
    db = Database.get_db()
    
    if stato not in ASSEGNO_STATI:
        raise HTTPException(status_code=400, detail=f"Stato non valido. Valori ammessi: {list(ASSEGNO_STATI.keys())}")
    
    result = await db[COLLECTION_ASSEGNI].delete_many({"stato": stato})
    
    return {
        "message": f"Eliminati {result.deleted_count} assegni con stato '{stato}'",
        "deleted_count": result.deleted_count
    }


@router.post("/auto-associa")
async def auto_associa_assegni() -> Dict[str, Any]:
    """
    Auto-associa assegni alle fatture con algoritmo migliorato.
    
    Logica migliorata:
    1. Match esatto per importo (tolleranza 0.5€)
    2. Match per importo + nome fornitore simile (fuzzy matching)
    3. Match multiplo (N assegni = 1 fattura)
    4. Learning: usa associazioni precedenti per suggerire
    5. Match per data (assegno emesso entro 30gg dalla fattura)
    """
    db = Database.get_db()
    from app.database import Collections
    from difflib import SequenceMatcher
    
    def similarity(a: str, b: str) -> float:
        """Calcola similarità tra due stringhe (0-1)."""
        if not a or not b:
            return 0
        a = a.lower().strip()
        b = b.lower().strip()
        return SequenceMatcher(None, a, b).ratio()
    
    def normalize_name(name: str) -> str:
        """Normalizza nome fornitore per confronto."""
        if not name:
            return ""
        name = name.lower().strip()
        # Rimuovi forme giuridiche comuni
        for suffix in [" srl", " s.r.l.", " spa", " s.p.a.", " snc", " sas", " srls"]:
            name = name.replace(suffix, "")
        return name.strip()
    
    # Carica assegni da associare
    assegni_da_associare = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": None},
            {"beneficiario": ""},
            {"beneficiario": "N/A"},
            {"fattura_collegata": None}
        ],
        "importo": {"$gt": 0},
        "stato": {"$nin": ["annullato", "incassato"]}
    }, {"_id": 0}).to_list(1000)
    
    # Carica fatture non pagate
    fatture = await db[Collections.INVOICES].find({
        "status": {"$nin": STATI_PAGATI},
        "total_amount": {"$gt": 0}
    }, {"_id": 0}).to_list(5000)
    
    # Carica associazioni storiche per learning
    associazioni_storiche = await db[COLLECTION_ASSEGNI].find({
        "fattura_collegata": {"$ne": None},
        "beneficiario": {"$nin": [None, "", "N/A"]}
    }, {"_id": 0, "importo": 1, "beneficiario": 1, "fattura_collegata": 1}).to_list(5000)
    
    # Crea indice per learning: importo -> fornitori associati
    learning_map = {}
    for ass in associazioni_storiche:
        imp = round(ass.get("importo", 0), 2)
        ben = normalize_name(ass.get("beneficiario", ""))
        if imp > 0 and ben:
            if imp not in learning_map:
                learning_map[imp] = set()
            learning_map[imp].add(ben)
    
    logger.info(f"Auto-associazione: {len(assegni_da_associare)} assegni, {len(fatture)} fatture, {len(learning_map)} pattern appresi")
    
    associazioni = []
    assegni_associati = set()
    fatture_usate = set()
    
    # === FASE 1: Match esatto per importo ===
    for fattura in fatture:
        if fattura.get("id") in fatture_usate:
            continue
        importo_fattura = round(fattura.get("total_amount", 0), 2)
        fornitore_fattura = normalize_name(fattura.get("supplier_name", ""))
        
        for assegno in assegni_da_associare:
            if assegno["id"] in assegni_associati:
                continue
            importo_assegno = round(assegno.get("importo", 0), 2)
            
            # Match esatto importo (tolleranza 0.5€)
            if abs(importo_fattura - importo_assegno) < 0.5:
                associazioni.append({
                    "tipo": "esatto",
                    "confidenza": 1.0,
                    "assegno_id": assegno["id"],
                    "assegno_numero": assegno.get("numero"),
                    "fattura_id": fattura.get("id"),
                    "fattura_numero": fattura.get("invoice_number"),
                    "fornitore": fattura.get("supplier_name"),
                    "importo": importo_fattura
                })
                assegni_associati.add(assegno["id"])
                fatture_usate.add(fattura.get("id"))
                break
    
    # === FASE 2: Match con learning (stesso importo + fornitore conosciuto) ===
    for fattura in fatture:
        if fattura.get("id") in fatture_usate:
            continue
        importo_fattura = round(fattura.get("total_amount", 0), 2)
        fornitore_fattura = normalize_name(fattura.get("supplier_name", ""))
        
        # Cerca se questo fornitore è già stato associato a questo importo
        if importo_fattura in learning_map:
            fornitori_noti = learning_map[importo_fattura]
            for fornitore_noto in fornitori_noti:
                if similarity(fornitore_fattura, fornitore_noto) > 0.7:
                    # Cerca assegno con importo simile
                    for assegno in assegni_da_associare:
                        if assegno["id"] in assegni_associati:
                            continue
                        importo_assegno = round(assegno.get("importo", 0), 2)
                        
                        if abs(importo_fattura - importo_assegno) < 1.0:  # Tolleranza 1€
                            associazioni.append({
                                "tipo": "learning",
                                "confidenza": 0.85,
                                "assegno_id": assegno["id"],
                                "assegno_numero": assegno.get("numero"),
                                "fattura_id": fattura.get("id"),
                                "fattura_numero": fattura.get("invoice_number"),
                                "fornitore": fattura.get("supplier_name"),
                                "importo": importo_fattura,
                                "nota": f"Associato via learning (fornitore simile a {fornitore_noto})"
                            })
                            assegni_associati.add(assegno["id"])
                            fatture_usate.add(fattura.get("id"))
                            break
                    break
    
    # === FASE 3: Match multipli (N assegni = 1 fattura grande) ===
    from collections import Counter
    importi_assegni = Counter()
    for a in assegni_da_associare:
        if a["id"] not in assegni_associati:
            imp = round(a.get("importo", 0), 2)
            if imp > 0:
                importi_assegni[imp] += 1
    
    for importo_assegno, count in importi_assegni.items():
        if count <= 1:
            continue
        
        # Cerca fatture che potrebbero corrispondere a N assegni
        for n in range(count, 1, -1):  # Prova da count a 2
            importo_target = round(importo_assegno * n, 2)
            
            for fattura in fatture:
                if fattura.get("id") in fatture_usate:
                    continue
                importo_fattura = round(fattura.get("total_amount", 0), 2)
                
                tolleranza = max(2, importo_target * 0.005)  # 0.5% o minimo 2€
                
                if abs(importo_fattura - importo_target) <= tolleranza:
                    # Trova N assegni con questo importo
                    assegni_match = [a for a in assegni_da_associare 
                                   if abs(round(a.get("importo", 0), 2) - importo_assegno) < 0.5
                                   and a["id"] not in assegni_associati]
                    
                    if len(assegni_match) >= n:
                        for assegno in assegni_match[:n]:
                            associazioni.append({
                                "tipo": "multiplo",
                                "confidenza": 0.8,
                                "assegno_id": assegno["id"],
                                "assegno_numero": assegno.get("numero"),
                                "fattura_id": fattura.get("id"),
                                "fattura_numero": fattura.get("invoice_number"),
                                "fornitore": fattura.get("supplier_name"),
                                "importo": importo_assegno,
                                "nota": f"Fattura €{importo_fattura:.2f} = {n} assegni da €{importo_assegno:.2f}"
                            })
                            assegni_associati.add(assegno["id"])
                        fatture_usate.add(fattura.get("id"))
                        break
    
    # === FASE 4: Match fuzzy per nome (bassa confidenza) ===
    for fattura in fatture:
        if fattura.get("id") in fatture_usate:
            continue
        importo_fattura = round(fattura.get("total_amount", 0), 2)
        fornitore_fattura = normalize_name(fattura.get("supplier_name", ""))
        
        if not fornitore_fattura or len(fornitore_fattura) < 3:
            continue
        
        for assegno in assegni_da_associare:
            if assegno["id"] in assegni_associati:
                continue
            importo_assegno = round(assegno.get("importo", 0), 2)
            causale = normalize_name(assegno.get("causale", "") or assegno.get("note", ""))
            
            # Match importo (tolleranza 2%) E nome simile in causale
            if abs(importo_fattura - importo_assegno) < importo_fattura * 0.02:
                if causale and similarity(fornitore_fattura, causale) > 0.6:
                    associazioni.append({
                        "tipo": "fuzzy",
                        "confidenza": 0.6,
                        "assegno_id": assegno["id"],
                        "assegno_numero": assegno.get("numero"),
                        "fattura_id": fattura.get("id"),
                        "fattura_numero": fattura.get("invoice_number"),
                        "fornitore": fattura.get("supplier_name"),
                        "importo": importo_fattura,
                        "nota": f"Match fuzzy nome (similarity: {similarity(fornitore_fattura, causale):.0%})"
                    })
                    assegni_associati.add(assegno["id"])
                    fatture_usate.add(fattura.get("id"))
                    break
    
    # === APPLICA ASSOCIAZIONI (solo confidence >= 80%) ===
    MIN_CONFIDENCE_AUTO = 0.80
    
    associazioni_auto = [a for a in associazioni if a.get("confidenza", 0) >= MIN_CONFIDENCE_AUTO]
    proposte_manuali = [a for a in associazioni if a.get("confidenza", 0) < MIN_CONFIDENCE_AUTO]
    
    updated = 0
    for assoc in associazioni_auto:
        try:
            nota = assoc.get("nota", f"Pagamento fattura {assoc['fattura_numero']}")
            fornitore_str = (assoc.get('fornitore') or 'N/A')[:35]
            beneficiario = f"Pag. fatt. {assoc['fattura_numero']} - {fornitore_str}"
            
            result = await db[COLLECTION_ASSEGNI].update_one(
                {"id": assoc["assegno_id"]},
                {"$set": {
                    "beneficiario": beneficiario,
                    "numero_fattura": assoc["fattura_numero"],
                    "fattura_collegata": assoc["fattura_id"],
                    "note": nota,
                    "stato": "compilato",
                    "match_type": assoc["tipo"],
                    "match_confidenza": assoc["confidenza"],
                    "associazione_auto": True,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            if result.modified_count > 0:
                updated += 1
        except Exception as e:
            logger.error(f"Errore associazione assegno {assoc['assegno_numero']}: {e}")
    
    # === SALVA PROPOSTE MANUALI (confidence < 80%) ===
    proposte_salvate = 0
    for proposta in proposte_manuali:
        try:
            proposta_doc = {
                "id": f"prop-{proposta['assegno_id']}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                "assegno_id": proposta["assegno_id"],
                "assegno_numero": proposta.get("assegno_numero"),
                "fattura_id": proposta["fattura_id"],
                "fattura_numero": proposta.get("fattura_numero"),
                "fornitore": proposta.get("fornitore"),
                "importo": proposta.get("importo"),
                "tipo_match": proposta["tipo"],
                "confidenza": proposta["confidenza"],
                "nota": proposta.get("nota"),
                "stato": "da_confermare",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db["proposte_associazione_assegni"].update_one(
                {"assegno_id": proposta["assegno_id"], "fattura_id": proposta["fattura_id"]},
                {"$set": proposta_doc},
                upsert=True
            )
            proposte_salvate += 1
        except Exception as e:
            logger.error(f"Errore salvataggio proposta: {e}")
    
    # Raggruppa per tipo di match
    by_type = {}
    for a in associazioni:
        t = a["tipo"]
        if t not in by_type:
            by_type[t] = 0
        by_type[t] += 1
    
    return {
        "success": True,
        "message": f"Associati automaticamente {updated} assegni (confidence >= 80%), {proposte_salvate} proposte per conferma manuale",
        "associazioni_trovate": len(associazioni),
        "assegni_aggiornati_auto": updated,
        "proposte_manuali": proposte_salvate,
        "per_tipo": by_type,
        "soglia_auto": f"{MIN_CONFIDENCE_AUTO:.0%}",
        "dettagli_auto": sorted(associazioni_auto, key=lambda x: -x.get("confidenza", 0))[:30],
        "dettagli_manuali": sorted(proposte_manuali, key=lambda x: -x.get("confidenza", 0))[:20]
    }


@router.get("/proposte-associazione")
async def get_proposte_associazione() -> Dict[str, Any]:
    """Restituisce le proposte di associazione da confermare manualmente."""
    db = Database.get_db()
    
    proposte = await db["proposte_associazione_assegni"].find(
        {"stato": "da_confermare"},
        {"_id": 0}
    ).sort("confidenza", -1).to_list(100)
    
    return {
        "success": True,
        "totale": len(proposte),
        "proposte": proposte
    }


@router.post("/conferma-proposta/{proposta_id}")
async def conferma_proposta_associazione(proposta_id: str) -> Dict[str, Any]:
    """Conferma una proposta di associazione e applica l'associazione."""
    db = Database.get_db()
    
    proposta = await db["proposte_associazione_assegni"].find_one({"id": proposta_id})
    if not proposta:
        raise HTTPException(status_code=404, detail="Proposta non trovata")
    
    # Applica l'associazione
    fornitore_str = (proposta.get('fornitore') or 'N/A')[:35]
    beneficiario = f"Pag. fatt. {proposta['fattura_numero']} - {fornitore_str}"
    
    result = await db[COLLECTION_ASSEGNI].update_one(
        {"id": proposta["assegno_id"]},
        {"$set": {
            "beneficiario": beneficiario,
            "numero_fattura": proposta["fattura_numero"],
            "fattura_collegata": proposta["fattura_id"],
            "note": f"{proposta.get('nota', '')} [Confermato manualmente]",
            "stato": "compilato",
            "match_type": proposta["tipo_match"],
            "match_confidenza": proposta["confidenza"],
            "associazione_manuale": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Aggiorna stato proposta
    await db["proposte_associazione_assegni"].update_one(
        {"id": proposta_id},
        {"$set": {"stato": "confermata", "confirmed_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {
        "success": True,
        "message": f"Associazione confermata per assegno {proposta.get('assegno_numero')}"
    }


@router.post("/rifiuta-proposta/{proposta_id}")
async def rifiuta_proposta_associazione(proposta_id: str) -> Dict[str, Any]:
    """Rifiuta una proposta di associazione."""
    db = Database.get_db()
    
    result = await db["proposte_associazione_assegni"].update_one(
        {"id": proposta_id},
        {"$set": {"stato": "rifiutata", "rejected_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Proposta non trovata")
    
    return {"success": True, "message": "Proposta rifiutata"}


@router.get("/senza-associazione")
async def get_assegni_senza_associazione() -> Dict[str, Any]:
    """
    Restituisce assegni che hanno importo ma nessun beneficiario/fattura associata.
    Utile per debug e verifica manuale.
    """
    db = Database.get_db()
    
    assegni = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": None},
            {"beneficiario": ""},
            {"beneficiario": "N/A"}
        ],
        "importo": {"$gt": 0}
    }, {"_id": 0}).to_list(500)
    
    # Raggruppa per importo
    from collections import defaultdict
    per_importo = defaultdict(list)
    for a in assegni:
        imp = round(a.get("importo", 0), 2)
        per_importo[imp].append(a.get("numero"))
    
    return {
        "totale": len(assegni),
        "per_importo": {f"€{k:.2f}": {"count": len(v), "numeri": v[:10]} for k, v in sorted(per_importo.items(), key=lambda x: -len(x[1]))}
    }



@router.post("/sync-da-estratto-conto")
async def sync_assegni_da_estratto_conto() -> Dict[str, Any]:
    """
    Sincronizza gli assegni dall'estratto conto.
    
    Cerca movimenti con pattern "ASSEGNO" nella descrizione e li importa
    come assegni nella collection dedicata.
    
    Pattern riconosciuti:
    - VOSTRO ASSEGNO N. XXXXXXXXXX
    - PRELIEVO ASSEGNO N. XXXXXXXXXX
    - PAGAMENTO ASSEGNO
    - VS. ASSEGNO
    """
    import re
    db = Database.get_db()
    
    risultati = {
        "movimenti_analizzati": 0,
        "assegni_trovati": 0,
        "assegni_creati": 0,
        "assegni_esistenti": 0,
        "errori": [],
        "dettagli": []
    }
    
    # Pattern per estrarre numero assegno - AGGIORNATO per formato banca
    # Formato tipico: "PRELIEVO ASSEGNO - DM 06230 CRA: 42601623084409 NUM: 0208767182"
    # Il numero vero è quello dopo "NUM:", non dopo "CRA:"
    patterns_assegno = [
        r"NUM[:\s]+(\d{10,})",  # Prima cerca NUM: che è il numero reale
        r"ASSEGNO\s*N\.?\s*(\d{10,})",
        r"ASSEGNO\s+(\d{10,})",
        r"VS\.?\s*ASSEGNO\s*N?\.?\s*(\d{10,})",
        r"VOSTRO\s+ASSEGNO\s*N\.?\s*(\d{10,})",
        r"PRELIEVO\s+ASSEGNO\s*N?\.?\s*(\d{10,})",
    ]
    
    # Cerca movimenti con pattern specifici di pagamento assegno
    movimenti = await db.estratto_conto_movimenti.find({
        "$and": [
            {"$or": [
                {"descrizione": {"$regex": "PRELIEVO.*ASSEGNO", "$options": "i"}},
                {"descrizione": {"$regex": "VOSTRO.*ASSEGNO", "$options": "i"}},
                {"descrizione": {"$regex": "VS\\..*ASSEGNO", "$options": "i"}},
                {"descrizione": {"$regex": "PAGAMENTO.*ASSEGNO", "$options": "i"}},
                {"descrizione_originale": {"$regex": "PRELIEVO.*ASSEGNO", "$options": "i"}},
                {"descrizione_originale": {"$regex": "VOSTRO.*ASSEGNO", "$options": "i"}}
            ]},
            {"importo": {"$lt": 0}},  # Solo uscite
            {"descrizione": {"$not": {"$regex": "RILASCIO.*CARNET", "$options": "i"}}}  # Escludi rilascio carnet
        ]
    }, {"_id": 0}).to_list(1000)
    
    risultati["movimenti_analizzati"] = len(movimenti)
    
    for mov in movimenti:
        descrizione = mov.get("descrizione") or mov.get("descrizione_originale") or ""
        
        # Salta se è solo "RILASCIO CARNET ASSEGNI"
        if "RILASCIO CARNET" in descrizione.upper():
            continue
        
        # Estrai numero assegno
        numero_assegno = None
        for pattern in patterns_assegno:
            match = re.search(pattern, descrizione, re.IGNORECASE)
            if match:
                numero_assegno = match.group(1)
                break
        
        if not numero_assegno:
            # Se non trova numero, usa un ID univoco basato sul movimento
            numero_assegno = f"AUTO-{mov.get('id', '')[:8]}"
        
        risultati["assegni_trovati"] += 1
        
        # Verifica se esiste già
        esistente = await db[COLLECTION_ASSEGNI].find_one({
            "$or": [
                {"numero": numero_assegno},
                {"movimento_id": mov.get("id")}
            ]
        })
        
        if esistente:
            risultati["assegni_esistenti"] += 1
            continue
        
        # C3: Prima cerca nel carnet se già compilato/emesso
        assegno_carnet = await db[COLLECTION_ASSEGNI].find_one({
            "$or": [
                {"numero": {"$regex": numero_assegno[-8:] if len(numero_assegno) >= 8 else numero_assegno, "$options": "i"}},
                {"numero": numero_assegno}
            ],
            "stato": {"$in": ["compilato", "emesso"]}
        })
        if assegno_carnet:
            data = mov.get("data") or mov.get("data_pagamento")
            await db[COLLECTION_ASSEGNI].update_one(
                {"id": assegno_carnet["id"]},
                {"$set": {"stato": "incassato", "data_incasso": data,
                          "movimento_estratto_conto_id": mov.get("id"),
                          "updated_at": datetime.now().isoformat()}}
            )
            if assegno_carnet.get("fattura_collegata"):
                fid = assegno_carnet["fattura_collegata"]
                await db["invoices"].update_one({"id": fid},
                    {"$set": {"pagato": True, "data_pagamento": data}})
                await db["scadenziario_fornitori"].update_many(
                    {"fattura_id": fid, "pagato": {"$ne": True}},
                    {"$set": {"pagato": True, "data_pagamento": data}})
            if assegno_carnet.get("prima_nota_banca_id"):
                await db["prima_nota_banca"].update_one(
                    {"id": assegno_carnet["prima_nota_banca_id"]},
                    {"$set": {"riconciliato": True, "data_riconciliazione": data,
                              "movimento_estratto_conto_id": mov.get("id")}})
            risultati["assegni_riconciliati"] = risultati.get("assegni_riconciliati", 0) + 1
            continue
        
        # Crea assegno
        importo = abs(float(mov.get("importo", 0)))
        data = mov.get("data") or mov.get("data_pagamento")
        
        assegno = {
            "id": str(uuid.uuid4()),
            "numero": numero_assegno,
            "importo": importo,
            "data": data,
            "data_emissione": data,
            "stato": "emesso",
            "beneficiario": mov.get("fornitore") or mov.get("ragione_sociale") or "",
            "descrizione": descrizione,
            "movimento_id": mov.get("id"),
            "fonte": "estratto_conto",
            "banca": mov.get("banca"),
            "confermato": False,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        try:
            await db[COLLECTION_ASSEGNI].insert_one(assegno)
            risultati["assegni_creati"] += 1
            risultati["dettagli"].append({
                "numero": numero_assegno,
                "importo": importo,
                "data": data,
                "descrizione": descrizione[:50]
            })
        except Exception as e:
            risultati["errori"].append(f"Errore creazione assegno {numero_assegno}: {str(e)}")
    
    return risultati


@router.post("/ricostruisci-dati")
async def ricostruisci_dati_assegni() -> Dict[str, Any]:
    """
    LOGICA INTELLIGENTE: Ricostruisce automaticamente i dati mancanti degli assegni.
    
    Questa funzione viene chiamata automaticamente dal frontend quando si carica
    la pagina Gestione Assegni. Implementa la logica di un commercialista esperto.
    
    REGOLE:
    1. Estrae beneficiario dalla descrizione bancaria se mancante
    2. Cerca fatture con lo stesso importo per associazione
    3. Gestisce pagamenti parziali/splittati
    4. Cerca nel database fornitori per conferma nome
    """
    import re
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now().isoformat(),
        "assegni_processati": 0,
        "beneficiari_trovati": 0,
        "fatture_associate": 0,
        "errori": []
    }
    
    # 1. Carica assegni con dati mancanti
    assegni = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": {"$in": [None, "", "-"]}},
            {"numero_fattura": {"$exists": False}},
            {"numero_fattura": None}
        ]
    }, {"_id": 0}).to_list(10000)
    
    if not assegni:
        return {"message": "Tutti gli assegni hanno già i dati completi", **risultati}
    
    risultati["assegni_processati"] = len(assegni)
    
    # 2. Carica dati di supporto
    fatture = await db.invoices.find({}, {
        "_id": 0, "id": 1, "invoice_number": 1, "numero_documento": 1,
        "supplier_name": 1, "fornitore_ragione_sociale": 1,
        "supplier_vat": 1, "fornitore_partita_iva": 1,
        "total_amount": 1, "importo_totale": 1, "pagato": 1
    }).to_list(10000)
    
    fornitori = await db["fornitori"].find({}, {
        "_id": 0, "denominazione": 1, "ragione_sociale": 1, "partita_iva": 1
    }).to_list(10000)
    
    movimenti = await db.estratto_conto_movimenti.find({}, {
        "_id": 0, "id": 1, "descrizione": 1, "descrizione_originale": 1,
        "beneficiario": 1, "controparte": 1
    }).to_list(10000)
    
    # 3. Crea indici
    # Indice fatture per importo
    fatture_per_importo = {}
    for f in fatture:
        imp = round(float(f.get("total_amount") or f.get("importo_totale") or 0), 2)
        if imp > 0:
            if imp not in fatture_per_importo:
                fatture_per_importo[imp] = []
            fatture_per_importo[imp].append(f)
    
    # Indice fornitori per nome
    fornitori_nomi = {(f.get("denominazione") or f.get("ragione_sociale") or "").upper()[:20]: f for f in fornitori if f.get("denominazione") or f.get("ragione_sociale")}
    
    # Indice movimenti per id
    movimenti_idx = {m.get("id"): m for m in movimenti}
    
    # 4. Pattern per estrarre beneficiario
    def estrai_beneficiario(testo):
        if not testo:
            return None
        testo = testo.upper()
        
        # Pattern comuni nei movimenti bancari italiani
        patterns = [
            r"BEN[:\s]+([A-Z][A-Z0-9\s\.\&\'-]+?)(?:\s+(?:CRO|TRN|DATA|IBAN|$))",
            r"VERS[OA]?\s+([A-Z][A-Z0-9\s\.\&\'-]+?)(?:\s+(?:CRO|DATA|$))",
            r"BONIFICO\s+(?:A\s+)?([A-Z][A-Z0-9\s\.\&\'-]+?)(?:\s+(?:CRO|DATA|$))",
            r"PAGAMENTO\s+([A-Z][A-Z0-9\s\.\&\'-]+?)(?:\s+(?:FATT|N\.|$))",
        ]
        
        for p in patterns:
            match = re.search(p, testo)
            if match:
                nome = match.group(1).strip()
                if len(nome) > 3:
                    return nome
        
        # Cerca nomi fornitori noti
        for nome_forn in fornitori_nomi.keys():
            if nome_forn and len(nome_forn) > 5 and nome_forn in testo:
                return fornitori_nomi[nome_forn].get("denominazione") or fornitori_nomi[nome_forn].get("ragione_sociale")
        
        return None
    
    # 5. Processa ogni assegno
    for ass in assegni:
        ass_id = ass.get("id")
        importo = round(float(ass.get("importo", 0)), 2)
        descrizione = ass.get("descrizione", "")
        beneficiario = ass.get("beneficiario")
        mov_id = ass.get("movimento_id")
        
        aggiornamenti = {}
        
        # a) Trova beneficiario se mancante
        if not beneficiario or beneficiario in ["", "-", None]:
            # Prima prova dalla descrizione assegno
            ben = estrai_beneficiario(descrizione)
            
            # Se non trovato, cerca nel movimento originale
            if not ben and mov_id and mov_id in movimenti_idx:
                mov = movimenti_idx[mov_id]
                ben = mov.get("beneficiario") or mov.get("controparte") or estrai_beneficiario(mov.get("descrizione") or mov.get("descrizione_originale"))
            
            if ben:
                aggiornamenti["beneficiario"] = ben
                risultati["beneficiari_trovati"] += 1
        
        # b) Trova fattura se mancante
        if not ass.get("numero_fattura") and importo > 0:
            if importo in fatture_per_importo:
                candidates = fatture_per_importo[importo]
                
                # Se una sola fattura con questo importo, associa direttamente
                if len(candidates) == 1:
                    fatt = candidates[0]
                    aggiornamenti["fattura_id"] = fatt.get("id")
                    aggiornamenti["numero_fattura"] = fatt.get("invoice_number") or fatt.get("numero_documento")
                    aggiornamenti["fornitore_fattura"] = fatt.get("supplier_name") or fatt.get("fornitore_ragione_sociale")
                    
                    # Se non avevamo beneficiario, usa quello della fattura
                    if "beneficiario" not in aggiornamenti and not beneficiario:
                        aggiornamenti["beneficiario"] = aggiornamenti["fornitore_fattura"]
                    
                    risultati["fatture_associate"] += 1
                
                # Se più fatture, cerca match per beneficiario
                elif len(candidates) > 1 and (beneficiario or aggiornamenti.get("beneficiario")):
                    ben_search = (beneficiario or aggiornamenti.get("beneficiario", "")).upper()[:15]
                    for fatt in candidates:
                        nome_forn = (fatt.get("supplier_name") or fatt.get("fornitore_ragione_sociale") or "").upper()
                        if ben_search in nome_forn or nome_forn[:15] in ben_search:
                            aggiornamenti["fattura_id"] = fatt.get("id")
                            aggiornamenti["numero_fattura"] = fatt.get("invoice_number") or fatt.get("numero_documento")
                            aggiornamenti["fornitore_fattura"] = fatt.get("supplier_name") or fatt.get("fornitore_ragione_sociale")
                            risultati["fatture_associate"] += 1
                            break
        
        # c) Aggiorna nel DB
        if aggiornamenti:
            aggiornamenti["ultima_ricostruzione"] = datetime.now().isoformat()
            try:
                await db[COLLECTION_ASSEGNI].update_one(
                    {"id": ass_id},
                    {"$set": aggiornamenti}
                )
            except Exception as e:
                risultati["errori"].append(f"Errore aggiornamento {ass_id}: {str(e)}")
    
    return risultati



@router.post("/correggi-numeri")
async def correggi_numeri_assegni() -> Dict[str, Any]:
    """
    Corregge i numeri degli assegni estratti erroneamente (CRA invece di NUM).
    
    Il formato bancario è: "PRELIEVO ASSEGNO - DM 06230 CRA: 42601623084409 NUM: 0208767182"
    Il numero corretto è quello dopo "NUM:", non quello dopo "CRA:".
    """
    import re
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assegni_analizzati": 0,
        "numeri_corretti": 0,
        "errori": []
    }
    
    # Trova assegni con numeri lunghi (probabilmente CRA)
    assegni = await db[COLLECTION_ASSEGNI].find({
        "numero": {"$regex": r"^\d{14,}$"}  # Numeri con 14+ cifre sono probabilmente CRA
    }, {"_id": 0}).to_list(10000)
    
    risultati["assegni_analizzati"] = len(assegni)
    
    for ass in assegni:
        descrizione = ass.get("descrizione", "")
        numero_attuale = ass.get("numero", "")
        
        # Cerca il numero reale dopo "NUM:"
        match = re.search(r"NUM[:\s]+(\d{10,})", descrizione, re.IGNORECASE)
        if match:
            numero_corretto = match.group(1)
            
            if numero_corretto != numero_attuale:
                try:
                    # Salva il vecchio numero come riferimento
                    await db[COLLECTION_ASSEGNI].update_one(
                        {"id": ass["id"]},
                        {"$set": {
                            "numero": numero_corretto,
                            "numero_cra": numero_attuale,  # Salva CRA per riferimento
                            "numero_corretto_automaticamente": True,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    risultati["numeri_corretti"] += 1
                except Exception as e:
                    risultati["errori"].append(f"Errore update {ass['id']}: {str(e)}")
    
    return risultati



@router.post("/associa-beneficiari-robusto")
async def associa_beneficiari_robusto() -> Dict[str, Any]:
    """
    LOGICA ROBUSTA: Cerca e associa beneficiari agli assegni senza beneficiario.
    
    ALGORITMO:
    1. Per ogni assegno senza beneficiario
    2. Cerca fatture con importo simile (±10€) nella finestra temporale (±30 giorni)
    3. Se trovato match unico, associa
    4. Se trovati più match, cerca di distinguere per fornitore già pagato con altri assegni
    5. Gestisce pagamenti multipli (una fattura pagata con più assegni)
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assegni_analizzati": 0,
        "beneficiari_trovati": 0,
        "fatture_associate": 0,
        "pagamenti_multipli": 0,
        "non_trovati": [],
        "errori": []
    }
    
    # 1. Trova assegni senza beneficiario
    assegni_senza_ben = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": None},
            {"beneficiario": ""},
            {"beneficiario": {"$exists": False}}
        ]
    }, {"_id": 0}).to_list(10000)
    
    risultati["assegni_analizzati"] = len(assegni_senza_ben)
    
    # 2. Carica tutte le fatture (collection 'invoices' - fatture ricevute da fornitori)
    fatture = await db.invoices.find({
        "total_amount": {"$gt": 0}
    }, {"_id": 0}).to_list(50000)
    
    # Indice fatture per importo approssimativo (arrotondato)
    fatture_by_importo = {}
    for f in fatture:
        importo = round(float(f.get("total_amount") or f.get("importo_totale") or 0), 0)
        if importo > 0:
            if importo not in fatture_by_importo:
                fatture_by_importo[importo] = []
            fatture_by_importo[importo].append(f)
    
    # 3. Carica fornitori per nome
    fornitori = await db["fornitori"].find({}, {"_id": 0}).to_list(10000)
    fornitori_idx = {}
    for f in fornitori:
        nome = (f.get("ragione_sociale") or f.get("denominazione") or "").upper()
        if nome:
            fornitori_idx[nome] = f
    
    for ass in assegni_senza_ben:
        importo_ass = abs(float(ass.get("importo") or 0))
        data_ass_str = ass.get("data") or ""
        numero_ass = ass.get("numero", "")
        
        if importo_ass == 0:
            continue
        
        # Cerca fatture con importo simile (±10€)
        candidati = []
        for delta in range(-10, 11):
            importo_cerca = round(importo_ass + delta, 0)
            if importo_cerca in fatture_by_importo:
                candidati.extend(fatture_by_importo[importo_cerca])
        
        # Filtra per data (±60 giorni dall'assegno)
        try:
            if data_ass_str:
                data_ass = datetime.fromisoformat(data_ass_str.replace('Z', '+00:00'))
            else:
                data_ass = None
        except Exception:
            data_ass = None
        
        match_trovato = None
        
        if len(candidati) == 1:
            # Match unico!
            match_trovato = candidati[0]
        elif len(candidati) > 1 and data_ass:
            # Più candidati - cerca quello più vicino per data
            candidati_ordinati = []
            for c in candidati:
                data_fatt_str = c.get("invoice_date") or c.get("data_fattura") or ""
                try:
                    data_fatt = datetime.fromisoformat(data_fatt_str.replace('Z', '+00:00'))
                    diff_giorni = abs((data_ass - data_fatt).days)
                    if diff_giorni <= 90:  # Max 90 giorni di differenza
                        candidati_ordinati.append((c, diff_giorni))
                except Exception:
                    pass
            
            if candidati_ordinati:
                candidati_ordinati.sort(key=lambda x: x[1])
                match_trovato = candidati_ordinati[0][0]
        
        if match_trovato:
            fornitore = match_trovato.get("supplier_name") or match_trovato.get("fornitore") or ""
            numero_fatt = match_trovato.get("invoice_number") or match_trovato.get("numero_fattura") or ""
            
            try:
                await db[COLLECTION_ASSEGNI].update_one(
                    {"id": ass["id"]},
                    {"$set": {
                        "beneficiario": fornitore,
                        "fattura_associata": numero_fatt,
                        "fattura_id": match_trovato.get("id"),
                        "importo_fattura": match_trovato.get("total_amount"),
                        "associazione_automatica": True,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                risultati["beneficiari_trovati"] += 1
                risultati["fatture_associate"] += 1
            except Exception as e:
                risultati["errori"].append(f"Errore update {ass['id']}: {str(e)}")
        else:
            risultati["non_trovati"].append({
                "numero": numero_ass,
                "importo": importo_ass,
                "data": data_ass_str
            })
    
    return risultati


@router.post("/associa-pagamenti-multipli")
async def associa_pagamenti_multipli() -> Dict[str, Any]:
    """
    LOGICA AVANZATA: Gestisce fatture pagate con più assegni.
    
    ALGORITMO:
    1. Raggruppa assegni per beneficiario
    2. Per ogni gruppo, cerca fatture con importo = somma assegni
    3. Se trovato, marca tutti gli assegni come parte dello stesso pagamento
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gruppi_analizzati": 0,
        "pagamenti_multipli_trovati": 0,
        "assegni_collegati": 0,
        "errori": []
    }
    
    # Raggruppa assegni per beneficiario
    pipeline = [
        {"$match": {"beneficiario": {"$exists": True, "$ne": ""}}},
        {"$group": {
            "_id": "$beneficiario",
            "assegni": {"$push": {
                "id": "$id",
                "numero": "$numero",
                "importo": "$importo",
                "data": "$data",
                "fattura_associata": "$fattura_associata"
            }},
            "totale": {"$sum": {"$abs": "$importo"}},
            "count": {"$sum": 1}
        }},
        {"$match": {"count": {"$gt": 1}}}  # Solo beneficiari con più assegni
    ]
    
    gruppi = await db[COLLECTION_ASSEGNI].aggregate(pipeline).to_list(1000)
    risultati["gruppi_analizzati"] = len(gruppi)
    
    for gruppo in gruppi:
        beneficiario = gruppo["_id"]
        totale_assegni = round(float(gruppo["totale"]), 2)
        assegni_gruppo = gruppo["assegni"]
        
        # Cerca fattura con importo uguale al totale degli assegni (±5€)
        fattura_match = await db.invoices.find_one({
            "supplier_name": {"$regex": beneficiario, "$options": "i"},
            "total_amount": {"$gte": totale_assegni - 5, "$lte": totale_assegni + 5}
        }, {"_id": 0})
        
        if fattura_match:
            numero_fatt = fattura_match.get("invoice_number") or ""
            
            # Aggiorna tutti gli assegni del gruppo
            for i, ass in enumerate(assegni_gruppo):
                try:
                    await db[COLLECTION_ASSEGNI].update_one(
                        {"id": ass["id"]},
                        {"$set": {
                            "fattura_associata": numero_fatt,
                            "fattura_id": fattura_match.get("id"),
                            "pagamento_multiplo": True,
                            "pagamento_multiplo_numero": i + 1,
                            "pagamento_multiplo_totale": len(assegni_gruppo),
                            "pagamento_multiplo_importo_fattura": fattura_match.get("total_amount"),
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    risultati["assegni_collegati"] += 1
                except Exception as e:
                    risultati["errori"].append(f"Errore {ass['id']}: {str(e)}")
            
            risultati["pagamenti_multipli_trovati"] += 1
    
    return risultati


@router.post("/cerca-combinazioni-assegni")
async def cerca_combinazioni_assegni(
    max_assegni: int = Query(4, ge=2, le=6, description="Numero massimo di assegni per combinazione"),
    tolleranza: float = Query(1.0, ge=0.01, le=10, description="Tolleranza in euro per il match")
) -> Dict[str, Any]:
    """
    🔍 LOGICA AVANZATA: Cerca combinazioni di assegni senza beneficiario che sommati
    corrispondono all'importo di una fattura non pagata.
    
    CASO D'USO:
    - 3 assegni da €1.663,26 → cerca fattura da €4.989,78 (3 × 1.663,26)
    - Assegni €855,98 + €1.028,82 → cerca fattura da €1.884,80
    
    ALGORITMO:
    1. Prende tutti gli assegni senza beneficiario
    2. Genera tutte le combinazioni possibili (da 2 a max_assegni elementi)
    3. Per ogni combinazione, calcola la somma
    4. Cerca fatture non pagate con importo corrispondente (± tolleranza)
    5. Se trova match, associa tutti gli assegni della combinazione
    
    PARAMETRI:
    - max_assegni: numero massimo di assegni per combinazione (default: 4)
    - tolleranza: tolleranza in euro per il match (default: 1.0€)
    """
    from itertools import combinations
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assegni_analizzati": 0,
        "combinazioni_testate": 0,
        "match_trovati": 0,
        "assegni_associati": 0,
        "dettagli_match": [],
        "assegni_non_associabili": [],
        "errori": []
    }
    
    # 1. Carica assegni senza beneficiario valido
    assegni_senza_ben = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": None},
            {"beneficiario": ""},
            {"beneficiario": "N/A"},
            {"beneficiario": "-"}
        ],
        "importo": {"$gt": 0}
    }, {"_id": 0}).to_list(1000)
    
    # Filtra quelli non cancellati (entity_status potrebbe non esistere)
    assegni_senza_ben = [a for a in assegni_senza_ben if a.get("entity_status") != "deleted"]
    
    risultati["assegni_analizzati"] = len(assegni_senza_ben)
    
    if len(assegni_senza_ben) < 2:
        return {
            **risultati,
            "message": "Meno di 2 assegni senza beneficiario - nessuna combinazione possibile"
        }
    
    # 2. Carica fatture non pagate
    fatture_non_pagate = await db.invoices.find({
        "$or": [
            {"status": {"$nin": STATI_PAGATI}},
            {"pagato": {"$ne": True}}
        ],
        "total_amount": {"$gt": 0}
    }, {"_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1, "total_amount": 1}).to_list(10000)
    
    # Crea indice per importo arrotondato
    fatture_per_importo = {}
    for f in fatture_non_pagate:
        imp = round(float(f.get("total_amount", 0)), 2)
        if imp not in fatture_per_importo:
            fatture_per_importo[imp] = []
        fatture_per_importo[imp].append(f)
    
    logger.info(f"Cerca combinazioni: {len(assegni_senza_ben)} assegni, {len(fatture_non_pagate)} fatture non pagate")
    
    # 3. Prepara lista di importi con riferimento agli assegni
    assegni_con_importo = [
        {"assegno": a, "importo": round(float(a.get("importo", 0)), 2)}
        for a in assegni_senza_ben
        if float(a.get("importo", 0)) > 0
    ]
    
    # 4. Genera e testa combinazioni (da 2 a max_assegni)
    assegni_gia_associati = set()
    
    for num_assegni in range(2, min(max_assegni + 1, len(assegni_con_importo) + 1)):
        for combo in combinations(enumerate(assegni_con_importo), num_assegni):
            # Salta se qualche assegno è già stato associato
            indices = [c[0] for c in combo]
            if any(idx in assegni_gia_associati for idx in indices):
                continue
            
            risultati["combinazioni_testate"] += 1
            
            assegni_combo = [c[1]["assegno"] for c in combo]
            somma = sum(c[1]["importo"] for c in combo)
            somma_round = round(somma, 2)
            
            # Cerca fattura con questo importo (con tolleranza)
            fattura_match = None
            for delta in [0, -0.01, 0.01, -0.02, 0.02, -0.5, 0.5, -1, 1]:
                importo_cerca = round(somma_round + delta, 2)
                if importo_cerca in fatture_per_importo:
                    fattura_match = fatture_per_importo[importo_cerca][0]
                    break
            
            # Se non trovato con lookup diretto, cerca con range
            if not fattura_match:
                for f in fatture_non_pagate:
                    imp_fatt = round(float(f.get("total_amount", 0)), 2)
                    if abs(imp_fatt - somma_round) <= tolleranza:
                        fattura_match = f
                        break
            
            if fattura_match:
                # MATCH TROVATO!
                risultati["match_trovati"] += 1
                
                fornitore = fattura_match.get("supplier_name", "")
                numero_fatt = fattura_match.get("invoice_number", "")
                importo_fatt = fattura_match.get("total_amount", 0)
                
                dettaglio = {
                    "tipo": "combinazione",
                    "num_assegni": num_assegni,
                    "assegni": [a.get("numero") for a in assegni_combo],
                    "importi_assegni": [round(float(a.get("importo", 0)), 2) for a in assegni_combo],
                    "somma_assegni": somma_round,
                    "fattura_numero": numero_fatt,
                    "fattura_importo": importo_fatt,
                    "fornitore": fornitore,
                    "differenza": round(importo_fatt - somma_round, 2)
                }
                risultati["dettagli_match"].append(dettaglio)
                
                # Associa tutti gli assegni della combinazione
                for i, ass in enumerate(assegni_combo):
                    try:
                        await db[COLLECTION_ASSEGNI].update_one(
                            {"id": ass["id"]},
                            {"$set": {
                                "beneficiario": fornitore,
                                "fattura_associata": numero_fatt,
                                "fattura_id": fattura_match.get("id"),
                                "pagamento_combinato": True,
                                "combinazione_assegni": [a.get("numero") for a in assegni_combo],
                                "combinazione_numero": i + 1,
                                "combinazione_totale": num_assegni,
                                "importo_fattura_combinata": importo_fatt,
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }}
                        )
                        risultati["assegni_associati"] += 1
                        assegni_gia_associati.add(indices[i])
                    except Exception as e:
                        risultati["errori"].append(f"Errore update {ass['id']}: {str(e)}")
                
                # Rimuovi fattura dall'indice per evitare doppi match
                if somma_round in fatture_per_importo:
                    fatture_per_importo[somma_round] = [
                        f for f in fatture_per_importo[somma_round] 
                        if f.get("id") != fattura_match.get("id")
                    ]
    
    # 5. Elenco assegni rimasti non associabili
    for idx, item in enumerate(assegni_con_importo):
        if idx not in assegni_gia_associati:
            risultati["assegni_non_associabili"].append({
                "numero": item["assegno"].get("numero"),
                "importo": item["importo"]
            })
    
    return risultati


@router.get("/preview-combinazioni")
async def preview_combinazioni_assegni(
    max_assegni: int = Query(4, ge=2, le=6)
) -> Dict[str, Any]:
    """
    🔎 PREVIEW: Mostra le possibili combinazioni di assegni che potrebbero matchare fatture.
    Non esegue modifiche, solo analisi.
    
    Utile per verificare prima di eseguire l'associazione.
    """
    from itertools import combinations
    db = Database.get_db()
    
    # Carica assegni senza beneficiario
    assegni_senza_ben = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": None},
            {"beneficiario": ""},
            {"beneficiario": "N/A"},
            {"beneficiario": "-"}
        ],
        "importo": {"$gt": 0}
    }, {"_id": 0, "numero": 1, "importo": 1}).to_list(100)
    
    # Filtra quelli non cancellati
    assegni_senza_ben = [a for a in assegni_senza_ben if a.get("entity_status") != "deleted"]
    
    if len(assegni_senza_ben) < 2:
        return {
            "assegni_senza_beneficiario": len(assegni_senza_ben),
            "combinazioni_possibili": [],
            "message": "Servono almeno 2 assegni per cercare combinazioni"
        }
    
    # Carica fatture non pagate
    fatture = await db.invoices.find({
        "$or": [
            {"status": {"$nin": STATI_PAGATI}},
            {"pagato": {"$ne": True}}
        ],
        "total_amount": {"$gt": 0}
    }, {"_id": 0, "invoice_number": 1, "supplier_name": 1, "total_amount": 1}).to_list(10000)
    
    importi_fatture = {round(float(f.get("total_amount", 0)), 2): f for f in fatture}
    
    # Cerca combinazioni
    possibili_match = []
    importi = [(a.get("numero"), round(float(a.get("importo", 0)), 2)) for a in assegni_senza_ben]
    
    for r in range(2, min(max_assegni + 1, len(importi) + 1)):
        for combo in combinations(importi, r):
            somma = round(sum(imp for _, imp in combo), 2)
            
            # Cerca fattura con questo importo (±1€)
            for delta in [0, -0.01, 0.01, -0.02, 0.02, -0.5, 0.5, -1, 1]:
                imp_cerca = round(somma + delta, 2)
                if imp_cerca in importi_fatture:
                    f = importi_fatture[imp_cerca]
                    possibili_match.append({
                        "assegni": [num for num, _ in combo],
                        "importi": [imp for _, imp in combo],
                        "somma": somma,
                        "fattura": f.get("invoice_number"),
                        "fornitore": f.get("supplier_name", "")[:40],
                        "importo_fattura": f.get("total_amount"),
                        "differenza": round(f.get("total_amount", 0) - somma, 2)
                    })
                    break
    
    return {
        "assegni_senza_beneficiario": len(assegni_senza_ben),
        "fatture_non_pagate": len(fatture),
        "combinazioni_con_match": len(possibili_match),
        "dettagli": possibili_match[:20]  # Primi 20 per non sovraccaricare
    }

