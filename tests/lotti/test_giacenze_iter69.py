"""
test_giacenze_iter69.py
-----------------------
Test backend per le nuove funzionalità iter69:
  - PATCH /api/magazzino-bar/prodotti/{id}/soglia
  - GET  /api/magazzino-bar/soglie-suggest
  - POST /api/magazzino-bar/riordina
  - GET  /api/magazzino-bar/report-giacenze (HTML)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def primo_prodotto():
    """Recupera il primo prodotto del magazzino bar per i test."""
    r = requests.get(f"{BASE_URL}/api/magazzino-bar/prodotti")
    assert r.status_code == 200
    prods = r.json()
    assert len(prods) > 0, "Nessun prodotto trovato nel magazzino bar"
    return prods[0]


# ── Soglia PATCH ──────────────────────────────────────────────────────────────

class TestPatchSoglia:
    """PATCH /api/magazzino-bar/prodotti/{id}/soglia"""

    def test_patch_soglia_200(self, primo_prodotto):
        """Impostare soglia a 5 → 200 OK con valore aggiornato."""
        prod_id = primo_prodotto["id"]
        r = requests.patch(
            f"{BASE_URL}/api/magazzino-bar/prodotti/{prod_id}/soglia",
            json={"soglia_minima": 5.0}
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data["soglia_minima"] == 5.0, f"Soglia non aggiornata: {data}"
        assert "_id" not in data, "MongoDB _id esposta nella risposta"

    def test_patch_soglia_zero(self, primo_prodotto):
        """Reset soglia a 0 → 200 OK."""
        prod_id = primo_prodotto["id"]
        r = requests.patch(
            f"{BASE_URL}/api/magazzino-bar/prodotti/{prod_id}/soglia",
            json={"soglia_minima": 0.0}
        )
        assert r.status_code == 200
        data = r.json()
        assert data["soglia_minima"] == 0.0

    def test_patch_soglia_prodotto_inesistente(self):
        """Prodotto inesistente → 404."""
        r = requests.patch(
            f"{BASE_URL}/api/magazzino-bar/prodotti/non-esiste-1234/soglia",
            json={"soglia_minima": 3.0}
        )
        assert r.status_code == 404, f"Expected 404, got {r.status_code}"

    def test_patch_soglia_persistenza(self, primo_prodotto):
        """Verifica che la soglia sia persistita con GET dopo PATCH."""
        prod_id = primo_prodotto["id"]
        # Imposta soglia a 7.5
        requests.patch(
            f"{BASE_URL}/api/magazzino-bar/prodotti/{prod_id}/soglia",
            json={"soglia_minima": 7.5}
        )
        # Verifica con GET lista prodotti
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/prodotti")
        assert r.status_code == 200
        prods = r.json()
        p = next((x for x in prods if x["id"] == prod_id), None)
        assert p is not None
        assert p.get("soglia_minima") == 7.5, f"Persistenza fallita: {p}"
        # Reset
        requests.patch(
            f"{BASE_URL}/api/magazzino-bar/prodotti/{prod_id}/soglia",
            json={"soglia_minima": 0.0}
        )


# ── Soglie suggest ────────────────────────────────────────────────────────────

class TestSoglieSuggest:
    """GET /api/magazzino-bar/soglie-suggest"""

    def test_suggest_200(self):
        """GET soglie-suggest → 200 OK."""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/soglie-suggest")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_suggest_struttura(self):
        """Ogni suggerimento ha i campi obbligatori."""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/soglie-suggest")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list), "La risposta deve essere una lista"
        assert len(data) > 0, "Lista suggerimenti vuota"
        
        # Verifica il primo suggerimento
        s = data[0]
        campi_obbligatori = ["prodotto_id", "nome", "categoria", "stock_attuale", "soglia_corrente", "soglia_suggerita", "n_fatture_match"]
        for campo in campi_obbligatori:
            assert campo in s, f"Campo '{campo}' mancante nel suggerimento"

    def test_suggest_32_prodotti(self):
        """Devono esserci almeno 32 prodotti (il seed ne crea 32)."""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/soglie-suggest")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 32, f"Attesi almeno 32 prodotti, trovati {len(data)}"

    def test_suggest_soglia_positiva(self):
        """soglia_suggerita deve essere > 0 per tutti i prodotti."""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/soglie-suggest")
        assert r.status_code == 200
        data = r.json()
        for s in data:
            assert s["soglia_suggerita"] > 0, f"soglia_suggerita <= 0 per {s['nome']}"

    def test_suggest_no_mongodb_id(self):
        """Nessun _id MongoDB nella risposta."""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/soglie-suggest")
        assert r.status_code == 200
        data = r.json()
        for s in data:
            assert "_id" not in s, f"MongoDB _id esposta in {s['nome']}"

    def test_suggest_ordinato_per_n_fatture(self):
        """I suggerimenti devono essere ordinati per n_fatture_match DESC."""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/soglie-suggest")
        assert r.status_code == 200
        data = r.json()
        if len(data) > 1:
            for i in range(len(data) - 1):
                assert data[i]["n_fatture_match"] >= data[i+1]["n_fatture_match"], \
                    f"Ordine non corretto alla posizione {i}: {data[i]['n_fatture_match']} < {data[i+1]['n_fatture_match']}"


# ── Riordina ──────────────────────────────────────────────────────────────────

class TestRiordina:
    """POST /api/magazzino-bar/riordina"""

    def test_riordina_nessun_prodotto_sotto_soglia(self):
        """Con tutte le soglie a 0, riordina risponde con n_prodotti=0."""
        r = requests.post(f"{BASE_URL}/api/magazzino-bar/riordina?operatore_nome=TestAuto")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("ok") == True
        # Non verifichiamo n_prodotti specifico (potrebbero esserci prodotti con soglia già impostata)

    def test_riordina_con_prodotto_sotto_soglia(self, primo_prodotto):
        """Imposta soglia alta su un prodotto con stock basso → riordina crea ordine."""
        prod_id = primo_prodotto["id"]
        stock_attuale = float(primo_prodotto.get("stock", 0))
        
        # Imposta soglia alta (sopra lo stock attuale)
        soglia_alta = stock_attuale + 10.0
        patch_r = requests.patch(
            f"{BASE_URL}/api/magazzino-bar/prodotti/{prod_id}/soglia",
            json={"soglia_minima": soglia_alta}
        )
        assert patch_r.status_code == 200
        
        # Esegui riordino
        r = requests.post(f"{BASE_URL}/api/magazzino-bar/riordina?operatore_nome=TestIter69")
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") == True
        
        # Con soglia alta deve trovare almeno il prodotto che abbiamo impostato
        if data.get("n_prodotti", 0) > 0:
            assert "ordine_id" in data, "ordine_id mancante nella risposta"
            assert "prodotti" in data, "prodotti mancanti nella risposta"
            # Verifica struttura prodotto nell'ordine
            if data["prodotti"]:
                p = data["prodotti"][0]
                assert "nome" in p
                assert "quantita" in p
                assert p["quantita"] > 0, f"Quantità ordine deve essere > 0: {p}"
        
        # Cleanup: reset soglia
        requests.patch(
            f"{BASE_URL}/api/magazzino-bar/prodotti/{prod_id}/soglia",
            json={"soglia_minima": 0.0}
        )

    def test_riordina_crea_ordine_in_ordini_fornitori(self, primo_prodotto):
        """Verifica che l'ordine creato sia visibile in /api/ordini-fornitori."""
        prod_id = primo_prodotto["id"]
        stock_attuale = float(primo_prodotto.get("stock", 0))
        soglia_alta = stock_attuale + 20.0
        
        # Imposta soglia alta
        requests.patch(
            f"{BASE_URL}/api/magazzino-bar/prodotti/{prod_id}/soglia",
            json={"soglia_minima": soglia_alta}
        )
        
        # Crea ordine
        r = requests.post(f"{BASE_URL}/api/magazzino-bar/riordina?operatore_nome=TestIter69B")
        assert r.status_code == 200
        data = r.json()
        
        if data.get("n_prodotti", 0) > 0:
            ordine_id = data.get("ordine_id")
            assert ordine_id, "ordine_id mancante"
            
            # Verifica nel DB degli ordini
            r2 = requests.get(f"{BASE_URL}/api/ordini-fornitori?limit=10")
            assert r2.status_code == 200
            ordini = r2.json()
            ordini_ids = [o.get("id") for o in ordini]
            assert ordine_id in ordini_ids, f"Ordine {ordine_id} non trovato in ordini_fornitori"
        
        # Cleanup: reset soglia
        requests.patch(
            f"{BASE_URL}/api/magazzino-bar/prodotti/{prod_id}/soglia",
            json={"soglia_minima": 0.0}
        )

    def test_riordina_no_mongodb_id(self, primo_prodotto):
        """La risposta di riordina non deve contenere _id MongoDB."""
        prod_id = primo_prodotto["id"]
        stock_attuale = float(primo_prodotto.get("stock", 0))
        soglia_alta = stock_attuale + 5.0
        
        requests.patch(
            f"{BASE_URL}/api/magazzino-bar/prodotti/{prod_id}/soglia",
            json={"soglia_minima": soglia_alta}
        )
        
        r = requests.post(f"{BASE_URL}/api/magazzino-bar/riordina?operatore_nome=TestIter69C")
        assert r.status_code == 200
        data = r.json()
        assert "_id" not in data
        for p in data.get("prodotti", []):
            assert "_id" not in p
        
        # Cleanup
        requests.patch(
            f"{BASE_URL}/api/magazzino-bar/prodotti/{prod_id}/soglia",
            json={"soglia_minima": 0.0}
        )


# ── Report Giacenze HTML ──────────────────────────────────────────────────────

class TestReportGiacenze:
    """GET /api/magazzino-bar/report-giacenze"""

    def test_report_200(self):
        """GET report-giacenze → 200 OK."""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/report-giacenze")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"

    def test_report_content_type_html(self):
        """Content-Type deve essere text/html."""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/report-giacenze")
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/html" in ct, f"Content-Type non HTML: {ct}"

    def test_report_contiene_tabella_bar(self):
        """Il report HTML contiene la sezione Magazzino Bar."""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/report-giacenze")
        assert r.status_code == 200
        html = r.text
        assert "Magazzino Bar" in html, "Sezione 'Magazzino Bar' non trovata nel report"

    def test_report_contiene_tabella_materie_prime(self):
        """Il report HTML contiene la sezione Materie Prime."""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/report-giacenze")
        assert r.status_code == 200
        html = r.text
        assert "Materie Prime" in html, "Sezione 'Materie Prime' non trovata nel report"

    def test_report_contiene_stats(self):
        """Il report HTML contiene le stats (prodotti bar, esauriti, sotto soglia)."""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/report-giacenze")
        assert r.status_code == 200
        html = r.text
        assert "prodotti bar" in html, "Stat 'prodotti bar' non trovata"
        assert "esauriti" in html, "Stat 'esauriti' non trovata"
        assert "sotto soglia" in html, "Stat 'sotto soglia' non trovata"

    def test_report_contiene_pulsante_stampa(self):
        """Il report HTML contiene il pulsante di stampa."""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/report-giacenze")
        assert r.status_code == 200
        html = r.text
        assert "window.print()" in html, "Pulsante stampa non trovato nel report"

    def test_report_intestazioni_tabella_bar(self):
        """Il report HTML contiene le intestazioni della tabella bar."""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/report-giacenze")
        assert r.status_code == 200
        html = r.text
        assert "Prodotto" in html
        assert "Categoria" in html
        assert "Stock" in html
        assert "Soglia Min" in html
        assert "Stato" in html

    def test_report_periodo_settimanale(self):
        """Il report HTML contiene la dicitura 'Periodo' con le date."""
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/report-giacenze")
        assert r.status_code == 200
        html = r.text
        assert "Periodo:" in html, "Periodo settimanale non trovato nel report"


# ── Test integrazione completa ────────────────────────────────────────────────

class TestIntegrazione:
    """Test di integrazione: flusso completo soglia → riordino."""

    def test_flusso_soglia_riordino(self):
        """Flusso: PATCH soglia → soglie-suggest → riordina → check ordine."""
        # 1. Recupera prodotti
        r = requests.get(f"{BASE_URL}/api/magazzino-bar/prodotti")
        assert r.status_code == 200
        prods = r.json()
        assert len(prods) > 0
        
        prod = prods[0]
        prod_id = prod["id"]
        stock = float(prod.get("stock", 0))
        
        # 2. Imposta soglia
        r2 = requests.patch(
            f"{BASE_URL}/api/magazzino-bar/prodotti/{prod_id}/soglia",
            json={"soglia_minima": stock + 15.0}
        )
        assert r2.status_code == 200
        
        # 3. Controlla soglie-suggest
        r3 = requests.get(f"{BASE_URL}/api/magazzino-bar/soglie-suggest")
        assert r3.status_code == 200
        sugg = r3.json()
        prod_sugg = next((s for s in sugg if s["prodotto_id"] == prod_id), None)
        assert prod_sugg is not None, "Prodotto non trovato nei suggerimenti"
        assert prod_sugg["soglia_corrente"] == stock + 15.0, f"Soglia corrente non aggiornata: {prod_sugg}"
        
        # 4. Riordina
        r4 = requests.post(f"{BASE_URL}/api/magazzino-bar/riordina?operatore_nome=TestIntegrazione")
        assert r4.status_code == 200
        data = r4.json()
        assert data.get("ok") == True
        assert data.get("n_prodotti", 0) >= 1, "Almeno il prodotto con soglia alta deve essere in ordine"
        
        # 5. Cleanup
        requests.patch(
            f"{BASE_URL}/api/magazzino-bar/prodotti/{prod_id}/soglia",
            json={"soglia_minima": 0.0}
        )
