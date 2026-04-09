"""
Router Sanificazione HACCP — Attrezzature e Apparecchi Refrigeranti.
Adattato da tracciabilita/backend/routers/sanificazione.py
Prefix: /api/tr/sanificazione
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
from datetime import datetime, timezone, date, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid, random

from app.database import get_database
from app.tr_utils import get_chiusure_obbligatorie

router = APIRouter(prefix="/sanificazione", tags=["Tracciabilità - Sanificazione"])

OPERATORE_SANIFICAZIONE = "SANKAPALA ARACHCHILAGE JANANIE AYACHANA DISSANAYAKA"

ATTREZZATURE_SANIFICAZIONE = [
    "Lavabo, Forno, Banchi, Cappa, Frigo, Friggitrice, Affettatrice, Piastra",
    "Pavimentazione", "Tagliere, Coltelli",
    "Lavabo, Macch.Espresso, Macinino, Banco Erogatore, Banco Frigo, Scaffali, Vetrine",
    "Attrezzature Laboratorio", "Attrezzature Bar", "Montacarichi", "Deposito"
]

MESI_IT = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno",
           "Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"]

class AggiornaSchedaRequest(BaseModel):
    registrazioni: Dict[str, Dict[str, str]]
    operatore: str = ""


def genera_calendario_sanificazione_anno(anno: int) -> dict:
    random.seed(anno * 12345)
    oggi = date.today()
    fine_anno = min(date(anno, 12, 31), oggi)
    date_occupate = set()
    risultato = {"frigoriferi": {str(i): [] for i in range(1, 13)},
                 "congelatori": {str(i): [] for i in range(1, 13)}}
    apparecchi = []
    for i in range(1, 13):
        apparecchi.append(("frigoriferi", i))
        apparecchi.append(("congelatori", i))
    random.shuffle(apparecchi)
    for tipo, num in apparecchi:
        chiave = str(num)
        offset = random.randint(0, 6)
        data_corrente = date(anno, 1, 1) + timedelta(days=offset)
        while data_corrente <= fine_anno:
            data_assegnata = None
            for t in range(4):
                dp = data_corrente + timedelta(days=t)
                if dp <= fine_anno and dp not in date_occupate:
                    data_assegnata = dp
                    break
            if data_assegnata:
                eseguita = random.random() > 0.10
                risultato[tipo][chiave].append({
                    "data": data_assegnata.strftime("%d/%m/%Y"),
                    "giorno": data_assegnata.day, "mese": data_assegnata.month,
                    "eseguita": eseguita, "operatore": OPERATORE_SANIFICAZIONE,
                    "note": "" if eseguita else "Pulizia non eseguita",
                    "prodotto": "Detergente alimentare professionale" if eseguita else ""
                })
                date_occupate.add(data_assegnata)
            data_corrente += timedelta(days=random.randint(7, 10))
    return risultato


async def _get_or_create_apparecchi(db, anno: int) -> dict:
    scheda = await db["sanificazione_apparecchi"].find_one({"anno": anno}, {"_id": 0})
    if not scheda:
        cal = genera_calendario_sanificazione_anno(anno)
        scheda = {"id": str(uuid.uuid4()), "anno": anno,
                  "azienda": "Ceraldi Group S.R.L.", "operatore": OPERATORE_SANIFICAZIONE,
                  "registrazioni_frigoriferi": cal["frigoriferi"],
                  "registrazioni_congelatori": cal["congelatori"],
                  "created_at": datetime.now(timezone.utc).isoformat(),
                  "updated_at": datetime.now(timezone.utc).isoformat()}
        await db["sanificazione_apparecchi"].insert_one(scheda)
    if "_id" in scheda: del scheda["_id"]
    return scheda


async def _get_or_create_scheda(db, mese: int, anno: int) -> dict:
    scheda = await db["sanificazione_schede"].find_one({"mese": mese, "anno": anno}, {"_id": 0})
    if not scheda:
        scheda = {"id": str(uuid.uuid4()), "mese": mese, "anno": anno,
                  "azienda": "Ceraldi Group S.R.L.", "area": "Sala e Servizi",
                  "registrazioni": {attr: {} for attr in ATTREZZATURE_SANIFICAZIONE},
                  "operatore_responsabile": OPERATORE_SANIFICAZIONE,
                  "created_at": datetime.now(timezone.utc).isoformat(),
                  "updated_at": datetime.now(timezone.utc).isoformat()}
        await db["sanificazione_schede"].insert_one(scheda)
    if "_id" in scheda: del scheda["_id"]
    return scheda


# ── Attrezzature ───────────────────────────────────────────────────────────

@router.get("/scheda/{anno}/{mese}")
async def get_scheda_mensile(anno: int, mese: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    return await _get_or_create_scheda(db, mese, anno)

@router.put("/scheda/{anno}/{mese}")
async def aggiorna_scheda(anno: int, mese: int, data: AggiornaSchedaRequest,
                           db: AsyncIOMotorDatabase = Depends(get_database)):
    scheda = await _get_or_create_scheda(db, mese, anno)
    scheda["registrazioni"] = data.registrazioni
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()
    if data.operatore: scheda["operatore_responsabile"] = data.operatore
    await db["sanificazione_schede"].update_one({"mese": mese, "anno": anno}, {"$set": scheda})
    return {"success": True}

@router.post("/giorno-completo")
async def giorno_completo(anno: int = Query(...), mese: int = Query(...), giorno: int = Query(...),
                           operatore: str = Query(default=""),
                           db: AsyncIOMotorDatabase = Depends(get_database)):
    scheda = await _get_or_create_scheda(db, mese, anno)
    for attr in scheda["registrazioni"]:
        scheda["registrazioni"][attr][str(giorno)] = "X"
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db["sanificazione_schede"].update_one({"mese": mese, "anno": anno}, {"$set": scheda})
    return {"success": True}

@router.get("/attrezzature")
async def get_attrezzature():
    return ATTREZZATURE_SANIFICAZIONE

# ── Apparecchi Refrigeranti ────────────────────────────────────────────────

@router.get("/apparecchi/{anno}")
async def get_apparecchi(anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    return await _get_or_create_apparecchi(db, anno)

@router.get("/apparecchi/{anno}/mese/{mese}")
async def get_apparecchi_mese(anno: int, mese: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    scheda = await _get_or_create_apparecchi(db, anno)
    result = {"frigoriferi": {}, "congelatori": {}}
    for chiave, sanifs in scheda.get("registrazioni_frigoriferi", {}).items():
        sm = [s for s in sanifs if s.get("mese") == mese]
        if sm: result["frigoriferi"][chiave] = sm
    for chiave, sanifs in scheda.get("registrazioni_congelatori", {}).items():
        sm = [s for s in sanifs if s.get("mese") == mese]
        if sm: result["congelatori"][chiave] = sm
    return {"anno": anno, "mese": mese, "sanificazioni": result}

@router.post("/apparecchi/{anno}/registra")
async def registra_apparecchio(anno: int, tipo: str = Query(...), numero: int = Query(...),
                                giorno: int = Query(...), mese: int = Query(...),
                                eseguita: bool = Query(default=True), note: str = Query(default=""),
                                db: AsyncIOMotorDatabase = Depends(get_database)):
    scheda = await _get_or_create_apparecchi(db, anno)
    chiave = str(numero)
    reg = {"data": f"{giorno:02d}/{mese:02d}/{anno}", "giorno": giorno, "mese": mese,
           "eseguita": eseguita, "operatore": OPERATORE_SANIFICAZIONE, "note": note,
           "prodotto": "Detergente alimentare professionale" if eseguita else "",
           "timestamp": datetime.now(timezone.utc).isoformat()}
    campo = "registrazioni_frigoriferi" if tipo == "frigorifero" else "registrazioni_congelatori"
    if chiave not in scheda[campo]: scheda[campo][chiave] = []
    scheda[campo][chiave].append(reg)
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db["sanificazione_apparecchi"].update_one({"anno": anno}, {"$set": scheda})
    return {"success": True}

@router.get("/statistiche/{anno}")
async def statistiche(anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    scheda = await _get_or_create_apparecchi(db, anno)
    tf = sum(len(v) for v in scheda.get("registrazioni_frigoriferi", {}).values())
    ef = sum(len([s for s in v if s.get("eseguita")]) for v in scheda.get("registrazioni_frigoriferi", {}).values())
    tc = sum(len(v) for v in scheda.get("registrazioni_congelatori", {}).values())
    ec = sum(len([s for s in v if s.get("eseguita")]) for v in scheda.get("registrazioni_congelatori", {}).values())
    return {"anno": anno, "frigoriferi": {"totale": tf, "eseguite": ef},
            "congelatori": {"totale": tc, "eseguite": ec},
            "totale": {"programmate": tf+tc, "eseguite": ef+ec}}

@router.get("/export-pdf/{anno}/{mese}", response_class=HTMLResponse)
async def export_pdf(anno: int, mese: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    scheda = await db["sanificazione_schede"].find_one({"mese": mese, "anno": anno}, {"_id": 0})
    if not scheda: scheda = {"registrazioni": {}, "operatore_responsabile": OPERATORE_SANIFICAZIONE}
    reg = scheda.get("registrazioni", {})
    ng = 31 if mese in [1,3,5,7,8,10,12] else 30 if mese in [4,6,9,11] else (29 if (anno%4==0 and anno%100!=0) or anno%400==0 else 28)
    html = f'<html><head><title>Sanificazione {MESI_IT[mese-1]} {anno}</title><style>body{{font:9pt Arial}}table{{width:100%;border-collapse:collapse}}th,td{{border:1px solid #ddd;padding:3px;text-align:center;font-size:8pt}}th{{background:#1976d2;color:#fff}}.ck{{background:#e8f5e9;color:#2e7d32;font-weight:bold}}</style></head><body>'
    html += f'<h2>Sanificazione Attrezzature — {MESI_IT[mese-1]} {anno}</h2><p>Operatore: {scheda.get("operatore_responsabile","")}</p><table><tr><th>Attrezzatura</th>'
    for g in range(1, ng+1): html += f"<th>{g}</th>"
    html += "</tr>"
    for attr in ATTREZZATURE_SANIFICAZIONE:
        ga = reg.get(attr, {})
        html += f"<tr><td style='text-align:left'><b>{attr}</b></td>"
        for g in range(1, ng+1):
            v = ga.get(str(g), "")
            html += f"<td class='{'ck' if v=='X' else ''}'>{v}</td>"
        html += "</tr>"
    html += "</table></body></html>"
    return HTMLResponse(content=html)

# ── Popola dati ────────────────────────────────────────────────────────────

@router.post("/popola-attrezzature")
async def popola(start_anno: int = 2022, end_anno: int = 2025,
                  db: AsyncIOMotorDatabase = Depends(get_database)):
    oggi = date.today()
    cnt = 0
    for anno in range(start_anno, end_anno+1):
        random.seed(anno * 11111)
        chiusure = get_chiusure_obbligatorie(anno)
        dc = set((c["data"].month, c["data"].day) for c in chiusure)
        for mese in range(1, 13):
            ng = 31 if mese in [1,3,5,7,8,10,12] else 30 if mese in [4,6,9,11] else (29 if (anno%4==0 and anno%100!=0) or anno%400==0 else 28)
            reg = {attr: {} for attr in ATTREZZATURE_SANIFICAZIONE}
            for g in range(1, ng+1):
                d = date(anno, mese, g)
                if d > oggi or d.weekday() == 6 or (mese, g) in dc: continue
                for attr in ATTREZZATURE_SANIFICAZIONE:
                    if random.random() > 0.05: reg[attr][str(g)] = "X"
            scheda = {"id": str(uuid.uuid4()), "mese": mese, "anno": anno,
                      "azienda": "Ceraldi Group S.R.L.", "area": "Sala e Servizi",
                      "registrazioni": reg, "operatore_responsabile": OPERATORE_SANIFICAZIONE,
                      "created_at": datetime.now(timezone.utc).isoformat(),
                      "updated_at": datetime.now(timezone.utc).isoformat()}
            await db["sanificazione_schede"].update_one({"mese": mese, "anno": anno}, {"$set": scheda}, upsert=True)
            cnt += 1
    return {"success": True, "schede_aggiornate": cnt}

# Alias per compatibilità con vecchio frontend
@router.post("/haccp/popola-sanificazione")
async def popola_alias(anno: int = Query(2025), mese: int = Query(None),
                        db: AsyncIOMotorDatabase = Depends(get_database)):
    """Alias — il frontend chiama questo path."""
    return await popola(start_anno=anno, end_anno=anno, db=db)

@router.post("/scheda/{anno}/{mese}/giorno-completo")
async def giorno_completo_path(anno: int, mese: int, giorno: int = Query(...),
                                operatore: str = Query(default=""),
                                db: AsyncIOMotorDatabase = Depends(get_database)):
    """Alias con anno/mese nel path — usato dal frontend."""
    return await giorno_completo(anno=anno, mese=mese, giorno=giorno, operatore=operatore, db=db)
