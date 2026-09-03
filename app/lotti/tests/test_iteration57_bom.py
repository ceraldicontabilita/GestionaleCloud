"""
Iteration 57: Tests for new BOM features
Tests:
  GET /api/ricette/{id}/bom           - BOM explosion (arancini, simple recipe)
  GET /api/ricette/{id}/bom?porzioni  - BOM scaling
  POST /api/food-cost/calcola-nutrizionale (simple recipe regression)
  POST /api/registra-produzione-lotto with lotti_componenti_json param
  Regression: previous features still working
"""
import pytest
import requests
import os
import json

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ARANCINI_ID = "f853d874-50be-45bf-81a3-e4c9797f5a28"
INVALID_ID = "00000000-0000-0000-0000-000000000000"


class TestBomEndpoint:
    """GET /api/ricette/{id}/bom - BOM explosion endpoint"""

    def test_bom_arancini_status_200(self):
        """BOM endpoint returns 200 for valid arancini recipe"""
        res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}/bom")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    def test_bom_arancini_response_structure(self):
        """BOM response must have required keys"""
        res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}/bom")
        assert res.status_code == 200
        data = res.json()
        required_keys = ["ricetta_id", "ricetta_nome", "porzioni_richieste", "porzioni_base",
                         "moltiplicatore", "ingredienti_esplosi", "struttura", "e_composita"]
        for key in required_keys:
            assert key in data, f"Missing key '{key}' in BOM response"

    def test_bom_arancini_ricetta_id(self):
        """BOM response ricetta_id must match arancini ID"""
        res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}/bom")
        assert res.status_code == 200
        data = res.json()
        assert data["ricetta_id"] == ARANCINI_ID

    def test_bom_arancini_e_composita_false(self):
        """Arancini is a simple recipe - e_composita must be False"""
        res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}/bom")
        assert res.status_code == 200
        data = res.json()
        assert data["e_composita"] == False, f"Expected e_composita=False, got {data['e_composita']}"

    def test_bom_arancini_ingredienti_esplosi_count(self):
        """Arancini should have 6 ingredienti_esplosi"""
        res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}/bom")
        assert res.status_code == 200
        data = res.json()
        count = len(data["ingredienti_esplosi"])
        assert count == 6, f"Expected 6 ingredienti_esplosi, got {count}: {data['ingredienti_esplosi']}"

    def test_bom_arancini_ingredienti_esplosi_structure(self):
        """Each ingrediente_esploso must have nome, quantita, unita_misura"""
        res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}/bom")
        assert res.status_code == 200
        data = res.json()
        for ing in data["ingredienti_esplosi"]:
            assert "nome" in ing, f"Missing 'nome' in ingrediente: {ing}"
            assert "quantita" in ing, f"Missing 'quantita' in ingrediente: {ing}"
            assert "unita_misura" in ing, f"Missing 'unita_misura' in ingrediente: {ing}"
            assert isinstance(ing["quantita"], (int, float)), f"quantita not numeric: {ing['quantita']}"

    def test_bom_arancini_base_porzioni(self):
        """BOM base porzioni_base should be > 0"""
        res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}/bom")
        assert res.status_code == 200
        data = res.json()
        assert data["porzioni_base"] > 0, "porzioni_base must be > 0"

    def test_bom_arancini_moltiplicatore_default(self):
        """Without porzioni param, moltiplicatore should be 1.0 (base == requested)"""
        res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}/bom")
        assert res.status_code == 200
        data = res.json()
        assert data["moltiplicatore"] == 1.0, f"Expected moltiplicatore=1.0, got {data['moltiplicatore']}"

    def test_bom_not_found_404(self):
        """BOM endpoint returns 404 for invalid recipe ID"""
        res = requests.get(f"{BASE_URL}/api/ricette/{INVALID_ID}/bom")
        assert res.status_code == 404, f"Expected 404, got {res.status_code}"


class TestBomScaling:
    """GET /api/ricette/{id}/bom?porzioni=N - BOM scaling by portion"""

    def test_bom_scaled_porzioni_16_status(self):
        """BOM with porzioni=16 should return 200"""
        res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}/bom?porzioni=16")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    def test_bom_scaled_porzioni_16_moltiplicatore(self):
        """BOM with porzioni=16 - moltiplicatore should reflect scaling"""
        # First get base porzioni
        base_res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}/bom")
        assert base_res.status_code == 200
        base_data = base_res.json()
        porzioni_base = base_data["porzioni_base"]

        # Get scaled BOM
        scaled_res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}/bom?porzioni=16")
        assert scaled_res.status_code == 200
        scaled_data = scaled_res.json()

        expected_mult = round(16 / porzioni_base, 4)
        assert scaled_data["moltiplicatore"] == expected_mult, (
            f"Expected moltiplicatore={expected_mult} (16/{porzioni_base}), "
            f"got {scaled_data['moltiplicatore']}"
        )

    def test_bom_scaled_quantities_doubled(self):
        """When porzioni=2*base, quantities should approximately double"""
        base_res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}/bom")
        assert base_res.status_code == 200
        base_data = base_res.json()
        porzioni_base = base_data["porzioni_base"]
        base_ings = {i["nome"]: i["quantita"] for i in base_data["ingredienti_esplosi"]}

        double_porzioni = porzioni_base * 2
        scaled_res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}/bom?porzioni={double_porzioni}")
        assert scaled_res.status_code == 200
        scaled_data = scaled_res.json()
        scaled_ings = {i["nome"]: i["quantita"] for i in scaled_data["ingredienti_esplosi"]}

        # Check each ingredient is approximately doubled
        for nome, base_qt in base_ings.items():
            if nome in scaled_ings and base_qt > 0:
                expected = base_qt * 2
                actual = scaled_ings[nome]
                tolerance = 0.01
                assert abs(actual - expected) <= tolerance + abs(expected) * 0.01, (
                    f"Ingredient '{nome}': expected ~{expected}, got {actual}"
                )

    def test_bom_scaled_porzioni_richieste(self):
        """BOM with porzioni=16 should report porzioni_richieste=16"""
        res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}/bom?porzioni=16")
        assert res.status_code == 200
        data = res.json()
        assert data["porzioni_richieste"] == 16, f"Expected porzioni_richieste=16, got {data['porzioni_richieste']}"


class TestBomNutrizionaleIntegration:
    """POST /api/food-cost/calcola-nutrizionale - BOM integration and regression"""

    def test_calcola_nutrizionale_simple_recipe_regression(self):
        """Simple recipe (arancini) calcola-nutrizionale still works after v57"""
        res = requests.post(f"{BASE_URL}/api/food-cost/calcola-nutrizionale/{ARANCINI_ID}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    def test_calcola_nutrizionale_has_valori_nutrizionali(self):
        """calcola-nutrizionale returns valori_nutrizionali dict"""
        res = requests.post(f"{BASE_URL}/api/food-cost/calcola-nutrizionale/{ARANCINI_ID}")
        assert res.status_code == 200
        data = res.json()
        assert "valori_nutrizionali" in data
        vn = data["valori_nutrizionali"]
        required = ["kcal", "kj", "grassi", "saturi", "carboidrati", "zuccheri", "fibre", "proteine", "sale"]
        for key in required:
            assert key in vn, f"Missing '{key}'"
        assert isinstance(vn["kcal"], (int, float)), "kcal must be numeric"
        assert vn["kcal"] > 0, "kcal must be > 0"

    def test_calcola_nutrizionale_invalid_id_404(self):
        """calcola-nutrizionale returns 404 for invalid recipe"""
        res = requests.post(f"{BASE_URL}/api/food-cost/calcola-nutrizionale/{INVALID_ID}")
        assert res.status_code == 404, f"Expected 404, got {res.status_code}"

    def test_calcola_nutrizionale_copertura_field(self):
        """Response must include copertura_percentuale field"""
        res = requests.post(f"{BASE_URL}/api/food-cost/calcola-nutrizionale/{ARANCINI_ID}")
        assert res.status_code == 200
        data = res.json()
        assert "copertura_percentuale" in data
        cop = data["copertura_percentuale"]
        assert isinstance(cop, (int, float)), "copertura_percentuale must be numeric"
        assert 0 <= cop <= 100, f"copertura_percentuale out of range: {cop}"


class TestRegistraProduzioneConLottiComponenti:
    """POST /api/registra-produzione-lotto with lotti_componenti_json param"""

    def test_registra_produzione_with_lotti_componenti(self):
        """registra-produzione-lotto with lotti_componenti_json saves lotti_componenti field"""
        lotti_componenti = [
            {
                "lotto_id": "test-lotto-comp-001",
                "numero_lotto": "TESTCOMP-001-10pz-01012026",
                "nome": "Test Sotto-ricetta",
                "quantita_usata": 2.0,
                "unita": "porzioni"
            }
        ]
        lotti_componenti_json = json.dumps(lotti_componenti)
        params = {
            "ricetta_id": ARANCINI_ID,
            "pezzi": 8,
            "pezzi_base": 8,
            "costo_totale": 5.0,
            "data_produzione": "2026-02-15",
            "lotti_componenti_json": lotti_componenti_json
        }
        res = requests.post(f"{BASE_URL}/api/registra-produzione-lotto", params=params)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        # Verify lotti_componenti saved
        assert "lotti_componenti" in data, "Response missing 'lotti_componenti' field"
        saved = data["lotti_componenti"]
        assert isinstance(saved, list), "lotti_componenti must be a list"
        assert len(saved) == 1, f"Expected 1 component, got {len(saved)}"
        assert saved[0]["lotto_id"] == "test-lotto-comp-001"
        assert saved[0]["nome"] == "Test Sotto-ricetta"

    def test_registra_produzione_without_lotti_componenti(self):
        """registra-produzione-lotto without lotti_componenti_json - lotti_componenti should be []"""
        params = {
            "ricetta_id": ARANCINI_ID,
            "pezzi": 4,
            "pezzi_base": 4,
            "costo_totale": 2.5,
            "data_produzione": "2026-02-15"
        }
        res = requests.post(f"{BASE_URL}/api/registra-produzione-lotto", params=params)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        # lotti_componenti should exist and be []
        assert "lotti_componenti" in data, "Response missing 'lotti_componenti' field"
        assert data["lotti_componenti"] == [], f"Expected [], got {data['lotti_componenti']}"

    def test_registra_produzione_lotti_componenti_malformed_json(self):
        """registra-produzione-lotto with malformed JSON - should gracefully handle (return [] not crash)"""
        params = {
            "ricetta_id": ARANCINI_ID,
            "pezzi": 4,
            "pezzi_base": 4,
            "costo_totale": 2.5,
            "data_produzione": "2026-02-15",
            "lotti_componenti_json": "not-valid-json"
        }
        res = requests.post(f"{BASE_URL}/api/registra-produzione-lotto", params=params)
        # Should not crash (500), should return 200 with empty lotti_componenti
        assert res.status_code == 200, f"Expected 200 (graceful handling), got {res.status_code}: {res.text}"
        data = res.json()
        assert "lotti_componenti" in data
        assert data["lotti_componenti"] == [], f"Expected [] for malformed JSON, got {data['lotti_componenti']}"


class TestRecallLottiComponenti:
    """GET /api/lotti/recall/cerca - recall extended to search in lotti_componenti[]"""

    def test_recall_cerca_returns_200(self):
        """Recall endpoint returns 200"""
        res = requests.get(f"{BASE_URL}/api/lotti/recall/cerca?ingrediente=riso")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    def test_recall_cerca_has_required_fields(self):
        """Recall response has ingrediente_cercato, totale_lotti, lotti fields"""
        res = requests.get(f"{BASE_URL}/api/lotti/recall/cerca?ingrediente=riso")
        assert res.status_code == 200
        data = res.json()
        assert "ingrediente_cercato" in data
        assert "totale_lotti" in data
        assert "lotti" in data
        assert isinstance(data["lotti"], list)


class TestBomComponentiPatch:
    """PATCH /api/ricette/{id} with componenti field - BOM update test"""

    def test_patch_componenti_empty(self):
        """PATCH with componenti=[] should succeed with 200"""
        res = requests.patch(f"{BASE_URL}/api/ricette/{ARANCINI_ID}", json={"componenti": []})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data.get("success") == True

    def test_patch_componenti_with_ingredient(self):
        """PATCH with a sample ingrediente component should persist"""
        test_comp = [{"tipo": "ingrediente", "nome": "TEST_Farina", "quantita": 200, "unita_misura": "g"}]
        res = requests.patch(f"{BASE_URL}/api/ricette/{ARANCINI_ID}", json={"componenti": test_comp})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

        # Verify saved
        get_res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}")
        assert get_res.status_code == 200
        data = get_res.json()
        assert len(data.get("componenti", [])) == 1
        assert data["componenti"][0]["nome"] == "TEST_Farina"

        # Cleanup - reset to empty
        cleanup = requests.patch(f"{BASE_URL}/api/ricette/{ARANCINI_ID}", json={"componenti": []})
        assert cleanup.status_code == 200


class TestRicetteRegression:
    """Regression: existing ricette endpoints still work"""

    def test_get_ricette_list(self):
        """GET /api/ricette returns 200"""
        res = requests.get(f"{BASE_URL}/api/ricette")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)

    def test_get_arancini_detail(self):
        """GET /api/ricette/{id} returns 200 for arancini"""
        res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == ARANCINI_ID
        assert "nome" in data

    def test_arancini_has_componenti_field(self):
        """Arancini recipe has 'componenti' field in response (new BOM schema)"""
        res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}")
        assert res.status_code == 200
        data = res.json()
        # componenti should be present (even if empty list)
        assert "componenti" in data, "Recipe response missing 'componenti' field (BOM schema)"
        assert isinstance(data["componenti"], list), "componenti must be a list"

    def test_arancini_componenti_empty(self):
        """Arancini (simple recipe) should have componenti=[] or None"""
        res = requests.get(f"{BASE_URL}/api/ricette/{ARANCINI_ID}")
        assert res.status_code == 200
        data = res.json()
        comp = data.get("componenti") or []
        assert len(comp) == 0, f"Expected empty componenti for simple recipe, got {len(comp)}"
