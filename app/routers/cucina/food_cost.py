"""
Router Cucina — Food Cost
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List

from app.database import Database
from app.utils.error_handler import handle_errors

router = APIRouter(prefix="/cucina/food-cost", tags=["Cucina Food Cost"])


@router.get("/ricette-riepilogo")
@handle_errors
async def ricette_riepilogo() -> List[Dict[str, Any]]:
    """Lista ricette con food cost calcolato."""
    db = Database.get_db()
    ricette = await db["ricette"].find({}, {"_id": 0}).sort("nome", 1).to_list(1000)
    risultati = []
    for r in ricette:
        ingredienti = r.get("ingredienti", []) or []
        costo_totale = 0.0
        for ing in ingredienti:
            try:
                q = float(str(ing.get("quantita", 1) or 1).replace(",", "."))
                c = float(str(ing.get("costo", ing.get("prezzo_kg", ing.get("prezzo", 0))) or 0).replace(",", "."))
                costo_totale += c * q
            except (TypeError, ValueError, AttributeError):
                pass
        porzioni = max(1, int(r.get("porzioni", 1) or 1))
        costo_porzione = round(costo_totale / porzioni, 3)
        risultati.append({
            "id": r.get("id"),
            "nome": r.get("nome", ""),
            "reparto": r.get("reparto", ""),
            "porzioni": porzioni,
            "costo_totale": round(costo_totale, 2),
            "costo_porzione": costo_porzione,
            "food_cost": r.get("food_cost", costo_porzione),
            "approvata": r.get("approvata", False),
            "n_ingredienti": len(ingredienti),
        })
    return risultati


@router.get("/dizionario")
@handle_errors
async def dizionario_ingredienti() -> List[Dict[str, Any]]:
    """Ingredienti con prezzi da fornitori (da acquisti_prodotti o warehouse_inventory)."""
    db = Database.get_db()
    pipeline = [
        {"$group": {
            "_id": "$descrizione",
            "prezzo_medio": {"$avg": "$prezzo_unitario"},
            "ultimo_prezzo": {"$last": "$prezzo_unitario"},
            "fornitore": {"$last": "$fornitore"},
            "unita": {"$last": "$unita_misura"},
            "n_acquisti": {"$sum": 1}
        }},
        {"$project": {
            "_id": 0,
            "nome": "$_id",
            "prezzo_medio": {"$round": ["$prezzo_medio", 3]},
            "ultimo_prezzo": {"$round": ["$ultimo_prezzo", 3]},
            "fornitore": 1,
            "unita": 1,
            "n_acquisti": 1
        }},
        {"$sort": {"nome": 1}},
        {"$limit": 500}
    ]
    try:
        risultati = await db["acquisti_prodotti"].aggregate(pipeline).to_list(500)
    except Exception:
        risultati = []
    if not risultati:
        # fallback su warehouse_inventory
        try:
            prodotti = await db["warehouse_inventory"].find(
                {}, {"_id": 0, "name": 1, "description": 1, "unit_cost": 1, "unit": 1}
            ).limit(500).to_list(500)
            risultati = [
                {
                    "nome": p.get("name") or p.get("description", ""),
                    "prezzo_medio": float(p.get("unit_cost", 0) or 0),
                    "ultimo_prezzo": float(p.get("unit_cost", 0) or 0),
                    "fornitore": "",
                    "unita": p.get("unit", ""),
                    "n_acquisti": 0
                }
                for p in prodotti if p.get("name") or p.get("description")
            ]
        except Exception:
            risultati = []
    return risultati


@router.get("/calcola/{ricetta_id}")
@handle_errors
async def calcola_food_cost(ricetta_id: str) -> Dict[str, Any]:
    """Calcola il food cost di una singola ricetta."""
    db = Database.get_db()
    ricetta = await db["ricette"].find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")
    ingredienti = ricetta.get("ingredienti", [])
    costo_totale = 0.0
    dettaglio = []
    for ing in ingredienti:
        if not isinstance(ing, dict):
            continue  # Salta ingredienti salvati come stringhe invece di dict
        try:
            costo_unit = float(ing.get("costo", ing.get("prezzo", 0)) or 0)
            qty = float(ing.get("quantita", 1) or 1)
            subtotale = round(costo_unit * qty, 3)
            costo_totale += subtotale
            dettaglio.append({
                "nome": ing.get("nome", ing.get("descrizione", "")),
                "quantita": qty,
                "unita": ing.get("unita", ""),
                "costo_unitario": costo_unit,
                "subtotale": subtotale
            })
        except (TypeError, ValueError):
            pass
    porzioni = ricetta.get("porzioni", 1) or 1
    return {
        "id": ricetta_id,
        "nome": ricetta.get("nome", ""),
        "porzioni": porzioni,
        "costo_totale": round(costo_totale, 2),
        "costo_porzione": round(costo_totale / porzioni, 3),
        "ingredienti": dettaglio
    }
