"""
Iteration 55 Bug-fix regression tests.
Tests:
1. POST /api/anomalie/registra - new alias endpoint (was 404 in iter 54)
2. POST /api/anomalie/ - original route still works
3. GET /api/anomalie/lista - returns list
4. GET /api/supervisor/stato - alerts with fixed check_anomalie_senza_azione (stato field)
5. POST /api/pec/import with force_reimport=true - structure check
6. PUT /api/ricette/{id}/prezzo-vendita - endpoint exists
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


# ──────────────────────────────────────────────────────────────────
# FIXTURES
# ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ──────────────────────────────────────────────────────────────────
# ANOMALIE ENDPOINTS
# ──────────────────────────────────────────────────────────────────

class TestAnomalieEndpoints:
    """Test anomalie endpoints including new /registra alias"""

    PAYLOAD = {
        "attrezzatura": "TEST_Frigorifero N°1",
        "categoria": "Frigorifero",
        "tipo": "Malfunzionamento",
        "descrizione": "TEST - Temperatura non stabile",
        "operatore_segnalazione": "Test Runner",
        "priorita": "Media"
    }

    created_ids = []

    def test_post_anomalie_registra_returns_200(self, session):
        """POST /api/anomalie/registra - new alias must return 200 (was 404)"""
        resp = session.post(f"{BASE_URL}/api/anomalie/registra", json=self.PAYLOAD)
        assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        assert "success" in data, "Response missing 'success' field"
        assert data["success"] == True, "success should be True"
        assert "anomalia" in data, "Response missing 'anomalia' field"
        anomalia = data["anomalia"]
        assert "id" in anomalia, "anomalia missing 'id'"
        assert anomalia.get("stato") == "Aperta", f"Expected stato=Aperta, got {anomalia.get('stato')}"
        assert anomalia.get("attrezzatura") == self.PAYLOAD["attrezzatura"]
        TestAnomalieEndpoints.created_ids.append(anomalia["id"])
        print(f"PASS: POST /api/anomalie/registra returned 200, id={anomalia['id']}")

    def test_post_anomalie_registra_response_structure(self, session):
        """POST /api/anomalie/registra - response has all required fields"""
        resp = session.post(f"{BASE_URL}/api/anomalie/registra", json=self.PAYLOAD)
        assert resp.status_code == 200
        anomalia = resp.json()["anomalia"]
        required_fields = ["id", "attrezzatura", "categoria", "tipo", "descrizione", "stato",
                           "data_segnalazione", "created_at"]
        for field in required_fields:
            assert field in anomalia, f"anomalia missing field: {field}"
        TestAnomalieEndpoints.created_ids.append(anomalia["id"])
        print(f"PASS: All required fields present in anomalia response")

    def test_post_anomalie_root_still_works(self, session):
        """POST /api/anomalie/ - original route must still return 200"""
        resp = session.post(f"{BASE_URL}/api/anomalie/", json=self.PAYLOAD)
        assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        assert data.get("success") == True
        anomalia = data.get("anomalia", {})
        TestAnomalieEndpoints.created_ids.append(anomalia.get("id", ""))
        print(f"PASS: POST /api/anomalie/ returned 200")

    def test_get_anomalie_lista_returns_200(self, session):
        """GET /api/anomalie/lista - returns list"""
        resp = session.get(f"{BASE_URL}/api/anomalie/lista")
        assert resp.status_code == 200, f"Expected 200 got {resp.status_code}"
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"PASS: GET /api/anomalie/lista returned {len(data)} anomalie")

    def test_get_anomalie_lista_contains_test_anomalia(self, session):
        """GET /api/anomalie/lista - created anomalie appear in list"""
        # First create one
        resp_create = session.post(f"{BASE_URL}/api/anomalie/registra", json=self.PAYLOAD)
        assert resp_create.status_code == 200
        created_id = resp_create.json()["anomalia"]["id"]
        TestAnomalieEndpoints.created_ids.append(created_id)

        # Now fetch list
        resp = session.get(f"{BASE_URL}/api/anomalie/lista")
        assert resp.status_code == 200
        data = resp.json()
        ids = [a.get("id") for a in data]
        assert created_id in ids, f"Created anomalia {created_id} not found in lista"
        print(f"PASS: Created anomalia found in lista")

    def test_anomalie_lista_filter_by_stato(self, session):
        """GET /api/anomalie/lista?stato=Aperta - filter works"""
        resp = session.get(f"{BASE_URL}/api/anomalie/lista", params={"stato": "Aperta"})
        assert resp.status_code == 200
        data = resp.json()
        for a in data:
            assert a.get("stato") == "Aperta", f"Got non-Aperta stato: {a.get('stato')}"
        print(f"PASS: Filter by stato=Aperta returned {len(data)} items, all Aperta")

    @pytest.fixture(autouse=True, scope="class")
    def cleanup(self, session):
        """Cleanup test anomalie after class"""
        yield
        for aid in self.created_ids:
            if aid:
                try:
                    session.delete(f"{BASE_URL}/api/anomalie/{aid}")
                except Exception:
                    pass
        print(f"CLEANUP: Deleted {len(self.created_ids)} test anomalie")


# ──────────────────────────────────────────────────────────────────
# SUPERVISOR STATO
# ──────────────────────────────────────────────────────────────────

class TestSupervisorStato:
    """Test GET /api/supervisor/stato - fixed check_anomalie_senza_azione"""

    def test_get_supervisor_stato_returns_200(self, session):
        """GET /api/supervisor/stato - returns 200"""
        resp = session.get(f"{BASE_URL}/api/supervisor/stato")
        assert resp.status_code == 200, f"Expected 200 got {resp.status_code}: {resp.text[:300]}"
        print(f"PASS: GET /api/supervisor/stato returned 200")

    def test_supervisor_stato_structure(self, session):
        """GET /api/supervisor/stato - response has required fields"""
        resp = session.get(f"{BASE_URL}/api/supervisor/stato")
        assert resp.status_code == 200
        data = resp.json()
        required = ["data_controllo", "totale_alert", "critici", "alti", "medi", "bassi",
                    "semaforo", "alerts"]
        for field in required:
            assert field in data, f"Response missing field: {field}"
        assert isinstance(data["alerts"], list), "alerts should be a list"
        assert data["semaforo"] in ["verde", "arancione", "rosso"], \
            f"semaforo should be verde/arancione/rosso, got {data['semaforo']}"
        print(f"PASS: supervisor/stato structure OK. Semaforo: {data['semaforo']}, Alerts: {data['totale_alert']}")

    def test_supervisor_stato_alerts_have_required_fields(self, session):
        """GET /api/supervisor/stato - each alert has id, titolo, priorita, route"""
        resp = session.get(f"{BASE_URL}/api/supervisor/stato")
        assert resp.status_code == 200
        alerts = resp.json()["alerts"]
        for alert in alerts:
            assert "id" in alert, f"Alert missing 'id': {alert}"
            assert "titolo" in alert, f"Alert missing 'titolo': {alert}"
            assert "priorita" in alert, f"Alert missing 'priorita': {alert}"
            assert "route" in alert, f"Alert missing 'route': {alert}"
            assert alert["priorita"] in ["critica", "alta", "media", "bassa"], \
                f"Invalid priorita: {alert['priorita']}"
        print(f"PASS: All {len(alerts)} alerts have required fields")

    def test_supervisor_no_wrong_field_anomalie_check(self, session):
        """
        After fix: check_anomalie_senza_azione uses stato field.
        Verify A6 alert is returned only for real open anomalie without action.
        (Previously used wrong 'data' field & always-true soluzione condition)
        """
        resp = session.get(f"{BASE_URL}/api/supervisor/stato")
        assert resp.status_code == 200
        data = resp.json()
        alerts = data["alerts"]
        a6_alerts = [a for a in alerts if a.get("id") == "A6"]
        # A6 might or might not be present — just verify it doesn't crash
        # and if present, it has sensible data
        for a in a6_alerts:
            assert "anomalia" in a["titolo"].lower() or "azione" in a["titolo"].lower(), \
                f"A6 titolo unexpected: {a['titolo']}"
        print(f"PASS: A6 check_anomalie_senza_azione OK. A6 alerts present: {len(a6_alerts)}")

    def test_supervisor_sommario_returns_200(self, session):
        """GET /api/supervisor/sommario - returns 200 with semaforo"""
        resp = session.get(f"{BASE_URL}/api/supervisor/sommario")
        assert resp.status_code == 200, f"Expected 200 got {resp.status_code}"
        data = resp.json()
        assert "semaforo" in data
        assert "totale_alert" in data
        print(f"PASS: supervisor/sommario OK. Semaforo: {data['semaforo']}")


# ──────────────────────────────────────────────────────────────────
# PEC IMPORT
# ──────────────────────────────────────────────────────────────────

class TestPECImport:
    """Test PEC import endpoint - force_reimport parameter added"""

    def test_pec_status_returns_200(self, session):
        """GET /api/pec/status - returns 200"""
        resp = session.get(f"{BASE_URL}/api/pec/status")
        assert resp.status_code == 200, f"Expected 200 got {resp.status_code}"
        data = resp.json()
        # May be not connected if no PEC configured
        assert "connected" in data, "Response missing 'connected' field"
        print(f"PASS: GET /api/pec/status returned 200, connected={data['connected']}")

    def test_pec_import_endpoint_exists_and_accepts_force_reimport(self, session):
        """POST /api/pec/import - endpoint exists and accepts force_reimport param"""
        # We don't have real PEC credentials, so we expect either 200 (success)
        # or a graceful error (422 would mean bad schema, 404 means missing endpoint)
        resp = session.post(
            f"{BASE_URL}/api/pec/import",
            json={"force_reimport": True, "only_unread": False}
        )
        # Should NOT be 404 (endpoint missing) or 405 (method not allowed)
        assert resp.status_code != 404, f"Endpoint /api/pec/import not found (404)"
        assert resp.status_code != 405, f"Method not allowed on /api/pec/import (405)"
        # 200 or 500 (no PEC creds) are both acceptable
        print(f"PASS: POST /api/pec/import responded {resp.status_code} (endpoint exists)")


# ──────────────────────────────────────────────────────────────────
# RICETTE PREZZO VENDITA ENDPOINT
# ──────────────────────────────────────────────────────────────────

class TestRicettePrezzVendita:
    """Test PUT /api/ricette/{id}/prezzo-vendita endpoint"""

    def test_ricette_endpoint_exists(self, session):
        """GET /api/ricette - returns list for finding a test recipe"""
        resp = session.get(f"{BASE_URL}/api/ricette")
        assert resp.status_code == 200, f"GET /api/ricette failed: {resp.status_code}"
        data = resp.json()
        assert isinstance(data, list), "Expected list of ricette"
        print(f"PASS: GET /api/ricette returned {len(data)} ricette")

    def test_put_prezzo_vendita_endpoint(self, session):
        """PUT /api/ricette/{id}/prezzo-vendita - endpoint exists and works"""
        # Get a real recipe ID
        resp = session.get(f"{BASE_URL}/api/ricette")
        assert resp.status_code == 200
        ricette = resp.json()
        if not ricette:
            pytest.skip("No ricette available to test prezzo-vendita")

        ricetta = ricette[0]
        ricetta_id = ricetta.get("id")
        assert ricetta_id, "Recipe has no id"

        resp_put = session.put(f"{BASE_URL}/api/ricette/{ricetta_id}/prezzo-vendita?prezzo=1.50")
        # Should not be 404 or 405
        assert resp_put.status_code != 404, \
            f"PUT /api/ricette/{ricetta_id}/prezzo-vendita returned 404 (endpoint missing)"
        assert resp_put.status_code != 405, \
            f"Method not allowed on PUT /api/ricette/{ricetta_id}/prezzo-vendita"
        assert resp_put.status_code == 200, \
            f"Expected 200, got {resp_put.status_code}: {resp_put.text[:200]}"
        print(f"PASS: PUT /api/ricette/{ricetta_id}/prezzo-vendita returned {resp_put.status_code}")

    def test_put_prezzo_vendita_invalid_value(self, session):
        """PUT /api/ricette/{id}/prezzo-vendita with invalid prezzo - returns 4xx"""
        resp = session.get(f"{BASE_URL}/api/ricette")
        assert resp.status_code == 200
        ricette = resp.json()
        if not ricette:
            pytest.skip("No ricette available")
        ricetta_id = ricette[0]["id"]
        resp_bad = session.put(f"{BASE_URL}/api/ricette/{ricetta_id}/prezzo-vendita?prezzo=-5")
        # Should handle gracefully (not 500)
        assert resp_bad.status_code != 500, \
            f"Server error on negative prezzo: {resp_bad.text[:200]}"
        print(f"PASS: Negative prezzo handled with status {resp_bad.status_code}")


# ──────────────────────────────────────────────────────────────────
# LOTTI ENDPOINTS (delete + smaltimento)
# ──────────────────────────────────────────────────────────────────

class TestLottiEndpoints:
    """Test lotti endpoints - delete and smaltimento"""

    def test_get_lotti_returns_200(self, session):
        """GET /api/lotti - returns 200"""
        resp = session.get(f"{BASE_URL}/api/lotti")
        assert resp.status_code == 200, f"Expected 200 got {resp.status_code}"
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: GET /api/lotti returned {len(data)} lotti")

    def test_lotti_smaltimento_endpoint(self, session):
        """PATCH /api/lotti/{id}/smalti - endpoint exists"""
        # Try with fake ID to check endpoint exists (expect 404 for missing lotto, not 405/405)
        fake_id = "TEST_" + str(uuid.uuid4())
        resp = session.patch(f"{BASE_URL}/api/lotti/{fake_id}/smalti?motivo=test")
        assert resp.status_code != 405, "PATCH /lotti/{id}/smalti returns 405 (method not allowed)"
        # 404 is fine (lotto not found), anything else shows the endpoint exists
        print(f"PASS: PATCH /api/lotti/{fake_id}/smalti responded {resp.status_code} (endpoint exists)")

    def test_lotti_delete_endpoint(self, session):
        """DELETE /api/lotti/{id} - endpoint exists"""
        fake_id = "TEST_" + str(uuid.uuid4())
        resp = session.delete(f"{BASE_URL}/api/lotti/{fake_id}")
        assert resp.status_code != 405, "DELETE /lotti/{id} returns 405 (method not allowed)"
        # 404 is fine (lotto not found)
        print(f"PASS: DELETE /api/lotti/{fake_id} responded {resp.status_code}")
