"""Letture puntuali e canoniche per deduplicare documenti tramite impronta."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


async def find_one_by_hashes(
    db,
    collection: str,
    candidates: Iterable[tuple[str, str | None]],
    projection: dict[str, Any] | None = None,
):
    """Cerca un documento senza query ``$or`` che causano scansioni complete.

    Ogni candidato viene risolto dalla RPC indicizzata del runtime. Le coppie
    duplicate vengono ignorate mantenendo l'ordine di priorita' del chiamante.
    """
    seen: set[tuple[str, str]] = set()
    for field, raw_value in candidates:
        if raw_value in (None, ""):
            continue
        value = str(raw_value)
        candidate = (field, value)
        if candidate in seen:
            continue
        seen.add(candidate)
        found = await db[collection].find_one({field: value}, projection)
        if found:
            return found
    return None
