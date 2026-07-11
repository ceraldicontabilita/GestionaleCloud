"""
Analisi F24 — classificazione normativa, scadenze/ravvedimenti,
associazione ai cedolini e doppi pagamenti.

Espone via API il motore unico app/engines/tributi_engine.py
(specifica: memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md).

Endpoint (montati sotto /api/f24-analisi):
  GET /{f24_id}                     → analisi completa del modello (§11+§20)
  GET /{f24_id}/associazione        → esito §15 verso i cedolini di mese/anno
  GET /doppi-pagamenti              → scansione coppie DM10↔RC01 pagate (§21+§23)
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from app.database import Database
from app.engines import tributi_engine as te

logger = logging.getLogger(__name__)
router = APIRouter()

# Gli F24 vivono in due collezioni per storia: f24_commercialista (flusso
# riconciliazione/quietanze) e f24_unificato (archivio). Il lookup le prova
# entrambe — il motore lavora sul documento, non sulla collezione.
_COLLEZIONI_F24 = ("f24_commercialista", "f24_unificato")


async def _trova_f24(db, f24_id: str) -> Optional[Dict[str, Any]]:
    for coll in _COLLEZIONI_F24:
        doc = await db[coll].find_one({"id": f24_id}, {"_id": 0, "pdf_data": 0})
        if doc:
            doc["_collezione"] = coll
            return doc
    return None


@router.get("/doppi-pagamenti")
async def scan_doppi_pagamenti() -> Dict[str, Any]:
    """Cerca coppie F24 ordinario (DM10) ↔ RC01 dello stesso periodo con
    entrambi i pagamenti risultanti: POSSIBILE DOPPIO PAGAMENTO (§23)."""
    db = Database.get_db()
    ordinari, regolarizzazioni = [], []
    for coll in _COLLEZIONI_F24:
        docs = await db[coll].find({}, {"_id": 0, "pdf_data": 0}).to_list(2000)
        for d in docs:
            causali = te.causali_inps(d)
            if "RC01" in causali:
                regolarizzazioni.append(d)
            elif causali or d.get("sezione_erario"):
                ordinari.append(d)

    anomalie = []
    for rc in regolarizzazioni:
        periodo_rc = te.periodo_prevalente(rc)
        for ordinario in ordinari:
            if te.periodo_prevalente(ordinario) != periodo_rc:
                continue  # il confronto completo è costoso: pre-filtro sul periodo
            esito = te.rileva_doppio_pagamento(ordinario, rc)
            if esito.get("possibile_doppio_pagamento"):
                anomalie.append({
                    "f24_ordinario_id": ordinario.get("id"),
                    "f24_ordinario_file": ordinario.get("file_name") or ordinario.get("filename"),
                    "f24_rc01_id": rc.get("id"),
                    "f24_rc01_file": rc.get("file_name") or rc.get("filename"),
                    "periodo": esito["dettaglio"]["controlli"][1]["rc01"],
                    "quota_potenzialmente_duplicata": esito["quota_potenzialmente_duplicata"],
                    "quota_sanzioni_interessi": esito["quota_sanzioni_interessi"],
                    "messaggio": esito["messaggio"],
                    "stato": esito["stato"],
                })
    return {
        "esaminati_ordinari": len(ordinari),
        "esaminati_rc01": len(regolarizzazioni),
        "possibili_doppi_pagamenti": len(anomalie),
        "anomalie": anomalie,
        "stati_possibili": list(te.STATI_ANOMALIA_DOPPIO_PAGAMENTO),
    }


@router.get("/{f24_id}")
async def analisi_f24(f24_id: str) -> Dict[str, Any]:
    """Analisi completa: righe classificate (natura/ente/deducibilità),
    totali per natura, periodo prevalente, scadenza naturale, giorni di
    ritardo, stato pagamento e tipo versamento."""
    db = Database.get_db()
    f24 = await _trova_f24(db, f24_id)
    if not f24:
        raise HTTPException(status_code=404, detail="F24 non trovato")
    analisi = te.classifica_f24(f24)
    return {"f24_id": f24_id, "collezione": f24.pop("_collezione", None),
            "file": f24.get("file_name") or f24.get("filename"), **analisi}


@router.get("/{f24_id}/associazione")
async def associazione_cedolini(
    f24_id: str,
    mese: int = Query(..., ge=1, le=12),
    anno: int = Query(..., ge=2000, le=2100),
) -> Dict[str, Any]:
    """Esito e motivazione leggibile dell'associazione F24 ↔ cedolini di
    un mese (§15): periodo, causali, regolarizzazioni, date."""
    db = Database.get_db()
    f24 = await _trova_f24(db, f24_id)
    if not f24:
        raise HTTPException(status_code=404, detail="F24 non trovato")
    esito = te.valuta_associazione_cedolini(f24, mese, anno)
    return {"f24_id": f24_id, **esito}
