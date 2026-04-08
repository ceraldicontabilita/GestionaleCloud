"""
Router Ordini Fornitori — Ceraldi ERP gestionale2
=================================================
PREFIX: /api/ordini

Flusso:
  1. Operatore (pasticcere/barista) crea bozza ordine scegliendo prodotti
  2. Sistema mostra prezzi migliori dalle ultime 4 fatture per prodotto
  3. Admin rivede, modifica, approva
  4. Sistema invia ordine al fornitore (email / testo WhatsApp)

Collections usate:
  - fatture_passive  → storico prezzi per comparazione
  - fornitori        → anagrafica (email, pec, telefono)
  - ordini_ceraldi   → ordini creati (non la collection di ceraldiapp.it)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel
import uuid, re

from app.database import get_database

router = APIRouter()

AZIENDA_ID = "b0295759-35ce-4b34-a6b4-f01b883234ad"
N_FATTURE_COMPARAZIONE = 4  # quante fatture recenti usare per il prezzo medio


# ─── MODELLI ─────────────────────────────────────────────────────────────────

class RigaOrdine(BaseModel):
    nome: str                        # nome prodotto (testo libero dell'operatore)
    quantita: float = 1.0
    unita: str = "kg"
    note: str = ""
    fornitore_selezionato: str = ""  # fornitore scelto dall'admin dopo comparazione


class OrdineCreate(BaseModel):
    operatore: str = ""              # chi ha creato l'ordine
    reparto: str = ""                # pasticceria / bar / cucina / deposito
    righe: List[RigaOrdine]
    note: str = ""


class OrdineUpdate(BaseModel):
    righe: Optional[List[RigaOrdine]] = None
    note: Optional[str] = None
    stato: Optional[str] = None      # bozza | approvato | inviato | completato


# ─── NORMALIZZAZIONE NOMI ──────────────────────────────────────────────────────

def _normalizza(testo: str) -> str:
    """Normalizza nome prodotto per matching fuzzy."""
    t = testo.lower().strip()
    # Rimuovi unità di misura, numeri, punteggiatura
    t = re.sub(r'\b\d+[\.,]?\d*\s*(kg|g|lt|l|cl|ml|pz|cf|ct|nr|n\b)', '', t)
    t = re.sub(r'[^a-zàèéìòù\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _parole_chiave(testo: str) -> list[str]:
    """Estrae parole chiave significative (> 3 caratteri)."""
    stop = {'tipo', 'per', 'con', 'del', 'della', 'dei', 'degli', 'alla',
            'alle', 'dai', 'dalle', 'prodotto', 'prodotti', 'misc', 'vari'}
    return [p for p in _normalizza(testo).split() if len(p) > 3 and p not in stop]


def _score_match(cerca: str, descrizione_fattura: str) -> float:
    """Score 0-1 di similarità tra nome cercato e descrizione fattura."""
    parole = _parole_chiave(cerca)
    if not parole:
        return 0.0
    desc_norm = _normalizza(descrizione_fattura)
    hits = sum(1 for p in parole if p in desc_norm)
    return hits / len(parole)


# ─── ENDPOINT: COMPARAZIONE PREZZI ────────────────────────────────────────────

@router.get("/api/ordini/prezzi/{nome_prodotto}")
async def get_prezzi_prodotto(
    nome_prodotto: str,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Cerca nelle ultime N fatture passive di tutti i fornitori il prodotto
    indicato e restituisce il prezzo per fornitore (migliore evidenziato).

    Logica matching:
    1. Cerca per parole chiave (es. "farina 00" → trova "FARINA TIPO 00 CAPUTO 25KG")
    2. Raggruppa per fornitore con media delle ultime 4 fatture
    3. Ordina per prezzo crescente (il primo = il migliore)
    """
    # Carica tutte le fatture recenti (ultime 200)
    fatture = await db["fatture_passive"].find(
        {},
        {"cedente": 1, "data": 1, "linee": 1}
    ).sort("data", -1).limit(200).to_list(200)

    # Raggruppa per fornitore → ultime N fatture
    fatture_per_fornitore: dict[str, list] = {}
    for fat in fatture:
        fornitore = fat.get("cedente", {}).get("denominazione", "").strip()
        if not fornitore:
            continue
        if fornitore not in fatture_per_fornitore:
            fatture_per_fornitore[fornitore] = []
        if len(fatture_per_fornitore[fornitore]) < N_FATTURE_COMPARAZIONE:
            fatture_per_fornitore[fornitore].append(fat)

    risultati = []

    for fornitore, fatts in fatture_per_fornitore.items():
        prezzi_trovati = []

        for fat in fatts:
            for linea in (fat.get("linee") or []):
                desc = linea.get("descrizione") or linea.get("descrizione", "")
                prezzo = float(linea.get("prezzo_unitario") or 0)
                qty = float(linea.get("quantita") or 1)
                um = linea.get("unita_misura") or "PZ"

                if prezzo <= 0 or not desc:
                    continue

                score = _score_match(nome_prodotto, desc)
                if score >= 0.4:  # almeno 40% parole chiave in comune
                    prezzi_trovati.append({
                        "descrizione_fattura": desc,
                        "prezzo_unitario": prezzo,
                        "quantita": qty,
                        "unita_misura": um,
                        "data_fattura": fat.get("data", ""),
                        "score": round(score, 2),
                    })

        if not prezzi_trovati:
            continue

        # Prendi il match migliore per score, poi media prezzi
        prezzi_trovati.sort(key=lambda x: -x["score"])
        miglior_desc = prezzi_trovati[0]["descrizione_fattura"]

        # Filtra solo righe con la stessa descrizione (o simile)
        prezzi_stessa_desc = [p["prezzo_unitario"] for p in prezzi_trovati
                              if _score_match(miglior_desc, p["descrizione_fattura"]) >= 0.7]
        prezzo_medio = sum(prezzi_stessa_desc) / len(prezzi_stessa_desc)

        # Recupera dati anagrafica fornitore (email, pec, telefono)
        doc_forn = await db["fornitori"].find_one(
            {"anagrafica.ragione_sociale": {"$regex": fornitore[:15], "$options": "i"}},
            {"anagrafica": 1}
        )
        anagrafica = doc_forn.get("anagrafica", {}) if doc_forn else {}

        risultati.append({
            "fornitore": fornitore,
            "fornitore_id": str(doc_forn.get("_id", "")) if doc_forn else "",
            "email": anagrafica.get("email") or anagrafica.get("pec", ""),
            "pec": anagrafica.get("pec", ""),
            "telefono": anagrafica.get("telefono", ""),
            "descrizione_fattura": miglior_desc,
            "prezzo_medio_ultime_fatture": round(prezzo_medio, 4),
            "num_fatture": len(prezzi_stessa_desc),
            "score_match": prezzi_trovati[0]["score"],
            "ultima_data": prezzi_trovati[0]["data_fattura"],
            "unita_misura": prezzi_trovati[0]["unita_misura"],
        })

    # Ordina per prezzo crescente (migliore per primo)
    risultati.sort(key=lambda x: x["prezzo_medio_ultime_fatture"])

    # Marca il migliore
    if risultati:
        risultati[0]["e_il_migliore"] = True

    return {
        "prodotto_cercato": nome_prodotto,
        "num_fornitori": len(risultati),
        "risultati": risultati,
    }


# ─── ENDPOINT: CATALOGO PRODOTTI (per selezione rapida) ───────────────────────

# ─── CRUD ORDINI ─────────────────────────────────────────────────────────────

@router.post("/api/ordini")
async def crea_ordine(
    payload: OrdineCreate,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
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
    """Lista ordini, filtrabili per stato."""
    filtro = {}
    if stato:
        filtro["stato"] = stato
    ordini = await db["ordini_ceraldi"].find(filtro, {"_id": 0}).sort(
        "created_at", -1
    ).limit(limit).to_list(limit)
    return ordini


@router.get("/api/ordini/{ordine_id}")
async def get_ordine(ordine_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    doc = await db["ordini_ceraldi"].find_one({"id": ordine_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Ordine non trovato")
    return doc


@router.put("/api/ordini/{ordine_id}")
async def aggiorna_ordine(
    ordine_id: str,
    payload: OrdineUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """Admin modifica/approva un ordine."""
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


# ─── GENERAZIONE TESTO ORDINE (per email / WhatsApp) ─────────────────────────

@router.get("/api/ordini/{ordine_id}/testo-invio")
async def genera_testo_invio(
    ordine_id: str,
    fornitore: str = Query(..., description="Nome fornitore a cui inviare"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Genera il testo dell'ordine da inviare al fornitore via email o WhatsApp.
    Filtra solo le righe destinate a questo fornitore.
    """
    doc = await db["ordini_ceraldi"].find_one({"id": ordine_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Ordine non trovato")

    # Filtra righe per questo fornitore (o tutte se fornitore_selezionato vuoto)
    righe = [r for r in (doc.get("righe") or [])
             if not r.get("fornitore_selezionato")
             or r.get("fornitore_selezionato", "").lower() == fornitore.lower()]

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

    # Recupera dati contatto fornitore
    doc_forn = await db["fornitori"].find_one(
        {"anagrafica.ragione_sociale": {"$regex": fornitore[:15], "$options": "i"}},
        {"anagrafica": 1}
    )
    anagrafica = doc_forn.get("anagrafica", {}) if doc_forn else {}

    return {
        "oggetto": oggetto,
        "corpo": corpo,
        "email_fornitore": anagrafica.get("email") or anagrafica.get("pec", ""),
        "pec_fornitore": anagrafica.get("pec", ""),
        "telefono_fornitore": anagrafica.get("telefono", ""),
        "whatsapp_testo": f"*{oggetto}*\n\n{righe_testo}\n\nCeraldi Group S.R.L., Napoli",
        "righe": righe,
    }
