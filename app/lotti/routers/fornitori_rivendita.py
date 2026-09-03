"""
Registro fornitori di RIVENDITA (prodotti che arrivano già pronti dal fornitore
e vanno al banco / in colazione).

tipo:
  - "colazione"      → surgelati colazione mattina (Acquaviva, Vandemoortele, Sammontana, ...)
  - "senza_glutine"  → prodotti senza glutine (Alfa, ...)

I selettori del tablet (Colazione e Senza Glutine) sono guidati da questo registro:
aggiungere un fornitore qui fa comparire automaticamente i suoi prodotti nel modale
giusto. Disattivare un fornitore (attivo=false) lo toglie dai selezionabili SENZA
toccare lo storico vendite/lotti già registrati.
"""

from fastapi import APIRouter, HTTPException, Body
from datetime import datetime, timezone
from typing import Optional, List
import uuid

from app.lotti.db import database as db

router = APIRouter(prefix="/fornitori-rivendita", tags=["fornitori_rivendita"])

_TIPI = ("colazione", "senza_glutine")  # nomi dei flag booleani per-fornitore

# Fornitori già presenti nel sistema (cablati in passato) → seminati una volta sola.
_SEED = [
    {"nome": "Acquaviva",     "fonte": "acquaviva",     "colazione": True,  "senza_glutine": False, "match_fattura": "acquaviva"},
    {"nome": "Vandemoortele", "fonte": "vandemoortele", "colazione": True,  "senza_glutine": False, "match_fattura": "vandemoortele"},
    {"nome": "Alfa Service",  "fonte": "alpha",         "colazione": False, "senza_glutine": True,  "match_fattura": "alfa|alpha"},
]


async def _ensure_seed():
    if await db.fornitori_rivendita.count_documents({}) == 0:
        now = datetime.now(timezone.utc).isoformat()
        for s in _SEED:
            await db.fornitori_rivendita.insert_one(
                {"id": str(uuid.uuid4()), "attivo": True, "created_at": now, **s}
            )
    # Migrazione: vecchi documenti con 'tipo' (valore singolo) → due flag booleani
    async for d in db.fornitori_rivendita.find({"tipo": {"$exists": True}}, {"_id": 0, "id": 1, "tipo": 1}):
        await db.fornitori_rivendita.update_one(
            {"id": d["id"]},
            {"$set": {"colazione": d.get("tipo") == "colazione", "senza_glutine": d.get("tipo") == "senza_glutine"},
             "$unset": {"tipo": ""}},
        )


# ── Helper usati dai selettori (colazione.py / acquaviva.py) ───────────────────
async def fonti_attive(tipo: str) -> List[str]:
    """Lista dei tag 'fonte' dei fornitori ATTIVI con il flag richiesto (colazione/senza_glutine)."""
    if tipo not in _TIPI:
        return []
    await _ensure_seed()
    docs = await db.fornitori_rivendita.find(
        {tipo: True, "attivo": True}, {"_id": 0, "fonte": 1}
    ).to_list(200)
    return [d["fonte"] for d in docs if d.get("fonte")]


async def regex_fatture_attive(tipo: str) -> str:
    """Regex (OR) per trovare nelle fatture i fornitori ATTIVI col flag richiesto."""
    if tipo not in _TIPI:
        return "___nomatch___"
    await _ensure_seed()
    docs = await db.fornitori_rivendita.find(
        {tipo: True, "attivo": True}, {"_id": 0, "match_fattura": 1, "fonte": 1}
    ).to_list(200)
    parts = [(d.get("match_fattura") or d.get("fonte") or "").strip() for d in docs]
    parts = [p for p in parts if p]
    return "|".join(parts) if parts else "___nomatch___"


# ── CRUD ───────────────────────────────────────────────────────────────────────
@router.get("")
async def lista(tipo: Optional[str] = None, includi_inattivi: bool = False):
    await _ensure_seed()
    q = {}
    if tipo in _TIPI:
        q[tipo] = True
    if not includi_inattivi:
        q["attivo"] = True
    return await db.fornitori_rivendita.find(q, {"_id": 0}).sort("nome", 1).to_list(500)


@router.post("")
async def crea(payload: dict = Body(...)):
    await _ensure_seed()
    nome = (payload.get("nome") or "").strip()
    colazione = bool(payload.get("colazione"))
    senza_glutine = bool(payload.get("senza_glutine"))
    if not nome or not (colazione or senza_glutine):
        raise HTTPException(status_code=400, detail="Servono 'nome' e almeno una spunta (colazione o senza_glutine)")
    fonte = (payload.get("fonte") or nome.lower().replace(" ", "_")).strip()
    if await db.fornitori_rivendita.find_one({"fonte": fonte}):
        raise HTTPException(status_code=409, detail=f"Fornitore con fonte '{fonte}' già presente")
    doc = {
        "id": str(uuid.uuid4()),
        "nome": nome,
        "fonte": fonte,
        "colazione": colazione,
        "senza_glutine": senza_glutine,
        "match_fattura": (payload.get("match_fattura") or nome).strip(),
        "attivo": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.fornitori_rivendita.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/{fid}")
async def aggiorna(fid: str, payload: dict = Body(...)):
    campi = {}
    for k in ("nome", "fonte", "match_fattura"):
        if k in payload:
            campi[k] = payload[k]
    for k in ("attivo", "colazione", "senza_glutine"):
        if k in payload:
            campi[k] = bool(payload[k])
    if not campi:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")
    r = await db.fornitori_rivendita.update_one({"id": fid}, {"$set": campi})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    return {"success": True, "id": fid, **campi}


@router.delete("/{fid}")
async def disattiva(fid: str):
    """Soft-delete: disattiva il fornitore. Lo storico vendite/lotti NON viene toccato."""
    r = await db.fornitori_rivendita.update_one({"id": fid}, {"$set": {"attivo": False}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    return {"success": True, "disattivato": fid, "nota": "Storico vendite preservato"}
