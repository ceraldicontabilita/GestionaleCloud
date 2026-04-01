"""
Router Cucina — Ordini Fornitori (endpoint prodotti suggeriti per CatalogoOrdini)
Adattato da /tmp/ceraldi_zip/unificazione_v2/backend/ordini_fornitori.py
prefix: /cucina/ordini-fornitori
"""
from fastapi import APIRouter, Query
from typing import Optional

from app.database import Database

router = APIRouter(prefix="/ordini-fornitori", tags=["Cucina Ordini Fornitori"])


@router.get("/prodotti-suggeriti")
async def get_prodotti_suggeriti(
    fornitore: Optional[str] = Query(None),
    limit: int = Query(500)
):
    """
    Ritorna prodotti dal dizionario_prodotti ordinati per rilevanza.
    Usato dal CatalogoOrdini per mostrare i prodotti disponibili.
    """
    db = Database.get_db()
    filtro = {"prezzo_kg": {"$gt": 0}}
    if fornitore:
        filtro["fornitore"] = fornitore

    prodotti = await db["dizionario_prodotti"].find(filtro, {"_id": 0}).sort(
        [("conteggio_acquisti", -1), ("ultima_fattura_data", -1)]
    ).limit(limit).to_list(limit)

    risultato = []
    for p in prodotti:
        disp = float(p.get("quantita_disponibile_kg") or 0)
        scorta_min = float(p.get("scorta_minima") or 0)
        sotto_scorta = disp < 1.0 if scorta_min == 0 else disp < scorta_min

        risultato.append({
            "id": p.get("id"),
            "nome": p.get("nome_canonico") or p.get("nome_normalizzato", "").title(),
            "nome_normalizzato": p.get("nome_normalizzato", ""),
            "fornitore": p.get("fornitore", ""),
            "prezzo_kg": float(p.get("prezzo_kg") or 0),
            "unita_confezione": p.get("unita_confezione", "kg"),
            "peso_confezione": float(p.get("peso_confezione") or 1),
            "quantita_disponibile_kg": disp,
            "sotto_scorta": sotto_scorta,
            "categoria": p.get("categoria", ""),
            "immagine_url": p.get("immagine_url", ""),
        })
    return risultato
