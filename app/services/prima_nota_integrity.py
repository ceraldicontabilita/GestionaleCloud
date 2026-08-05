"""Controlli condivisi di coerenza fattura <-> Prima Nota.

Le collezioni storiche usano piu' alias sia per lo stato pagato sia per
l'identificativo della riga di Prima Nota. Tutti i controlli e le riparazioni
devono quindi usare la stessa regola, altrimenti una fattura puo' restare
``paid=True`` mentre il movimento collegato e' gia' soft-deleted.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional


COLLEZIONI_PRIMA_NOTA = ("prima_nota_banca", "prima_nota_cassa")
CAMPI_ID_PRIMA_NOTA = (
    "prima_nota_id",
    "prima_nota_banca_id",
    "prima_nota_cassa_id",
)
CAMPI_EVIDENZA_BANCA = (
    "estratto_conto_id",
    "movimento_bancario_id",
    "movimento_estratto_conto_id",
    "bank_movement_id",
    "paypal_transaction_id",
    "movimento_paypal_id",
    "nexi_transaction_id",
    "carta_transaction_id",
)


def filtro_fatture_marcate_pagate() -> Dict[str, Any]:
    """Filtro Mongo tollerante a tutti gli alias storici di 'pagata'."""
    return {
        "status": {"$nin": ["deleted", "archived"]},
        "entity_status": {"$ne": "deleted"},
        "$or": [
            {"pagato": True},
            {"paid": True},
            {"stato_pagamento": {"$in": ["pagata", "paid", "pagato"]}},
            {"payment_status": {"$in": ["paid", "pagata", "pagato"]}},
        ],
    }


def _riferimenti_fattura(fattura: Dict[str, Any]) -> list[str]:
    return list({
        str(value)
        for value in (fattura.get("id"), fattura.get("invoice_key"))
        if value not in (None, "")
    })


def _riferimenti_prima_nota(fattura: Dict[str, Any]) -> list[str]:
    return list({
        str(fattura.get(campo))
        for campo in CAMPI_ID_PRIMA_NOTA
        if fattura.get(campo) not in (None, "")
    })


async def trova_movimento_prima_nota_attivo(
    db, fattura: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Trova una riga attiva per ID diretto o collegamento alla fattura."""
    pn_ids = _riferimenti_prima_nota(fattura)
    fattura_refs = _riferimenti_fattura(fattura)
    condizioni = []
    if pn_ids:
        condizioni.append({"id": {"$in": pn_ids}})
    if fattura_refs:
        condizioni.extend([
            {"fattura_id": {"$in": fattura_refs}},
            {"invoice_id": {"$in": fattura_refs}},
            {"riferimento": {"$in": [f"FATT-{ref}" for ref in fattura_refs]}},
        ])
    if not condizioni:
        return None

    for collection in COLLEZIONI_PRIMA_NOTA:
        movimento = await db[collection].find_one(
            {
                "status": {"$nin": ["deleted", "archived"]},
                "entity_status": {"$ne": "deleted"},
                "$or": condizioni,
            },
            {"_id": 0, "id": 1, "fattura_id": 1, "invoice_id": 1},
        )
        if movimento:
            return {"collection": collection, **movimento}
    return None


async def fatture_senza_pagamento_contabile_confermato(
    db, fatture: list[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    """Restituisce le fatture che devono restare in Provvisoria.

    Una riga cassa attiva e' una registrazione contabile confermata. Una riga
    banca e' definitiva soltanto se contiene il riferimento al movimento
    dell'estratto conto; le righe auto-create dal metodo fornitore non bastano.
    Il caricamento e' batch per evitare centinaia di round-trip verso Atlas.
    """
    if not fatture:
        return []

    riferimenti = {
        str(v)
        for f in fatture
        for v in (f.get("id"), f.get("invoice_key"))
        if v not in (None, "")
    }
    pn_ids = {
        str(f.get(campo))
        for f in fatture
        for campo in CAMPI_ID_PRIMA_NOTA
        if f.get(campo) not in (None, "")
    }
    condizioni = []
    if pn_ids:
        condizioni.append({"id": {"$in": list(pn_ids)}})
    if riferimenti:
        refs = list(riferimenti)
        condizioni.extend([
            {"fattura_id": {"$in": refs}},
            {"invoice_id": {"$in": refs}},
            {"riferimento": {"$in": [f"FATT-{ref}" for ref in refs]}},
        ])
    if not condizioni:
        return fatture

    filtro = {
        "status": {"$nin": ["deleted", "archived"]},
        "entity_status": {"$ne": "deleted"},
        "$or": condizioni,
    }
    projection = {
        "_id": 0, "id": 1, "fattura_id": 1, "invoice_id": 1,
        "riferimento": 1, **{campo: 1 for campo in CAMPI_EVIDENZA_BANCA},
    }
    confermati_pn = set()
    confermati_fattura = set()

    for collection in COLLEZIONI_PRIMA_NOTA:
        righe = await db[collection].find(filtro, projection).to_list(10000)
        for movimento in righe:
            if collection == "prima_nota_banca" and not any(
                movimento.get(campo) not in (None, "")
                for campo in CAMPI_EVIDENZA_BANCA
            ):
                continue
            if movimento.get("id"):
                confermati_pn.add(str(movimento["id"]))
            for campo in ("fattura_id", "invoice_id"):
                if movimento.get(campo):
                    confermati_fattura.add(str(movimento[campo]))
            riferimento = str(movimento.get("riferimento") or "")
            if riferimento.startswith("FATT-"):
                confermati_fattura.add(riferimento[5:])

    risultato = []
    for fattura in fatture:
        refs_fattura = {
            str(v) for v in (fattura.get("id"), fattura.get("invoice_key"))
            if v not in (None, "")
        }
        ids_fattura = {
            str(fattura.get(campo)) for campo in CAMPI_ID_PRIMA_NOTA
            if fattura.get(campo) not in (None, "")
        }
        if refs_fattura & confermati_fattura or ids_fattura & confermati_pn:
            continue
        risultato.append(fattura)
    return risultato


async def ripristina_fattura_senza_movimento_attivo(
    db, fattura: Dict[str, Any]
) -> bool:
    """Riapre la fattura solo se nessuna riga attiva la rappresenta."""
    if await trova_movimento_prima_nota_attivo(db, fattura):
        return False

    if fattura.get("_id") is not None:
        filtro: Dict[str, Any] = {"_id": fattura["_id"]}
    elif fattura.get("id"):
        filtro = {"id": fattura["id"]}
    elif fattura.get("invoice_key"):
        filtro = {"invoice_key": fattura["invoice_key"]}
    else:
        return False

    totale = float(
        fattura.get("total_amount") or fattura.get("importo_totale") or 0
    )
    result = await db["invoices"].update_one(
        filtro,
        {
            "$set": {
                "pagato": False,
                "paid": False,
                "stato_pagamento": "da_pagare",
                "payment_status": "open",
                "stato_finanziario": "da_registrare",
                "importo_pagato": 0,
                "importo_residuo": totale,
                "prima_nota_id": None,
                "prima_nota_tipo": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "$unset": {
                "prima_nota_cassa_id": "",
                "prima_nota_banca_id": "",
                "data_pagamento": "",
                "movimento_bancario_id": "",
                "estratto_conto_id": "",
                "riconciliato": "",
                "riconciliato_con_ec": "",
            },
        },
    )
    return bool(getattr(result, "modified_count", 0))
