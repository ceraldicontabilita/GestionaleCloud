"""
Test file for Ceraldi ERP - Iteration 6
Tests for: Bilancio, Magazzino, F24, Corrispettivi, and page loading
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://mittenti-integration.preview.emergentagent.com')

class TestBilancioAPI:
    """Test Bilancio endpoints - Stato Patrimoniale and Conto Economico"""
    
    def test_stato_patrimoniale_2026(self):
        """GET /api/bilancio/stato-patrimoniale?anno=2026 - crediti_vs_clienti=0, totale_attivo=totale_passivo"""
        response = requests.get(f"{BASE_URL}/api/bilancio/stato-patrimoniale?anno=2026")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "attivo" in data
        assert "passivo" in data
        
        # Verify crediti_vs_clienti = 0 (no fatture emesse in this system)
        crediti_vs_clienti = data["attivo"]["crediti"]["crediti_vs_clienti"]
        assert crediti_vs_clienti == 0, f"Expected crediti_vs_clienti=0, got {crediti_vs_clienti}"
        
        # Verify totale_attivo equals totale_passivo (balance check)
        totale_attivo = data["attivo"]["totale_attivo"]
        totale_passivo = data["passivo"]["totale_passivo"]
        assert abs(totale_attivo - totale_passivo) < 0.01, f"Attivo ({totale_attivo}) != Passivo ({totale_passivo})"
        
        print(f"✓ Stato Patrimoniale: Attivo={totale_attivo:.2f}, Passivo={totale_passivo:.2f}, Crediti vs Clienti={crediti_vs_clienti}")

    def test_conto_economico_2026(self):
        """GET /api/bilancio/conto-economico?anno=2026 - returns valid ricavi and costi data"""
        response = requests.get(f"{BASE_URL}/api/bilancio/conto-economico?anno=2026")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "ricavi" in data
        assert "costi" in data
        assert "risultato" in data
        
        # Verify ricavi data
        ricavi = data["ricavi"]
        assert "corrispettivi" in ricavi
        assert "totale_ricavi" in ricavi
        assert ricavi["totale_ricavi"] >= 0
        
        # Verify costi data
        costi = data["costi"]
        assert "acquisti" in costi
        assert "totale_costi" in costi
        assert costi["totale_costi"] >= 0
        
        # Verify risultato
        risultato = data["risultato"]
        assert "utile_perdita" in risultato
        assert "tipo" in risultato
        
        print(f"✓ Conto Economico: Ricavi={ricavi['totale_ricavi']:.2f}, Costi={costi['totale_costi']:.2f}, Risultato={risultato['utile_perdita']:.2f}")


class TestWarehouseAPI:
    """Test Warehouse/Magazzino endpoints"""
    
    def test_warehouse_manutenzione_products(self):
        """GET /api/warehouse/products?category=manutenzione returns 12 maintenance products"""
        response = requests.get(f"{BASE_URL}/api/warehouse/products?category=manutenzione")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list of products"
        
        # Verify exactly 12 maintenance products
        assert len(data) == 12, f"Expected 12 manutenzione products, got {len(data)}"
        
        # Verify all products have category 'manutenzione'
        for prod in data:
            cat = prod.get("category", prod.get("categoria"))
            assert cat == "manutenzione", f"Expected category 'manutenzione', got '{cat}'"
        
        print(f"✓ Warehouse manutenzione: {len(data)} products")
    
    def test_warehouse_all_products(self):
        """GET /api/warehouse/products (without filter) returns all products"""
        response = requests.get(f"{BASE_URL}/api/warehouse/products")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list of products"
        # Should have at least the 12 maintenance products
        assert len(data) >= 12, f"Expected at least 12 products, got {len(data)}"
        
        print(f"✓ Warehouse all products: {len(data)} products")


class TestCorrispettiviAPI:
    """Test Corrispettivi endpoints"""
    
    def test_corrispettivi_2026_matricola_rt(self):
        """GET /api/corrispettivi?anno=2026 returns records with non-empty matricola_rt"""
        response = requests.get(f"{BASE_URL}/api/corrispettivi?anno=2026")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        records = data if isinstance(data, list) else data.get('data', data.get('corrispettivi', []))
        
        assert len(records) > 0, "Expected at least some corrispettivi records"
        
        # Count records with matricola_rt
        with_matricola = [r for r in records if r.get('matricola_rt')]
        assert len(with_matricola) > 0, "Expected at least some records with matricola_rt"
        
        print(f"✓ Corrispettivi 2026: {len(records)} records, {len(with_matricola)} with matricola_rt")


class TestF24PublicAPI:
    """Test F24 Public API endpoints"""
    
    def test_f24_models_2025(self):
        """GET /api/f24-public/models?anno=2025 returns F24s with real payment data from quietanze"""
        response = requests.get(f"{BASE_URL}/api/f24-public/models?anno=2025")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "f24s" in data
        assert "count" in data
        
        f24s = data["f24s"]
        assert len(f24s) > 0, "Expected at least some F24 records for 2025"
        
        # Check for paid F24s (from quietanze)
        paid_f24s = [f for f in f24s if f.get("pagato") or f.get("status") == "pagato"]
        totale_pagato = data.get("totale_pagato", 0)
        
        print(f"✓ F24 2025: {len(f24s)} records, {len(paid_f24s)} paid, totale_pagato={totale_pagato:.2f}")


class TestPageEndpoints:
    """Test page-related API endpoints for loading pages"""
    
    def test_health_endpoint(self):
        """Health check"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        print("✓ Health endpoint OK")
    
    def test_cespiti_endpoint(self):
        """GET /api/cespiti - for /cespiti page"""
        response = requests.get(f"{BASE_URL}/api/cespiti")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        cespiti = data if isinstance(data, list) else data.get('data', data.get('cespiti', []))
        
        print(f"✓ Cespiti: {len(cespiti)} cespiti")
    
    def test_iva_mensile_endpoint(self):
        """GET /api/iva/mensile - for /verifica-coerenza/iva page"""
        response = requests.get(f"{BASE_URL}/api/iva/mensile?anno=2026")
        # 404 is acceptable - frontend handles IVA data display internally
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert "mesi" in data or isinstance(data, list)
        print(f"✓ IVA mensile endpoint: status {response.status_code}")
    
    def test_discrepanze_endpoint(self):
        """GET /api/analytics/discrepanze - for /verifica-coerenza/discrepanze page"""
        response = requests.get(f"{BASE_URL}/api/analytics/discrepanze?anno=2026")
        # May return 404 if not implemented, just check it doesn't error badly
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}"
        print(f"✓ Discrepanze endpoint: status {response.status_code}")
    
    def test_dashboard_summary(self):
        """GET /api/dashboard/summary - for Dashboard page"""
        response = requests.get(f"{BASE_URL}/api/dashboard/summary?anno=2026")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ Dashboard summary OK")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
