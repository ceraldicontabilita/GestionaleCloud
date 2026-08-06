"""Mittenti attendibili — collezione canonica unica `mittenti_email` (P2-2).

Prima esistevano DUE collezioni per lo stesso concetto (mittenti fidati per
canale/tipo documento):
  - `mittenti_email`       → pattern / canale / tipo_documento / attivo
                             (gestita dalla CRUD in email_download.py)
  - `mittenti_attendibili` → indirizzo_email / tipo_documento / canale / attivo
                             (letta solo dal verbali_gmail_scanner)

`mittenti_email` è un superset (ha già `tipo_documento`; `indirizzo_email` è solo
un `pattern` esatto), quindi diventa la fonte UNICA. Qui si forniscono:
  - un accessor unico (`senders_attendibili`) che legge la collezione canonica e,
    per retro-compatibilità, unisce la legacy finché non è stata migrata;
  - una migrazione idempotente dei dati legacy (nessuna perdita di configurazioni).
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Set

COLL = "mittenti_email"
COLL_LEGACY = "mittenti_attendibili"


# Mittenti istituzionali gia' previsti dai servizi Verbali/PagoPA, resi
# espliciti nella collezione canonica. Il trasportatore PEC
# `posta-certificata@pec.aruba.it` NON e' attendibile da solo: consegna PEC di
# qualunque origine e causava l'acquisizione di documenti non pertinenti.
BUILTIN_MITTENTI = (
    {
        "pattern": "notifica.pl.napoli@pec.it",
        "tipo_documento": "verbale",
        "descrizione": "Polizia Locale Napoli - notifiche verbali",
    },
    {
        "pattern": "asianapoli.protocollo@pec.it",
        "tipo_documento": "verbale",
        "descrizione": "ASIA Napoli - verbali Comune di Napoli",
    },
    {
        "pattern": "ufficiosanzioni@arval.it",
        "tipo_documento": "verbale",
        "descrizione": "Arval - ufficio sanzioni",
    },
    {
        "pattern": "comando.pm@pec.comune.napoli.it",
        "tipo_documento": "verbale",
        "descrizione": "Polizia Municipale Napoli",
    },
    {
        "pattern": "prefettura.napoli@pec.interno.it",
        "tipo_documento": "verbale",
        "descrizione": "Prefettura di Napoli",
    },
    {
        "pattern": "partenopay@ext.comune.napoli.it",
        "tipo_documento": "pagopa",
        "descrizione": "Comune di Napoli - PagoPA",
    },
    {
        "pattern": "noreply-checkout@ricevute.pagopa.it",
        "tipo_documento": "pagopa",
        "descrizione": "Ricevute PagoPA",
    },
    {
        "pattern": "noreply.enelenergia@enel.com",
        "tipo_documento": "bolletta_energia",
        "descrizione": "Enel Energia - bollette e consumi elettrici",
    },
    {
        "pattern": "rosaria.marotta@email.it",
        "tipo_documento": "f24",
        "descrizione": "Studio Marotta - F24 e documenti fiscali",
    },
)


def _addr(m: Dict[str, Any]) -> str:
    return (m.get("indirizzo_email") or m.get("pattern") or "").strip().lower()


async def senders_attendibili(db, tipo_documento: str, canale: str) -> Set[str]:
    """Insieme degli indirizzi/pattern attendibili per (tipo_documento, canale),
    letti dalla collezione canonica + (back-compat) dalla legacy non ancora
    migrata."""
    filtro = {"tipo_documento": tipo_documento, "canale": canale, "attivo": True}
    out: Set[str] = set()
    async for m in db[COLL].find(filtro):
        a = _addr(m)
        if a:
            out.add(a)
    # Back-compat: unisce la legacy finché la migrazione non è stata eseguita.
    try:
        async for m in db[COLL_LEGACY].find(filtro):
            a = _addr(m)
            if a:
                out.add(a)
    except Exception:
        pass
    return out


async def assicura_mittenti_builtin(db) -> Dict[str, Any]:
    """Registra i mittenti istituzionali in modo idempotente.

    Usa solo ``$setOnInsert``: una scelta dell'utente (per esempio disattivare
    un mittente) non viene mai sovrascritta al riavvio.
    """
    inseriti = gia_presenti = 0
    for item in BUILTIN_MITTENTI:
        pattern = item["pattern"].strip().lower()
        result = await db[COLL].update_one(
            {"pattern": pattern, "canale": "gmail"},
            {"$setOnInsert": {
                "id": str(uuid.uuid4()),
                "pattern": pattern,
                "indirizzo_email": pattern,
                "canale": "gmail",
                "tipo_documento": item["tipo_documento"],
                "descrizione": item["descrizione"],
                "attivo": True,
                "builtin": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        if result.upserted_id is not None:
            inseriti += 1
        else:
            gia_presenti += 1
    return {"inseriti": inseriti, "gia_presenti": gia_presenti}


async def migra_mittenti_legacy(db, dry_run: bool = True) -> Dict[str, Any]:
    """Copia i mittenti da `mittenti_attendibili` a `mittenti_email` (canonica),
    saltando quelli già presenti (per pattern+canale). Idempotente. Con
    `dry_run=True` non scrive nulla: riporta solo cosa farebbe."""
    legacy = await db[COLL_LEGACY].find({}).to_list(1000)
    migrati = gia_presenti = senza_indirizzo = 0
    for m in legacy:
        addr = _addr(m)
        if not addr:
            senza_indirizzo += 1
            continue
        canale = (m.get("canale") or "gmail").lower()
        if await db[COLL].find_one({"pattern": addr, "canale": canale}):
            gia_presenti += 1
            continue
        if not dry_run:
            await db[COLL].insert_one({
                "id": str(uuid.uuid4()),
                "pattern": addr,
                "indirizzo_email": m.get("indirizzo_email") or addr,
                "canale": canale,
                "tipo_documento": m.get("tipo_documento") or "generico",
                "descrizione": m.get("descrizione") or "migrato da mittenti_attendibili",
                "attivo": bool(m.get("attivo", True)),
                "builtin": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "migrato_da": COLL_LEGACY,
            })
        migrati += 1
    return {
        "totale_legacy": len(legacy),
        "migrati": migrati,
        "gia_presenti": gia_presenti,
        "senza_indirizzo": senza_indirizzo,
        "dry_run": dry_run,
    }
