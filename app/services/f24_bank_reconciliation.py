"""Riconciliazione bancaria canonica degli F24, anche per singolo tributo.

Il servizio e' riusabile da upload estratto conto, import F24, scheduler e API.
Associa soltanto combinazioni univoche; quietanza e modello non sostituiscono
mai la prova bancaria.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.db_collections import COLL_ESTRATTO_CONTO, COLL_F24
from app.services.bank_evidence import filtro_solo_evidenza_ufficiale
from app.services.estratto_conto_bpm_parser import riconcilia_f24_con_estratto
from app.services.f24_payment_evidence import patch_pagamento_banca


def _filtro_f24_aperti(anno: Optional[int] = None) -> Dict[str, Any]:
    filtro: Dict[str, Any] = {
        "entity_status": {"$ne": "deleted"},
        "$or": [
            {"pagato": {"$ne": True}},
            {"importo_residuo": {"$gt": 0}},
            {"saldo_tributi.stato": {"$in": ["da_pagare", "parzialmente_pagato"]}},
        ],
    }
    if anno:
        anno_s = str(int(anno))
        filtro["$and"] = [{"$or": [
            {"anno": int(anno)},
            {"anno": anno_s},
            {"dati_generali.data_versamento": {"$regex": f"^{anno_s}"}},
            {"data_versamento": {"$regex": f"^{anno_s}"}},
        ]}]
    return filtro


async def riconcilia_f24_tributi_banca(
    db, *, anno: Optional[int] = None, movimento_ids=None,
) -> Dict[str, Any]:
    """Collega movimenti F24 univoci al modello o alle sue righe tributo.

    Un movimento che coincide con una sola riga (es. 2001) paga quella riga
    soltanto. Importi ripetuti, modelli concorrenti e duplicati bancari restano
    sospesi.
    """
    f24_list = await db[COLL_F24].find(
        _filtro_f24_aperti(anno), {"_id": 0, "pdf_data": 0}
    ).to_list(5000)

    filtro_movimenti: Dict[str, Any] = {
        "$and": [
            {"$or": [
                {"descrizione_originale": {"$regex": "I24.*AGENZIA|AGENZIA.*ENTRATE|F24", "$options": "i"}},
                {"descrizione": {"$regex": "I24.*AGENZIA|AGENZIA.*ENTRATE|F24", "$options": "i"}},
                {"categoria": {"$regex": "Tasse|Imposte|Tributi|F24", "$options": "i"}},
            ]},
            filtro_solo_evidenza_ufficiale(),
            {"tipo_riconciliazione": {"$ne": "f24_tributi"}},
        ]
    }
    if movimento_ids:
        filtro_movimenti["$and"].append({"id": {"$in": list(movimento_ids)}})
    movimenti = await db[COLL_ESTRATTO_CONTO].find(
        filtro_movimenti, {"_id": 0}
    ).to_list(10000)

    if not f24_list or not movimenti:
        return {
            "f24_analizzati": len(f24_list),
            "movimenti_analizzati": len(movimenti),
            "f24_pagati": 0,
            "f24_parziali": 0,
            "movimenti_associati": 0,
            "ambigui_o_non_compatibili": len(movimenti),
        }

    risultato = riconcilia_f24_con_estratto(f24_list, movimenti)
    now = datetime.now(timezone.utc).isoformat()
    movimenti_associati = set()

    for f24 in risultato.get("f24_riconciliati", []):
        if f24.get("riconciliato_per_tributi"):
            patch = {
                "allocazioni_banca": f24.get("allocazioni_banca", []),
                "saldo_tributi": f24.get("saldo_tributi", {}),
                "importo_residuo": 0.0,
                "status": "pagato",
                "stato_pagamento": "PAGATO_BANCA",
                "pagato": True,
                "pagamento_verificato_banca": True,
                "fonte_prova_pagamento": "estratto_conto",
                "updated_at": now,
            }
            movimenti_associati.update(
                str(a.get("movimento_id"))
                for a in f24.get("allocazioni_banca", []) if a.get("movimento_id")
            )
        else:
            movimento = f24.get("movimento_bancario") or {}
            movimento_id = movimento.get("id") or movimento.get("fingerprint")
            if not movimento_id:
                continue
            movimenti_associati.add(str(movimento_id))
            patch = {
                **patch_pagamento_banca(
                    movimento_id=str(movimento_id),
                    data_pagamento=f24.get("data_pagamento_effettivo"),
                    riferimento=(movimento.get("f24_info") or {}).get("riferimento"),
                ),
                "status": "pagato",
                "stato_pagamento": "PAGATO_BANCA",
                "pagato": True,
                "importo_residuo": 0.0,
                "updated_at": now,
            }
        await db[COLL_F24].update_one({"id": f24.get("id")}, {"$set": patch})

    for f24 in risultato.get("f24_parzialmente_pagati", []):
        allocazioni = f24.get("allocazioni_banca", [])
        movimenti_associati.update(
            str(a.get("movimento_id")) for a in allocazioni if a.get("movimento_id")
        )
        await db[COLL_F24].update_one(
            {"id": f24.get("id")},
            {"$set": {
                "allocazioni_banca": allocazioni,
                "saldo_tributi": f24.get("saldo_tributi", {}),
                "importo_residuo": f24.get("importo_residuo", 0),
                "status": "parzialmente_pagato",
                "stato_pagamento": "PARZIALMENTE_PAGATO_BANCA",
                "pagato": False,
                "pagamento_verificato_banca": True,
                "fonte_prova_pagamento": "estratto_conto",
                "updated_at": now,
            }},
        )

    for movimento_id in movimenti_associati:
        f24_ids = []
        for f24 in (
            risultato.get("f24_riconciliati", [])
            + risultato.get("f24_parzialmente_pagati", [])
        ):
            alloc_ids = {
                str(a.get("movimento_id"))
                for a in f24.get("allocazioni_banca", []) if a.get("movimento_id")
            }
            movimento = f24.get("movimento_bancario") or {}
            if movimento_id in alloc_ids or movimento_id == str(
                movimento.get("id") or movimento.get("fingerprint") or ""
            ):
                f24_ids.append(str(f24.get("id")))
        await db[COLL_ESTRATTO_CONTO].update_one(
            {"$or": [{"id": movimento_id}, {"fingerprint": movimento_id}]},
            {"$set": {
                "riconciliato": True,
                "tipo_riconciliazione": "f24_tributi",
                "f24_ids": f24_ids,
                "data_riconciliazione": now,
            }},
        )

    stats = risultato.get("stats", {})
    return {
        "f24_analizzati": len(f24_list),
        "movimenti_analizzati": len(movimenti),
        "f24_pagati": stats.get("riconciliati", 0),
        "f24_parziali": stats.get("parzialmente_pagati", 0),
        "movimenti_associati": len(movimenti_associati),
        "ambigui_o_non_compatibili": len(risultato.get("movimenti_non_associati", [])),
    }
