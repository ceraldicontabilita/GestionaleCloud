"""\
Endpoint unificato per import Bonifici compatibile con ImportUnificato frontend.

Motivazione:
- La UI ImportUnificato carica file singoli/multipli (PDF/ZIP) verso un singolo endpoint.
- Il router archivio_bonifici espone una pipeline a job: POST /archivio-bonifici/jobs e poi /jobs/{job_id}/upload.

Questo router fornisce:
- POST /api/archivio-bonifici/jobs/import
che:
  1) crea un job
  2) carica i file sul job
  3) restituisce job_id e conteggi

NB: l'elaborazione resta in background (come da archivio_bonifici).
"""

from fastapi import APIRouter
from typing import Dict, Any

from app.routers.bonifici_module.jobs import create_job

router = APIRouter(prefix="/archivio-bonifici/jobs", tags=["Archivio Bonifici"])


@router.post("/import")
async def import_bonifici_unificato() -> Dict[str, Any]:
    """Wrapper compatibile con ImportUnificato.

    Crea un job e restituisce l'ID. La UI poi deve fare upload su:
    POST /api/archivio-bonifici/jobs/{job_id}/upload

    (questa  pipeline esiste gi0 in archivio_bonifici e usa background tasks internamente).
    """
    job = await create_job()
    job_id = job.get("id")
    return {
        "success": True,
        "message": "Job bonifici creato. Ora carico i file sul job",
        "job_id": job_id,
    }
