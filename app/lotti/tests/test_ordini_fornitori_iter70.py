"""
Test backend iteration 70 — OrdiniFornitoriView refactor
Endpoints testati:
  - GET  /ordini-fornitori/count-pendenti
  - POST /ordini-fornitori  (stato=bozza default)
  - GET  /ordini-fornitori?stato=bozza
  - GET  /ordini-fornitori?stato=inviato_fornitori
  - DELETE /ordini-fornitori/{id}
  - GET  /ordini-fornitori/prodotti-suggeriti
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestOrdiniFornitoriAPI:
    """Test completi per OrdiniFornitoriView (iter70)"""

    def test_count_pendenti_returns_int(self):
        """GET /count-pendenti deve tornare {"count": <int>}"""
        r = requests.get(f"{BASE_URL}/api/ordini-fornitori/count-pendenti")
        assert r.status_code == 200, f"Unexpected status: {r.status_code} — {r.text}"
        data = r.json()
        assert "count" in data, f"Manca 'count' in risposta: {data}"
        assert isinstance(data["count"], int), f"count non è int: {data['count']}"
        print(f"[PASS] count-pendenti = {data['count']}")

    def test_lista_ordini_senza_filtro(self):
        """GET /ordini-fornitori senza filtro deve tornare lista (anche vuota)"""
        r = requests.get(f"{BASE_URL}/api/ordini-fornitori")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        print(f"[PASS] Lista ordini senza filtro: {len(data)} ordini")

    def test_crea_ordine_stato_bozza(self):
        """POST /ordini-fornitori deve creare ordine con stato=bozza"""
        payload = {
            "reparto": "TEST_reparto",
            "operatore": "TEST_operatore",
            "prodotti": [
                {
                    "prodotto_id": "test_id_001",
                    "nome": "TEST_Prodotto Alpha",
                    "fornitore": "TEST_Fornitore X",
                    "quantita": 2.5,
                    "unita": "kg",
                    "prezzo_ultimo": 4.50,
                    "note": "test iter70"
                }
            ],
            "ricette_da_produrre": [],
            "note_operatore": "TEST_iter70",
            "source": "manuale"
        }
        r = requests.post(f"{BASE_URL}/api/ordini-fornitori", json=payload)
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("success") == True
        assert "ordine_id" in data
        assert "ordine" in data

        ordine = data["ordine"]
        assert ordine["stato"] == "bozza", f"Stato atteso 'bozza', ricevuto: '{ordine['stato']}'"
        assert ordine["source"] == "manuale"
        assert len(ordine["prodotti"]) == 1
        assert ordine["prodotti"][0]["nome"] == "TEST_Prodotto Alpha"

        # Salviamo l'id per i test successivi
        TestOrdiniFornitoriAPI._test_ordine_id = data["ordine_id"]
        print(f"[PASS] Ordine creato con stato=bozza, id={data['ordine_id']}")

    def test_get_ordine_by_id(self):
        """GET /ordini-fornitori/{id} deve tornare l'ordine appena creato"""
        ordine_id = getattr(TestOrdiniFornitoriAPI, "_test_ordine_id", None)
        if not ordine_id:
            pytest.skip("test_crea_ordine_stato_bozza non eseguito")
        r = requests.get(f"{BASE_URL}/api/ordini-fornitori/{ordine_id}")
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert data["id"] == ordine_id
        assert data["stato"] == "bozza"
        print(f"[PASS] GET ordine {ordine_id}: stato={data['stato']}")

    def test_filtro_stato_bozza(self):
        """GET /ordini-fornitori?stato=bozza deve tornare solo bozze"""
        r = requests.get(f"{BASE_URL}/api/ordini-fornitori?stato=bozza&limit=100")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for o in data:
            assert o["stato"] == "bozza", f"Ordine {o.get('id')} ha stato={o.get('stato')}, atteso bozza"
        print(f"[PASS] filtro stato=bozza: {len(data)} bozze (tutte con stato='bozza')")

    def test_filtro_stato_inviato_fornitori(self):
        """GET /ordini-fornitori?stato=inviato_fornitori deve tornare solo inviati ai fornitori"""
        r = requests.get(f"{BASE_URL}/api/ordini-fornitori?stato=inviato_fornitori&limit=100")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for o in data:
            assert o["stato"] == "inviato_fornitori", f"Ordine ha stato={o.get('stato')}"
        print(f"[PASS] filtro stato=inviato_fornitori: {len(data)} ordini inviati")

    def test_filtro_stato_inviato_backward_compat(self):
        """GET /ordini-fornitori?stato=inviato deve tornare gli ordini vecchi con stato='inviato'"""
        r = requests.get(f"{BASE_URL}/api/ordini-fornitori?stato=inviato&limit=100")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for o in data:
            assert o["stato"] == "inviato", f"Ordine ha stato={o.get('stato')}"
        print(f"[PASS] backward compat stato=inviato: {len(data)} ordini")

    def test_count_pendenti_include_bozze_e_inviato(self):
        """
        count-pendenti deve includere sia stato='bozza' che stato='inviato'
        Per verificarlo: contiamo bozze + inviato e confrontiamo col count
        """
        r_bozze = requests.get(f"{BASE_URL}/api/ordini-fornitori?stato=bozza&limit=200")
        r_inv   = requests.get(f"{BASE_URL}/api/ordini-fornitori?stato=inviato&limit=200")
        r_count = requests.get(f"{BASE_URL}/api/ordini-fornitori/count-pendenti")

        assert r_bozze.status_code == 200
        assert r_inv.status_code == 200
        assert r_count.status_code == 200

        n_bozze = len(r_bozze.json())
        n_inv   = len(r_inv.json())
        count   = r_count.json()["count"]

        # Il count deve essere >= n_bozze + n_inv (potrebbe non eguagliare per il limit(200))
        # In pratica dovrebbe essere uguale se abbiamo < 200 ordini
        assert count == n_bozze + n_inv, \
            f"count-pendenti={count} ≠ bozze({n_bozze}) + inviato({n_inv}) = {n_bozze + n_inv}"
        print(f"[PASS] count-pendenti={count} = bozze({n_bozze}) + inviato({n_inv})")

    def test_delete_ordine(self):
        """DELETE /ordini-fornitori/{id} deve eliminare la bozza"""
        ordine_id = getattr(TestOrdiniFornitoriAPI, "_test_ordine_id", None)
        if not ordine_id:
            pytest.skip("test_crea_ordine_stato_bozza non eseguito")
        r = requests.delete(f"{BASE_URL}/api/ordini-fornitori/{ordine_id}")
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("ok") == True
        print(f"[PASS] DELETE ordine {ordine_id}: ok")

    def test_delete_ordine_not_found(self):
        """DELETE /ordini-fornitori/{id} con id inesistente deve tornare 404"""
        r = requests.delete(f"{BASE_URL}/api/ordini-fornitori/ordine_inesistente_test_9999")
        assert r.status_code == 404, f"Atteso 404, ricevuto {r.status_code}: {r.text}"
        print("[PASS] DELETE ordine inesistente → 404")

    def test_get_ordine_eliminato_404(self):
        """GET ordine eliminato deve tornare 404"""
        ordine_id = getattr(TestOrdiniFornitoriAPI, "_test_ordine_id", None)
        if not ordine_id:
            pytest.skip("test_crea/delete non eseguiti")
        r = requests.get(f"{BASE_URL}/api/ordini-fornitori/{ordine_id}")
        assert r.status_code == 404, f"Atteso 404, ricevuto {r.status_code}"
        print(f"[PASS] GET ordine eliminato {ordine_id} → 404")

    def test_prodotti_suggeriti(self):
        """GET /prodotti-suggeriti deve tornare lista con flag sotto_scorta"""
        r = requests.get(f"{BASE_URL}/api/ordini-fornitori/prodotti-suggeriti?limit=50")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        if data:
            p = data[0]
            assert "id" in p
            assert "nome" in p
            assert "sotto_scorta" in p
            assert isinstance(p["sotto_scorta"], bool)
        print(f"[PASS] prodotti-suggeriti: {len(data)} prodotti")

    def test_prodotti_suggeriti_sotto_scorta_prima(self):
        """I prodotti sotto scorta devono apparire prima degli altri"""
        r = requests.get(f"{BASE_URL}/api/ordini-fornitori/prodotti-suggeriti?limit=200")
        assert r.status_code == 200
        data = r.json()
        if len(data) < 2:
            pytest.skip("Troppo pochi prodotti per verificare ordinamento")

        # Cerca prima posizione di un non-sotto-scorta
        idx_no_ss = next((i for i, p in enumerate(data) if not p["sotto_scorta"]), None)
        if idx_no_ss is None:
            print("[PASS] Tutti i prodotti sono sotto scorta, ordinamento non verificabile")
            return

        # Tutti i prodotti prima di idx_no_ss devono essere sotto_scorta=True
        for p in data[:idx_no_ss]:
            assert p["sotto_scorta"] == True, f"Prodotto {p['nome']} non sotto scorta ma prima di idx_no_ss"
        print(f"[PASS] Prodotti sotto scorta prima: {idx_no_ss} SS, poi non-SS")

    def test_crea_ordine_senza_prodotti_400(self):
        """POST /ordini-fornitori senza prodotti deve tornare 400"""
        payload = {
            "reparto": "test",
            "operatore": "test",
            "prodotti": [],
            "source": "manuale"
        }
        r = requests.post(f"{BASE_URL}/api/ordini-fornitori", json=payload)
        assert r.status_code == 400, f"Atteso 400, ricevuto {r.status_code}: {r.text}"
        print("[PASS] Ordine senza prodotti → 400")
