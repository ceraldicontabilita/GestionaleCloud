import httpx
from fastapi.testclient import TestClient

from enable_banking_probe import main


class FakeEnableBankingClient:
    calls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if url.endswith("/aspsps"):
            return httpx.Response(
                200,
                json={"aspsps": [{"name": "Banco BPM - Corporate", "country": "IT"}]},
            )
        if url.endswith("/balances"):
            return httpx.Response(200, json={"balances": []})
        if url.endswith("/transactions"):
            return httpx.Response(200, json={"transactions": [{
                "entry_reference": "safe",
                "status": "BOOK",
                "booking_date": "2026-09-01",
                "credit_debit_indicator": "DBIT",
                "transaction_amount": {"currency": "EUR", "amount": "12.50"},
                "remittance_information": ["PAGAMENTO POS"],
            }]})
        return httpx.Response(200, json={})

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url.endswith("/auth"):
            return httpx.Response(200, json={"url": "https://auth.enablebanking.com/start"})
        if url.endswith("/sessions"):
            return httpx.Response(
                200,
                json={
                    "session_id": "memory-session",
                    "accounts": [{"uid": "memory-account", "account_id": {"iban": "IT60X0542811101000000123456"}}],
                    "access": {"valid_until": "2026-12-22T10:00:00+00:00"},
                },
            )
        return httpx.Response(400, json={})


def _reset_state():
    main._pending_states.clear()
    main._session_id = None
    main._account_uids = []
    main._accounts_meta = {}
    main._consent_valid_until = None
    main._viewer_token = None
    main._letture.clear()
    main._confronto = None
    main._last_result = {
        "connected": False,
        "session": {},
        "accounts": {},
        "balances": {},
        "transactions": {},
        "ready": False,
    }
    FakeEnableBankingClient.calls.clear()


def test_health_is_explicitly_isolated():
    _reset_state()
    with TestClient(main.app, base_url="https://testserver") as client:
        health = client.get("/health").json()
    assert health["supabase_connected"] is False
    assert health["session_present_in_memory"] is False


def test_registration_pages_are_available_without_configuration():
    _reset_state()
    with TestClient(main.app, base_url="https://testserver") as client:
        privacy = client.get("/privacy")
        terms = client.get("/terms")
    assert privacy.status_code == 200
    assert "non utilizza Supabase" in privacy.text
    assert terms.status_code == 200
    assert "sola lettura" in terms.text


def test_connect_and_callback_keep_only_sanitized_results(monkeypatch):
    _reset_state()
    monkeypatch.setattr(main, "APPLICATION_ID", "application-id")
    monkeypatch.setattr(main, "PRIVATE_KEY_PEM", "private-key-never-returned")
    monkeypatch.setattr(main, "_api_headers", lambda: {"Authorization": "Bearer test"})
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeEnableBankingClient)

    with TestClient(main.app, base_url="https://testserver") as client:
        home = client.get("/")
        csrf = client.cookies.get("__Host-banco_bpm_probe_csrf")
        assert csrf
        connect = client.post(
            "/connect",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert connect.status_code == 303
        assert connect.headers["location"] == "https://auth.enablebanking.com/start"

        state = next(iter(main._pending_states))
        callback = client.get(
            f"/callback?code=one-time-code&state={state}",
            follow_redirects=False,
        )
        assert callback.status_code == 303
        result = client.get("/probe")
        assert result.json() == {
            "connected": True,
            "session": {"ok": True},
            "accounts": {"ok": True, "count": 1},
            "balances": {"ok": True, "count": 1},
            "transactions": {
                "ok": True,
                "accounts_checked": 1,
                "count": 1,
                "pages": 1,
                "period_days": 90,
                "errors": [],
            },
            "ready": True,
            "session_present_in_memory": True,
        }
        exposed = result.text + client.get("/health").text
        assert "private-key-never-returned" not in exposed
        assert "one-time-code" not in exposed
        assert "memory-session" not in exposed
        assert "memory-account" not in exposed
        assert "12.50" not in exposed and "IT60" not in exposed


def test_connect_rejects_invalid_csrf(monkeypatch):
    _reset_state()
    monkeypatch.setattr(main, "APPLICATION_ID", "application-id")
    monkeypatch.setattr(main, "PRIVATE_KEY_PEM", "private-key")
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeEnableBankingClient)

    with TestClient(main.app, base_url="https://testserver") as client:
        response = client.post("/connect", data={"csrf_token": "invalid"})
    assert response.status_code == 400
    assert not FakeEnableBankingClient.calls


def test_csrf_validation_does_not_depend_on_process_memory():
    token = main._new_csrf()

    assert main._consume_csrf(token, token) is True
    assert main._consume_csrf(token, token) is True
    assert main._consume_csrf(token, "different") is False


# ── Lettura completa, normalizzazione e confronto col CSV ──────────────────

import asyncio
from decimal import Decimal

from enable_banking_probe import lettura


def _tx(ref, giorno, importo, segno="DBIT", testo="BONIFICO", stato="BOOK"):
    return {
        "entry_reference": ref,
        "status": stato,
        "booking_date": giorno,
        "value_date": giorno,
        "credit_debit_indicator": segno,
        "transaction_amount": {"currency": "EUR", "amount": importo},
        "remittance_information": [testo],
    }


class PaginatedClient:
    def __init__(self, risposte):
        self.risposte = list(risposte)
        self.params = []

    async def get(self, url, headers=None, params=None):
        self.params.append(dict(params or {}))
        return self.risposte.pop(0)


async def _nessuna_attesa(_secondi):
    return None


def _leggi(client):
    return asyncio.run(lettura.leggi_transazioni(
        client, "https://api/accounts/x/transactions",
        headers=lambda: {}, date_from="2026-06-01", attendi=_nessuna_attesa,
    ))


def test_lettura_segue_tutte_le_pagine_e_tiene_solo_i_contabilizzati():
    client = PaginatedClient([
        httpx.Response(200, json={"transactions": [_tx("a", "2026-06-02", "1.00")], "continuation_key": "k1"}),
        httpx.Response(200, json={"transactions": [_tx("b", "2026-06-03", "2.00", stato="PDNG")], "continuation_key": "k2"}),
        httpx.Response(200, json={"transactions": [_tx("c", "2026-06-04", "3.00")]}),
    ])
    letti = _leggi(client)
    assert letti["pagine"] == 3
    assert [t["entry_reference"] for t in letti["movimenti"]] == ["a", "c"]
    assert letti["altri_stati"] == {"PDNG": 1}
    assert "continuation_key" not in client.params[0]
    assert [p.get("continuation_key") for p in client.params[1:]] == ["k1", "k2"]


def test_cursore_che_si_ripete_ferma_la_lettura():
    pagina = httpx.Response(200, json={"transactions": [], "continuation_key": "uguale"})
    client = PaginatedClient([pagina, pagina, pagina])
    try:
        _leggi(client)
    except lettura.ErroreLettura as exc:
        assert exc.stato == "cursore_bloccato"
    else:
        raise AssertionError("un cursore ripetuto deve interrompere la lettura")


def test_errore_temporaneo_si_riprova_limite_e_consenso_no():
    client = PaginatedClient([
        httpx.Response(503, json={"error": "ASPSP_TIMEOUT"}),
        httpx.Response(200, json={"transactions": [_tx("a", "2026-06-02", "1.00")]}),
    ])
    assert len(_leggi(client)["movimenti"]) == 1

    for corpo, atteso in (
        ({"error": "ASPSP_RATE_LIMIT_EXCEEDED"}, "limite_banca"),
        ({"error": "EXPIRED_SESSION"}, "consenso_scaduto"),
    ):
        client = PaginatedClient([httpx.Response(429 if atteso == "limite_banca" else 401, json=corpo)])
        try:
            _leggi(client)
        except lettura.ErroreLettura as exc:
            assert exc.stato == atteso
            assert client.risposte == []  # una sola chiamata: nessun nuovo tentativo
        else:
            raise AssertionError(atteso)


def test_normalizzazione_usa_decimal_segno_e_impronta():
    mov = lettura.normalizza_api(_tx("r1", "2026-06-02", "1234.5"), "IT60****3456", "2026-09-23T10:00:00+00:00")
    assert mov["importo"] == Decimal("-1234.50")
    assert mov["tipo"] == "uscita"
    assert mov["entry_reference"] == "r1"
    assert len(mov["hash_fonte"]) == 64
    assert lettura.normalizza_api({"status": "BOOK"}, "x", "t") is None
    assert lettura.maschera_iban("IT60 X054 2811 1010 0000 0123 456") == "IT60****3456"


CSV_BPM = (
    '"Ragione Sociale";"Data contabile";"Data valuta";"Banca";"Rapporto";"Importo";"Divisa";'
    '"Descrizione";"Categoria/sottocategoria";"Hashtag"\n'
    '"CERALDI GROUP S.R.L.";"02/06/2026";"02/06/2026";"05034 - BANCO BPM S.P.A.";"1 - 2 - 3";"-1147";"EUR";'
    '"BONIFICO FORNITORE";"Fornitori";""\n'
    '"CERALDI GROUP S.R.L.";"03/06/2026";"03/06/2026";"05034 - BANCO BPM S.P.A.";"1 - 2 - 3";"-50,25";"EUR";'
    '"COMMISSIONI - SPESE TENUTA CONTO";"Banca";""\n'
    '"CERALDI GROUP S.R.L.";"04/06/2026";"04/06/2026";"05034 - BANCO BPM S.P.A.";"1 - 2 - 3";"-80";"EUR";'
    '"PRELIEVO ASSEGNO - NUM: 0208770635";"Assegni";""\n'
    '"CERALDI GROUP S.R.L.";"05/06/2026";"05/06/2026";"05034 - BANCO BPM S.P.A.";"1 - 2 - 3";"-9,99";"EUR";'
    '"RIGA SOLO NEL CSV";"Banca";""\n'
    '"CERALDI GROUP S.R.L.";"data rotta";"";"";"";"xx";"EUR";"ILLEGGIBILE";"";""\n'
).encode("cp1252")


def test_lettore_csv_bpm_formato_reale():
    letto = lettura.leggi_csv_bpm(CSV_BPM)
    assert letto["illeggibili"] == 1
    importi = [m["importo"] for m in letto["movimenti"]]
    assert importi == [Decimal("-1147.00"), Decimal("-50.25"), Decimal("-80.00"), Decimal("-9.99")]
    try:
        lettura.leggi_csv_bpm(b"a;b\n1;2\n")
    except ValueError:
        pass
    else:
        raise AssertionError("un CSV di altro formato va rifiutato")


def test_confronto_nuovi_presenti_ambigui_e_solo_csv():
    csv_mov = lettura.leggi_csv_bpm(CSV_BPM)["movimenti"]
    api = [
        lettura.normalizza_api(t, "c", "t") for t in (
            _tx("1", "2026-06-02", "1147", testo="BONIFICO FORNITORE"),       # stessa descrizione
            _tx("2", "2026-06-03", "50.25", testo="ADDEBITO SPESE"),          # solo data e importo
            _tx("3", "2026-06-04", "80", testo="VOSTRO ASSEGNO N. 0208770635"),  # stesso assegno
            _tx("4", "2026-06-04", "999", testo="NUOVO MOVIMENTO"),           # solo API
            _tx("5", "2026-05-01", "10", testo="FUORI PERIODO"),              # prima del CSV
        )
    ]
    esito = lettura.confronta(api, csv_mov)
    assert esito["periodo_comune"] == ["2026-06-02", "2026-06-04"]
    assert [c["api"]["entry_reference"] for c in esito["gia_presenti"]] == ["1", "3"]
    assert [c["api"]["entry_reference"] for c in esito["ambigui"]] == ["2"]
    assert [m["entry_reference"] for m in esito["nuovi"]] == ["4"]
    assert esito["solo_nel_csv"] == []  # la riga del 05/06 e' fuori dal periodo dell'API
    assert esito["fuori_periodo_api"] == 1 and esito["fuori_periodo_csv"] == 1


def test_assegni_con_numeri_diversi_non_sono_lo_stesso_movimento():
    csv_mov = lettura.leggi_csv_bpm(CSV_BPM)["movimenti"]
    api = [lettura.normalizza_api(_tx("x", "2026-06-04", "80", testo="VOSTRO ASSEGNO N. 0208770999"), "c", "t")]
    esito = lettura.confronta(api, csv_mov)
    assert esito["gia_presenti"] == [] and esito["ambigui"] == []
    assert [m["entry_reference"] for m in esito["nuovi"]] == ["x"]


def test_dettagli_e_csv_solo_dal_browser_che_ha_collegato_il_conto(monkeypatch):
    _reset_state()
    monkeypatch.setattr(main, "APPLICATION_ID", "application-id")
    monkeypatch.setattr(main, "PRIVATE_KEY_PEM", "private-key")
    monkeypatch.setattr(main, "_api_headers", lambda: {"Authorization": "Bearer test"})
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeEnableBankingClient)

    with TestClient(main.app, base_url="https://testserver") as estraneo:
        assert estraneo.post("/retest", data={"giorni": "30"}).status_code == 403
        assert estraneo.post("/confronta-csv", files={"csv": ("e.csv", CSV_BPM)}).status_code == 403

    with TestClient(main.app, base_url="https://testserver") as client:
        client.get("/")
        csrf = client.cookies.get("__Host-banco_bpm_probe_csrf")
        client.post("/connect", data={"csrf_token": csrf}, follow_redirects=False)
        state = next(iter(main._pending_states))
        client.get(f"/callback?code=c&state={state}", follow_redirects=False)

        pagina = client.get("/result").text
        assert "IT60****3456" in pagina
        assert "22/12/2026" in pagina  # scadenza del consenso
        assert "12,50" in pagina

        upload = client.post("/confronta-csv", files={"csv": ("e.csv", CSV_BPM)}, follow_redirects=False)
        assert upload.status_code == 303
        assert main._confronto["csv_movimenti"] == 4
        assert "Confronto con il CSV" in client.get("/result").text

        assert client.post("/retest", data={"giorni": "30"}, follow_redirects=False).status_code == 303
        assert main._last_result["transactions"]["period_days"] == 30

    with TestClient(main.app, base_url="https://testserver") as estraneo:
        pagina = estraneo.get("/result").text
        assert "IT60****3456" not in pagina and "12,50" not in pagina
