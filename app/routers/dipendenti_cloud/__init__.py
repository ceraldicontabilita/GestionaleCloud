"""
Dipendenti in Cloud - Router Module
Sistema HR completo per gestione personale
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone

from app.database import Database

# Router principale
router = APIRouter(prefix="/dipendenti-cloud", tags=["Dipendenti Cloud"])

# ============ HELPERS ============

def get_db():
    """Get database instance"""
    return Database.get_db()

def generate_id():
    return str(uuid.uuid4())

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def serialize_doc(doc):
    if doc and '_id' in doc:
        del doc['_id']
    return doc

# ============ MODELS ============

class DipendenteCloud(BaseModel):
    nome: str
    cognome: str
    matricola: Optional[str] = None
    codice_fiscale: Optional[str] = None
    data_nascita: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    indirizzo: Optional[str] = None
    ruolo: Optional[str] = None
    luogo_lavoro: Optional[str] = None
    contratto: str = "Indeterminato"
    data_assunzione: Optional[str] = None
    data_fine_contratto: Optional[str] = None
    iban: Optional[str] = None
    stato: str = "attivo"

class PresenzaCloud(BaseModel):
    dipendente_id: str
    data: str
    entrata: Optional[str] = None
    uscita: Optional[str] = None
    stato: str = "presente"
    giustificativo: Optional[str] = None
    ore_lavorate: float = 0
    note: Optional[str] = None

class FerieCloud(BaseModel):
    dipendente_id: str
    tipo: str  # Ferie, Permesso, Malattia, ROL
    data_inizio: str
    data_fine: str
    giorni: int = 1
    stato: str = "in_attesa"
    nota: Optional[str] = None

class TurnoCloud(BaseModel):
    nome: str
    orario_inizio: str
    orario_fine: str
    colore: str = "#3b82f6"

class BustaPagaCloud(BaseModel):
    dipendente_id: str
    mese: int
    anno: int
    lordo: float
    netto: float
    inps: float = 0
    irpef: float = 0
    trattenute: float = 0
    stato: str = "DA_PAGARE"
    data_pagamento: Optional[str] = None

class MissioneCloud(BaseModel):
    dipendente_id: str
    destinazione: str
    data_inizio: str
    data_fine: str
    scopo: str
    rimborso: float = 0
    stato: str = "in_attesa"

class DocumentoCloud(BaseModel):
    dipendente_id: str
    titolo: str
    tipo: str
    scadenza: Optional[str] = None
    file_url: Optional[str] = None

# ============ DIPENDENTI ============

@router.get("/dipendenti")
async def get_dipendenti():
    dipendenti = await get_db().dipendenti_cloud.find({}, {"_id": 0}).to_list(1000)
    return dipendenti

@router.get("/dipendenti/{dipendente_id}")
async def get_dipendente(dipendente_id: str):
    dip = await get_db().dipendenti_cloud.find_one({"id": dipendente_id}, {"_id": 0})
    if not dip:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    return dip

@router.post("/dipendenti")
async def create_dipendente(dip: DipendenteCloud):
    dip_dict = dip.model_dump()
    dip_dict["id"] = generate_id()
    dip_dict["created_at"] = now_iso()
    await get_db().dipendenti_cloud.insert_one(dip_dict)
    return serialize_doc(dip_dict)

@router.put("/dipendenti/{dipendente_id}")
async def update_dipendente(dipendente_id: str, dip: DipendenteCloud):
    result = await get_db().dipendenti_cloud.update_one(
        {"id": dipendente_id},
        {"$set": dip.model_dump()}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    return {"message": "Dipendente aggiornato"}

@router.delete("/dipendenti/{dipendente_id}")
async def delete_dipendente(dipendente_id: str):
    result = await get_db().dipendenti_cloud.delete_one({"id": dipendente_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    return {"message": "Dipendente eliminato"}

# ============ PRESENZE ============

@router.get("/presenze")
async def get_presenze(anno: Optional[int] = None, mese: Optional[int] = None, dipendente_id: Optional[str] = None):
    """
    Recupera presenze dalla collezione 'presenze' (dati storici).
    Combina dati storici con nuovi inserimenti in presenze_cloud.
    """
    query = {}
    if dipendente_id:
        query["dipendente_id"] = dipendente_id
    if anno and mese:
        query["data"] = {"$regex": f"^{anno}-{str(mese).zfill(2)}"}
    
    # Leggi da entrambe le collezioni e combina
    presenze_cloud = await get_db().presenze_cloud.find(query, {"_id": 0}).to_list(5000)
    presenze_storiche = await get_db().presenze.find(query, {"_id": 0}).to_list(5000)
    
    # Crea un set di date già presenti in cloud per evitare duplicati
    cloud_keys = {(p.get("dipendente_id"), p.get("data")) for p in presenze_cloud}
    
    # Aggiungi presenze storiche se non già in cloud
    result = list(presenze_cloud)
    for p in presenze_storiche:
        key = (p.get("dipendente_id"), p.get("data"))
        if key not in cloud_keys:
            result.append({
                "id": p.get("id", ""),
                "dipendente_id": p.get("dipendente_id", ""),
                "data": p.get("data", ""),
                "entrata": p.get("entrata"),
                "uscita": p.get("uscita"),
                "stato": p.get("stato", "presente"),
                "giustificativo": p.get("giustificativo"),
                "ore_lavorate": p.get("ore_lavorate", 0),
                "note": p.get("note", "")
            })
    
    return result

@router.post("/presenze")
async def create_presenza(presenza: PresenzaCloud):
    pres_dict = presenza.model_dump()
    pres_dict["id"] = generate_id()
    pres_dict["created_at"] = now_iso()
    
    # Calculate hours worked
    if pres_dict.get("entrata") and pres_dict.get("uscita"):
        try:
            ent = datetime.strptime(pres_dict["entrata"], "%H:%M")
            usc = datetime.strptime(pres_dict["uscita"], "%H:%M")
            pres_dict["ore_lavorate"] = round((usc - ent).seconds / 3600, 2)
        except:
            pass
    
    await get_db().presenze_cloud.insert_one(pres_dict)
    return serialize_doc(pres_dict)

@router.put("/presenze/{presenza_id}")
async def update_presenza(presenza_id: str, presenza: PresenzaCloud):
    pres_dict = presenza.model_dump()
    
    if pres_dict.get("entrata") and pres_dict.get("uscita"):
        try:
            ent = datetime.strptime(pres_dict["entrata"], "%H:%M")
            usc = datetime.strptime(pres_dict["uscita"], "%H:%M")
            pres_dict["ore_lavorate"] = round((usc - ent).seconds / 3600, 2)
        except:
            pass
    
    result = await get_db().presenze_cloud.update_one(
        {"id": presenza_id},
        {"$set": pres_dict}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Presenza non trovata")
    return {"message": "Presenza aggiornata"}

@router.delete("/presenze/{presenza_id}")
async def delete_presenza(presenza_id: str):
    result = await get_db().presenze_cloud.delete_one({"id": presenza_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Presenza non trovata")
    return {"message": "Presenza eliminata"}

@router.post("/presenze/batch")
async def create_presenze_batch(presenze: List[PresenzaCloud]):
    created = []
    for p in presenze:
        pres_dict = p.model_dump()
        pres_dict["id"] = generate_id()
        pres_dict["created_at"] = now_iso()
        
        existing = await get_db().presenze_cloud.find_one({
            "dipendente_id": pres_dict["dipendente_id"],
            "data": pres_dict["data"]
        })
        
        if existing:
            await get_db().presenze_cloud.update_one(
                {"id": existing["id"]},
                {"$set": pres_dict}
            )
        else:
            await get_db().presenze_cloud.insert_one(pres_dict)
        created.append(pres_dict)
    
    return {"message": f"Inserite/aggiornate {len(created)} presenze"}

# ============ FERIE E PERMESSI ============

@router.get("/ferie")
async def get_ferie(dipendente_id: Optional[str] = None, stato: Optional[str] = None):
    query = {}
    if dipendente_id:
        query["dipendente_id"] = dipendente_id
    if stato:
        query["stato"] = stato
    ferie = await get_db().ferie_cloud.find(query, {"_id": 0}).to_list(1000)
    return ferie

@router.post("/ferie")
async def create_ferie(ferie: FerieCloud):
    ferie_dict = ferie.model_dump()
    ferie_dict["id"] = generate_id()
    ferie_dict["created_at"] = now_iso()
    await get_db().ferie_cloud.insert_one(ferie_dict)
    return serialize_doc(ferie_dict)

@router.put("/ferie/{ferie_id}/approva")
async def approva_ferie(ferie_id: str):
    result = await get_db().ferie_cloud.update_one(
        {"id": ferie_id},
        {"$set": {"stato": "approvata"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    return {"message": "Richiesta approvata"}

@router.put("/ferie/{ferie_id}/rifiuta")
async def rifiuta_ferie(ferie_id: str):
    result = await get_db().ferie_cloud.update_one(
        {"id": ferie_id},
        {"$set": {"stato": "rifiutata"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    return {"message": "Richiesta rifiutata"}

@router.delete("/ferie/{ferie_id}")
async def delete_ferie(ferie_id: str):
    result = await get_db().ferie_cloud.delete_one({"id": ferie_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    return {"message": "Richiesta eliminata"}

# ============ TURNI ============

@router.get("/turni")
async def get_turni():
    turni = await get_db().turni_cloud.find({}, {"_id": 0}).to_list(100)
    return turni

@router.post("/turni")
async def create_turno(turno: TurnoCloud):
    turno_dict = turno.model_dump()
    turno_dict["id"] = generate_id()
    await get_db().turni_cloud.insert_one(turno_dict)
    return serialize_doc(turno_dict)

@router.put("/turni/{turno_id}")
async def update_turno(turno_id: str, turno: TurnoCloud):
    result = await get_db().turni_cloud.update_one(
        {"id": turno_id},
        {"$set": turno.model_dump()}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Turno non trovato")
    return {"message": "Turno aggiornato"}

@router.delete("/turni/{turno_id}")
async def delete_turno(turno_id: str):
    result = await get_db().turni_cloud.delete_one({"id": turno_id})
    await get_db().assegnazioni_turni_cloud.delete_many({"turno_id": turno_id})
    return {"message": "Turno eliminato"}

@router.get("/assegnazioni-turni")
async def get_assegnazioni():
    assegnazioni = await get_db().assegnazioni_turni_cloud.find({}, {"_id": 0}).to_list(1000)
    return assegnazioni

@router.post("/assegnazioni-turni")
async def create_or_update_assegnazione(data: dict):
    dipendente_id = data.get("dipendente_id")
    giorno = data.get("giorno")
    turno_id = data.get("turno_id")
    
    if not dipendente_id or not giorno:
        raise HTTPException(status_code=400, detail="dipendente_id e giorno sono obbligatori")
    
    existing = await get_db().assegnazioni_turni_cloud.find_one({
        "dipendente_id": dipendente_id,
        "giorno": giorno
    })
    
    if turno_id:
        if existing:
            await get_db().assegnazioni_turni_cloud.update_one(
                {"id": existing["id"]},
                {"$set": {"turno_id": turno_id}}
            )
        else:
            ass = {
                "id": generate_id(),
                "dipendente_id": dipendente_id,
                "giorno": giorno,
                "turno_id": turno_id
            }
            await get_db().assegnazioni_turni_cloud.insert_one(ass)
    else:
        if existing:
            await get_db().assegnazioni_turni_cloud.delete_one({"id": existing["id"]})
    
    return {"message": "Assegnazione salvata"}

# ============ BUSTE PAGA ============

@router.get("/buste-paga")
async def get_buste_paga(anno: Optional[int] = None, mese: Optional[int] = None, dipendente_id: Optional[str] = None):
    """
    Recupera cedolini dalla collezione 'cedolini' (dati storici dal 2014).
    Se dipendente_id è fornito, cerca anche per nome del dipendente in dipendenti_cloud.
    """
    query = {}
    if anno:
        query["anno"] = anno
    if mese:
        query["mese"] = mese
    
    # Se abbiamo un dipendente_id, dobbiamo trovare il nome per cercare nei cedolini
    if dipendente_id:
        dip = await get_db().dipendenti_cloud.find_one({"id": dipendente_id})
        if dip:
            nome_completo = f"{dip.get('nome', '')} {dip.get('cognome', '')}".strip().upper()
            query["$or"] = [
                {"dipendente_id": dipendente_id},
                {"nome_dipendente": {"$regex": dip.get('cognome', ''), "$options": "i"}}
            ]
    
    # Leggi dalla collezione cedolini (dati storici)
    cedolini = await get_db().cedolini.find(query, {"_id": 0}).sort([("anno", -1), ("mese", -1)]).to_list(1000)
    
    # Normalizza i campi per compatibilità con il frontend
    result = []
    for c in cedolini:
        result.append({
            "id": c.get("id", str(c.get("_id", ""))),
            "dipendente_id": c.get("dipendente_id", ""),
            "dipendente_nome": c.get("nome_dipendente") or c.get("dipendente_nome") or "",
            "mese": c.get("mese"),
            "anno": c.get("anno"),
            "lordo": c.get("lordo", 0),
            "netto": c.get("netto", 0),
            "inps": c.get("inps_dipendente", 0),
            "irpef": c.get("irpef", 0),
            "trattenute": c.get("trattenute", 0),
            "stato": c.get("stato_pagamento") or c.get("stato") or "DA_PAGARE",
            "created_at": c.get("created_at", "")
        })
    
    return result

@router.post("/buste-paga")
async def create_busta_paga(busta: BustaPagaCloud):
    busta_dict = busta.model_dump()
    busta_dict["id"] = generate_id()
    busta_dict["created_at"] = now_iso()
    await get_db().buste_paga_cloud.insert_one(busta_dict)
    return serialize_doc(busta_dict)

@router.post("/buste-paga/genera")
async def genera_buste_paga(data: dict):
    """Genera buste paga per tutti i dipendenti attivi per un mese specifico"""
    mese = data.get("mese")
    anno = data.get("anno")
    lordo_default = data.get("lordo", 1500)
    
    if not mese or not anno:
        raise HTTPException(status_code=400, detail="mese e anno sono obbligatori")
    
    dipendenti = await get_db().dipendenti_cloud.find({"stato": "attivo"}, {"_id": 0}).to_list(1000)
    created = 0
    
    for dip in dipendenti:
        existing = await get_db().buste_paga_cloud.find_one({
            "dipendente_id": dip["id"],
            "mese": mese,
            "anno": anno
        })
        
        if not existing:
            inps = round(lordo_default * 0.0919, 2)
            irpef = round((lordo_default - inps) * 0.23, 2)
            netto = round(lordo_default - inps - irpef, 2)
            
            busta = {
                "id": generate_id(),
                "dipendente_id": dip["id"],
                "mese": mese,
                "anno": anno,
                "lordo": lordo_default,
                "inps": inps,
                "irpef": irpef,
                "trattenute": 0,
                "netto": netto,
                "stato": "DA_PAGARE",
                "created_at": now_iso()
            }
            await get_db().buste_paga_cloud.insert_one(busta)
            created += 1
    
    return {"message": f"Generate {created} buste paga"}

@router.put("/buste-paga/{busta_id}/paga")
async def paga_busta(busta_id: str):
    result = await get_db().buste_paga_cloud.update_one(
        {"id": busta_id},
        {"$set": {"stato": "PAGATO", "data_pagamento": now_iso()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Busta paga non trovata")
    return {"message": "Busta paga marcata come pagata"}

# ============ MISSIONI ============

@router.get("/missioni")
async def get_missioni(dipendente_id: Optional[str] = None, stato: Optional[str] = None):
    query = {}
    if dipendente_id:
        query["dipendente_id"] = dipendente_id
    if stato:
        query["stato"] = stato
    missioni = await get_db().missioni_cloud.find(query, {"_id": 0}).to_list(1000)
    return missioni

@router.post("/missioni")
async def create_missione(missione: MissioneCloud):
    miss_dict = missione.model_dump()
    miss_dict["id"] = generate_id()
    miss_dict["created_at"] = now_iso()
    await get_db().missioni_cloud.insert_one(miss_dict)
    return serialize_doc(miss_dict)

@router.put("/missioni/{missione_id}/approva")
async def approva_missione(missione_id: str):
    result = await get_db().missioni_cloud.update_one(
        {"id": missione_id},
        {"$set": {"stato": "approvata"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Missione non trovata")
    return {"message": "Missione approvata"}

@router.delete("/missioni/{missione_id}")
async def delete_missione(missione_id: str):
    result = await get_db().missioni_cloud.delete_one({"id": missione_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Missione non trovata")
    return {"message": "Missione eliminata"}

# ============ DOCUMENTI ============

@router.get("/documenti")
async def get_documenti(dipendente_id: Optional[str] = None):
    query = {}
    if dipendente_id:
        query["dipendente_id"] = dipendente_id
    documenti = await get_db().documenti_cloud.find(query, {"_id": 0}).to_list(1000)
    return documenti

@router.post("/documenti")
async def create_documento(doc: DocumentoCloud):
    doc_dict = doc.model_dump()
    doc_dict["id"] = generate_id()
    doc_dict["data_caricamento"] = now_iso()
    await get_db().documenti_cloud.insert_one(doc_dict)
    return serialize_doc(doc_dict)

@router.delete("/documenti/{documento_id}")
async def delete_documento(documento_id: str):
    result = await get_db().documenti_cloud.delete_one({"id": documento_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    return {"message": "Documento eliminato"}

# ============ DASHBOARD STATS ============

@router.get("/dashboard/stats")
async def get_dashboard_stats():
    dipendenti = await get_db().dipendenti_cloud.find({}, {"_id": 0}).to_list(1000)
    attivi = [d for d in dipendenti if d.get("stato") == "attivo"]
    
    ferie_pending = await get_db().ferie_cloud.count_documents({"stato": "in_attesa"})
    missioni_pending = await get_db().missioni_cloud.count_documents({"stato": "in_attesa"})
    
    # Presenze oggi
    today = datetime.now().strftime("%Y-%m-%d")
    presenze_oggi = await get_db().presenze_cloud.count_documents({"data": today, "stato": "presente"})
    
    return {
        "totale_dipendenti": len(dipendenti),
        "dipendenti_attivi": len(attivi),
        "ferie_in_attesa": ferie_pending,
        "missioni_in_attesa": missioni_pending,
        "presenze_oggi": presenze_oggi
    }

# ============ SEED DATA ============

@router.post("/seed-data")
async def seed_data():
    """Crea dati di esempio se non esistono"""
    existing = await get_db().dipendenti_cloud.count_documents({})
    if existing > 0:
        return {"message": "Dati già presenti"}
    
    # Crea dipendenti di esempio
    dipendenti_sample = [
        {"nome": "Mario", "cognome": "Rossi", "ruolo": "Responsabile", "stato": "attivo", "contratto": "Indeterminato"},
        {"nome": "Lucia", "cognome": "Bianchi", "ruolo": "Cameriere", "stato": "attivo", "contratto": "Determinato"},
        {"nome": "Giuseppe", "cognome": "Verdi", "ruolo": "Barista", "stato": "attivo", "contratto": "Indeterminato"},
    ]
    
    for d in dipendenti_sample:
        d["id"] = generate_id()
        d["created_at"] = now_iso()
        await get_db().dipendenti_cloud.insert_one(d)
    
    # Crea turni di esempio
    turni_sample = [
        {"nome": "Mattina", "orario_inizio": "06:00", "orario_fine": "14:00", "colore": "#3b82f6"},
        {"nome": "Pomeriggio", "orario_inizio": "14:00", "orario_fine": "22:00", "colore": "#10b981"},
        {"nome": "Notte", "orario_inizio": "22:00", "orario_fine": "06:00", "colore": "#8b5cf6"},
    ]
    
    for t in turni_sample:
        t["id"] = generate_id()
        await get_db().turni_cloud.insert_one(t)
    
    return {"message": "Dati di esempio creati"}
