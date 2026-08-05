"""Catalogo sicuro delle cartelle Drive configurate in ambiente."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings


_AUTOMATIC_AREAS = {
    "fatture", "cedolini", "corrispettivi", "quietanze", "estratti_conto",
    "bonifici_dipendenti", "cartelle_esattoriali", "avvisi_bonari", "f24",
    "verbali", "dichiarazioni_iva", "documenti",
    "paypal", "noleggio",
}

_AREA_ALIASES = {
    "busta_paga": ("cedolini", "buste_paga"),
    "cedolino": ("cedolini", "buste_paga"),
    "cartella_esattoriale": ("cartelle_esattoriali", "avvisi_esattoriali"),
    "avviso_bonario": ("avvisi_bonari",),
    "verbale": ("verbali",),
    "paypal": ("paypal", "estratti_conto_paypal"),
    "noleggio": ("noleggio", "noleggio_auto"),
    "f24": ("f24", "quietanze"),
    "quietanza": ("quietanze", "f24"),
    "dichiarazione_iva": ("dichiarazioni_iva",),
    "estratto_conto": ("estratti_conto",),
    "bonifico": ("bonifici_dipendenti", "bonifici"),
    "fattura": ("fatture",),
    "fattura_xml": ("fatture",),
}


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9_]+", "_", text).strip("_")


def _registry_entries() -> list[dict[str, Any]]:
    raw = (settings.DRIVE_FOLDER_REGISTRY_JSON or "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if isinstance(payload, dict):
        payload = payload.get("folders", [])
    return [entry for entry in payload if isinstance(entry, dict)] if isinstance(payload, list) else []


def get_folder_id(area: str) -> str | None:
    """Risolve internamente una cartella configurata senza esporne l'ID via API."""
    requested = _slug(area)
    candidates = (requested, *_AREA_ALIASES.get(requested, ()))
    entries = _registry_entries()
    for candidate in candidates:
        for entry in entries:
            entry_area = _slug(entry.get("area") or entry.get("label"))
            if entry_area != candidate:
                continue
            folder_id = str(entry.get("folder_id") or "").strip()
            if folder_id:
                return folder_id
    return None


def get_generic_documents_folder_id() -> str | None:
    """Radice sotto cui creare cartelle documentali mancanti, se configurata."""
    for area in ("documenti", "documenti_generici", "archivio_documenti"):
        folder_id = get_folder_id(area)
        if folder_id:
            return folder_id
    return None


def get_public_catalog() -> dict[str, Any]:
    """Restituisce etichette e stato, senza includere mai i folder ID."""
    folders: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in _registry_entries():
        area = _slug(entry.get("area") or entry.get("label"))
        if not area or area in seen:
            continue
        seen.add(area)
        configured = bool(str(entry.get("folder_id") or "").strip())
        automatic = area in _AUTOMATIC_AREAS
        folders.append({
            "area": area,
            "label": str(entry.get("label") or area.replace("_", " ").title()).strip(),
            "configured": configured,
            "mode": "automatico" if automatic else "catalogo",
            "status": "pronto" if configured and automatic else "catalogato" if configured else "da_configurare",
        })

    folders.sort(key=lambda item: (item["mode"] != "automatico", item["label"].casefold()))
    return {
        "folders": folders,
        "total": len(folders),
        "configured": sum(1 for item in folders if item["configured"]),
        "automatic": sum(1 for item in folders if item["configured"] and item["mode"] == "automatico"),
    }
