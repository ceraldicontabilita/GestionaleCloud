"""Porta su Supabase Storage le foto ricette ancora solo su Google Drive.

Una ricetta con ``foto_drive_id`` e senza ``foto_storage_path`` serviva ogni
foto leggendola da Drive a ogni richiesta: ~2 MB di PNG per card, ~300 card in
parallelo, e ogni richiesta occupava un thread per decine di secondi. Qui si
copia un file per volta (memoria bassa) nell'archivio canonico e si annota
sul record; ``GET /api/foto/<id>`` poi rimanda al CDN di Storage.

Idempotente: una ricetta con ``foto_storage_path`` non si ritocca (secondo
giro = 0 nuovi); l'id e il ``foto_url`` restano quelli, il file su Drive non
si tocca. Un fallimento resta nel risultato col motivo, mai muto.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

LIMITE_BYTE = 15 * 1024 * 1024


def _da_migrare(ricetta: dict) -> bool:
    return bool(str(ricetta.get("foto_drive_id") or "").strip()) and not str(
        ricetta.get("foto_storage_path") or ""
    ).strip()


def _copia_una(service: Any, ricetta: dict) -> dict:
    """Scarica da Drive e carica su Storage (bloccante: va in un thread)."""
    from app.lotti.servizi import drive_foto_ricette, supabase_foto_ricette
    from app.services.drive_download import scarica_bytes

    file_id = str(ricetta["foto_drive_id"]).strip()
    cartella = str(ricetta.get("foto_drive_folder_id") or "").strip()
    meta = drive_foto_ricette._metadata(service, file_id, folder_id=cartella)
    mime = str(meta.get("mimeType") or "")
    if not mime.startswith("image/"):
        raise ValueError(f"il file Drive non e' un'immagine ({mime or 'tipo ignoto'})")
    if int(meta.get("size") or 0) > LIMITE_BYTE:
        raise ValueError("immagine oltre il limite di 15 MB")
    contenuto = scarica_bytes(service, file_id)
    if not contenuto:
        raise ValueError("file Drive vuoto")
    caricata = supabase_foto_ricette.carica(
        ricetta_id=str(ricetta.get("id") or file_id),
        contenuto=contenuto,
        mime=mime,
        filename=meta.get("name"),
    )
    caricata["mime"] = mime
    return caricata


async def migra_lotto(db, limite: int = 5) -> dict:
    """Un lotto di al massimo ``limite`` foto. ``db`` e' il database Lotti."""
    ricette = await db.ricette.find(
        {}, {"_id": 0, "id": 1, "foto_drive_id": 1, "foto_drive_folder_id": 1, "foto_storage_path": 1}
    ).to_list(5000)
    da_fare = [r for r in ricette if r.get("id") and _da_migrare(r)]
    esito = {"da_migrare": len(da_fare), "migrate": 0, "errori": 0, "dettaglio_errori": []}
    if not da_fare:
        esito["restano"] = 0
        return esito

    from app.lotti.servizi import drive_foto_ricette

    servizi: dict[str, Any] = {}
    try:
        for ricetta in da_fare[: max(1, int(limite))]:
            cartella = str(ricetta.get("foto_drive_folder_id") or "").strip()
            try:
                if cartella not in servizi:
                    servizi[cartella] = await asyncio.to_thread(
                        drive_foto_ricette.build_drive_service, cartella
                    )
                caricata = await asyncio.to_thread(_copia_una, servizi[cartella], ricetta)
                await db.ricette.update_one(
                    {"id": ricetta["id"]},
                    {"$set": {
                        "foto_storage_bucket": caricata["bucket"],
                        "foto_storage_path": caricata["path"],
                        "foto_sha256": caricata["sha256"],
                        "foto_content_type": caricata["mime"],
                        "foto_migrated_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
                esito["migrate"] += 1
            except Exception as exc:  # noqa: BLE001 - ogni foto e' indipendente
                esito["errori"] += 1
                motivo = f"{type(exc).__name__}: {exc}"
                logger.warning("[FOTO-RICETTE] ricetta %s non migrata: %s", ricetta.get("id"), motivo)
                if len(esito["dettaglio_errori"]) < 10:
                    esito["dettaglio_errori"].append({"ricetta_id": ricetta.get("id"), "motivo": motivo})
    finally:
        for service in servizi.values():
            close = getattr(service, "close", None)
            if callable(close):
                await asyncio.to_thread(close)
    esito["restano"] = esito["da_migrare"] - esito["migrate"]
    return esito
