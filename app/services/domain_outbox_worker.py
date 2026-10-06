"""Consumer durevole degli eventi che attraversano i domini applicativi.

La coda e i tentativi vivono in PostgreSQL. Questo modulo esegue soltanto il
lavoro applicativo e conferma ogni evento con il token ricevuto al claim.
"""
from __future__ import annotations

import logging
from typing import Any

from app.database import Database

logger = logging.getLogger(__name__)


def _campo(evento: dict[str, Any], nome: str) -> str:
    return str(evento.get(nome) or "").strip()


async def _proietta_fattura(evento: dict[str, Any]) -> dict[str, Any]:
    from app.lotti.routers.gestionale_fatture import alimenta_lotti_da_fattura

    source_id = _campo(evento, "aggregate_id")
    if not source_id:
        raise ValueError("invoice.project senza aggregate_id")

    esito = await alimenta_lotti_da_fattura(source_id)
    stato = str(esito.get("stato") or "").strip().lower()
    motivo = str(esito.get("motivo") or "").strip()

    if stato == "alimentata":
        return esito

    # Sono esiti deterministici della fattura corrente, non guasti temporanei:
    # ripeterli dieci volte non aggiunge informazione e intasa la coda.
    if stato == "saltata" and motivo in {
        "fornitore fuori dal magazzino",
        "nessun XML ne' righe strutturate",
    }:
        return esito

    raise RuntimeError(motivo or f"proiezione fattura conclusa con stato {stato or 'ignoto'}")


async def _processa(evento: dict[str, Any]) -> dict[str, Any]:
    tipo = _campo(evento, "event_type")
    if tipo == "invoice.project":
        return await _proietta_fattura(evento)
    raise ValueError(f"tipo evento outbox non supportato: {tipo or 'mancante'}")


async def processa_domain_outbox(limit: int = 20) -> dict[str, int]:
    """Lavora un lotto limitato; ogni evento viene confermato separatamente."""
    database = Database.db
    claim = getattr(database, "outbox_claim", None) if database else None
    completa = getattr(database, "outbox_complete", None) if database else None
    fallisci = getattr(database, "outbox_fail", None) if database else None
    if not all(callable(funzione) for funzione in (claim, completa, fallisci)):
        logger.debug("Outbox non disponibile sul backend dati corrente")
        return {"presi": 0, "completati": 0, "falliti": 0}

    eventi = await claim(max(1, min(int(limit), 100)))
    risultato = {"presi": len(eventi), "completati": 0, "falliti": 0}
    for evento in eventi:
        event_id = _campo(evento, "id")
        lock_token = _campo(evento, "lock_token")
        if not event_id or not lock_token:
            logger.error("Evento outbox privo di id o lock token: %s", evento)
            risultato["falliti"] += 1
            continue
        try:
            await _processa(evento)
            if not await completa(event_id, lock_token):
                raise RuntimeError("conferma outbox rifiutata: lock non piu' valido")
            risultato["completati"] += 1
        except Exception as exc:  # il database conserva errore e backoff
            logger.warning(
                "Evento outbox %s (%s) fallito: %s: %s",
                event_id, evento.get("event_type"), type(exc).__name__, exc,
            )
            try:
                await fallisci(event_id, lock_token, f"{type(exc).__name__}: {exc}")
            except Exception:
                logger.exception("Impossibile registrare il fallimento outbox %s", event_id)
            risultato["falliti"] += 1
    return risultato
