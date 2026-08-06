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
        "importo": 1,
        "riferimento": 1, **{campo: 1 for campo in CAMPI_EVIDENZA_BANCA},
    }
    # Una fattura puo' essere pagata in piu' passaggi (per esempio una quota
    # in contanti e il residuo tramite banca). La sola presenza di una riga di
    # Prima Nota non prova quindi che l'intero documento sia saldato: bisogna
    # sommare esclusivamente gli importi confermati. Le righe banca prive di
    # evidenza dell'estratto conto restano, come prima, non confermate.
    importi_per_fattura: Dict[str, float] = {}
    importi_per_pn: Dict[str, float] = {}
    riferimenti_senza_importo = set()
    pn_senza_importo = set()

    pn_verso_fatture: Dict[str, set[str]] = {}
    for fattura in fatture:
        refs = _riferimenti_fattura(fattura)
        for pn_id in _riferimenti_prima_nota(fattura):
            pn_verso_fatture.setdefault(pn_id, set()).update(refs)

    for collection in COLLEZIONI_PRIMA_NOTA:
        righe = await db[collection].find(filtro, projection).to_list(10000)
        for movimento in righe:
            if collection == "prima_nota_banca" and not any(
                movimento.get(campo) not in (None, "")
                for campo in CAMPI_EVIDENZA_BANCA
            ):
                continue
            movimento_id = str(movimento.get("id") or "")
            riferimenti_movimento = set()
            for campo in ("fattura_id", "invoice_id"):
                if movimento.get(campo):
                    riferimenti_movimento.add(str(movimento[campo]))
            riferimento = str(movimento.get("riferimento") or "")
            if riferimento.startswith("FATT-"):
                riferimenti_movimento.add(riferimento[5:])
            if movimento_id:
                riferimenti_movimento.update(pn_verso_fatture.get(movimento_id, set()))

            valore = movimento.get("importo")
            try:
                importo = abs(float(valore)) if valore not in (None, "") else None
            except (TypeError, ValueError):
                importo = None

            # I record storici talvolta non riportano l'importo sulla riga ma
            # hanno un collegamento esplicito fattura/PN. Per non riaprire
            # pagamenti storici validi, quel solo caso conserva il significato
            # precedente di pagamento completo.
            if importo is None:
                riferimenti_senza_importo.update(riferimenti_movimento)
                if movimento_id:
                    pn_senza_importo.add(movimento_id)
                continue

            for ref in riferimenti_movimento:
                importi_per_fattura[ref] = round(
                    importi_per_fattura.get(ref, 0.0) + importo, 2
                )
            if movimento_id:
                importi_per_pn[movimento_id] = round(
                    importi_per_pn.get(movimento_id, 0.0) + importo, 2
                )

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
        totale = abs(float(
            fattura.get("total_amount") or fattura.get("importo_totale") or 0
        ))
        pagamento_confermato = max(
            [importi_per_fattura.get(ref, 0.0) for ref in refs_fattura]
            + [importi_per_pn.get(pn_id, 0.0) for pn_id in ids_fattura]
            + [0.0]
        )
        collegamento_storico_completo = bool(
            refs_fattura & riferimenti_senza_importo
            or ids_fattura & pn_senza_importo
        )
        if collegamento_storico_completo or (
            totale > 0 and pagamento_confermato >= totale - 0.01
        ):
            continue

        # I campi con prefisso '_' sono derivati di sola lettura. Permettono
        # alla pagina Provvisori e agli endpoint di registrare solo il residuo,
        # senza alterare il documento sorgente nel database.
        fattura_aperta = dict(fattura)
        fattura_aperta["_importo_pagato_confermato"] = round(
            pagamento_confermato, 2
        )
        fattura_aperta["_importo_residuo"] = round(
            max(0.0, totale - pagamento_confermato), 2
        )
        risultato.append(fattura_aperta)
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
