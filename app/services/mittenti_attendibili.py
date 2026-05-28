"""
Whitelist mittenti email attendibili per import automatico Gmail.

Regola (CLAUDE.md aggiornato 28/05/2026):
- Fatture XML/PDF -> SOLO upload manuale/massivo nel gestionale. Mai Gmail.
- Documenti NON-fattura -> Gmail importa automaticamente SOLO da mittenti
  presenti in questa whitelist (es. cartelle esattoriali AdER, avvisi
  bonari Agenzia Entrate, verbali soci, cedolini Vicedomini, quietanze).

Collezione MongoDB: `mittenti_attendibili`
Schema:
    {
        "id": "ma_<uuid>",
        "email": "noreply@adm.gov.it",       # mittente o pattern (case-insensitive)
        "descrizione": "Agenzia Entrate Riscossione",
        "categoria_default": "cartella_esattoriale",
        "modulo_destinazione": "tributi",    # dove va instradato il doc
        "attivo": True,
        "created_at": ...,
        "updated_at": ...,
    }

Categorie supportate (vedi CATEGORIE_DOCUMENTO):
    verbale_soci, quietanza, allegato_generico, cartella_esattoriale,
    avviso_pagamento, avviso_bonario, cedolino_vicedomini, altro
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

COLL_MITTENTI = "mittenti_attendibili"

CATEGORIE_DOCUMENTO = {
    "verbale_soci": "Verbali assemblea/decisioni soci",
    "quietanza": "Quietanze di pagamento, ricevute",
    "allegato_generico": "Allegato PDF generico da mittente noto",
    "cartella_esattoriale": "Cartelle esattoriali (AdER)",
    "avviso_pagamento": "Avvisi di pagamento (Comune, INPS, INAIL, enti)",
    "avviso_bonario": "Avvisi bonari Agenzia Entrate (pre-ruolo)",
    "cedolino_vicedomini": "Cedolini/comunicazioni da commercialista lavoro",
    "altro": "Altri documenti attendibili",
}

# Mappa categoria -> modulo di destinazione del gestionale
MODULO_DESTINAZIONE_DEFAULT = {
    "verbale_soci": "documenti_societari",
    "quietanza": "prima_nota",
    "allegato_generico": "documenti",
    "cartella_esattoriale": "tributi",
    "avviso_pagamento": "scadenze",
    "avviso_bonario": "tributi",
    "cedolino_vicedomini": "hr_cedolini",
    "altro": "documenti",
}


def _ora_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


async def crea_indici(db) -> None:
    """Indici per ricerche rapide per email."""
    await db[COLL_MITTENTI].create_index("email", unique=False)
    await db[COLL_MITTENTI].create_index("attivo")


async def upsert_mittente(
    db,
    email: str,
    descrizione: str = "",
    categoria_default: str = "altro",
    modulo_destinazione: Optional[str] = None,
    attivo: bool = True,
) -> Dict[str, Any]:
    """Inserisce o aggiorna un mittente attendibile (idempotente per email)."""
    email_norm = (email or "").strip().lower()
    if not email_norm:
        raise ValueError("email vuota")
    if categoria_default not in CATEGORIE_DOCUMENTO:
        categoria_default = "altro"
    if modulo_destinazione is None:
        modulo_destinazione = MODULO_DESTINAZIONE_DEFAULT.get(
            categoria_default, "documenti"
        )

    doc = {
        "email": email_norm,
        "descrizione": descrizione,
        "categoria_default": categoria_default,
        "modulo_destinazione": modulo_destinazione,
        "attivo": bool(attivo),
        "updated_at": _ora_utc(),
    }
    result = await db[COLL_MITTENTI].update_one(
        {"email": email_norm},
        {
            "$set": doc,
            "$setOnInsert": {
                "id": f"ma_{uuid.uuid4()}",
                "created_at": _ora_utc(),
            },
        },
        upsert=True,
    )
    return {"upserted": result.upserted_id is not None, "email": email_norm}


async def elenca_mittenti(
    db, solo_attivi: bool = False
) -> List[Dict[str, Any]]:
    """Lista tutti i mittenti (default: anche disattivi)."""
    filtro: Dict[str, Any] = {}
    if solo_attivi:
        filtro["attivo"] = True
    cursor = db[COLL_MITTENTI].find(filtro, {"_id": 0}).sort("email", 1)
    return await cursor.to_list(length=10_000)


async def disattiva_mittente(db, email: str) -> bool:
    """Disattiva un mittente senza eliminarlo (storico preservato)."""
    email_norm = (email or "").strip().lower()
    result = await db[COLL_MITTENTI].update_one(
        {"email": email_norm}, {"$set": {"attivo": False, "updated_at": _ora_utc()}}
    )
    return result.matched_count > 0


async def riattiva_mittente(db, email: str) -> bool:
    email_norm = (email or "").strip().lower()
    result = await db[COLL_MITTENTI].update_one(
        {"email": email_norm}, {"$set": {"attivo": True, "updated_at": _ora_utc()}}
    )
    return result.matched_count > 0


async def elimina_mittente(db, email: str) -> bool:
    """Eliminazione hard (raro: di solito usa disattiva_mittente)."""
    email_norm = (email or "").strip().lower()
    result = await db[COLL_MITTENTI].delete_one({"email": email_norm})
    return result.deleted_count > 0


async def trova_mittente(db, email: str) -> Optional[Dict[str, Any]]:
    """Cerca un mittente per email esatta o per match parziale (sottostringa)."""
    email_norm = (email or "").strip().lower()
    if not email_norm:
        return None
    # 1) match esatto
    doc = await db[COLL_MITTENTI].find_one(
        {"email": email_norm, "attivo": True}, {"_id": 0}
    )
    if doc:
        return doc
    # 2) match per dominio o sottostringa (utile per pattern tipo "@adm.gov.it")
    cursor = db[COLL_MITTENTI].find({"attivo": True}, {"_id": 0})
    async for d in cursor:
        pattern = d.get("email", "").lower()
        if pattern and pattern in email_norm:
            return d
    return None


def e_fattura_xml(filename: str) -> bool:
    """Riconosce un possibile XML SDI/P7M anche se arrivato via Gmail.

    Regola: anche se mittente in whitelist, le fatture XML NON si importano
    via Gmail. Vanno messe in quarantena con alert e ignorate.
    """
    if not filename:
        return False
    fn = filename.lower()
    return fn.endswith(".xml") or fn.endswith(".xml.p7m") or fn.endswith(".p7m")


# Seed iniziale: mittenti tipici italiani. Idempotente: usa upsert.
SEED_MITTENTI: List[Dict[str, Any]] = [
    {"email": "noreply@adm.gov.it",
     "descrizione": "Agenzia Entrate Riscossione (AdER)",
     "categoria_default": "cartella_esattoriale"},
    {"email": "@agenziaentrate.gov.it",
     "descrizione": "Agenzia delle Entrate",
     "categoria_default": "avviso_bonario"},
    {"email": "@inps.it",
     "descrizione": "INPS",
     "categoria_default": "avviso_pagamento"},
    {"email": "@inail.it",
     "descrizione": "INAIL",
     "categoria_default": "avviso_pagamento"},
    {"email": "@vicedomini.it",
     "descrizione": "Studio Vicedomini (paghe)",
     "categoria_default": "cedolino_vicedomini"},
]


async def seed_mittenti_iniziali(db) -> int:
    """Idempotente: crea i mittenti tipici se mancano. Restituisce il conteggio."""
    n = 0
    for m in SEED_MITTENTI:
        res = await upsert_mittente(
            db,
            email=m["email"],
            descrizione=m["descrizione"],
            categoria_default=m["categoria_default"],
        )
        if res["upserted"]:
            n += 1
    return n
