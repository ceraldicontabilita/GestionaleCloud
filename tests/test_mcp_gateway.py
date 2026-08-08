"""MCP gateway tests use synthetic HTTP responses only: never MongoDB or production."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path

import httpx
import pytest

# Il backend FastAPI e il gateway MCP hanno ambienti runtime separati. La CI
# dedicata MCP installa l'SDK e deve eseguire questo file; la suite backend può
# raccoglierlo senza forzare dipendenze ASGI incompatibili.
pytest.importorskip("mcp", reason="SDK MCP verificato dalla pipeline mcp-ci dedicata")

from gestionale_mcp.auth import GestionaleTokenVerifier
from gestionale_mcp.catalog import ACTION_BY_ID, READ_BY_ID
from gestionale_mcp.client import (
    APIContractError,
    APIRequestError,
    GestionaleAPIClient,
    sanitize_payload,
)
from gestionale_mcp.config import ConfigurationError, MCPConfig, _validate_base_url
from gestionale_mcp.proposals import ProposalError, ProposalStore
from gestionale_mcp.server import _current_access_token, create_server


def config(**overrides) -> MCPConfig:
    base = MCPConfig(
        api_base_url="http://127.0.0.1:8000",
        api_token="synthetic-test-token",
        timeout_seconds=5,
        max_response_bytes=100_000,
        max_items=50,
        allow_writes=False,
        proposal_ttl_seconds=900,
        host="127.0.0.1",
        port=8765,
        allowed_hosts=("127.0.0.1:*",),
        allowed_origins=("http://127.0.0.1:*",),
        issuer_url=None,
        resource_server_url=None,
        log_level="ERROR",
    )
    return replace(base, **overrides)


def openapi_schema() -> dict:
    return {
        "openapi": "3.1.0",
        "paths": {
            "/api/items/{item_id}": {
                "get": {
                    "operationId": "get_item",
                    "summary": "Get item",
                    "tags": ["Test"],
                    "parameters": [
                        {"name": "item_id", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer", "maximum": 20}},
                    ],
                },
                "post": {"operationId": "write_item", "summary": "Write item", "tags": ["Test"]},
            },
            "/api/items/export-pdf": {
                "get": {"operationId": "export_items", "summary": "Export Pdf", "tags": ["Test"]}
            },
        },
    }


def test_remote_plain_http_is_rejected() -> None:
    with pytest.raises(ConfigurationError):
        _validate_base_url("http://example.com", allow_insecure_remote=False)
    assert _validate_base_url("https://example.com/", allow_insecure_remote=False) == "https://example.com"


def test_http_transport_requires_auth_metadata() -> None:
    with pytest.raises(ConfigurationError):
        config().require_http_security()


def test_stdio_token_falls_back_when_no_http_auth_context(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_request_context():
        raise LookupError("no MCP request context")

    monkeypatch.setattr("gestionale_mcp.server.get_access_token", no_request_context)
    assert _current_access_token(config()) == "synthetic-test-token"


def test_sanitizer_removes_secrets_and_bounds_lists() -> None:
    payload = {
        "access_token": "secret",
        "pdf_base64": "AAAA",
        "safe": [{"password": "hidden", "value": index} for index in range(4)],
    }
    clean = sanitize_payload(payload, max_items=2)
    assert clean["access_token"] == "[omesso]"
    assert clean["pdf_base64"] == "[omesso]"
    assert clean["safe"][0]["password"] == "[omesso]"
    assert clean["safe"][-1] == {"_truncated": 2}


def test_openapi_read_is_allowlisted_and_limit_is_clamped() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json=openapi_schema())
        return httpx.Response(200, json={"items": [{"id": "A"}], "access_token": "never-return"})

    client = GestionaleAPIClient(config(), transport=httpx.MockTransport(handler))
    result = asyncio.run(
        client.read_operation("get_item", path_parameters={"item_id": "A"}, query={"limit": 999})
    )
    assert result["access_token"] == "[omesso]"
    assert seen[-1].url.params["limit"] == "20"
    assert seen[-1].headers["authorization"] == "Bearer synthetic-test-token"


def test_openapi_blocks_write_binary_and_unknown_query() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=openapi_schema())

    client = GestionaleAPIClient(config(), transport=httpx.MockTransport(handler))
    with pytest.raises(APIContractError):
        asyncio.run(client.read_operation("write_item"))
    with pytest.raises(APIContractError):
        asyncio.run(client.read_operation("export_items"))
    with pytest.raises(APIContractError):
        asyncio.run(
            client.read_operation(
                "get_item",
                path_parameters={"item_id": "A"},
                query={"authorization": "injected"},
            )
        )


def test_path_injection_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=openapi_schema())

    client = GestionaleAPIClient(config(), transport=httpx.MockTransport(handler))
    with pytest.raises(APIContractError):
        asyncio.run(client.read_operation("get_item", path_parameters={"item_id": "../../admin"}))


def test_redirect_and_non_json_are_rejected() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(302, headers={"location": "https://evil.example"})
        return httpx.Response(200, content=b"PDF", headers={"content-type": "application/pdf"})

    client = GestionaleAPIClient(config(), transport=httpx.MockTransport(handler))
    with pytest.raises(APIRequestError):
        asyncio.run(client._request("GET", "/api/test"))
    with pytest.raises(APIRequestError):
        asyncio.run(client._request("GET", "/api/test"))


def test_proposals_are_allowlisted_confirmed_and_single_use() -> None:
    store = ProposalStore(900)
    prepared = store.prepare(
        action_id="prima_nota_mark_uncertain",
        path_parameters={},
        query={},
        body={"fattura_id": "synthetic-id"},
        reason="Pagamento ambiguo: richiede verifica umana.",
    )
    with pytest.raises(ProposalError):
        store.consume(prepared.proposal_id, "CONFERMO altro")
    stored = store.consume(prepared.proposal_id, prepared.confirmation_phrase)
    assert stored.body == {"fattura_id": "synthetic-id"}
    with pytest.raises(ProposalError):
        store.consume(prepared.proposal_id, prepared.confirmation_phrase)
    with pytest.raises(ProposalError):
        store.prepare(action_id="delete_everything", path_parameters={}, query={}, body={}, reason="Motivo sintetico valido")


def test_token_verifier_reuses_erp_role_and_mfa() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/auth/verify"
        assert request.headers["authorization"] == "Bearer erp-jwt"
        return httpx.Response(
            200,
            json={
                "ok": True,
                "user": {
                    "email": "admin@example.invalid",
                    "role": "admin",
                    "mfa_enabled": True,
                    "mfa_verified": True,
                },
            },
        )

    client = GestionaleAPIClient(config(api_token=None), transport=httpx.MockTransport(handler))
    token = asyncio.run(GestionaleTokenVerifier(client).verify_token("erp-jwt"))
    assert token is not None
    assert "gestionale:write" in token.scopes
    assert token.claims["mfa_verified"] is True


def test_server_exposes_complete_guarded_surface() -> None:
    server = create_server(config())
    tools = {tool.name: tool for tool in server._tool_manager.list_tools()}
    assert len(tools) == 17
    assert "gestionale_read_api" in tools
    assert "gestionale_get_invoice_context" in tools
    assert "gestionale_get_f24_status" in tools
    assert "gestionale_get_payment_channel" in tools
    assert tools["gestionale_execute_confirmed_action"].annotations.destructive_hint is True
    assert tools["gestionale_read_api"].annotations.read_only_hint is True


def test_catalog_covers_all_requested_accounting_domains() -> None:
    required = {
        "documenti",
        "fatture",
        "fornitori",
        "banca",
        "bonifici",
        "prima_nota",
        "assegni",
        "paypal",
        "pos",
        "paghe",
        "f24",
        "iva",
        "scadenze",
        "contabilita",
        "audit",
        "pagopa",
        "noleggio",
        "verbali",
        "cespiti",
    }
    assert required <= {item.domain for item in READ_BY_ID.values()}
    assert {"prima_nota_mark_uncertain", "f24_reconcile", "invoice_reconcile_bank"} <= set(ACTION_BY_ID)


def test_read_only_evaluation_set_has_ten_cases_without_real_data() -> None:
    path = Path("gestionale_mcp/evals/read_only_evals.json")
    cases = json.loads(path.read_text(encoding="utf-8"))
    assert len(cases) >= 10
    assert all(case["read_only"] is True for case in cases)
    assert all("expected_tool" in case and "criteria" in case for case in cases)
