"""Task Render Workflows non invasivi per GestionaleCloud."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen

from render_sdk import Retry, Workflows

try:
    from .document_ingest import ingest_document_inbox, scan_document_inbox_preview
except ImportError:  # Render avvia main.py dalla root directory del Workflow.
    from document_ingest import ingest_document_inbox, scan_document_inbox_preview


PRODUCTION_HEALTH_URL = "https://impresasemplice.online/api/health"
app = Workflows()


def fetch_production_health(url: str = PRODUCTION_HEALTH_URL) -> dict[str, Any]:
    """Legge e valida lo stato pubblico senza accedere a segreti o dati fiscali."""
    request = Request(url, headers={"User-Agent": "GestionaleCloud-Workflow/1.0"})
    with urlopen(request, timeout=20) as response:  # noqa: S310 - URL costante HTTPS
        if response.status != 200:
            raise RuntimeError(f"Health check HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))

    if payload.get("status") != "healthy":
        raise RuntimeError(f"Servizio non healthy: {payload.get('status')!r}")
    if payload.get("storage") != "drive_sheets":
        raise RuntimeError(f"Archivio inatteso: {payload.get('storage')!r}")
    if int(payload.get("hydration_errors", 0)) != 0:
        raise RuntimeError(
            f"Errori idratazione presenti: {payload.get('hydration_errors')!r}"
        )

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": payload["status"],
        "storage": payload["storage"],
        "database": payload.get("database"),
        "hydrated_rows": int(payload.get("hydrated_rows", 0)),
        "hydration_errors": 0,
        "deploy_commit": payload.get("deploy_commit"),
    }


@app.task(
    name="production_health_check",
    plan="starter",
    retry=Retry(max_retries=0, wait_duration_ms=0),
    timeout_seconds=60,
)
def production_health_check() -> dict[str, Any]:
    """Controlla che la produzione e il registro Drive/Sheets siano sani."""
    return fetch_production_health()


@app.task(
    name="calderone_documenti_preview",
    plan="starter",
    retry=Retry(max_retries=1, wait_duration_ms=30000),
    timeout_seconds=7200,
)
def calderone_documenti_preview(max_documents: int = 20_000) -> dict[str, Any]:
    """Confronto universale sola lettura contro l'indice documentale canonico."""
    return scan_document_inbox_preview(max_documents=max_documents)


@app.task(
    name="calderone_documenti_ingest",
    plan="starter",
    retry=Retry(max_retries=0, wait_duration_ms=0),
    timeout_seconds=7200,
)
def calderone_documenti_ingest(
    confirm: bool = False, max_documents: int = 100,
) -> dict[str, Any]:
    """Invia solo file nuovi e riconosciuti dopo doppia conferma esplicita."""
    return ingest_document_inbox(
        confirm=confirm, max_documents=max_documents,
    )


if __name__ == "__main__":
    app.start()
