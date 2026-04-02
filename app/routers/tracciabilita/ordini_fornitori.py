"""
Router: ordini_fornitori
Gestisce ordini ai fornitori creati dal tracciabilità (tablet/telefono).
Gli ordini vengono salvati con stato='bozza' e source='tracciabilita',
poi completati e inviati dall'amministratore via listino-prezzi-merci.
"""
from fastapi import APIRouter, HTTPException, Query
from app.routers.tracciabilita.server import db
from pydantic import BaseModel, Field
from typing import List, Optional
import os, uuid
from datetime import datetime, timezone

router = APIRouter(prefix="/ordini-fornitori", tags=["Ordini Fornitori"])



# ── Modelli ─────────────────────────────────────────────────
class ProdottoOrdine(BaseModel):
    prodotto_id: str
    nome: str
    fornitore: str = ""
    quantita: float = 1.0
    unita: str = "kg"
    prezzo_ultimo: float = 0.0
    note: str = ""


class RicettaDaProdurre(BaseModel):
    ricetta_id: str
    nome: str
    reparto: str = ""
    quantita: float = 1.0   # numero di lotti da produrre
    note: str = ""


class OrdineCreate(BaseModel):
    reparto: str = ""
    operatore: str = ""
    prodotti: List[ProdottoOrdine]
    ricette_da_produrre: List[RicettaDaProdurre] = []
    note_operatore: str = ""


# ── Endpoints ───────────────────────────────────────────────
@router.get("/prodotti-suggeriti")
async def get_prodotti_suggeriti(
    fornitore: Optional[str] = Query(None),
    limit: int = Query(500)
):
    """
    Ritorna prodotti dal dizionario_prodotti ordinati per rilevanza:
    1. Prodotti sotto scorta (quantita_disponibile_kg < soglia)
    2. Prodotti più acquistati (conteggio_acquisti desc)
    Solo prodotti con prezzo_kg > 0 (reali, non ERP-only).
    """
    filtro = {"prezzo_kg": {"$gt": 0}}
    if fornitore:
        filtro["fornitore"] = fornitore

    prodotti = await db.dizionario_prodotti.find(filtro, {"_id": 0}).sort(
        [("conteggio_acquisti", -1), ("ultima_fattura_data", -1)]
    ).limit(limit).to_list(limit)

    # Arricchisce con flag sotto_scorta
    risultato = []
    for p in prodotti:
        disp = float(p.get("quantita_disponibile_kg") or 0)
        scorta_min = float(p.get("scorta_minima") or 0)

        # Heuristic: sotto scorta se disponibile < 1 kg oppure < scorta_minima impostata
        sotto_scorta = disp < 1.0 if scorta_min == 0 else disp < scorta_min

        risultato.append({
            "id":                    p.get("id"),
            "nome":                  p.get("nome_canonico") or p.get("nome_normalizzato", "").title(),
            "nome_normalizzato":     p.get("nome_normalizzato"),
            "fornitore":             p.get("fornitore", ""),
            "categoria":             p.get("categoria_canonica") or p.get("categoria") or "Altro",
            "prezzo_kg":             float(p.get("prezzo_kg") or 0),
            "unita_confezione":      p.get("unita_confezione", "kg"),
            "peso_confezione":       float(p.get("peso_confezione") or 1),
            "ultima_fattura_data":   p.get("ultima_fattura_data", ""),
            "quantita_disponibile_kg": disp,
            "scorta_minima":         scorta_min,
            "sotto_scorta":          sotto_scorta,
            "conteggio_acquisti":    int(p.get("conteggio_acquisti") or 0),
            "foto_url":              p.get("foto_url"),
        })

    # Ordina: sotto scorta prima, poi per conteggio_acquisti
    risultato.sort(key=lambda x: (not x["sotto_scorta"], -x["conteggio_acquisti"]))
    return risultato


@router.post("")
async def crea_ordine(payload: OrdineCreate):
    """Crea un nuovo ordine in stato bozza dal tracciabilità."""
    if not payload.prodotti:
        raise HTTPException(status_code=400, detail="Nessun prodotto selezionato")

    now = datetime.now(timezone.utc).isoformat()
    ordine = {
        "id":                   str(uuid.uuid4()),
        "data_ordine":          datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "stato":                "inviato",
        "source":               "tracciabilita",
        "reparto":              payload.reparto,
        "operatore":            payload.operatore,
        "prodotti":             [p.model_dump() for p in payload.prodotti],
        "ricette_da_produrre":  [r.model_dump() for r in payload.ricette_da_produrre],
        "note_operatore":       payload.note_operatore,
        "created_at":           now,
        "updated_at":           now,
    }
    await db.ordini_fornitori.insert_one(ordine)
    ordine.pop("_id", None)
    return {"success": True, "ordine_id": ordine["id"], "ordine": ordine}


@router.get("")
async def lista_ordini(
    stato: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(50)
):
    """Lista ordini, filtrabili per stato e source."""
    filtro = {}
    if stato:
        filtro["stato"] = stato
    if source:
        filtro["source"] = source

    ordini = await db.ordini_fornitori.find(filtro, {"_id": 0}).sort(
        "created_at", -1
    ).limit(limit).to_list(limit)
    return ordini


@router.get("/{ordine_id}")
async def get_ordine(ordine_id: str):
    ordine = await db.ordini_fornitori.find_one({"id": ordine_id}, {"_id": 0})
    if not ordine:
        raise HTTPException(status_code=404, detail="Ordine non trovato")
    return ordine
