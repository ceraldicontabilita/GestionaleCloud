"""
Documenti Module - Costanti e utility condivise.
"""
import os
import logging
from pathlib import Path
from typing import Optional
import threading

logger = logging.getLogger(__name__)

# Directory documenti
DOCUMENTS_DIR = Path(os.environ.get("DOCUMENTS_DIR", "/app/uploads/documenti"))
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

# Collections
COL_DOCUMENTS = "documents_inbox"
COL_EMAIL_TASKS = "email_download_tasks"
COL_EMAIL_SYNC = "email_sync_status"

# Lock per operazioni email
_email_operation_lock = threading.Lock()
_current_operation: Optional[str] = None


def is_email_operation_running() -> bool:
    """Verifica se un'operazione email è in corso."""
    return _current_operation is not None


def get_current_operation() -> Optional[str]:
    """Restituisce l'operazione email corrente."""
    return _current_operation


def set_current_operation(operation: Optional[str]):
    """Imposta l'operazione email corrente."""
    global _current_operation
    _current_operation = operation


# Categorie documenti
CATEGORIES = {
    "fatture": "Fatture",
    "f24": "Modelli F24",
    "estratti_conto": "Estratti Conto",
    "buste_paga": "Buste Paga",
    "contratti": "Contratti",
    "altro": "Altro"
}
