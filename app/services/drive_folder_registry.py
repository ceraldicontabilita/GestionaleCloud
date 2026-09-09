"""Catalogo sicuro delle cartelle Drive configurate in ambiente."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings


_AUTOMATIC_AREAS = {
    "fatture", "cedolini", "corrispettivi", "quietanze", "estratti_conto",
    "bonifici_dipendenti", "cartelle_esattoriali", "avvisi_bonari", "f24",
    "verbali", "verbali_auto", "dichiarazioni_iva", "documenti",
    "paypal", "noleggio",
    "partenopay",
    "carte", "nexi", "estratti_conto_carte",
}

_AREA_ALIASES = {
    "busta_paga": ("cedolini", "buste_paga"),
    "cedolino": ("cedolini", "buste_paga"),
    "cartella_esattoriale": ("cartelle_esattoriali", "avvisi_esattoriali"),
    "avviso_bonario": ("avvisi_bonari",),
    # Il catalogo Drive reale usa `verbali_auto`; i servizi documentali usano
    # sia il singolare `verbale` sia l'area canonica `verbali`.
    "verbale": ("verbali", "verbali_auto"),
    "verbali": ("verbali_auto",),
    "paypal": ("paypal", "estratti_conto_paypal"),
    "noleggio": ("noleggio", "noleggio_auto"),
    "f24": ("f24", "quietanze"),
    "quietanza": ("quietanze", "f24"),
    "dichiarazione_iva": ("dichiarazioni_iva",),
    "estratto_conto": ("estratti_conto",),
    "nexi": ("carte", "estratti_conto_carte", "carta_nexi"),
    "carta": ("carte", "nexi", "estratti_conto_carte"),
    "bonifico": ("bonifici_dipendenti", "bonifici"),
    "fattura": ("fatture",),
    "fattura_xml": ("fatture",),
    "partenopay": ("partenopay",),
}

# Le variabili esplicite di Render sono la sorgente primaria per gli
# importatori automatici. Il registro JSON serve al catalogo completo e alle
# aree che non hanno una variabile dedicata; non deve poter sovrascrivere una
# configurazione specialistica con un ID storico.
_CANONICAL_SETTING_AREAS = {
    "fatture": ("GOOGLE_DRIVE_FATTURE_FOLDER_ID", "Fatture XML e PDF"),
    "cedolini": ("GOOGLE_DRIVE_CEDOLINI_FOLDER_ID", "Cedolini paga"),
    "corrispettivi": ("GOOGLE_DRIVE_CORRISPETTIVI_FOLDER_ID", "Corrispettivi"),
    "quietanze": ("GOOGLE_DRIVE_QUIETANZE_FOLDER_ID", "Quietanze"),
    "estratti_conto": ("GOOGLE_DRIVE_ESTRATTI_FOLDER_ID", "Estratti conto"),
    "bonifici_dipendenti": ("GOOGLE_DRIVE_BONIFICI_FOLDER_ID", "Bonifici effettuati"),
    "dichiarazioni_iva": ("GOOGLE_DRIVE_DICHIARAZIONI_IVA_FOLDER_ID", "Dichiarazioni IVA"),
    "cartelle_esattoriali": ("GOOGLE_DRIVE_CARTELLE_ESATTORIALI_FOLDER_ID", "Cartelle esattoriali"),
    "avvisi_bonari": ("GOOGLE_DRIVE_AVVISI_BONARI_FOLDER_ID", "Avvisi bonari"),
    "f24": ("DRIVE_F24_FOLDER_ID", "F24"),
    "carte": ("DRIVE_CARTE_FOLDER_ID", "Carte"),
    "paypal": ("DRIVE_PAYPAL_FOLDER_ID", "PayPal"),
    "noleggio": ("DRIVE_NOLEGGIO_FOLDER_ID", "Noleggio"),
    "verbali_auto": ("DRIVE_VERBALI_FOLDER_ID", "Verbali auto"),
}

_runtime_entries: list[dict[str, Any]] = []


def set_runtime_folders(entries: list[dict[str, Any]]) -> None:
    """Aggiorna il registro scoperto senza mutare configurazioni o segreti."""
    global _runtime_entries
    _runtime_entries = [dict(entry) for entry in entries if isinstance(entry, dict)]


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9_]+", "_", text).strip("_")


def _registry_entries() -> list[dict[str, Any]]:
    raw = (settings.DRIVE_FOLDER_REGISTRY_JSON or "").strip()
    if not raw:
        return list(_runtime_entries)
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if isinstance(payload, dict):
        payload = payload.get("folders", [])
    configured = [entry for entry in payload if isinstance(entry, dict)] if isinstance(payload, list) else []
    # Il valore scoperto e persistito prevale sul JSON storico per la stessa
    # area; il catalogo pubblico continua a non esporre gli ID.
    merged = {_slug(entry.get("area") or entry.get("label")): entry for entry in configured}
    for entry in _runtime_entries:
        merged[_slug(entry.get("area") or entry.get("label"))] = entry
    # Una variabile esplicita e verificata su Render prevale sul JSON, che puo'
    # contenere un catalogo precedente. Cosi tutti i pulsanti e gli importatori
    # vedono la stessa cartella senza richiedere duplicazioni di ID.
    for area, (setting_name, label) in _CANONICAL_SETTING_AREAS.items():
        folder_id = str(getattr(settings, setting_name, None) or "").strip()
        if folder_id:
            merged[area] = {"area": area, "label": label, "folder_id": folder_id}
    return list(merged.values())


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


def get_configured_entries() -> list[dict[str, Any]]:
    """Voci con folder ID, per risoluzione admin del link Drive reale.

    Non e' mai raggiungibile dal catalogo pubblico: solo un endpoint protetto
    da `richiedi_admin` puo' chiamarla (vedi app/routers/documenti.py).
    """
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for entry in _registry_entries():
        area = _slug(entry.get("area") or entry.get("label"))
        if not area or area in seen:
            continue
        folder_id = str(entry.get("folder_id") or "").strip()
        if not folder_id:
            continue
        seen.add(area)
        result.append({
            "area": area,
            "label": str(entry.get("label") or area.replace("_", " ").title()).strip(),
            "folder_id": folder_id,
        })
    return result


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
