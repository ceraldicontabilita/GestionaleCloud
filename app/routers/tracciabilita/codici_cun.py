"""
Gestione codici CUN (Commissioni Uniche Nazionali)
Fonte ufficiale: MASAF - Provvedimento AdE n. 93628/2026 del 18 marzo 2026
Obbligatori in fattura elettronica dal 18 marzo 2026 (fino al 31/12/2028)
"""
from fastapi import APIRouter
from app.routers.tracciabilita.server import db
import os

router = APIRouter(prefix="/codici-cun", tags=["Codici CUN"])



@router.get("/")
async def get_codici_cun(categoria: str = None):
    """Restituisce l'elenco completo (o filtrato per categoria) dei codici CUN ufficiali."""
    filtro = {}
    if categoria:
        filtro["categoria"] = categoria
    docs = await db.codici_cun.find(filtro, {"_id": 0}).to_list(200)
    return docs


@router.get("/categorie")
async def get_categorie_cun():
    """Restituisce le categorie distinte disponibili."""
    cats = await db.codici_cun.distinct("categoria")
    return sorted(cats)


@router.get("/search")
async def search_codici_cun(q: str):
    """Ricerca full-text tra codici e descrizioni CUN."""
    docs = await db.codici_cun.find(
        {"$or": [
            {"codice": {"$regex": q, "$options": "i"}},
            {"descrizione": {"$regex": q, "$options": "i"}},
            {"categoria": {"$regex": q, "$options": "i"}},
        ]},
        {"_id": 0}
    ).to_list(100)
    return docs
