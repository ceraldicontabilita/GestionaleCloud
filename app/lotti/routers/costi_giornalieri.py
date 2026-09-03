"""
Gestione costi giornalieri: personale + esercizio.
Usati per calcolare l'incidenza sul food cost reale.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone

from app.lotti.routers.date_utils import oggi_iso as oggi_str
from app.lotti.db import database as db

router = APIRouter(prefix="/costi-giornalieri", tags=["Costi Giornalieri"])

# ── Modelli ────────────────────────────────────────────────────────────────────


class VoceCosto(BaseModel):
    ruolo: str  # Es: "Pasticciere", "Energia"
    importo: float  # Costo giornaliero in €


class CostiGiornalieriPayload(BaseModel):
    data: Optional[str] = None  # yyyy-MM-dd, default oggi
    personale: List[VoceCosto] = []
    esercizio: List[VoceCosto] = []


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("/data/{data}")
async def get_costi(data: str = None):
    """Restituisce i costi salvati per una data (default: oggi)."""
    target = data or oggi_str()
    doc = await db.costi_giornalieri.find_one({"data": target}, {"_id": 0})
    if not doc:
        return {
            "data": target,
            "personale": [],
            "esercizio": [],
            "totale_personale": 0,
            "totale_esercizio": 0,
            "totale": 0,
        }
    doc["totale_personale"] = sum(v["importo"] for v in doc.get("personale", []))
    doc["totale_esercizio"] = sum(v["importo"] for v in doc.get("esercizio", []))
    doc["totale"] = doc["totale_personale"] + doc["totale_esercizio"]
    return doc


@router.post("/salva")
async def salva_costi(payload: CostiGiornalieriPayload):
    """Salva o aggiorna i costi giornalieri per una data."""
    target = payload.data or oggi_str()
    doc = {
        "data": target,
        "personale": [{"ruolo": v.ruolo, "importo": v.importo} for v in payload.personale],
        "esercizio": [{"ruolo": v.ruolo, "importo": v.importo} for v in payload.esercizio],
        "aggiornato_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.costi_giornalieri.replace_one({"data": target}, doc, upsert=True)

    tot_p = sum(v.importo for v in payload.personale)
    tot_e = sum(v.importo for v in payload.esercizio)
    return {
        "ok": True,
        "totale_personale": tot_p,
        "totale_esercizio": tot_e,
        "totale": tot_p + tot_e,
    }


@router.get("/incidenza/data/{data}")
async def calcola_incidenza(data: str = None):
    """
    Calcola il costo giornaliero per pezzo prodotto.
    Utile per calcolare il vero food cost (materie prime + personale + esercizio).
    """
    target = data or oggi_str()

    # Costi salvati
    costi = await db.costi_giornalieri.find_one({"data": target}, {"_id": 0})
    tot_costi = 0
    if costi:
        tot_costi = sum(v["importo"] for v in costi.get("personale", [])) + sum(
            v["importo"] for v in costi.get("esercizio", [])
        )

    # Pezzi prodotti oggi (da vendite_banco — esclude semilavorati)
    vendite = await db.vendite_banco.find(
        {"data": target, "prodotto_nome": {"$ne": None}},
        {"_id": 0, "pezzi_prodotti": 1, "fonte": 1},
    ).to_list(500)

    pezzi_lab = sum(
        v.get("pezzi_prodotti", 0) or 0
        for v in vendite
        if v.get("fonte") not in ("colazione", "acquaviva")
    )
    pezzi_totali = sum(v.get("pezzi_prodotti", 0) or 0 for v in vendite)

    incidenza_pz = round(tot_costi / pezzi_lab, 4) if pezzi_lab > 0 else 0
    incidenza_pz_tot = round(tot_costi / pezzi_totali, 4) if pezzi_totali > 0 else 0

    return {
        "data": target,
        "totale_costi": tot_costi,
        "pezzi_laboratorio": pezzi_lab,
        "pezzi_totali": pezzi_totali,
        "incidenza_per_pezzo_lab": incidenza_pz,
        "incidenza_per_pezzo_totale": incidenza_pz_tot,
    }
