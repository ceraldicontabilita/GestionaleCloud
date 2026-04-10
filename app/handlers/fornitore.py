"""
Handler Fornitore — reagisce a fornitore.creato e fornitore.aggiornato
Aggiorna la Learning Machine con le keyword del nuovo fornitore.
Quando viene creato da una fattura XML, estrae automaticamente
le keyword dalle descrizioni delle righe.
"""
import logging
import uuid
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Parole troppo generiche da non usare come keyword
STOP_WORDS = {
    "srl", "spa", "snc", "sas", "ltd", "gmbh", "di", "della", "del",
    "the", "and", "per", "con", "tra", "via", "dei", "degli", "alle",
    "fattura", "nota", "credito", "iva", "imponibile", "totale",
    "quantita", "descrizione", "servizio", "fornitura", "prestazione",
    "it", "eu", "com", "net", "pec", "email", "srl", "spa",
}


def _estrai_keyword(testo: str) -> List[str]:
    """Estrae keyword significative da una stringa di testo."""
    if not testo:
        return []
    # Tokenizza: solo parole di almeno 4 caratteri
    parole = re.findall(r'[A-Za-zÀ-ÿ]{4,}', testo.lower())
    return [p for p in parole if p not in STOP_WORDS][:10]


async def handler_aggiorna_learning_fornitore(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Quando viene creato o aggiornato un fornitore, aggiorna le sue keyword
    in fornitori_keywords per migliorare la classificazione automatica delle fatture.
    Le keyword vengono estratte da: ragione sociale, righe delle fatture, categoria.
    """
    if db is None:
        return {"skipped": True, "reason": "db non disponibile"}

    fornitore_id = payload.get("fornitore_id") or payload.get("id")
    ragione_sociale = (payload.get("ragione_sociale") or
                      payload.get("denominazione") or "")
    piva = payload.get("partita_iva") or payload.get("piva") or ""
    righe = payload.get("righe") or payload.get("linee") or []

    if not fornitore_id and not ragione_sociale:
        return {"skipped": True, "reason": "dati fornitore insufficienti"}

    # Raccoglie keyword
    keywords = set()

    # Da ragione sociale
    for kw in _estrai_keyword(ragione_sociale):
        keywords.add(kw)

    # Dalla P.IVA (primi 6 caratteri significativi)
    if piva and len(piva) >= 6:
        keywords.add(piva[:6].lower())

    # Dalle descrizioni delle righe fattura
    for riga in righe[:10]:
        desc = riga.get("descrizione") or riga.get("description") or ""
        for kw in _estrai_keyword(desc):
            keywords.add(kw)

    # Dalla categoria già assegnata (se esiste)
    categoria = payload.get("categoria") or payload.get("centro_costo_nome") or ""
    if categoria:
        keywords.add(categoria.lower()[:20])

    if not keywords:
        return {"skipped": True, "reason": "nessuna keyword estratta"}

    # Cerca record esistente
    existing = await db["fornitori_keywords"].find_one(
        {"fornitore_id": fornitore_id} if fornitore_id else {"piva": piva}
    )

    keywords_list = sorted(list(keywords))

    if existing:
        # Unisci con le keyword esistenti (no duplicati)
        all_kw = list(set(existing.get("keywords", []) + keywords_list))
        await db["fornitori_keywords"].update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "keywords": all_kw[:50],  # max 50 keyword per fornitore
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        logger.info(f"[HandlerFornitore] Updated keywords {ragione_sociale}: {len(all_kw)} total")
        return {"action": "updated", "keywords_count": len(all_kw)}
    else:
        # Crea nuovo record
        doc = {
            "id":             str(uuid.uuid4()),
            "fornitore_id":   fornitore_id,
            "ragione_sociale": ragione_sociale,
            "piva":           piva,
            "keywords":       keywords_list[:50],
            "source":         "auto_fattura",
            "created_at":     datetime.now(timezone.utc).isoformat(),
            "updated_at":     datetime.now(timezone.utc).isoformat(),
        }
        await db["fornitori_keywords"].insert_one(doc.copy())
        logger.info(f"[HandlerFornitore] Created keywords {ragione_sociale}: {len(keywords_list)}")
        return {"action": "created", "keywords_count": len(keywords_list)}


async def handler_controlla_iban_mancante(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Quando viene creato un fornitore con metodo pagamento "bonifico" ma senza IBAN,
    crea una segnalazione di avviso.
    """
    if db is None:
        return {"skipped": True}

    metodo = (payload.get("metodo_pagamento") or "").lower()
    iban   = payload.get("iban") or ""
    nome   = payload.get("ragione_sociale") or payload.get("denominazione") or "?"

    metodi_bancari = {"bonifico", "sepa", "rid", "riba", "sdd"}
    if metodo not in metodi_bancari or iban:
        return {"skipped": True, "reason": "non richiede IBAN o IBAN già presente"}

    # Crea segnalazione
    await db["agenti_segnalazioni"].insert_one({
        "id": str(uuid.uuid4()),
        "agente": "HandlerFornitore",
        "tipo": "avviso",
        "titolo": f"IBAN mancante per {nome}",
        "descrizione": (
            f"Il fornitore '{nome}' ha metodo di pagamento '{metodo}' "
            f"ma non ha un IBAN configurato. I bonifici non possono essere "
            f"preparati automaticamente."
        ),
        "azione": "Fornitori → cerca fornitore → aggiungi IBAN",
        "letta": False,
        "risolta": False,
        "dati": {
            "ragione_sociale": nome,
            "fornitore_id": payload.get("fornitore_id") or payload.get("id"),
            "metodo_pagamento": metodo,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(f"[HandlerFornitore] Segnalazione IBAN mancante: {nome}")
    return {"segnalazione_creata": True, "fornitore": nome}
