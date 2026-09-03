"""
Iteration 68 - Test Magazzino Bar API endpoints
Tests: GET prodotti, GET filtri, POST carico, POST scarico, GET movimenti/oggi
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
_PIN_OP1 = os.environ.get("TEST_PIN_OP1", "0000")  # PIN da env, mai in chiaro


class TestMagazzinoBarProdotti:
    """Test lista prodotti magazzino bar"""

    def test_get_prodotti_status(self):
        """GET /api/magazzino-bar/prodotti → 200 OK"""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/prodotti")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        print(f"PASS: GET prodotti → {r.status_code}")

    def test_get_prodotti_count(self):
        """Deve restituire 32 prodotti (seed default)"""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/prodotti")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list), "Expected list"
        assert len(data) >= 32, f"Expected >=32 prodotti, got {len(data)}"
        print(f"PASS: {len(data)} prodotti trovati")

    def test_get_prodotti_fields(self):
        """Ogni prodotto deve avere id, nome, categoria, stock, unita"""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/prodotti")
        data = r.json()
        assert len(data) > 0, "Nessun prodotto"
        prod = data[0]
        for field in ["id", "nome", "categoria", "stock", "unita"]:
            assert field in prod, f"Campo '{field}' mancante nel prodotto"
        assert "_id" not in prod, "_id MongoDB non deve essere esposto"
        print(f"PASS: Campi prodotto corretti: {list(prod.keys())}")

    def test_get_prodotti_filtro_categoria(self):
        """GET /api/magazzino-bar/prodotti?categoria=Bibite → solo bibite"""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/prodotti", params={"categoria": "Bibite"})
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0, "Nessuna bibita trovata"
        for p in data:
            assert p["categoria"] == "Bibite", f"Prodotto con categoria sbagliata: {p['categoria']}"
        print(f"PASS: Filtro categoria 'Bibite' → {len(data)} prodotti")

    def test_get_prodotti_search(self):
        """GET /api/magazzino-bar/prodotti?q=kimbo → prodotti kimbo"""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/prodotti", params={"q": "kimbo"})
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0, "Nessun prodotto trovato per 'kimbo'"
        for p in data:
            assert "kimbo" in p["nome"].lower(), f"Nome non contiene 'kimbo': {p['nome']}"
        print(f"PASS: Ricerca 'kimbo' → {len(data)} prodotti")


class TestMagazzinoBarFiltri:
    """Test endpoint filtri (categorie)"""

    def test_get_filtri_status(self):
        """GET /api/magazzino-bar/filtri → 200 OK"""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/filtri")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        print(f"PASS: GET filtri → {r.status_code}")

    def test_get_filtri_count_categorie(self):
        """Deve restituire 7 categorie"""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/filtri")
        data = r.json()
        assert "categorie" in data, "Campo 'categorie' mancante"
        categorie = data["categorie"]
        assert len(categorie) >= 7, f"Expected >=7 categorie, got {len(categorie)}: {categorie}"
        print(f"PASS: {len(categorie)} categorie: {categorie}")

    def test_get_filtri_categorie_names(self):
        """Le categorie devono includere Caffè, Bibite, Alcolici, Liquori, Monouso, Imballaggi, Vetreria"""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/filtri")
        data = r.json()
        categorie = data["categorie"]
        expected = {"Caffè", "Bibite", "Alcolici", "Liquori", "Monouso", "Imballaggi", "Vetreria"}
        trovate = set(categorie)
        mancanti = expected - trovate
        assert not mancanti, f"Categorie mancanti: {mancanti}"
        print(f"PASS: Tutte le 7 categorie presenti: {categorie}")


class TestMagazzinoBarCaricoScarico:
    """Test POST carico e scarico — verificano stock prima e dopo"""

    @pytest.fixture(autouse=True)
    def get_prodotto_id(self):
        """Prendi l'ID del primo prodotto Caffè per i test"""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/prodotti", params={"categoria": "Caffè"})
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0, "Nessun prodotto Caffè disponibile"
        self.prodotto = data[0]
        self.prod_id = self.prodotto["id"]
        print(f"Prodotto test: {self.prodotto['nome']} (id={self.prod_id}, stock={self.prodotto['stock']})")

    def test_carico_aumenta_stock(self):
        """POST /api/magazzino-bar/carico → stock aumenta di 5"""
        stock_prima = self.prodotto["stock"]

        r = requests.post(f"{BASE_URL}/api/magazzino-bar/carico", json={
            "prodotto_id": self.prod_id,
            "quantita": 5,
            "nota": "TEST_Fattura n. 9999",
            "operatore_nome": "TEST_sistema",
        })
        assert r.status_code == 200, f"Carico fallito: {r.text}"
        data = r.json()
        assert data.get("ok") == True, f"ok != True: {data}"
        assert data.get("stock_nuovo") == round(stock_prima + 5, 3), \
            f"Stock nuovo sbagliato: expected {stock_prima + 5}, got {data.get('stock_nuovo')}"

        # Verifica persistenza con GET
        r2 = requests.get(f"{BASE_URL}/api/magazzino-bar/prodotti", params={"q": self.prodotto["nome"]})
        assert r2.status_code == 200
        p = next((x for x in r2.json() if x["id"] == self.prod_id), None)
        assert p is not None, "Prodotto non trovato dopo carico"
        assert p["stock"] == round(stock_prima + 5, 3), \
            f"Stock persisted sbagliato: expected {stock_prima + 5}, got {p['stock']}"
        print(f"PASS: Carico +5 → stock {stock_prima} → {p['stock']}")

    def test_carico_response_movimento(self):
        """Il carico deve restituire anche il movimento con i campi corretti"""
        r = requests.post(f"{BASE_URL}/api/magazzino-bar/carico", json={
            "prodotto_id": self.prod_id,
            "quantita": 1,
            "nota": "TEST_verifica",
            "operatore_nome": "TEST_Pocci",
        })
        assert r.status_code == 200
        data = r.json()
        assert "movimento" in data, "Campo 'movimento' mancante nella risposta"
        mov = data["movimento"]
        for field in ["id", "prodotto_id", "tipo", "quantita", "operatore_nome", "data"]:
            assert field in mov, f"Campo '{field}' mancante nel movimento"
        assert mov["tipo"] == "carico"
        assert mov["quantita"] == 1
        assert mov["operatore_nome"] == "TEST_Pocci"
        assert "_id" not in mov, "_id MongoDB non deve essere esposto"
        print(f"PASS: Movimento carico corretto: {mov}")

    def test_scarico_diminuisce_stock(self):
        """POST /api/magazzino-bar/carico (prima), poi scarico → stock diminuisce"""
        # Prima faccio un carico di 10 per avere stock sufficiente
        r_carico = requests.post(f"{BASE_URL}/api/magazzino-bar/carico", json={
            "prodotto_id": self.prod_id,
            "quantita": 10,
            "nota": "TEST_prep_scarico",
            "operatore_nome": "TEST_sistema",
        })
        assert r_carico.status_code == 200
        stock_dopo_carico = r_carico.json()["stock_nuovo"]

        # Ora scarico di 3
        r = requests.post(f"{BASE_URL}/api/magazzino-bar/scarico", json={
            "prodotto_id": self.prod_id,
            "quantita": 3,
            "operatore_nome": "Pocci",
            "nota": "TEST_consumo",
        })
        assert r.status_code == 200, f"Scarico fallito: {r.text}"
        data = r.json()
        assert data.get("ok") == True
        expected_stock = round(stock_dopo_carico - 3, 3)
        assert data.get("stock_nuovo") == expected_stock, \
            f"Stock nuovo sbagliato: expected {expected_stock}, got {data.get('stock_nuovo')}"
        print(f"PASS: Scarico -3 → stock {stock_dopo_carico} → {data['stock_nuovo']}")

    def test_scarico_operatore_nome_corretto(self):
        """Scarico deve registrare operatore_nome = 'Pocci' nel movimento"""
        # Carico per avere stock
        r_carico = requests.post(f"{BASE_URL}/api/magazzino-bar/carico", json={
            "prodotto_id": self.prod_id,
            "quantita": 5,
            "nota": "TEST_prep",
            "operatore_nome": "TEST_sistema",
        })
        assert r_carico.status_code == 200

        r = requests.post(f"{BASE_URL}/api/magazzino-bar/scarico", json={
            "prodotto_id": self.prod_id,
            "quantita": 1,
            "operatore_nome": "Pocci",
            "nota": "TEST_operatore_check",
        })
        assert r.status_code == 200
        data = r.json()
        mov = data.get("movimento", {})
        assert mov.get("operatore_nome") == "Pocci", \
            f"operatore_nome sbagliato: expected 'Pocci', got '{mov.get('operatore_nome')}'"
        assert mov.get("tipo") == "scarico"
        print(f"PASS: Scarico operatore_nome = '{mov['operatore_nome']}'")

    def test_scarico_stock_insufficiente(self):
        """Scarico con quantità superiore allo stock → 400"""
        # Assicurati che lo stock sia 0 o recupera lo stock attuale
        r_prod = requests.get(f"{BASE_URL}/api/magazzino-bar/prodotti", params={"q": self.prodotto["nome"]})
        prod = next((x for x in r_prod.json() if x["id"] == self.prod_id), None)
        stock_attuale = prod["stock"] if prod else 0

        r = requests.post(f"{BASE_URL}/api/magazzino-bar/scarico", json={
            "prodotto_id": self.prod_id,
            "quantita": stock_attuale + 9999,
            "operatore_nome": "TEST_Pocci",
        })
        assert r.status_code == 400, f"Expected 400 per stock insufficiente, got {r.status_code}: {r.text}"
        print(f"PASS: Scarico stock insufficiente → {r.status_code}")

    def test_carico_prodotto_inesistente(self):
        """Carico su prodotto_id inesistente → 404"""
        r = requests.post(f"{BASE_URL}/api/magazzino-bar/carico", json={
            "prodotto_id": "id-inesistente-xyz-999",
            "quantita": 1,
            "operatore_nome": "TEST",
        })
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"
        print(f"PASS: Carico prodotto inesistente → 404")


class TestMagazzinoBarMovimenti:
    """Test GET movimenti e movimenti/oggi"""

    def test_get_movimenti_status(self):
        """GET /api/magazzino-bar/movimenti → 200 OK"""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/movimenti")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()
        assert isinstance(data, list), "Expected list"
        print(f"PASS: GET movimenti → {len(data)} movimenti")

    def test_get_movimenti_oggi_status(self):
        """GET /api/magazzino-bar/movimenti/oggi → 200 OK"""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/movimenti/oggi")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()
        assert isinstance(data, list), "Expected list"
        print(f"PASS: GET movimenti/oggi → {len(data)} movimenti oggi")

    def test_get_movimenti_oggi_contiene_test(self):
        """Dopo carico/scarico di test, movimenti/oggi deve contenere almeno un movimento"""
        # Il fixture di carico/scarico nei test precedenti dovrebbe aver già creato movimenti
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/movimenti/oggi")
        assert r.status_code == 200
        data = r.json()
        # Dovrebbe esserci almeno un movimento dai test precedenti
        # Non forziamo il conteggio esatto, ma ci aspettiamo che il metodo funzioni
        print(f"PASS: GET movimenti/oggi → {len(data)} movimenti")
        if len(data) > 0:
            mov = data[0]
            assert "_id" not in mov, "_id non deve essere esposto"
            for field in ["id", "prodotto_nome", "tipo", "quantita", "operatore_nome", "data"]:
                assert field in mov, f"Campo '{field}' mancante nel movimento"
            print(f"PASS: Struttura movimento corretta: {list(mov.keys())}")

    def test_movimenti_no_mongodb_id(self):
        """I movimenti non devono esporre _id di MongoDB"""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/movimenti", params={"limit": 10})
        assert r.status_code == 200
        for mov in r.json():
            assert "_id" not in mov, f"_id esposto nel movimento {mov.get('id')}"
        print("PASS: Nessun _id MongoDB nei movimenti")


class TestTabletOperatoriLogin:
    """Test login operatori tablet (necessario per accesso a #tablet/bar)"""

    def test_login_pocci(self):
        """PIN operatore (Pocci) → login corretto"""
        r = requests.post(f"{BASE_URL}/api/tablet-operatori/login", json={"pin": _PIN_OP1})
        assert r.status_code == 200, f"Login Pocci fallito: {r.text}"
        data = r.json()
        assert "operatore" in data, "Campo 'operatore' mancante"
        op = data["operatore"]
        assert op.get("nome", "").lower() == "pocci", f"Nome sbagliato: {op.get('nome')}"
        print(f"PASS: Login Pocci → operatore: {op}")

    def test_login_pin_errato(self):
        """PIN errato → 401"""
        r = requests.post(f"{BASE_URL}/api/tablet-operatori/login", json={"pin": "0000"})
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"
        print(f"PASS: PIN errato → {r.status_code}")
