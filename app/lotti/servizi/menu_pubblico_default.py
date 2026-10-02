"""Attiva una sola volta il Menu pubblico sulle ricette gia' esistenti."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
MARKER = "menu_pubblico_tutte_ricette_20261002_v1"


async def applica(db) -> dict:
    stato = await db.sistema_stato.find_one({"chiave": MARKER}, {"_id": 0})
    if stato and stato.get("stato") == "completato":
        return stato.get("risultato") or {"gia_eseguito": True}
    await db.sistema_stato.update_one(
        {"chiave": MARKER},
        {"$set": {"chiave": MARKER, "stato": "in_corso", "avviato_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    esito = await db.ricette.update_many(
        {"menu_pubblico": {"$ne": True}}, {"$set": {"menu_pubblico": True}}
    )
    from app.lotti.servizi.menu_backfill import ripubblica_menu

    risultato = await ripubblica_menu(db, dry_run=False)
    riepilogo = {"ricette_attivate": int(getattr(esito, "modified_count", 0)), **risultato}
    stato_finale = "completato" if not risultato.get("errori") and not risultato.get("troncato") else "da_rivedere"
    await db.sistema_stato.update_one(
        {"chiave": MARKER},
        {"$set": {"stato": stato_finale, "terminato_at": datetime.now(timezone.utc).isoformat(), "risultato": riepilogo}},
        upsert=True,
    )
    logger.info("Menu pubblico ricette: %s", riepilogo)
    return riepilogo


async def applica_sicuro(db) -> None:
    try:
        await applica(db)
    except Exception:  # il recupero non deve impedire l'avvio del gestionale
        logger.exception("Attivazione predefinita delle ricette nel Menu non completata")
