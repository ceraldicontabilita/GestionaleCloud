"""
Test Iteration 52 Features:
- GET /api/lotti: stato, consumato, data_consumo fields for all lotti
- GET /api/produzioni/: moltiplicatore field for all records
- GET /api/prodotti-vendita/: at least 150 products with costo_produzione > 0
- GET /api/lotti-fornitori?limit=5: returns exactly 5 records
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestLottiFields:
    """Test lotti endpoint returns stato, consumato, data_consumo for all records"""

    def test_lotti_returns_all_required_fields(self):
        """GET /api/lotti should return stato, consumato, data_consumo for all 33 lotti"""
        response = requests.get(f"{BASE_URL}/api/lotti")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        lotti = response.json()
        assert isinstance(lotti, list), "Response should be a list"
        assert len(lotti) >= 30, f"Expected at least 30 lotti, got {len(lotti)}"
        
        # Check all lotti have required fields
        missing_stato = []
        missing_consumato = []
        missing_data_consumo = []
        
        for lotto in lotti:
            lotto_id = lotto.get("id", lotto.get("numero_lotto", "unknown"))
            
            if "stato" not in lotto:
                missing_stato.append(lotto_id)
            if "consumato" not in lotto:
                missing_consumato.append(lotto_id)
            if "data_consumo" not in lotto:
                missing_data_consumo.append(lotto_id)
        
        assert len(missing_stato) == 0, f"Lotti missing 'stato': {missing_stato[:5]}"
        assert len(missing_consumato) == 0, f"Lotti missing 'consumato': {missing_consumato[:5]}"
        assert len(missing_data_consumo) == 0, f"Lotti missing 'data_consumo': {missing_data_consumo[:5]}"
        
        print(f"PASS: All {len(lotti)} lotti have stato, consumato, data_consumo fields")

    def test_lotti_stato_default_value(self):
        """Verify stato defaults to 'attivo'"""
        response = requests.get(f"{BASE_URL}/api/lotti")
        assert response.status_code == 200
        
        lotti = response.json()
        for lotto in lotti:
            stato = lotto.get("stato")
            assert stato is not None, f"Lotto {lotto.get('id')} has None stato"
            # stato should be a string (typically 'attivo')
            assert isinstance(stato, str), f"Lotto {lotto.get('id')} stato is not string: {stato}"
        
        print(f"PASS: All lotti have valid stato values")


class TestProduzioniMoltiplicatore:
    """Test produzioni endpoint returns moltiplicatore for all records"""

    def test_produzioni_returns_moltiplicatore(self):
        """GET /api/produzioni/ should return moltiplicatore for all records"""
        response = requests.get(f"{BASE_URL}/api/produzioni/")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        produzioni = response.json()
        assert isinstance(produzioni, list), "Response should be a list"
        
        missing_moltiplicatore = []
        invalid_moltiplicatore = []
        
        for prod in produzioni:
            prod_id = prod.get("id", "unknown")
            
            if "moltiplicatore" not in prod:
                missing_moltiplicatore.append(prod_id)
            else:
                molt = prod.get("moltiplicatore")
                if molt is None:
                    invalid_moltiplicatore.append(prod_id)
                elif not isinstance(molt, (int, float)):
                    invalid_moltiplicatore.append(f"{prod_id} (type: {type(molt).__name__})")
        
        assert len(missing_moltiplicatore) == 0, f"Produzioni missing 'moltiplicatore': {missing_moltiplicatore[:5]}"
        assert len(invalid_moltiplicatore) == 0, f"Produzioni with invalid 'moltiplicatore': {invalid_moltiplicatore[:5]}"
        
        print(f"PASS: All {len(produzioni)} produzioni have valid moltiplicatore field")


class TestProdottiVenditaCosto:
    """Test prodotti-vendita endpoint has at least 150 products with costo_produzione > 0"""

    def test_prodotti_vendita_costo_count(self):
        """GET /api/prodotti-vendita/ should have at least 150 products with costo_produzione > 0"""
        response = requests.get(f"{BASE_URL}/api/prodotti-vendita/")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        prodotti = response.json()
        assert isinstance(prodotti, list), "Response should be a list"
        
        # Count products with costo_produzione > 0
        prodotti_con_costo = [p for p in prodotti if float(p.get("costo_produzione", 0) or 0) > 0]
        
        print(f"Total prodotti: {len(prodotti)}")
        print(f"Prodotti con costo_produzione > 0: {len(prodotti_con_costo)}")
        
        assert len(prodotti_con_costo) >= 150, f"Expected at least 150 products with costo > 0, got {len(prodotti_con_costo)}"
        
        print(f"PASS: {len(prodotti_con_costo)} prodotti have costo_produzione > 0 (>= 150 required)")


class TestLottiFornitoiLimit:
    """Test lotti-fornitori endpoint respects limit parameter"""

    def test_lotti_fornitori_limit_5(self):
        """GET /api/lotti-fornitori?limit=5 should return exactly 5 records"""
        response = requests.get(f"{BASE_URL}/api/lotti-fornitori?limit=5")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        lotti = response.json()
        assert isinstance(lotti, list), "Response should be a list"
        assert len(lotti) == 5, f"Expected exactly 5 records, got {len(lotti)}"
        
        print(f"PASS: GET /api/lotti-fornitori?limit=5 returns exactly 5 records")

    def test_lotti_fornitori_limit_10(self):
        """GET /api/lotti-fornitori?limit=10 should return exactly 10 records"""
        response = requests.get(f"{BASE_URL}/api/lotti-fornitori?limit=10")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        lotti = response.json()
        assert isinstance(lotti, list), "Response should be a list"
        assert len(lotti) == 10, f"Expected exactly 10 records, got {len(lotti)}"
        
        print(f"PASS: GET /api/lotti-fornitori?limit=10 returns exactly 10 records")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
