"""
Iteration 56: Tests for new nutritional calculation feature (USDA-based)
Tests: POST /api/food-cost/calcola-nutrizionale/{ricetta_id}
       GET /api/food-cost/nutrizionale/{ricetta_id}
       Regression: POST /api/anomalie/registra
       Regression: GET /api/supervisor/stato
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ARANCINI_ID = "f853d874-50be-45bf-81a3-e4c9797f5a28"
INVALID_ID = "00000000-0000-0000-0000-000000000000"


class TestNutrizionaleCalcolo:
    """POST /api/food-cost/calcola-nutrizionale/{ricetta_id}"""

    def test_calcola_nutrizionale_arancini_status(self):
        """Should return 200 for valid arancini recipe"""
        res = requests.post(f"{BASE_URL}/api/food-cost/calcola-nutrizionale/{ARANCINI_ID}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    def test_calcola_nutrizionale_returns_valori_nutrizionali(self):
        """Response must contain valori_nutrizionali dict"""
        res = requests.post(f"{BASE_URL}/api/food-cost/calcola-nutrizionale/{ARANCINI_ID}")
        assert res.status_code == 200
        data = res.json()
        assert "valori_nutrizionali" in data, "Missing valori_nutrizionali in response"
        vn = data["valori_nutrizionali"]
        assert isinstance(vn, dict), "valori_nutrizionali must be a dict"

    def test_calcola_nutrizionale_all_required_fields(self):
        """valori_nutrizionali must contain all 9 required nutrient keys"""
        res = requests.post(f"{BASE_URL}/api/food-cost/calcola-nutrizionale/{ARANCINI_ID}")
        assert res.status_code == 200
        vn = res.json()["valori_nutrizionali"]
        required_keys = ["kcal", "kj", "grassi", "saturi", "carboidrati", "zuccheri", "fibre", "proteine", "sale"]
        for key in required_keys:
            assert key in vn, f"Missing key '{key}' in valori_nutrizionali"

    def test_calcola_nutrizionale_numeric_values(self):
        """All nutrient values must be numeric (float or int)"""
        res = requests.post(f"{BASE_URL}/api/food-cost/calcola-nutrizionale/{ARANCINI_ID}")
        assert res.status_code == 200
        vn = res.json()["valori_nutrizionali"]
        for key, val in vn.items():
            assert isinstance(val, (int, float)), f"Value for '{key}' is not numeric: {val}"

    def test_calcola_nutrizionale_kcal_positive(self):
        """kcal must be > 0 for a recipe with ingredients"""
        res = requests.post(f"{BASE_URL}/api/food-cost/calcola-nutrizionale/{ARANCINI_ID}")
        assert res.status_code == 200
        kcal = res.json()["valori_nutrizionali"].get("kcal", 0)
        assert kcal > 0, f"Expected kcal > 0, got {kcal}"

    def test_calcola_nutrizionale_kj_positive(self):
        """kj must be > 0"""
        res = requests.post(f"{BASE_URL}/api/food-cost/calcola-nutrizionale/{ARANCINI_ID}")
        assert res.status_code == 200
        kj = res.json()["valori_nutrizionali"].get("kj", 0)
        assert kj > 0, f"Expected kj > 0, got {kj}"

    def test_calcola_nutrizionale_copertura_present(self):
        """Response must include copertura_percentuale"""
        res = requests.post(f"{BASE_URL}/api/food-cost/calcola-nutrizionale/{ARANCINI_ID}")
        assert res.status_code == 200
        data = res.json()
        assert "copertura_percentuale" in data, "Missing copertura_percentuale"
        assert 0 <= data["copertura_percentuale"] <= 100

    def test_calcola_nutrizionale_ingredienti_non_trovati_present(self):
        """Response must include ingredienti_non_trovati list"""
        res = requests.post(f"{BASE_URL}/api/food-cost/calcola-nutrizionale/{ARANCINI_ID}")
        assert res.status_code == 200
        data = res.json()
        assert "ingredienti_non_trovati" in data, "Missing ingredienti_non_trovati"
        assert isinstance(data["ingredienti_non_trovati"], list)

    def test_calcola_nutrizionale_invalid_id_returns_404(self):
        """Invalid ricetta_id must return 404"""
        res = requests.post(f"{BASE_URL}/api/food-cost/calcola-nutrizionale/{INVALID_ID}")
        assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"

    def test_calcola_nutrizionale_data_persisted(self):
        """After POST, GET should return the saved nutritional values"""
        # First calculate
        post_res = requests.post(f"{BASE_URL}/api/food-cost/calcola-nutrizionale/{ARANCINI_ID}")
        assert post_res.status_code == 200
        saved_vn = post_res.json()["valori_nutrizionali"]

        # Then GET to verify persistence
        get_res = requests.get(f"{BASE_URL}/api/food-cost/nutrizionale/{ARANCINI_ID}")
        assert get_res.status_code == 200
        stored_vn = get_res.json()["valori_nutrizionali"]
        assert stored_vn == saved_vn, f"Stored values don't match: {stored_vn} vs {saved_vn}"


class TestNutrizionaleGet:
    """GET /api/food-cost/nutrizionale/{ricetta_id}"""

    def test_get_nutrizionale_valid_recipe(self):
        """Returns 200 for valid recipe"""
        res = requests.get(f"{BASE_URL}/api/food-cost/nutrizionale/{ARANCINI_ID}")
        assert res.status_code == 200

    def test_get_nutrizionale_response_structure(self):
        """Response includes ricetta_id, nome, valori_nutrizionali"""
        res = requests.get(f"{BASE_URL}/api/food-cost/nutrizionale/{ARANCINI_ID}")
        assert res.status_code == 200
        data = res.json()
        assert "ricetta_id" in data
        assert "nome" in data
        assert "valori_nutrizionali" in data
        assert data["ricetta_id"] == ARANCINI_ID

    def test_get_nutrizionale_invalid_returns_404(self):
        """Invalid ID returns 404"""
        res = requests.get(f"{BASE_URL}/api/food-cost/nutrizionale/{INVALID_ID}")
        assert res.status_code == 404


class TestRegressionAnomalie:
    """Regression: POST /api/anomalie/registra"""

    def test_anomalie_registra_still_works(self):
        """POST /api/anomalie/registra must return 200"""
        payload = {
            "tipo": "Test Nutrizionale",
            "descrizione": "Test regressione iteration 56",
            "gravita": "Bassa",
            "stato": "Aperta",
            "attrezzatura": "Test",
            "categoria": "Test"
        }
        res = requests.post(f"{BASE_URL}/api/anomalie/registra", json=payload)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data.get("success") == True

    def test_anomalie_lista_works(self):
        """GET /api/anomalie/lista must return list"""
        res = requests.get(f"{BASE_URL}/api/anomalie/lista")
        assert res.status_code == 200
        assert isinstance(res.json(), list)


class TestRegressionSupervisor:
    """Regression: GET /api/supervisor/stato"""

    def test_supervisor_stato_returns_200(self):
        """GET /api/supervisor/stato must return 200"""
        res = requests.get(f"{BASE_URL}/api/supervisor/stato")
        assert res.status_code == 200

    def test_supervisor_stato_has_alerts(self):
        """Response should include alerts list"""
        res = requests.get(f"{BASE_URL}/api/supervisor/stato")
        assert res.status_code == 200
        data = res.json()
        assert "alerts" in data or "stato" in data, f"Unexpected response: {data.keys()}"
