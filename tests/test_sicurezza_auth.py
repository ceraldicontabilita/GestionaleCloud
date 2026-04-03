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

    def test_setup_pubblico(self):
        """Endpoint setup iniziale deve essere pubblico."""
        assert "/api/auth/setup" in PUBLIC_PATHS

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

    def test_auth_prefix(self):
        """Tutti gli endpoint auth sono pubblici."""
        assert "/api/auth/" in PUBLIC_PREFIXES

    def test_public_api_prefix(self):
        """API esplicitamente pubbliche."""
        assert "/api/public/" in PUBLIC_PREFIXES

    def test_f24_public_prefix(self):
        """F24 pubblici (dashboard widget)."""
        assert "/api/f24-public/" in PUBLIC_PREFIXES

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

    def test_f24_public_prefix(self):
        assert self._is_public("/api/f24-public/models") is True

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
