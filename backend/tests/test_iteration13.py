"""
Test completo per iterazione 13 - ERP Food Cost Portal
Testa: health, tracciabilità (/api/tr/*), fornitori CRUD, commercialista,
       alias routes per mini-site CRA (/api/supervisor/stato)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL non impostata")


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# =============================================
# HEALTH CHECK
# =============================================

class TestHealth:
    """Backend health check"""

    def test_health_200(self, session):
        r = session.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200, f"Health failed: {r.text}"


# =============================================
# TRACCIABILITÀ — /api/tr/*
# =============================================

class TestTracciabilita:
    """Router tracciabilità con prefisso /api/tr"""

    def test_supervisor_stato(self, session):
        r = session.get(f"{BASE_URL}/api/tr/supervisor/stato")
        assert r.status_code == 200, f"supervisor/stato: {r.text}"
        data = r.json()
        # Verifica che sia un oggetto (dict)
        assert isinstance(data, dict), f"Risposta non è un dict: {type(data)}"

    def test_stats(self, session):
        r = session.get(f"{BASE_URL}/api/tr/stats")
        assert r.status_code == 200, f"stats: {r.text}"
        data = r.json()
        assert isinstance(data, dict)
        # Verifica campi principali
        assert "ricette" in data or "lotti_totali" in data, f"Campi mancanti: {list(data.keys())}"

    def test_lotti_list(self, session):
        r = session.get(f"{BASE_URL}/api/tr/lotti")
        assert r.status_code == 200, f"lotti: {r.text}"
        data = r.json()
        # Può essere lista o dict con chiave 'lotti'
        if isinstance(data, dict):
            items = data.get('lotti', [])
        else:
            items = data
        assert isinstance(items, list), f"Lotti non è una lista: {type(items)}"

    def test_produzioni_list(self, session):
        r = session.get(f"{BASE_URL}/api/tr/produzioni/")
        assert r.status_code == 200, f"produzioni: {r.text}"
        data = r.json()
        if isinstance(data, dict):
            items = data.get('produzioni', [])
        else:
            items = data
        assert isinstance(items, list), f"Produzioni non è una lista: {type(items)}"

    def test_fatture_list(self, session):
        r = session.get(f"{BASE_URL}/api/tr/fatture")
        assert r.status_code == 200, f"fatture HACCP: {r.text}"
        data = r.json()
        if isinstance(data, dict):
            items = data.get('fatture', [])
        else:
            items = data
        assert isinstance(items, list)

    def test_lotti_delete_first(self, session):
        """Prende il primo lotto dalla lista e lo elimina"""
        r = session.get(f"{BASE_URL}/api/tr/lotti")
        assert r.status_code == 200
        data = r.json()
        items = data.get('lotti', data) if isinstance(data, dict) else data
        if not items:
            pytest.skip("Nessun lotto disponibile per il test DELETE")
        first_id = items[0].get('id') or items[0].get('_id')
        assert first_id, "Nessun ID trovato nel primo lotto"

        del_r = session.delete(f"{BASE_URL}/api/tr/lotti/{first_id}")
        assert del_r.status_code in [200, 204], f"DELETE lotto fallito: {del_r.status_code} {del_r.text}"

        # Verifica che non esiste più (se API di GET singolo disponibile)
        # GET lista e controlla che non c'è più
        r2 = session.get(f"{BASE_URL}/api/tr/lotti")
        data2 = r2.json()
        items2 = data2.get('lotti', data2) if isinstance(data2, dict) else data2
        ids_after = [item.get('id') or item.get('_id') for item in items2]
        assert first_id not in ids_after, f"Lotto {first_id} ancora presente dopo DELETE"


# =============================================
# ALIAS ROUTES — mini-site CRA
# =============================================

class TestAliasRoutes:
    """
    La mini-site CRA usa i vecchi path (senza /tr/).
    Se fixati, questi devono rispondere 200. Se non fixati, 404.
    """

    def test_old_supervisor_stato_alias(self, session):
        """Verifica se /api/supervisor/stato è un alias di /api/tr/supervisor/stato"""
        r = session.get(f"{BASE_URL}/api/supervisor/stato")
        # NOTA: questo DOVREBBE essere 200 se il fix è stato applicato
        # se è 404 il fix NON è ancora applicato
        if r.status_code == 404:
            pytest.fail(
                "ALIAS NON APPLICATO: /api/supervisor/stato → 404. "
                "La mini-site CRA non funzionerà correttamente. "
                "Fix: aggiungere route alias in main.py"
            )
        assert r.status_code == 200, f"Alias supervisor/stato: {r.status_code}"

    def test_old_haccp_auto_verifica_alias(self, session):
        """Verifica se /api/haccp-auto/verifica-oggi è un alias"""
        r = session.get(f"{BASE_URL}/api/haccp-auto/verifica-oggi")
        if r.status_code == 404:
            pytest.fail(
                "ALIAS NON APPLICATO: /api/haccp-auto/verifica-oggi → 404. "
                "La mini-site CRA non funzionerà correttamente."
            )
        assert r.status_code == 200, f"Alias haccp-auto: {r.status_code}"


# =============================================
# FORNITORI — /api/suppliers
# =============================================

class TestFornitori:
    """CRUD Fornitori"""

    @pytest.fixture(scope="class")
    def test_supplier_id(self, session):
        """Crea un fornitore di test e lo elimina alla fine"""
        # CREATE
        payload = {
            "ragione_sociale": "TEST_ITER13_Fornitore SRL",
            "denominazione": "TEST_ITER13_Fornitore SRL",
            "partita_iva": "99988877701",
            "email": "test_iter13@example.com",
            "metodo_pagamento": "bonifico",
            "giorni_pagamento": 30,
            "esclude_magazzino": True,
            "escludi_da_tracciabilita": True,
            "note": "Test iterazione 13 - DA ELIMINARE"
        }
        r = session.post(f"{BASE_URL}/api/suppliers", json=payload)
        assert r.status_code in [200, 201], f"Create supplier: {r.status_code} {r.text}"
        data = r.json()
        sid = data.get('id') or data.get('_id')
        assert sid, f"Nessun ID nel risposta: {data}"
        yield sid
        # CLEANUP
        session.delete(f"{BASE_URL}/api/suppliers/{sid}?force=true")

    def test_list_suppliers(self, session):
        r = session.get(f"{BASE_URL}/api/suppliers")
        assert r.status_code == 200, f"List suppliers: {r.text}"
        data = r.json()
        assert isinstance(data, list), f"Non è una lista: {type(data)}"

    def test_create_and_persist_flags(self, session, test_supplier_id):
        """Verifica che i flag escludi_da_tracciabilita e esclude_magazzino siano persistiti"""
        r = session.get(f"{BASE_URL}/api/suppliers/{test_supplier_id}")
        assert r.status_code == 200, f"GET supplier: {r.text}"
        data = r.json()
        # Verifica campi critici
        assert data.get('escludi_da_tracciabilita'), \
            f"escludi_da_tracciabilita non persistito: {data.get('escludi_da_tracciabilita')}"
        assert data.get('esclude_magazzino'), \
            f"esclude_magazzino non persistito: {data.get('esclude_magazzino')}"

    def test_update_supplier(self, session, test_supplier_id):
        """Aggiorna il fornitore e verifica la persistenza"""
        update_payload = {"giorni_pagamento": 60, "metodo_pagamento": "riba"}
        r = session.put(f"{BASE_URL}/api/suppliers/{test_supplier_id}", json=update_payload)
        assert r.status_code == 200, f"UPDATE supplier: {r.status_code} {r.text}"

        # Verifica via GET
        r2 = session.get(f"{BASE_URL}/api/suppliers/{test_supplier_id}")
        data = r2.json()
        assert data.get('giorni_pagamento') == 60, f"giorni_pagamento non aggiornato: {data}"
        assert data.get('metodo_pagamento') == 'riba', f"metodo_pagamento non aggiornato: {data}"

    def test_delete_supplier(self, session, test_supplier_id):
        """Elimina il fornitore e verifica rimozione"""
        r = session.delete(f"{BASE_URL}/api/suppliers/{test_supplier_id}?force=true")
        assert r.status_code in [200, 204], f"DELETE supplier: {r.status_code} {r.text}"

        # Verifica 404
        r2 = session.get(f"{BASE_URL}/api/suppliers/{test_supplier_id}")
        assert r2.status_code == 404, f"Fornitore ancora presente dopo DELETE: {r2.status_code}"


# =============================================
# COMMERCIALISTA
# =============================================

class TestCommercialista:
    """API commercialista"""

    def test_config(self, session):
        r = session.get(f"{BASE_URL}/api/commercialista/config")
        assert r.status_code == 200, f"config: {r.text}"
        data = r.json()
        assert 'email' in data, f"Manca campo 'email': {data}"

    def test_alert_status(self, session):
        r = session.get(f"{BASE_URL}/api/commercialista/alert-status")
        assert r.status_code == 200, f"alert-status: {r.text}"
        data = r.json()
        assert 'show_alert' in data, f"Manca campo 'show_alert': {data}"

    def test_log(self, session):
        r = session.get(f"{BASE_URL}/api/commercialista/log?limit=5")
        assert r.status_code == 200, f"log: {r.text}"
        data = r.json()
        assert 'log' in data or isinstance(data, list), f"Struttura inattesa: {data}"

    def test_prima_nota_cassa(self, session):
        r = session.get(f"{BASE_URL}/api/commercialista/prima-nota-cassa/2025/1")
        assert r.status_code == 200, f"prima-nota-cassa: {r.text}"

    def test_fatture_cassa(self, session):
        r = session.get(f"{BASE_URL}/api/commercialista/fatture-cassa/2025/1")
        assert r.status_code == 200, f"fatture-cassa: {r.text}"


# =============================================
# MAGAZZINO / WAREHOUSE
# =============================================

class TestMagazzino:
    """API magazzino base"""

    def test_products_list(self, session):
        r = session.get(f"{BASE_URL}/api/warehouse/products")
        assert r.status_code == 200, f"warehouse/products: {r.text}"

    def test_fatture_ciclo_passivo(self, session):
        r = session.get(f"{BASE_URL}/api/invoices")
        assert r.status_code == 200, f"invoices: {r.text}"


# =============================================
# DASHBOARD
# =============================================

class TestDashboard:
    """Dashboard API base"""

    def test_dashboard_stats(self, session):
        # prova vari endpoint dashboard comuni
        r = session.get(f"{BASE_URL}/api/dashboard/stats")
        # accettiamo anche 404 se non esiste, ma non 500
        assert r.status_code in [200, 404], f"Dashboard stats: {r.status_code} {r.text}"

    def test_invoices_list(self, session):
        r = session.get(f"{BASE_URL}/api/invoices?limit=10")
        assert r.status_code == 200, f"invoices: {r.text}"
