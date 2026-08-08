"""Environment-only configuration for the GestionaleCloud MCP gateway."""

from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import urlsplit


class ConfigurationError(ValueError):
    """Raised when a security-sensitive MCP setting is invalid."""


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} deve essere un intero") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} deve essere compreso tra {minimum} e {maximum}")
    return value


def _env_csv(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = os.getenv(name)
    if not raw:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _validate_base_url(value: str, *, allow_insecure_remote: bool) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigurationError("GESTIONALE_MCP_API_BASE_URL deve essere un URL HTTP(S) assoluto")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError("L'URL API non può contenere credenziali, query o frammenti")
    is_local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not is_local and not allow_insecure_remote:
        raise ConfigurationError(
            "Le API remote devono usare HTTPS; per un ambiente isolato impostare "
            "GESTIONALE_MCP_ALLOW_INSECURE_REMOTE=true"
        )
    return value.rstrip("/")


@dataclass(frozen=True, slots=True)
class MCPConfig:
    api_base_url: str
    api_token: str | None
    timeout_seconds: int
    max_response_bytes: int
    max_items: int
    allow_writes: bool
    proposal_ttl_seconds: int
    host: str
    port: int
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]
    issuer_url: str | None
    resource_server_url: str | None
    log_level: str

    @classmethod
    def from_env(cls) -> "MCPConfig":
        allow_insecure = _env_bool("GESTIONALE_MCP_ALLOW_INSECURE_REMOTE")
        base_url = _validate_base_url(
            os.getenv("GESTIONALE_MCP_API_BASE_URL", "http://127.0.0.1:8000"),
            allow_insecure_remote=allow_insecure,
        )
        host = os.getenv("GESTIONALE_MCP_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port = _env_int("GESTIONALE_MCP_PORT", 8765, 1, 65535)
        default_hosts = (f"{host}:{port}", "127.0.0.1:*", "localhost:*")
        default_origins = (f"http://{host}:{port}", "http://127.0.0.1:*", "http://localhost:*")
        level = os.getenv("GESTIONALE_MCP_LOG_LEVEL", "INFO").upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigurationError("GESTIONALE_MCP_LOG_LEVEL non valido")
        return cls(
            api_base_url=base_url,
            api_token=(os.getenv("GESTIONALE_MCP_API_TOKEN") or "").strip() or None,
            timeout_seconds=_env_int("GESTIONALE_MCP_TIMEOUT_SECONDS", 30, 2, 120),
            max_response_bytes=_env_int(
                "GESTIONALE_MCP_MAX_RESPONSE_BYTES", 2_000_000, 16_384, 10_000_000
            ),
            max_items=_env_int("GESTIONALE_MCP_MAX_ITEMS", 500, 1, 2_000),
            allow_writes=_env_bool("GESTIONALE_MCP_ALLOW_WRITES"),
            proposal_ttl_seconds=_env_int("GESTIONALE_MCP_PROPOSAL_TTL", 900, 60, 3_600),
            host=host,
            port=port,
            allowed_hosts=_env_csv("GESTIONALE_MCP_ALLOWED_HOSTS", default_hosts),
            allowed_origins=_env_csv("GESTIONALE_MCP_ALLOWED_ORIGINS", default_origins),
            issuer_url=(os.getenv("GESTIONALE_MCP_ISSUER_URL") or "").strip() or None,
            resource_server_url=(os.getenv("GESTIONALE_MCP_RESOURCE_SERVER_URL") or "").strip()
            or None,
            log_level=level,
        )

    def require_http_security(self) -> None:
        """Fail closed before exposing the gateway over HTTP."""
        if not self.issuer_url or not self.resource_server_url:
            raise ConfigurationError(
                "Il trasporto HTTP richiede GESTIONALE_MCP_ISSUER_URL e "
                "GESTIONALE_MCP_RESOURCE_SERVER_URL"
            )
        if not self.allowed_hosts:
            raise ConfigurationError("Il trasporto HTTP richiede almeno un host consentito")
