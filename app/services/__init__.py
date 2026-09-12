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


# Accesso Drive canonico
# ----------------------
# Il censimento live del 12/09/2026 ha verificato che l'account dedicato
# agli Estratti conto e' quello che riesce ad accedere alla gerarchia Drive
# canonica GESTIONALE, mentre alcuni vecchi account dedicati per canale
# restituiscono 404 sui nuovi folder ID. Non cancelliamo ne' sovrascriviamo i
# relativi secret Render: instradiamo soltanto gli scanner documentali
# canonici verso la credenziale gia' verificata, con fallback alla credenziale
# storica quando quella canonica non e' configurata.
#
# L'instradamento e' limitato ai cinque scanner oggetto del censimento:
# fatture, cedolini, quietanze/F24 e documenti generici (bonifici/cartelle).
# Altri servizi, incluso il registro Google Sheets, conservano le proprie
# credenziali e quindi non subiscono effetti collaterali.
def _wire_canonical_drive_credentials() -> None:
    from app.config import settings
    from . import drive_invoice_ingest as _drive_invoice

    original_shared_loader = _drive_invoice._load_credentials

    def canonical_loader():
        raw = getattr(settings, "GOOGLE_SERVICE_ACCOUNT_JSON_ESTRATTI_CONTO", None)
        if not raw:
            return original_shared_loader()
        try:
            from google.oauth2 import service_account

            info = _drive_invoice._parse_sa_json(raw)
            return service_account.Credentials.from_service_account_info(
                info, scopes=_drive_invoice._SCOPES
            ), None
        except Exception as exc:
            # Un secret canonico malformato non deve spegnere tutti i canali:
            # ricade sulle credenziali storiche e lascia il dettaglio ai log
            # del singolo scanner.
            creds, err = original_shared_loader()
            if creds is not None:
                return creds, None
            return None, f"credenziale Drive canonica non valida: {exc}; fallback: {err}"

    # Fatture usa un loader dedicato.
    _drive_invoice._load_credentials_fatture = canonical_loader

    # Cedolini e Quietanze hanno loader dedicati propri.
    from . import drive_cedolini_ingest as _drive_cedolini
    from . import drive_quietanze_ingest as _drive_quietanze

    _drive_cedolini._load_credentials_cedolini = canonical_loader
    _drive_quietanze._load_credentials_quietanze = canonical_loader

    # F24 e ingest generico avevano importato il loader condiviso per valore:
    # sostituiamo solo il riferimento locale di questi moduli, senza cambiare
    # il loader condiviso usato dagli altri servizi.
    from . import drive_f24_ingest as _drive_f24
    from . import drive_documenti_ingest as _drive_documenti

    _drive_f24._load_credentials = canonical_loader
    _drive_documenti._load_credentials = canonical_loader


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
