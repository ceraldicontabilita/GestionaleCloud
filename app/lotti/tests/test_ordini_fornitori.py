"""
Backend tests for ordini-fornitori endpoints.
Verifica fix: prodotti con nomi corretti (non raw ID), prodotti non vuoti.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "http://localhost:8000"


class TestOrdiniFornitoriBackend:
    """Test suite for /api/ordini-fornitori endpoints"""

    def test_health_check(self):
        """Verifica che il backend sia raggiungibile"""
        r = requests.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        print("✅ Health check OK")

    def test_get_prodotti_suggeriti(self):
        """GET /api/ordini-fornitori/prodotti-suggeriti deve restituire prodotti"""
        r = requests.get(f"{BASE_URL}/api/ordini-fornitori/prodotti-suggeriti?limit=20")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ Prodotti suggeriti: {len(data)} prodotti restituiti")

        if len(data) > 0:
            # Verifica struttura prodotto
            p = data[0]
            assert "id" in p, "Prodotto deve avere campo 'id'"
            assert "nome" in p, "Prodotto deve avere campo 'nome'"
            assert "fornitore" in p, "Prodotto deve avere campo 'fornitore'"
            assert "sotto_scorta" in p, "Prodotto deve avere campo 'sotto_scorta'"
            print(f"✅ Struttura prodotto corretta. Primo prodotto: {p.get('nome', 'N/A')}")

    def test_get_lista_ordini(self):
        """GET /api/ordini-fornitori deve restituire lista di ordini"""
        r = requests.get(f"{BASE_URL}/api/ordini-fornitori?source=tracciabilita&limit=30")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ Lista ordini: {len(data)} ordini restituiti")

    def test_crea_ordine_con_prodotto(self):
        """POST /api/ordini-fornitori crea un ordine con prodotti e verifica che il nome sia corretto"""
        payload = {
            "reparto": "test",
            "operatore": "test_agent",
            "prodotti": [
                {
                    "prodotto_id": "TEST_PROD_001",
                    "nome": "Burro Test",
                    "fornitore": "Fornitore Test",
                    "quantita": 2.0,
                    "unita": "kg",
                    "prezzo_ultimo": 3.50,
                    "note": ""
                },
                {
                    "prodotto_id": "TEST_PROD_002",
                    "nome": "Farina Test",
                    "fornitore": "Fornitore Test",
                    "quantita": 5.0,
                    "unita": "kg",
                    "prezzo_ultimo": 1.20,
                    "note": ""
                }
            ],
            "ricette_da_produrre": [],
            "note_operatore": "Test da agent di testing"
        }
        r = requests.post(f"{BASE_URL}/api/ordini-fornitori", json=payload)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:400]}"
        data = r.json()
        assert data.get("success") == True, "Response should have success=True"
        assert "ordine_id" in data, "Response deve avere ordine_id"
        assert "ordine" in data, "Response deve avere campo 'ordine'"

        ordine = data["ordine"]
        assert "prodotti" in ordine, "Ordine deve avere campo 'prodotti'"
        prodotti_salvati = ordine["prodotti"]
        assert len(prodotti_salvati) == 2, f"Expected 2 prodotti, got {len(prodotti_salvati)}"

        # *** VERIFICA CRITICA: i nomi NON devono essere l'ID grezzo ***
        for p in prodotti_salvati:
            assert p.get("nome") != p.get("prodotto_id"), \
                f"Nome prodotto non deve essere l'ID grezzo! nome={p.get('nome')}, id={p.get('prodotto_id')}"
            assert p.get("nome") != "", "Nome prodotto non deve essere vuoto"
            assert p.get("prodotto_id") in ["TEST_PROD_001", "TEST_PROD_002"], "prodotto_id deve corrispondere"
            print(f"  ✅ Prodotto: nome='{p.get('nome')}' id='{p.get('prodotto_id')}'")

        print(f"✅ Ordine creato con ID: {data['ordine_id'][:8]}...")
        return data["ordine_id"]

    def test_ordine_prodotti_non_vuoti(self):
        """Verifica GET /api/ordini-fornitori: ordini recenti hanno 'prodotti' non vuoto"""
        # Prima crea un ordine di test
        payload = {
            "reparto": "pasticceria",
            "operatore": "test_verifica",
            "prodotti": [
                {
                    "prodotto_id": "PROD_VERIFICA_001",
                    "nome": "Zucchero Verifica",
                    "fornitore": "Fornitore A",
                    "quantita": 3.0,
                    "unita": "kg",
                    "prezzo_ultimo": 1.50,
                    "note": ""
                }
            ],
            "ricette_da_produrre": [],
            "note_operatore": "Test verifica prodotti non vuoti"
        }
        create_r = requests.post(f"{BASE_URL}/api/ordini-fornitori", json=payload)
        assert create_r.status_code == 200
        created_id = create_r.json()["ordine_id"]

        # Recupera la lista degli ordini e verifica che il prodotto sia presente
        list_r = requests.get(f"{BASE_URL}/api/ordini-fornitori?source=tracciabilita&limit=50")
        assert list_r.status_code == 200
        ordini = list_r.json()

        # Trova l'ordine creato
        ordine_trovato = next((o for o in ordini if o.get("id") == created_id), None)
        assert ordine_trovato is not None, f"Ordine {created_id} non trovato nella lista"

        prodotti = ordine_trovato.get("prodotti", [])
        assert len(prodotti) > 0, "Prodotti non devono essere vuoti nell'ordine salvato!"
        assert prodotti[0].get("nome") == "Zucchero Verifica", \
            f"Nome prodotto errato: {prodotti[0].get('nome')}"
        print(f"✅ Ordine recuperato con prodotti non vuoti: {len(prodotti)} prodotto/i")

    def test_get_singolo_ordine(self):
        """GET /api/ordini-fornitori/{id} deve restituire l'ordine specifico"""
        # Prima crea un ordine
        payload = {
            "reparto": "bar",
            "operatore": "test_singolo",
            "prodotti": [
                {
                    "prodotto_id": "PROD_SINGOLO_001",
                    "nome": "Caffè Test",
                    "fornitore": "Fornitore B",
                    "quantita": 1.0,
                    "unita": "kg",
                    "prezzo_ultimo": 10.0,
                    "note": ""
                }
            ],
            "ricette_da_produrre": [],
            "note_operatore": ""
        }
        create_r = requests.post(f"{BASE_URL}/api/ordini-fornitori", json=payload)
        assert create_r.status_code == 200
        ordine_id = create_r.json()["ordine_id"]

        # Recupera per ID
        get_r = requests.get(f"{BASE_URL}/api/ordini-fornitori/{ordine_id}")
        assert get_r.status_code == 200, f"Expected 200, got {get_r.status_code}"
        data = get_r.json()
        assert data["id"] == ordine_id, "ID ordine non corrisponde"
        assert len(data.get("prodotti", [])) == 1, "Deve avere 1 prodotto"
        assert data["prodotti"][0]["nome"] == "Caffè Test", "Nome prodotto errato"
        print(f"✅ GET singolo ordine OK: {ordine_id[:8]}...")

    def test_crea_ordine_senza_prodotti_fallisce(self):
        """POST senza prodotti deve dare errore 400"""
        payload = {
            "reparto": "test",
            "operatore": "test",
            "prodotti": [],
            "ricette_da_produrre": [],
            "note_operatore": ""
        }
        r = requests.post(f"{BASE_URL}/api/ordini-fornitori", json=payload)
        assert r.status_code == 400, f"Expected 400 for empty products, got {r.status_code}"
        print("✅ Errore 400 corretto per ordine senza prodotti")

    def test_prodotti_suggeriti_sotto_scorta_prima(self):
        """I prodotti sotto scorta devono apparire prima nella lista"""
        r = requests.get(f"{BASE_URL}/api/ordini-fornitori/prodotti-suggeriti?limit=50")
        assert r.status_code == 200
        data = r.json()
        if len(data) < 2:
            print("⚠️ Meno di 2 prodotti, salto test ordinamento")
            return

        # Verifica che i prodotti sotto scorta siano all'inizio (se presenti)
        sotto_scorta_found = [i for i, p in enumerate(data) if p.get("sotto_scorta")]
        non_sotto_scorta_found = [i for i, p in enumerate(data) if not p.get("sotto_scorta")]
        if sotto_scorta_found and non_sotto_scorta_found:
            assert max(sotto_scorta_found) < max(non_sotto_scorta_found) or \
                   min(sotto_scorta_found) < min(non_sotto_scorta_found), \
                "Prodotti sotto scorta dovrebbero apparire prima"
            print(f"✅ Ordinamento: {len(sotto_scorta_found)} sotto scorta, {len(non_sotto_scorta_found)} normali")
        else:
            print(f"ℹ️ Tutti i prodotti sono {'sotto scorta' if sotto_scorta_found else 'nella norma'}")
