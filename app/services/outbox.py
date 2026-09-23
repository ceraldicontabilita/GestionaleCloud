"""Outbox persistente per gli eventi di dominio (RST-0510).

La riga evento + le consegne per consumer sopravvivono al processo.
Il bus in memoria resta il dispatcher degli handler già registrati.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

PAYLOAD_VERSION = 1


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


def chiave_idempotenza(
    event_type: str,
    entity_id: str,
    entity_version: int,
    extra: str = "",
) -> str:
    grezzo = f"{event_type}|{entity_id}|{entity_version}|{extra}"
    return hashlib.sha256(grezzo.encode("utf-8")).hexdigest()


def consumatori_registrati(event_type: str) -> List[str]:
    from app.services.event_bus import elenco_handler

    return [h.__name__ for h in elenco_handler(event_type)]


def _entity_id(payload: Dict[str, Any]) -> str:
    for chiave in (
        "fattura_id",
        "cedolino_id",
        "documento_id",
        "f24_id",
        "movimento_id",
        "dipendente_id",
        "entity_id",
        "id",
    ):
        valore = payload.get(chiave)
        if valore:
            return str(valore)
    return ""


def _entity_version(payload: Dict[str, Any]) -> int:
    grezzo = payload.get("entity_version") or payload.get("version") or 1
    try:
        return int(grezzo)
    except (TypeError, ValueError):
        return 1


async def registra(
    db,
    event_type: str,
    payload: Dict[str, Any],
    source_module: str = "",
    actor: str = "sistema",
    consumers: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Scrive l'evento e le consegne pending. Idempotente sulla chiave."""
    entity_id = _entity_id(payload)
    entity_version = _entity_version(payload)
    idem = payload.get("idempotency_key") or chiave_idempotenza(
        event_type, entity_id, entity_version
    )
    event_id = str(payload.get("event_id") or uuid.uuid4())
    nomi = list(consumers) if consumers is not None else consumatori_registrati(event_type)

    rpc = getattr(db, "_rpc", None)
    if callable(rpc):
        try:
            esito = await rpc(
                "gc_outbox_enqueue",
                {
                    "p_id": event_id,
                    "p_event_type": event_type,
                    "p_entity_id": entity_id,
                    "p_entity_version": entity_version,
                    "p_payload": payload,
                    "p_payload_version": PAYLOAD_VERSION,
                    "p_idempotency_key": idem,
                    "p_source_module": source_module,
                    "p_actor": actor,
                    "p_consumers": nomi,
                },
            )
            if isinstance(esito, dict) and esito.get("id"):
                return {
                    "id": esito["id"],
                    "idempotency_key": idem,
                    "duplicato": bool(esito.get("duplicato")),
                    "consumers": nomi,
                }
        except Exception:
            logger.exception("RPC outbox enqueue non riuscita, fallback collezione")

    esistente = await db["outbox_events"].find_one({"idempotency_key": idem})
    if esistente:
        return {
            "id": esistente.get("id"),
            "idempotency_key": idem,
            "duplicato": True,
            "consumers": nomi,
        }

    documento = {
        "id": event_id,
        "event_type": event_type,
        "entity_id": entity_id,
        "entity_version": entity_version,
        "payload": payload,
        "payload_version": PAYLOAD_VERSION,
        "idempotency_key": idem,
        "source_module": source_module,
        "actor": actor,
        "created_at": _ora(),
    }
    await db["outbox_events"].insert_one(documento)
    for nome in nomi:
        await db["outbox_deliveries"].update_one(
            {"event_id": event_id, "consumer": nome},
            {
                "$setOnInsert": {
                    "id": f"{event_id}:{nome}",
                    "event_id": event_id,
                    "consumer": nome,
                    "stato": "pending",
                    "tentativi": 0,
                    "errore": None,
                    "created_at": _ora(),
                },
                "$set": {"updated_at": _ora()},
            },
            upsert=True,
        )
    return {
        "id": event_id,
        "idempotency_key": idem,
        "duplicato": False,
        "consumers": nomi,
    }


async def registra_esito(
    db,
    event_id: str,
    consumer: str,
    stato: str,
    errore: Optional[str] = None,
) -> None:
    if stato not in {"done", "error", "non_applicabile", "pending"}:
        raise ValueError("stato outbox non valido")
    rpc = getattr(db, "_rpc", None)
    if callable(rpc):
        try:
            await rpc(
                "gc_outbox_ack",
                {
                    "p_event_id": event_id,
                    "p_consumer": consumer,
                    "p_stato": stato,
                    "p_errore": errore,
                },
            )
            return
        except Exception:
            logger.exception("RPC outbox ack non riuscita, fallback collezione")
    await db["outbox_deliveries"].update_one(
        {"event_id": event_id, "consumer": consumer},
        {
            "$set": {
                "stato": stato,
                "errore": (errore or "")[:500] if stato == "error" else None,
                "leased_until": None,
                "updated_at": _ora(),
            }
        },
        upsert=True,
    )


async def riprocessa_pendenti(db, limite: int = 25) -> Dict[str, int]:
    """Riesegue le consegne pending/error. Non duplica se l'handler è idempotente."""
    from app.services import event_bus

    stats = {"esaminati": 0, "ok": 0, "errori": 0, "saltati": 0}
    rpc = getattr(db, "_rpc", None)
    lotti: List[Dict[str, Any]] = []
    if callable(rpc):
        try:
            grezzo = await rpc(
                "gc_outbox_claim",
                {"p_limit": limite, "p_lease_seconds": 120},
            )
            if isinstance(grezzo, list):
                lotti = grezzo
        except Exception:
            logger.exception("RPC outbox claim non riuscita")
            return stats
    else:
        cursor = db["outbox_deliveries"].find(
            {"stato": {"$in": ["pending", "error"]}}
        )
        async for riga in cursor:
            evento = await db["outbox_events"].find_one({"id": riga.get("event_id")})
            if not evento:
                stats["saltati"] += 1
                continue
            lotti.append({**evento, **riga, "payload": evento.get("payload") or {}})
            if len(lotti) >= limite:
                break

    for riga in lotti:
        stats["esaminati"] += 1
        consumer = riga.get("consumer") or ""
        event_type = riga.get("event_type") or ""
        payload = dict(riga.get("payload") or {})
        event_id = riga.get("event_id") or riga.get("id")
        handler = next(
            (h for h in event_bus.elenco_handler(event_type) if h.__name__ == consumer),
            None,
        )
        if handler is None:
            await registra_esito(db, event_id, consumer, "non_applicabile")
            stats["saltati"] += 1
            continue
        contesto = {
            "event_type": event_type,
            "timestamp": _ora(),
            "source_module": riga.get("source_module") or "outbox",
            "user": riga.get("actor") or "sistema",
            "event_id": event_id,
            **payload,
        }
        try:
            await handler(contesto, db)
            await registra_esito(db, event_id, consumer, "done")
            stats["ok"] += 1
        except Exception as exc:
            await registra_esito(db, event_id, consumer, "error", str(exc))
            stats["errori"] += 1
            logger.exception(
                "Outbox consumer %s fallito su %s/%s",
                consumer,
                event_type,
                event_id,
            )
    return stats
