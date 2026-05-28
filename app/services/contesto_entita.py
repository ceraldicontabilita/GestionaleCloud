"""
Servizio che ricostruisce il "contesto relazionale" di un'entita'.

Dato il tipo (fattura, fornitore, dipendente, movimento_banca, f24,
cedolino, assegno, documento) e l'id, restituisce l'entita' + tutte le
collegate (alert, partite aperte, match riconciliazione, prima nota,
altri documenti). Cosi' il frontend rende una vista "tutto su una
entita'" senza chiamare 5 endpoint diversi.

Ogni risultato e' un dict {
    "entita": {...},
    "collegate": {
        "alerts": [...],
        "partite_aperte": [...],
        "match": [...],
        "prima_nota": [...],
        "documenti_correlati": [...],
        ...specifici per tipo...
    },
    "links_ui": [
        {"label": "Vai al fornitore", "rotta_ui": "/fornitori/<id>"},
        ...
    ],
}
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


TIPI_SUPPORTATI = {
    "fattura", "fornitore", "dipendente",
    "movimento_banca", "f24", "cedolino", "assegno", "documento",
}


async def _alerts_per_entita(db, entita_id: str, collection: str) -> List[Dict[str, Any]]:
    cursor = db["alerts"].find(
        {"entita_id": entita_id, "entita_collection": collection, "stato": "aperto"},
        {"_id": 0},
    ).sort("created_at", -1).limit(50)
    return await cursor.to_list(length=50)


async def _partite_per_documento(db, documento_id: str) -> List[Dict[str, Any]]:
    cursor = db["partite_aperte"].find(
        {"documento_id": documento_id}, {"_id": 0}
    ).sort("data_scadenza", 1).limit(50)
    return await cursor.to_list(length=50)


async def _match_per_partita_ids(db, partita_ids: List[str]) -> List[Dict[str, Any]]:
    if not partita_ids:
        return []
    cursor = db["riconciliazioni_match"].find(
        {"partita_id": {"$in": partita_ids}}, {"_id": 0}
    ).sort("created_at", -1).limit(100)
    return await cursor.to_list(length=100)


async def contesto_fattura(db, fattura_id: str) -> Dict[str, Any]:
    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        return {}
    fornitore = None
    piva = fattura.get("fornitore_piva") or fattura.get("piva")
    if piva:
        fornitore = await db["fornitori"].find_one({"partita_iva": piva}, {"_id": 0})
    partite = await _partite_per_documento(db, fattura_id)
    match = await _match_per_partita_ids(db, [p["id"] for p in partite if "id" in p])
    alerts = await _alerts_per_entita(db, fattura_id, "invoices")
    prima_nota = []
    cursor = db["prima_nota_banca"].find(
        {"$or": [{"fattura_id": fattura_id}, {"documento_id": fattura_id}]},
        {"_id": 0},
    ).limit(20)
    prima_nota.extend(await cursor.to_list(length=20))
    cursor = db["prima_nota_cassa"].find(
        {"$or": [{"fattura_id": fattura_id}, {"documento_id": fattura_id}]},
        {"_id": 0},
    ).limit(20)
    prima_nota.extend(await cursor.to_list(length=20))
    return {
        "entita": fattura,
        "tipo": "fattura",
        "collegate": {
            "fornitore": fornitore,
            "partite_aperte": partite,
            "match": match,
            "alerts": alerts,
            "prima_nota": prima_nota,
        },
        "links_ui": [
            {"label": "Vai al fornitore",
             "rotta_ui": f"/fornitori/{fornitore['id']}" if fornitore else None},
            {"label": "Scadenzario fornitore",
             "rotta_ui": "/scadenze?piva=" + piva if piva else None},
        ],
    }


async def contesto_fornitore(db, fornitore_id: str) -> Dict[str, Any]:
    fornitore = await db["fornitori"].find_one({"id": fornitore_id}, {"_id": 0})
    if not fornitore:
        # prova per partita_iva
        fornitore = await db["fornitori"].find_one(
            {"partita_iva": fornitore_id}, {"_id": 0}
        )
    if not fornitore:
        return {}
    piva = fornitore.get("partita_iva")
    fatture = []
    if piva:
        cursor = db["invoices"].find(
            {"$or": [{"fornitore_piva": piva}, {"piva": piva}]}, {"_id": 0}
        ).sort("data", -1).limit(100)
        fatture = await cursor.to_list(length=100)
    partite = []
    if piva:
        cursor = db["partite_aperte"].find(
            {"controparte_id": fornitore.get("id"), "stato": {"$in": ["aperta", "parziale"]}},
            {"_id": 0},
        ).sort("data_scadenza", 1).limit(50)
        partite = await cursor.to_list(length=50)
    alerts = await _alerts_per_entita(db, fornitore.get("id", fornitore_id), "fornitori")
    scadenze = []
    if piva:
        cursor = db["scadenziario_fornitori"].find(
            {"$or": [{"fornitore_piva": piva}, {"piva": piva}]}, {"_id": 0}
        ).sort("data_scadenza", 1).limit(50)
        scadenze = await cursor.to_list(length=50)
    return {
        "entita": fornitore,
        "tipo": "fornitore",
        "collegate": {
            "fatture": fatture,
            "partite_aperte": partite,
            "scadenze": scadenze,
            "alerts": alerts,
        },
        "links_ui": [
            {"label": "Tutte le fatture", "rotta_ui": "/fatture-ricevute?piva=" + piva if piva else None},
        ],
    }


async def contesto_dipendente(db, dipendente_id: str) -> Dict[str, Any]:
    dip = await db["dipendenti"].find_one({"id": dipendente_id}, {"_id": 0})
    if not dip:
        return {}
    cursor = db["cedolini"].find(
        {"dipendente_id": dipendente_id}, {"_id": 0}
    ).sort([("anno", -1), ("mese", -1)]).limit(36)
    cedolini = await cursor.to_list(length=36)
    cursor = db["bonifici_stipendi"].find(
        {"dipendente_id": dipendente_id}, {"_id": 0}
    ).sort("data", -1).limit(36)
    bonifici = await cursor.to_list(length=36)
    cursor = db["presenze_mensili"].find(
        {"dipendente_id": dipendente_id}, {"_id": 0}
    ).sort([("anno", -1), ("mese", -1)]).limit(24)
    presenze = await cursor.to_list(length=24)
    alerts = await _alerts_per_entita(db, dipendente_id, "dipendenti")
    return {
        "entita": dip,
        "tipo": "dipendente",
        "collegate": {
            "cedolini": cedolini,
            "bonifici_stipendi": bonifici,
            "presenze": presenze,
            "alerts": alerts,
        },
        "links_ui": [
            {"label": "Cedolini dipendente", "rotta_ui": f"/hr/cedolini?dip={dipendente_id}"},
            {"label": "Presenze", "rotta_ui": f"/hr/presenze?dip={dipendente_id}"},
        ],
    }


async def contesto_movimento_banca(db, movimento_id: str) -> Dict[str, Any]:
    mov = await db["estratto_conto_movimenti"].find_one(
        {"id": movimento_id}, {"_id": 0}
    )
    if not mov:
        return {}
    cursor = db["riconciliazioni_match"].find(
        {"movimento_id": movimento_id}, {"_id": 0}
    )
    match = await cursor.to_list(length=50)
    alerts = await _alerts_per_entita(db, movimento_id, "estratto_conto_movimenti")
    return {
        "entita": mov,
        "tipo": "movimento_banca",
        "collegate": {"match": match, "alerts": alerts},
    }


async def contesto_f24(db, f24_id: str) -> Dict[str, Any]:
    f24 = await db["f24_unificato"].find_one({"id": f24_id}, {"_id": 0})
    if not f24:
        return {}
    quietanze = await db["quietanze_f24"].find(
        {"f24_id": f24_id}, {"_id": 0}
    ).to_list(length=20)
    partite = await _partite_per_documento(db, f24_id)
    match = await _match_per_partita_ids(db, [p["id"] for p in partite if "id" in p])
    alerts = await _alerts_per_entita(db, f24_id, "f24_unificato")
    return {
        "entita": f24,
        "tipo": "f24",
        "collegate": {
            "quietanze": quietanze,
            "partite_aperte": partite,
            "match": match,
            "alerts": alerts,
        },
    }


async def contesto_cedolino(db, cedolino_id: str) -> Dict[str, Any]:
    ced = await db["cedolini"].find_one({"id": cedolino_id}, {"_id": 0})
    if not ced:
        return {}
    dip = None
    if ced.get("dipendente_id"):
        dip = await db["dipendenti"].find_one(
            {"id": ced["dipendente_id"]}, {"_id": 0}
        )
    bonifico = None
    if ced.get("dipendente_id") and ced.get("anno") and ced.get("mese"):
        bonifico = await db["bonifici_stipendi"].find_one(
            {
                "dipendente_id": ced["dipendente_id"],
                "anno": ced["anno"],
                "mese": ced["mese"],
            },
            {"_id": 0},
        )
    partite = await _partite_per_documento(db, cedolino_id)
    alerts = await _alerts_per_entita(db, cedolino_id, "cedolini")
    return {
        "entita": ced,
        "tipo": "cedolino",
        "collegate": {
            "dipendente": dip,
            "bonifico_stipendio": bonifico,
            "partite_aperte": partite,
            "alerts": alerts,
        },
    }


async def contesto_assegno(db, assegno_id: str) -> Dict[str, Any]:
    a = await db["assegni"].find_one({"id": assegno_id}, {"_id": 0})
    if not a:
        return {}
    fatture_collegate: List[Dict[str, Any]] = []
    inv_ids = a.get("invoice_ids") or []
    if a.get("invoice_id"):
        inv_ids = list(set(inv_ids + [a["invoice_id"]]))
    if inv_ids:
        cursor = db["invoices"].find({"id": {"$in": inv_ids}}, {"_id": 0})
        fatture_collegate = await cursor.to_list(length=20)
    fornitore = None
    piva = a.get("beneficiario_piva")
    if piva:
        fornitore = await db["fornitori"].find_one(
            {"partita_iva": piva}, {"_id": 0}
        )
    alerts = await _alerts_per_entita(db, assegno_id, "assegni")
    return {
        "entita": a,
        "tipo": "assegno",
        "collegate": {
            "fatture": fatture_collegate,
            "fornitore": fornitore,
            "alerts": alerts,
        },
    }


async def contesto_documento(db, documento_id: str) -> Dict[str, Any]:
    """Vista unificata sulle 3 collezioni documenti (vedi documenti_unified)."""
    from app.services.documenti_unified import trova_per_id
    doc = await trova_per_id(db, documento_id)
    if not doc:
        return {}
    alerts = await _alerts_per_entita(db, documento_id, doc.get("fonte_collection", "documents_inbox"))
    return {"entita": doc, "tipo": "documento", "collegate": {"alerts": alerts}}


DISPATCH = {
    "fattura": contesto_fattura,
    "fornitore": contesto_fornitore,
    "dipendente": contesto_dipendente,
    "movimento_banca": contesto_movimento_banca,
    "f24": contesto_f24,
    "cedolino": contesto_cedolino,
    "assegno": contesto_assegno,
    "documento": contesto_documento,
}


async def ricostruisci_contesto(
    db, tipo: str, entita_id: str
) -> Optional[Dict[str, Any]]:
    fn = DISPATCH.get(tipo)
    if not fn:
        return None
    res = await fn(db, entita_id)
    if not res:
        return None
    return res
