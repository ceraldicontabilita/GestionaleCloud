"""Fonte unica e tracciabile dei saldi di cassa e banca.

Il saldo contabile (Prima Nota) e il saldo documentale (Estratto Conto) sono
evidenze diverse. Questo servizio non ne nasconde una dietro l'altra: espone
entrambe e calcola lo scarto da riconciliare. Le pagine contabili usano come
valore principale il saldo di Prima Nota, che e' il registro contabile.
"""

from datetime import date
from typing import Any, Dict, Optional

from app.routers.prima_nota_module.common import (
    ESCLUSIONI_PRIMA_NOTA,
    aggrega_saldo_prima_nota,
)


async def calcola_liquidita(
    db,
    anno: int,
    data_riferimento: Optional[str] = None,
) -> Dict[str, Any]:
    data_fine = data_riferimento or f"{anno}-12-31"
    if data_fine > f"{anno}-12-31":
        data_fine = f"{anno}-12-31"
    data_inizio = f"{anno}-01-01"
    intervallo = {"$gte": data_inizio, "$lte": data_fine}
    pn_query = {
        "status": {"$nin": ["deleted", "archived"]},
        **ESCLUSIONI_PRIMA_NOTA,
        "data": intervallo,
    }
    cassa = await aggrega_saldo_prima_nota(
        db, "prima_nota_cassa", pn_query, anno,
    )
    banca = await aggrega_saldo_prima_nota(
        db, "prima_nota_banca", pn_query, anno,
    )

    ec_base = {
        "status": {"$nin": ["deleted", "archived"]},
        "entity_status": {"$ne": "deleted"},
    }
    ec_query = {**ec_base, "data": intervallo}
    righe_ec_periodo = await db["estratto_conto_movimenti"].count_documents(ec_query)
    righe_ec = await db["estratto_conto_movimenti"].count_documents({
        **ec_base, "data": {"$lte": data_fine},
    })
    estratto = await aggrega_saldo_prima_nota(
        db,
        "estratto_conto_movimenti",
        ec_query,
        anno,
        query_base_precedente=ec_base,
    ) if righe_ec else {
        "totale_entrate": 0.0,
        "totale_uscite": 0.0,
        "saldo_anno": 0.0,
        "saldo_precedente": 0.0,
        "saldo_iniziale_manuale": False,
        "saldo": 0.0,
    }

    scarto = round(estratto["saldo"] - banca["saldo"], 2) if righe_ec else None
    return {
        "anno": anno,
        "data_riferimento": data_fine,
        "cassa": cassa,
        "banca_contabile": banca,
        "banca_estratto_conto": {
            **estratto,
            "righe": righe_ec,
            "righe_periodo": righe_ec_periodo,
            "disponibile": righe_ec > 0,
        },
        "scarto_banca": scarto,
        "riconciliato": scarto is not None and abs(scarto) < 0.01,
        "fonte_principale": "prima_nota",
        "nota": (
            "Il saldo mostrato e' quello contabile di Prima Nota. "
            "Il saldo Estratto Conto resta separato come evidenza bancaria."
        ),
        "calcolato_il": date.today().isoformat(),
    }
