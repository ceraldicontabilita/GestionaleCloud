"""
Router ordini-app: SOLO le giacenze del magazzino-bar per la pagina Ordini
nativa (OrdiniView). Il resto del vecchio sistema parallelo (iframe
ordini-app.html) è stato demolito il 13/06/2026 — vedi nota in coda.
"""

from fastapi import APIRouter
from app.lotti.db import database as db
from app.lotti.routers.prodotti_master import normalize_nome

router = APIRouter(prefix="/ordini-app", tags=["Ordini App"])


@router.get("/giacenze")
async def giacenze():
    """Giacenze del magazzino-bar per mostrare lo stock nel catalogo Ordini.
    `by_key` è indicizzato per nome normalizzato (aggancio ai prodotti del catalogo)."""
    from app.lotti.routers.classificatore_alimenti import e_merce_alimentare
    prods = await db.magazzino_bar_prodotti.find({}, {"_id": 0}).to_list(1000)
    out, by_key = [], {}
    for p in prods:
        # Vista pulita: i non-alimentari (candeggina, cavi, monitor...) restano
        # nel DB per le statistiche ma NON compaiono in giacenza.
        if not e_merce_alimentare(p.get("nome", ""), p.get("categoria", "")):
            continue
        stock = float(p.get("stock", 0) or 0)
        soglia = float(p.get("soglia_minima", 0) or 0)
        k = normalize_nome(p.get("nome", ""))
        sotto = bool(soglia > 0 and stock < soglia)
        out.append({"id": p.get("id"), "nome": p.get("nome", ""), "key": k,
                    "stock": stock, "soglia": soglia, "sotto_soglia": sotto,
                    "fornitore": p.get("fornitore", "") or "", "unita": p.get("unita", "pz"),
                    "categoria": p.get("categoria", "")})
        if k:
            by_key[k] = {"id": p.get("id"), "nome": p.get("nome", ""),
                         "stock": stock, "soglia": soglia, "sotto_soglia": sotto,
                         "unita": p.get("unita", "pz")}
    return {"giacenze": out, "by_key": by_key, "totale": len(out)}



# ─────────────────────────────────────────────────────────────────────────────
# NOTA DEMOLIZIONE (13/06/2026): questo router conteneva 20+ endpoint del
# vecchio sistema parallelo ordini-app.html (iframe, eliminato). Il frontend
# nativo (OrdiniView) usa SOLO /giacenze. Eliminati: stato, storico, carico
# (scriveva lo stock bypassando applica_movimento_stock), genera-riordini
# (sostituito da /ordini-fornitori/genera-riordino), da-validare, reparti,
# accesso/invita, listino* (il listino vive in routers/listino.py).
# ─────────────────────────────────────────────────────────────────────────────
