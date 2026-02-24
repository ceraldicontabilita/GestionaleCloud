"""
ATTENDANCE - Sistema Gestione Presenze
======================================

Modulo per la gestione delle presenze dipendenti:
- Timbrature (entrata/uscita)
- Ferie e Permessi
- Straordinari
- Calcolo ore lavorate
- Report presenze
- Generazione PDF per consulente

Autore: Sistema Gestionale
Data: 22 Gennaio 2026
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Dict, Any
from datetime import datetime, timezone, timedelta
from enum import Enum
import uuid
import io

from app.database import Database

import logging
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# ENUMS
# =============================================================================

class TipoTimbratura(Enum):
    ENTRATA = "entrata"
    USCITA = "uscita"
    PAUSA_INIZIO = "pausa_inizio"
    PAUSA_FINE = "pausa_fine"


class TipoAssenza(Enum):
    FERIE = "ferie"
    PERMESSO = "permesso"
    MALATTIA = "malattia"
    MATERNITA = "maternita"
    PATERNITA = "paternita"
    INFORTUNIO = "infortunio"
    LUTTO = "lutto"
    MATRIMONIO = "matrimonio"
    ROL = "rol"  # Riduzione Orario Lavoro
    EX_FESTIVITA = "ex_festivita"
    ALTRO = "altro"


class StatoRichiesta(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# =============================================================================
# COSTANTI
# =============================================================================

# Ore lavorative standard
ORE_GIORNALIERE_STANDARD = 8
ORE_SETTIMANALI_STANDARD = 40
PAUSA_PRANZO_MINUTI = 60

# Giorni ferie annuali (default contratto commercio)
GIORNI_FERIE_ANNUALI = 26
GIORNI_ROL_ANNUALI = 72  # in ore


# =============================================================================
# TIMBRATURE
# =============================================================================

@router.post("/timbratura")
@handle_errors
async def registra_timbratura(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Registra una timbratura (entrata, uscita, pausa).
    
    Payload:
    {
        "employee_id": "uuid",
        "tipo": "entrata" | "uscita" | "pausa_inizio" | "pausa_fine",
        "data_ora": "2026-01-21T09:00:00" (opzionale, default: now),
        "note": "Note opzionali",
        "geolocation": {"lat": 41.9, "lng": 12.5} (opzionale)
    }
    """
    db = Database.get_db()
    
    employee_id = payload.get("employee_id")
    tipo = payload.get("tipo", "").lower()
    data_ora_str = payload.get("data_ora")
    note = payload.get("note", "")
    geolocation = payload.get("geolocation")
    
    if not employee_id:
        raise HTTPException(status_code=400, detail="employee_id obbligatorio")
    
    tipi_validi = [t.value for t in TipoTimbratura]
    if tipo not in tipi_validi:
        raise HTTPException(status_code=400, detail=f"tipo deve essere uno di: {tipi_validi}")
    
    # Verifica dipendente esiste
    employee = await db["employees"].find_one({"id": employee_id}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1})
    if not employee:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # Data/ora
    if data_ora_str:
        try:
            data_ora = datetime.fromisoformat(data_ora_str.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato data_ora non valido")
    else:
        data_ora = datetime.now(timezone.utc)
    
    data_giorno = data_ora.strftime("%Y-%m-%d")
    
    # Verifica coerenza timbrature
    if tipo == TipoTimbratura.USCITA.value:
        # Deve esistere un'entrata senza uscita per oggi
        entrata_oggi = await db["attendance_timbrature"].find_one({
            "employee_id": employee_id,
            "data": data_giorno,
            "tipo": TipoTimbratura.ENTRATA.value,
            "uscita_id": {"$exists": False}
        })
        if not entrata_oggi:
            logger.warning(f"Uscita senza entrata per {employee_id} il {data_giorno}")
    
    # Crea timbratura
    timbratura_id = str(uuid.uuid4())
    timbratura = {
        "id": timbratura_id,
        "employee_id": employee_id,
        "employee_nome": f"{employee.get('nome', '')} {employee.get('cognome', '')}".strip(),
        "tipo": tipo,
        "data": data_giorno,
        "ora": data_ora.strftime("%H:%M:%S"),
        "data_ora": data_ora.isoformat(),
        "note": note,
        "geolocation": geolocation,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["attendance_timbrature"].insert_one(timbratura.copy())
    
    # Se è uscita, collega all'entrata e calcola ore
    ore_lavorate = None
    if tipo == TipoTimbratura.USCITA.value and entrata_oggi:
        await db["attendance_timbrature"].update_one(
            {"id": entrata_oggi["id"]},
            {"$set": {"uscita_id": timbratura_id}}
        )
        
        # Calcola ore lavorate
        try:
            entrata_dt = datetime.fromisoformat(entrata_oggi["data_ora"].replace("Z", "+00:00"))
            delta = data_ora - entrata_dt
            ore_lavorate = round(delta.total_seconds() / 3600, 2)
        except Exception as e:
            logger.warning(f"Errore calcolo ore lavorate: {e}")
    
    logger.info(f"✅ Timbratura registrata: {employee.get('cognome')} - {tipo} - {data_ora.strftime('%H:%M')}")
    
    return {
        "success": True,
        "timbratura_id": timbratura_id,
        "tipo": tipo,
        "data_ora": data_ora.isoformat(),
        "ore_lavorate": ore_lavorate
    }


@router.get("/timbrature/{employee_id}")
@handle_errors
async def get_timbrature_dipendente(
    employee_id: str,
    data_da: str = Query(None),
    data_a: str = Query(None),
    limit: int = Query(100, ge=1, le=1000)
) -> Dict[str, Any]:
    """
    Recupera le timbrature di un dipendente.
    """
    db = Database.get_db()
    
    query = {"employee_id": employee_id}
    
    if data_da:
        query["data"] = {"$gte": data_da}
    if data_a:
        if "data" in query:
            query["data"]["$lte"] = data_a
        else:
            query["data"] = {"$lte": data_a}
    
    timbrature = await db["attendance_timbrature"].find(
        query, {"_id": 0}
    ).sort("data_ora", -1).to_list(limit)
    
    return {
        "success": True,
        "employee_id": employee_id,
        "count": len(timbrature),
        "timbrature": timbrature
    }


@router.get("/timbrature/giorno/{data}")
@handle_errors
async def get_timbrature_giorno(data: str) -> Dict[str, Any]:
    """
    Recupera tutte le timbrature di un giorno specifico.
    """
    db = Database.get_db()
    
    timbrature = await db["attendance_timbrature"].find(
        {"data": data},
        {"_id": 0}
    ).sort([("employee_nome", 1), ("ora", 1)]).to_list(500)
    
    # Raggruppa per dipendente
    per_dipendente = {}
    for t in timbrature:
        emp_id = t["employee_id"]
        if emp_id not in per_dipendente:
            per_dipendente[emp_id] = {
                "employee_id": emp_id,
                "employee_nome": t.get("employee_nome", ""),
                "timbrature": []
            }
        per_dipendente[emp_id]["timbrature"].append(t)
    
    return {
        "success": True,
        "data": data,
        "totale_timbrature": len(timbrature),
        "dipendenti": list(per_dipendente.values())
    }


# =============================================================================
# FERIE E PERMESSI
# =============================================================================

@router.post("/richiesta-assenza")
@handle_errors
async def crea_richiesta_assenza(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Crea una richiesta di assenza (ferie, permesso, malattia, ecc.).
    
    Payload:
    {
        "employee_id": "uuid",
        "tipo": "ferie" | "permesso" | "malattia" | etc.,
        "data_inizio": "2026-01-25",
        "data_fine": "2026-01-30",
        "ore_giornaliere": 8 (opzionale, per permessi a ore),
        "motivo": "Motivo richiesta",
        "certificato_medico": "numero_certificato" (per malattia)
    }
    """
    db = Database.get_db()
    
    employee_id = payload.get("employee_id")
    tipo = payload.get("tipo", "").lower()
    data_inizio = payload.get("data_inizio")
    data_fine = payload.get("data_fine")
    ore = payload.get("ore_giornaliere", ORE_GIORNALIERE_STANDARD)
    motivo = payload.get("motivo", "")
    certificato = payload.get("certificato_medico")
    
    if not employee_id or not data_inizio or not data_fine:
        raise HTTPException(status_code=400, detail="employee_id, data_inizio e data_fine obbligatori")
    
    tipi_validi = [t.value for t in TipoAssenza]
    if tipo not in tipi_validi:
        raise HTTPException(status_code=400, detail=f"tipo deve essere uno di: {tipi_validi}")
    
    # Verifica dipendente
    employee = await db["employees"].find_one({"id": employee_id}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1})
    if not employee:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # Calcola giorni
    try:
        dt_inizio = datetime.strptime(data_inizio, "%Y-%m-%d")
        dt_fine = datetime.strptime(data_fine, "%Y-%m-%d")
        
        if dt_fine < dt_inizio:
            raise HTTPException(status_code=400, detail="data_fine deve essere >= data_inizio")
        
        # Conta giorni lavorativi (escludi weekend)
        giorni_totali = 0
        current = dt_inizio
        while current <= dt_fine:
            if current.weekday() < 5:  # Lun-Ven
                giorni_totali += 1
            current += timedelta(days=1)
        
        ore_totali = giorni_totali * ore
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Formato date non valido: {e}")
    
    # Verifica sovrapposizioni
    sovrapposizione = await db["attendance_assenze"].find_one({
        "employee_id": employee_id,
        "stato": {"$ne": StatoRichiesta.CANCELLED.value},
        "$or": [
            {"data_inizio": {"$lte": data_fine}, "data_fine": {"$gte": data_inizio}}
        ]
    })
    
    if sovrapposizione:
        raise HTTPException(
            status_code=400, 
            detail=f"Esiste già una richiesta per il periodo {sovrapposizione.get('data_inizio')} - {sovrapposizione.get('data_fine')}"
        )
    
    # Crea richiesta
    richiesta_id = str(uuid.uuid4())
    richiesta = {
        "id": richiesta_id,
        "employee_id": employee_id,
        "employee_nome": f"{employee.get('nome', '')} {employee.get('cognome', '')}".strip(),
        "tipo": tipo,
        "data_inizio": data_inizio,
        "data_fine": data_fine,
        "giorni_totali": giorni_totali,
        "ore_giornaliere": ore,
        "ore_totali": ore_totali,
        "motivo": motivo,
        "certificato_medico": certificato,
        "stato": StatoRichiesta.PENDING.value,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["attendance_assenze"].insert_one(richiesta.copy())
    
    logger.info(f"✅ Richiesta assenza creata: {employee.get('cognome')} - {tipo} - {giorni_totali} giorni")
    
    return {
        "success": True,
        "richiesta_id": richiesta_id,
        "tipo": tipo,
        "giorni_totali": giorni_totali,
        "ore_totali": ore_totali,
        "stato": StatoRichiesta.PENDING.value
    }


@router.put("/richiesta-assenza/{richiesta_id}/approva")
@handle_errors
async def approva_richiesta_assenza(richiesta_id: str, payload: Dict[str, Any] = {}) -> Dict[str, Any]:
    """
    Approva una richiesta di assenza.
    """
    db = Database.get_db()
    
    note = payload.get("note", "")
    
    richiesta = await db["attendance_assenze"].find_one({"id": richiesta_id}, {"_id": 0})
    if not richiesta:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    
    if richiesta.get("stato") != StatoRichiesta.PENDING.value:
        raise HTTPException(status_code=400, detail=f"Richiesta già {richiesta.get('stato')}")
    
    await db["attendance_assenze"].update_one(
        {"id": richiesta_id},
        {"$set": {
            "stato": StatoRichiesta.APPROVED.value,
            "approvato_at": datetime.now(timezone.utc).isoformat(),
            "approvato_note": note
        }}
    )
    
    logger.info(f"✅ Richiesta approvata: {richiesta_id}")
    
    return {
        "success": True,
        "richiesta_id": richiesta_id,
        "stato": StatoRichiesta.APPROVED.value
    }


@router.put("/richiesta-assenza/{richiesta_id}/rifiuta")
@handle_errors
async def rifiuta_richiesta_assenza(richiesta_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rifiuta una richiesta di assenza.
    """
    db = Database.get_db()
    
    motivo = payload.get("motivo", "")
    if not motivo:
        raise HTTPException(status_code=400, detail="motivo obbligatorio per il rifiuto")
    
    richiesta = await db["attendance_assenze"].find_one({"id": richiesta_id}, {"_id": 0})
    if not richiesta:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    
    await db["attendance_assenze"].update_one(
        {"id": richiesta_id},
        {"$set": {
            "stato": StatoRichiesta.REJECTED.value,
            "rifiutato_at": datetime.now(timezone.utc).isoformat(),
            "rifiuto_motivo": motivo
        }}
    )
    
    return {
        "success": True,
        "richiesta_id": richiesta_id,
        "stato": StatoRichiesta.REJECTED.value
    }


@router.get("/assenze/{employee_id}")
@handle_errors
async def get_assenze_dipendente(
    employee_id: str,
    anno: int = Query(None),
    tipo: str = Query(None),
    stato: str = Query(None)
) -> Dict[str, Any]:
    """
    Recupera le assenze di un dipendente.
    """
    db = Database.get_db()
    
    query = {"employee_id": employee_id}
    
    if anno:
        query["data_inizio"] = {"$regex": f"^{anno}"}
    if tipo:
        query["tipo"] = tipo
    if stato:
        query["stato"] = stato
    
    assenze = await db["attendance_assenze"].find(
        query, {"_id": 0}
    ).sort("data_inizio", -1).to_list(500)
    
    # Calcola totali per tipo
    totali = {}
    for a in assenze:
        if a.get("stato") == StatoRichiesta.APPROVED.value:
            t = a.get("tipo", "altro")
            if t not in totali:
                totali[t] = {"giorni": 0, "ore": 0}
            totali[t]["giorni"] += a.get("giorni_totali", 0)
            totali[t]["ore"] += a.get("ore_totali", 0)
    
    return {
        "success": True,
        "employee_id": employee_id,
        "count": len(assenze),
        "totali_per_tipo": totali,
        "assenze": assenze
    }


@router.get("/richieste-pending")
@handle_errors
async def get_richieste_pending() -> Dict[str, Any]:
    """
    Recupera tutte le richieste di assenza in attesa di approvazione.
    """
    db = Database.get_db()
    
    richieste = await db["attendance_assenze"].find(
        {"stato": StatoRichiesta.PENDING.value},
        {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    
    return {
        "success": True,
        "count": len(richieste),
        "richieste": richieste
    }


# =============================================================================
# CALCOLO ORE E REPORT
# =============================================================================

@router.get("/ore-lavorate/{employee_id}")
@handle_errors
async def get_ore_lavorate(
    employee_id: str,
    mese: int = Query(..., ge=1, le=12),
    anno: int = Query(...)
) -> Dict[str, Any]:
    """
    Calcola le ore lavorate da un dipendente in un mese.
    """
    db = Database.get_db()
    
    # Range date del mese
    data_inizio = f"{anno}-{mese:02d}-01"
    if mese == 12:
        data_fine = f"{anno+1}-01-01"
    else:
        data_fine = f"{anno}-{mese+1:02d}-01"
    
    # Recupera timbrature del mese
    timbrature = await db["attendance_timbrature"].find({
        "employee_id": employee_id,
        "data": {"$gte": data_inizio, "$lt": data_fine}
    }, {"_id": 0}).sort("data_ora", 1).to_list(1000)
    
    # Raggruppa per giorno
    giorni = {}
    for t in timbrature:
        giorno = t.get("data")
        if giorno not in giorni:
            giorni[giorno] = {"entrate": [], "uscite": [], "pause": []}
        
        tipo = t.get("tipo")
        if tipo == TipoTimbratura.ENTRATA.value:
            giorni[giorno]["entrate"].append(t)
        elif tipo == TipoTimbratura.USCITA.value:
            giorni[giorno]["uscite"].append(t)
        elif tipo in [TipoTimbratura.PAUSA_INIZIO.value, TipoTimbratura.PAUSA_FINE.value]:
            giorni[giorno]["pause"].append(t)
    
    # Calcola ore per giorno
    dettaglio_giorni = []
    ore_totali = 0
    ore_straordinario = 0
    giorni_lavorati = 0
    
    for giorno, dati in sorted(giorni.items()):
        ore_giorno = 0
        
        # Abbina entrate e uscite
        entrate = sorted(dati["entrate"], key=lambda x: x.get("ora", ""))
        uscite = sorted(dati["uscite"], key=lambda x: x.get("ora", ""))
        
        for i, entrata in enumerate(entrate):
            if i < len(uscite):
                try:
                    dt_entrata = datetime.fromisoformat(entrata["data_ora"].replace("Z", "+00:00"))
                    dt_uscita = datetime.fromisoformat(uscite[i]["data_ora"].replace("Z", "+00:00"))
                    delta = dt_uscita - dt_entrata
                    ore_sessione = delta.total_seconds() / 3600
                    ore_giorno += ore_sessione
                except Exception as e:
                    logger.warning(f"Errore calcolo ore sessione: {e}")
        
        # Sottrai pausa pranzo se > 6 ore
        if ore_giorno > 6:
            ore_giorno -= 1  # 1 ora di pausa
        
        ore_giorno = round(ore_giorno, 2)
        
        # Calcola straordinario
        straordinario = max(0, ore_giorno - ORE_GIORNALIERE_STANDARD)
        ore_ordinarie = min(ore_giorno, ORE_GIORNALIERE_STANDARD)
        
        if ore_giorno > 0:
            giorni_lavorati += 1
            ore_totali += ore_giorno
            ore_straordinario += straordinario
        
        dettaglio_giorni.append({
            "data": giorno,
            "ore_totali": ore_giorno,
            "ore_ordinarie": round(ore_ordinarie, 2),
            "ore_straordinario": round(straordinario, 2),
            "entrata": entrate[0].get("ora") if entrate else None,
            "uscita": uscite[-1].get("ora") if uscite else None
        })
    
    # Recupera assenze del mese
    assenze = await db["attendance_assenze"].find({
        "employee_id": employee_id,
        "stato": StatoRichiesta.APPROVED.value,
        "data_inizio": {"$lte": data_fine},
        "data_fine": {"$gte": data_inizio}
    }, {"_id": 0}).to_list(50)
    
    ore_assenza = sum(a.get("ore_totali", 0) for a in assenze)
    
    return {
        "success": True,
        "employee_id": employee_id,
        "mese": mese,
        "anno": anno,
        "riepilogo": {
            "giorni_lavorati": giorni_lavorati,
            "ore_totali": round(ore_totali, 2),
            "ore_ordinarie": round(ore_totali - ore_straordinario, 2),
            "ore_straordinario": round(ore_straordinario, 2),
            "ore_assenza": ore_assenza
        },
        "dettaglio_giorni": dettaglio_giorni,
        "assenze": assenze
    }


@router.get("/dashboard-presenze")
@handle_errors
async def get_dashboard_presenze(data: str = Query(None)) -> Dict[str, Any]:
    """
    Dashboard presenze giornaliera.
    Mostra solo dipendenti attivi E in_carico (per escludere dipendenti non più gestiti)
    """
    db = Database.get_db()
    
    if not data:
        data = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    # Solo dipendenti con status "attivo" E in_carico=true E non cessati
    dipendenti = await db["employees"].find(
        {
            "$and": [
                {"$or": [
                    {"status": "attivo"},
                    {"status": {"$exists": False}}
                ]},
                {"$or": [
                    {"in_carico": True},
                    {"in_carico": {"$exists": False}}  # Per retrocompatibilità
                ]},
                {"$or": [
                    {"stato_contratto": {"$ne": "cessato"}},
                    {"stato_contratto": {"$exists": False}}
                ]}
            ]
        },
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1, "name": 1, "in_carico": 1}
    ).to_list(500)
    
    # Timbrature di oggi
    timbrature_oggi = await db["attendance_timbrature"].find(
        {"data": data},
        {"_id": 0}
    ).to_list(1000)
    
    # Assenze di oggi
    assenze_oggi = await db["attendance_assenze"].find({
        "stato": StatoRichiesta.APPROVED.value,
        "data_inizio": {"$lte": data},
        "data_fine": {"$gte": data}
    }, {"_id": 0}).to_list(200)
    
    # Mappa timbrature per dipendente
    timbrature_per_dip = {}
    for t in timbrature_oggi:
        emp_id = t["employee_id"]
        if emp_id not in timbrature_per_dip:
            timbrature_per_dip[emp_id] = []
        timbrature_per_dip[emp_id].append(t)
    
    # Mappa assenze per dipendente
    assenze_per_dip = {a["employee_id"]: a for a in assenze_oggi}
    
    # Costruisci report
    presenti = []
    assenti = []
    non_timbrato = []
    
    for dip in dipendenti:
        emp_id = dip["id"]
        # Usa nome_completo, name, o costruisci da nome+cognome
        nome_completo = dip.get("nome_completo") or dip.get("name") or f"{dip.get('nome', '')} {dip.get('cognome', '')}".strip()
        if not nome_completo:
            continue  # Salta dipendenti senza nome
        
        if emp_id in assenze_per_dip:
            assenza = assenze_per_dip[emp_id]
            assenti.append({
                "employee_id": emp_id,
                "nome": nome_completo,
                "tipo_assenza": assenza.get("tipo"),
                "motivo": assenza.get("motivo")
            })
        elif emp_id in timbrature_per_dip:
            timb = timbrature_per_dip[emp_id]
            entrate = [t for t in timb if t["tipo"] == TipoTimbratura.ENTRATA.value]
            uscite = [t for t in timb if t["tipo"] == TipoTimbratura.USCITA.value]
            
            presenti.append({
                "employee_id": emp_id,
                "nome": nome_completo,
                "entrata": entrate[0].get("ora") if entrate else None,
                "uscita": uscite[-1].get("ora") if uscite else None,
                "in_ufficio": len(entrate) > len(uscite)
            })
        else:
            # Verifica se è weekend
            try:
                dt = datetime.strptime(data, "%Y-%m-%d")
                if dt.weekday() < 5:  # Lun-Ven
                    non_timbrato.append({
                        "employee_id": emp_id,
                        "nome": nome_completo
                    })
            except ValueError:
                pass  # Data non valida, ignora
    
    return {
        "success": True,
        "data": data,
        "riepilogo": {
            "totale_dipendenti": len(dipendenti),
            "presenti": len(presenti),
            "assenti": len(assenti),
            "non_timbrato": len(non_timbrato)
        },
        "presenti": presenti,
        "assenti": assenti,
        "non_timbrato": non_timbrato
    }


@router.get("/saldo-ferie/{employee_id}")
@handle_errors
async def get_saldo_ferie(employee_id: str, anno: int = Query(None)) -> Dict[str, Any]:
    """
    Calcola il saldo ferie e permessi di un dipendente.
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Recupera assenze approvate dell'anno
    assenze = await db["attendance_assenze"].find({
        "employee_id": employee_id,
        "stato": StatoRichiesta.APPROVED.value,
        "data_inizio": {"$regex": f"^{anno}"}
    }, {"_id": 0}).to_list(500)
    
    # Calcola consumo per tipo
    consumo = {
        "ferie": 0,
        "permesso": 0,
        "rol": 0,
        "malattia": 0,
        "altro": 0
    }
    
    for a in assenze:
        tipo = a.get("tipo", "altro")
        if tipo in consumo:
            if tipo in ["rol", "permesso"]:
                consumo[tipo] += a.get("ore_totali", 0)
            else:
                consumo[tipo] += a.get("giorni_totali", 0)
        else:
            consumo["altro"] += a.get("giorni_totali", 0)
    
    # Calcola residui
    saldo = {
        "ferie": {
            "spettanti": GIORNI_FERIE_ANNUALI,
            "godute": consumo["ferie"],
            "residue": GIORNI_FERIE_ANNUALI - consumo["ferie"]
        },
        "rol": {
            "spettanti_ore": GIORNI_ROL_ANNUALI,
            "godute_ore": consumo["rol"],
            "residue_ore": GIORNI_ROL_ANNUALI - consumo["rol"]
        },
        "permessi": {
            "godute_ore": consumo["permesso"]
        },
        "malattia": {
            "giorni": consumo["malattia"]
        }
    }
    
    return {
        "success": True,
        "employee_id": employee_id,
        "anno": anno,
        "saldo": saldo
    }



# =============================================================================
# CALENDARIO PRESENZE - Nuovi Endpoint
# =============================================================================

@router.get("/presenze-mese")
@handle_errors
async def get_presenze_mese(anno: int = Query(...), mese: int = Query(...)) -> Dict[str, Any]:
    """
    Recupera tutte le presenze del mese per tutti i dipendenti.
    Ritorna un dizionario con chiave "employeeId_YYYY-MM-DD" e valore lo stato.
    """
    db = Database.get_db()
    
    # Calcola range date
    primo_giorno = f"{anno}-{str(mese).zfill(2)}-01"
    if mese == 12:
        ultimo_giorno = f"{anno + 1}-01-01"
    else:
        ultimo_giorno = f"{anno}-{str(mese + 1).zfill(2)}-01"
    
    # Recupera presenze dal DB
    presenze_db = await db["attendance_presenze_calendario"].find(
        {
            "data": {"$gte": primo_giorno, "$lt": ultimo_giorno}
        },
        {"_id": 0}
    ).to_list(10000)
    
    # Recupera assenze approvate nel mese
    assenze = await db["attendance_assenze"].find({
        "stato": "approved",
        "$or": [
            {"data_inizio": {"$gte": primo_giorno, "$lt": ultimo_giorno}},
            {"data_fine": {"$gte": primo_giorno, "$lt": ultimo_giorno}},
            {"data_inizio": {"$lte": primo_giorno}, "data_fine": {"$gte": ultimo_giorno}}
        ]
    }, {"_id": 0}).to_list(1000)
    
    # Costruisci mappa presenze
    presenze_map = {}
    
    # Prima aggiungi le presenze esplicite
    for p in presenze_db:
        emp_id = p["employee_id"]
        data = p["data"]
        key = f"{emp_id}_{data}"
        presenze_map[key] = p.get("stato", "presente")
    
    # Poi sovrascrivi con le assenze approvate
    for a in assenze:
        emp_id = a["employee_id"]
        tipo = a.get("tipo", "assente")
        
        # Mappa tipo assenza a stato calendario
        stato_map = {
            "ferie": "ferie",
            "permesso": "permesso",
            "malattia": "malattia",
            "rol": "rol",
            "maternita": "assente",
            "paternita": "assente",
            "lutto": "assente",
            "matrimonio": "assente",
            "altro": "assente"
        }
        stato = stato_map.get(tipo, "assente")
        
        # Itera sui giorni dell'assenza
        try:
            start = datetime.strptime(a["data_inizio"], "%Y-%m-%d")
            end = datetime.strptime(a["data_fine"], "%Y-%m-%d")
            current = start
            while current <= end:
                data_str = current.strftime("%Y-%m-%d")
                if data_str >= primo_giorno and data_str < ultimo_giorno:
                    key = f"{emp_id}_{data_str}"
                    presenze_map[key] = stato
                current += timedelta(days=1)
        except ValueError:
            continue  # Date non valide, salta questa assenza
    
    return {
        "success": True,
        "anno": anno,
        "mese": mese,
        "presenze": presenze_map
    }


@router.post("/set-presenza")
@handle_errors
async def set_presenza(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Imposta lo stato presenza per un dipendente in una data specifica.
    """
    db = Database.get_db()
    
    employee_id = data.get("employee_id")
    data_str = data.get("data")
    stato = data.get("stato")
    
    if not employee_id or not data_str or not stato:
        raise HTTPException(status_code=400, detail="Campi obbligatori: employee_id, data, stato")
    
    # Upsert presenza
    await db["attendance_presenze_calendario"].update_one(
        {"employee_id": employee_id, "data": data_str},
        {
            "$set": {
                "employee_id": employee_id,
                "data": data_str,
                "stato": stato,
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )
    
    return {
        "success": True,
        "message": f"Presenza impostata: {stato}",
        "employee_id": employee_id,
        "data": data_str,
        "stato": stato
    }



# =============================================================================
# GESTIONE FLAG IN_CARICO
# =============================================================================

@router.get("/dipendenti-in-carico")
@handle_errors
async def get_dipendenti_in_carico() -> Dict[str, Any]:
    """
    Ritorna tutti i dipendenti attivi con il loro stato in_carico.
    Utile per la gestione del modulo presenze.
    """
    db = Database.get_db()
    
    dipendenti = await db["employees"].find(
        {
            "$and": [
                {"$or": [
                    {"status": "attivo"},
                    {"status": {"$exists": False}}
                ]},
                {"$or": [
                    {"stato_contratto": {"$ne": "cessato"}},
                    {"stato_contratto": {"$exists": False}}
                ]}
            ]
        },
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1, "name": 1, 
         "in_carico": 1, "mansione": 1, "status": 1, "stato_contratto": 1}
    ).sort("nome_completo", 1).to_list(500)
    
    # Normalizza il campo in_carico (default True per retrocompatibilità)
    for dip in dipendenti:
        if "in_carico" not in dip:
            dip["in_carico"] = True
        dip["nome_completo"] = dip.get("nome_completo") or dip.get("name") or \
                              f"{dip.get('nome', '')} {dip.get('cognome', '')}".strip()
    
    in_carico_count = sum(1 for d in dipendenti if d.get("in_carico", True))
    non_in_carico_count = len(dipendenti) - in_carico_count
    
    return {
        "success": True,
        "totale": len(dipendenti),
        "in_carico": in_carico_count,
        "non_in_carico": non_in_carico_count,
        "dipendenti": dipendenti
    }


@router.put("/set-in-carico/{employee_id}")
@handle_errors
async def set_in_carico(employee_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Imposta il flag in_carico per un dipendente.
    Payload: { "in_carico": true/false }
    """
    db = Database.get_db()
    
    in_carico = data.get("in_carico", True)
    
    result = await db["employees"].update_one(
        {"$or": [{"id": employee_id}, {"codice_fiscale": employee_id}]},
        {"$set": {
            "in_carico": in_carico,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    logger.info(f"✅ Flag in_carico impostato: {employee_id} -> {in_carico}")
    
    return {
        "success": True,
        "employee_id": employee_id,
        "in_carico": in_carico
    }




# =============================================================================
# NOTE PRESENZE (Protocolli Malattia, etc.)
# =============================================================================

@router.post("/set-nota-presenza")
@handle_errors
async def set_nota_presenza(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Imposta una nota per una presenza (es. protocollo certificato medico).
    
    Payload:
    {
        "employee_id": "...",
        "data": "YYYY-MM-DD",
        "protocollo_malattia": "xxxxx",
        "note": "..."
    }
    """
    db = Database.get_db()
    
    employee_id = data.get("employee_id")
    data_str = data.get("data")
    protocollo = data.get("protocollo_malattia")
    note = data.get("note")
    
    if not employee_id or not data_str:
        raise HTTPException(400, "employee_id e data sono obbligatori")
    
    update_fields = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if protocollo:
        update_fields["protocollo_malattia"] = protocollo
    if note:
        update_fields["note"] = note
    
    await db["attendance_note_presenze"].update_one(
        {"employee_id": employee_id, "data": data_str},
        {
            "$set": update_fields,
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "employee_id": employee_id,
                "data": data_str,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )
    
    return {"success": True, "message": "Nota salvata"}


@router.get("/note-presenze/{anno}/{mese}")
@handle_errors
async def get_note_presenze(anno: int, mese: int) -> Dict[str, Any]:
    """Recupera tutte le note presenze per un mese."""
    db = Database.get_db()
    
    # Genera range date
    data_inizio = f"{anno}-{mese:02d}-01"
    if mese == 12:
        data_fine = f"{anno + 1}-01-01"
    else:
        data_fine = f"{anno}-{mese + 1:02d}-01"
    
    note = await db["attendance_note_presenze"].find(
        {"data": {"$gte": data_inizio, "$lt": data_fine}},
        {"_id": 0}
    ).to_list(1000)
    
    # Converti in dizionario per accesso rapido
    note_dict = {}
    for n in note:
        emp_id = n["employee_id"]
        data_val = n["data"]
        key = f"{emp_id}_{data_val}"
        note_dict[key] = n
    
    return {"success": True, "note": note_dict}


# =============================================================================
# GENERAZIONE PDF PER CONSULENTE DEL LAVORO
# =============================================================================

@router.post("/genera-pdf-consulente")
@handle_errors
async def genera_pdf_consulente(data: Dict[str, Any]):
    """
    Genera un PDF riepilogativo delle presenze per il consulente del lavoro.
    Include:
    - Riepilogo presenze per dipendente
    - Dettaglio giorni (P, F, M, etc.)
    - Protocolli certificati malattia
    - Acconti mensili
    - Note
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    except ImportError:
        raise HTTPException(500, "reportlab non installato. Eseguire: pip install reportlab")
    
    db = Database.get_db()
    
    anno = data.get("anno", datetime.now().year)
    mese = data.get("mese", datetime.now().month)
    
    MESI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
            "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    
    # Recupera dipendenti in carico (escludi cessati)
    dipendenti = await db["employees"].find(
        {
            "$and": [
                {"$or": [{"in_carico": True}, {"in_carico": {"$exists": False}}]},
                {"$or": [{"stato_contratto": {"$ne": "cessato"}}, {"stato_contratto": {"$exists": False}}]}
            ]
        },
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1, "name": 1}
    ).sort("cognome", 1).to_list(500)
    
    # Recupera presenze del mese
    data_inizio = f"{anno}-{mese:02d}-01"
    if mese == 12:
        data_fine = f"{anno + 1}-01-01"
    else:
        data_fine = f"{anno}-{mese + 1:02d}-01"
    
    presenze_raw = await db["attendance_presenze_calendario"].find(
        {"data": {"$gte": data_inizio, "$lt": data_fine}},
        {"_id": 0}
    ).to_list(10000)
    
    presenze = {}
    for p in presenze_raw:
        emp_id = p["employee_id"]
        data_val = p["data"]
        key = f"{emp_id}_{data_val}"
        presenze[key] = p.get("stato")
    
    # Recupera note (protocolli malattia)
    note_raw = await db["attendance_note_presenze"].find(
        {"data": {"$gte": data_inizio, "$lt": data_fine}},
        {"_id": 0}
    ).to_list(1000)
    
    note = {}
    for n in note_raw:
        emp_id = n["employee_id"]
        data_val = n["data"]
        key = f"{emp_id}_{data_val}"
        note[key] = n
    
    # Recupera acconti del mese
    acconti_raw = await db["acconti_dipendenti"].find(
        {"anno": anno, "mese": mese},
        {"_id": 0}
    ).to_list(500)
    
    acconti = {a.get("employee_id"): a.get("importo", 0) for a in acconti_raw}
    
    # Calcola giorni del mese
    import calendar
    giorni_mese = calendar.monthrange(anno, mese)[1]
    
    # Genera PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), 
                           leftMargin=10*mm, rightMargin=10*mm,
                           topMargin=15*mm, bottomMargin=15*mm)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Heading1"], 
                                  fontSize=16, alignment=TA_CENTER, spaceAfter=10)
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"],
                                     fontSize=10, alignment=TA_CENTER, spaceAfter=15)
    
    elements = []
    
    # Titolo
    elements.append(Paragraph(f"RIEPILOGO PRESENZE - {MESI[mese-1].upper()} {anno}", title_style))
    elements.append(Paragraph(f"Generato il {datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitle_style))
    
    # Header tabella
    header = ["Dipendente"] + [str(g) for g in range(1, giorni_mese + 1)] + ["P", "F", "M", "PE", "Acc.€"]
    
    # Mappa stati a label
    stato_label = {
        "presente": "P", "assente": "A", "ferie": "F", "permesso": "PE",
        "malattia": "M", "rol": "R", "smartworking": "SW", "trasferta": "T", "riposo": "-"
    }
    
    table_data = [header]
    
    note_malattia_list = []  # Per sezione note in fondo
    
    for dip in dipendenti:
        emp_id = dip.get("id")
        nome_val = dip.get("nome", "")
        cognome_val = dip.get("cognome", "")
        nome = dip.get("nome_completo") or dip.get("name") or f"{nome_val} {cognome_val}".strip()
        
        row = [nome[:20]]  # Tronca nome
        totali = {"P": 0, "F": 0, "M": 0, "PE": 0}
        
        for g in range(1, giorni_mese + 1):
            data_str = f"{anno}-{mese:02d}-{g:02d}"
            key = f"{emp_id}_{data_str}"
            stato = presenze.get(key, "")
            label = stato_label.get(stato, "-")
            row.append(label)
            
            # Conta totali
            if label == "P" or label == "SW" or label == "T":
                totali["P"] += 1
            elif label == "F":
                totali["F"] += 1
            elif label == "M":
                totali["M"] += 1
                # Controlla se cè protocollo
                nota = note.get(key)
                if nota and nota.get("protocollo_malattia"):
                    note_malattia_list.append({
                        "dipendente": nome,
                        "data": f"{g:02d}/{mese:02d}/{anno}",
                        "protocollo": nota.get("protocollo_malattia")
                    })
            elif label == "PE" or label == "R":
                totali["PE"] += 1
        
        # Acconti
        acconto = acconti.get(emp_id, 0)
        
        row.extend([str(totali["P"]), str(totali["F"]), str(totali["M"]), str(totali["PE"]), 
                    f"{acconto:.0f}" if acconto else "-"])
        table_data.append(row)
    
    # Crea tabella
    col_widths = [50*mm] + [5.5*mm] * giorni_mese + [10*mm, 10*mm, 10*mm, 10*mm, 15*mm]
    
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTSIZE", (0, 0), (0, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    
    elements.append(table)
    
    # Sezione Protocolli Malattia
    if note_malattia_list:
        elements.append(Spacer(1, 15*mm))
        elements.append(Paragraph("PROTOCOLLI CERTIFICATI MALATTIA", title_style))
        
        note_header = ["Dipendente", "Data", "N. Protocollo INPS"]
        note_data = [note_header]
        for nm in note_malattia_list:
            note_data.append([nm["dipendente"], nm["data"], nm["protocollo"]])
        
        note_table = Table(note_data, colWidths=[80*mm, 40*mm, 80*mm])
        note_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3b82f6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ]))
        elements.append(note_table)
    
    # Legenda
    elements.append(Spacer(1, 10*mm))
    legenda = Paragraph(
        "<b>Legenda:</b> P=Presente, F=Ferie, M=Malattia, PE=Permesso, R=ROL, CH=Chiuso, RS=Riposo Sett., T=Trasferta, A=Assente, X=Cessato",
        ParagraphStyle("Legenda", fontSize=8, textColor=colors.grey)
    )
    elements.append(legenda)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    filename = f"Presenze_{MESI[mese-1]}_{anno}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

