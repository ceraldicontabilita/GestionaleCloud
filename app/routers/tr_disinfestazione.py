"""
Router Disinfestazione HACCP — Interventi mensili e monitoraggio apparecchi.
Adattato da tracciabilita/backend/routers/disinfestazione.py
Prefix: /api/tr/disinfestazione
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Dict, List, Optional
from datetime import datetime, timezone, date
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid, random

from app.database import get_database

router = APIRouter(prefix="/disinfestazione", tags=["Tracciabilità - Disinfestazione"])

APPARECCHI_MONITORAGGIO = {
    "frigoriferi": [f"Frigorifero N°{i}" for i in range(1, 13)],
    "congelatori": [f"Congelatore N°{i}" for i in range(1, 13)],
    "altri": ["Cucina - Zona preparazione","Laboratorio - Banco lavoro","Magazzino - Scaffali",
              "Deposito - Derrate","Bar - Bancone","Sala - Perimetro","Esterno - Ingressi"]
}
DITTA = {
    "ragione_sociale": "ANTHIRAT CONTROL S.R.L.", "partita_iva": "07764320631",
    "codice_fiscale": "07764320631", "indirizzo": "VIA CAMALDOLILLI 142 - 80131 - NAPOLI (NA)",
    "rea": "657008", "pec": "anthiratcontrol@pec.it"
}
MESI_IT = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno",
           "Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"]

def _gen_interventi(anno):
    oggi, out = date.today(), {}
    for m in range(1, 13):
        if date(anno, m, 15) <= oggi:
            out[str(m)] = {"giorno": 15, "data": f"15/{m:02d}/{anno}",
                           "esito": "OK - Nessuna infestazione rilevata",
                           "tipo": "Controllo programmato + trattamento preventivo",
                           "tecnico": "ANTHIRAT CONTROL S.R.L.",
                           "note": "Derattizzazione e disinfestazione eseguite come da contratto"}
    return out

def _gen_monitoraggio(anno):
    random.seed(anno * 98765)
    oggi, mon = date.today(), {}
    tutti = APPARECCHI_MONITORAGGIO["frigoriferi"] + APPARECCHI_MONITORAGGIO["congelatori"] + APPARECCHI_MONITORAGGIO["altri"]
    for app in tutti:
        mon[app] = {}
        for m in range(1, 13):
            if date(anno, m, 1) <= oggi:
                ok = random.random() < 0.98
                mon[app][str(m)] = {"esito": "OK" if ok else "Richiede intervento",
                                     "note": "" if ok else "Segnalata presenza tracce", "controllato": True}
    return mon

async def _get_scheda(db, anno):
    s = await db["disinfestazione_annuale"].find_one({"anno": anno}, {"_id": 0})
    if not s:
        s = {"id": str(uuid.uuid4()), "anno": anno, "ditta": DITTA,
             "interventi_mensili": _gen_interventi(anno),
             "monitoraggio_apparecchi": _gen_monitoraggio(anno),
             "created_at": datetime.now(timezone.utc).isoformat(),
             "updated_at": datetime.now(timezone.utc).isoformat()}
        await db["disinfestazione_annuale"].insert_one(s)
    if "_id" in s: del s["_id"]
    return s

@router.get("/scheda-annuale/{anno}")
async def scheda_annuale(anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    return await _get_scheda(db, anno)

@router.get("/interventi/{anno}")
async def interventi(anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    s = await _get_scheda(db, anno)
    return {"anno": anno, "interventi": s.get("interventi_mensili", {}), "ditta": s.get("ditta", DITTA)}

@router.get("/monitoraggio/{anno}")
async def monitoraggio(anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    s = await _get_scheda(db, anno)
    return {"anno": anno, "monitoraggio": s.get("monitoraggio_apparecchi", {}), "apparecchi_disponibili": APPARECCHI_MONITORAGGIO}

@router.get("/monitoraggio/{anno}/mese/{mese}")
async def monitoraggio_mese(anno: int, mese: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    s = await _get_scheda(db, anno)
    ms = str(mese)
    mm = {a: mesi[ms] for a, mesi in s.get("monitoraggio_apparecchi", {}).items() if ms in mesi}
    return {"anno": anno, "mese": mese, "mese_nome": MESI_IT[mese-1] if 1<=mese<=12 else "",
            "intervento": s.get("interventi_mensili", {}).get(ms, {}), "monitoraggio": mm}

@router.post("/registra-intervento/{anno}/{mese}")
async def registra_intervento(anno: int, mese: int, giorno: int,
                               esito: str = "OK - Nessuna infestazione", tipo: str = "Controllo programmato",
                               note: str = "", db: AsyncIOMotorDatabase = Depends(get_database)):
    s = await _get_scheda(db, anno)
    s["interventi_mensili"][str(mese)] = {"giorno": giorno, "data": f"{giorno:02d}/{mese:02d}/{anno}",
                                           "esito": esito, "tipo": tipo, "note": note,
                                           "timestamp": datetime.now(timezone.utc).isoformat()}
    s["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db["disinfestazione_annuale"].update_one({"anno": anno}, {"$set": s})
    return {"success": True}

@router.post("/registra-monitoraggio/{anno}/{mese}")
async def registra_monitoraggio(anno: int, mese: int, apparecchio: str,
                                 esito: str = "OK", note: str = "",
                                 db: AsyncIOMotorDatabase = Depends(get_database)):
    s = await _get_scheda(db, anno)
    if apparecchio not in s["monitoraggio_apparecchi"]:
        s["monitoraggio_apparecchi"][apparecchio] = {}
    s["monitoraggio_apparecchi"][apparecchio][str(mese)] = {"esito": esito, "note": note, "controllato": True,
                                                             "timestamp": datetime.now(timezone.utc).isoformat()}
    s["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db["disinfestazione_annuale"].update_one({"anno": anno}, {"$set": s})
    return {"success": True}

@router.get("/apparecchi")
async def get_apparecchi():
    return APPARECCHI_MONITORAGGIO

@router.get("/ditta")
async def get_ditta():
    return DITTA

@router.get("/statistiche/{anno}")
async def statistiche(anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    s = await _get_scheda(db, anno)
    tc = tok = tp = 0
    for mesi in s.get("monitoraggio_apparecchi", {}).values():
        for d in mesi.values():
            if d.get("controllato"): tc += 1
            if d.get("esito") == "OK": tok += 1
            else: tp += 1
    return {"anno": anno, "interventi_effettuati": len(s.get("interventi_mensili", {})),
            "controlli": tc, "ok": tok, "problemi": tp,
            "conformita": round(tok/tc*100, 1) if tc else 0}

@router.post("/rigenera/{anno}")
async def rigenera(anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    await db["disinfestazione_annuale"].delete_one({"anno": anno})
    s = await _get_scheda(db, anno)
    return {"success": True, "interventi": len(s.get("interventi_mensili", {}))}

@router.get("/export-pdf/{anno}", response_class=HTMLResponse)
async def export_pdf(anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    s = await _get_scheda(db, anno)
    iv = s.get("interventi_mensili", {})
    h = f'<html><head><title>Disinfestazione {anno}</title><style>body{{font:11pt Arial}}table{{width:100%;border-collapse:collapse}}th,td{{border:1px solid #ddd;padding:8px;text-align:center}}th{{background:#8b0000;color:#fff}}.ok{{background:#e8f5e9;color:#2e7d32;font-weight:bold}}</style></head><body>'
    h += f'<h1>Registro Disinfestazione {anno}</h1><p><b>{DITTA["ragione_sociale"]}</b> — {DITTA["indirizzo"]}</p>'
    h += '<table><tr><th>Mese</th><th>Giorno</th><th>Esito</th><th>Note</th></tr>'
    for m in range(1, 13):
        i = iv.get(str(m), {})
        c = "ok" if "OK" in i.get("esito","") else ""
        h += f'<tr><td><b>{MESI_IT[m-1]}</b></td><td>{i.get("giorno","-")}</td><td class="{c}">{i.get("esito","Non effettuato")}</td><td>{i.get("note","")}</td></tr>'
    h += '</table><button onclick="window.print()">Stampa</button></body></html>'
    return HTMLResponse(content=h)
