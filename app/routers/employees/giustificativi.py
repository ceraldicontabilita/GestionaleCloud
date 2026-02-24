"""
GESTIONE GIUSTIFICATIVI DIPENDENTI
===================================

Sistema per la gestione dei giustificativi con limiti massimali:
- Codici giustificativi standard italiani
- Limiti annuali e mensili configurabili
- Contatori automatici per dipendente
- Validazione e blocco superamento limiti

Autore: Sistema Gestionale
Data: 22 Gennaio 2026
"""

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from typing import Dict, Any, List
from datetime import datetime, timezone
import uuid
import tempfile
import os
import base64

from app.database import Database

import logging
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# GIUSTIFICATIVI STANDARD ITALIANI
# =============================================================================

GIUSTIFICATIVI_DEFAULT = [
    # Assenze
    {"codice": "AI", "descrizione": "Assenza Ingiustificata", "categoria": "assenza", 
     "limite_annuale_ore": 173, "limite_mensile_ore": 16, "retribuito": False},
    {"codice": "ASNR", "descrizione": "Aspettativa Non Retribuita", "categoria": "assenza",
     "limite_annuale_ore": None, "limite_mensile_ore": None, "retribuito": False},
    {"codice": "AS", "descrizione": "Aspettativa Retribuita", "categoria": "assenza",
     "limite_annuale_ore": None, "limite_mensile_ore": None, "retribuito": True},
    
    # Ferie e Permessi
    {"codice": "FER", "descrizione": "Ferie", "categoria": "ferie",
     "limite_annuale_ore": 208, "limite_mensile_ore": None, "retribuito": True},  # 26 giorni * 8 ore
    {"codice": "PER", "descrizione": "Permesso Retribuito", "categoria": "permesso",
     "limite_annuale_ore": 32, "limite_mensile_ore": 8, "retribuito": True},
    {"codice": "ROL", "descrizione": "Riduzione Orario Lavoro", "categoria": "permesso",
     "limite_annuale_ore": 72, "limite_mensile_ore": None, "retribuito": True},
    {"codice": "EXF", "descrizione": "Ex Festività", "categoria": "permesso",
     "limite_annuale_ore": 32, "limite_mensile_ore": None, "retribuito": True},  # 4 giorni * 8 ore
    {"codice": "PNR", "descrizione": "Permesso Non Retribuito", "categoria": "permesso",
     "limite_annuale_ore": None, "limite_mensile_ore": None, "retribuito": False},
    
    # Congedi
    {"codice": "CP", "descrizione": "Congedo Parentale", "categoria": "congedo",
     "limite_annuale_ore": None, "limite_mensile_ore": None, "retribuito": True},
    {"codice": "CPFNR", "descrizione": "Congedo Parentale Figli 12+ anni", "categoria": "congedo",
     "limite_annuale_ore": None, "limite_mensile_ore": None, "retribuito": False},
    {"codice": "CMAT", "descrizione": "Congedo Maternità", "categoria": "congedo",
     "limite_annuale_ore": None, "limite_mensile_ore": None, "retribuito": True},
    {"codice": "CPAT", "descrizione": "Congedo Paternità", "categoria": "congedo",
     "limite_annuale_ore": 80, "limite_mensile_ore": None, "retribuito": True},  # 10 giorni * 8 ore
    {"codice": "CLUT", "descrizione": "Congedo Lutto", "categoria": "congedo",
     "limite_annuale_ore": 24, "limite_mensile_ore": None, "retribuito": True},  # 3 giorni
    {"codice": "CMAT", "descrizione": "Congedo Matrimonio", "categoria": "congedo",
     "limite_annuale_ore": 120, "limite_mensile_ore": None, "retribuito": True},  # 15 giorni
    
    # Malattia e Infortunio
    {"codice": "MAL", "descrizione": "Malattia", "categoria": "malattia",
     "limite_annuale_ore": None, "limite_mensile_ore": None, "retribuito": True},
    {"codice": "INF", "descrizione": "Infortunio sul Lavoro", "categoria": "infortunio",
     "limite_annuale_ore": None, "limite_mensile_ore": None, "retribuito": True},
    {"codice": "MALF", "descrizione": "Malattia Figlio", "categoria": "malattia",
     "limite_annuale_ore": 40, "limite_mensile_ore": None, "retribuito": False},
    
    # Formazione
    {"codice": "CFG", "descrizione": "Corso di Formazione", "categoria": "formazione",
     "limite_annuale_ore": None, "limite_mensile_ore": None, "retribuito": True},
    {"codice": "CFGA", "descrizione": "Corso di Formazione (Assenza)", "categoria": "formazione",
     "limite_annuale_ore": None, "limite_mensile_ore": None, "retribuito": False},
    
    # Altro
    {"codice": "SMART", "descrizione": "Smart Working", "categoria": "lavoro",
     "limite_annuale_ore": None, "limite_mensile_ore": None, "retribuito": True},
    {"codice": "TRAS", "descrizione": "Trasferta", "categoria": "lavoro",
     "limite_annuale_ore": None, "limite_mensile_ore": None, "retribuito": True},
    {"codice": "DON", "descrizione": "Donazione Sangue", "categoria": "permesso",
     "limite_annuale_ore": 32, "limite_mensile_ore": 8, "retribuito": True},  # 4 giorni
    {"codice": "L104", "descrizione": "Permesso Legge 104", "categoria": "permesso",
     "limite_annuale_ore": None, "limite_mensile_ore": 24, "retribuito": True},  # 3 giorni/mese
    {"codice": "STUD", "descrizione": "Permesso Studio", "categoria": "permesso",
     "limite_annuale_ore": 150, "limite_mensile_ore": None, "retribuito": True},
    {"codice": "SIN", "descrizione": "Permesso Sindacale", "categoria": "permesso",
     "limite_annuale_ore": None, "limite_mensile_ore": None, "retribuito": True},
    {"codice": "VIS", "descrizione": "Visita Medica", "categoria": "permesso",
     "limite_annuale_ore": None, "limite_mensile_ore": None, "retribuito": True},
]


# =============================================================================
# INIZIALIZZAZIONE GIUSTIFICATIVI
# =============================================================================

@router.post("/init-giustificativi")
@handle_errors
async def inizializza_giustificativi() -> Dict[str, Any]:
    """
    Inizializza la collection giustificativi con i codici standard.
    Da chiamare una volta per popolare il database.
    """
    db = Database.get_db()
    
    inseriti = 0
    aggiornati = 0
    
    for giust in GIUSTIFICATIVI_DEFAULT:
        existing = await db["giustificativi"].find_one({"codice": giust["codice"]})
        
        if existing:
            # Aggiorna se esiste
            await db["giustificativi"].update_one(
                {"codice": giust["codice"]},
                {"$set": {
                    **giust,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            aggiornati += 1
        else:
            # Inserisci nuovo
            await db["giustificativi"].insert_one({
                "id": str(uuid.uuid4()),
                **giust,
                "attivo": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            inseriti += 1
    
    logger.info(f"✅ Giustificativi inizializzati: {inseriti} nuovi, {aggiornati} aggiornati")
    
    return {
        "success": True,
        "inseriti": inseriti,
        "aggiornati": aggiornati,
        "totale": len(GIUSTIFICATIVI_DEFAULT)
    }


# =============================================================================
# CRUD GIUSTIFICATIVI
# =============================================================================

@router.get("/giustificativi")
@handle_errors
async def get_giustificativi(
    categoria: str = Query(None),
    attivo: bool = Query(True)
) -> Dict[str, Any]:
    """
    Lista tutti i giustificativi disponibili.
    """
    db = Database.get_db()
    
    query = {}
    if categoria:
        query["categoria"] = categoria
    if attivo is not None:
        query["attivo"] = attivo
    
    giustificativi = await db["giustificativi"].find(
        query, {"_id": 0}
    ).sort("codice", 1).to_list(100)
    
    # Se vuoto, inizializza
    if not giustificativi:
        await inizializza_giustificativi()
        giustificativi = await db["giustificativi"].find(
            query, {"_id": 0}
        ).sort("codice", 1).to_list(100)
    
    # Raggruppa per categoria
    per_categoria = {}
    for g in giustificativi:
        cat = g.get("categoria", "altro")
        if cat not in per_categoria:
            per_categoria[cat] = []
        per_categoria[cat].append(g)
    
    return {
        "success": True,
        "totale": len(giustificativi),
        "giustificativi": giustificativi,
        "per_categoria": per_categoria
    }


@router.put("/giustificativi/{codice}")
@handle_errors
async def update_giustificativo(codice: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggiorna un giustificativo (limiti, descrizione, etc).
    
    Payload:
    {
        "limite_annuale_ore": 200,
        "limite_mensile_ore": 20,
        "descrizione": "Nuova descrizione",
        "attivo": true
    }
    """
    db = Database.get_db()
    
    giust = await db["giustificativi"].find_one({"codice": codice.upper()})
    if not giust:
        raise HTTPException(status_code=404, detail=f"Giustificativo {codice} non trovato")
    
    update_fields = {}
    
    if "limite_annuale_ore" in payload:
        update_fields["limite_annuale_ore"] = payload["limite_annuale_ore"]
    if "limite_mensile_ore" in payload:
        update_fields["limite_mensile_ore"] = payload["limite_mensile_ore"]
    if "descrizione" in payload:
        update_fields["descrizione"] = payload["descrizione"]
    if "attivo" in payload:
        update_fields["attivo"] = payload["attivo"]
    if "retribuito" in payload:
        update_fields["retribuito"] = payload["retribuito"]
    
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db["giustificativi"].update_one(
        {"codice": codice.upper()},
        {"$set": update_fields}
    )
    
    return {
        "success": True,
        "codice": codice.upper(),
        "aggiornato": update_fields
    }


# =============================================================================
# CONTATORI GIUSTIFICATIVI PER DIPENDENTE
# =============================================================================

@router.get("/dipendente/{employee_id}/giustificativi")
@handle_errors
async def get_giustificativi_dipendente(
    employee_id: str,
    anno: int = Query(None)
) -> Dict[str, Any]:
    """
    Ritorna i contatori giustificativi per un dipendente.
    Include ore usate, limiti e saldo residuo.
    OTTIMIZZATO: Usa aggregazione invece di N query singole.
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Verifica dipendente
    employee = await db["employees"].find_one(
        {"id": employee_id},
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1}
    )
    if not employee:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # Recupera tutti i giustificativi
    giustificativi = await db["giustificativi"].find(
        {"attivo": True}, {"_id": 0}
    ).to_list(100)
    
    if not giustificativi:
        await inizializza_giustificativi()
        giustificativi = await db["giustificativi"].find(
            {"attivo": True}, {"_id": 0}
        ).to_list(100)
    
    # Recupera limiti personalizzati dipendente (se esistono)
    limiti_custom = await db["giustificativi_dipendente"].find_one(
        {"employee_id": employee_id, "anno": anno},
        {"_id": 0}
    )
    limiti_per_codice = limiti_custom.get("limiti", {}) if limiti_custom else {}
    
    # OTTIMIZZAZIONE: Carica tutte le ore usate in una sola query aggregata
    mese_corrente = datetime.now().month
    data_inizio_anno = f"{anno}-01-01"
    data_fine_anno = f"{anno+1}-01-01"
    data_inizio_mese = f"{anno}-{mese_corrente:02d}-01"
    data_fine_mese = f"{anno}-{mese_corrente+1:02d}-01" if mese_corrente < 12 else f"{anno+1}-01-01"
    
    # Aggregazione per presenze_mensili (anno)
    presenze_anno = await db["presenze_mensili"].aggregate([
        {"$match": {
            "employee_id": employee_id,
            "data": {"$gte": data_inizio_anno, "$lt": data_fine_anno}
        }},
        {"$group": {
            "_id": "$stato",
            "ore": {"$sum": {"$ifNull": ["$ore", 8]}}
        }}
    ]).to_list(100)
    
    # Aggregazione per presenze_mensili (mese corrente)
    presenze_mese = await db["presenze_mensili"].aggregate([
        {"$match": {
            "employee_id": employee_id,
            "data": {"$gte": data_inizio_mese, "$lt": data_fine_mese}
        }},
        {"$group": {
            "_id": "$stato",
            "ore": {"$sum": {"$ifNull": ["$ore", 8]}}
        }}
    ]).to_list(100)
    
    # Converti in dizionari per lookup veloce
    ore_anno_per_codice = {p["_id"]: p["ore"] for p in presenze_anno if p["_id"]}
    ore_mese_per_codice = {p["_id"]: p["ore"] for p in presenze_mese if p["_id"]}
    
    # Calcola risultati per ogni giustificativo
    risultato = []
    
    for giust in giustificativi:
        codice = giust["codice"]
        
        # Limiti (custom o default)
        limite_annuale = limiti_per_codice.get(codice, {}).get("limite_annuale_ore") or giust.get("limite_annuale_ore")
        limite_mensile = limiti_per_codice.get(codice, {}).get("limite_mensile_ore") or giust.get("limite_mensile_ore")
        
        # Ore usate (lookup veloce)
        ore_anno = ore_anno_per_codice.get(codice, 0) + ore_anno_per_codice.get(codice.lower(), 0)
        ore_mese = ore_mese_per_codice.get(codice, 0) + ore_mese_per_codice.get(codice.lower(), 0)
        
        # Calcola residui
        residuo_annuale = None
        residuo_mensile = None
        superato_annuale = False
        superato_mensile = False
        
        if limite_annuale is not None:
            residuo_annuale = limite_annuale - ore_anno
            superato_annuale = residuo_annuale < 0
        
        if limite_mensile is not None:
            residuo_mensile = limite_mensile - ore_mese
            superato_mensile = residuo_mensile < 0
        
        risultato.append({
            "codice": codice,
            "descrizione": giust.get("descrizione"),
            "categoria": giust.get("categoria"),
            "retribuito": giust.get("retribuito"),
            "limite_annuale_ore": limite_annuale,
            "limite_mensile_ore": limite_mensile,
            "ore_usate_anno": ore_anno,
            "ore_usate_mese": ore_mese,
            "residuo_annuale": residuo_annuale,
            "residuo_mensile": residuo_mensile,
            "superato_annuale": superato_annuale,
            "superato_mensile": superato_mensile,
            "custom_limits": codice in limiti_per_codice
        })
    
    # Raggruppa per categoria
    per_categoria = {}
    for r in risultato:
        cat = r.get("categoria", "altro")
        if cat not in per_categoria:
            per_categoria[cat] = []
        per_categoria[cat].append(r)
    
    return {
        "success": True,
        "employee_id": employee_id,
        "employee_nome": employee.get("nome_completo") or f"{employee.get('nome', '')} {employee.get('cognome', '')}",
        "anno": anno,
        "mese_corrente": mese_corrente,
        "giustificativi": risultato,
        "per_categoria": per_categoria,
        "totale_giustificativi": len(risultato)
    }


async def _calcola_ore_giustificativo(
    db, 
    employee_id: str, 
    codice_giustificativo: str, 
    anno: int, 
    mese: int = None
) -> float:
    """
    Calcola le ore usate per un giustificativo specifico.
    Cerca in: presenze_mensili, richieste_assenza, timbrature
    """
    ore_totali = 0.0
    
    # Query base per l'anno
    if mese:
        data_inizio = f"{anno}-{mese:02d}-01"
        if mese == 12:
            data_fine = f"{anno+1}-01-01"
        else:
            data_fine = f"{anno}-{mese+1:02d}-01"
    else:
        data_inizio = f"{anno}-01-01"
        data_fine = f"{anno+1}-01-01"
    
    # 1. Cerca in presenze_mensili (calendario)
    presenze = await db["presenze_mensili"].find({
        "employee_id": employee_id,
        "data": {"$gte": data_inizio, "$lt": data_fine},
        "stato": codice_giustificativo
    }).to_list(500)
    
    for p in presenze:
        ore_totali += float(p.get("ore", 8))  # Default 8 ore per giornata
    
    # 2. Cerca in richieste_assenza approvate
    richieste = await db["richieste_assenza"].find({
        "employee_id": employee_id,
        "tipo": {"$regex": codice_giustificativo, "$options": "i"},
        "stato": "approved",
        "data_inizio": {"$gte": data_inizio, "$lt": data_fine}
    }).to_list(500)
    
    for r in richieste:
        ore_totali += float(r.get("ore_totali", 0))
    
    return ore_totali


@router.put("/dipendente/{employee_id}/giustificativi/limiti")
@handle_errors
async def set_limiti_custom_dipendente(
    employee_id: str,
    payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Imposta limiti personalizzati per un dipendente.
    
    Payload:
    {
        "anno": 2026,
        "limiti": {
            "FER": {"limite_annuale_ore": 240},
            "PER": {"limite_annuale_ore": 40, "limite_mensile_ore": 10}
        }
    }
    """
    db = Database.get_db()
    
    anno = payload.get("anno", datetime.now().year)
    limiti = payload.get("limiti", {})
    
    # Verifica dipendente
    employee = await db["employees"].find_one({"id": employee_id}, {"_id": 0, "id": 1})
    if not employee:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # Upsert limiti custom
    await db["giustificativi_dipendente"].update_one(
        {"employee_id": employee_id, "anno": anno},
        {"$set": {
            "employee_id": employee_id,
            "anno": anno,
            "limiti": limiti,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    return {
        "success": True,
        "employee_id": employee_id,
        "anno": anno,
        "limiti_impostati": len(limiti)
    }


# =============================================================================
# VALIDAZIONE GIUSTIFICATIVO
# =============================================================================

@router.post("/valida-giustificativo")
@handle_errors
async def valida_giustificativo(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida se è possibile inserire un giustificativo per un dipendente.
    Verifica i limiti annuali e mensili.
    
    Payload:
    {
        "employee_id": "uuid",
        "codice_giustificativo": "FER",
        "data": "2026-01-22",
        "ore": 8
    }
    
    Returns:
    {
        "valido": true/false,
        "messaggio": "...",
        "dettagli": {...}
    }
    """
    db = Database.get_db()
    
    employee_id = payload.get("employee_id")
    codice = payload.get("codice_giustificativo", "").upper()
    data = payload.get("data")
    ore_richieste = float(payload.get("ore", 8))
    
    if not employee_id or not codice:
        raise HTTPException(status_code=400, detail="employee_id e codice_giustificativo obbligatori")
    
    # Estrai anno e mese dalla data
    try:
        dt = datetime.fromisoformat(data) if data else datetime.now()
        anno = dt.year
        mese = dt.month
    except Exception:
        anno = datetime.now().year
        mese = datetime.now().month
    
    # Recupera giustificativo
    giust = await db["giustificativi"].find_one({"codice": codice}, {"_id": 0})
    if not giust:
        return {
            "valido": False,
            "messaggio": f"Giustificativo {codice} non trovato",
            "bloccante": True
        }
    
    # Recupera limiti custom
    limiti_custom = await db["giustificativi_dipendente"].find_one(
        {"employee_id": employee_id, "anno": anno},
        {"_id": 0}
    )
    limiti_per_codice = limiti_custom.get("limiti", {}) if limiti_custom else {}
    
    # Determina limiti applicabili
    limite_annuale = limiti_per_codice.get(codice, {}).get("limite_annuale_ore") or giust.get("limite_annuale_ore")
    limite_mensile = limiti_per_codice.get(codice, {}).get("limite_mensile_ore") or giust.get("limite_mensile_ore")
    
    # Calcola ore già usate
    ore_anno = await _calcola_ore_giustificativo(db, employee_id, codice, anno)
    ore_mese = await _calcola_ore_giustificativo(db, employee_id, codice, anno, mese)
    
    # Valida
    errori = []
    warnings = []
    
    if limite_annuale is not None:
        ore_dopo = ore_anno + ore_richieste
        if ore_dopo > limite_annuale:
            errori.append({
                "tipo": "limite_annuale_superato",
                "messaggio": f"Limite annuale superato: {ore_anno:.1f}h usate + {ore_richieste:.1f}h = {ore_dopo:.1f}h > {limite_annuale:.1f}h",
                "ore_disponibili": max(0, limite_annuale - ore_anno)
            })
        elif ore_dopo > limite_annuale * 0.9:
            warnings.append(f"Attenzione: quasi al limite annuale ({ore_dopo:.1f}h / {limite_annuale:.1f}h)")
    
    if limite_mensile is not None:
        ore_dopo_mese = ore_mese + ore_richieste
        if ore_dopo_mese > limite_mensile:
            errori.append({
                "tipo": "limite_mensile_superato",
                "messaggio": f"Limite mensile superato: {ore_mese:.1f}h usate + {ore_richieste:.1f}h = {ore_dopo_mese:.1f}h > {limite_mensile:.1f}h",
                "ore_disponibili": max(0, limite_mensile - ore_mese)
            })
        elif ore_dopo_mese > limite_mensile * 0.9:
            warnings.append(f"Attenzione: quasi al limite mensile ({ore_dopo_mese:.1f}h / {limite_mensile:.1f}h)")
    
    valido = len(errori) == 0
    
    return {
        "valido": valido,
        "bloccante": not valido,
        "messaggio": errori[0]["messaggio"] if errori else "OK",
        "errori": errori,
        "warnings": warnings,
        "dettagli": {
            "codice": codice,
            "descrizione": giust.get("descrizione"),
            "ore_richieste": ore_richieste,
            "ore_anno_attuali": ore_anno,
            "ore_mese_attuali": ore_mese,
            "limite_annuale": limite_annuale,
            "limite_mensile": limite_mensile
        }
    }


# =============================================================================
# SALDO FERIE E PERMESSI
# =============================================================================

@router.get("/dipendente/{employee_id}/saldo-ferie")
@handle_errors
async def get_saldo_ferie_dipendente(
    employee_id: str,
    anno: int = Query(None)
) -> Dict[str, Any]:
    """
    Calcola il saldo ferie e permessi per un dipendente.
    
    Include:
    - Ferie maturate/godute/residue
    - ROL maturati/goduti/residui
    - Ex-festività
    - Permessi vari
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    mese_corrente = datetime.now().month if anno == datetime.now().year else 12
    
    # Verifica dipendente
    employee = await db["employees"].find_one(
        {"id": employee_id},
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1, 
         "data_assunzione": 1, "ore_settimanali": 1}
    )
    if not employee:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # Parametri contrattuali (default CCNL Commercio)
    ore_settimanali = float(employee.get("ore_settimanali", 40))
    giorni_ferie_annuali = 26  # Giorni
    ore_ferie_annuali = giorni_ferie_annuali * 8  # 208 ore
    ore_rol_annuali = 72  # Ore
    ore_ex_festivita_annuali = 32  # 4 giorni * 8 ore
    
    # Calcola maturato (proporzionale ai mesi lavorati)
    # TODO: Verificare data assunzione per primo anno
    ferie_maturate = (ore_ferie_annuali / 12) * mese_corrente
    rol_maturati = (ore_rol_annuali / 12) * mese_corrente
    exf_maturati = (ore_ex_festivita_annuali / 12) * mese_corrente
    
    # Calcola godute
    ferie_godute = await _calcola_ore_giustificativo(db, employee_id, "FER", anno)
    rol_goduti = await _calcola_ore_giustificativo(db, employee_id, "ROL", anno)
    exf_godute = await _calcola_ore_giustificativo(db, employee_id, "EXF", anno)
    permessi_goduti = await _calcola_ore_giustificativo(db, employee_id, "PER", anno)
    
    # Recupera anno precedente per riporto
    ferie_anno_prec = await _calcola_ore_giustificativo(db, employee_id, "FER", anno - 1)
    rol_anno_prec = await _calcola_ore_giustificativo(db, employee_id, "ROL", anno - 1)
    
    # Calcola riporto (ferie non godute anno precedente)
    # Semplificato: assumiamo che il riporto sia già calcolato
    riporto_ferie = await db["riporti_ferie"].find_one(
        {"employee_id": employee_id, "anno": anno},
        {"_id": 0}
    )
    ferie_riportate = float(riporto_ferie.get("ferie_riportate", 0)) if riporto_ferie else 0
    rol_riportati = float(riporto_ferie.get("rol_riportati", 0)) if riporto_ferie else 0
    
    # Calcola residui
    ferie_totali = ferie_maturate + ferie_riportate
    rol_totali = rol_maturati + rol_riportati
    exf_totali = exf_maturati
    
    ferie_residue = ferie_totali - ferie_godute
    rol_residui = rol_totali - rol_goduti
    exf_residue = exf_totali - exf_godute
    
    # Dettaglio mensile
    dettaglio_mensile = []
    for m in range(1, mese_corrente + 1):
        ferie_mese = await _calcola_ore_giustificativo(db, employee_id, "FER", anno, m)
        rol_mese = await _calcola_ore_giustificativo(db, employee_id, "ROL", anno, m)
        
        dettaglio_mensile.append({
            "mese": m,
            "ferie_godute": ferie_mese,
            "rol_goduti": rol_mese,
            "ferie_maturate": ore_ferie_annuali / 12,
            "rol_maturati": ore_rol_annuali / 12
        })
    
    return {
        "success": True,
        "employee_id": employee_id,
        "employee_nome": employee.get("nome_completo") or f"{employee.get('nome', '')} {employee.get('cognome', '')}",
        "anno": anno,
        "mese_corrente": mese_corrente,
        
        "ferie": {
            "spettanti_annue": ore_ferie_annuali,
            "maturate": round(ferie_maturate, 1),
            "riportate_anno_prec": ferie_riportate,
            "totali_disponibili": round(ferie_totali, 1),
            "godute": ferie_godute,
            "residue": round(ferie_residue, 1),
            "giorni_residui": round(ferie_residue / 8, 1)
        },
        
        "rol": {
            "spettanti_annui": ore_rol_annuali,
            "maturati": round(rol_maturati, 1),
            "riportati_anno_prec": rol_riportati,
            "totali_disponibili": round(rol_totali, 1),
            "goduti": rol_goduti,
            "residui": round(rol_residui, 1)
        },
        
        "ex_festivita": {
            "spettanti_annue": ore_ex_festivita_annuali,
            "maturate": round(exf_maturati, 1),
            "godute": exf_godute,
            "residue": round(exf_residue, 1)
        },
        
        "permessi": {
            "goduti_anno": permessi_goduti
        },
        
        "dettaglio_mensile": dettaglio_mensile
    }


@router.post("/dipendente/{employee_id}/riporto-ferie")
@handle_errors
async def set_riporto_ferie(
    employee_id: str,
    payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Imposta il riporto ferie/ROL da anno precedente.
    
    Payload:
    {
        "anno": 2026,
        "ferie_riportate": 24,
        "rol_riportati": 16
    }
    """
    db = Database.get_db()
    
    anno = payload.get("anno", datetime.now().year)
    ferie = float(payload.get("ferie_riportate", 0))
    rol = float(payload.get("rol_riportati", 0))
    
    await db["riporti_ferie"].update_one(
        {"employee_id": employee_id, "anno": anno},
        {"$set": {
            "employee_id": employee_id,
            "anno": anno,
            "ferie_riportate": ferie,
            "rol_riportati": rol,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    
    return {
        "success": True,
        "employee_id": employee_id,
        "anno": anno,
        "ferie_riportate": ferie,
        "rol_riportati": rol
    }


# =============================================================================
# NOTIFICHE LIMITI GIUSTIFICATIVI
# =============================================================================

@router.get("/alert-limiti")
@handle_errors
async def get_alert_limiti_giustificativi(
    soglia_percentuale: float = Query(90, description="Soglia % per generare alert (default 90%)"),
    anno: int = Query(None)
) -> Dict[str, Any]:
    """
    Ritorna gli alert per dipendenti vicini al limite dei giustificativi.
    
    Verifica:
    - Dipendenti che hanno usato >= soglia_percentuale del limite annuale
    - Dipendenti che hanno usato >= soglia_percentuale del limite mensile
    
    Returns:
    {
        "alerts": [
            {
                "employee_id": "...",
                "employee_nome": "Mario Rossi",
                "codice": "FER",
                "descrizione": "Ferie",
                "tipo_limite": "annuale",
                "ore_usate": 187,
                "limite": 208,
                "percentuale": 89.9,
                "ore_residue": 21,
                "livello": "warning" | "critical"
            }
        ],
        "totale_alerts": 5,
        "dipendenti_coinvolti": 3
    }
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    mese_corrente = datetime.now().month
    
    # Recupera tutti i dipendenti in carico
    dipendenti = await db["employees"].find(
        {"$or": [{"in_carico": True}, {"in_carico": {"$exists": False}}]},
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1}
    ).to_list(500)
    
    # Recupera giustificativi con limiti
    giustificativi = await db["giustificativi"].find(
        {"attivo": True, "$or": [
            {"limite_annuale_ore": {"$ne": None, "$gt": 0}},
            {"limite_mensile_ore": {"$ne": None, "$gt": 0}}
        ]},
        {"_id": 0}
    ).to_list(100)
    
    if not giustificativi:
        return {"alerts": [], "totale_alerts": 0, "dipendenti_coinvolti": 0}
    
    # Date per query
    data_inizio_anno = f"{anno}-01-01"
    data_fine_anno = f"{anno+1}-01-01"
    data_inizio_mese = f"{anno}-{mese_corrente:02d}-01"
    data_fine_mese = f"{anno}-{mese_corrente+1:02d}-01" if mese_corrente < 12 else f"{anno+1}-01-01"
    
    alerts = []
    dipendenti_set = set()
    
    for dip in dipendenti:
        emp_id = dip.get("id")
        if not emp_id:
            continue
        
        nome = dip.get("nome_completo") or f"{dip.get('nome', '')} {dip.get('cognome', '')}".strip()
        
        # Recupera limiti custom per questo dipendente
        limiti_custom = await db["giustificativi_dipendente"].find_one(
            {"employee_id": emp_id, "anno": anno},
            {"_id": 0, "limiti": 1}
        )
        limiti_per_codice = limiti_custom.get("limiti", {}) if limiti_custom else {}
        
        # Aggregazione ore anno per tutti i codici
        presenze_anno = await db["presenze_mensili"].aggregate([
            {"$match": {
                "employee_id": emp_id,
                "data": {"$gte": data_inizio_anno, "$lt": data_fine_anno}
            }},
            {"$group": {"_id": "$stato", "ore": {"$sum": {"$ifNull": ["$ore", 8]}}}}
        ]).to_list(100)
        
        # Aggregazione ore mese corrente
        presenze_mese = await db["presenze_mensili"].aggregate([
            {"$match": {
                "employee_id": emp_id,
                "data": {"$gte": data_inizio_mese, "$lt": data_fine_mese}
            }},
            {"$group": {"_id": "$stato", "ore": {"$sum": {"$ifNull": ["$ore", 8]}}}}
        ]).to_list(100)
        
        ore_anno = {p["_id"]: p["ore"] for p in presenze_anno if p["_id"]}
        ore_mese = {p["_id"]: p["ore"] for p in presenze_mese if p["_id"]}
        
        for giust in giustificativi:
            codice = giust["codice"]
            
            # Determina limiti (custom o default)
            limite_annuale = limiti_per_codice.get(codice, {}).get("limite_annuale_ore") or giust.get("limite_annuale_ore")
            limite_mensile = limiti_per_codice.get(codice, {}).get("limite_mensile_ore") or giust.get("limite_mensile_ore")
            
            ore_usate_anno = ore_anno.get(codice, 0) + ore_anno.get(codice.lower(), 0)
            ore_usate_mese = ore_mese.get(codice, 0) + ore_mese.get(codice.lower(), 0)
            
            # Verifica limite annuale
            if limite_annuale and limite_annuale > 0 and ore_usate_anno > 0:
                percentuale = (ore_usate_anno / limite_annuale) * 100
                if percentuale >= soglia_percentuale:
                    livello = "critical" if percentuale >= 100 else "warning"
                    alerts.append({
                        "employee_id": emp_id,
                        "employee_nome": nome,
                        "codice": codice,
                        "descrizione": giust.get("descrizione"),
                        "categoria": giust.get("categoria"),
                        "tipo_limite": "annuale",
                        "ore_usate": round(ore_usate_anno, 1),
                        "limite": limite_annuale,
                        "percentuale": round(percentuale, 1),
                        "ore_residue": round(max(0, limite_annuale - ore_usate_anno), 1),
                        "livello": livello,
                        "anno": anno
                    })
                    dipendenti_set.add(emp_id)
            
            # Verifica limite mensile
            if limite_mensile and limite_mensile > 0 and ore_usate_mese > 0:
                percentuale = (ore_usate_mese / limite_mensile) * 100
                if percentuale >= soglia_percentuale:
                    livello = "critical" if percentuale >= 100 else "warning"
                    alerts.append({
                        "employee_id": emp_id,
                        "employee_nome": nome,
                        "codice": codice,
                        "descrizione": giust.get("descrizione"),
                        "categoria": giust.get("categoria"),
                        "tipo_limite": "mensile",
                        "ore_usate": round(ore_usate_mese, 1),
                        "limite": limite_mensile,
                        "percentuale": round(percentuale, 1),
                        "ore_residue": round(max(0, limite_mensile - ore_usate_mese), 1),
                        "livello": livello,
                        "anno": anno,
                        "mese": mese_corrente
                    })
                    dipendenti_set.add(emp_id)
    
    # Ordina: critical prima, poi per percentuale decrescente
    alerts.sort(key=lambda x: (0 if x["livello"] == "critical" else 1, -x["percentuale"]))
    
    return {
        "success": True,
        "alerts": alerts,
        "totale_alerts": len(alerts),
        "dipendenti_coinvolti": len(dipendenti_set),
        "soglia_percentuale": soglia_percentuale,
        "anno": anno,
        "mese_corrente": mese_corrente
    }


@router.get("/riepilogo-limiti")
@handle_errors
async def get_riepilogo_limiti(anno: int = Query(None)) -> Dict[str, Any]:
    """
    Ritorna un riepilogo compatto dei limiti per tutti i dipendenti.
    Utile per la dashboard.
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Conta dipendenti attivi
    totale_dipendenti = await db["employees"].count_documents(
        {"$or": [{"in_carico": True}, {"in_carico": {"$exists": False}}]}
    )
    
    # Recupera alert (soglia 80% per avere anche quelli vicini)
    alert_data = await get_alert_limiti_giustificativi(soglia_percentuale=80, anno=anno)
    
    # Separa per livello
    critical = [a for a in alert_data["alerts"] if a["livello"] == "critical"]
    warning = [a for a in alert_data["alerts"] if a["livello"] == "warning"]
    
    # Raggruppa per tipo giustificativo
    per_giustificativo = {}
    for a in alert_data["alerts"]:
        codice = a["codice"]
        if codice not in per_giustificativo:
            per_giustificativo[codice] = {
                "codice": codice,
                "descrizione": a["descrizione"],
                "critical": 0,
                "warning": 0
            }
        if a["livello"] == "critical":
            per_giustificativo[codice]["critical"] += 1
        else:
            per_giustificativo[codice]["warning"] += 1
    
    return {
        "success": True,
        "anno": anno,
        "totale_dipendenti": totale_dipendenti,
        "dipendenti_con_alert": alert_data["dipendenti_coinvolti"],
        "totale_critical": len(critical),
        "totale_warning": len(warning),
        "per_giustificativo": list(per_giustificativo.values()),
        "top_critical": critical[:5],
        "top_warning": warning[:5]
    }


# =============================================================================
# UPLOAD E PARSING PDF BUSTE PAGA PER GIUSTIFICATIVI
# =============================================================================

@router.post("/upload-libro-unico")
@handle_errors
async def upload_libro_unico_pdf(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Upload PDF del Libro Unico del Lavoro per estrarre e aggiornare i giustificativi.
    
    Supporta:
    - PDF singolo (Libro Unico)
    - ZIP con multipli PDF
    
    Estrae per ogni dipendente:
    - Ore ferie godute (FE -> FER)
    - Ore ROL utilizzate (RL -> ROL)
    - Ore malattia (MA -> MAL)
    - Ore permesso (PE -> PER)
    - Altri giustificativi
    
    I dati vengono salvati nella collection `presenze_mensili` per essere
    visualizzati correttamente nel tab Giustificativi.
    """
    from app.parsers.payslip_giustificativi_parser import parse_libro_unico_pdf
    
    filename = (file.filename or "").lower()
    if not (filename.endswith('.pdf') or filename.endswith('.zip')):
        raise HTTPException(status_code=400, detail="Il file deve essere PDF o ZIP")
    
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="File vuoto")
        
        pdf_files = []
        tmp_dir = None
        
        if filename.endswith('.pdf'):
            pdf_files = [(content, file.filename or "libro_unico.pdf")]
        else:
            # Estrai da ZIP
            import zipfile
            tmp_dir = tempfile.TemporaryDirectory()
            archive_path = os.path.join(tmp_dir.name, file.filename or 'archivio.zip')
            with open(archive_path, 'wb') as f:
                f.write(content)
            
            with zipfile.ZipFile(archive_path) as zf:
                for name in zf.namelist():
                    if name.lower().endswith('.pdf') and 'libro unico' in name.lower():
                        pdf_data = zf.read(name)
                        pdf_files.append((pdf_data, name))
        
        if not pdf_files:
            raise HTTPException(status_code=400, detail="Nessun PDF 'Libro Unico' trovato")
        
        db = Database.get_db()
        results = {
            "success": [],
            "errors": [],
            "total_pdf": len(pdf_files),
            "dipendenti_processati": 0,
            "giustificativi_aggiornati": 0
        }
        
        for pdf_bytes, pdf_filename in pdf_files:
            try:
                dipendenti = parse_libro_unico_pdf(pdf_bytes)
                
                for dip in dipendenti:
                    if dip.get("error"):
                        results["errors"].append({"file": pdf_filename, "error": dip["error"]})
                        continue
                    
                    cf = dip.get("codice_fiscale")
                    nome = dip.get("nome_completo")
                    mese = dip.get("mese")
                    anno = dip.get("anno")
                    giustificativi = dip.get("giustificativi", {})
                    
                    if not (nome or cf) or not mese or not anno:
                        continue
                    
                    # Trova dipendente nel database
                    employee = None
                    if cf:
                        employee = await db["employees"].find_one(
                            {"codice_fiscale": cf},
                            {"_id": 0, "id": 1, "nome_completo": 1}
                        )
                    
                    if not employee and nome:
                        # Cerca per nome
                        nome_upper = nome.upper().strip()
                        all_emps = await db["employees"].find({}, {"_id": 0, "id": 1, "nome_completo": 1, "cognome": 1, "nome": 1}).to_list(500)
                        for emp in all_emps:
                            emp_nome = (emp.get("nome_completo") or f"{emp.get('cognome', '')} {emp.get('nome', '')}").upper().strip()
                            if emp_nome == nome_upper or nome_upper in emp_nome:
                                employee = emp
                                break
                    
                    if not employee:
                        results["errors"].append({
                            "file": pdf_filename,
                            "nome": nome,
                            "error": "Dipendente non trovato in anagrafica"
                        })
                        continue
                    
                    employee_id = employee.get("id")
                    results["dipendenti_processati"] += 1
                    
                    # Salva giustificativi in presenze_mensili
                    for codice, ore in giustificativi.items():
                        if codice == 'ORE_ORDINARIE' or ore <= 0:
                            continue
                        
                        # Calcola giorni approssimativi (8 ore = 1 giorno)
                        giorni = ore / 8
                        
                        # Crea/aggiorna record in presenze_mensili
                        # Un record per ogni giorno del mese con quel giustificativo
                        data_base = f"{anno}-{mese:02d}"
                        
                        # Cerca se esiste già un record aggregato per questo mese
                        existing = await db["presenze_mensili"].find_one({
                            "employee_id": employee_id,
                            "stato": codice,
                            "data": {"$regex": f"^{data_base}"}
                        })
                        
                        if existing:
                            # Aggiorna ore totali
                            await db["presenze_mensili"].update_one(
                                {"_id": existing["_id"]},
                                {"$set": {
                                    "ore": ore,
                                    "updated_at": datetime.now(timezone.utc).isoformat(),
                                    "source": "libro_unico_pdf"
                                }}
                            )
                        else:
                            # Crea nuovo record aggregato
                            await db["presenze_mensili"].insert_one({
                                "id": str(uuid.uuid4()),
                                "employee_id": employee_id,
                                "data": f"{data_base}-01",  # Primo del mese come riferimento
                                "stato": codice,
                                "ore": ore,
                                "giorni": round(giorni, 1),
                                "note": f"Importato da {pdf_filename}",
                                "source": "libro_unico_pdf",
                                "created_at": datetime.now(timezone.utc).isoformat()
                            })
                        
                        results["giustificativi_aggiornati"] += 1
                    
                    # NUOVO: Salva saldi finali nella collection dedicata
                    # Filtra solo i saldi residui (FER, ROL, EXF, PER)
                    saldi_finali = {k: v for k, v in giustificativi.items() 
                                   if k in ['FER', 'ROL', 'EXF', 'PER'] and v > 0}
                    
                    if saldi_finali:
                        periodo = f"{anno}-{mese:02d}"
                        now = datetime.now(timezone.utc).isoformat()
                        
                        # Verifica se esiste già un record per questo anno
                        existing_saldo = await db["giustificativi_saldi_finali"].find_one(
                            {"employee_id": employee_id, "anno": anno}
                        )
                        
                        # Aggiorna solo se il nuovo periodo è >= al periodo esistente
                        should_update = True
                        if existing_saldo:
                            existing_periodo = existing_saldo.get("periodo", "")
                            if periodo < existing_periodo:
                                should_update = False
                        
                        if should_update:
                            await db["giustificativi_saldi_finali"].update_one(
                                {"employee_id": employee_id, "anno": anno},
                                {
                                    "$set": {
                                        "employee_id": employee_id,
                                        "anno": anno,
                                        "periodo": periodo,
                                        "saldi": saldi_finali,
                                        "source": "libro_unico_pdf",
                                        "updated_at": now
                                    },
                                    "$setOnInsert": {
                                        "id": str(uuid.uuid4()),
                                        "created_at": now
                                    },
                                    "$push": {
                                        "storico": {
                                            "periodo": periodo,
                                            "saldi": saldi_finali,
                                            "source": "libro_unico_pdf",
                                            "data": now
                                        }
                                    }
                                },
                                upsert=True
                            )
                    
                    results["success"].append({
                        "nome": nome,
                        "periodo": f"{mese:02d}/{anno}",
                        "giustificativi": giustificativi,
                        "saldi_finali_salvati": bool(saldi_finali)
                    })
            
            except Exception as e:
                logger.error(f"Errore parsing {pdf_filename}: {e}")
                results["errors"].append({"file": pdf_filename, "error": str(e)})
        
        if tmp_dir:
            try:
                tmp_dir.cleanup()
            except Exception:
                pass
        
        return {
            "success": True,
            **results
        }
    
    except Exception as e:
        logger.error(f"Errore upload Libro Unico: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-giustificativi-da-cedolini")
@handle_errors
async def sync_giustificativi_da_cedolini(
    anno: int = Query(None),
    mese: int = Query(None)
) -> Dict[str, Any]:
    """
    Sincronizza i giustificativi dai cedolini già presenti nel database.
    
    Cerca nei cedolini salvati eventuali dati sui giustificativi
    e li copia nella collection presenze_mensili.
    """
    db = Database.get_db()
    
    query = {}
    if anno:
        query["anno"] = anno
    if mese:
        query["mese"] = mese
    
    cedolini = await db["cedolini"].find(query, {"_id": 0}).to_list(10000)
    
    risultato = {
        "cedolini_analizzati": len(cedolini),
        "giustificativi_trovati": 0,
        "aggiornati": 0
    }
    
    for ced in cedolini:
        # Verifica se il cedolino ha giustificativi
        giust = ced.get("giustificativi", {})
        if not giust:
            continue
        
        employee_id = ced.get("dipendente_id")
        mese_ced = ced.get("mese")
        anno_ced = ced.get("anno")
        
        if not employee_id or not mese_ced or not anno_ced:
            continue
        
        data_base = f"{anno_ced}-{mese_ced:02d}"
        
        for codice, ore in giust.items():
            if ore <= 0:
                continue
            
            risultato["giustificativi_trovati"] += 1
            
            # Upsert in presenze_mensili
            await db["presenze_mensili"].update_one(
                {
                    "employee_id": employee_id,
                    "stato": codice,
                    "data": {"$regex": f"^{data_base}"}
                },
                {
                    "$set": {
                        "ore": ore,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "source": "cedolino_sync"
                    },
                    "$setOnInsert": {
                        "id": str(uuid.uuid4()),
                        "employee_id": employee_id,
                        "data": f"{data_base}-01",
                        "stato": codice,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                },
                upsert=True
            )
            risultato["aggiornati"] += 1
    
    return {
        "success": True,
        **risultato
    }


@router.get("/presenze-mensili/{employee_id}")
@handle_errors
async def get_presenze_mensili_dipendente(
    employee_id: str,
    anno: int = Query(None),
    mese: int = Query(None)
) -> Dict[str, Any]:
    """
    Ritorna le presenze mensili (giustificativi) per un dipendente.
    Utile per debugging e verifica dati.
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    query = {"employee_id": employee_id}
    
    if mese:
        data_pattern = f"{anno}-{mese:02d}"
        query["data"] = {"$regex": f"^{data_pattern}"}
    else:
        query["data"] = {"$regex": f"^{anno}"}
    
    presenze = await db["presenze_mensili"].find(
        query,
        {"_id": 0}
    ).sort("data", 1).to_list(500)
    
    # Raggruppa per mese e stato
    per_mese = {}
    for p in presenze:
        data = p.get("data", "")[:7]  # YYYY-MM
        stato = p.get("stato", "")
        ore = p.get("ore", 0)
        
        if data not in per_mese:
            per_mese[data] = {}
        
        per_mese[data][stato] = per_mese[data].get(stato, 0) + ore
    
    return {
        "success": True,
        "employee_id": employee_id,
        "anno": anno,
        "mese": mese,
        "totale_record": len(presenze),
        "presenze": presenze,
        "riepilogo_per_mese": per_mese
    }



# =============================================================================
# FOGLIO DATI PROGRESSIVO - RIEPILOGO FINALE GIUSTIFICATIVI
# =============================================================================
# Logica: quando si caricano buste paga, il sistema:
# 1. Salva i dati estratti in "presenze_mensili" per ogni mese
# 2. Aggiorna "giustificativi_saldi_finali" con l'ultimo periodo letto
# 3. Il riepilogo usa sempre i saldi finali dell'ultimo periodo per il calcolo
# =============================================================================

@router.get("/riepilogo-progressivo/{employee_id}")
@handle_errors
async def get_riepilogo_progressivo(
    employee_id: str,
    anno: int = Query(None)
) -> Dict[str, Any]:
    """
    Ritorna il riepilogo progressivo dei giustificativi per un dipendente.
    
    Questo "foglio dati" mostra:
    - Ultimo periodo letto (es. 12/2025)
    - Saldi finali basati sull'ultimo parsing
    - Storico delle letture per mese
    
    LOGICA: Se carichi busta 12/2025, poi 01/2021, il sistema usa
    12/2025 come riferimento per i saldi attuali (è il dato più recente).
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Verifica dipendente
    employee = await db["employees"].find_one(
        {"id": employee_id},
        {"_id": 0, "id": 1, "nome_completo": 1, "nome": 1, "cognome": 1}
    )
    if not employee:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # PRIORITÀ 1: Cerca saldi finali salvati nella collection dedicata
    saldo_finale = await db["giustificativi_saldi_finali"].find_one(
        {"employee_id": employee_id, "anno": anno},
        {"_id": 0}
    )
    
    if saldo_finale:
        # Usa i saldi finali salvati (più affidabili)
        return {
            "success": True,
            "employee_id": employee_id,
            "employee_nome": employee.get("nome_completo") or f"{employee.get('cognome', '')} {employee.get('nome', '')}",
            "anno": anno,
            "ultimo_periodo_letto": saldo_finale.get("periodo"),
            "saldi_ultimo_periodo": saldo_finale.get("saldi", {}),
            "data_aggiornamento": saldo_finale.get("updated_at"),
            "source": saldo_finale.get("source", "libro_unico"),
            "note": "Saldi da collection giustificativi_saldi_finali (dato più recente importato)"
        }
    
    # PRIORITÀ 2: Calcola da presenze_mensili (fallback)
    presenze = await db["presenze_mensili"].find(
        {
            "employee_id": employee_id,
            "data": {"$regex": f"^{anno}"}
        },
        {"_id": 0}
    ).sort("data", -1).to_list(500)
    
    # Trova l'ultimo mese con dati (periodo più recente letto)
    ultimo_periodo = None
    
    for p in presenze:
        data_str = p.get("data", "")[:7]  # YYYY-MM
        if not ultimo_periodo or data_str > ultimo_periodo:
            ultimo_periodo = data_str
    
    # Calcola saldi basati sull'ultimo periodo
    saldi_ultimo_periodo = {}
    for p in presenze:
        data_str = p.get("data", "")[:7]
        if data_str == ultimo_periodo:
            codice = p.get("stato", "")
            ore = p.get("ore", 0)
            saldi_ultimo_periodo[codice] = saldi_ultimo_periodo.get(codice, 0) + ore
    
    # Raggruppa storico per mese
    storico_mesi = {}
    for p in presenze:
        data_str = p.get("data", "")[:7]
        if data_str not in storico_mesi:
            storico_mesi[data_str] = {
                "mese": data_str,
                "giustificativi": {},
                "data_parsing": p.get("created_at"),
                "source": p.get("source")
            }
        
        codice = p.get("stato", "")
        ore = p.get("ore", 0)
        storico_mesi[data_str]["giustificativi"][codice] = ore
    
    # Ordina storico per mese (descending)
    storico_ordinato = sorted(
        storico_mesi.values(),
        key=lambda x: x["mese"],
        reverse=True
    )
    
    # Calcola totali annuali (somma tutti i mesi)
    totali_anno = {}
    for mese_data in storico_mesi.values():
        for codice, ore in mese_data["giustificativi"].items():
            totali_anno[codice] = totali_anno.get(codice, 0) + ore
    
    return {
        "success": True,
        "employee_id": employee_id,
        "employee_nome": employee.get("nome_completo") or f"{employee.get('cognome', '')} {employee.get('nome', '')}",
        "anno": anno,
        "ultimo_periodo_letto": ultimo_periodo,
        "saldi_ultimo_periodo": saldi_ultimo_periodo,
        "totali_anno": totali_anno,
        "storico_mesi": storico_ordinato,
        "note": "Saldi calcolati da presenze_mensili (ultimo periodo disponibile)"
    }


@router.post("/salva-saldi-finali")
@handle_errors
async def salva_saldi_finali(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Salva i saldi finali di ferie/permessi per un dipendente.
    
    Questa è la collection di riferimento per i saldi correnti.
    Viene aggiornata automaticamente quando si carica un Libro Unico,
    o manualmente dall'utente.
    
    Payload:
    {
        "employee_id": "uuid",
        "anno": 2025,
        "periodo": "2025-12",  // Mese a cui si riferiscono i saldi
        "saldi": {
            "FER": 120,      // Ore ferie residue
            "ROL": 40,       // Ore ROL residue
            "EXF": 16,       // Ore ex-festività residue
            "PER": 8         // Ore permessi residui
        },
        "source": "libro_unico" | "manual" | "cedolino"
    }
    """
    db = Database.get_db()
    
    employee_id = payload.get("employee_id")
    anno = payload.get("anno", datetime.now().year)
    periodo = payload.get("periodo", f"{anno}-{datetime.now().month:02d}")
    saldi = payload.get("saldi", {})
    source = payload.get("source", "manual")
    
    if not employee_id:
        raise HTTPException(status_code=400, detail="employee_id obbligatorio")
    
    # Verifica dipendente
    employee = await db["employees"].find_one({"id": employee_id}, {"_id": 0, "id": 1})
    if not employee:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # Verifica se esiste già un record per questo anno
    existing = await db["giustificativi_saldi_finali"].find_one(
        {"employee_id": employee_id, "anno": anno}
    )
    
    # Determina se aggiornare in base al periodo
    # Aggiorna solo se il nuovo periodo è >= al periodo esistente
    should_update = True
    if existing:
        existing_periodo = existing.get("periodo", "")
        if periodo < existing_periodo:
            # Il nuovo periodo è più vecchio, non aggiornare i saldi principali
            # ma salva nello storico
            should_update = False
    
    now = datetime.now(timezone.utc).isoformat()
    
    if should_update:
        # Upsert del saldo principale
        await db["giustificativi_saldi_finali"].update_one(
            {"employee_id": employee_id, "anno": anno},
            {
                "$set": {
                    "employee_id": employee_id,
                    "anno": anno,
                    "periodo": periodo,
                    "saldi": saldi,
                    "source": source,
                    "updated_at": now
                },
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "created_at": now
                },
                "$push": {
                    "storico": {
                        "periodo": periodo,
                        "saldi": saldi,
                        "source": source,
                        "data": now
                    }
                }
            },
            upsert=True
        )
    else:
        # Aggiungi solo allo storico
        await db["giustificativi_saldi_finali"].update_one(
            {"employee_id": employee_id, "anno": anno},
            {
                "$push": {
                    "storico": {
                        "periodo": periodo,
                        "saldi": saldi,
                        "source": source,
                        "data": now,
                        "note": "Periodo precedente, non usato per saldi attuali"
                    }
                }
            }
        )
    
    return {
        "success": True,
        "employee_id": employee_id,
        "anno": anno,
        "periodo": periodo,
        "saldi_salvati": saldi,
        "aggiornato_principale": should_update,
        "message": "Saldi finali salvati" if should_update else f"Saldi aggiunti allo storico (periodo {periodo} precedente a {existing.get('periodo', 'N/A')})"
    }


@router.get("/saldi-finali/{employee_id}")
@handle_errors
async def get_saldi_finali(
    employee_id: str,
    anno: int = Query(None)
) -> Dict[str, Any]:
    """
    Recupera i saldi finali salvati per un dipendente.
    
    Restituisce:
    - Saldi attuali (ultimo periodo)
    - Storico di tutte le letture effettuate
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Verifica dipendente
    employee = await db["employees"].find_one(
        {"id": employee_id},
        {"_id": 0, "id": 1, "nome_completo": 1, "nome": 1, "cognome": 1}
    )
    if not employee:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    saldo = await db["giustificativi_saldi_finali"].find_one(
        {"employee_id": employee_id, "anno": anno},
        {"_id": 0}
    )
    
    if not saldo:
        return {
            "success": True,
            "employee_id": employee_id,
            "employee_nome": employee.get("nome_completo") or f"{employee.get('cognome', '')} {employee.get('nome', '')}",
            "anno": anno,
            "saldi": None,
            "message": "Nessun saldo finale salvato per questo anno. Caricare un Libro Unico o inserire manualmente."
        }
    
    return {
        "success": True,
        "employee_id": employee_id,
        "employee_nome": employee.get("nome_completo") or f"{employee.get('cognome', '')} {employee.get('nome', '')}",
        "anno": anno,
        "periodo": saldo.get("periodo"),
        "saldi": saldo.get("saldi", {}),
        "source": saldo.get("source"),
        "updated_at": saldo.get("updated_at"),
        "storico": saldo.get("storico", [])
    }


@router.get("/saldi-finali-tutti")
@handle_errors
async def get_saldi_finali_tutti(
    anno: int = Query(None)
) -> Dict[str, Any]:
    """
    Recupera i saldi finali per tutti i dipendenti.
    Se non esistono saldi salvati, li calcola dai cedolini.
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Prima prova a recuperare i saldi salvati
    saldi = await db["giustificativi_saldi_finali"].find(
        {"anno": anno},
        {"_id": 0, "storico": 0}
    ).to_list(500)
    
    # Se non ci sono saldi, calcola dai cedolini
    if not saldi:
        # Recupera tutti i dipendenti attivi
        employees = await db["employees"].find(
            {"stato": {"$ne": "cessato"}},
            {"_id": 0, "id": 1, "nome_completo": 1, "nome": 1, "cognome": 1}
        ).to_list(500)
        
        for emp in employees:
            emp_id = emp.get("id")
            nome = emp.get("nome_completo") or f"{emp.get('cognome', '')} {emp.get('nome', '')}"
            
            # Cerca ultimo cedolino dell'anno per questo dipendente
            cedolino = await db["cedolini"].find_one(
                {"employee_id": emp_id, "anno": anno},
                {"_id": 0},
                sort=[("mese", -1)]
            )
            
            saldo = {
                "employee_id": emp_id,
                "employee_nome": nome,
                "anno": anno,
                "ferie_residue": cedolino.get("ferie_residue", 0) if cedolino else 0,
                "rol_residui": cedolino.get("rol_residui", 0) if cedolino else 0,
                "permessi_residui": cedolino.get("permessi_residui", 0) if cedolino else 0,
                "exf_residui": cedolino.get("exf_residui", 0) if cedolino else 0,
                "data_ultimo_aggiornamento": cedolino.get("created_at") if cedolino else None,
                "fonte": "cedolino" if cedolino else "nessun_dato"
            }
            saldi.append(saldo)
    else:
        # Arricchisci con nomi dipendenti
        for s in saldi:
            emp_id = s.get("employee_id")
            employee = await db["employees"].find_one(
                {"id": emp_id},
                {"_id": 0, "nome_completo": 1, "nome": 1, "cognome": 1}
            )
            
            nome = ""
            if employee:
                nome = employee.get("nome_completo") or f"{employee.get('cognome', '')} {employee.get('nome', '')}"
            
            s["employee_nome"] = nome
    
    # Ordina per nome
    saldi.sort(key=lambda x: x.get("employee_nome", ""))
    
    return {
        "success": True,
        "anno": anno,
        "totale_dipendenti": len(saldi),
        "saldi": saldi
    }


@router.post("/aggiorna-riepilogo")
@handle_errors
async def aggiorna_riepilogo_dipendente(
    employee_id: str = Query(...),
    mese: int = Query(...),
    anno: int = Query(...),
    ferie_residue: float = Query(None),
    rol_residui: float = Query(None),
    permessi_residui: float = Query(None),
    note: str = Query(None)
) -> Dict[str, Any]:
    """
    Aggiorna manualmente il riepilogo giustificativi per un dipendente.
    
    Usare quando i dati estratti dal PDF non sono corretti
    o per inserire saldi iniziali.
    """
    db = Database.get_db()
    
    periodo = f"{anno}-{mese:02d}"
    
    updates = {}
    if ferie_residue is not None:
        updates["FER"] = ferie_residue
    if rol_residui is not None:
        updates["ROL"] = rol_residui
    if permessi_residui is not None:
        updates["PER"] = permessi_residui
    
    aggiornati = 0
    for codice, ore in updates.items():
        await db["presenze_mensili"].update_one(
            {
                "employee_id": employee_id,
                "stato": codice,
                "data": {"$regex": f"^{periodo}"}
            },
            {
                "$set": {
                    "ore": ore,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "source": "manual_update",
                    "note": note
                },
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "employee_id": employee_id,
                    "data": f"{periodo}-01",
                    "stato": codice,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )
        aggiornati += 1
    
    return {
        "success": True,
        "employee_id": employee_id,
        "periodo": periodo,
        "aggiornati": aggiornati,
        "valori": updates
    }
