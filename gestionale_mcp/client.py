"""Safe HTTP facade over the existing GestionaleCloud API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import re
import time
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx

from .config import MCPConfig


_PATH_PARAM = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "access_token",
    "refresh_token",
    "authorization",
    "api_key",
    "base64",
    "file_content",
    "raw_pdf",
    "xml_originale",
)
_BINARY_PATH_PARTS = (
    "/download",
    "/export",
    "/pdf",
    "xml-originale",
    "template-csv",
)


class APIContractError(ValueError):
    """Invalid or unsafe operation requested by an MCP caller."""


class APIRequestError(RuntimeError):
    """Backend request failed without exposing credentials or stack traces."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class OpenAPIOperation:
    operation_id: str
    method: str
    path: str
    tags: tuple[str, ...]
    summary: str
    path_parameters: tuple[str, ...]
    query_parameters: tuple[str, ...]
    query_schemas: Mapping[str, Mapping[str, Any]]
    binary: bool


def _token_from_context() -> str | None:
    try:
        from mcp.server.auth.middleware.auth_context import get_access_token

        access_token = get_access_token()
        return access_token.token if access_token else None
    except (ImportError, LookupError, RuntimeError):
        return None


def sanitize_payload(value: Any, *, max_items: int, depth: int = 0) -> Any:
    """Remove secrets/binary blobs and bound recursive output size."""
    if depth > 12:
        return "[profondità massima raggiunta]"
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
                clean[key_text] = "[omesso]"
            else:
                clean[key_text] = sanitize_payload(item, max_items=max_items, depth=depth + 1)
        return clean
    if isinstance(value, list):
        limited = value[:max_items]
        result = [sanitize_payload(item, max_items=max_items, depth=depth + 1) for item in limited]
        if len(value) > max_items:
            result.append({"_truncated": len(value) - max_items})
        return result
    if isinstance(value, str) and len(value) > 20_000:
        return value[:20_000] + "…[troncato]"
    return value


class GestionaleAPIClient:
    """Discovers and invokes only documented GestionaleCloud operations."""

    def __init__(
        self,
        config: MCPConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport
        self._operations: dict[str, OpenAPIOperation] = {}
        self._openapi_loaded_at = 0.0
        self._openapi_lock = asyncio.Lock()

    def _headers(self, token: str | None = None) -> dict[str, str]:
        effective_token = token or _token_from_context() or self.config.api_token
        headers = {
            "Accept": "application/json",
            "User-Agent": "gestionale-cloud-mcp/1.0",
        }
        if effective_token:
            headers["Authorization"] = f"Bearer {effective_token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        token: str | None = None,
    ) -> Any:
        self._validate_api_path(path, allow_openapi=path == "/openapi.json")
        timeout = httpx.Timeout(self.config.timeout_seconds)
        async with httpx.AsyncClient(
            base_url=self.config.api_base_url,
            headers=self._headers(token),
            timeout=timeout,
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            try:
                response = await client.request(method, path, params=query, json=body)
            except httpx.TimeoutException as exc:
                raise APIRequestError("Timeout delle API GestionaleCloud") from exc
            except httpx.RequestError as exc:
                raise APIRequestError("API GestionaleCloud non raggiungibili") from exc

        if response.is_redirect:
            raise APIRequestError("Redirect API rifiutato per sicurezza", status_code=response.status_code)
        if response.status_code >= 400:
            detail = ""
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    detail = str(payload.get("detail") or payload.get("message") or "")
            except ValueError:
                detail = ""
            messages = {
                401: "Token GestionaleCloud assente, scaduto o revocato",
                403: "Ruolo non autorizzato per questa operazione",
                404: "Endpoint non disponibile: possibile deriva tra MCP e backend",
                422: "Parametri non validi per l'endpoint GestionaleCloud",
                429: "Limite richieste GestionaleCloud raggiunto",
            }
            message = messages.get(response.status_code, "Errore restituito dalle API GestionaleCloud")
            if detail:
                message = f"{message}: {detail[:300]}"
            raise APIRequestError(message, status_code=response.status_code)

        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > self.config.max_response_bytes:
            raise APIRequestError("Risposta troppo grande: restringere filtri e paginazione")
        content_type = response.headers.get("content-type", "").lower()
        if "json" not in content_type:
            raise APIRequestError("Il tool MCP non trasferisce file o contenuti binari")
        if len(response.content) > self.config.max_response_bytes:
            raise APIRequestError("Risposta troppo grande: restringere filtri e paginazione")
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise APIRequestError("Risposta API non JSON") from exc
        return sanitize_payload(data, max_items=self.config.max_items)

    @staticmethod
    def _validate_api_path(path: str, *, allow_openapi: bool = False) -> None:
        if allow_openapi and path == "/openapi.json":
            return
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise APIContractError("Sono consentiti soltanto percorsi API relativi")
        if not path.startswith("/api/") or ".." in path or "\\" in path:
            raise APIContractError("Percorso API non consentito")

    async def verify_token(self, token: str) -> dict[str, Any]:
        data = await self._request("GET", "/api/auth/verify", token=token)
        if not isinstance(data, dict) or not data.get("ok"):
            raise APIRequestError("Token GestionaleCloud non verificato", status_code=401)
        return data

    async def _load_openapi(self, *, force: bool = False) -> None:
        if self._operations and not force and time.monotonic() - self._openapi_loaded_at < 300:
            return
        async with self._openapi_lock:
            if self._operations and not force and time.monotonic() - self._openapi_loaded_at < 300:
                return
            schema = await self._request("GET", "/openapi.json")
            operations: dict[str, OpenAPIOperation] = {}
            for path, path_item in (schema.get("paths") or {}).items():
                if not isinstance(path_item, dict):
                    continue
                for method, raw in path_item.items():
                    if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                        continue
                    if not isinstance(raw, dict) or not raw.get("operationId"):
                        continue
                    parameters = raw.get("parameters") or []
                    path_parameters = tuple(
                        item["name"] for item in parameters if item.get("in") == "path"
                    )
                    query_parameters = tuple(
                        item["name"] for item in parameters if item.get("in") == "query"
                    )
                    query_schemas = {
                        item["name"]: item.get("schema") or {}
                        for item in parameters
                        if item.get("in") == "query"
                    }
                    summary = str(raw.get("summary") or "")
                    binary = any(part in path.lower() for part in _BINARY_PATH_PARTS) or any(
                        word in summary.lower() for word in ("download", "export", " pdf", "xml originale")
                    )
                    operation = OpenAPIOperation(
                        operation_id=raw["operationId"],
                        method=method.upper(),
                        path=path,
                        tags=tuple(raw.get("tags") or ()),
                        summary=summary,
                        path_parameters=path_parameters,
                        query_parameters=query_parameters,
                        query_schemas=query_schemas,
                        binary=binary,
                    )
                    operations[operation.operation_id] = operation
            self._operations = operations
            self._openapi_loaded_at = time.monotonic()

    async def list_read_operations(self, *, force_refresh: bool = False) -> list[OpenAPIOperation]:
        await self._load_openapi(force=force_refresh)
        return sorted(
            (
                operation
                for operation in self._operations.values()
                if operation.method == "GET"
                and operation.path.startswith("/api/")
                and not operation.binary
            ),
            key=lambda item: (item.tags, item.path),
        )

    async def get_operation(self, operation_id: str) -> OpenAPIOperation:
        await self._load_openapi()
        operation = self._operations.get(operation_id)
        if operation is None:
            raise APIContractError(f"Operazione OpenAPI sconosciuta: {operation_id}")
        return operation

    async def get_read_operation_by_path(self, path: str) -> OpenAPIOperation:
        await self._load_openapi()
        candidates = [
            operation
            for operation in self._operations.values()
            if operation.method == "GET" and operation.path == path
        ]
        if len(candidates) != 1:
            raise APIContractError(
                f"Contratto GET non univoco o assente per {path}: trovati {len(candidates)} endpoint"
            )
        operation = candidates[0]
        if operation.binary:
            raise APIContractError("Download ed export binari non sono esposti dal gateway")
        return operation

    @staticmethod
    def _render_path(template: str, path_parameters: Mapping[str, Any]) -> str:
        required = set(_PATH_PARAM.findall(template))
        supplied = set(path_parameters)
        if required != supplied:
            missing = sorted(required - supplied)
            extra = sorted(supplied - required)
            raise APIContractError(f"Parametri path non validi; mancanti={missing}, extra={extra}")
        path = template
        for name in required:
            value = str(path_parameters[name]).strip()
            if not value or len(value) > 200 or value in {".", ".."} or "/" in value or "\\" in value:
                raise APIContractError(f"Valore non valido per {name}")
            path = path.replace("{" + name + "}", value)
        return path

    def _validate_query(
        self, operation: OpenAPIOperation, query: Mapping[str, Any]
    ) -> dict[str, Any]:
        extra = set(query) - set(operation.query_parameters)
        if extra:
            raise APIContractError(f"Parametri query non previsti: {sorted(extra)}")
        clean = {key: value for key, value in query.items() if value is not None and value != ""}
        for pagination_key in ("limit",):
            if pagination_key in clean:
                try:
                    requested = int(clean[pagination_key])
                except (TypeError, ValueError) as exc:
                    raise APIContractError("limit deve essere un intero") from exc
                schema = operation.query_schemas.get(pagination_key, {})
                endpoint_max = int(schema.get("maximum") or self.config.max_items)
                clean[pagination_key] = max(1, min(requested, endpoint_max, self.config.max_items))
        return clean

    async def read_operation(
        self,
        operation_id: str,
        *,
        path_parameters: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> Any:
        operation = await self.get_operation(operation_id)
        if operation.method != "GET":
            raise APIContractError("Il tool generico consente soltanto operazioni GET")
        if operation.binary:
            raise APIContractError("Download ed export binari non sono esposti dal tool generico")
        path = self._render_path(operation.path, path_parameters or {})
        clean_query = self._validate_query(operation, query or {})
        return await self._request("GET", path, query=clean_query)

    async def read_path(
        self,
        path_template: str,
        *,
        path_parameters: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> Any:
        operation = await self.get_read_operation_by_path(path_template)
        path = self._render_path(operation.path, path_parameters or {})
        clean_query = self._validate_query(operation, query or {})
        return await self._request("GET", path, query=clean_query)

    async def call_action(
        self,
        *,
        method: str,
        path_template: str,
        path_parameters: Mapping[str, Any],
        query: Mapping[str, Any],
        body: Mapping[str, Any],
    ) -> Any:
        if method not in {"POST", "PUT", "PATCH"}:
            raise APIContractError("Metodo di modifica non consentito")
        path = self._render_path(path_template, path_parameters)
        return await self._request(method, path, query=query, body=body)
