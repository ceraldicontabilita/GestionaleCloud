"""Applicazione idempotente delle evidenze di pagamento alle singole rate."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


async def applica_quota_scadenze(
    db, *, fattura_id: str, quota: float, evidenza_id: str,
    metodo: str, data_pagamento: str,
) -> List[Dict[str, Any]]:
    """Distribuisce una quota sulle rate aperte senza riusare la stessa evidenza."""
    coll = db["scadenziario_fornitori"]
    gia = await coll.find_one({
        "fattura_id": fattura_id,
        "evidenze_pagamento.evidenza_id": evidenza_id,
    })
    if gia:
        return []

    rate = await coll.find(
        {"fattura_id": fattura_id, "pagato": {"$ne": True}}, {"_id": 0},
    ).sort([("data_scadenza", 1), ("blocco_indice", 1), ("rata_indice", 1)]).to_list(100)
    residuo_quota = _dec(quota)
    applicazioni = []
    now = datetime.now(timezone.utc).isoformat()
    for rata in rate:
        if residuo_quota <= 0:
            break
        importo_rata = _dec(rata.get("importo_rata") or rata.get("importo_totale") or rata.get("importo"))
        gia_pagato = _dec(rata.get("importo_pagato"))
        residuo_rata = max(Decimal("0.00"), importo_rata - gia_pagato)
        if residuo_rata <= 0:
            continue
        applicato = min(residuo_quota, residuo_rata)
        nuovo_pagato = gia_pagato + applicato
        chiusa = nuovo_pagato >= importo_rata
        evidenza = {
            "evidenza_id": evidenza_id,
            "metodo": metodo,
            "importo": float(applicato),
            "data_pagamento": data_pagamento,
            "registrata_at": now,
        }
        await coll.update_one(
            {"id": rata.get("id"), "evidenze_pagamento.evidenza_id": {"$ne": evidenza_id}},
            {
                "$set": {
                    "importo_pagato": float(nuovo_pagato),
                    "importo_residuo": float(max(Decimal("0.00"), importo_rata - nuovo_pagato)),
                    "pagato": chiusa,
                    "stato": "pagata" if chiusa else "parziale",
                    "data_pagamento": data_pagamento if chiusa else None,
                    "metodo_pagamento_effettivo": metodo,
                    "updated_at": now,
                },
                "$push": {"evidenze_pagamento": evidenza},
            },
        )
        applicazioni.append({"scadenza_id": rata.get("id"), "importo": float(applicato), "pagata": chiusa})
        residuo_quota -= applicato
    return applicazioni
