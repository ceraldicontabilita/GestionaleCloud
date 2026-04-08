"""
Router Ordini Fornitori — Ceraldi ERP gestionale2
=================================================
PREFIX: nessuno (ogni endpoint ha già /api/ordini nel path)

Endpoints:
  GET  /api/ordini/prezzi/{nome}         → comparazione prezzi da fatture_passive
  POST /api/ordini                        → crea bozza ordine
  GET  /api/ordini                        → lista ordini
  GET  /api/ordini/{id}                  → dettaglio ordine
  PUT  /api/ordini/{id}                  → modifica/approva
  DELETE /api/ordini/{id}               → elimina
  GET  /api/ordini/{id}/testo-invio      → genera testo email/WhatsApp

Collections usate:
  - fatture_passive   → campi: fornitore_denominazione, data, linee[].descrizione,
                        linee[].prezzo_unitario, linee[].quantita, linee[].unita_misura
  - fornitori         → campi: anagrafica.ragione_sociale, anagrafica.email,
                        anagrafica.pec, anagrafica.telefono
  - ordini_ceraldi    → ordini creati dall'operatore
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel
import uuid, re

from app.database import get_database

router = APIRouter()

N_FATTURE = 4  # quante fatture recenti per fornitore per la comparazione


# ─── NORMALIZZAZIONE NOMI ──────────────────────────────────────────────────────

def _norm(testo: str) -> str:
    t = testo.lower().strip()
    t = re.sub(r'\b\d+[\.,]?\d*\s*(kg|g|lt|l|cl|ml|pz|cf|ct|nr|n)\b', ' ', t)
    t = re.sub(r'[^a-zàèéìòù\s]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

STOP = {'tipo','per','con','del','della','dei','degli','alla','alle','dai','dalle',
        'prodotto','prodotti','misc','vari','conf','confezione','cartone'}

def _parole(testo: str) -> list:
    return [p for p in _norm(testo).split() if len(p) > 3 and p not in STOP]

def _score(cerca: str, desc_fattura: str) -> float:
    parole = _parole(cerca)
    if not parole: return 0.0
    desc = _norm(desc_fattura)
    hits = sum(1 for p in parole if p in desc)
    return hits / len(parole)


# ─── MODELLI ──────────────────────────────────────────────────────────────────

class RigaOrdine(BaseModel):
    nome: str
    quantita: float = 1.0
    unita: str = "kg"
    note: str = ""
    fornitore_selezionato: str = ""

class OrdineCreate(BaseModel):
    operatore: str = ""
    reparto: str = ""
    righe: List[RigaOrdine]
    note: str = ""

class OrdineUpdate(BaseModel):
    righe: Optional[List[RigaOrdine]] = None
    note: Optional[str] = None
    stato: Optional[str] = None


# ─── COMPARAZIONE PREZZI ──────────────────────────────────────────────────────

@router.get("/api/ordini/prezzi/{nome_prodotto}")
async def get_prezzi_prodotto(
    nome_prodotto: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Cerca nelle ultime N fatture passive di tutti i fornitori il prodotto
    indicato e restituisce il prezzo medio per fornitore.
    Usa i campi reali di fatture_passive:
      - fornitore_denominazione (stringa)
      - data (stringa ISO)
      - linee[].descrizione, .prezzo_unitario, .quantita, .unita_misura
    """
    # Carica le ultime 300 fatture ordinate per data DESC
    fatture = await db["fatture_passive"].find(
        {},
        {"fornitore_denominazione": 1, "data": 1, "linee": 1, "_id": 0}
    ).sort("data", -1).limit(300).to_list(300)

    # Raggruppa per fornitore → max N_FATTURE più recenti
    per_fornitore: dict[str, list] = {}
    for fat in fatture:
        forn = (fat.get("fornitore_denominazione") or "").strip()
        if not forn:
            continue
        if forn not in per_fornitore:
            per_fornitore[forn] = []
        if len(per_fornitore[forn]) < N_FATTURE:
            per_fornitore[forn].append(fat)

    risultati = []

    for fornitore, fatts in per_fornitore.items():
        migliori: list[dict] = []

        for fat in fatts:
            for linea in (fat.get("linee") or []):
                desc = (linea.get("descrizione") or "").strip()
                prezzo = float(linea.get("prezzo_unitario") or 0)
                um = linea.get("unita_misura") or "PZ"
                if prezzo <= 0 or not desc:
                    continue
                score = _score(nome_prodotto, desc)
                if score >= 0.4:
                    migliori.append({
                        "descrizione": desc,
                        "prezzo": prezzo,
                        "unita_misura": um,
                        "data": fat.get("data", ""),
                        "score": score,
                    })

        if not migliori:
            continue

        # Ordina per score desc, prendi il match migliore
        migliori.sort(key=lambda x: -x["score"])
        desc_top = migliori[0]["descrizione"]

        # Media prezzi righe con la stessa descrizione (o simile)
        prezzi_simili = [m["prezzo"] for m in migliori
                         if _score(desc_top, m["descrizione"]) >= 0.7]
        prezzo_medio = sum(prezzi_simili) / len(prezzi_simili)

        # Cerca dati contatto fornitore in collection fornitori
        doc_forn = await db["fornitori"].find_one(
            {"anagrafica.ragione_sociale": {"$regex": re.escape(fornitore[:15]), "$options": "i"}},
            {"anagrafica": 1, "_id": 0}
        )
        ana = (doc_forn or {}).get("anagrafica", {})

        risultati.append({
            "fornitore": fornitore,
            "email": ana.get("email") or ana.get("pec", ""),
            "pec": ana.get("pec", ""),
            "telefono": ana.get("telefono", ""),
            "descrizione_fattura": desc_top,
            "prezzo_medio": round(prezzo_medio, 4),
            "num_fatture": len(prezzi_simili),
            "score_match": round(migliori[0]["score"], 2),
            "ultima_data": migliori[0]["data"],
            "unita_misura": migliori[0]["unita_misura"],
        })

    # Ordina per prezzo crescente → il primo è il migliore
    risultati.sort(key=lambda x: x["prezzo_medio"])
    if risultati:
        risultati[0]["e_il_migliore"] = True

    return {
        "prodotto_cercato": nome_prodotto,
        "num_fornitori": len(risultati),
        "risultati": risultati,
    }


# ─── CRUD ORDINI ──────────────────────────────────────────────────────────────

@router.post("/api/ordini")
async def crea_ordine(payload: OrdineCreate, db: AsyncIOMotorDatabase = Depends(get_database)):
    """Crea nuovo ordine in stato 'bozza'."""
    doc = {
        "id": str(uuid.uuid4()),
        "operatore": payload.operatore,
        "reparto": payload.reparto,
        "righe": [r.model_dump() for r in payload.righe],
        "note": payload.note,
        "stato": "bozza",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db["ordini_ceraldi"].insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "ordine": doc}


@router.get("/api/ordini")
async def lista_ordini(
    stato: Optional[str] = Query(None),
    limit: int = Query(50),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    filtro = {}
    if stato:
        filtro["stato"] = stato
    ordini = await db["ordini_ceraldi"].find(filtro, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return ordini


@router.get("/api/ordini/{ordine_id}")
async def get_ordine(ordine_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["ordini_ceraldi"].find_one({"id": ordine_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Ordine non trovato")
    return doc


@router.put("/api/ordini/{ordine_id}")
async def aggiorna_ordine(ordine_id: str, payload: OrdineUpdate, db: AsyncIOMotorDatabase = Depends(get_database)):
    upd: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if payload.righe is not None:
        upd["righe"] = [r.model_dump() for r in payload.righe]
    if payload.note is not None:
        upd["note"] = payload.note
    if payload.stato is not None:
        upd["stato"] = payload.stato
    result = await db["ordini_ceraldi"].update_one({"id": ordine_id}, {"$set": upd})
    if result.matched_count == 0:
        raise HTTPException(404, "Ordine non trovato")
    return {"success": True}


@router.delete("/api/ordini/{ordine_id}")
async def elimina_ordine(ordine_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    await db["ordini_ceraldi"].delete_one({"id": ordine_id})
    return {"success": True}


# ─── GENERA TESTO INVIO ───────────────────────────────────────────────────────

@router.get("/api/ordini/{ordine_id}/testo-invio")
async def genera_testo_invio(
    ordine_id: str,
    fornitore: str = Query(...),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Genera testo ordine per email / WhatsApp filtrato per fornitore."""
    doc = await db["ordini_ceraldi"].find_one({"id": ordine_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Ordine non trovato")

    righe = [r for r in (doc.get("righe") or [])
             if not r.get("fornitore_selezionato")
             or r["fornitore_selezionato"].lower() == fornitore.lower()]

    if not righe:
        raise HTTPException(400, f"Nessuna riga per il fornitore '{fornitore}'")

    oggi = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    reparto = doc.get("reparto") or "Deposito"
    operatore = doc.get("operatore") or "Staff Ceraldi"

    righe_testo = "\n".join([
        f"  • {r['nome']}: {r['quantita']} {r['unita']}"
        + (f" — {r['note']}" if r.get("note") else "")
        for r in righe
    ])

    oggetto = f"Ordine Ceraldi Group S.R.L. del {oggi}"
    corpo = f"""Gentili {fornitore},

Vi inviamo il nostro ordine del {oggi}.

--- PRODOTTI RICHIESTI ---
{righe_testo}

Reparto: {reparto}
Richiesto da: {operatore}
{("Note: " + doc['note']) if doc.get('note') else ""}

Consegna presso:
Ceraldi Group S.R.L.
Piazza Carità 14, 80134 Napoli (NA)
Tel: +39 081 5523488
Email: ceraldigroupsrl@gmail.com

Cordiali saluti,
Ceraldi Group S.R.L."""

    # Dati contatto fornitore
    doc_forn = await db["fornitori"].find_one(
        {"anagrafica.ragione_sociale": {"$regex": re.escape(fornitore[:15]), "$options": "i"}},
        {"anagrafica": 1, "_id": 0}
    )
    ana = (doc_forn or {}).get("anagrafica", {})

    return {
        "oggetto": oggetto,
        "corpo": corpo,
        "email_fornitore": ana.get("email") or ana.get("pec", ""),
        "pec_fornitore": ana.get("pec", ""),
        "telefono_fornitore": ana.get("telefono", ""),
        "whatsapp_testo": f"*{oggetto}*\n\n{righe_testo}\n\nCeraldi Group S.R.L., Napoli",
        "righe": righe,
    }
