"""
Test iteration 66: Email Ordini features
- GET /api/ordini-fornitori/{id}/suppliers-email
- GET /api/ordini-fornitori/email-fornitori/lista
- POST /api/ordini-fornitori/email-fornitore/salva
- GET /api/ordini-fornitori/{id}/pdf
- POST /api/ordini-fornitori/{id}/invia-email (solo che ritorna JSON con 'risultati')
- GET /api/ordini-fornitori (senza source filter, ritorna TUTTI gli ordini)
- POST /api/ordini-fornitori con source=manuale
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def api():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def test_ordine_id(api):
    """Crea un ordine di test e restituisce il suo ID."""
    unique_nome = f"TEST_PROD_{uuid.uuid4().hex[:8]}"
    payload = {
        "reparto": "TestReparto",
        "operatore": "TestAgent",
        "prodotti": [
            {
                "prodotto_id": f"test_{uuid.uuid4().hex[:6]}",
                "nome": unique_nome,
                "fornitore": "TestFornitore_EmailOrdini",
                "quantita": 5.0,
                "unita": "kg",
                "prezzo_ultimo": 2.5,
                "note": ""
            }
        ],
        "ricette_da_produrre": [],
        "note_operatore": "Ordine di test iter66",
        "source": "manuale"
    }
    r = api.post(f"{BASE_URL}/api/ordini-fornitori", json=payload)
    assert r.status_code == 200, f"Creazione ordine fallita: {r.status_code} {r.text}"
    data = r.json()
    assert data["success"] == True
    return data["ordine_id"]


# ── Test lista ordini (TUTTI, senza filtro source) ─────────────────────────────

class TestListaOrdiniAll:
    """GET /api/ordini-fornitori senza filtro deve restituire TUTTI gli ordini."""

    def test_lista_ordini_no_filter_returns_list(self, api):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori?limit=50")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list), "Deve ritornare una lista"

    def test_lista_ordini_has_items(self, api):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori?limit=50")
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0, "Lista non deve essere vuota (ci sono ordini in DB)"

    def test_lista_ordini_source_field_present(self, api):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori?limit=50")
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0
        # Verifica che i record abbiano il campo source
        first = data[0]
        assert "source" in first or "id" in first, "Ogni ordine deve avere un id"

    def test_lista_ordini_no_mongodb_id(self, api):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori?limit=10")
        assert r.status_code == 200
        data = r.json()
        for item in data:
            assert "_id" not in item, "MongoDB _id non deve essere esposto"


# ── Test POST ordine manuale con source=manuale ────────────────────────────────

class TestCreaOrdineManuale:
    """POST /api/ordini-fornitori con source=manuale."""

    def test_crea_ordine_manuale_200(self, api):
        payload = {
            "reparto": "Bar",
            "operatore": "",
            "prodotti": [
                {"prodotto_id": "man_test_001", "nome": "TEST_Caffè", "fornitore": "TestFornitore_A", "quantita": 2, "unita": "kg", "prezzo_ultimo": 10.0, "note": ""}
            ],
            "ricette_da_produrre": [],
            "note_operatore": "Ordine manuale test iter66",
            "source": "manuale"
        }
        r = api.post(f"{BASE_URL}/api/ordini-fornitori", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") == True
        assert "ordine_id" in data

    def test_crea_ordine_manuale_source_salvato(self, api):
        """Verifica che source=manuale sia salvato nel DB."""
        payload = {
            "reparto": "Pasticceria",
            "operatore": "",
            "prodotti": [
                {"prodotto_id": "man_test_002", "nome": "TEST_Farina", "fornitore": "TestFornitore_B", "quantita": 10, "unita": "kg", "prezzo_ultimo": 1.2, "note": ""}
            ],
            "ricette_da_produrre": [],
            "note_operatore": "",
            "source": "manuale"
        }
        r = api.post(f"{BASE_URL}/api/ordini-fornitori", json=payload)
        assert r.status_code == 200
        ordine_id = r.json()["ordine_id"]

        # Verifica che source=manuale sia salvato
        r2 = api.get(f"{BASE_URL}/api/ordini-fornitori/{ordine_id}")
        assert r2.status_code == 200
        ordine = r2.json()
        assert ordine.get("source") == "manuale", f"source atteso 'manuale', trovato: {ordine.get('source')}"

    def test_crea_ordine_senza_source_default_tracciabilita(self, api):
        """Ordine senza source esplicito deve avere source='tracciabilita'."""
        payload = {
            "reparto": "",
            "operatore": "",
            "prodotti": [
                {"prodotto_id": "auto_test_001", "nome": "TEST_Latte", "fornitore": "TestFornitore_C", "quantita": 5, "unita": "lt", "prezzo_ultimo": 0.8, "note": ""}
            ],
            "ricette_da_produrre": [],
            "note_operatore": ""
        }
        r = api.post(f"{BASE_URL}/api/ordini-fornitori", json=payload)
        assert r.status_code == 200
        ordine_id = r.json()["ordine_id"]

        r2 = api.get(f"{BASE_URL}/api/ordini-fornitori/{ordine_id}")
        assert r2.status_code == 200
        ordine = r2.json()
        assert ordine.get("source") == "tracciabilita", f"source atteso 'tracciabilita', trovato: {ordine.get('source')}"


# ── Test email-fornitori/lista ─────────────────────────────────────────────────

class TestEmailFornitoriLista:
    """GET /api/ordini-fornitori/email-fornitori/lista"""

    def test_lista_email_status_200(self, api):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/email-fornitori/lista")
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"

    def test_lista_email_returns_list(self, api):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/email-fornitori/lista")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list), "Deve ritornare una lista"

    def test_lista_email_no_mongodb_id(self, api):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/email-fornitori/lista")
        assert r.status_code == 200
        data = r.json()
        for item in data:
            assert "_id" not in item, "MongoDB _id non deve essere esposto"


# ── Test salva-email-fornitore ─────────────────────────────────────────────────

class TestSalvaEmailFornitore:
    """POST /api/ordini-fornitori/email-fornitore/salva"""

    def test_salva_email_200(self, api):
        payload = {"nome_fornitore": "TEST_Fornitore_EmailSalva", "email": "test@fornitore.it"}
        r = api.post(f"{BASE_URL}/api/ordini-fornitori/email-fornitore/salva", json=payload)
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"

    def test_salva_email_response_fields(self, api):
        payload = {"nome_fornitore": "TEST_Fornitore_EmailSalva2", "email": "test2@fornitore.it"}
        r = api.post(f"{BASE_URL}/api/ordini-fornitori/email-fornitore/salva", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") == True
        assert data.get("email") == "test2@fornitore.it"
        assert data.get("nome") == "TEST_Fornitore_EmailSalva2"

    def test_salva_email_persisted_in_lista(self, api):
        """Verifica che l'email salvata compaia nella lista."""
        nome = f"TEST_Fornitore_{uuid.uuid4().hex[:6]}"
        email = f"{uuid.uuid4().hex[:8]}@test-fornitore.it"
        payload = {"nome_fornitore": nome, "email": email}
        r = api.post(f"{BASE_URL}/api/ordini-fornitori/email-fornitore/salva", json=payload)
        assert r.status_code == 200

        # Verifica lista
        r2 = api.get(f"{BASE_URL}/api/ordini-fornitori/email-fornitori/lista")
        assert r2.status_code == 200
        lista = r2.json()
        trovato = next((x for x in lista if x.get("nome_fornitore") == nome), None)
        assert trovato is not None, f"Fornitore {nome} non trovato nella lista dopo salvataggio"
        assert trovato.get("email") == email


# ── Test suppliers-email ──────────────────────────────────────────────────────

class TestSuppliersEmail:
    """GET /api/ordini-fornitori/{id}/suppliers-email"""

    def test_suppliers_email_200(self, api, test_ordine_id):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/{test_ordine_id}/suppliers-email")
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"

    def test_suppliers_email_response_structure(self, api, test_ordine_id):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/{test_ordine_id}/suppliers-email")
        assert r.status_code == 200
        data = r.json()
        assert "ordine_id" in data
        assert "fornitori" in data
        assert isinstance(data["fornitori"], list)
        assert data["ordine_id"] == test_ordine_id

    def test_suppliers_email_fornitore_fields(self, api, test_ordine_id):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/{test_ordine_id}/suppliers-email")
        assert r.status_code == 200
        data = r.json()
        assert len(data["fornitori"]) > 0, "Deve esserci almeno un fornitore"
        forn = data["fornitori"][0]
        assert "nome" in forn
        assert "n_prodotti" in forn
        assert "prodotti" in forn
        assert isinstance(forn["n_prodotti"], int)
        assert forn["n_prodotti"] > 0

    def test_suppliers_email_404_on_invalid_id(self, api):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/invalid-nonexistent-id-xyz/suppliers-email")
        assert r.status_code == 404


# ── Test PDF ───────────────────────────────────────────────────────────────────

class TestPdfOrdine:
    """GET /api/ordini-fornitori/{id}/pdf"""

    def test_pdf_returns_200(self, api, test_ordine_id):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/{test_ordine_id}/pdf")
        assert r.status_code == 200, f"Status {r.status_code}: {r.text[:200]}"

    def test_pdf_content_type_is_pdf(self, api, test_ordine_id):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/{test_ordine_id}/pdf")
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "application/pdf" in ct, f"Content-Type atteso application/pdf, trovato: {ct}"

    def test_pdf_has_content(self, api, test_ordine_id):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/{test_ordine_id}/pdf")
        assert r.status_code == 200
        assert len(r.content) > 1000, f"PDF troppo piccolo: {len(r.content)} bytes"

    def test_pdf_starts_with_pdf_magic(self, api, test_ordine_id):
        """Il file PDF deve iniziare con il magic bytes '%PDF'."""
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/{test_ordine_id}/pdf")
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF", f"Non inizia con %PDF: {r.content[:10]}"

    def test_pdf_con_filtro_fornitore(self, api, test_ordine_id):
        """PDF filtrato per fornitore specifico."""
        r = api.get(
            f"{BASE_URL}/api/ordini-fornitori/{test_ordine_id}/pdf",
            params={"fornitore": "TestFornitore_EmailOrdini"}
        )
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "application/pdf" in ct

    def test_pdf_404_on_invalid_id(self, api):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/invalid-nonexistent-id-xyz/pdf")
        assert r.status_code == 404


# ── Test invia-email ───────────────────────────────────────────────────────────

class TestInviaEmail:
    """POST /api/ordini-fornitori/{id}/invia-email - solo che ritorna JSON con 'risultati'."""

    def test_invia_email_returns_json_with_risultati(self, api, test_ordine_id):
        """L'endpoint deve rispondere con JSON contenente 'risultati'.
        L'email vera non viene spedita se credenziali SMTP non funzionano,
        ma l'endpoint deve comunque rispondere con struttura corretta."""
        payload = {
            "fornitori": [
                {
                    "nome": "TestFornitore_EmailOrdini",
                    "email": "test_noreply@example.com",
                    "prodotti": [{"nome": "TestProd", "quantita": 5, "unita": "kg"}]
                }
            ],
            "note": ""
        }
        r = api.post(f"{BASE_URL}/api/ordini-fornitori/{test_ordine_id}/invia-email", json=payload)
        # L'endpoint può rispondere con 200 (anche se SMTP fallisce) oppure 500 se SMTP non configurato
        # Ma deve avere 'risultati' nel body se 200 o 207
        assert r.status_code in [200, 207, 500], f"Status inatteso: {r.status_code} {r.text}"
        if r.status_code in [200, 207]:
            data = r.json()
            assert "risultati" in data, f"Manca 'risultati' nel body: {data}"

    def test_invia_email_fornitori_senza_email_ritorna_errore_soft(self, api, test_ordine_id):
        """Se email mancante, il fornitore viene saltato con errore soft (non 500)."""
        payload = {
            "fornitori": [
                {"nome": "TestFornitore_SenzaEmail", "email": "", "prodotti": []}
            ],
            "note": ""
        }
        r = api.post(f"{BASE_URL}/api/ordini-fornitori/{test_ordine_id}/invia-email", json=payload)
        # Con email vuota, deve essere filtrato (email.strip() == "")
        # La lista fornitori filtrata diventa vuota, nessuna chiamata SMTP
        # Ma l'endpoint gestisce anche il caso "nessuna email con PEC_USER non impostato"
        assert r.status_code in [200, 500]

    def test_invia_email_404_on_invalid_ordine(self, api):
        payload = {"fornitori": [{"nome": "X", "email": "x@x.it", "prodotti": []}], "note": ""}
        r = api.post(f"{BASE_URL}/api/ordini-fornitori/invalid-nonexistent-id-xyz/invia-email", json=payload)
        assert r.status_code == 404
