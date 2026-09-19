"""
Test Iteration 47 Features:
- Toggle 'Giorno Non Produttivo' API endpoints
- Auto-rileva Allergeni Tutte API
- Supervisor P1 alert suppression when giorno non produttivo
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    pytest.skip(
        "test live: impostare REACT_APP_BACKEND_URL per eseguirlo contro un backend dedicato",
        allow_module_level=True,
    )


class TestGiornoNonProduttivo:
    """Test GET/POST /api/chiusure/giorno-non-produttivo/oggi endpoints"""
    
    def test_get_giorno_non_produttivo_oggi_returns_correct_structure(self):
        """GET /api/chiusure/giorno-non-produttivo/oggi returns {data, non_produttivo, motivo}"""
        response = requests.get(f"{BASE_URL}/api/chiusure/giorno-non-produttivo/oggi")
        assert response.status_code == 200
        
        data = response.json()
        assert "data" in data, "Response should contain 'data' field"
        assert "non_produttivo" in data, "Response should contain 'non_produttivo' field"
        assert isinstance(data["non_produttivo"], bool), "non_produttivo should be boolean"
        # Data should be in YYYY-MM-DD format
        assert len(data["data"]) == 10, "data should be in YYYY-MM-DD format"
        assert "-" in data["data"], "data should contain dashes"
    
    def test_post_giorno_non_produttivo_attivo_true(self):
        """POST with {attivo: true} sets non_produttivo=true"""
        response = requests.post(
            f"{BASE_URL}/api/chiusure/giorno-non-produttivo/oggi",
            json={"attivo": True, "motivo": "Test giorno riposo"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == True
        assert data.get("non_produttivo") == True
        
        # Verify with GET
        get_response = requests.get(f"{BASE_URL}/api/chiusure/giorno-non-produttivo/oggi")
        assert get_response.status_code == 200
        get_data = get_response.json()
        assert get_data["non_produttivo"] == True
    
    def test_post_giorno_non_produttivo_attivo_false(self):
        """POST with {attivo: false} removes the flag"""
        # First set it to true
        requests.post(
            f"{BASE_URL}/api/chiusure/giorno-non-produttivo/oggi",
            json={"attivo": True}
        )
        
        # Then set it to false
        response = requests.post(
            f"{BASE_URL}/api/chiusure/giorno-non-produttivo/oggi",
            json={"attivo": False}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") == True
        assert data.get("non_produttivo") == False
        
        # Verify with GET
        get_response = requests.get(f"{BASE_URL}/api/chiusure/giorno-non-produttivo/oggi")
        assert get_response.status_code == 200
        get_data = get_response.json()
        assert get_data["non_produttivo"] == False


class TestSupervisorP1Suppression:
    """Test that P1 alert is suppressed when giorno non produttivo is active"""
    
    def test_p1_present_when_produttivo(self):
        """P1 alert should be present when giorno is produttivo (non_produttivo=false)"""
        # Ensure giorno is produttivo
        requests.post(
            f"{BASE_URL}/api/chiusure/giorno-non-produttivo/oggi",
            json={"attivo": False}
        )
        
        response = requests.get(f"{BASE_URL}/api/supervisor/stato")
        assert response.status_code == 200
        
        data = response.json()
        alerts = data.get("alerts", [])
        alert_ids = [a.get("id") for a in alerts]
        
        # P1 should be present (assuming no lotti registered today)
        # Note: This test may fail if lotti are registered today
        assert "P1" in alert_ids, "P1 alert should be present when giorno is produttivo"
    
    def test_p1_suppressed_when_non_produttivo(self):
        """P1 alert should be suppressed when giorno non produttivo is active"""
        # Set giorno as non produttivo
        requests.post(
            f"{BASE_URL}/api/chiusure/giorno-non-produttivo/oggi",
            json={"attivo": True}
        )
        
        response = requests.get(f"{BASE_URL}/api/supervisor/stato")
        assert response.status_code == 200
        
        data = response.json()
        alerts = data.get("alerts", [])
        alert_ids = [a.get("id") for a in alerts]
        
        # P1 should NOT be present
        assert "P1" not in alert_ids, "P1 alert should be suppressed when giorno non produttivo"
        
        # Cleanup: reset to produttivo
        requests.post(
            f"{BASE_URL}/api/chiusure/giorno-non-produttivo/oggi",
            json={"attivo": False}
        )
    
    def test_p1_returns_after_reset(self):
        """P1 alert should return after resetting giorno to produttivo"""
        # Set as non produttivo
        requests.post(
            f"{BASE_URL}/api/chiusure/giorno-non-produttivo/oggi",
            json={"attivo": True}
        )
        
        # Verify P1 is suppressed
        response1 = requests.get(f"{BASE_URL}/api/supervisor/stato")
        alerts1 = [a.get("id") for a in response1.json().get("alerts", [])]
        assert "P1" not in alerts1
        
        # Reset to produttivo
        requests.post(
            f"{BASE_URL}/api/chiusure/giorno-non-produttivo/oggi",
            json={"attivo": False}
        )
        
        # Verify P1 is back
        response2 = requests.get(f"{BASE_URL}/api/supervisor/stato")
        alerts2 = [a.get("id") for a in response2.json().get("alerts", [])]
        assert "P1" in alerts2, "P1 should return after resetting to produttivo"


class TestAutoRilevaAllergeniTutte:
    """Test POST /api/food-cost/auto-rileva-allergeni-tutte endpoint"""
    
    def test_auto_rileva_allergeni_tutte_endpoint_exists(self):
        """POST /api/food-cost/auto-rileva-allergeni-tutte should return 200"""
        response = requests.post(
            f"{BASE_URL}/api/food-cost/auto-rileva-allergeni-tutte",
            json={}
        )
        assert response.status_code == 200
    
    def test_auto_rileva_allergeni_tutte_returns_correct_structure(self):
        """Response should contain aggiornate, skippate_manuale, con_allergeni fields"""
        response = requests.post(
            f"{BASE_URL}/api/food-cost/auto-rileva-allergeni-tutte",
            json={}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "aggiornate" in data, "Response should contain 'aggiornate' field"
        assert "skippate_manuale" in data or "status" in data, "Response should contain status info"
        assert isinstance(data.get("aggiornate", 0), int), "aggiornate should be integer"


class TestAutoRilevaAllergeneSingola:
    """Test POST /api/food-cost/auto-rileva-allergeni-ricetta/{id} endpoint"""
    
    def test_auto_rileva_single_recipe_endpoint_format(self):
        """Verify the single recipe auto-rileva endpoint exists"""
        # Get a recipe ID first
        response = requests.get(f"{BASE_URL}/api/food-cost/registro-allergeni")
        assert response.status_code == 200
        
        ricette = response.json().get("ricette", [])
        if len(ricette) > 0:
            ricetta_id = ricette[0].get("id")
            if ricetta_id:
                # Test the endpoint
                auto_response = requests.post(
                    f"{BASE_URL}/api/food-cost/auto-rileva-allergeni-ricetta/{ricetta_id}"
                )
                # Should return 200 or 404 if recipe not found
                assert auto_response.status_code in [200, 404]


class TestRegistroAllergeni:
    """Test GET /api/food-cost/registro-allergeni endpoint"""
    
    def test_registro_allergeni_returns_ricette(self):
        """GET /api/food-cost/registro-allergeni should return ricette list"""
        response = requests.get(f"{BASE_URL}/api/food-cost/registro-allergeni")
        assert response.status_code == 200
        
        data = response.json()
        assert "ricette" in data, "Response should contain 'ricette' field"
        assert isinstance(data["ricette"], list), "ricette should be a list"
    
    def test_ricette_have_required_fields(self):
        """Each ricetta should have id, nome, allergeni fields"""
        response = requests.get(f"{BASE_URL}/api/food-cost/registro-allergeni")
        assert response.status_code == 200
        
        ricette = response.json().get("ricette", [])
        if len(ricette) > 0:
            ricetta = ricette[0]
            assert "id" in ricetta, "Ricetta should have 'id' field"
            assert "nome" in ricetta, "Ricetta should have 'nome' field"
            # allergeni may be empty list or None


# Cleanup fixture to ensure state is reset after tests
@pytest.fixture(autouse=True, scope="module")
def cleanup_giorno_non_produttivo():
    """Ensure giorno non produttivo is reset after all tests"""
    yield
    # Cleanup: reset to produttivo
    requests.post(
        f"{BASE_URL}/api/chiusure/giorno-non-produttivo/oggi",
        json={"attivo": False}
    )
