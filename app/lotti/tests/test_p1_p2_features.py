"""
Test P1/P2 Features for HACCP Ceraldi:
- GET /api/ricette-prezzi (Prezzi & Margini)
- GET /api/lotti (Lotti list)
- GET /api/lotti/recall/cerca (Recall ingrediente)
- GET /api/report-haccp/mensile (Report PDF HACCP)
- GET /api/produzioni/ (Storico Produzioni)
- GET /api/backup/lista (Backup list)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8000')

class TestRicettePrezzi:
    """Test Prezzi & Margini tab - GET /api/ricette-prezzi"""
    
    def test_ricette_prezzi_endpoint_returns_200(self):
        """Verify ricette-prezzi endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/ricette-prezzi")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/ricette-prezzi returned 200")
    
    def test_ricette_prezzi_returns_list(self):
        """Verify ricette-prezzi returns a list of recipes with pricing data"""
        response = requests.get(f"{BASE_URL}/api/ricette-prezzi")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"✓ Returned {len(data)} ricette with pricing data")
    
    def test_ricette_prezzi_structure(self):
        """Verify each ricetta has required pricing fields"""
        response = requests.get(f"{BASE_URL}/api/ricette-prezzi")
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            ricetta = data[0]
            required_fields = ['id', 'nome', 'costo_pezzo', 'prezzo_vendita', 'margine_pct']
            for field in required_fields:
                assert field in ricetta, f"Missing field: {field}"
            print(f"✓ Ricetta structure verified: {ricetta.get('nome', 'N/A')}")
            print(f"  - costo_pezzo: €{ricetta.get('costo_pezzo', 0):.4f}")
            print(f"  - prezzo_vendita: €{ricetta.get('prezzo_vendita', 0):.2f}")
            print(f"  - margine_pct: {ricetta.get('margine_pct', 0):.1f}%")
        else:
            pytest.skip("No ricette available to test structure")


class TestLotti:
    """Test Lotti tab - GET /api/lotti"""
    
    def test_lotti_endpoint_returns_200(self):
        """Verify lotti endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/lotti")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/lotti returned 200")
    
    def test_lotti_returns_list(self):
        """Verify lotti returns a list"""
        response = requests.get(f"{BASE_URL}/api/lotti")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"✓ Returned {len(data)} lotti totali")
    
    def test_lotti_count_expected(self):
        """Verify lotti count is approximately 125 as expected"""
        response = requests.get(f"{BASE_URL}/api/lotti")
        assert response.status_code == 200
        data = response.json()
        # Expected ~125 lotti
        assert len(data) >= 50, f"Expected at least 50 lotti, got {len(data)}"
        print(f"✓ Lotti count: {len(data)} (expected ~125)")
    
    def test_lotti_structure(self):
        """Verify lotto has required fields"""
        response = requests.get(f"{BASE_URL}/api/lotti")
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            lotto = data[0]
            required_fields = ['id', 'prodotto', 'numero_lotto', 'data_produzione']
            for field in required_fields:
                assert field in lotto, f"Missing field: {field}"
            print(f"✓ Lotto structure verified: {lotto.get('numero_lotto', 'N/A')}")
            print(f"  - prodotto: {lotto.get('prodotto', 'N/A')}")
            print(f"  - data_produzione: {lotto.get('data_produzione', 'N/A')}")
            if lotto.get('frigo_numero'):
                print(f"  - frigo_numero: {lotto.get('frigo_numero')}")
        else:
            pytest.skip("No lotti available to test structure")
    
    def test_lotti_with_date_filter(self):
        """Test lotti with date filter"""
        response = requests.get(f"{BASE_URL}/api/lotti", params={"data_da": "2025-01-01"})
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Lotti with date filter: {len(data)} results")


class TestLottiRecall:
    """Test Lotti Recall - GET /api/lotti/recall/cerca"""
    
    def test_recall_endpoint_returns_200(self):
        """Verify recall endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/lotti/recall/cerca", params={"ingrediente": "farina"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/lotti/recall/cerca returned 200")
    
    def test_recall_returns_structure(self):
        """Verify recall returns proper structure"""
        response = requests.get(f"{BASE_URL}/api/lotti/recall/cerca", params={"ingrediente": "farina", "mesi": 6})
        assert response.status_code == 200
        data = response.json()
        
        assert "ingrediente_cercato" in data, "Missing ingrediente_cercato"
        assert "totale_lotti" in data, "Missing totale_lotti"
        assert "lotti" in data, "Missing lotti"
        
        print(f"✓ Recall structure verified")
        print(f"  - ingrediente_cercato: {data.get('ingrediente_cercato')}")
        print(f"  - totale_lotti: {data.get('totale_lotti')}")
    
    def test_recall_with_mesi_parameter(self):
        """Test recall with different mesi parameter"""
        response = requests.get(f"{BASE_URL}/api/lotti/recall/cerca", params={"ingrediente": "olio", "mesi": 12})
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Recall with 12 mesi: {data.get('totale_lotti', 0)} lotti found")


class TestReportHACCP:
    """Test Report HACCP Mensile - GET /api/report-haccp/mensile"""
    
    def test_report_haccp_returns_200(self):
        """Verify report HACCP endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/report-haccp/mensile", params={"anno": 2025, "mese": 1})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/report-haccp/mensile returned 200")
    
    def test_report_haccp_returns_html(self):
        """Verify report returns HTML content"""
        response = requests.get(f"{BASE_URL}/api/report-haccp/mensile", params={"anno": 2025, "mese": 1})
        assert response.status_code == 200
        content_type = response.headers.get('content-type', '')
        assert 'text/html' in content_type, f"Expected text/html, got {content_type}"
        print(f"✓ Report returns HTML content")
    
    def test_report_haccp_contains_data(self):
        """Verify report HTML contains expected sections"""
        response = requests.get(f"{BASE_URL}/api/report-haccp/mensile", params={"anno": 2025, "mese": 1})
        assert response.status_code == 200
        html = response.text
        
        # Check for key sections
        assert "REGISTRO HACCP MENSILE" in html, "Missing title"
        assert "Temperature Positive" in html or "Monitoraggio Temperature" in html, "Missing temperature section"
        assert "Sanificazione" in html or "Piano di Sanificazione" in html, "Missing sanificazione section"
        
        print(f"✓ Report HTML contains expected sections")
        print(f"  - HTML length: {len(html)} chars")


class TestStoricoProduzioni:
    """Test Storico Produzioni - GET /api/produzioni/"""
    
    def test_produzioni_endpoint_returns_200(self):
        """Verify produzioni endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/produzioni/")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/produzioni/ returned 200")
    
    def test_produzioni_returns_list(self):
        """Verify produzioni returns a list"""
        response = requests.get(f"{BASE_URL}/api/produzioni/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"✓ Returned {len(data)} produzioni")
    
    def test_produzioni_structure(self):
        """Verify produzione has required fields"""
        response = requests.get(f"{BASE_URL}/api/produzioni/")
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            prod = data[0]
            required_fields = ['id', 'ricetta_nome', 'pezzi', 'data']
            for field in required_fields:
                assert field in prod, f"Missing field: {field}"
            print(f"✓ Produzione structure verified")
            print(f"  - ricetta_nome: {prod.get('ricetta_nome', 'N/A')}")
            print(f"  - pezzi: {prod.get('pezzi', 0)}")
            print(f"  - costo_totale: €{prod.get('costo_totale', 0):.2f}")
        else:
            pytest.skip("No produzioni available to test structure")
    
    def test_produzioni_trend(self):
        """Test produzioni trend endpoint"""
        response = requests.get(f"{BASE_URL}/api/produzioni/trend", params={"giorni": 30})
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Expected list response"
        print(f"✓ Produzioni trend: {len(data)} data points")


class TestBackup:
    """Test Backup & Restore - GET /api/backup/lista"""
    
    def test_backup_lista_returns_200(self):
        """Verify backup lista endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/backup/lista")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/backup/lista returned 200")
    
    def test_backup_lista_structure(self):
        """Verify backup lista returns proper structure"""
        response = requests.get(f"{BASE_URL}/api/backup/lista")
        assert response.status_code == 200
        data = response.json()
        
        assert "backup" in data, "Missing backup field"
        assert "totale" in data, "Missing totale field"
        
        print(f"✓ Backup lista structure verified")
        print(f"  - totale: {data.get('totale', 0)} backup disponibili")
        
        if data.get('backup') and len(data['backup']) > 0:
            backup = data['backup'][0]
            print(f"  - ultimo backup: {backup.get('file', 'N/A')}")
            print(f"  - dimensione: {backup.get('dimensione', 'N/A')}")
    
    def test_backup_stato(self):
        """Test backup stato endpoint"""
        response = requests.get(f"{BASE_URL}/api/backup/stato")
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Backup stato: {data.get('stato', 'N/A')}")


class TestRicette:
    """Test Ricette base endpoint"""
    
    def test_ricette_endpoint_returns_200(self):
        """Verify ricette endpoint returns 200"""
        response = requests.get(f"{BASE_URL}/api/ricette")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print(f"✓ GET /api/ricette returned 200")
    
    def test_ricette_count_expected(self):
        """Verify ricette count is approximately 85 as expected"""
        response = requests.get(f"{BASE_URL}/api/ricette")
        assert response.status_code == 200
        data = response.json()
        # Expected ~85 ricette
        assert len(data) >= 50, f"Expected at least 50 ricette, got {len(data)}"
        print(f"✓ Ricette count: {len(data)} (expected ~85)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
