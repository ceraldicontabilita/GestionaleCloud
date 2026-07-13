"""
Disponibilità liquide (Contabilità Avanzata)
============================================

Unica route viva di questo router: GET /api/contabilita/disponibilita-liquide,
usata da ContabilitaAvanzata.jsx.

STORIA (§13.2, pulizia 2026-07-13, scelta utente): questo file era il modulo
"Contabilità Italiana Completa" con 12 route (cespiti, cassa-banca, personale,
ritenute, ratei/risconti, bilancio SP/CE). Erano tutte doppioni concettuali
dei flussi canonici — cespiti.py (/api/cespiti), accounting/bilancio.py
(/api/bilancio), prima_nota_module, prima_nota_salari, /api/rapido — e a zero
chiamanti (FE, interni, test): rimosse. Storia completa in git.
"""

from fastapi import APIRouter, Query

from app.database import Database

router = APIRouter()



# ============================================
# DISPONIBILITA LIQUIDE + VERSAMENTI
# Endpoint aggregati richiesti dalla UI Contabilità Avanzata.
# ============================================

@router.get("/disponibilita-liquide")
async def get_disponibilita_liquide(
    anno: int = Query(..., description="Anno di riferimento"),
    data_rif: str | None = Query(None, description="Data ISO (YYYY-MM-DD) per saldo al giorno; default=oggi"),
):
    """
    Disponibilità liquide al giorno indicato (o ad oggi).

    Ritorna:
      - cassa: saldo giornaliero da prima_nota_cassa (entrate - uscite) <= data_rif
      - banca: saldo giornaliero da prima_nota_banca (entrate - uscite) <= data_rif
      - totale: cassa + banca
      - versamenti: totale versamenti (da cassa verso banca) dell'anno
      - saldo_iniziale_anno: saldo cassa+banca all'1 gennaio dell'anno
    """
    from datetime import datetime as _dt
    if data_rif is None:
        data_rif = _dt.now().strftime("%Y-%m-%d")
    inizio_anno = f"{anno}-01-01"
    db = Database.get_db()

    async def _saldo(coll_name: str, data_from: str | None, data_to: str) -> tuple[float, float, float]:
        """Ritorna (entrate, uscite, saldo) sulla coll nel range (data_from, data_to]."""
        date_filter: dict = {"$lte": data_to}
        if data_from:
            date_filter["$gte"] = data_from
        pipeline = [
            {"$match": {"data": date_filter}},
            {"$group": {
                "_id": "$tipo",
                "tot": {"$sum": "$importo"},
            }}
        ]
        e, u = 0.0, 0.0
        async for r in db[coll_name].aggregate(pipeline):
            imp = float(r.get("tot") or 0)
            if r["_id"] == "entrata":
                e = imp
            elif r["_id"] == "uscita":
                u = imp
        return round(e, 2), round(u, 2), round(e - u, 2)

    cassa_e, cassa_u, cassa_saldo = await _saldo("prima_nota_cassa", inizio_anno, data_rif)
    banca_e, banca_u, banca_saldo = await _saldo("prima_nota_banca", inizio_anno, data_rif)

    # Versamenti = movimenti cassa tipo=uscita categoria~Versament*
    vers_pipeline = [
        {"$match": {
            "data": {"$gte": inizio_anno, "$lte": data_rif},
            "tipo": "uscita",
            "$or": [
                {"categoria": {"$regex": "versament", "$options": "i"}},
                {"descrizione": {"$regex": "versament", "$options": "i"}},
            ]
        }},
        {"$group": {"_id": None, "tot": {"$sum": "$importo"}, "count": {"$sum": 1}}}
    ]
    vers_tot, vers_count = 0.0, 0
    async for r in db["prima_nota_cassa"].aggregate(vers_pipeline):
        vers_tot = round(float(r.get("tot") or 0), 2)
        vers_count = int(r.get("count") or 0)

    return {
        "anno": anno,
        "data_riferimento": data_rif,
        "cassa": {
            "entrate": cassa_e, "uscite": cassa_u, "saldo": cassa_saldo,
        },
        "banca": {
            "entrate": banca_e, "uscite": banca_u, "saldo": banca_saldo,
        },
        "totale_disponibilita_liquide": round(cassa_saldo + banca_saldo, 2),
        "versamenti_cassa_to_banca": {
            "totale": vers_tot,
            "operazioni": vers_count,
        },
    }



# (costanti COEFFICIENTI_AMMORTAMENTO/PIANO_CONTI_CEE e modelli pydantic delle
#  route rimosse eliminati: nessun import esterno; il piano dei conti canonico
#  e' SOLO quello ufficiale CEE in services/piano_conti_ufficiale.py)
