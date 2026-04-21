"""
Test suite FASE 2 (PayPal matching) + FASE 3 (Verbali ricerca pagamento) +
FASE 4 (Workflow bidirezionale Gmail scanner).

Testing esclusivamente l'API backend contro l'URL pubblico
REACT_APP_BACKEND_URL. Niente frontend.

Nota: i test sono "read-mostly" — non creano dati nuovi in DB, si limitano
a verificare gli endpoint contro dati reali già presenti (verbale
B25123609980, transazione PayPal 6TE49269X41363546) e a verificare la
non-regressione degli endpoint pre-esistenti.
"""
import os
import pytest
import requests
from typing import Any, Dict


def _get_base_url() -> str:
    # Cerco in più posti perché questo processo potrebbe non avere l'env var esportato
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        # Fallback: leggo il .env del frontend
        env_path = "/app/frontend/.env"
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
    if not url:
        pytest.fail("REACT_APP_BACKEND_URL non disponibile")
    return url.rstrip("/")


BASE_URL = _get_base_url()
VERBALE_TEST_ID = "B25123609980"
TX_PAYPAL_TEST_ID = "6TE49269X41363546"


@pytest.fixture(scope="session")
def api_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Regressione endpoint preesistenti ────────────────────────────────

class TestPaypalRegression:
    def test_paypal_status_ok(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/paypal-api/status", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("total_transazioni", "arricchite_da_api", "identificate_pagopa"):
            assert k in data, f"manca chiave {k} in {data}"
        assert isinstance(data["total_transazioni"], int)
        assert data["total_transazioni"] >= 0

    def test_paypal_sync_endpoint_accepts_body(self, api_client):
        """Non forzo il sync reale (può sforare timeout/API), ma verifico
        la validazione del body: data invalida → 400."""
        r = api_client.post(
            f"{BASE_URL}/api/paypal-api/sync",
            json={"start_date": "not-a-date", "end_date": "also-bad"},
            timeout=30,
        )
        assert r.status_code == 400, f"atteso 400 per date invalide, ottenuto {r.status_code}: {r.text}"


# ── FASE 2: /api/paypal-api/riconcilia ───────────────────────────────

class TestPaypalRiconcilia:
    def test_riconcilia_shape(self, api_client):
        body = {"start_date": "2025-09-01", "end_date": "2025-09-30"}
        r = api_client.post(
            f"{BASE_URL}/api/paypal-api/riconcilia", json=body, timeout=120
        )
        assert r.status_code == 200, r.text
        data: Dict[str, Any] = r.json()
        # La firma richiesta dal main agent: {multe_pagopa, fatture, banca}
        assert "multe_pagopa" in data, data
        assert "fatture" in data, data
        assert "banca" in data, data
        assert isinstance(data["multe_pagopa"], dict)
        assert isinstance(data["fatture"], dict)
        assert isinstance(data["banca"], dict)

    def test_riconcilia_empty_body_ok(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/paypal-api/riconcilia", json={}, timeout=120
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert {"multe_pagopa", "fatture", "banca"}.issubset(data.keys())


# ── FASE 2: /api/paypal-api/ricevuta-pdf/{tx_id} ─────────────────────

class TestPaypalRicevutaPdf:
    def test_ricevuta_pdf_404_per_tx_inesistente(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/paypal-api/ricevuta-pdf/NON_EXISTENT_TX",
            timeout=30,
        )
        assert r.status_code == 404, f"atteso 404, ottenuto {r.status_code}: {r.text[:200]}"

    def test_ricevuta_pdf_tx_reale(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/paypal-api/ricevuta-pdf/{TX_PAYPAL_TEST_ID}",
            timeout=60,
        )
        if r.status_code == 404:
            pytest.skip(
                f"Transazione {TX_PAYPAL_TEST_ID} non presente in DB o PDF non generabile"
            )
        assert r.status_code == 200, r.text[:500]
        ctype = r.headers.get("content-type", "")
        assert "application/pdf" in ctype, f"content-type atteso application/pdf, ottenuto {ctype}"
        # Primi byte di un PDF valido iniziano con %PDF-
        assert r.content[:4] == b"%PDF", f"header PDF non valido: {r.content[:20]!r}"
        assert len(r.content) > 500, f"PDF troppo piccolo: {len(r.content)} byte"


# ── FASE 3: /api/verbali-noleggio/{id}/cerca-pagamento ───────────────

class TestVerbaliCercaPagamento:
    def test_cerca_pagamento_verbale_reale(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/verbali-noleggio/{VERBALE_TEST_ID}/cerca-pagamento",
            timeout=120,
        )
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        assert "trovato" in data, data
        assert isinstance(data["trovato"], bool)
        if data["trovato"]:
            # Se è trovato, tutti i campi obbligatori
            for key in ("fonte", "psp", "importo", "data_pagamento",
                        "metodo_pagamento", "pdf_disponibile"):
                assert key in data, f"campo {key} mancante in risposta 'trovato=True': {data}"
            assert data["fonte"] in ("paypal", "gmail", "estratto_conto"), data["fonte"]

    def test_cerca_pagamento_verbale_inesistente(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/verbali-noleggio/FAKE_VERBALE_ID_XYZ/cerca-pagamento",
            timeout=30,
        )
        assert r.status_code == 404, r.text[:300]


# ── FASE 3: /api/verbali-noleggio/{id}/ricevuta-pdf ──────────────────

class TestVerbaliRicevutaPdf:
    def test_ricevuta_pdf_verbale_reale(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/verbali-noleggio/{VERBALE_TEST_ID}/ricevuta-pdf",
            timeout=60,
        )
        # Se PDF non ancora scaricato, 404 accettabile
        if r.status_code == 404:
            pytest.skip(
                "PDF ricevuta non ancora associato al verbale (serve prima /cerca-pagamento che scarichi Gmail)"
            )
        assert r.status_code == 200, r.text[:500]
        ctype = r.headers.get("content-type", "")
        assert "application/pdf" in ctype
        assert r.content[:4] == b"%PDF"

    def test_ricevuta_pdf_404_se_inesistente(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/verbali-noleggio/FAKE_VERBALE_XYZ/ricevuta-pdf",
            timeout=30,
        )
        assert r.status_code == 404


# ── FASE 4: /api/verbali-noleggio/scan-gmail ─────────────────────────

class TestVerbaliScanGmail:
    def test_scan_gmail_7_giorni(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/verbali-noleggio/scan-gmail?days_back=7",
            timeout=120,
        )
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        # Chiavi tipiche di uno scanner: email_analizzate/nuovi_verbali/etc.
        # Verifico almeno che sia dict non vuoto
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_scan_gmail_30_giorni(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/verbali-noleggio/scan-gmail?days_back=30",
            timeout=180,
        )
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        assert isinstance(data, dict)


# ── FASE 4: /api/verbali-noleggio/riconcilia-completo ────────────────

class TestVerbaliRiconciliaCompleto:
    def test_riconcilia_completo_pipeline(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/verbali-noleggio/riconcilia-completo",
            timeout=300,
        )
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        # La pipeline torna struct con 3 step (scan+link+ricerca)
        assert isinstance(data, dict)
        # check che il dict contenga almeno qualcosa di rappresentativo
        assert len(data) > 0, f"risposta pipeline vuota: {data}"


# ── FASE 4: /api/alert-verbali/... ───────────────────────────────────

class TestAlertVerbali:
    def test_contatore_alert(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/alert-verbali/contatore", timeout=30
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "scadenza_imminente_5gg" in data, data
        assert "in_attesa_notifica" in data, data
        assert isinstance(data["scadenza_imminente_5gg"], int)
        assert isinstance(data["in_attesa_notifica"], int)
        assert data["scadenza_imminente_5gg"] >= 0
        assert data["in_attesa_notifica"] >= 0

    def test_scadenza_imminente_default(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/alert-verbali/scadenza-imminente", timeout=30
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        for item in data:
            # Verifico struttura di ogni item
            for k in ("numero_verbale", "targa", "data_scadenza",
                      "giorni_mancanti", "urgenza"):
                assert k in item, f"manca {k} in {item}"
            assert item["urgenza"] in ("critica", "alta", "media"), item["urgenza"]
            assert isinstance(item["giorni_mancanti"], int)

    def test_scadenza_imminente_giorni_custom(self, api_client):
        r = api_client.get(
            f"{BASE_URL}/api/alert-verbali/scadenza-imminente?giorni_soglia=30",
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)

        # con soglia 30 il numero di risultati deve essere >= rispetto a soglia 5
        r5 = api_client.get(
            f"{BASE_URL}/api/alert-verbali/scadenza-imminente?giorni_soglia=5",
            timeout=30,
        ).json()
        assert len(data) >= len(r5), (
            f"soglia 30 ({len(data)}) dovrebbe contenere almeno i risultati di soglia 5 ({len(r5)})"
        )
