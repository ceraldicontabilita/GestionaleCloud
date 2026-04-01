"""
Router Cucina — Food Cost (endpoint essenziali)
Adattato da /tmp/ceraldi_zip/unificazione_v2/backend/food_cost.py
prefix: /cucina/food-cost
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional, Any
from datetime import datetime, timezone
import re, uuid

from app.database import Database

router = APIRouter(prefix="/food-cost", tags=["Cucina Food Cost"])


# ─── Modelli ──────────────────────────────────────────────────────────────────
class IngredienteConQuantita(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nome: str
    quantita: float
    unita_misura: str = "g"
    prodotto_dizionario_id: Optional[str] = None
    prezzo_kg: Optional[float] = None
    costo_calcolato: Optional[float] = None

    @field_validator("quantita", mode="before")
    @classmethod
    def coerce_quantita(cls, v: Any) -> float:
        if isinstance(v, str):
            try:
                return float(v.replace(",", "."))
            except ValueError:
                raise ValueError(f"Quantità non valida: {v}")
        return v

    @field_validator("prezzo_kg", "costo_calcolato", mode="before")
    @classmethod
    def coerce_optional_float(cls, v: Any) -> Optional[float]:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            try:
                return float(v.replace(",", "."))
            except ValueError:
                return None
        return v


class AggiornaIngredienteRicetta(BaseModel):
    ricetta_id: str
    ingredienti_dettaglio: List[IngredienteConQuantita]


# ─── Helper ───────────────────────────────────────────────────────────────────
def converti_in_kg(quantita: float, unita: str) -> float:
    if not quantita:
        return 0
    unita = (unita or "g").lower().strip()
    if unita in ["kg", "kilogrammi", "lt", "litri", "l"]:
        return quantita
    elif unita in ["g", "gr", "grammi", "ml"]:
        return quantita / 1000
    else:
        return quantita / 1000


def trova_prodotto_dizionario(nome, dizionario: dict) -> Optional[dict]:
    if not nome:
        return None
    # Gestisce sia stringhe che dizionari {"nome": "..."}
    if isinstance(nome, dict):
        nome = nome.get("nome") or nome.get("ingrediente") or ""
    if not nome or not isinstance(nome, str):
        return None
    n = nome.lower().strip()
    # Ricerca esatta
    if n in dizionario:
        return dizionario[n]
    # Ricerca parziale
    for k, v in dizionario.items():
        if n in k or k in n:
            return v
    return None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/dizionario")
async def get_dizionario(search: str = Query(None)):
    db = Database.get_db()
    query = {}
    if search and len(search) >= 2:
        query["nome_normalizzato"] = {"$regex": search.lower(), "$options": "i"}
    prodotti = await db["dizionario_prodotti"].find(query, {"_id": 0}).sort("nome_normalizzato", 1).to_list(500)
    return prodotti


@router.get("/dizionario/search")
async def search_dizionario(q: str = Query(..., min_length=2)):
    db = Database.get_db()
    query = {"nome_normalizzato": {"$regex": q.lower(), "$options": "i"}}
    prodotti = await db["dizionario_prodotti"].find(query, {"_id": 0}).limit(20).to_list(20)

    def sort_key(p):
        nome = p.get("nome_normalizzato", "").lower()
        return (0, nome) if nome.startswith(q.lower()) else (1, nome)
    prodotti.sort(key=sort_key)

    for p in prodotti:
        if not p.get("costo_per_pezzo") and p.get("peso_pezzo_g") and p.get("prezzo_kg"):
            peso_kg = float(p["peso_pezzo_g"]) / 1000
            p["costo_per_pezzo"] = round(peso_kg * float(p["prezzo_kg"]), 4)
        p["nome_display"] = p.get("nome_canonico") or p.get("nome_normalizzato", "")
    return prodotti


@router.get("/calcola/{ricetta_id}")
async def calcola_food_cost_ricetta(ricetta_id: str):
    db = Database.get_db()
    ricetta = await db["ricette"].find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")

    prodotti = await db["dizionario_prodotti"].find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}

    ingredienti_result = []
    costo_totale = 0
    ingredienti_mancanti = []

    if ricetta.get("ingredienti_dettaglio"):
        for ing in ricetta["ingredienti_dettaglio"]:
            nome = ing.get("nome", "").strip()
            quantita_raw = ing.get("quantita", 0)
            unita = ing.get("unita_misura", "g")
            try:
                quantita = float(str(quantita_raw).replace(",", ".")) if quantita_raw else 0
            except (ValueError, TypeError):
                quantita = 0
            prodotto = trova_prodotto_dizionario(nome, dizionario)
            qb = str(quantita_raw).strip().lower() in ("q.b.", "qb", "q.b", "quanto basta", "")
            if prodotto and quantita > 0:
                prezzo_kg = float(prodotto.get("prezzo_kg", 0) or 0)
                costo_per_pezzo = float(prodotto.get("costo_per_pezzo", 0) or 0)
                unita_lower = (unita or "g").lower().strip()
                if unita_lower in ("pz", "pezzi", "pezzo", "nr", "n") and costo_per_pezzo > 0:
                    costo = quantita * costo_per_pezzo
                else:
                    quantita_kg = converti_in_kg(quantita, unita)
                    costo = quantita_kg * prezzo_kg
                ingredienti_result.append({
                    "nome": nome, "quantita": quantita, "unita": unita,
                    "prodotto_dizionario": prodotto.get("nome_normalizzato"),
                    "prezzo_kg": prezzo_kg, "costo": round(costo, 2)
                })
                costo_totale += costo
            elif prodotto and qb:
                prezzo_kg = float(prodotto.get("prezzo_kg", 0) or 0)
                ingredienti_result.append({
                    "nome": nome, "quantita": "q.b.", "unita": unita,
                    "prodotto_dizionario": prodotto.get("nome_normalizzato"),
                    "prezzo_kg": prezzo_kg, "costo": None
                })
            else:
                ingredienti_result.append({
                    "nome": nome, "quantita": quantita, "unita": unita,
                    "prodotto_dizionario": None, "prezzo_kg": None, "costo": None
                })
                if nome:
                    ingredienti_mancanti.append(nome)
    else:
        for nome_raw in ricetta.get("ingredienti", []):
            nome = nome_raw.get("nome", "") if isinstance(nome_raw, dict) else nome_raw
            if not nome:
                continue
            prodotto = trova_prodotto_dizionario(nome, dizionario)
            ingredienti_result.append({
                "nome": nome, "quantita": None, "unita": None,
                "prodotto_dizionario": prodotto.get("nome_normalizzato") if prodotto else None,
                "prezzo_kg": float(prodotto.get("prezzo_kg", 0)) if prodotto else None,
                "costo": None
            })
            if not prodotto:
                ingredienti_mancanti.append(nome)

    porzioni = ricetta.get("porzioni", 1) or 1
    return {
        "ricetta_id": ricetta_id,
        "nome": ricetta.get("nome", ""),
        "ingredienti": ingredienti_result,
        "costo_totale": round(costo_totale, 2),
        "porzioni": porzioni,
        "costo_porzione": round(costo_totale / porzioni, 2) if porzioni > 0 else 0,
        "ingredienti_mancanti": ingredienti_mancanti,
        "completezza": f"{len(ingredienti_result) - len(ingredienti_mancanti)}/{len(ingredienti_result)}"
    }


@router.get("/ricette-riepilogo")
async def get_ricette_con_costi():
    db = Database.get_db()
    ricette = await db["ricette"].find({}, {"_id": 0}).to_list(5000)
    prodotti = await db["dizionario_prodotti"].find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}

    risultati = []
    for ricetta in ricette:
        costo_totale = 0
        ingredienti_con_prezzo = 0
        ingredienti_totali = 0

        if ricetta.get("ingredienti_dettaglio"):
            for ing in ricetta["ingredienti_dettaglio"]:
                nome_ing = (ing.get("nome") or "").strip()
                if not nome_ing:
                    continue
                ingredienti_totali += 1
                prezzo_ing = ing.get("prezzo_kg")
                costo_ing = ing.get("costo_calcolato")
                if costo_ing is not None and costo_ing > 0:
                    costo_totale += costo_ing
                    ingredienti_con_prezzo += 1
                elif prezzo_ing and prezzo_ing > 0:
                    ingredienti_con_prezzo += 1
                elif nome_ing:
                    prodotto = trova_prodotto_dizionario(nome_ing, dizionario)
                    if prodotto and float(prodotto.get("prezzo_kg", 0) or 0) > 0:
                        try:
                            quantita_raw = ing.get("quantita", 0)
                            qb = str(quantita_raw).strip().lower() in ("q.b.", "qb", "q.b", "quanto basta", "")
                            if not qb:
                                quantita = float(str(quantita_raw).replace(",", "."))
                                prezzo_kg = float(prodotto.get("prezzo_kg", 0))
                                quantita_kg = converti_in_kg(quantita, ing.get("unita_misura", "g"))
                                costo_totale += quantita_kg * prezzo_kg
                            ingredienti_con_prezzo += 1
                        except Exception:
                            pass
        else:
            ingredienti_totali = len(ricetta.get("ingredienti", []))
            for nome in ricetta.get("ingredienti", []):
                nome_str = nome.get("nome", "") if isinstance(nome, dict) else str(nome)
                if trova_prodotto_dizionario(nome_str, dizionario):
                    ingredienti_con_prezzo += 1

        porzioni = ricetta.get("porzioni", 1) or 1
        risultati.append({
            "id": ricetta.get("id"),
            "nome": ricetta.get("nome"),
            "ingredienti_totali": ingredienti_totali,
            "ingredienti_con_prezzo": ingredienti_con_prezzo,
            "costo_totale": round(costo_totale, 2),
            "costo_porzione": round(costo_totale / porzioni, 2) if porzioni > 0 else 0,
            "completezza": f"{ingredienti_con_prezzo}/{ingredienti_totali}"
        })
    return risultati


@router.post("/aggiorna-ingredienti-ricetta")
async def aggiorna_ingredienti_ricetta(data: AggiornaIngredienteRicetta):
    db = Database.get_db()
    prodotti = await db["dizionario_prodotti"].find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}

    ingredienti_aggiornati = []
    costo_totale = 0
    for ing in data.ingredienti_dettaglio:
        prodotto = trova_prodotto_dizionario(ing.nome, dizionario)
        prezzo_kg = float(prodotto.get("prezzo_kg", 0) or 0) if prodotto else (ing.prezzo_kg or 0)
        quantita_kg = converti_in_kg(ing.quantita, ing.unita_misura)
        costo = round(quantita_kg * prezzo_kg, 4) if prezzo_kg > 0 else None
        if costo:
            costo_totale += costo
        ingredienti_aggiornati.append({
            "nome": ing.nome,
            "quantita": ing.quantita,
            "unita_misura": ing.unita_misura,
            "prodotto_dizionario_id": prodotto.get("id") if prodotto else ing.prodotto_dizionario_id,
            "prezzo_kg": prezzo_kg,
            "costo_calcolato": costo
        })

    await db["ricette"].update_one(
        {"id": data.ricetta_id},
        {"$set": {
            "ingredienti_dettaglio": ingredienti_aggiornati,
            "costo_totale": round(costo_totale, 2)
        }}
    )
    return {
        "success": True,
        "ricetta_id": data.ricetta_id,
        "costo_totale": round(costo_totale, 2),
        "ingredienti": ingredienti_aggiornati
    }


@router.get("/registro-allergeni")
async def get_registro_allergeni():
    db = Database.get_db()
    ricette = await db["ricette"].find(
        {"allergeni": {"$exists": True, "$ne": []}},
        {"_id": 0, "id": 1, "nome": 1, "allergeni": 1, "reparto": 1}
    ).sort("nome", 1).to_list(1000)
    return ricette
