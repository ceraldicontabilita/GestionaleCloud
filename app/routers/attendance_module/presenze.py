"""
ATTENDANCE - Presenze e Assenze
===============================
Gestione calendario presenze, assenze, ferie, permessi.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any
from datetime import datetime, timezone, timedelta
import uuid
import logging

from app.database import Database
from .models import TipoAssenza, StatoRichiesta, STATI_PRESENZA
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# CALENDARIO PRESENZE
# =============================================================================

@router.get("/dipendenti-in-carico")
@handle_errors
async def get_dipendenti_in_carico() -> Dict[str, Any]:
    """Recupera lista dipendenti attivi (in_carico=true)."""
    db = Database.get_db()
    
    pipeline = [
        {"$match": {"$or": [{"in_carico": True}, {"in_carico": {"$exists": False}}]}},
        {"$project": {
            "_id": 0,
            "id": 1,
            "nome": 1,
            "cognome": 1,
            "nome_completo": 1,
            "mansione": 1,
            "in_carico": 1
        }},
        {"$sort": {"cognome": 1, "nome": 1}}
    ]
    
    dipendenti = await db["employees"].aggregate(pipeline).to_list(500)
    
    total = await db["employees"].count_documents({})
    in_carico = len(dipendenti)
    
    return {
        "success": True,
        "totale": total,
        "in_carico": in_carico,
        "non_in_carico": total - in_carico,
        "dipendenti": dipendenti
    }


@router.get("/presenze-calendario/{anno}/{mese}")
@handle_errors
async def get_presenze_calendario(anno: int, mese: int) -> Dict[str, Any]:
    """
    Recupera le presenze per il calendario mensile.
    """
    db = Database.get_db()
    
    data_inizio = f"{anno}-{mese:02d}-01"
    if mese == 12:
        data_fine = f"{anno + 1}-01-01"
    else:
        data_fine = f"{anno}-{mese + 1:02d}-01"
    
    presenze = await db["attendance_presenze_calendario"].find(
        {"data": {"$gte": data_inizio, "$lt": data_fine}},
        {"_id": 0}
    ).to_list(10000)
    
    # Converti in dizionario per accesso rapido
    presenze_dict = {}
    for p in presenze:
        key = f"{p['employee_id']}_{p['data']}"
        presenze_dict[key] = p.get("stato")
    
    return {
        "success": True,
        "anno": anno,
        "mese": mese,
        "presenze": presenze_dict
    }


@router.post("/set-presenza")
@handle_errors
async def set_presenza(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Imposta lo stato presenza per un dipendente in una data.
    """
    db = Database.get_db()
    
    employee_id = payload.get("employee_id")
    data = payload.get("data")  # YYYY-MM-DD
    stato = payload.get("stato")
    
    if not employee_id or not data or not stato:
        raise HTTPException(400, "employee_id, data e stato obbligatori")
    
    if stato not in STATI_PRESENZA and stato != "riposo":
        raise HTTPException(400, f"Stato non valido. Stati ammessi: {list(STATI_PRESENZA.keys())}")
    
    # Upsert presenza
    await db["attendance_presenze_calendario"].update_one(
        {"employee_id": employee_id, "data": data},
        {
            "$set": {
                "stato": stato,
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "employee_id": employee_id,
                "data": data,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )
    
    return {"success": True, "employee_id": employee_id, "data": data, "stato": stato}


@router.get("/dashboard-presenze")
@handle_errors
async def get_dashboard_presenze(data: str = Query(None)) -> Dict[str, Any]:
    """
    Dashboard presenze giornaliere con statistiche.
    """
    db = Database.get_db()
    
    if not data:
        data = datetime.now().strftime("%Y-%m-%d")
    
    # Dipendenti in carico
    dipendenti = await db["employees"].find(
        {"$or": [{"in_carico": True}, {"in_carico": {"$exists": False}}]},
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1}
    ).to_list(500)
    
    # Presenze del giorno
    presenze = await db["attendance_presenze_calendario"].find(
        {"data": data},
        {"_id": 0}
    ).to_list(1000)
    
    presenze_map = {p["employee_id"]: p.get("stato") for p in presenze}
    
    # Statistiche
    stats = {
        "presenti": 0,
        "assenti": 0,
        "ferie": 0,
        "permesso": 0,
        "malattia": 0,
        "smartworking": 0,
        "non_timbrato": 0
    }
    
    dettaglio = []
    for dip in dipendenti:
        emp_id = dip["id"]
        stato = presenze_map.get(emp_id, None)
        
        if stato:
            if stato in stats:
                stats[stato] += 1
            elif stato == "presente":
                stats["presenti"] += 1
        else:
            stats["non_timbrato"] += 1
        
        nome = dip.get("nome_completo") or f"{dip.get('nome', '')} {dip.get('cognome', '')}".strip()
        dettaglio.append({
            "employee_id": emp_id,
            "nome": nome,
            "stato": stato
        })
    
    return {
        "success": True,
        "data": data,
        "totale_dipendenti": len(dipendenti),
        "statistiche": stats,
        "dettaglio": dettaglio
    }


# =============================================================================
# RICHIESTE ASSENZA (Ferie, Permessi, Malattia)
# =============================================================================

@router.post("/richiesta-assenza")
@handle_errors
async def crea_richiesta_assenza(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Crea una richiesta di assenza (ferie, permesso, malattia).
    """
    db = Database.get_db()
    
    employee_id = payload.get("employee_id")
    tipo = payload.get("tipo", "").lower()
    data_inizio = payload.get("data_inizio")  # YYYY-MM-DD
    data_fine = payload.get("data_fine")  # YYYY-MM-DD
    motivo = payload.get("motivo", "")
    ore = payload.get("ore_giornaliere", 8)
    certificato = payload.get("certificato_medico")
    
    if not employee_id:
        raise HTTPException(400, "employee_id obbligatorio")
    if not data_inizio or not data_fine:
        raise HTTPException(400, "data_inizio e data_fine obbligatorie")
    
    tipi_validi = [t.value for t in TipoAssenza]
    if tipo not in tipi_validi:
        raise HTTPException(400, f"tipo deve essere uno di: {tipi_validi}")
    
    # Verifica dipendente
    employee = await db["employees"].find_one({"id": employee_id}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1})
    if not employee:
        raise HTTPException(404, "Dipendente non trovato")
    
    # Calcola giorni
    try:
        dt_inizio = datetime.strptime(data_inizio, "%Y-%m-%d")
        dt_fine = datetime.strptime(data_fine, "%Y-%m-%d")
        
        if dt_fine < dt_inizio:
            raise HTTPException(400, "data_fine deve essere >= data_inizio")
        
        giorni_totali = 0
        current = dt_inizio
        while current <= dt_fine:
            if current.weekday() < 5:
                giorni_totali += 1
            current += timedelta(days=1)
        
        ore_totali = giorni_totali * ore
        
    except ValueError as e:
        raise HTTPException(400, f"Formato date non valido: {e}")
    
    # Verifica sovrapposizioni
    sovrapposizione = await db["attendance_assenze"].find_one({
        "employee_id": employee_id,
        "stato": {"$ne": "cancelled"},
        "$or": [
            {"data_inizio": {"$lte": data_fine}, "data_fine": {"$gte": data_inizio}}
        ]
    })
    
    if sovrapposizione:
        raise HTTPException(400, "Esiste già una richiesta per il periodo")
    
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
    
    return {
        "success": True,
        "richiesta_id": richiesta_id,
        "giorni_totali": giorni_totali,
        "ore_totali": ore_totali,
        "stato": StatoRichiesta.PENDING.value
    }


@router.put("/richiesta-assenza/{richiesta_id}/approva")
@handle_errors
async def approva_richiesta_assenza(richiesta_id: str, payload: Dict[str, Any] = {}) -> Dict[str, Any]:
    """Approva una richiesta di assenza."""
    db = Database.get_db()
    
    richiesta = await db["attendance_assenze"].find_one({"id": richiesta_id}, {"_id": 0})
    if not richiesta:
        raise HTTPException(404, "Richiesta non trovata")
    
    if richiesta.get("stato") != StatoRichiesta.PENDING.value:
        raise HTTPException(400, f"Richiesta già {richiesta.get('stato')}")
    
    await db["attendance_assenze"].update_one(
        {"id": richiesta_id},
        {"$set": {
            "stato": StatoRichiesta.APPROVED.value,
            "approvato_at": datetime.now(timezone.utc).isoformat(),
            "approvato_note": payload.get("note", "")
        }}
    )
    
    return {"success": True, "richiesta_id": richiesta_id, "stato": StatoRichiesta.APPROVED.value}


@router.put("/richiesta-assenza/{richiesta_id}/rifiuta")
@handle_errors
async def rifiuta_richiesta_assenza(richiesta_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Rifiuta una richiesta di assenza."""
    db = Database.get_db()
    
    motivo = payload.get("motivo", "")
    if not motivo:
        raise HTTPException(400, "motivo obbligatorio per il rifiuto")
    
    richiesta = await db["attendance_assenze"].find_one({"id": richiesta_id}, {"_id": 0})
    if not richiesta:
        raise HTTPException(404, "Richiesta non trovata")
    
    await db["attendance_assenze"].update_one(
        {"id": richiesta_id},
        {"$set": {
            "stato": StatoRichiesta.REJECTED.value,
            "rifiutato_at": datetime.now(timezone.utc).isoformat(),
            "rifiuto_motivo": motivo
        }}
    )
    
    return {"success": True, "richiesta_id": richiesta_id, "stato": StatoRichiesta.REJECTED.value}


@router.get("/assenze/{employee_id}")
@handle_errors
async def get_assenze_dipendente(
    employee_id: str,
    anno: int = Query(None),
    tipo: str = Query(None),
    stato: str = Query(None)
) -> Dict[str, Any]:
    """Recupera le assenze di un dipendente."""
    db = Database.get_db()
    
    query = {"employee_id": employee_id}
    
    if anno:
        query["data_inizio"] = {"$regex": f"^{anno}"}
    if tipo:
        query["tipo"] = tipo
    if stato:
        query["stato"] = stato
    
    assenze = await db["attendance_assenze"].find(query, {"_id": 0}).sort("data_inizio", -1).to_list(500)
    
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
    """Recupera tutte le richieste di assenza in attesa."""
    db = Database.get_db()
    
    richieste = await db["attendance_assenze"].find(
        {"stato": StatoRichiesta.PENDING.value},
        {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    
    return {"success": True, "count": len(richieste), "richieste": richieste}


# =============================================================================
# CALCOLO ORE E STORICO
# =============================================================================

@router.get("/ore-lavorate/{employee_id}")
@handle_errors
async def get_ore_lavorate(
    employee_id: str,
    mese: int = Query(..., ge=1, le=12),
    anno: int = Query(...)
) -> Dict[str, Any]:
    """Calcola le ore lavorate da un dipendente in un mese."""
    db = Database.get_db()
    
    data_inizio = f"{anno}-{mese:02d}-01"
    if mese == 12:
        data_fine = f"{anno + 1}-01-01"
    else:
        data_fine = f"{anno}-{mese + 1:02d}-01"
    
    # Timbrature del mese
    timbrature = await db["attendance_timbrature"].find({
        "employee_id": employee_id,
        "data": {"$gte": data_inizio, "$lt": data_fine}
    }, {"_id": 0}).to_list(1000)
    
    # Calcola ore per giorno
    ore_per_giorno = {}
    for t in timbrature:
        giorno = t.get("data")
        if giorno not in ore_per_giorno:
            ore_per_giorno[giorno] = {"entrate": [], "uscite": []}
        
        if t.get("tipo") == "entrata":
            ore_per_giorno[giorno]["entrate"].append(t.get("ora"))
        elif t.get("tipo") == "uscita":
            ore_per_giorno[giorno]["uscite"].append(t.get("ora"))
    
    ore_totali = 0
    dettaglio_giorni = []
    
    for giorno, dati in ore_per_giorno.items():
        if dati["entrate"] and dati["uscite"]:
            try:
                prima_entrata = min(dati["entrate"])
                ultima_uscita = max(dati["uscite"])
                
                dt_entrata = datetime.strptime(prima_entrata, "%H:%M:%S")
                dt_uscita = datetime.strptime(ultima_uscita, "%H:%M:%S")
                
                delta = dt_uscita - dt_entrata
                ore = round(delta.total_seconds() / 3600, 2)
                ore_totali += ore
                
                dettaglio_giorni.append({
                    "data": giorno,
                    "entrata": prima_entrata,
                    "uscita": ultima_uscita,
                    "ore": ore
                })
            except Exception:
                pass
    
    return {
        "success": True,
        "employee_id": employee_id,
        "anno": anno,
        "mese": mese,
        "ore_totali": round(ore_totali, 2),
        "giorni_lavorati": len(dettaglio_giorni),
        "dettaglio": sorted(dettaglio_giorni, key=lambda x: x["data"])
    }


@router.get("/storico-ore/{employee_id}")
@handle_errors
async def get_storico_ore(
    employee_id: str,
    anno: int = Query(None)
) -> Dict[str, Any]:
    """Storico ore lavorate per mese."""
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    storico = []
    for mese in range(1, 13):
        result = await get_ore_lavorate(employee_id, mese, anno)
        storico.append({
            "mese": mese,
            "ore_totali": result.get("ore_totali", 0),
            "giorni_lavorati": result.get("giorni_lavorati", 0)
        })
    
    return {
        "success": True,
        "employee_id": employee_id,
        "anno": anno,
        "storico": storico,
        "totale_anno": sum(m["ore_totali"] for m in storico)
    }


@router.post("/imposta-tutti-presenti")
@handle_errors
async def imposta_tutti_presenti(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Imposta tutti i giorni lavorativi come 'presente' per tutti i dipendenti.
    Salta weekend e giorni che hanno già uno stato diverso da vuoto/riposo.
    """
    db = Database.get_db()
    
    anno = payload.get("anno", datetime.now().year)
    mese = payload.get("mese", datetime.now().month)
    employees = payload.get("employees", [])
    
    if not employees:
        # Recupera tutti i dipendenti attivi
        emps = await db["employees"].find(
            {"$or": [{"in_carico": True}, {"in_carico": {"$exists": False}}]},
            {"id": 1}
        ).to_list(500)
        employees = [e["id"] for e in emps]
    
    # Genera tutti i giorni del mese
    from calendar import monthrange
    _, num_giorni = monthrange(anno, mese)
    
    count_inseriti = 0
    count_saltati = 0
    
    for emp_id in employees:
        for giorno in range(1, num_giorni + 1):
            data_str = f"{anno}-{mese:02d}-{giorno:02d}"
            
            # Verifica se è weekend
            data_obj = datetime(anno, mese, giorno)
            if data_obj.weekday() >= 5:  # 5=Sabato, 6=Domenica
                count_saltati += 1
                continue
            
            # Verifica se esiste già una presenza
            existing = await db["attendance_presenze_calendario"].find_one({
                "employee_id": emp_id,
                "data": data_str
            })
            
            if existing and existing.get("stato") not in [None, "", "riposo"]:
                count_saltati += 1
                continue
            
            # Inserisci/aggiorna come presente
            await db["attendance_presenze_calendario"].update_one(
                {"employee_id": emp_id, "data": data_str},
                {"$set": {
                    "employee_id": emp_id,
                    "data": data_str,
                    "stato": "presente",
                    "updated_at": datetime.now(timezone.utc),
                    "auto_inserted": True
                }},
                upsert=True
            )
            count_inseriti += 1
    
    return {
        "success": True,
        "message": f"Presenze impostate: {count_inseriti} giorni, {count_saltati} saltati",
        "inseriti": count_inseriti,
        "saltati": count_saltati,
        "dipendenti": len(employees),
        "anno": anno,
        "mese": mese
    }


@router.get("/turni")
@handle_errors
async def get_turni(
    anno: int = Query(datetime.now().year),
    mese: int = Query(datetime.now().month)
) -> Dict[str, Any]:
    """Ottiene i turni assegnati per mese."""
    db = Database.get_db()
    
    turni_list = await db["attendance_turni"].find(
        {"anno": anno, "mese": mese},
        {"_id": 0}
    ).to_list(500)
    
    # Converti in dizionario
    turni_dict = {}
    for t in turni_list:
        key = f"{t.get('mansione_id')}_{t.get('employee_id')}"
        turni_dict[key] = True
    
    return {"turni": turni_dict, "anno": anno, "mese": mese}


@router.post("/turni/assegna")
@handle_errors
async def assegna_turno(payload: Dict[str, Any]) -> Dict[str, str]:
    """Assegna un dipendente a un turno/mansione."""
    db = Database.get_db()
    
    doc = {
        "employee_id": payload.get("employee_id"),
        "mansione_id": payload.get("mansione_id"),
        "anno": payload.get("anno", datetime.now().year),
        "mese": payload.get("mese", datetime.now().month),
        "created_at": datetime.now(timezone.utc)
    }
    
    await db["attendance_turni"].update_one(
        {
            "employee_id": doc["employee_id"],
            "mansione_id": doc["mansione_id"],
            "anno": doc["anno"],
            "mese": doc["mese"]
        },
        {"$set": doc},
        upsert=True
    )
    
    return {"message": "Turno assegnato"}


@router.delete("/turni/rimuovi")
@handle_errors
async def rimuovi_turno(
    employee_id: str = Query(...),
    mansione_id: str = Query(...)
) -> Dict[str, str]:
    """Rimuove un dipendente da un turno/mansione."""
    db = Database.get_db()
    
    await db["attendance_turni"].delete_one({
        "employee_id": employee_id,
        "mansione_id": mansione_id
    })
    
    return {"message": "Turno rimosso"}