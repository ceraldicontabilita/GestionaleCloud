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
from app.services.liquidita_service import calcola_liquidita

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
        oggi = _dt.now().strftime("%Y-%m-%d")
        data_rif = oggi if oggi.startswith(f"{anno}-") else f"{anno}-12-31"
    inizio_anno = f"{anno}-01-01"
    db = Database.get_db()
    liquidita = await calcola_liquidita(db, anno, data_rif)
    data_rif = liquidita["data_riferimento"]
    cassa = liquidita["cassa"]
    banca = liquidita["banca_contabile"]

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
            "entrate": cassa["totale_entrate"],
            "uscite": cassa["totale_uscite"],
            "riporto": cassa["saldo_precedente"],
            "saldo": cassa["saldo"],
        },
        "banca": {
            "entrate": banca["totale_entrate"],
            "uscite": banca["totale_uscite"],
            "riporto": banca["saldo_precedente"],
            "saldo": banca["saldo"],
        },
        "totale_disponibilita_liquide": round(cassa["saldo"] + banca["saldo"], 2),
        "riconciliazione_banca": {
            "saldo_contabile": banca["saldo"],
            "saldo_estratto_conto": liquidita["banca_estratto_conto"]["saldo"],
            "estratto_conto_disponibile": liquidita["banca_estratto_conto"]["disponibile"],
            "righe_estratto_conto": liquidita["banca_estratto_conto"]["righe"],
            "scarto": liquidita["scarto_banca"],
            "riconciliato": liquidita["riconciliato"],
        },
        "fonte_saldo": liquidita["fonte_principale"],
        "nota_saldo": liquidita["nota"],
        "versamenti_cassa_to_banca": {
            "totale": vers_tot,
            "operazioni": vers_count,
        },
    }



# (costanti COEFFICIENTI_AMMORTAMENTO/PIANO_CONTI_CEE e modelli pydantic delle
#  route rimosse eliminati: nessun import esterno; il piano dei conti canonico
#  e' SOLO quello ufficiale CEE in services/piano_conti_ufficiale.py)
