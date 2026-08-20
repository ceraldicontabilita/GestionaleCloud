"""
Test middleware autenticazione JWT.

Verifica:
- Path pubblici accessibili senza token
- Path protetti richiedono token valido
- Validazione token JWT
- Gestione prefissi pubblici
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.middleware.authentication import PUBLIC_PATHS, PUBLIC_PREFIXES


class TestPublicPaths:
    """Verifica che i path pubblici siano configurati correttamente."""

    def test_health_checks_pubblici(self):
        """Health check devono essere pubblici."""
        assert "/" in PUBLIC_PATHS
        assert "/health" in PUBLIC_PATHS
        assert "/api/health" in PUBLIC_PATHS
        assert "/api/ping" in PUBLIC_PATHS

    def test_login_pubblico(self):
        """Endpoint login deve essere pubblico."""
        assert "/api/auth/login" in PUBLIC_PATHS

    def test_pin_login_pubblico(self):
        """Endpoint PIN login (login reale usato dal frontend) deve essere
        pubblico — regressione trovata da review Codex su PR #65: senza
        questo path esplicito nessuno può più autenticarsi."""
        assert "/api/auth/pin-login" in PUBLIC_PATHS
        assert "/api/auth/mfa/verify-login" in PUBLIC_PATHS

    def test_diagnostica_e_setup_non_pubblici(self):
        """Diagnostica PIN e vecchio setup non devono bypassare il login."""
        assert "/api/auth/pin-login/health" not in PUBLIC_PATHS
        assert "/api/auth/setup" not in PUBLIC_PATHS

    def test_docs_pubblici(self):
        """OpenAPI docs devono essere pubblici."""
        assert "/docs" in PUBLIC_PATHS
        assert "/redoc" in PUBLIC_PATHS
        assert "/openapi.json" in PUBLIC_PATHS

    def test_register_non_pubblico(self):
        """Register non deve essere nei path pubblici (richiede admin)."""
        assert "/api/auth/register" not in PUBLIC_PATHS


class TestPublicPrefixes:
    """Verifica prefissi pubblici."""

    def test_auth_paths_espliciti(self):
        """I 3 endpoint auth reali (login/logout/verify) sono pubblici come
        path espliciti, non più come prefisso (audit sicurezza 19/07/2026:
        il prefisso "/api/auth/" rendeva pubblico anche qualunque endpoint
        futuro montato lì sotto)."""
        assert "/api/auth/login" in PUBLIC_PATHS
        assert "/api/auth/logout" in PUBLIC_PATHS
        assert "/api/auth/verify" in PUBLIC_PATHS
        assert "/api/auth/" not in PUBLIC_PREFIXES

    def test_nessun_prefisso_api_pubblico_generico(self):
        """Un futuro endpoint aziendale non deve diventare pubblico per prefisso."""
        assert "/api/public/" not in PUBLIC_PREFIXES

    def test_f24_public_prefix_ora_protetto(self):
        """F24-public NON deve più essere pubblico: esponeva lettura/scrittura
        di F24 reali senza auth (bug #24 memoria/endpoints/README.md, fix lug 2026).
        L'unico chiamante (Dashboard.jsx) usa già il client autenticato."""
        assert "/api/f24-public/" not in PUBLIC_PREFIXES

    def test_exports_non_pubblici(self):
        """Gli export NON devono essere pubblici (contengono dati sensibili)."""
        assert "/api/exports/" not in PUBLIC_PREFIXES

    def test_employees_non_pubblici(self):
        """Endpoint dipendenti non devono essere pubblici."""
        assert "/api/employees/" not in PUBLIC_PREFIXES
        assert "/api/dipendenti/" not in PUBLIC_PREFIXES

    def test_invoices_non_pubblici(self):
        """Endpoint fatture non devono essere pubblici."""
        assert "/api/invoices/" not in PUBLIC_PREFIXES

    def test_accounting_non_pubblico(self):
        """Contabilità non deve essere pubblica."""
        assert "/api/accounting/" not in PUBLIC_PREFIXES
        assert "/api/bilancio/" not in PUBLIC_PREFIXES

    def test_bank_non_pubblico(self):
        """Banca non deve essere pubblica."""
        assert "/api/bank/" not in PUBLIC_PREFIXES


class TestAllowlistCongelata:
    """§12: fotografia ESATTA dell'allowlist del middleware.

    Se questi test falliscono, qualcuno ha aggiunto (o tolto) un path
    pubblico: la modifica va fatta DELIBERATAMENTE aggiornando anche
    questa fotografia e memoria/ENDPOINT_CLASSIFICAZIONE_FINALE.md.
    Ogni path qui dentro è raggiungibile da internet SENZA login.
    """

    ALLOWLIST_PATHS_ATTESA = {
        # Health check
        "/", "/health", "/api/health", "/api/ping",
        # Autenticazione necessaria prima di una sessione valida
        "/api/auth/login", "/api/auth/logout", "/api/auth/verify",
        "/api/auth/pin-login", "/api/auth/mfa/verify-login",
        # Integrazioni esterne con auth propria (ERP bridge, non WhatsApp legacy)
        "/api/erp/ponte/fattura-ricevuta",
        # Pagine legali
        "/api/privacy", "/api/terms", "/api/data-deletion",
        # OpenAPI docs
        "/docs", "/redoc", "/openapi.json",
        # SEO/crawler
        "/robots.txt", "/sitemap.xml", "/favicon.ico",
    }

    ALLOWLIST_PREFISSI_ATTESA = ["/docs", "/redoc"]

    def test_public_paths_esattamente_quelli_attesi(self):
        assert PUBLIC_PATHS == self.ALLOWLIST_PATHS_ATTESA, (
            f"Allowlist path pubblici cambiata!\n"
            f"Aggiunti: {PUBLIC_PATHS - self.ALLOWLIST_PATHS_ATTESA}\n"
            f"Rimossi: {self.ALLOWLIST_PATHS_ATTESA - PUBLIC_PATHS}"
        )

    def test_public_prefixes_esattamente_quelli_attesi(self):
        assert sorted(PUBLIC_PREFIXES) == sorted(self.ALLOWLIST_PREFISSI_ATTESA), (
            f"Prefissi pubblici cambiati: {PUBLIC_PREFIXES}"
        )

    def test_middleware_montato_in_app(self):
        """Il middleware deve essere davvero montato: senza, l'allowlist è carta."""
        import app.main as main_mod
        from app.middleware.authentication import AuthenticationMiddleware
        stack = [m.cls for m in main_mod.app.user_middleware]
        assert AuthenticationMiddleware in stack, (
            "AuthenticationMiddleware NON è montato su app: tutte le route sarebbero pubbliche"
        )

    def test_nessun_prefisso_pubblico_su_dati_reali(self):
        """Nessun prefisso pubblico deve coprire router con dati aziendali."""
        prefissi_vietati = {
            "/api/f24", "/api/invoices", "/api/fatture", "/api/employees",
            "/api/dipendenti", "/api/cash", "/api/bank", "/api/assegni",
            "/api/warehouse", "/api/suppliers", "/api/prima-nota",
            "/api/accounting", "/api/bilancio", "/api/exports", "/api/v1",
        }
        for prefix in PUBLIC_PREFIXES:
            for vietato in prefissi_vietati:
                assert not vietato.startswith(prefix.rstrip("/")) or prefix == "/api/auth/", (
                    f"Il prefisso pubblico {prefix} copre {vietato} (dati reali)"
                )


class TestPathMatching:
    """Test matching dei path con la logica del middleware."""

    def _is_public(self, path: str) -> bool:
        """Simula la logica del middleware per verificare se un path è pubblico."""
        if path in PUBLIC_PATHS:
            return True
        for prefix in PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return True
        if not path.startswith("/api/"):
            return False
        return False

    def test_api_health_pubblico(self):
        assert self._is_public("/api/health") is True

    def test_api_login_pubblico(self):
        assert self._is_public("/api/auth/login") is True

    def test_whatsapp_non_pubblico(self):
        assert self._is_public("/api/whatsapp/webhook") is False

    def test_whatsapp_non_montato_nella_route_table(self):
        from fastapi import FastAPI
        from app.router_registry import register_all_routers

        app = FastAPI()
        register_all_routers(app)
        assert all(
            "whatsapp" not in str(getattr(route, "path", "")).lower()
            for route in app.routes
        )

    def test_futuri_dati_aziendali_non_pubblici_per_prefisso(self):
        assert self._is_public("/api/public/dati-azienda") is False

    def test_diagnostica_pin_richiede_sessione(self):
        assert self._is_public("/api/auth/pin-login/health") is False

    def test_api_invoices_protetto(self):
        assert self._is_public("/api/invoices") is False

    def test_api_employees_protetto(self):
        assert self._is_public("/api/employees/list") is False

    def test_api_bilancio_protetto(self):
        assert self._is_public("/api/bilancio/conto-economico") is False

    def test_static_files_passano(self):
        """File statici (non /api/) passano senza auth."""
        assert self._is_public("/static/app.js") is False  # non è API, non è public
        # Il middleware lascia passare i non-API paths

    def test_f24_public_prefix_ora_protetto(self):
        assert self._is_public("/api/f24-public/models") is False

    def test_f24_protetto(self):
        """F24 normali (non pubblici) sono protetti."""
        assert self._is_public("/api/f24/models") is False


class TestErrorHandlerDecorator:
    """Test dell'error handler decorator."""

    def test_handle_errors_importabile(self):
        """Verifica che handle_errors sia importabile."""
        from app.utils.error_handler import handle_errors
        assert callable(handle_errors)

    def test_api_response_success(self):
        """Verifica APIResponse.success."""
        from app.utils.error_handler import APIResponse
        result = APIResponse.success(data={"key": "value"}, message="OK")
        assert result["success"] is True
        assert result["data"] == {"key": "value"}
        assert result["message"] == "OK"

    def test_api_response_error(self):
        """Verifica APIResponse.error."""
        from app.utils.error_handler import APIResponse
        result = APIResponse.error(message="Errore", code="ERR001")
        assert result["success"] is False
        assert result["error"] == "Errore"
        assert result["error_code"] == "ERR001"

    def test_api_response_paginated(self):
        """Verifica APIResponse.paginated."""
        from app.utils.error_handler import APIResponse
        result = APIResponse.paginated(items=[1, 2, 3], total=10, page=1, per_page=3)
        assert result["success"] is True
        assert len(result["data"]) == 3
        assert result["pagination"]["total"] == 10
        assert result["pagination"]["total_pages"] == 4


class TestCustomExceptions:
    """Test custom exceptions."""

    def test_app_error(self):
        from app.exceptions import AppError
        err = AppError("test error", status_code=400)
        assert err.message == "test error"
        assert err.status_code == 400

    def test_validation_error(self):
        from app.exceptions import ValidationError
        err = ValidationError("campo non valido")
        assert err.status_code == 400

    def test_not_found_error(self):
        from app.exceptions import NotFoundError
        err = NotFoundError("Dipendente", "dip-001")
        assert err.status_code == 404
        assert "Dipendente" in err.message

    def test_duplicate_error(self):
        from app.exceptions import DuplicateError
        err = DuplicateError("Fattura", "invoice_number", "FT-001")
        assert err.status_code == 409

    def test_business_logic_error(self):
        from app.exceptions import BusinessLogicError
        err = BusinessLogicError("TFR non sufficiente")
        assert err.status_code == 422
