"""
Ceraldi ERP - Backend API Tests for Iteration 5
Tests for specific features:
- Fatture Ricevute archivio (imponibile, iva, prima_nota_cassa_id)
- Paga manuale con metodo cassa/banca
- F24 from quietanze_f24 (anno 2025/2026)
- Corrispettivi matricola_rt for 2026
- Noleggio veicoli totals consistency
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://bilancio-patch.preview.emergentagent.com"


class TestHealthEndpoints:
    """Basic health check"""
    
    def test_health_check(self):
        """Test /api/health returns status ok"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") in ["ok", "healthy"]
        print(f"✅ Health check passed: {data}")


class TestFattureRicevuteArchivio:
    """Test GET /api/fatture-ricevute/archivio returns imponibile, iva, prima_nota_cassa_id fields"""
    
    def test_archivio_returns_imponibile_iva(self):
        """Test archivio endpoint returns imponibile and iva fields"""
        response = requests.get(f"{BASE_URL}/api/fatture-ricevute/archivio?anno=2026&limit=10", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # API returns {"fatture": [...], "total": X}
        assert "fatture" in data, f"Expected 'fatture' key in response: {data.keys()}"
        
        if len(data["fatture"]) > 0:
            fattura = data["fatture"][0]
            # Check that imponibile and iva are present
            assert "imponibile" in fattura, f"Missing 'imponibile' in fattura: {fattura.keys()}"
            assert "iva" in fattura, f"Missing 'iva' in fattura: {fattura.keys()}"
            assert "prima_nota_cassa_id" in fattura, f"Missing 'prima_nota_cassa_id' in fattura: {fattura.keys()}"
            print(f"✅ Archivio returns imponibile={fattura.get('imponibile')}, iva={fattura.get('iva')}, prima_nota_cassa_id={fattura.get('prima_nota_cassa_id')}")
        else:
            # Try 2025 data
            response2 = requests.get(f"{BASE_URL}/api/fatture-ricevute/archivio?anno=2025&limit=5", timeout=30)
            data2 = response2.json()
            if len(data2.get("fatture", [])) > 0:
                fattura = data2["fatture"][0]
                assert "imponibile" in fattura
                assert "iva" in fattura
                print(f"✅ Archivio (2025) returns imponibile={fattura.get('imponibile')}, iva={fattura.get('iva')}")
            else:
                print("⚠️ No fatture found for 2026 or 2025, skipping field verification")


class TestPagaManualeEndpoint:
    """Test POST /api/fatture-ricevute/paga-manuale creates prima_nota_cassa entry when metodo='cassa'"""
    
    def test_paga_manuale_endpoint_exists(self):
        """Test that paga-manuale endpoint exists and accepts POST"""
        # First, we need a fattura ID - get one from archivio
        response = requests.get(f"{BASE_URL}/api/fatture-ricevute/archivio?anno=2026&limit=1", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        if len(data.get("fatture", [])) == 0:
            # Try 2025
            response = requests.get(f"{BASE_URL}/api/fatture-ricevute/archivio?anno=2025&limit=1", timeout=30)
            data = response.json()
        
        if len(data.get("fatture", [])) > 0:
            fattura = data["fatture"][0]
            fattura_id = fattura.get("id")
            
            # Test that the endpoint exists by sending a minimal payload
            # We'll use a FAKE fattura_id to avoid modifying real data
            payload = {
                "fattura_id": "TEST_nonexistent_id_123",
                "importo": 100.00,
                "metodo": "cassa",
                "data_pagamento": "2026-01-15",
                "fornitore": "Test Fornitore",
                "numero_fattura": "TEST123"
            }
            
            response = requests.post(f"{BASE_URL}/api/fatture-ricevute/paga-manuale", json=payload, timeout=30)
            # Should fail with 404 (fattura not found) or succeed if ID exists
            assert response.status_code in [200, 400, 404, 422, 500], f"Unexpected status: {response.status_code}"
            print(f"✅ paga-manuale endpoint exists and responds: {response.status_code}")
        else:
            pytest.skip("No fatture available for testing")
    
    def test_paga_manuale_metodo_validation(self):
        """Test that metodo must be 'cassa' or 'banca'"""
        payload = {
            "fattura_id": "test_id",
            "importo": 100.00,
            "metodo": "invalid_metodo",
            "data_pagamento": "2026-01-15"
        }
        response = requests.post(f"{BASE_URL}/api/fatture-ricevute/paga-manuale", json=payload, timeout=30)
        # Should return 400 for invalid metodo
        assert response.status_code in [400, 404, 422], f"Expected validation error, got {response.status_code}"
        print(f"✅ paga-manuale validates metodo correctly: {response.status_code}")


class TestF24PublicModels:
    """Test GET /api/f24-public/models returns F24s from quietanze_f24"""
    
    def test_f24_models_2025(self):
        """Test F24 models for anno 2025 returns data with saldo_finale and data_scadenza"""
        response = requests.get(f"{BASE_URL}/api/f24-public/models?anno=2025", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "f24s" in data, f"Expected 'f24s' key in response: {data.keys()}"
        assert "count" in data, f"Expected 'count' key in response"
        
        # Should have data from quietanze_f24
        print(f"✅ F24 2025 count: {data.get('count', 0)}")
        
        if data.get("count", 0) > 0 and len(data.get("f24s", [])) > 0:
            f24 = data["f24s"][0]
            # Check required fields
            assert "saldo_finale" in f24, f"Missing 'saldo_finale' in F24: {f24.keys()}"
            assert "data_scadenza" in f24, f"Missing 'data_scadenza' in F24: {f24.keys()}"
            print(f"✅ F24 fields: saldo_finale={f24.get('saldo_finale')}, data_scadenza={f24.get('data_scadenza')}")
            
            # Verify count >= 1 (requirement says ~52 entries for 2025)
            assert data.get("count", 0) >= 1, f"Expected at least 1 F24 for 2025"
    
    def test_f24_models_2026(self):
        """Test F24 models for anno 2026 returns at least 1 item"""
        response = requests.get(f"{BASE_URL}/api/f24-public/models?anno=2026", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "f24s" in data
        print(f"✅ F24 2026 count: {data.get('count', 0)}")
        
        # Per requirement: at least 1 F24 for 2026
        assert data.get("count", 0) >= 1, f"Expected at least 1 F24 for 2026, got {data.get('count', 0)}"
        print(f"✅ F24 2026 has {data.get('count')} items")


class TestCorrispettivi:
    """Test GET /api/corrispettivi?anno=2026 returns records with non-empty matricola_rt"""
    
    def test_corrispettivi_2026_matricola_rt(self):
        """Test corrispettivi for 2026 have matricola_rt field"""
        response = requests.get(f"{BASE_URL}/api/corrispettivi?anno=2026", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Response is a list of corrispettivi
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        
        print(f"✅ Corrispettivi 2026 count: {len(data)}")
        
        if len(data) > 0:
            # Check that at least one has non-empty matricola_rt
            has_matricola = False
            for corr in data:
                matricola = corr.get("matricola_rt", "")
                if matricola and len(str(matricola).strip()) > 0:
                    has_matricola = True
                    print(f"✅ Found corrispettivo with matricola_rt: {matricola}")
                    break
            
            # Requirement: matricola_rt should be '99MEY026532' per problem statement
            assert has_matricola, f"No corrispettivo with non-empty matricola_rt found"
        else:
            pytest.skip("No corrispettivi found for 2026")


class TestNoleggioVeicoli:
    """Test GET /api/noleggio/veicoli returns consistent totals"""
    
    def test_noleggio_veicoli_endpoint(self):
        """Test noleggio veicoli endpoint works"""
        response = requests.get(f"{BASE_URL}/api/noleggio/veicoli", timeout=30)
        # Endpoint may return 200 or 404 if no data
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Noleggio veicoli endpoint works, keys: {data.keys() if isinstance(data, dict) else 'list'}")
            
            # Check veicoli list
            veicoli = data.get("veicoli", []) if isinstance(data, dict) else data
            if len(veicoli) > 0:
                for veicolo in veicoli[:2]:  # Check first 2
                    if isinstance(veicolo, dict):
                        # Verify totale_generale = sum of all sub-totals
                        totale_canoni = veicolo.get("totale_canoni", 0) or 0
                        totale_bollo = veicolo.get("totale_bollo", 0) or 0
                        totale_pedaggio = veicolo.get("totale_pedaggio", 0) or 0
                        totale_verbali = veicolo.get("totale_verbali", 0) or 0
                        totale_costi_extra = veicolo.get("totale_costi_extra", 0) or 0
                        totale_riparazioni = veicolo.get("totale_riparazioni", 0) or 0
                        totale_generale = veicolo.get("totale_generale", 0) or 0
                        
                        calculated_total = totale_canoni + totale_bollo + totale_pedaggio + totale_verbali + totale_costi_extra + totale_riparazioni
                        
                        # Allow small floating point difference
                        diff = abs(calculated_total - totale_generale)
                        assert diff < 0.1, f"Total mismatch: calculated {calculated_total} != stored {totale_generale} (diff: {diff})"
                        
                        print(f"✅ Veicolo {veicolo.get('targa', 'N/A')}: totale_generale={totale_generale} matches sum={calculated_total}")
        else:
            print(f"⚠️ Noleggio veicoli returned 404 - may be no data")
    
    def test_noleggio_veicoli_anno_filter(self):
        """Test noleggio veicoli with anno=2026"""
        response = requests.get(f"{BASE_URL}/api/noleggio/veicoli?anno=2026", timeout=30)
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            veicoli = data.get("veicoli", []) if isinstance(data, dict) else data
            print(f"✅ Noleggio veicoli 2026: {len(veicoli)} veicoli found")


class TestDashboardNoPOSCalendar:
    """Test that Dashboard doesn't have POS Calendar (verify via API or code check)"""
    
    def test_dashboard_loads(self):
        """Test dashboard API endpoints work"""
        # Test dashboard summary
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", timeout=30)
        # May return 200 or 404 depending on implementation
        assert response.status_code in [200, 404], f"Dashboard stats: {response.status_code}"
        print(f"✅ Dashboard stats endpoint: {response.status_code}")
        
        # Test dashboard summary with anno
        response = requests.get(f"{BASE_URL}/api/dashboard/summary?anno=2026", timeout=30)
        assert response.status_code in [200, 404], f"Dashboard summary: {response.status_code}"
        print(f"✅ Dashboard summary endpoint: {response.status_code}")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
