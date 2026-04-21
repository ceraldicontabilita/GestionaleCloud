"""
Alert verbali CdS in scadenza (beneficio riduzione 30% entro 5 giorni dalla notifica).
Endpoint: GET /api/alert-verbali/scadenza-imminente, /api/alert-verbali/contatore.
"""
from fastapi import APIRouter
from datetime import datetime, timedelta
from typing import List, Dict, Any

from app.database import Database

router = APIRouter(prefix="/alert-verbali", tags=["Alert Verbali"])


@router.get("/scadenza-imminente")
async def verbali_in_scadenza(giorni_soglia: int = 5) -> List[Dict[str, Any]]:
    db = Database.get_db()
    oggi = datetime.now().date().isoformat()
    limite = (datetime.now() + timedelta(days=giorni_soglia)).date().isoformat()
    cursor = db["verbali_noleggio"].find({
        "stato": {"$in": ["notificato", "da_verificare", "notifica_attesa"]},
        "data_scadenza_riduzione_30": {"$gte": oggi, "$lte": limite},
        "data_pagamento": {"$in": [None, ""]},
    }, {"_id": 0, "pdf_data": 0, "quietanza_pdf": 0}).sort("data_scadenza_riduzione_30", 1)
    out: List[Dict[str, Any]] = []
    async for v in cursor:
        try:
            scad = datetime.fromisoformat(v["data_scadenza_riduzione_30"]).date()
        except Exception:
            continue
        gg = (scad - datetime.now().date()).days
        imp = v.get("importo") or v.get("importo_addebitato_fornitore") or 0
        try:
            imp = float(imp)
        except (ValueError, TypeError):
            imp = 0
        out.append({
            "id": v.get("id"),
            "numero_verbale": v.get("numero_verbale"),
            "targa": v.get("targa"),
            "importo_pieno": imp,
            "importo_ridotto_30": round(imp * 0.70, 2) if imp else None,
            "data_scadenza": v.get("data_scadenza_riduzione_30"),
            "giorni_mancanti": gg,
            "urgenza": "critica" if gg <= 1 else ("alta" if gg <= 3 else "media"),
            "iuv": v.get("iuv"),
            "fattura_ricevuta": bool(v.get("fattura_associata_id") or v.get("fattura_id")),
            "notifica_ricevuta": bool(v.get("data_ricezione_notifica")),
        })
    return out


@router.get("/contatore")
async def contatore_alert() -> Dict[str, int]:
    db = Database.get_db()
    oggi = datetime.now().date().isoformat()
    scad5 = (datetime.now() + timedelta(days=5)).date().isoformat()
    in_scad = await db["verbali_noleggio"].count_documents({
        "stato": {"$in": ["notificato", "da_verificare", "notifica_attesa"]},
        "data_scadenza_riduzione_30": {"$gte": oggi, "$lte": scad5},
        "data_pagamento": {"$in": [None, ""]},
    })
    in_attesa = await db["verbali_noleggio"].count_documents({"stato": "notifica_attesa"})
    return {"scadenza_imminente_5gg": in_scad, "in_attesa_notifica": in_attesa}
