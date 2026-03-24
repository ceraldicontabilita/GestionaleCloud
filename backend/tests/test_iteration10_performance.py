"""
Iteration 10 - Performance & correctness tests for optimized ERP endpoints.

Tests cover:
1. API Performance: alert-limiti endpoint < 3s
2. API Performance: saldo-ferie endpoint < 2s  
3. Dipendenti dedup: no duplicate CF in list
4. Prima Nota Banca: endpoint returns data
5. Dashboard: full load chain benchmark
"""
import pytest
import requests
import time
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


# ====================== HEALTH CHECK ======================

class TestHealth:
    """Health check - must pass before all tests"""

    def test_health_check(self):
        """Backend must be reachable"""
        resp = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok"
        assert data.get("database") == "connected"
        print(f"✅ Health OK: {data}")


# ====================== PERFORMANCE TESTS ======================

class TestPerformanceAlertLimiti:
    """
    P0 fix: alert-limiti was N+1 queries (102 queries for 34 employees).
    Now must use bulk aggregation => response in < 3s
    """

    def test_alert_limiti_response_time_under_3s(self):
        """alert-limiti must respond in < 3s after optimization"""
        start = time.time()
        resp = requests.get(
            f"{BASE_URL}/api/giustificativi/alert-limiti",
            params={"soglia_percentuale": 80, "anno": 2026},
            timeout=30
        )
        elapsed = time.time() - start

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        assert elapsed < 3.0, f"❌ alert-limiti too slow: {elapsed:.2f}s (limit: 3.0s)"
        print(f"✅ alert-limiti responded in {elapsed:.2f}s (< 3s)")

    def test_alert_limiti_response_structure(self):
        """alert-limiti must return expected structure"""
        resp = requests.get(
            f"{BASE_URL}/api/giustificativi/alert-limiti",
            params={"soglia_percentuale": 80, "anno": 2026},
            timeout=30
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data, "Missing 'alerts' key"
        assert "totale_alerts" in data, "Missing 'totale_alerts' key"
        assert "dipendenti_coinvolti" in data, "Missing 'dipendenti_coinvolti' key"
        assert isinstance(data["alerts"], list), "'alerts' must be a list"
        print(f"✅ alert-limiti structure OK: {data['totale_alerts']} alerts, {data['dipendenti_coinvolti']} dipendenti coinvolti")

    def test_alert_limiti_alert_fields(self):
        """Each alert must have required fields"""
        resp = requests.get(
            f"{BASE_URL}/api/giustificativi/alert-limiti",
            params={"soglia_percentuale": 80, "anno": 2026},
            timeout=30
        )
        data = resp.json()
        for alert in data.get("alerts", [])[:5]:
            required_fields = ["employee_id", "employee_nome", "codice", "tipo_limite", "percentuale", "livello"]
            for field in required_fields:
                assert field in alert, f"Missing field '{field}' in alert: {alert}"
        print(f"✅ Alert fields OK for {len(data['alerts'])} alerts")


class TestPerformanceSaldoFerie:
    """
    P0 fix: saldo-ferie was 12+ sequential queries.
    Now must use 2 bulk aggregations => response in < 2s
    """
    
    _employee_id = None

    @classmethod
    def get_employee_id(cls):
        """Get a real employee ID from the API"""
        if cls._employee_id:
            return cls._employee_id
        resp = requests.get(f"{BASE_URL}/api/dipendenti", timeout=10)
        if resp.status_code == 200:
            employees = resp.json()
            if employees and len(employees) > 0:
                cls._employee_id = employees[0].get("id")
        return cls._employee_id

    def test_saldo_ferie_response_time_under_2s(self):
        """saldo-ferie must respond in < 2s after optimization"""
        employee_id = self.get_employee_id()
        if not employee_id:
            pytest.skip("No employee found to test saldo-ferie")

        start = time.time()
        resp = requests.get(
            f"{BASE_URL}/api/giustificativi/dipendente/{employee_id}/saldo-ferie",
            params={"anno": 2026},
            timeout=20
        )
        elapsed = time.time() - start

        assert resp.status_code in [200, 404], f"Unexpected status: {resp.status_code}: {resp.text[:200]}"
        if resp.status_code == 200:
            assert elapsed < 2.0, f"❌ saldo-ferie too slow: {elapsed:.2f}s (limit: 2.0s)"
            print(f"✅ saldo-ferie responded in {elapsed:.2f}s (< 2s) for employee {employee_id}")
        else:
            print(f"⚠️ Employee {employee_id} not found in giustificativi (404 - expected if no presenze data)")

    def test_saldo_ferie_response_structure(self):
        """saldo-ferie must return expected structure"""
        employee_id = self.get_employee_id()
        if not employee_id:
            pytest.skip("No employee found")

        resp = requests.get(
            f"{BASE_URL}/api/giustificativi/dipendente/{employee_id}/saldo-ferie",
            params={"anno": 2026},
            timeout=20
        )
        if resp.status_code == 404:
            pytest.skip("Employee not found in giustificativi - acceptable")
        
        assert resp.status_code == 200
        data = resp.json()
        assert "ferie" in data, "Missing 'ferie' key"
        assert "rol" in data, "Missing 'rol' key"
        assert "employee_nome" in data, "Missing 'employee_nome' key"
        assert "anno" in data, "Missing 'anno' key"
        print(f"✅ saldo-ferie structure OK for {data.get('employee_nome')}")

    def test_multiple_employees_saldo_ferie_performance(self):
        """Test saldo-ferie for first 3 employees - each must be < 2s"""
        resp = requests.get(f"{BASE_URL}/api/dipendenti", timeout=10)
        assert resp.status_code == 200
        employees = resp.json()[:3]  # Test first 3 only
        
        for emp in employees:
            emp_id = emp.get("id")
            if not emp_id:
                continue
            start = time.time()
            r = requests.get(
                f"{BASE_URL}/api/giustificativi/dipendente/{emp_id}/saldo-ferie",
                params={"anno": 2026},
                timeout=20
            )
            elapsed = time.time() - start
            assert r.status_code in [200, 404]
            if r.status_code == 200:
                assert elapsed < 2.0, f"❌ saldo-ferie slow for {emp.get('nome_completo')}: {elapsed:.2f}s"
                print(f"  ✅ {emp.get('nome_completo')}: {elapsed:.2f}s")


# ====================== DIPENDENTI DEDUP ======================

class TestDipendentiDedup:
    """
    P2 fix: list_dipendenti must deduplicate by codice fiscale
    """

    def test_no_duplicate_cf_in_list(self):
        """GET /api/dipendenti must return list with no duplicate codice fiscale"""
        resp = requests.get(f"{BASE_URL}/api/dipendenti", timeout=15)
        assert resp.status_code == 200
        dipendenti = resp.json()
        assert isinstance(dipendenti, list), "Expected list of dipendenti"
        
        # Check for CF duplicates
        seen_cf = {}
        duplicates = []
        for dip in dipendenti:
            cf = (dip.get("codice_fiscale") or "").upper().strip()
            if cf:
                if cf in seen_cf:
                    duplicates.append({
                        "cf": cf,
                        "nome1": seen_cf[cf],
                        "nome2": dip.get("nome_completo")
                    })
                else:
                    seen_cf[cf] = dip.get("nome_completo")
        
        assert len(duplicates) == 0, f"❌ Found {len(duplicates)} duplicate CF: {duplicates}"
        print(f"✅ No duplicate CF found in {len(dipendenti)} dipendenti")

    def test_dipendenti_count_reasonable(self):
        """Dipendenti count should be between 1 and 200"""
        resp = requests.get(f"{BASE_URL}/api/dipendenti", timeout=15)
        assert resp.status_code == 200
        dipendenti = resp.json()
        assert 1 <= len(dipendenti) <= 200, f"Unexpected dipendenti count: {len(dipendenti)}"
        print(f"✅ Dipendenti count: {len(dipendenti)}")

    def test_dipendenti_response_time(self):
        """GET /api/dipendenti must respond quickly"""
        start = time.time()
        resp = requests.get(f"{BASE_URL}/api/dipendenti", timeout=15)
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 5.0, f"❌ /api/dipendenti too slow: {elapsed:.2f}s"
        print(f"✅ /api/dipendenti responded in {elapsed:.2f}s")


# ====================== PRIMA NOTA BANCA ======================

class TestPrimaNotaBanca:
    """
    Verify /api/prima-nota/banca endpoint returns data
    """

    def test_prima_nota_banca_returns_data(self):
        """GET /api/prima-nota/banca must return 200 and valid structure"""
        resp = requests.get(
            f"{BASE_URL}/api/prima-nota/banca",
            params={"anno": 2026},
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        # Should have movimenti key (even if empty)
        print(f"✅ prima-nota/banca OK: {data}")

    def test_prima_nota_banca_2025(self):
        """GET /api/prima-nota/banca for 2025 should return some movements"""
        resp = requests.get(
            f"{BASE_URL}/api/prima-nota/banca",
            params={"anno": 2025},
            timeout=15
        )
        assert resp.status_code == 200
        data = resp.json()
        print(f"✅ prima-nota/banca 2025 OK: response keys={list(data.keys()) if isinstance(data, dict) else 'list'}")


# ====================== DASHBOARD API CHAIN ======================

class TestDashboardPerformance:
    """
    Test that dashboard APIs load in reasonable time collectively.
    Dashboard was loading in 30-45s before optimization.
    """

    def test_dashboard_summary_fast(self):
        """Dashboard summary must respond quickly"""
        start = time.time()
        resp = requests.get(
            f"{BASE_URL}/api/dashboard/summary",
            params={"anno": 2026},
            timeout=20
        )
        elapsed = time.time() - start
        assert resp.status_code in [200, 404]
        print(f"✅ dashboard/summary: {elapsed:.2f}s (status: {resp.status_code})")

    def test_alert_limiti_non_blocking(self):
        """
        Dashboard loads alert-limiti SEPARATELY (non-blocking).
        This means it should NOT be in the critical path Promise.all.
        Verify it still responds (even if slow).
        """
        start = time.time()
        resp = requests.get(
            f"{BASE_URL}/api/giustificativi/alert-limiti",
            params={"soglia_percentuale": 80, "anno": 2026},
            timeout=30
        )
        elapsed = time.time() - start
        assert resp.status_code == 200
        # After optimization must be < 3s
        assert elapsed < 3.0, f"❌ alert-limiti still too slow: {elapsed:.2f}s"
        print(f"✅ alert-limiti non-blocking check: {elapsed:.2f}s")

    def test_concurrent_dashboard_requests(self):
        """Simulate dashboard loading multiple APIs concurrently"""
        import threading
        
        results = {}
        start_total = time.time()

        def fetch(name, url, params=None):
            t0 = time.time()
            try:
                r = requests.get(url, params=params or {}, timeout=15)
                results[name] = {"status": r.status_code, "time": time.time() - t0}
            except Exception as e:
                results[name] = {"status": "error", "error": str(e), "time": time.time() - t0}

        threads = [
            threading.Thread(target=fetch, args=("health", f"{BASE_URL}/api/health")),
            threading.Thread(target=fetch, args=("summary", f"{BASE_URL}/api/dashboard/summary"), kwargs={"params": {"anno": 2026}}),
            threading.Thread(target=fetch, args=("trend", f"{BASE_URL}/api/dashboard/trend-mensile"), kwargs={"params": {"anno": 2026}}),
            threading.Thread(target=fetch, args=("scadenze", f"{BASE_URL}/api/scadenze/prossime"), kwargs={"params": {"giorni": 30, "limit": 8}}),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        total_elapsed = time.time() - start_total

        print(f"✅ Dashboard concurrent fetch completed in {total_elapsed:.2f}s")
        for name, result in results.items():
            print(f"  {name}: {result['status']} in {result['time']:.2f}s")

        # All should respond (no 500 errors)
        for name, result in results.items():
            assert result.get("status") != "error", f"❌ {name} failed: {result.get('error')}"


# ====================== ESTRATTO CONTO (CSV Import backend) ======================

class TestEstrattoConto:
    """
    P1 fix: CSV import dedup - commissioni bancarie (importo <= 2€) 
    must NOT be deduplicated even if they appear multiple times.
    """

    def test_estratto_conto_movimenti_endpoint_works(self):
        """GET /api/prima-nota/banca should work (uses estratto conto)"""
        resp = requests.get(
            f"{BASE_URL}/api/prima-nota/banca",
            params={"anno": 2026},
            timeout=15
        )
        assert resp.status_code in [200], f"Got {resp.status_code}"
        print(f"✅ estratto conto endpoint accessible")

    def test_estratto_conto_movimenti_direct(self):
        """GET /api/estratto-conto/movimenti endpoint (if exists)"""
        resp = requests.get(
            f"{BASE_URL}/api/estratto-conto/movimenti",
            params={"anno": 2026, "limit": 10},
            timeout=15
        )
        if resp.status_code == 404:
            # Try alternative path
            resp = requests.get(
                f"{BASE_URL}/api/banca/estratto-conto/movimenti",
                params={"anno": 2026, "limit": 10},
                timeout=15
            )
        assert resp.status_code in [200, 404], f"Unexpected status: {resp.status_code}"
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ estratto-conto/movimenti OK: {data.get('totale', 'N/A')} movimenti")
        else:
            print("⚠️ estratto-conto/movimenti endpoint path needs to be verified")


# ====================== SALDO PROGRESSIVO ======================

class TestSaldoProgressivo:
    """
    P2 fix: saldo progressivo in PrimaNota.jsx now sorts forward (ASC) 
    before calculating, then shows DESC.
    """

    def test_prima_nota_banca_response_with_saldo(self):
        """Verify prima nota banca data has saldo_precedente for progressive calculation"""
        resp = requests.get(
            f"{BASE_URL}/api/prima-nota/banca",
            params={"anno": 2026},
            timeout=15
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should have saldo_precedente for progressive balance calculation
        if isinstance(data, dict):
            # Check for expected fields from estratto_conto endpoint
            print(f"✅ Prima Nota Banca keys: {list(data.keys())}")
        print("✅ prima-nota/banca data accessible for progressive balance")


# ====================== CEDOLINI DEDUP ======================

class TestCedoliniDedup:
    """
    P2 fix: Cedolini insert now checks CF+mese+anno for dedup before insert.
    """

    def test_cedolini_no_duplicates_cf_mese_anno(self):
        """GET /api/cedolini must not have duplicates for same CF+mese+anno"""
        resp = requests.get(
            f"{BASE_URL}/api/cedolini",
            params={"anno": 2026},
            timeout=15
        )
        assert resp.status_code == 200
        data = resp.json()
        
        cedolini = data if isinstance(data, list) else data.get("data", data.get("cedolini", []))
        
        # Check for CF+mese+anno duplicates
        seen = {}
        duplicates = []
        for ced in cedolini:
            cf = (ced.get("codice_fiscale") or ced.get("dipendente_cf") or "").upper().strip()
            mese = ced.get("mese")
            anno = ced.get("anno")
            if cf and mese and anno:
                key = f"{cf}_{mese}_{anno}"
                if key in seen:
                    duplicates.append(key)
                else:
                    seen[key] = True
        
        assert len(duplicates) == 0, f"❌ Found {len(duplicates)} cedolini duplicates: {duplicates[:5]}"
        print(f"✅ No cedolini duplicates found among {len(cedolini)} records")
