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


async def _install_canonical_email_sender_guard() -> None:
    """Segnaposto async non usato: la guardia viene installata sotto in import."""


def _patch_email_monitor_sender_rules() -> None:
    """Rende atomica la whitelist anche nel servizio email legacy.

    ``email_monitor_service`` storicamente usa ``pattern in from_addr``. Finche'
    quel modulo non viene ridotto nel refactoring generale, centralizziamo qui
    il comportamento senza duplicare il parser: indirizzo esatto, PEC
    normalizzata, esclusioni e tipi ammessi per mittente.
    """
    try:
        from . import email_monitor_service as monitor
        from .canonical_email_senders import (
            canonical_sender_from_header,
            default_rule_for_sender,
            is_excluded_sender,
            normalize_document_type,
            rule_allows_document_type,
            sender_matches_rule,
        )
    except Exception:
        return

    original_resolver = monitor._risolvi_tipo_documento_email

    async def _canonical_check_mittente(db, from_addr: str, canale: str):
        if is_excluded_sender(from_addr):
            return None
        canonical = canonical_sender_from_header(from_addr)
        if not canonical:
            return None
        mittenti = await db["mittenti_email"].find(
            {"canale": canale, "attivo": True}, {"_id": 0}
        ).to_list(200)
        for mittente in mittenti:
            configured = str(mittente.get("pattern") or "").strip()
            if not sender_matches_rule(from_addr, configured):
                continue
            result = dict(mittente)
            result["canonical_address"] = canonical
            default_rule = default_rule_for_sender(from_addr)
            if default_rule:
                result["allowed_types"] = sorted(default_rule.allowed_types)
                result["canonical_label"] = default_rule.label
            return result
        return None

    def _canonical_resolver(doc, mittente):
        tipo = original_resolver(doc, mittente)
        if not tipo:
            return None
        normalized = normalize_document_type(tipo)
        allowed = {
            normalize_document_type(item)
            for item in (mittente.get("allowed_types") or [])
            if str(item or "").strip()
        }
        if allowed:
            return tipo if normalized in allowed else None
        default_rule = default_rule_for_sender(
            mittente.get("canonical_address") or mittente.get("pattern") or ""
        )
        if default_rule and not rule_allows_document_type(default_rule, normalized):
            return None
        return tipo

    monitor._check_mittente = _canonical_check_mittente
    monitor._risolvi_tipo_documento_email = _canonical_resolver


_patch_email_monitor_sender_rules()

# Ponte di compatibilita': i vecchi job Drive dello scheduler diventano sveglie
# della coda persistente, senza cambiare il contratto degli endpoint manuali.
try:
    from .document_ingestion_runtime import install_legacy_scheduler_bridge
    install_legacy_scheduler_bridge()
except Exception:
    # Fail closed sul bridge: il vecchio scheduler resta disponibile e il
    # fallimento emerge nei log/test invece di impedire l'avvio dell'intera app.
    pass


__all__ = [
    "AuthService",
    "InvoiceServiceV2",
    "get_invoice_service_v2",
    "WarehouseService",
    "AccountingService",
    "AccountingEntriesService",
    "CashService",
    "ChartOfAccountsService",
    "EmailService",
    "CorrispettiviService",
    "get_corrispettivi_service",
    "DataPropagationService",
    "get_propagation_service",
    "BusinessRules",
    "ValidationResult",
    "DataFlowManager"
]
