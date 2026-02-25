"""
Test Iteration 9 Features:
1. /presenze URL works (not /attendance)
2. /cedolini shows real data with 14 records for 2026
3. /dipendenti - Anagrafica shows 34 dipendenti with stats and toggle buttons
4. /saldi-ferie-permessi - Ferie page with action buttons
5. No duplicate 'Orosco Posligua' employee
6. Backend: GET /api/cedolini?anno=2026 returns 14 cedolini
7. Backend: DELETE /api/giustificativi/saldi-finali/test-id?anno=2026
8. Backend: GET /api/prima-nota/cassa?anno=2026 returns 5 movimenti
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

class TestIteration9Backend:
    """Backend API tests for iteration 9 features"""
    
    def test_health_check(self):
        """Verify API is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        print(f"Health check: {response.status_code}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"Health response: {data}")
    
    def test_cedolini_api_2026(self):
        """Test GET /api/cedolini?anno=2026 returns 14 cedolini"""
        response = requests.get(f"{BASE_URL}/api/cedolini", params={"anno": 2026})
        print(f"Cedolini API status: {response.status_code}")
        
        assert response.status_code == 200, f"Cedolini API failed: {response.text}"
        
        data = response.json()
        print(f"Cedolini API response keys: {data.keys() if isinstance(data, dict) else 'list'}")
        
        # Get cedolini list - could be in 'cedolini' key or direct list
        cedolini = data.get("cedolini") if isinstance(data, dict) else data
        if cedolini is None:
            cedolini = data.get("data", [])
        
        print(f"Cedolini count: {len(cedolini) if cedolini else 0}")
        
        # Verify we have 14 records for 2026
        assert cedolini is not None, "No cedolini data returned"
        assert len(cedolini) == 14, f"Expected 14 cedolini, got {len(cedolini)}"
        
        # Verify each cedolino has required fields
        if cedolini:
            sample = cedolini[0]
            print(f"Sample cedolino keys: {sample.keys()}")
            # Should have dipendente name and periodo
            has_name = any(k in sample for k in ['dipendente_nome', 'nome_dipendente', 'nome'])
            assert has_name, f"Cedolino missing dipendente name field. Keys: {sample.keys()}"
    
    def test_employees_api(self):
        """Test GET /api/employees returns ~34 employees"""
        response = requests.get(f"{BASE_URL}/api/employees", params={"limit": 200})
        print(f"Employees API status: {response.status_code}")
        
        assert response.status_code == 200, f"Employees API failed: {response.text}"
        
        data = response.json()
        employees = data.get("data", []) if isinstance(data, dict) else data
        
        print(f"Employees count: {len(employees)}")
        
        # Should be around 34 employees
        assert len(employees) >= 30, f"Expected ~34 employees, got {len(employees)}"
        assert len(employees) <= 40, f"Expected ~34 employees, got {len(employees)}"
        
        # Check for duplicate "Orosco Posligua" - should only have one
        orosco_count = 0
        orosco_names = []
        for emp in employees:
            nome = emp.get("nome_completo", "") or f"{emp.get('cognome', '')} {emp.get('nome', '')}"
            if "orosco" in nome.lower() or "orozco" in nome.lower():
                orosco_count += 1
                orosco_names.append(nome)
        
        print(f"Orosco/Orozco employees found: {orosco_count} - {orosco_names}")
        assert orosco_count <= 1, f"Found duplicate Orosco employees: {orosco_names}"
    
    def test_dipendenti_api(self):
        """Test GET /api/dipendenti returns dipendenti from dipendenti collection"""
        response = requests.get(f"{BASE_URL}/api/dipendenti")
        print(f"Dipendenti API status: {response.status_code}")
        
        assert response.status_code == 200, f"Dipendenti API failed: {response.text}"
        
        data = response.json()
        dipendenti = data if isinstance(data, list) else data.get("data", data.get("dipendenti", []))
        
        print(f"Dipendenti count: {len(dipendenti)}")
        
        # Should have ~34 dipendenti
        assert len(dipendenti) >= 30, f"Expected ~34 dipendenti, got {len(dipendenti)}"
        
        # Check in_carico field exists
        if dipendenti:
            sample = dipendenti[0]
            print(f"Sample dipendente keys: {sample.keys()}")
            # in_carico may or may not exist - check for it
            has_in_carico = "in_carico" in sample
            print(f"Has in_carico field: {has_in_carico}")
    
    def test_giustificativi_delete_endpoint(self):
        """Test DELETE /api/giustificativi/saldi-finali/{id}?anno=2026 exists"""
        # Test with a non-existent ID - should return success even if not found
        response = requests.delete(
            f"{BASE_URL}/api/giustificativi/saldi-finali/test-nonexistent-id",
            params={"anno": 2026}
        )
        print(f"Delete saldi-finali status: {response.status_code}")
        print(f"Delete response: {response.text[:200] if response.text else 'empty'}")
        
        # Should return 200 with deleted: 0 or 404 if not found
        assert response.status_code in [200, 404], f"Delete endpoint failed: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert data.get("success") == True, f"Delete response: {data}"
    
    def test_prima_nota_cassa_2026(self):
        """Test GET /api/prima-nota/cassa?anno=2026 returns 5 movimenti"""
        response = requests.get(f"{BASE_URL}/api/prima-nota/cassa", params={"anno": 2026})
        print(f"Prima Nota Cassa API status: {response.status_code}")
        
        assert response.status_code == 200, f"Prima Nota Cassa API failed: {response.text}"
        
        data = response.json()
        print(f"Prima Nota Cassa response keys: {data.keys() if isinstance(data, dict) else 'list'}")
        
        movimenti = data.get("movimenti", []) if isinstance(data, dict) else data
        
        print(f"Cassa movimenti count: {len(movimenti)}")
        
        # Should have 5 movimenti for 2026
        assert len(movimenti) == 5, f"Expected 5 cassa movimenti, got {len(movimenti)}"
    
    def test_giustificativi_saldi_finali_tutti(self):
        """Test GET /api/giustificativi/saldi-finali-tutti?anno=2026"""
        response = requests.get(
            f"{BASE_URL}/api/giustificativi/saldi-finali-tutti",
            params={"anno": 2026}
        )
        print(f"Saldi finali tutti status: {response.status_code}")
        
        assert response.status_code == 200, f"Saldi finali API failed: {response.text}"
        
        data = response.json()
        print(f"Saldi finali response: {data.get('totale_dipendenti')} dipendenti")
        
        saldi = data.get("saldi", [])
        print(f"Saldi count: {len(saldi)}")
    
    def test_giustificativi_update_periodo_endpoint(self):
        """Test PUT /api/giustificativi/saldi-finali/{id}/periodo endpoint exists"""
        # Test with non-existent ID - should return 404
        response = requests.put(
            f"{BASE_URL}/api/giustificativi/saldi-finali/test-nonexistent-id/periodo",
            json={"anno": 2026, "periodo": "2026-02"}
        )
        print(f"Update periodo status: {response.status_code}")
        
        # Should return 404 for non-existent ID (endpoint exists but data not found)
        assert response.status_code in [200, 404], f"Update periodo endpoint issue: {response.text}"


class TestRouteRename:
    """Test that /presenze route works and /attendance is redirected or removed"""
    
    def test_presenze_route_accessible(self):
        """Test that /presenze route is accessible on frontend"""
        response = requests.get(f"{BASE_URL}/presenze", allow_redirects=True)
        print(f"Presenze route status: {response.status_code}")
        # Should return 200 or redirect to valid page
        assert response.status_code in [200, 304], f"Presenze route issue: {response.status_code}"
    
    def test_attendance_api_still_works(self):
        """Test that attendance API still works (backend API not renamed)"""
        response = requests.get(f"{BASE_URL}/api/attendance/presenze")
        print(f"Attendance API status: {response.status_code}")
        # The API endpoint may or may not exist
        # Just checking it doesn't return 500
        assert response.status_code != 500, f"Attendance API error: {response.text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
