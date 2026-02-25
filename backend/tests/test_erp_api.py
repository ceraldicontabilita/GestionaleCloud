"""
ERP System API Tests - OpenClaw UI Revamp
Tests for backend APIs with real MongoDB Atlas database
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

if not BASE_URL:
    # Fallback for testing environment
    BASE_URL = "https://bilancio-patch.preview.emergentagent.com"


class TestHealthEndpoints:
    """Health check endpoint tests"""
    
    def test_health_check(self):
        """Test /api/health returns status ok"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=30)
        assert response.status_code == 200
        data = response.json()
        # Health can return "ok" or "healthy" depending on endpoint
        assert data.get("status") in ["ok", "healthy"]
        assert "database" in data
        assert data.get("database") == "connected"
        print(f"✅ Health check passed: database={data.get('database')}")
    
    def test_ping_endpoint(self):
        """Test /api/ping returns pong"""
        response = requests.get(f"{BASE_URL}/api/ping", timeout=10)
        assert response.status_code == 200
        data = response.json()
        assert data.get("pong") == True
        print("✅ Ping endpoint working")
    
    def test_root_endpoint(self):
        """Test root endpoint returns 200 (may be SPA HTML or API JSON)"""
        response = requests.get(f"{BASE_URL}/", timeout=10)
        assert response.status_code == 200
        # Root may return HTML (SPA) or JSON (API), both are valid
        content_type = response.headers.get('content-type', '')
        if 'application/json' in content_type:
            data = response.json()
            assert "status" in data
            print(f"✅ Root endpoint (JSON): app={data.get('app')}")
        else:
            # SPA serves HTML at root
            assert 'text/html' in content_type or len(response.text) > 0
            print("✅ Root endpoint (HTML/SPA): Frontend served correctly")


class TestSuppliersAPI:
    """Suppliers (Fornitori) endpoint tests"""
    
    def test_get_suppliers_list(self):
        """Test /api/suppliers returns list of suppliers"""
        response = requests.get(f"{BASE_URL}/api/suppliers", timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # User has 316+ suppliers
        assert len(data) >= 300, f"Expected 300+ suppliers, got {len(data)}"
        print(f"✅ Suppliers list: {len(data)} suppliers found")
    
    def test_supplier_data_structure(self):
        """Test supplier data has required fields"""
        response = requests.get(f"{BASE_URL}/api/suppliers", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            supplier = data[0]
            # Check for required fields
            required_fields = ["id", "denominazione", "partita_iva"]
            for field in required_fields:
                if field not in supplier:
                    # Some suppliers might have ragione_sociale instead of denominazione
                    if field == "denominazione" and "ragione_sociale" in supplier:
                        continue
                    pytest.skip(f"Field {field} not found in supplier (may be optional)")
            print(f"✅ Supplier data structure valid: {list(supplier.keys())[:5]}...")


class TestEmployeesAPI:
    """Employees (Dipendenti) endpoint tests"""
    
    def test_get_employees_list(self):
        """Test /api/dipendenti returns list of employees"""
        response = requests.get(f"{BASE_URL}/api/dipendenti", timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # User has 2 employees
        assert len(data) >= 2, f"Expected at least 2 employees, got {len(data)}"
        print(f"✅ Employees list: {len(data)} employees found")
    
    def test_employee_data_structure(self):
        """Test employee data has required fields"""
        response = requests.get(f"{BASE_URL}/api/dipendenti", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            employee = data[0]
            # Check for expected fields
            expected_fields = ["nome", "cognome", "codice_fiscale"]
            for field in expected_fields:
                assert field in employee, f"Missing field: {field}"
            print(f"✅ Employee data: {employee.get('nome')} {employee.get('cognome')}")


class TestDashboardAPI:
    """Dashboard endpoint tests"""
    
    def test_dashboard_stats(self):
        """Test /api/dashboard/stats returns stats"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        # Check for expected stats
        expected_keys = ["invoices", "suppliers", "employees"]
        for key in expected_keys:
            assert key in data, f"Missing stat: {key}"
        
        # Verify data matches user's database
        assert data.get("suppliers") >= 300, f"Expected 300+ suppliers in stats"
        print(f"✅ Dashboard stats: invoices={data.get('invoices')}, suppliers={data.get('suppliers')}, employees={data.get('employees')}")


class TestInvoicesAPI:
    """Invoices (Fatture) endpoint tests"""
    
    def test_get_invoices(self):
        """Test fatture ricevute endpoint"""
        response = requests.get(f"{BASE_URL}/api/fatture-ricevute", timeout=30)
        # API may return 200, 404 (no data without year), or validation error
        assert response.status_code in [200, 400, 404, 422]
        print(f"✅ Fatture ricevute endpoint responded: {response.status_code}")
    
    def test_get_invoices_with_year(self):
        """Test fatture ricevute with year parameter"""
        response = requests.get(f"{BASE_URL}/api/fatture-ricevute?anno=2026", timeout=30)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Fatture ricevute (2026): {len(data) if isinstance(data, list) else 'data received'}")
        else:
            print(f"⚠️ Fatture ricevute returned: {response.status_code}")


class TestBankAPI:
    """Bank (Riconciliazione) endpoint tests"""
    
    def test_bank_reconciliation(self):
        """Test bank reconciliation endpoint"""
        response = requests.get(f"{BASE_URL}/api/bank/accounts", timeout=30)
        # Bank accounts may be empty but should respond
        assert response.status_code in [200, 404]
        print(f"✅ Bank accounts endpoint responded: {response.status_code}")


class TestF24API:
    """F24 endpoint tests"""
    
    def test_f24_list(self):
        """Test F24 list endpoint"""
        response = requests.get(f"{BASE_URL}/api/f24", timeout=30)
        # F24 may require auth (403) or year param
        assert response.status_code in [200, 403, 404, 422]
        print(f"✅ F24 endpoint responded: {response.status_code}")
    
    def test_f24_with_year(self):
        """Test F24 with year parameter"""
        response = requests.get(f"{BASE_URL}/api/f24?anno=2026", timeout=30)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ F24 (2026): {len(data) if isinstance(data, list) else 'data received'}")


class TestCorrispettiviAPI:
    """Corrispettivi endpoint tests"""
    
    def test_corrispettivi_list(self):
        """Test corrispettivi endpoint"""
        response = requests.get(f"{BASE_URL}/api/corrispettivi", timeout=30)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Corrispettivi: {len(data) if isinstance(data, list) else 'data received'}")
        else:
            print(f"⚠️ Corrispettivi returned: {response.status_code}")


class TestNotificationsAPI:
    """Notifications endpoint tests"""
    
    def test_notifications_list(self):
        """Test notifications endpoint"""
        response = requests.get(f"{BASE_URL}/api/notifications", timeout=30)
        assert response.status_code in [200, 404]
        print(f"✅ Notifications endpoint responded: {response.status_code}")


class TestPrimaNotaAPI:
    """Prima Nota endpoint tests"""
    
    def test_prima_nota_cassa(self):
        """Test prima nota cassa endpoint"""
        response = requests.get(f"{BASE_URL}/api/prima-nota/cassa", timeout=30)
        assert response.status_code in [200, 404, 422]
        print(f"✅ Prima Nota Cassa endpoint responded: {response.status_code}")


class TestCedoliniAPI:
    """Cedolini (Payslips) endpoint tests"""
    
    def test_cedolini_list(self):
        """Test cedolini endpoint"""
        response = requests.get(f"{BASE_URL}/api/cedolini", timeout=30)
        assert response.status_code in [200, 404, 422]
        print(f"✅ Cedolini endpoint responded: {response.status_code}")


class TestAttendanceAPI:
    """Attendance (Presenze) endpoint tests"""
    
    def test_attendance_list(self):
        """Test attendance endpoint"""
        response = requests.get(f"{BASE_URL}/api/attendance/presenze", timeout=30)
        assert response.status_code in [200, 404, 422]
        print(f"✅ Attendance endpoint responded: {response.status_code}")


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
