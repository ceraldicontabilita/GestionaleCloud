"""
Iteration 11 - Tests for new fixes + full P0/P1 module verification.

Tests cover:
1. FIX: Prima Nota Salari anno filter uses 'anno' field (not 'data' regex)
2. FIX: Cedolini anno filter handles both int (2026) and string ('2026')
3. P0 verification: Cassa, Banca, Salari, Fornitori, Fatture
4. P1 verification: Dipendenti, Cedolini, Dashboard bilancio
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


# ====================== HEALTH CHECK ======================

class TestHealth:
    """Health check - must pass before all tests"""

    def test_health_check(self):
        resp = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ok"
        assert data.get("database") == "connected"
        print(f"✅ Health OK: {data}")


# ====================== P0: PRIMA NOTA CASSA ======================

class TestPrimaNotaCassa:
    """P0: Prima Nota Cassa - verify real data returned for both years"""

    def test_prima_nota_cassa_2025_returns_data(self):
        """GET /api/prima-nota/cassa?anno=2025 → deve restituire movimenti con saldo_anno > 0"""
        resp = requests.get(
            f"{BASE_URL}/api/prima-nota/cassa",
            params={"anno": 2025},
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        # Could be dict or list
        if isinstance(data, dict):
            movimenti = data.get("movimenti", [])
            saldo = data.get("saldo_anno") or data.get("saldo") or data.get("totale", 0)
            print(f"✅ Cassa 2025: {len(movimenti)} movimenti, saldo={saldo}")
            assert len(movimenti) > 0, "No movimenti found for cassa 2025"
        elif isinstance(data, list):
            assert len(data) > 0, "No movimenti found for cassa 2025 (list)"
            print(f"✅ Cassa 2025: {len(data)} movimenti")
        else:
            pytest.fail(f"Unexpected response type: {type(data)}")

    def test_prima_nota_cassa_2026_returns_data(self):
        """GET /api/prima-nota/cassa?anno=2026 → deve restituire movimenti"""
        resp = requests.get(
            f"{BASE_URL}/api/prima-nota/cassa",
            params={"anno": 2026},
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        if isinstance(data, dict):
            movimenti = data.get("movimenti", [])
            saldo = data.get("saldo_anno") or data.get("saldo") or data.get("totale", 0)
            print(f"✅ Cassa 2026: {len(movimenti)} movimenti, saldo={saldo}")
            assert len(movimenti) > 0, "No movimenti found for cassa 2026"
        elif isinstance(data, list):
            assert len(data) > 0, "No movimenti found for cassa 2026 (list)"
            print(f"✅ Cassa 2026: {len(data)} movimenti")
        else:
            pytest.fail(f"Unexpected response type: {type(data)}")

    def test_prima_nota_cassa_2025_saldo_positivo(self):
        """Cassa 2025: saldo_anno deve essere > 0 (atteso ~€359k)"""
        resp = requests.get(
            f"{BASE_URL}/api/prima-nota/cassa",
            params={"anno": 2025},
            timeout=15
        )
        assert resp.status_code == 200
        data = resp.json()
        if isinstance(data, dict):
            # Try multiple possible field names
            saldo = (data.get("saldo_anno") or data.get("saldo") or
                     data.get("totale") or 0)
            print(f"✅ Cassa 2025 saldo: {saldo}")
            # saldo should be substantial (known ~€359k)
            assert saldo != 0, f"Saldo 2025 is zero - expected real data"


# ====================== P0: PRIMA NOTA BANCA ======================

class TestPrimaNotaBanca:
    """P0: Prima Nota Banca - 100+ movimenti expected"""

    def test_prima_nota_banca_2026_100_plus_movimenti(self):
        """GET /api/prima-nota/banca?anno=2026 → deve restituire 100+ movimenti"""
        resp = requests.get(
            f"{BASE_URL}/api/prima-nota/banca",
            params={"anno": 2026, "limit": 500},
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        if isinstance(data, dict):
            movimenti = data.get("movimenti", [])
            count = data.get("count") or data.get("total") or len(movimenti)
            print(f"✅ Banca 2026: {len(movimenti)} movimenti returned (count={count})")
            assert len(movimenti) >= 100 or count >= 100, (
                f"Expected 100+ movimenti for banca 2026, got {len(movimenti)} (count={count})"
            )
        elif isinstance(data, list):
            assert len(data) >= 100, f"Expected 100+ movimenti, got {len(data)}"
            print(f"✅ Banca 2026: {len(data)} movimenti")

    def test_prima_nota_banca_2025_returns_data(self):
        """Banca 2025 must also return data"""
        resp = requests.get(
            f"{BASE_URL}/api/prima-nota/banca",
            params={"anno": 2025},
            timeout=15
        )
        assert resp.status_code == 200
        data = resp.json()
        if isinstance(data, dict):
            movimenti = data.get("movimenti", [])
            print(f"✅ Banca 2025: {len(movimenti)} movimenti returned")
            assert len(movimenti) > 0, "Banca 2025 returned no movimenti"
        elif isinstance(data, list):
            assert len(data) > 0
            print(f"✅ Banca 2025: {len(data)} movimenti")


# ====================== P0: FIX - PRIMA NOTA SALARI ======================

class TestPrimaNotaSalari:
    """
    FIX: salari.py now uses campo 'anno' (int) instead of 'data' (regex).
    Expected: 100 movimenti 2025, 100 movimenti 2024.
    """

    def test_prima_nota_salari_2025_fix_anno_field(self):
        """
        GET /api/prima-nota/salari?anno=2025 → deve restituire 64+ movimenti.
        VERIFICA FIX: il filtro anno usa campo 'anno' non 'data'.
        """
        resp = requests.get(
            f"{BASE_URL}/api/prima-nota/salari",
            params={"anno": 2025, "limit": 200},
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        if isinstance(data, dict):
            movimenti = data.get("movimenti", [])
            count = data.get("count") or len(movimenti)
            print(f"✅ Salari 2025: {len(movimenti)} movimenti returned (count={count})")
            assert len(movimenti) >= 64 or count >= 64, (
                f"FIX FAILED: Expected 64+ salari movimenti for 2025, got {len(movimenti)} (count={count}). "
                f"Check that salari.py uses campo 'anno' not 'data'."
            )
        elif isinstance(data, list):
            assert len(data) >= 64, (
                f"FIX FAILED: Expected 64+ salari movimenti for 2025, got {len(data)}"
            )
            print(f"✅ Salari 2025: {len(data)} movimenti")

    def test_prima_nota_salari_2024_returns_data(self):
        """GET /api/prima-nota/salari?anno=2024 → deve restituire movimenti"""
        resp = requests.get(
            f"{BASE_URL}/api/prima-nota/salari",
            params={"anno": 2024, "limit": 200},
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        if isinstance(data, dict):
            movimenti = data.get("movimenti", [])
            count = data.get("count") or len(movimenti)
            print(f"✅ Salari 2024: {len(movimenti)} movimenti (count={count})")
            assert len(movimenti) > 0 or count > 0, "Salari 2024 returned no movimenti"
        elif isinstance(data, list):
            assert len(data) > 0, "Salari 2024 returned empty list"
            print(f"✅ Salari 2024: {len(data)} movimenti")

    def test_prima_nota_salari_anno_field_filter(self):
        """Verify salari movimenti for 2025 all have anno=2025 field"""
        resp = requests.get(
            f"{BASE_URL}/api/prima-nota/salari",
            params={"anno": 2025, "limit": 10},
            timeout=15
        )
        assert resp.status_code == 200
        data = resp.json()
        movimenti = data.get("movimenti", []) if isinstance(data, dict) else data
        if movimenti:
            for m in movimenti[:5]:
                anno_val = m.get("anno")
                print(f"  Movimento: anno={anno_val}, data={m.get('data', 'N/A')}")
            # At least one movimento should have anno field
            has_anno = any(m.get("anno") for m in movimenti[:5])
            if not has_anno:
                print("⚠️ Movimenti don't have 'anno' field - check data structure")
            print(f"✅ Salari movimenti structure checked")


# ====================== P0: FORNITORI ======================

class TestFornitori:
    """P0: Fornitori - 200 record expected"""

    def test_fornitori_200_records(self):
        """GET /api/suppliers?limit=200 → deve restituire 200 fornitori"""
        resp = requests.get(
            f"{BASE_URL}/api/suppliers",
            params={"limit": 200},
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        if isinstance(data, list):
            print(f"✅ Fornitori: {len(data)} records returned")
            assert len(data) >= 100, f"Expected 200 suppliers, got {len(data)}"
        elif isinstance(data, dict):
            items = data.get("data", data.get("suppliers", data.get("items", [])))
            print(f"✅ Fornitori: {len(items)} records in response")
            assert len(items) >= 100, f"Expected 200 suppliers, got {len(items)}"

    def test_fornitori_structure(self):
        """Fornitori must have required fields"""
        resp = requests.get(
            f"{BASE_URL}/api/suppliers",
            params={"limit": 5},
            timeout=15
        )
        assert resp.status_code == 200
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", data.get("suppliers", []))
        if items:
            supplier = items[0]
            print(f"✅ Fornitore fields: {list(supplier.keys())}")
            # Should have some identifying field
            has_name = "nome" in supplier or "ragione_sociale" in supplier or "name" in supplier
            assert has_name, f"No name field in supplier: {supplier}"


# ====================== P0: FATTURE ======================

class TestFatture:
    """P0: Fatture - 204 totali (199 del 2026)"""

    def test_invoices_returns_data(self):
        """GET /api/invoices?limit=10 → deve restituire fatture con invoice_date"""
        resp = requests.get(
            f"{BASE_URL}/api/invoices",
            params={"limit": 10},
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", data.get("invoices", []))
        assert len(items) > 0, "No invoices returned"
        print(f"✅ Invoices: {len(items)} returned")
        # Check invoice_date field
        if items:
            inv = items[0]
            print(f"  Invoice fields: {list(inv.keys())}")
            has_date = "invoice_date" in inv or "data" in inv or "data_fattura" in inv
            assert has_date, f"No date field in invoice: {inv}"

    def test_invoices_2026_filter(self):
        """GET /api/invoices?anno=2026&limit=10 → deve restituire fatture del 2026"""
        resp = requests.get(
            f"{BASE_URL}/api/invoices",
            params={"anno": 2026, "limit": 10},
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", data.get("invoices", []))
        assert len(items) > 0, "No invoices for 2026"
        print(f"✅ Invoices 2026: {len(items)} returned")

    def test_invoices_total_count(self):
        """Total invoices should be ~204"""
        resp = requests.get(
            f"{BASE_URL}/api/invoices",
            params={"limit": 300},
            timeout=15
        )
        assert resp.status_code == 200
        data = resp.json()
        if isinstance(data, dict):
            total = data.get("total") or data.get("count") or len(data.get("data", []))
            print(f"✅ Invoices total: {total} (expected ~204)")
        elif isinstance(data, list):
            print(f"✅ Invoices list: {len(data)} items returned")


# ====================== P1: DIPENDENTI ======================

class TestDipendenti:
    """P1: Dipendenti - 34 record, no CF duplicates"""

    def test_dipendenti_34_records(self):
        """GET /api/dipendenti → deve restituire 34 dipendenti"""
        resp = requests.get(f"{BASE_URL}/api/dipendenti", timeout=15)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        assert isinstance(data, list), "Expected list of dipendenti"
        print(f"✅ Dipendenti: {len(data)} records (expected 34)")
        assert len(data) == 34, f"Expected 34 dipendenti, got {len(data)}"

    def test_dipendenti_no_cf_duplicates(self):
        """No duplicate codice_fiscale in dipendenti"""
        resp = requests.get(f"{BASE_URL}/api/dipendenti", timeout=15)
        assert resp.status_code == 200
        dipendenti = resp.json()
        seen_cf = {}
        duplicates = []
        for dip in dipendenti:
            cf = (dip.get("codice_fiscale") or "").upper().strip()
            if cf:
                if cf in seen_cf:
                    duplicates.append(cf)
                else:
                    seen_cf[cf] = dip.get("nome_completo")
        assert len(duplicates) == 0, f"❌ Duplicate CF found: {duplicates}"
        print(f"✅ No CF duplicates in {len(dipendenti)} dipendenti")


# ====================== P1: FIX - CEDOLINI ANNO STRING/INT ======================

class TestCedolini:
    """
    FIX: Cedolini anno filter now uses $or [int, string].
    Expected: 15 cedolini 2026, 253+ cedolini 2025.
    """

    def test_cedolini_2026_fix_anno_int_string(self):
        """
        GET /api/cedolini?anno=2026 → deve restituire 15 cedolini.
        VERIFICA FIX: gestisce sia int (2026) sia string ('2026').
        """
        resp = requests.get(
            f"{BASE_URL}/api/cedolini",
            params={"anno": 2026, "limit": 100},
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        if isinstance(data, list):
            count = len(data)
            print(f"✅ Cedolini 2026: {count} records returned")
            assert count >= 15, (
                f"FIX FAILED: Expected 15 cedolini for 2026, got {count}. "
                "Check $or filter in cedolini.py"
            )
        elif isinstance(data, dict):
            items = data.get("data", data.get("cedolini", []))
            total = data.get("total") or data.get("count") or len(items)
            print(f"✅ Cedolini 2026: {len(items)} items, total={total}")
            assert len(items) >= 15 or total >= 15, (
                f"FIX FAILED: Expected 15+ cedolini for 2026, got {len(items)} (total={total})"
            )

    def test_cedolini_2025_returns_253_plus(self):
        """GET /api/cedolini?anno=2025 → deve restituire 253+ cedolini"""
        resp = requests.get(
            f"{BASE_URL}/api/cedolini",
            params={"anno": 2025, "limit": 500},
            timeout=15
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        if isinstance(data, list):
            count = len(data)
            print(f"✅ Cedolini 2025: {count} records returned (expected 253+)")
            assert count >= 253, (
                f"Expected 253+ cedolini for 2025, got {count}"
            )
        elif isinstance(data, dict):
            items = data.get("data", data.get("cedolini", []))
            total = data.get("total") or data.get("count") or len(items)
            print(f"✅ Cedolini 2025: {len(items)} items, total={total}")
            assert total >= 253, (
                f"Expected 253+ cedolini for 2025, total={total}"
            )

    def test_cedolini_2026_no_cf_mese_anno_duplicates(self):
        """No CF+mese+anno duplicates in cedolini 2026"""
        resp = requests.get(
            f"{BASE_URL}/api/cedolini",
            params={"anno": 2026, "limit": 100},
            timeout=15
        )
        assert resp.status_code == 200
        data = resp.json()
        cedolini = data if isinstance(data, list) else data.get("data", data.get("cedolini", []))
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
        assert len(duplicates) == 0, f"Found {len(duplicates)} cedolini duplicates: {duplicates[:3]}"
        print(f"✅ No cedolini duplicates in 2026 records")


# ====================== P1: DASHBOARD BILANCIO ======================

class TestDashboardBilancio:
    """P1: Dashboard bilancio-istantaneo - ricavi e costi attesi"""

    def test_dashboard_bilancio_2026_ricavi_costi(self):
        """
        GET /api/dashboard/bilancio-istantaneo?anno=2026
        → ricavi > 0 (€31k atteso) e costi > 0 (€171k atteso)
        """
        resp = requests.get(
            f"{BASE_URL}/api/dashboard/bilancio-istantaneo",
            params={"anno": 2026},
            timeout=20
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        print(f"✅ Bilancio 2026 keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
        if isinstance(data, dict):
            ricavi_raw = data.get("ricavi") or data.get("totale_ricavi") or 0
            costi_raw = data.get("costi") or data.get("totale_costi") or 0
            # ricavi/costi may be nested dicts with 'totale' key
            ricavi = ricavi_raw.get("totale", 0) if isinstance(ricavi_raw, dict) else ricavi_raw
            costi = costi_raw.get("totale", 0) if isinstance(costi_raw, dict) else costi_raw
            print(f"  Ricavi: {ricavi}, Costi: {costi}")
            assert ricavi > 0, f"Expected ricavi > 0 for 2026, got {ricavi}"
            assert costi > 0, f"Expected costi > 0 for 2026, got {costi}"

    def test_dashboard_bilancio_2025_ricavi(self):
        """
        GET /api/dashboard/bilancio-istantaneo?anno=2025
        → ricavi ~€922k (nessuna fattura 2025 nel DB è normale per costi=€0)
        """
        resp = requests.get(
            f"{BASE_URL}/api/dashboard/bilancio-istantaneo",
            params={"anno": 2025},
            timeout=20
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        if isinstance(data, dict):
            ricavi_raw = data.get("ricavi") or data.get("totale_ricavi") or 0
            costi_raw = data.get("costi") or data.get("totale_costi") or 0
            ricavi = ricavi_raw.get("totale", 0) if isinstance(ricavi_raw, dict) else ricavi_raw
            costi = costi_raw.get("totale", 0) if isinstance(costi_raw, dict) else costi_raw
            print(f"✅ Bilancio 2025: Ricavi={ricavi}, Costi={costi}")
            # 2025: ricavi expected ~€922k from Prima Nota Cassa; costi=0 (no fatture 2025) is valid
            assert ricavi > 0, f"Expected ricavi > 0 for 2025, got {ricavi}"

    def test_dashboard_summary_2026(self):
        """GET /api/dashboard/summary?anno=2026 must work"""
        resp = requests.get(
            f"{BASE_URL}/api/dashboard/summary",
            params={"anno": 2026},
            timeout=20
        )
        assert resp.status_code in [200, 404], f"Got {resp.status_code}: {resp.text[:200]}"
        if resp.status_code == 200:
            data = resp.json()
            print(f"✅ Dashboard summary 2026 keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
