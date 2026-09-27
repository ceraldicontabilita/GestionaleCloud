"""Catalogo delle cartelle Drive del gestionale.

Dal 25/09/2026 i documenti entrano da una cartella sola, «DATI SOCIETA
CERALDI» (``GOOGLE_DRIVE_DATI_FOLDER_ID``, ``drive_cartella_unica``): le
cartelle per sezione (fatture, cedolini, F24, estratti, bonifici...) non
esistono piu', e con loro il registro JSON e le variabili per sezione.
Il catalogo pubblico non espone mai l'ID; solo l'endpoint admin lo risolve.
"""

from __future__ import annotations

from typing import Any

CARTELLA_UNICA = {"area": "dati_societa", "label": "DATI SOCIETA CERALDI"}


def get_configured_entries() -> list[dict[str, Any]]:
    """Voci con folder ID, per risoluzione admin del link Drive reale.

    Non e' mai raggiungibile dal catalogo pubblico: solo un endpoint protetto
    da `richiedi_admin` puo' chiamarla (vedi app/routers/documenti.py).
    """
    from app.services import drive_cartella_unica as cu

    folder_id = cu.radice()
    return [{**CARTELLA_UNICA, "folder_id": folder_id}] if folder_id else []


def get_public_catalog() -> dict[str, Any]:
    """Restituisce etichette e stato, senza includere mai i folder ID."""
    from app.services import drive_cartella_unica as cu

    configured = bool(cu.radice())
    folders = [{
        **CARTELLA_UNICA,
        "configured": configured,
        "mode": "automatico",
        "status": "pronto" if configured else "da_configurare",
    }]
    return {
        "folders": folders,
        "total": len(folders),
        "configured": int(configured),
        "automatic": int(configured),
    }
