"""
Test Iteration 67: Prezzi Alert + Deep Link features
- GET /api/ingredienti/prezzi-alert — mappa {product_id: delta_pct}
- GET /api/ordini-fornitori/prodotti-suggeriti — verifica prodotti con campo id
- Deep linking: #ordini → OrdiniFornitoriView, #fornitori → FornitoriList
- CatalogoFornitoreView: nessun crash di compilazione (indiretto)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def api():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


class TestPrezziAlert:
    """Tests for GET /api/ingredienti/prezzi-alert endpoint"""

    def test_prezzi_alert_returns_200(self, api):
        """Endpoint deve restituire 200 OK"""
        r = api.get(f"{BASE_URL}/api/ingredienti/prezzi-alert")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
        print("PASS: /api/ingredienti/prezzi-alert returns 200")

    def test_prezzi_alert_returns_dict(self, api):
        """Risposta deve essere un dizionario JSON"""
        r = api.get(f"{BASE_URL}/api/ingredienti/prezzi-alert")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        print(f"PASS: Response is dict with {len(data)} entries")

    def test_prezzi_alert_values_are_floats(self, api):
        """I valori della mappa devono essere float (delta percentuale)"""
        r = api.get(f"{BASE_URL}/api/ingredienti/prezzi-alert")
        assert r.status_code == 200
        data = r.json()
        if len(data) == 0:
            pytest.skip("No alert data available to validate values")
        for pid, delta in list(data.items())[:10]:
            assert isinstance(delta, (int, float)), f"Value for {pid} should be numeric, got {type(delta)}"
            print(f"  product_id={pid[:8]}... delta={delta}%")
        print(f"PASS: All sampled values are numeric")

    def test_prezzi_alert_delta_within_range(self, api):
        """Delta deve essere tra 15% e 300% (filtro del backend)"""
        r = api.get(f"{BASE_URL}/api/ingredienti/prezzi-alert")
        assert r.status_code == 200
        data = r.json()
        if len(data) == 0:
            pytest.skip("No alert data available to validate range")
        for pid, delta in data.items():
            assert 15.0 <= delta <= 300.0, f"Delta {delta} for {pid} out of range [15, 300]"
        print(f"PASS: All {len(data)} deltas are within [15, 300]%")

    def test_prezzi_alert_keys_are_uuids(self, api):
        """Le chiavi devono essere product_id (formato UUID)"""
        r = api.get(f"{BASE_URL}/api/ingredienti/prezzi-alert")
        assert r.status_code == 200
        data = r.json()
        if len(data) == 0:
            pytest.skip("No alert data available to validate keys")
        sample_key = list(data.keys())[0]
        # UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        parts = sample_key.split("-")
        assert len(parts) == 5, f"Key '{sample_key}' doesn't look like UUID"
        print(f"PASS: Keys are UUID-formatted (sample: {sample_key})")

    def test_prezzi_alert_no_mongodb_id(self, api):
        """La risposta non deve contenere '_id' MongoDB"""
        r = api.get(f"{BASE_URL}/api/ingredienti/prezzi-alert")
        assert r.status_code == 200
        text = r.text
        assert '"_id"' not in text, "Response contains MongoDB _id field!"
        print("PASS: No MongoDB _id in response")

    def test_prezzi_alert_custom_soglia(self, api):
        """Endpoint deve accettare parametro soglia personalizzato"""
        r = api.get(f"{BASE_URL}/api/ingredienti/prezzi-alert?soglia=50.0")
        assert r.status_code == 200
        data_50 = r.json()
        r2 = api.get(f"{BASE_URL}/api/ingredienti/prezzi-alert")
        data_15 = r2.json()
        # With higher threshold, fewer or equal results
        assert len(data_50) <= len(data_15), \
            f"Higher threshold should return fewer results: soglia=50 got {len(data_50)}, soglia=15 got {len(data_15)}"
        print(f"PASS: soglia=15 → {len(data_15)} alerts, soglia=50 → {len(data_50)} alerts")

    def test_prezzi_alert_has_data(self, api):
        """Ci devono essere prodotti con alert prezzi nel DB reale"""
        r = api.get(f"{BASE_URL}/api/ingredienti/prezzi-alert")
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0, "No price alerts found — need at least 1 product with 2+ suppliers and >15% delta"
        print(f"PASS: {len(data)} products with price alerts found")


class TestProdottiSuggeriti:
    """Tests to verify prodotti-suggeriti API returns proper ids for alertMap lookup"""

    def test_prodotti_suggeriti_returns_200(self, api):
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/prodotti-suggeriti?limit=10")
        assert r.status_code == 200
        print("PASS: /api/ordini-fornitori/prodotti-suggeriti returns 200")

    def test_prodotti_suggeriti_have_id_field(self, api):
        """Prodotti devono avere campo 'id' per poter fare lookup in alertMap"""
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/prodotti-suggeriti?limit=50")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        if len(data) == 0:
            pytest.skip("No suggested products available")
        # Verify id field exists
        for prod in data[:5]:
            assert "id" in prod, f"Product missing 'id' field: {list(prod.keys())}"
        print(f"PASS: {len(data)} products, all have 'id' field")

    def test_alert_map_integration(self, api):
        """Verifica che almeno un prodotto in prodotti-suggeriti abbia ID in prezzi-alert"""
        r_prod = api.get(f"{BASE_URL}/api/ordini-fornitori/prodotti-suggeriti?limit=700")
        r_alert = api.get(f"{BASE_URL}/api/ingredienti/prezzi-alert")
        assert r_prod.status_code == 200
        assert r_alert.status_code == 200
        prodotti = r_prod.json()
        alert_map = r_alert.json()
        if not alert_map:
            pytest.skip("No price alerts available")
        alert_ids = set(alert_map.keys())
        prod_ids = {p["id"] for p in prodotti if "id" in p}
        overlap = alert_ids & prod_ids
        print(f"Products in prodotti-suggeriti: {len(prod_ids)}")
        print(f"Products in alert map: {len(alert_ids)}")
        print(f"Overlap (products with alerts): {len(overlap)}")
        assert len(overlap) > 0, \
            "No overlap between prodotti-suggeriti IDs and prezzi-alert IDs — badges will never show!"
        print(f"PASS: {len(overlap)} products appear in both prodotti-suggeriti and alert map")

    def test_sotto_scorta_with_alert(self, api):
        """Verifica badge alert per prodotti sotto scorta"""
        r_prod = api.get(f"{BASE_URL}/api/ordini-fornitori/prodotti-suggeriti?limit=700")
        r_alert = api.get(f"{BASE_URL}/api/ingredienti/prezzi-alert")
        assert r_prod.status_code == 200
        assert r_alert.status_code == 200
        prodotti = r_prod.json()
        alert_map = r_alert.json()
        sotto_scorta = [p for p in prodotti if p.get("sotto_scorta")]
        alert_ids = set(alert_map.keys())
        ss_with_alert = [p for p in sotto_scorta if p.get("id") in alert_ids]
        print(f"Prodotti sotto scorta: {len(sotto_scorta)}")
        print(f"Prodotti sotto scorta con alert prezzi: {len(ss_with_alert)}")
        if ss_with_alert:
            sample = ss_with_alert[0]
            print(f"  Esempio: id={sample['id']}, nome={sample.get('nome','?')}, delta={alert_map[sample['id']]}%")
        # NOTE: This might be 0 if no sotto-scorta products overlap with alert - that's OK
        print(f"INFO: Badge ⚠ will show on {len(ss_with_alert)} sotto-scorta products")


class TestDeepLinking:
    """Tests for deep linking behavior via hash routing"""

    def test_hash_ordini_loads_app(self, api):
        """L'app deve essere raggiungibile — deep link verification è UI-only"""
        r = api.get(f"{BASE_URL}/")
        assert r.status_code == 200
        print("PASS: App loads at root URL")

    def test_ordini_fornitori_prodotti_api_accessible(self, api):
        """API usata da OrdiniFornitoriView deve essere accessibile"""
        r = api.get(f"{BASE_URL}/api/ordini-fornitori/prodotti-suggeriti?limit=5")
        assert r.status_code == 200
        print("PASS: prodotti-suggeriti API accessible (OrdiniFornitoriView will load)")

    def test_fornitori_list_api_accessible(self, api):
        """API usata da FornitoriList deve essere accessibile"""
        r = api.get(f"{BASE_URL}/api/fornitori")
        assert r.status_code == 200
        print("PASS: /api/fornitori accessible (FornitoriList will load)")

    def test_storico_ordini_api_accessible(self, api):
        """API usata dal tab Storico di OrdiniFornitoriView deve essere accessibile"""
        r = api.get(f"{BASE_URL}/api/ordini-fornitori?limit=10")
        assert r.status_code == 200
        print("PASS: /api/ordini-fornitori accessible (Storico tab will load)")


class TestIngredienteNormalizzazioneCheck:
    """Verifica che i prodotti nel dizionario abbiano ingrediente_canonico per alert"""

    def test_dizionario_products_with_canonico(self, api):
        """Verifica quanti prodotti hanno ingrediente_canonico (necessario per alert)"""
        r = api.get(f"{BASE_URL}/api/ingredienti/prezzi-alert")
        assert r.status_code == 200
        data = r.json()
        count = len(data)
        assert count > 0, "No products with ingrediente_canonico AND multi-supplier AND >15% delta"
        # Verifica che ci siano delta realistici (>15% ma <300%)
        over_100 = sum(1 for v in data.values() if v > 100)
        under_100 = sum(1 for v in data.values() if 15 <= v <= 100)
        print(f"PASS: {count} products with price alerts")
        print(f"  Delta 15-100%: {under_100} products")
        print(f"  Delta >100% (diversi prodotti stesso canonico?): {over_100} products")
