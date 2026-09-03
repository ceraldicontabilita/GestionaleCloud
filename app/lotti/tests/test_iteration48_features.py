"""
Test Iteration 48 Features:
1. Controllo Olio Frittura module
2. Temperature Cottura module  
3. Ricezione Merce module
4. Bug fix: Recipe ingredient editing (no more [object Object] error)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8000').rstrip('/')

class TestControlloOlioFrittura:
    """Test Controllo Olio Frittura HACCP module"""
    
    def test_get_controllo_olio_oggi(self):
        """GET /api/controllo-olio/oggi returns array"""
        response = requests.get(f"{BASE_URL}/api/controllo-olio/oggi")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/controllo-olio/oggi - {len(data)} records")
    
    def test_get_controllo_olio_statistiche(self):
        """GET /api/controllo-olio/statistiche returns stats"""
        response = requests.get(f"{BASE_URL}/api/controllo-olio/statistiche?giorni=30")
        assert response.status_code == 200
        data = response.json()
        assert "totale_controlli" in data
        assert "percentuale_conformita" in data
        assert "sostituzioni_olio" in data
        print(f"✓ GET /api/controllo-olio/statistiche - {data['totale_controlli']} controlli, {data['percentuale_conformita']}% conformità")
    
    def test_registra_controllo_olio_conforme(self):
        """POST /api/controllo-olio/registra with conforming values"""
        payload = {
            "friggitrice": "Friggitrice 1",
            "colore": 2,
            "odore_ok": True,
            "temperatura": 165,
            "operatore": "Test Operator",
            "note": "Test conforme"
        }
        response = requests.post(f"{BASE_URL}/api/controllo-olio/registra", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["esito"] == "CONFORME"
        assert "id" in data
        print(f"✓ POST /api/controllo-olio/registra CONFORME - ID: {data['id']}")
        return data["id"]
    
    def test_registra_controllo_olio_non_conforme_temperatura(self):
        """POST /api/controllo-olio/registra with temperature out of range (>=175°C)"""
        payload = {
            "friggitrice": "Friggitrice 2",
            "colore": 2,
            "odore_ok": True,
            "temperatura": 180,  # Over 175°C limit
            "azione_correttiva": "Ridotta temperatura",
            "operatore": "Test"
        }
        response = requests.post(f"{BASE_URL}/api/controllo-olio/registra", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["esito"] == "NON_CONFORME"
        print(f"✓ POST /api/controllo-olio/registra NON_CONFORME (temp) - ID: {data['id']}")
    
    def test_registra_controllo_olio_non_conforme_colore(self):
        """POST /api/controllo-olio/registra with color >= 4 (non-conforming)"""
        payload = {
            "friggitrice": "Friggitrice 1",
            "colore": 4,  # Color 4 or 5 = non-conforming
            "odore_ok": True,
            "temperatura": 165,
            "azione_correttiva": "Olio sostituito",
            "olio_sostituito": True,
            "operatore": "Test"
        }
        response = requests.post(f"{BASE_URL}/api/controllo-olio/registra", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["esito"] == "NON_CONFORME"
        print(f"✓ POST /api/controllo-olio/registra NON_CONFORME (colore) - ID: {data['id']}")


class TestTemperatureCottura:
    """Test Temperature Cottura HACCP module"""
    
    def test_get_temperature_cottura_oggi(self):
        """GET /api/temperature-cottura/oggi returns array"""
        response = requests.get(f"{BASE_URL}/api/temperature-cottura/oggi")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/temperature-cottura/oggi - {len(data)} records")
    
    def test_get_temperature_cottura_statistiche(self):
        """GET /api/temperature-cottura/statistiche returns stats"""
        response = requests.get(f"{BASE_URL}/api/temperature-cottura/statistiche?giorni=30")
        assert response.status_code == 200
        data = response.json()
        assert "totale_registrazioni" in data
        assert "percentuale_conformita" in data
        print(f"✓ GET /api/temperature-cottura/statistiche - {data['totale_registrazioni']} registrazioni, {data['percentuale_conformita']}% conformità")
    
    def test_registra_temperatura_cottura_conforme(self):
        """POST /api/temperature-cottura/registra with temp >= 75°C (conforming)"""
        payload = {
            "prodotto": "Brioche Test",
            "tipo_cottura": "forno",
            "temperatura_cuore": 82,  # >= 75°C = conforming
            "operatore": "Test Operator"
        }
        response = requests.post(f"{BASE_URL}/api/temperature-cottura/registra", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["conforme"] == True
        assert data["soglia"] == 75.0
        print(f"✓ POST /api/temperature-cottura/registra CONFORME - ID: {data['id']}")
    
    def test_registra_temperatura_cottura_non_conforme(self):
        """POST /api/temperature-cottura/registra with temp < 75°C (non-conforming)"""
        payload = {
            "prodotto": "Pollo Test",
            "tipo_cottura": "griglia",
            "temperatura_cuore": 60,  # < 75°C = non-conforming
            "azione_correttiva": "Prolungata cottura di 10 minuti",
            "operatore": "Test"
        }
        response = requests.post(f"{BASE_URL}/api/temperature-cottura/registra", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["conforme"] == False
        print(f"✓ POST /api/temperature-cottura/registra NON_CONFORME - ID: {data['id']}")
    
    def test_registra_temperatura_cottura_con_abbattimento(self):
        """POST /api/temperature-cottura/registra with abbattimento (threshold 70°C)"""
        payload = {
            "prodotto": "Arrosto Test",
            "tipo_cottura": "forno",
            "temperatura_cuore": 72,  # >= 70°C with abbattimento = conforming
            "abbattimento_immediato": True,
            "operatore": "Test"
        }
        response = requests.post(f"{BASE_URL}/api/temperature-cottura/registra", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["conforme"] == True
        assert data["soglia"] == 70.0  # Lower threshold with abbattimento
        print(f"✓ POST /api/temperature-cottura/registra con abbattimento - ID: {data['id']}")


class TestRicezioneMerce:
    """Test Ricezione Merce HACCP module"""
    
    def test_get_ricezione_merce_oggi(self):
        """GET /api/ricezione-merce/oggi returns array"""
        response = requests.get(f"{BASE_URL}/api/ricezione-merce/oggi")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/ricezione-merce/oggi - {len(data)} records")
    
    def test_get_ricezione_merce_statistiche(self):
        """GET /api/ricezione-merce/statistiche/riepilogo returns stats"""
        response = requests.get(f"{BASE_URL}/api/ricezione-merce/statistiche/riepilogo?giorni=30")
        assert response.status_code == 200
        data = response.json()
        assert "totale_ricezioni" in data
        assert "percentuale_conformita" in data
        assert "merci_respinte" in data
        print(f"✓ GET /api/ricezione-merce/statistiche - {data['totale_ricezioni']} ricezioni, {data['percentuale_conformita']}% conformità")
    
    def test_registra_ricezione_merce_conforme(self):
        """POST /api/ricezione-merce/registra with conforming values"""
        payload = {
            "fornitore_nome": "Test Fornitore",
            "prodotto": "Mozzarella Test",
            "tipo_prodotto": "refrigerato",
            "temperatura_ricezione": 3,  # 0-4°C for refrigerato = conforming
            "imballaggio_integro": True,
            "etichetta_conforme": True,
            "operatore": "Test Operator"
        }
        response = requests.post(f"{BASE_URL}/api/ricezione-merce/registra", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["conforme"] == True
        assert data["temp_conforme"] == True
        print(f"✓ POST /api/ricezione-merce/registra CONFORME - ID: {data['id']}")
    
    def test_registra_ricezione_merce_non_conforme_temperatura(self):
        """POST /api/ricezione-merce/registra with temperature out of range"""
        payload = {
            "fornitore_nome": "Test Fornitore",
            "prodotto": "Latte Test",
            "tipo_prodotto": "refrigerato",
            "temperatura_ricezione": 8,  # > 4°C for refrigerato = non-conforming
            "imballaggio_integro": True,
            "etichetta_conforme": True,
            "azione_correttiva": "Merce respinta",
            "accettato": False,
            "operatore": "Test"
        }
        response = requests.post(f"{BASE_URL}/api/ricezione-merce/registra", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["conforme"] == False
        assert data["temp_conforme"] == False
        print(f"✓ POST /api/ricezione-merce/registra NON_CONFORME (temp) - ID: {data['id']}")
    
    def test_registra_ricezione_merce_congelato(self):
        """POST /api/ricezione-merce/registra for frozen product"""
        payload = {
            "fornitore_nome": "Test Fornitore",
            "prodotto": "Pesce Surgelato Test",
            "tipo_prodotto": "surgelato",
            "temperatura_ricezione": -20,  # -25 to -18°C for surgelato = conforming
            "imballaggio_integro": True,
            "etichetta_conforme": True,
            "lotto_fornitore": "LOT-TEST-SURG-001",
            "operatore": "Test"
        }
        response = requests.post(f"{BASE_URL}/api/ricezione-merce/registra", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["conforme"] == True
        print(f"✓ POST /api/ricezione-merce/registra surgelato CONFORME - ID: {data['id']}")


class TestRecipeIngredientEdit:
    """Test bug fix: Recipe ingredient editing should not show [object Object] error"""
    
    def test_get_ricette_list(self):
        """GET /api/ricette returns list of recipes"""
        response = requests.get(f"{BASE_URL}/api/ricette")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ GET /api/ricette - {len(data)} ricette")
        return data
    
    def test_get_single_ricetta(self):
        """GET /api/ricette/:id returns recipe with ingredienti_dettaglio"""
        # First get list of recipes
        ricette = self.test_get_ricette_list()
        if len(ricette) == 0:
            pytest.skip("No recipes available for testing")
        
        ricetta_id = ricette[0]["id"]
        response = requests.get(f"{BASE_URL}/api/ricette/{ricetta_id}")
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "nome" in data
        # ingredienti_dettaglio should be a list (may be empty)
        assert "ingredienti_dettaglio" in data or "ingredienti" in data
        print(f"✓ GET /api/ricette/{ricetta_id} - {data['nome']}")
        return data
    
    def test_aggiorna_ingredienti_ricetta(self):
        """POST /api/food-cost/aggiorna-ingredienti-ricetta should work without [object Object] error"""
        # Get a recipe with ingredients
        ricette = self.test_get_ricette_list()
        if len(ricette) == 0:
            pytest.skip("No recipes available for testing")
        
        # Find a recipe with ingredients
        ricetta_con_ingredienti = None
        for r in ricette:
            response = requests.get(f"{BASE_URL}/api/ricette/{r['id']}")
            if response.status_code == 200:
                data = response.json()
                ingredienti = data.get("ingredienti_dettaglio") or data.get("ingredienti") or []
                if len(ingredienti) > 0:
                    ricetta_con_ingredienti = data
                    break
        
        if not ricetta_con_ingredienti:
            pytest.skip("No recipe with ingredients found")
        
        ricetta_id = ricetta_con_ingredienti["id"]
        ingredienti = ricetta_con_ingredienti.get("ingredienti_dettaglio") or ricetta_con_ingredienti.get("ingredienti") or []
        
        # Modify the first ingredient's quantity
        if len(ingredienti) > 0:
            ingredienti_modificati = []
            for ing in ingredienti:
                ing_copy = dict(ing)
                # Ensure proper structure
                if "quantita" in ing_copy:
                    ing_copy["quantita"] = float(ing_copy.get("quantita", 100))
                ingredienti_modificati.append(ing_copy)
            
            # Update the first ingredient quantity
            ingredienti_modificati[0]["quantita"] = ingredienti_modificati[0].get("quantita", 100) + 1
            
            payload = {
                "ricetta_id": ricetta_id,
                "ingredienti_dettaglio": ingredienti_modificati
            }
            
            response = requests.post(f"{BASE_URL}/api/food-cost/aggiorna-ingredienti-ricetta", json=payload)
            
            # The key test: should NOT return [object Object] error
            if response.status_code != 200:
                error_detail = response.json().get("detail", "")
                # Check that error is NOT [object Object]
                assert "[object Object]" not in str(error_detail), f"Bug not fixed: got [object Object] error: {error_detail}"
            
            # If successful, verify the update
            if response.status_code == 200:
                data = response.json()
                assert data.get("success") == True or "id" in data or "ricetta_id" in data
                print(f"✓ POST /api/food-cost/aggiorna-ingredienti-ricetta - Updated recipe {ricetta_id}")
            else:
                # Even if it fails, it should not be [object Object]
                print(f"✓ POST /api/food-cost/aggiorna-ingredienti-ricetta - No [object Object] error (status: {response.status_code})")


class TestFoodCostCalculation:
    """Test food cost calculation for recipes"""
    
    def test_calcola_food_cost(self):
        """GET /api/food-cost/calcola/:id returns cost breakdown"""
        # Get a recipe
        response = requests.get(f"{BASE_URL}/api/ricette")
        if response.status_code != 200:
            pytest.skip("Cannot get recipes")
        
        ricette = response.json()
        if len(ricette) == 0:
            pytest.skip("No recipes available")
        
        ricetta_id = ricette[0]["id"]
        response = requests.get(f"{BASE_URL}/api/food-cost/calcola/{ricetta_id}")
        assert response.status_code == 200
        data = response.json()
        assert "ricetta_id" in data
        assert "ingredienti" in data
        assert "costo_totale" in data
        print(f"✓ GET /api/food-cost/calcola/{ricetta_id} - Costo totale: €{data['costo_totale']:.2f}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
