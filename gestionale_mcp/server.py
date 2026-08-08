"""Production-oriented MCP tool surface for all GestionaleCloud domains."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Mapping

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.types import ToolAnnotations

from .audit import audit_span
from .auth import GestionaleTokenVerifier
from .catalog import ACTION_OPERATIONS, READ_BY_ID, READ_OPERATIONS
from .client import APIContractError, APIRequestError, GestionaleAPIClient
from .config import MCPConfig
from .proposals import ProposalError, ProposalStore
from .schemas import Capability, ToolResult


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
PROPOSAL_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
CONFIRMED_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=False,
)


INSTRUCTIONS = """
Usa questo server come livello semantico del GestionaleCloud. Non inferire mai un
pagamento dal solo importo. Documento, fattura, movimento bancario, assegno,
cedolino, F24, quietanza, liquidazione IVA e transazione POS sono entità distinte.
Mantieni fonte e collegamenti bidirezionali. Un caso ambiguo resta non confermato.
I movimenti bancari sono prove immutabili. Un F24 può contenere più tributi e deve
essere valutato riga per riga. XML RT, Numia, SumUp, PayPal e accrediti bancari sono
fonti indipendenti: un payout non è un nuovo ricavo. Le azioni mutative richiedono
sempre proposta, conferma umana, ruolo admin, MFA e abilitazione esplicita server.
""".strip()


def _tool_error(operation_id: str, trace_id: str, exc: Exception) -> ToolResult:
    if isinstance(exc, (APIContractError, ProposalError, ValueError)):
        message = str(exc)
    elif isinstance(exc, APIRequestError):
        message = str(exc)
    else:
        message = "Errore interno MCP; consultare l'audit tramite trace_id"
    return ToolResult(
        ok=False,
        operation_id=operation_id,
        error=message,
        trace_id=trace_id,
    )


def _current_access_token(config: MCPConfig) -> str | None:
    """Return the request token when a MCP auth context exists, else stdio token.

    ``get_access_token`` raises outside an authenticated HTTP request.  Stdio is
    an intentional supported transport, so the absence of a request context is
    not itself an error and must fall back to the explicitly configured API
    token.
    """
    try:
        access = get_access_token()
    except (LookupError, RuntimeError):
        access = None
    return access.token if access else config.api_token


def _list_from_payload(data: Any) -> list[Any] | None:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in (
            "items",
            "results",
            "data",
            "fatture",
            "movimenti",
            "documenti",
            "transactions",
            "transazioni",
            "records",
        ):
            if isinstance(data.get(key), list):
                return data[key]
    return None


def _success(operation_id: str, trace_id: str, data: Any, query: Mapping[str, Any]) -> ToolResult:
    items = _list_from_payload(data)
    count: int | None = len(items) if items is not None else None
    total: int | None = None
    if isinstance(data, dict):
        for key in ("total", "count", "totale"):
            if isinstance(data.get(key), int):
                total = data[key]
                break
    if total is not None:
        count = total
    has_more: bool | None = None
    next_cursor: str | None = None
    if items is not None and "limit" in query:
        limit = int(query.get("limit") or len(items) or 1)
        offset = int(query.get("skip") or query.get("offset") or 0)
        if total is not None:
            has_more = offset + len(items) < total
        else:
            has_more = len(items) >= limit
        if has_more:
            next_cursor = str(offset + len(items))
    return ToolResult(
        ok=True,
        operation_id=operation_id,
        data=data,
        count=count,
        has_more=has_more,
        next_cursor=next_cursor,
        trace_id=trace_id,
    )


async def _invoke(
    *,
    tool: str,
    operation_id: str,
    query: Mapping[str, Any],
    call: Callable[[], Awaitable[Any]],
) -> ToolResult:
    parameter_names = list(query.keys())
    async with audit_span(tool, operation_id, parameter_names) as span:
        try:
            data = await call()
            return _success(operation_id, span.trace_id, data, query)
        except Exception as exc:  # converted into a stable, secret-free tool result
            span.fail()
            return _tool_error(operation_id, span.trace_id, exc)


def create_server(
    config: MCPConfig | None = None,
    *,
    authenticated_http: bool = False,
    api_client: GestionaleAPIClient | None = None,
) -> MCPServer:
    """Build a server. HTTP mode delegates bearer verification to the ERP."""
    cfg = config or MCPConfig.from_env()
    client = api_client or GestionaleAPIClient(cfg)
    proposals = ProposalStore(cfg.proposal_ttl_seconds)
    kwargs: dict[str, Any] = {}
    if authenticated_http:
        cfg.require_http_security()
        kwargs["token_verifier"] = GestionaleTokenVerifier(client)
        kwargs["auth"] = AuthSettings(
            issuer_url=cfg.issuer_url,
            resource_server_url=cfg.resource_server_url,
            required_scopes=["gestionale:read"],
            service_documentation_url=cfg.resource_server_url,
        )
    server = MCPServer(
        "gestionale_cloud_mcp",
        title="GestionaleCloud MCP",
        description="Gateway tipizzato e auditabile per tutte le aree del GestionaleCloud",
        instructions=INSTRUCTIONS,
        version="1.0.0",
        log_level=cfg.log_level,
        **kwargs,
    )

    async def read_curated(
        operation_id: str,
        *,
        path_parameters: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
        tool: str,
    ) -> ToolResult:
        spec = READ_BY_ID[operation_id]
        clean_query = {key: value for key, value in (query or {}).items() if value is not None}
        return await _invoke(
            tool=tool,
            operation_id=operation_id,
            query=clean_query,
            call=lambda: client.read_path(
                spec.path,
                path_parameters=path_parameters,
                query=clean_query,
            ),
        )

    @server.tool(
        name="gestionale_status",
        description="Verifica autenticazione, raggiungibilità API e versione del contratto OpenAPI.",
        annotations=READ_ONLY,
    )
    async def gestionale_status() -> ToolResult:
        async with audit_span("gestionale_status", "auth_verify", []) as span:
            try:
                raw = _current_access_token(cfg)
                if not raw:
                    raise APIRequestError("Configurare GESTIONALE_MCP_API_TOKEN per il trasporto stdio")
                identity, operations = await asyncio.gather(
                    client.verify_token(raw),
                    client.list_read_operations(),
                )
                user = identity.get("user") or {}
                return ToolResult(
                    ok=True,
                    operation_id="auth_verify",
                    data={
                        "api_base_url": cfg.api_base_url,
                        "authenticated": True,
                        "role": user.get("role"),
                        "mfa_enabled": user.get("mfa_enabled"),
                        "mfa_verified": user.get("mfa_verified"),
                        "read_operations": len(operations),
                        "writes_enabled": cfg.allow_writes,
                    },
                    trace_id=span.trace_id,
                )
            except Exception as exc:
                span.fail()
                return _tool_error("auth_verify", span.trace_id, exc)

    @server.tool(
        name="gestionale_list_capabilities",
        description="Elenca strumenti curati e operazioni GET OpenAPI disponibili, filtrabili per area o testo.",
        annotations=READ_ONLY,
    )
    async def gestionale_list_capabilities(
        domain: str | None = None,
        search: str | None = None,
        include_openapi: bool = True,
        limit: int = 100,
        refresh: bool = False,
    ) -> ToolResult:
        clean_domain = (domain or "").strip().lower()
        clean_search = (search or "").strip().lower()
        bounded_limit = max(1, min(limit, cfg.max_items))

        async def load() -> dict[str, Any]:
            curated: list[dict[str, Any]] = []
            for spec in READ_OPERATIONS:
                if clean_domain and spec.domain != clean_domain:
                    continue
                haystack = f"{spec.operation_id} {spec.description} {spec.path}".lower()
                if clean_search and clean_search not in haystack:
                    continue
                operation = await client.get_read_operation_by_path(spec.path)
                curated.append(
                    Capability(
                        operation_id=spec.operation_id,
                        domain=spec.domain,
                        description=spec.description,
                        method="GET",
                        read_only=True,
                        path_parameters=list(operation.path_parameters),
                        query_parameters=list(operation.query_parameters),
                    ).model_dump()
                )
            dynamic: list[dict[str, Any]] = []
            if include_openapi:
                for operation in await client.list_read_operations(force_refresh=refresh):
                    tags = [tag.lower() for tag in operation.tags]
                    if clean_domain and not any(clean_domain in tag for tag in tags):
                        continue
                    haystack = f"{operation.operation_id} {operation.path} {operation.summary} {' '.join(tags)}".lower()
                    if clean_search and clean_search not in haystack:
                        continue
                    dynamic.append(
                        Capability(
                            operation_id=operation.operation_id,
                            domain=operation.tags[0] if operation.tags else "api",
                            description=operation.summary or operation.path,
                            method="GET",
                            read_only=True,
                            path_parameters=list(operation.path_parameters),
                            query_parameters=list(operation.query_parameters),
                        ).model_dump()
                    )
                    if len(dynamic) >= bounded_limit:
                        break
            actions = [
                Capability(
                    operation_id=item.action_id,
                    domain=item.domain,
                    description=item.description,
                    method=item.method,  # type: ignore[arg-type]
                    read_only=False,
                    requires_confirmation=True,
                ).model_dump()
                for item in ACTION_OPERATIONS
                if (not clean_domain or item.domain == clean_domain)
                and (not clean_search or clean_search in f"{item.action_id} {item.description}".lower())
            ]
            return {
                "curated": curated[:bounded_limit],
                "openapi": dynamic,
                "confirmed_actions": actions[:bounded_limit],
                "writes_enabled": cfg.allow_writes,
            }

        return await _invoke(
            tool="gestionale_list_capabilities",
            operation_id="capabilities",
            query={"domain": clean_domain, "search": clean_search, "limit": bounded_limit},
            call=load,
        )

    @server.tool(
        name="gestionale_read_api",
        description=(
            "Esegue una sola operazione GET documentata dall'OpenAPI del Gestionale. "
            "Rifiuta URL arbitrari, download, PDF, XML originali, export e parametri non dichiarati."
        ),
        annotations=READ_ONLY,
    )
    async def gestionale_read_api(
        operation_id: str,
        path_parameters: dict[str, str] | None = None,
        query_parameters: dict[str, Any] | None = None,
    ) -> ToolResult:
        query = query_parameters or {}
        return await _invoke(
            tool="gestionale_read_api",
            operation_id=operation_id,
            query=query,
            call=lambda: client.read_operation(
                operation_id,
                path_parameters=path_parameters or {},
                query=query,
            ),
        )

    @server.tool(name="gestionale_search_documents", description="Cerca documenti per anno, categoria, stato e testo conservando provenienza e hash.", annotations=READ_ONLY)
    async def gestionale_search_documents(
        anno: int | None = None,
        categoria: str | None = None,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        skip: int = 0,
    ) -> ToolResult:
        return await read_curated("documents_list", query=locals(), tool="gestionale_search_documents")

    @server.tool(name="gestionale_search_invoices", description="Cerca tutte le fatture ricevute per periodo, fornitore, stato o numero.", annotations=READ_ONLY)
    async def gestionale_search_invoices(
        anno: int | None = None,
        mese: int | None = None,
        fornitore_piva: str | None = None,
        fornitore_nome: str | None = None,
        stato: str | None = None,
        search: str | None = None,
        limit: int = 100,
        skip: int = 0,
    ) -> ToolResult:
        return await read_curated("invoices_received", query=locals(), tool="gestionale_search_invoices")

    @server.tool(name="gestionale_get_invoice_context", description="Restituisce dettaglio, storia e prove di pagamento di una fattura senza trasferire i file binari.", annotations=READ_ONLY)
    async def gestionale_get_invoice_context(fattura_id: str) -> ToolResult:
        async def load() -> dict[str, Any]:
            detail, history, documents = await asyncio.gather(
                client.read_path(READ_BY_ID["invoice_detail"].path, path_parameters={"fattura_id": fattura_id}),
                client.read_path(READ_BY_ID["invoice_history"].path, path_parameters={"fattura_id": fattura_id}),
                client.read_path(READ_BY_ID["invoice_payment_documents"].path, path_parameters={"fattura_id": fattura_id}),
            )
            return {"invoice": detail, "history": history, "payment_documents": documents}
        return await _invoke(tool="gestionale_get_invoice_context", operation_id="invoice_context", query={}, call=load)

    @server.tool(name="gestionale_list_bank_movements", description="Legge i movimenti dell'estratto conto, prova finanziaria immutabile, con filtri e paginazione.", annotations=READ_ONLY)
    async def gestionale_list_bank_movements(
        anno: int | None = None,
        mese: int | None = None,
        categoria: str | None = None,
        fornitore: str | None = None,
        tipo: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> ToolResult:
        return await read_curated("bank_statement_movements", query=locals(), tool="gestionale_list_bank_movements")

    @server.tool(name="gestionale_get_prima_nota", description="Legge Cassa, Banca o Provvisori senza creare scritture duplicate.", annotations=READ_ONLY)
    async def gestionale_get_prima_nota(
        sezione: str,
        anno: int,
        data_da: str | None = None,
        data_a: str | None = None,
        tipo: str | None = None,
        categoria: str | None = None,
        limit: int = 100,
        skip: int = 0,
    ) -> ToolResult:
        normalized = sezione.strip().lower()
        if normalized not in {"cassa", "banca", "provvisori"}:
            return ToolResult(ok=False, operation_id="prima_nota", error="sezione deve essere cassa, banca o provvisori", trace_id="validation")
        operation_id = {"cassa": "prima_nota_cash", "banca": "prima_nota_bank", "provvisori": "prima_nota_pending"}[normalized]
        query = {"anno": anno}
        if normalized != "provvisori":
            query.update({"data_da": data_da, "data_a": data_a, "tipo": tipo, "categoria": categoria, "limit": limit, "skip": skip})
        return await read_curated(operation_id, query=query, tool="gestionale_get_prima_nota")

    @server.tool(name="gestionale_get_checks", description="Legge assegni o proposte di associazione mantenendo separati stato, incasso, fornitore e fatture.", annotations=READ_ONLY)
    async def gestionale_get_checks(
        view: str = "assegni",
        anno: int | None = None,
        stato: str | None = None,
        search: str | None = None,
        fornitore_piva: str | None = None,
        limit: int = 100,
        skip: int = 0,
    ) -> ToolResult:
        normalized = view.strip().lower()
        operation_id = "checks_candidates" if normalized == "proposte" else "checks_list"
        query = {} if operation_id == "checks_candidates" else {"anno": anno, "stato": stato, "search": search, "fornitore_piva": fornitore_piva, "limit": limit, "skip": skip}
        return await read_curated(operation_id, query=query, tool="gestionale_get_checks")

    @server.tool(name="gestionale_get_payment_channel", description="Legge la quadratura di PayPal, SumUp o POS senza trattare payout/accrediti come ricavi.", annotations=READ_ONLY)
    async def gestionale_get_payment_channel(
        canale: str,
        anno: int,
        mese: int | None = None,
        limit: int = 200,
    ) -> ToolResult:
        normalized = canale.strip().lower()
        mapping = {"paypal": "paypal_transactions", "sumup": "sumup_summary", "pos": "pos_coherence"}
        if normalized not in mapping:
            return ToolResult(ok=False, operation_id="payment_channel", error="canale deve essere paypal, sumup o pos", trace_id="validation")
        operation_id = mapping[normalized]
        query = {"anno": anno, "mese": mese}
        if normalized == "paypal":
            query["limit"] = limit
        return await read_curated(operation_id, query=query, tool="gestionale_get_payment_channel")

    @server.tool(name="gestionale_get_payroll", description="Legge Prima Nota salari per dipendente, mese e anno con cedolino e bonifico separati.", annotations=READ_ONLY)
    async def gestionale_get_payroll(
        anno: int,
        mese: int | None = None,
        dipendente: str | None = None,
    ) -> ToolResult:
        return await read_curated("payroll_ledger", query=locals(), tool="gestionale_get_payroll")

    @server.tool(name="gestionale_get_f24_status", description="Legge un F24 o la dashboard; ogni codice tributo resta una riga distinta con quietanza e prova bancaria.", annotations=READ_ONLY)
    async def gestionale_get_f24_status(
        f24_id: str | None = None,
        anno: int | None = None,
        limit: int = 200,
        skip: int = 0,
    ) -> ToolResult:
        if f24_id:
            return await read_curated("f24_detail", path_parameters={"f24_id": f24_id}, tool="gestionale_get_f24_status")
        if anno is not None:
            return await read_curated("f24_reconciliation", query={"anno": anno}, tool="gestionale_get_f24_status")
        return await read_curated("f24_list", query={"limit": limit, "skip": skip}, tool="gestionale_get_f24_status")

    @server.tool(name="gestionale_get_vat_period", description="Legge liquidazione e anomalie IVA mensili; non usa una seconda logica trimestrale.", annotations=READ_ONLY)
    async def gestionale_get_vat_period(
        anno: int,
        mese: int | None = None,
        include_anomalies: bool = True,
    ) -> ToolResult:
        async def load() -> dict[str, Any]:
            if mese is None:
                vat = await client.read_path(READ_BY_ID["vat_year"].path, path_parameters={"anno": anno})
            else:
                if not 1 <= mese <= 12:
                    raise ValueError("mese deve essere compreso tra 1 e 12")
                vat = await client.read_path(READ_BY_ID["vat_period"].path, path_parameters={"periodo": f"{anno}-{mese:02d}"})
            anomalies = None
            if include_anomalies:
                anomalies = await client.read_path(
                    READ_BY_ID["vat_anomalies"].path,
                    query={"anno": anno},
                )
            return {"vat": vat, "anomalies": anomalies}
        return await _invoke(tool="gestionale_get_vat_period", operation_id="vat_context", query={"anno": anno, "mese": mese}, call=load)

    @server.tool(name="gestionale_get_accounting_report", description="Legge piano dei conti, bilancio o audit di coerenza per anno.", annotations=READ_ONLY)
    async def gestionale_get_accounting_report(report: str, anno: int) -> ToolResult:
        normalized = report.strip().lower()
        mapping = {"piano_conti": "chart_of_accounts", "bilancio": "financial_statement", "audit": "coherence_audit", "discrepanze": "coherence_discrepancies"}
        if normalized not in mapping:
            return ToolResult(ok=False, operation_id="accounting_report", error="report deve essere piano_conti, bilancio, audit o discrepanze", trace_id="validation")
        operation_id = mapping[normalized]
        path_parameters = {"anno": anno} if "{anno}" in READ_BY_ID[operation_id].path else None
        query = {} if path_parameters else {"anno": anno}
        return await read_curated(operation_id, path_parameters=path_parameters, query=query, tool="gestionale_get_accounting_report")

    @server.tool(name="gestionale_get_operational_context", description="Legge scadenze, PagoPA, noleggi, verbali o cespiti con i collegamenti esistenti.", annotations=READ_ONLY)
    async def gestionale_get_operational_context(
        area: str,
        anno: int | None = None,
        mese: int | None = None,
        stato: str | None = None,
        limit: int = 100,
    ) -> ToolResult:
        normalized = area.strip().lower()
        mapping = {"scadenze": "deadlines", "pagopa": "pagopa_receipts", "noleggio": "rentals_vehicles", "verbali": "fines_list", "cespiti": "assets_summary", "bonifici": "bank_transfers"}
        if normalized not in mapping:
            return ToolResult(ok=False, operation_id="operational_context", error="area non supportata", trace_id="validation")
        operation_id = mapping[normalized]
        if normalized == "scadenze":
            query = {"anno": anno, "mese": mese, "limit": limit}
        elif normalized == "pagopa":
            query = {"anno": anno, "limit": limit}
        elif normalized == "verbali":
            query = {"stato": stato}
        elif normalized == "bonifici":
            query = {"year": str(anno) if anno else None, "limit": limit}
        elif normalized == "noleggio":
            query = {"anno": anno}
        else:  # cespiti/riepilogo has no query parameters in the live contract
            query = {}
        return await read_curated(operation_id, query=query, tool="gestionale_get_operational_context")

    @server.tool(name="gestionale_prepare_action", description="Prepara una modifica allowlistata senza eseguirla e restituisce la frase di conferma.", annotations=PROPOSAL_ONLY)
    async def gestionale_prepare_action(
        action_id: str,
        reason: str,
        path_parameters: dict[str, Any] | None = None,
        query_parameters: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> ToolResult:
        async with audit_span("gestionale_prepare_action", action_id, ["reason", "path_parameters", "query_parameters", "body"]) as span:
            try:
                proposal = proposals.prepare(
                    action_id=action_id,
                    path_parameters=path_parameters or {},
                    query=query_parameters or {},
                    body=body or {},
                    reason=reason,
                )
                return ToolResult(ok=True, operation_id=action_id, data=proposal.model_dump(), trace_id=span.trace_id)
            except Exception as exc:
                span.fail()
                return _tool_error(action_id, span.trace_id, exc)

    @server.tool(name="gestionale_execute_confirmed_action", description="Esegue una proposta non scaduta solo con scritture abilitate, admin, MFA e frase esatta.", annotations=CONFIRMED_WRITE)
    async def gestionale_execute_confirmed_action(
        proposal_id: str,
        confirmation_phrase: str,
    ) -> ToolResult:
        async with audit_span("gestionale_execute_confirmed_action", proposal_id, ["proposal_id", "confirmation_phrase"]) as span:
            try:
                if not cfg.allow_writes:
                    raise ProposalError("Scritture MCP disabilitate: GESTIONALE_MCP_ALLOW_WRITES=false")
                raw_token = _current_access_token(cfg)
                if not raw_token:
                    raise ProposalError("Token GestionaleCloud richiesto")
                identity = await client.verify_token(raw_token)
                user = identity.get("user") or {}
                if user.get("role") != "admin":
                    raise ProposalError("Ruolo admin richiesto")
                if not user.get("mfa_enabled") or not user.get("mfa_verified"):
                    raise ProposalError("MFA attiva e verificata richiesta")
                proposal = proposals.consume(proposal_id, confirmation_phrase)
                data = await client.call_action(
                    method=proposal.action.method,
                    path_template=proposal.action.path,
                    path_parameters=proposal.path_parameters,
                    query=proposal.query,
                    body=proposal.body,
                )
                return ToolResult(ok=True, operation_id=proposal.action.action_id, data=data, trace_id=span.trace_id)
            except Exception as exc:
                span.fail()
                return _tool_error(proposal_id, span.trace_id, exc)

    return server
