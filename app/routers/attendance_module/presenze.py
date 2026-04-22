"""
ATTENDANCE - Presenze e Assenze
===============================
Gestione calendario presenze, assenze, ferie, permessi.
"""

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Body
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
    
    dipendenti = await db["dipendenti"].aggregate(pipeline).to_list(500)
    
    total = await db["dipendenti"].count_documents({})
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
async def set_presenza(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
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
    dipendenti = await db["dipendenti"].find(
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
async def crea_richiesta_assenza(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
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
    employee = await db["dipendenti"].find_one({"id": employee_id}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1})
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
async def rifiuta_richiesta_assenza(richiesta_id: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
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
async def imposta_tutti_presenti(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
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
        emps = await db["dipendenti"].find(
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
async def assegna_turno(payload: Dict[str, Any] = Body(...)) -> Dict[str, str]:
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


# =============================================================================
# PRESENZE DA LIBRO UNICO (collection "presenze")
# =============================================================================

@router.get("/libro-unico")
@handle_errors
async def get_presenze_libro_unico(
    anno: int = Query(None),
    mese: int = Query(None),
    codice_fiscale: str = Query(None),
) -> Dict[str, Any]:
    """
    Recupera le presenze dal Libro Unico del Lavoro (collection 'presenze').
    Questi dati vengono importati dal PDF del consulente del lavoro.
    """
    db = Database.get_db()
    
    query = {}
    if anno:
        query["anno"] = anno
    if mese:
        query["mese"] = mese
    if codice_fiscale:
        query["codice_fiscale"] = codice_fiscale
    
    presenze = await db["presenze"].find(
        query,
        {"_id": 0}
    ).sort([("anno", -1), ("mese", -1), ("cognome", 1)]).to_list(500)
    
    total = await db["presenze"].count_documents(query)
    
    # Statistiche
    anni_disponibili = await db["presenze"].distinct("anno")
    mesi_per_anno = {}
    for a in anni_disponibili:
        mesi = await db["presenze"].distinct("mese", {"anno": a})
        mesi_per_anno[str(a)] = sorted([m for m in mesi if m])
    
    return {
        "presenze": presenze,
        "total": total,
        "anni_disponibili": sorted([a for a in anni_disponibili if a], reverse=True),
        "mesi_per_anno": mesi_per_anno,
    }


@router.get("/libro-unico/riepilogo")
@handle_errors
async def get_riepilogo_presenze(anno: int = Query(None)) -> Dict[str, Any]:
    """Riepilogo ore per dipendente."""
    db = Database.get_db()
    
    query = {}
    if anno:
        query["anno"] = anno
    
    presenze = await db["presenze"].find(query, {"_id": 0}).to_list(500)
    
    riepilogo = {}
    for p in presenze:
        nome = f"{p.get('cognome', '')} {p.get('nome', '')}".strip()
        cf = p.get("codice_fiscale", "")
        key = cf or nome
        
        if key not in riepilogo:
            riepilogo[key] = {
                "nome": nome,
                "codice_fiscale": cf,
                "codice_dipendente": p.get("codice_dipendente", ""),
                "mesi": [],
                "ore_totali": 0,
                "giustificativi_totali": {},
            }
        
        totali = p.get("totali", {})
        ore = totali.get("ore_ordinarie", 0) or 0
        riepilogo[key]["ore_totali"] += ore
        riepilogo[key]["mesi"].append({
            "mese": p.get("mese"),
            "anno": p.get("anno"),
            "ore_ordinarie": ore,
            "giustificativi": {k: v for k, v in totali.items() if k != "ore_ordinarie"},
        })
        
        # Accumula giustificativi
        for k, v in totali.items():
            if k != "ore_ordinarie" and v:
                riepilogo[key]["giustificativi_totali"][k] = riepilogo[key]["giustificativi_totali"].get(k, 0) + v
    
    return {
        "dipendenti": list(riepilogo.values()),
        "total_dipendenti": len(riepilogo),
    }



# =============================================================================
# IMPORT PRESENZE DA PDF LIBRO UNICO
# =============================================================================

@router.post("/libro-unico/import-pdf")
@handle_errors
async def import_presenze_da_pdf(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Importa presenze giornaliere da PDF del Libro Unico del Lavoro.
    Estrae griglia giornaliera con ore e giustificativi per ogni dipendente.
    """
    import tempfile
    import calendar
    
    db = Database.get_db()
    
    if not hasattr(file, 'filename') or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Il file deve essere un PDF")
    
    # Salva file temporaneo
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        from app.routers.libro_unico_parser import parse_libro_unico_completo
        parsed = parse_libro_unico_completo(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Errore parsing PDF: {str(e)}")
    finally:
        import os
        os.unlink(tmp_path)
    
    dipendenti = parsed.get("dipendenti", [])
    if not dipendenti:
        return {"success": False, "message": "Nessun dipendente trovato nel PDF", "importati": 0}
    
    importati = 0
    aggiornati = 0
    errori = []
    
    MESI_LABEL = ['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']
    
    for dip_data in dipendenti:
        try:
            presenze_raw = dip_data.get("foglio_presenze", {}) or {}
            busta = dip_data.get("busta_paga", {}) or {}
            
            # Extract CF from either source
            cf = (presenze_raw.get("dipendente", {}).get("codice_fiscale") or 
                  busta.get("dipendente", {}).get("codice_fiscale"))
            
            if not cf:
                errori.append("Dipendente senza codice fiscale")
                continue
            
            # Extract name
            cognome_nome = (presenze_raw.get("dipendente", {}).get("cognome_nome") or
                           busta.get("dipendente", {}).get("cognome_nome") or "")
            parts = cognome_nome.split(maxsplit=1) if cognome_nome else []
            cognome = parts[0] if parts else ""
            nome = parts[1] if len(parts) > 1 else ""
            
            # Extract period
            periodo_str = presenze_raw.get("dipendente", {}).get("periodo") or ""
            anno = None
            mese = None
            
            MESI_IT = {
                'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4,
                'maggio': 5, 'giugno': 6, 'luglio': 7, 'agosto': 8,
                'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12
            }
            
            for mese_nome, mese_num in MESI_IT.items():
                if mese_nome in periodo_str.lower():
                    mese = mese_num
                    import re
                    anno_match = re.search(r'(\d{4})', periodo_str)
                    if anno_match:
                        anno = int(anno_match.group(1))
                    break
            
            if not anno or not mese:
                # Fallback: try to extract from filename
                # "Busta paga - Ariante Marcella - Gennaio 2025.pdf"
                import re as _re
                fname = file.filename if hasattr(file, 'filename') else ''
                for mese_nome, mese_num in MESI_IT.items():
                    if mese_nome in fname.lower():
                        mese = mese_num
                        anno_match = _re.search(r'(\d{4})', fname)
                        if anno_match:
                            anno = int(anno_match.group(1))
                        break
            
            if not anno or not mese:
                # Fallback 2: try from busta paga header text
                bp_text = ' '.join([str(v) for v in (busta.get("header", {}) or {}).values()])
                for mese_nome, mese_num in MESI_IT.items():
                    if mese_nome in bp_text.lower():
                        mese = mese_num
                        import re as _re2
                        anno_match = _re2.search(r'(\d{4})', bp_text)
                        if anno_match:
                            anno = int(anno_match.group(1))
                        break
            
            if not anno or not mese:
                errori.append(f"{cognome_nome}: periodo non riconosciuto '{periodo_str}'")
                continue
            
            # Build giorni array from parsed presenze
            presenze_parsed = presenze_raw.get("presenze", [])
            num_days = calendar.monthrange(anno, mese)[1]
            
            # Create a map of parsed days
            parsed_days = {}
            for p in presenze_parsed:
                day_num = p.get("giorno")
                if day_num:
                    parsed_days[day_num] = p
            
            # Build complete giorni array
            day_names = ['LU', 'MA', 'ME', 'GI', 'VE', 'SA', 'DO']
            giorni = []
            
            for day in range(1, num_days + 1):
                weekday = calendar.weekday(anno, mese, day)
                giorno_sett = day_names[weekday]
                is_festivo = giorno_sett in ('SA', 'DO')
                
                parsed = parsed_days.get(day, {})
                ore_raw = parsed.get("ore_ordinarie")
                giust_code = parsed.get("giustificativo")
                
                ore_ordinarie = 0.0
                giustificativi = []
                
                if ore_raw:
                    try:
                        ore_ordinarie = float(str(ore_raw).replace(',', '.'))
                    except Exception:
                        ore_ordinarie = 0.0
                
                # If there's a giustificativo code
                if giust_code:
                    giust_ore = ore_ordinarie if ore_ordinarie > 0 else 0.0
                    giustificativi.append({"codice": giust_code, "ore": giust_ore})
                    ore_ordinarie = 0.0  # Giustificativo hours are not ordinary hours
                
                giorni.append({
                    "giorno": day,
                    "giorno_settimana": giorno_sett,
                    "ore_ordinarie": ore_ordinarie,
                    "giustificativi": giustificativi,
                    "festivo": is_festivo,
                })
            
            # Build totali from riepilogo
            totali = {}
            legenda = {}
            for riep in presenze_raw.get("riepilogo_giustificativi", []):
                codice = riep.get("codice", "")
                desc = riep.get("descrizione", "")
                qty = riep.get("quantita", "0")
                try:
                    qty_float = float(str(qty).replace(',', '.'))
                except Exception:
                    qty_float = 0.0
                
                if not codice and "ore ordinarie" in desc.lower():
                    totali["ore_ordinarie"] = qty_float
                elif codice:
                    totali[codice] = qty_float
                    legenda[codice] = desc
            
            # Dedup key
            dedup_key = f"{cf}_{mese:02d}_{anno}"
            
            # Check if exists
            existing = await db["presenze"].find_one({"dedup_key": dedup_key})
            
            presenza = {
                "anno": anno,
                "mese": mese,
                "codice_fiscale": cf,
                "codice_dipendente": presenze_raw.get("dipendente", {}).get("codice", ""),
                "cognome": cognome,
                "nome": nome,
                "cessato": False,
                "data_cessazione": "",
                "filename": file.filename if hasattr(file, 'filename') else "upload.pdf",
                "indirizzo": presenze_raw.get("dipendente", {}).get("indirizzo", ""),
                "dedup_key": dedup_key,
                "giorni": giorni,
                "totali": totali,
                "legenda": legenda,
                "periodo_label": f"{MESI_LABEL[mese-1]} {anno}",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "source": "pdf_libro_unico",
                "giorni_estratti_dal_pdf": len(presenze_parsed),
            }
            
            if existing:
                await db["presenze"].update_one(
                    {"dedup_key": dedup_key},
                    {"$set": presenza}
                )
                aggiornati += 1
            else:
                await db["presenze"].insert_one(presenza)
                importati += 1
                
        except Exception as e:
            errori.append(f"Errore: {str(e)}")
    
    return {
        "success": True,
        "importati": importati,
        "aggiornati": aggiornati,
        "errori": len(errori),
        "dettagli_errori": errori[:10],
        "message": f"Import completato: {importati} nuovi, {aggiornati} aggiornati" + (f", {len(errori)} errori" if errori else "")
    }
