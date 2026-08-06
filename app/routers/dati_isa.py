"""Dati gestionali di supporto ISA (ex studi di settore)."""
from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Any, Dict

from app.database import Database


router = APIRouter()


@router.get("/riepilogo")
async def riepilogo_dati_isa(anno: int = Query(..., ge=2000, le=2100)) -> Dict[str, Any]:
    db = Database.get_db()
    snapshot = await db["dati_isa_snapshot"].find_one(
        {"anno": anno}, {"_id": 0}
    ) or {}
    energia = await db["consumi_energia"].find(
        {"anno": anno}, {"_id": 0, "source_hash": 0}
    ).sort("mese", 1).to_list(12)
    totali_energia = {
        "f1_kwh": sum(int(r.get("f1_kwh") or 0) for r in energia),
        "f2_kwh": sum(int(r.get("f2_kwh") or 0) for r in energia),
        "f3_kwh": sum(int(r.get("f3_kwh") or 0) for r in energia),
        "totale_kwh": sum(int(r.get("totale_kwh") or 0) for r in energia),
    }
    indicatori = snapshot.get("indicatori_acquisti", {})
    return {
        "anno": anno,
        "indicatori_acquisti": indicatori,
        "indicatori_disponibili": bool(indicatori),
        "energia": {
            "mensili": energia,
            "totali": totali_energia,
            "disponibile": bool(energia),
        },
        "provenienza": snapshot.get("provenienza", {}),
        "avvertenze": [
            "Gli importi derivano dalle fatture presenti nel gestionale.",
            "Le quantita di caffe sono acquisti documentati, non consumi: per il consumo servono rimanenze iniziali e finali.",
            "La compilazione ISA ufficiale va verificata con il commercialista e con i dati precalcolati dell'Agenzia delle Entrate.",
        ],
    }
