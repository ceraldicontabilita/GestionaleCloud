"""
Ricerca globale — Tranche 6 (HACCP features, 04/07/2026).

Punto 6 delle 7 macro-funzionalità: ricerca per prodotto, lotto,
fornitore, ricetta, frigorifero in un unico posto. Prima esisteva solo
`lotti/cerca-universale` (solo lotti). Qui si aggregano le altre
collection con lo stesso pattern regex case-insensitive già usato altrove
nel backend (es. `lotti_produzione.py::recall_lotti_per_ingrediente`),
nessuna logica di ricerca nuova da inventare — solo l'aggregazione.
"""
import re

from fastapi import APIRouter, Query

from app.lotti.db import database as db

router = APIRouter(prefix="/ricerca-globale", tags=["Ricerca Globale"])


@router.get("")
async def ricerca_globale(q: str = Query(..., min_length=2), limit: int = Query(8, ge=1, le=30)):
    rx = {"$regex": re.escape(q.strip()), "$options": "i"}

    # filtro canonico: prima controllava solo "consumato" → i lotti smaltiti/
    # esauriti comparivano nella ricerca globale come se fossero ancora attivi.
    from app.lotti.routers.utils import FILTRO_LOTTO_APERTO
    lotti = await db.lotti.find(
        {"$or": [{"prodotto": rx}, {"numero_lotto": rx}], **FILTRO_LOTTO_APERTO},
        {"_id": 0, "id": 1, "prodotto": 1, "numero_lotto": 1, "data_scadenza": 1},
    ).sort("created_at", -1).to_list(limit)

    ricette = await db.ricette.find(
        {"nome": rx}, {"_id": 0, "id": 1, "nome": 1, "reparto": 1}
    ).to_list(limit)

    fornitori = await db.fornitori.find(
        {"nome": rx}, {"_id": 0, "nome": 1, "stato": 1}
    ).to_list(limit)

    materie_prime = await db.dizionario_prodotti.find(
        {"$or": [{"nome_display": rx}, {"nome_canonico": rx}, {"nome_originale": rx}]},
        # nome_normalizzato/nome_originale in proiezione: senza, i doc privi di
        # nome_canonico apparivano come righe VUOTE nel frontend (24/07/2026).
        {"_id": 0, "id": 1, "nome_display": 1, "nome_canonico": 1,
         "nome_normalizzato": 1, "nome_originale": 1, "prezzo_kg": 1},
    ).to_list(limit)

    attrezzature = await db.attrezzature_config.find(
        {"nome": rx, "attivo": {"$ne": False}}, {"_id": 0, "tipo": 1, "numero": 1, "nome": 1}
    ).to_list(limit)

    # Fase 2 ristrutturazione (24/07/2026): anche fatture, ordini e produzioni
    # (la ricerca copre pure i codici GEL-/PESR- perché numero_lotto matcha).
    fatture = await db.fatture.find(
        {"$or": [{"numero_fattura": rx}, {"fornitore": rx}]},
        {"_id": 0, "id": 1, "numero_fattura": 1, "fornitore": 1, "data_fattura": 1, "totale": 1},
    ).sort("created_at", -1).to_list(limit)

    ordini = await db.ordini_fornitori.find(
        {"$or": [{"fornitore": rx}, {"prodotti.nome": rx}, {"numero_ordine": rx}]},
        {"_id": 0, "id": 1, "fornitore": 1, "stato": 1, "created_at": 1, "numero_ordine": 1},
    ).sort("created_at", -1).to_list(limit)

    produzioni = await db.produzioni.find(
        {"$or": [{"ricetta_nome": rx}, {"numero_lotto": rx}]},
        {"_id": 0, "id": 1, "ricetta_nome": 1, "numero_lotto": 1, "pezzi": 1, "data": 1},
    ).sort("created_at", -1).to_list(limit)

    return {
        "query": q,
        "lotti": lotti,
        "ricette": ricette,
        "fornitori": fornitori,
        "materie_prime": materie_prime,
        "attrezzature": attrezzature,
        "fatture": fatture,
        "ordini": ordini,
        "produzioni": produzioni,
        "totale": len(lotti) + len(ricette) + len(fornitori) + len(materie_prime)
                  + len(attrezzature) + len(fatture) + len(ordini) + len(produzioni),
    }


@router.get("/lotto/{lotto_id}")
async def dettaglio_lotto_ricerca(lotto_id: str):
    """Scheda RAPIDA del lotto per la ricerca globale: origine, fornitori,
    fatture, quantità, scadenza, consumo/residuo e destinazione — tutto in
    una chiamata (fase 2, 24/07/2026)."""
    lotto = await db.lotti.find_one(
        {"$or": [{"id": lotto_id}, {"numero_lotto": lotto_id}]}, {"_id": 0})
    if not lotto:
        return {"trovato": False}
    lf = lotto.get("lotti_fornitori") or {}
    scalati = lf.get("lotti_scalati") or []
    origine = [
        {"ingrediente": s.get("prodotto") or s.get("nome"),
         "fornitore": s.get("fornitore"),
         "lotto_fornitore": s.get("numero_lotto") or s.get("lotto"),
         "fattura": s.get("numero_fattura") or s.get("fattura_ref"),
         "quantita": s.get("quantita_scalata")}
        for s in scalati[:30]
    ]
    consumato = lotto.get("quantita_consumata") or 0
    quantita = lotto.get("quantita") or 0
    return {
        "trovato": True,
        "numero_lotto": lotto.get("numero_lotto"),
        "prodotto": lotto.get("prodotto"),
        "data_produzione": lotto.get("data_produzione"),
        "data_scadenza": lotto.get("data_scadenza"),
        "quantita": quantita,
        "consumato": consumato,
        "residuo": max(0, quantita - consumato) if isinstance(quantita, (int, float)) else None,
        "destinazione": lotto.get("frigo_numero") or lotto.get("destinazione") or "",
        "stato": ("smaltito" if lotto.get("smaltito") else
                  "consumato" if lotto.get("consumato") else
                  "esaurito" if lotto.get("esaurito") else "attivo"),
        "operatore": lotto.get("operatore_nome") or "",
        "allergeni": lotto.get("allergeni_presenti") or [],
        "origine": origine,
    }
