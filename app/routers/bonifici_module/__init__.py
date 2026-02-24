"""
Bonifici Module - Gestione Archivio Bonifici PDF.
Modulo suddiviso per funzionalità:
- common: Costanti, utility parsing, deduplicazione
- pdf_parser: Estrazione testo da PDF
- jobs: Gestione job import, upload, background processing
- transfers: CRUD bonifici, export
- riconciliazione: Riconciliazione con estratto conto, dashboard
"""
from fastapi import APIRouter, UploadFile, File, Query, BackgroundTasks
from typing import List, Optional

router = APIRouter()

# Import functions from modules
from .jobs import (
    create_job, list_jobs, get_job, upload_files
)
from .transfers import (
    list_transfers, count_transfers, transfers_summary,
    delete_transfer, get_bonifico_pdf, bulk_delete, update_transfer, export_transfers
)
from .riconciliazione import (
    riconcilia_bonifici_con_estratto, get_riconciliazione_task,
    stato_riconciliazione_bonifici, dashboard_bonifici,
    reset_riconciliazione, associa_bonifici_dipendenti
)

# === ROTTE STATICHE ===

# Jobs
router.add_api_route("/jobs", create_job, methods=["POST"])
router.add_api_route("/jobs", list_jobs, methods=["GET"])

# Transfers - Liste e statistiche
router.add_api_route("/transfers", list_transfers, methods=["GET"])
router.add_api_route("/transfers/count", count_transfers, methods=["GET"])
router.add_api_route("/transfers/summary", transfers_summary, methods=["GET"])
router.add_api_route("/transfers/bulk", bulk_delete, methods=["DELETE"])

# Export
router.add_api_route("/export", export_transfers, methods=["GET"])

# Riconciliazione
router.add_api_route("/riconcilia", riconcilia_bonifici_con_estratto, methods=["POST"])
router.add_api_route("/stato-riconciliazione", stato_riconciliazione_bonifici, methods=["GET"])
router.add_api_route("/dashboard", dashboard_bonifici, methods=["GET"])
router.add_api_route("/reset-riconciliazione", reset_riconciliazione, methods=["POST"])
router.add_api_route("/associa-dipendenti", associa_bonifici_dipendenti, methods=["POST"])

# === ROTTE DINAMICHE ===

# Jobs dinamici
router.add_api_route("/jobs/{job_id}", get_job, methods=["GET"])
router.add_api_route("/jobs/{job_id}/upload", upload_files, methods=["POST"])

# Transfers dinamici
router.add_api_route("/transfers/{transfer_id}", delete_transfer, methods=["DELETE"])
router.add_api_route("/transfers/{transfer_id}", update_transfer, methods=["PUT"])
router.add_api_route("/transfers/{transfer_id}/pdf", get_bonifico_pdf, methods=["GET"])

# Task riconciliazione
router.add_api_route("/riconcilia/task/{task_id}", get_riconciliazione_task, methods=["GET"])
