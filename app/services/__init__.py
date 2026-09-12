"""
Services package.
Business logic layer for all operations.

ARCHITETTURA:
- business_rules.py: Regole di business centralizzate e validazioni
- invoice_service_v2.py: Gestione fatture con controlli sicurezza
- corrispettivi_service.py: Gestione corrispettivi con propagazione Prima Nota
- *_service.py: Altri servizi specifici
"""
from .auth_service import AuthService
from .invoice_service_v2 import InvoiceServiceV2, get_invoice_service_v2
from .warehouse_service import WarehouseService
from .accounting_service import AccountingService
from .accounting_entries_service import AccountingEntriesService
from .cash_service import CashService
from .chart_service import ChartOfAccountsService
from .email_service import EmailService
from .business_rules import BusinessRules, ValidationResult, DataFlowManager
from .corrispettivi_service import CorrispettiviService, get_corrispettivi_service

from .data_propagation import DataPropagationService, get_propagation_service


def _wire_canonical_drive_credentials() -> None:
    """Instrada ogni scanner verso una credenziale con accesso provato.

    I vecchi service account dedicati non hanno tutti gli stessi permessi sulla
    gerarchia GESTIONALE ricostruita. La scelta quindi non si basa sul nome
    della variabile ma su un vero ``files.get`` sul folder canonico del canale.
    I secret non vengono letti nei log, copiati o modificati.
    """
    from contextvars import ContextVar
    from googleapiclient.discovery import build

    from .drive_credential_probe import load_credentials_for_folder
    from . import drive_invoice_ingest as _drive_invoice
    from . import drive_cedolini_ingest as _drive_cedolini
    from . import drive_quietanze_ingest as _drive_quietanze
    from . import drive_f24_ingest as _drive_f24
    from . import drive_documenti_ingest as _drive_documenti

    def _loader(folder_getter):
        def load():
            return load_credentials_for_folder(folder_getter())
        return load

    _drive_invoice._load_credentials_fatture = _loader(_drive_invoice._folder_id)
    _drive_cedolini._load_credentials_cedolini = _loader(_drive_cedolini._folder_id)
    _drive_quietanze._load_credentials_quietanze = _loader(_drive_quietanze._folder_id)
    _drive_f24._load_credentials = _loader(_drive_f24._folder_id)

    # L'ingest generico serve piu' canali con un solo modulo. Un ContextVar
    # conserva il canale della singola coroutine, quindi anche chiamate
    # concorrenti non possono scambiarsi la credenziale scelta.
    active_channel: ContextVar[str | None] = ContextVar(
        "drive_documenti_active_channel", default=None
    )
    original_sync = _drive_documenti.sync
    original_build = _drive_documenti._build_drive_service

    async def sync_with_folder_probe(db, canale: str):
        token = active_channel.set(canale)
        try:
            return await original_sync(db, canale)
        finally:
            active_channel.reset(token)

    def build_with_folder_probe():
        canale = active_channel.get()
        if not canale:
            return original_build()
        folder_id = _drive_documenti._folder_id(canale)
        creds, err = load_credentials_for_folder(folder_id)
        if creds is None:
            return None, err
        try:
            return build("drive", "v3", credentials=creds, cache_discovery=False), None
        except Exception as exc:
            return None, f"errore costruzione client Drive: {exc}"

    _drive_documenti.sync = sync_with_folder_probe
    _drive_documenti._build_drive_service = build_with_folder_probe


_wire_canonical_drive_credentials()


__all__ = [
    # Core Services
    "AuthService",
    "InvoiceServiceV2",
    "get_invoice_service_v2",
    "WarehouseService",
    "AccountingService",
    "AccountingEntriesService",
    "CashService",
    "ChartOfAccountsService",
    "EmailService",
    # V2 Services with Security
    "CorrispettiviService",
    "get_corrispettivi_service",
    # Propagation
    "DataPropagationService",
    "get_propagation_service",
    # Business Rules
    "BusinessRules",
    "ValidationResult",
    "DataFlowManager"
]
