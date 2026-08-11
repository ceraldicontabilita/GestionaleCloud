"""Proiezione di sola lettura della chiusura SumUp corrente in Prima Nota.

La sincronizzazione SumUp archivia continuamente l'evidenza API del terminale.
La riga operativa di Cassa, invece, puo' essere stata materializzata prima che
la giornata fosse terminata.  Questa proiezione aggiorna la risposta delle API
senza riscrivere o cancellare il movimento sorgente: il valore persistito resta
visibile nell'audit e la pagina usa il totale corrente certificato dall'API.

La sostituzione e' ammessa solo con zero o una riga Cassa candidata.  Se ne
esistono piu' di una, il caso e' ambiguo e nessuna somma viene accorpata.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services import conti_pos, sumup_sync


CATEGORIA_SUMUP_CASSA = "POS SUMUP Verso Banca"


def giorno_corrente_negozio() -> str:
    return datetime.now(sumup_sync.FUSO_NEGOZIO).date().isoformat()


def filtro_movimento_sumup_cassa(data: str) -> Dict[str, Any]:
    return {
        "data": data,
        "status": {"$nin": ["deleted", "archived"]},
        "entity_status": {"$ne": "deleted"},
        "$or": [
            {"gestore": conti_pos.SUMUP},
            {"categoria": CATEGORIA_SUMUP_CASSA},
            {"descrizione": {"$regex": r"^POS\s+SUMUP\b", "$options": "i"}},
        ],
    }


async def leggi_proiezione_sumup_cassa(
    db,
    data: Optional[str] = None,
) -> Dict[str, Any]:
    """Restituisce il delta fra evidenza SumUp corrente e riga Cassa.

    Non esegue scritture. Una evidenza API assente non equivale a zero e non
    modifica alcun saldo. Piu righe Cassa candidate restano esplicitamente
    ambigue: non vengono sommate ne' deduplicate per descrizione/importo.
    """
    data = data or giorno_corrente_negozio()
    evidenza = await db["chiusure_pos_manuali"].find_one(
        {
            "data": data,
            "gestore": conti_pos.SUMUP,
            "source": "api_gestore_pos",
        },
        {
            "_id": 0,
            "id": 1,
            "data": 1,
            "importo": 1,
            "totale": 1,
            "updated_at": 1,
            "note": 1,
            "fonte_dato": 1,
            "stato_dato": 1,
        },
    )
    if not evidenza:
        return {
            "data": data,
            "stato": "evidenza_non_disponibile",
            "applicabile": False,
            "delta": 0.0,
            "numero_righe_persistite": 0,
        }

    corrente = round(float(
        evidenza.get("importo")
        if evidenza.get("importo") is not None
        else evidenza.get("totale") or 0
    ), 2)
    righe = await db["prima_nota_cassa"].find(
        filtro_movimento_sumup_cassa(data),
        {"_id": 0},
    ).to_list(3)

    base = {
        "data": data,
        "importo_corrente": corrente,
        "evidenza_id": evidenza.get("id"),
        "evidenza_updated_at": evidenza.get("updated_at"),
        "fonte": "sumup_api_archiviata",
        "numero_righe_persistite": len(righe),
    }
    if len(righe) > 1:
        return {
            **base,
            "stato": "righe_persistite_ambigue",
            "applicabile": False,
            "delta": 0.0,
            "movimento_ids": [r.get("id") for r in righe if r.get("id")],
        }

    persistito = round(float(righe[0].get("importo") or 0), 2) if righe else 0.0
    return {
        **base,
        "stato": "aggiornato_live" if righe else "riga_virtuale_live",
        "applicabile": True,
        "delta": round(corrente - persistito, 2),
        "importo_persistito": persistito if righe else None,
        "movimento_id": righe[0].get("id") if righe else None,
    }


def applica_proiezione_ai_movimenti(
    movimenti: List[Dict[str, Any]],
    proiezione: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Sovrappone il valore live a una lista API senza mutare i documenti DB."""
    if not proiezione.get("applicabile"):
        return movimenti

    risultato = [dict(movimento) for movimento in movimenti]
    movimento_id = proiezione.get("movimento_id")
    corrente = proiezione.get("importo_corrente", 0.0)
    descrizione = (
        f"POS SUMUP {proiezione['data']} -> credito SumUp "
        "(dato live; accredito separato)"
    )
    if movimento_id:
        for indice, movimento in enumerate(risultato):
            if movimento.get("id") != movimento_id:
                continue
            risultato[indice] = {
                **movimento,
                "importo_persistito": movimento.get("importo"),
                "importo": corrente,
                "amount": corrente,
                "descrizione": descrizione,
                "sumup_live": True,
                "sumup_evidenza_id": proiezione.get("evidenza_id"),
                "sumup_evidenza_updated_at": proiezione.get("evidenza_updated_at"),
                "non_modificabile": True,
            }
            break
        return risultato

    risultato.append({
        "id": f"sumup-live:{proiezione['data']}",
        "data": proiezione["data"],
        "tipo": "uscita",
        "importo": corrente,
        "amount": corrente,
        "categoria": CATEGORIA_SUMUP_CASSA,
        "descrizione": descrizione,
        "gestore": conti_pos.SUMUP,
        "source": "sumup_live_projection",
        "sumup_live": True,
        "virtuale": True,
        "non_modificabile": True,
        "sumup_evidenza_id": proiezione.get("evidenza_id"),
        "sumup_evidenza_updated_at": proiezione.get("evidenza_updated_at"),
    })
    return risultato
