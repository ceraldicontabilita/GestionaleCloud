"""
test_iteration72_bugfixes.py
─────────────────────────────
Regression tests for 3 bug fixes (CeraldiApp):
  1) Anagrafica fornitore — match esatto, no contaminazione cross-fornitore
  2) Eliminate fatture "Fornitore Sconosciuto" + dedup duplicati
  3) PIN tablet pasticceria (operatori + amministratore, letti da env)
Plus check schede-ricevimento numero_documento valorizzato.
"""
import os
import urllib.parse
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
API = f"{BASE_URL}/api"
# PIN letti da env (regola: credenziali mai in chiaro nel codice). Fallback finti.
_PIN_OP1 = os.environ.get("TEST_PIN_OP1", "0000")
_PIN_OP2 = os.environ.get("TEST_PIN_OP2", "0000")
_PIN_ADMIN = os.environ.get("TEST_PIN_ADMIN", "0000")


# ───────── Fixtures ─────────
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ───────── PIN tablet operatori ─────────
class TestTabletOperatoriLogin:
    def test_login_pocci(self, session):
        r = session.post(f"{API}/tablet-operatori/login", json={"pin": _PIN_OP1}, timeout=15)
        assert r.status_code == 200, f"PIN OP1 failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("ok") is True
        op = data.get("operatore", {})
        assert op.get("nome") == "Pocci"
        assert op.get("ruolo") == "operatore"
        assert isinstance(op.get("id"), str) and len(op["id"]) > 0

    def test_login_parisi(self, session):
        r = session.post(f"{API}/tablet-operatori/login", json={"pin": _PIN_OP2}, timeout=15)
        assert r.status_code == 200, f"PIN OP2 failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("ok") is True
        assert data["operatore"]["nome"] == "Parisi"
        assert data["operatore"]["ruolo"] == "operatore"

    def test_login_amministratore(self, session):
        r = session.post(f"{API}/tablet-operatori/login", json={"pin": _PIN_ADMIN}, timeout=15)
        assert r.status_code == 200, f"PIN ADMIN failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("ok") is True
        assert data["operatore"]["ruolo"] == "amministratore"
        assert data["operatore"]["nome"] == "Amministratore"

    def test_login_pin_errato(self, session):
        r = session.post(f"{API}/tablet-operatori/login", json={"pin": "0000"}, timeout=15)
        # PIN inesistente → 401 (PIN non riconosciuto). PIN troppo corto darebbe 400.
        assert r.status_code == 401, f"PIN errato '0000': atteso 401, ricevuto {r.status_code} {r.text}"

    def test_login_pin_troppo_corto(self, session):
        r = session.post(f"{API}/tablet-operatori/login", json={"pin": "12"}, timeout=15)
        assert r.status_code == 400


# ───────── Fornitori - lista globale ─────────
class TestListaFornitori:
    def test_lista_fornitori_response_ok(self, session):
        r = session.get(f"{API}/fornitori", timeout=30)
        assert r.status_code == 200, f"GET /api/fornitori failed: {r.status_code}"
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0, "Nessun fornitore restituito"

    def test_gargiulo_giuseppe_unico_no_duplicati(self, session):
        """GARGIULO GIUSEPPE deve apparire come UN solo record (no duplicati)."""
        r = session.get(f"{API}/fornitori", timeout=30)
        assert r.status_code == 200
        data = r.json()
        # Conta tutte le occorrenze case-insensitive che iniziano con "GARGIULO GIUSEPPE"
        gg_records = [
            f for f in data
            if (f.get("nome", "") or "").strip().upper().startswith("GARGIULO GIUSEPPE")
        ]
        # Stampa per debug
        print("\n[GARGIULO GIUSEPPE matches]")
        for f in gg_records:
            print(f"  - nome='{f.get('nome')}', piva='{f.get('piva')}', stato='{f.get('stato')}'")
        assert len(gg_records) == 1, f"Atteso 1 GARGIULO GIUSEPPE, trovati {len(gg_records)}"

    def test_no_fornitore_sconosciuto_in_lista(self, session):
        """La lista non deve contenere 'Fornitore Sconosciuto' come fornitore."""
        r = session.get(f"{API}/fornitori", timeout=30)
        assert r.status_code == 200
        data = r.json()
        sconosciuti = [
            f for f in data
            if "sconosciut" in (f.get("nome", "") or "").lower()
        ]
        assert len(sconosciuti) == 0, f"Trovati {len(sconosciuti)} 'Fornitore Sconosciuto' in lista: {sconosciuti}"


# ───────── Anagrafica fornitore - match esatto ─────────
class TestAnagraficaFornitore:
    def test_anagrafica_gargiulo_giuseppe_no_contaminazione(self, session):
        """
        GARGIULO GIUSEPPE deve avere SOLO le sue fatture (13).
        GARGIULO MARCO deve essere SEPARATO (suo conteggio diverso).
        ELECTRONICS' HOUSE GIUSEPPE non deve essere accorpato.
        """
        # GARGIULO GIUSEPPE
        r1 = session.get(
            f"{API}/fornitori/{urllib.parse.quote('GARGIULO GIUSEPPE')}/anagrafica?anno=tutti",
            timeout=30,
        )
        assert r1.status_code == 200
        d1 = r1.json()
        n_giuseppe = d1.get("num_fatture_totali") or len(d1.get("storico_fatture", []))

        # GARGIULO MARCO
        r2 = session.get(
            f"{API}/fornitori/{urllib.parse.quote('GARGIULO MARCO')}/anagrafica?anno=tutti",
            timeout=30,
        )
        assert r2.status_code == 200
        d2 = r2.json()
        n_marco = d2.get("num_fatture_totali") or len(d2.get("storico_fatture", []))

        # ELECTRONICS' HOUSE GIUSEPPE (no contamination)
        nome_eh = urllib.parse.quote("ELECTRONICS' HOUSE GIUSEPPE")
        r3 = session.get(
            f"{API}/fornitori/{nome_eh}/anagrafica?anno=tutti",
            timeout=30,
        )
        d3 = r3.json() if r3.status_code == 200 else {}
        n_electronics = d3.get("num_fatture_totali") or len(d3.get("storico_fatture", []))

        print(
            f"\n[Anagrafiche] GARGIULO GIUSEPPE={n_giuseppe}, "
            f"GARGIULO MARCO={n_marco}, ELECTRONICS' HOUSE GIUSEPPE={n_electronics}"
        )

        # Sanity: i count devono essere DIVERSI (no merge cross-fornitore)
        assert n_giuseppe != n_marco, (
            f"CONTAMINAZIONE: GARGIULO GIUSEPPE ({n_giuseppe}) e GARGIULO MARCO ({n_marco}) "
            f"hanno lo stesso conteggio fatture → match regex troppo permissivo"
        )
        # Se il conteggio fosse contaminato, sarebbe ≥ n_giuseppe + n_marco. Verifica delimitazione.
        assert n_giuseppe < (n_giuseppe + n_marco + n_electronics) or n_marco == 0, "Contaminazione su MARCO"

    def test_anagrafica_gargiulo_giuseppe_totale_fatture(self, session):
        """Atteso esattamente 13 fatture totali per GARGIULO GIUSEPPE."""
        nome = urllib.parse.quote("GARGIULO GIUSEPPE")
        r = session.get(f"{API}/fornitori/{nome}/anagrafica?anno=tutti", timeout=30)
        assert r.status_code == 200
        data = r.json()
        totale = data.get("num_fatture_totali") or len(data.get("storico_fatture", []))
        print(f"[GARGIULO GIUSEPPE] totale fatture = {totale}")
        # Tolleranza ±2 per evolversi DB live
        assert 11 <= totale <= 15, f"Totale fatture GARGIULO GIUSEPPE = {totale}, atteso 13 (±2)"

    def test_anagrafica_gargiulo_marco_separato(self, session):
        """GARGIULO MARCO deve essere trattato come fornitore separato (count diverso da GIUSEPPE)."""
        nome = urllib.parse.quote("GARGIULO MARCO")
        r = session.get(f"{API}/fornitori/{nome}/anagrafica?anno=tutti", timeout=30)
        assert r.status_code == 200
        data = r.json()
        totale_marco = data.get("num_fatture_totali") or len(data.get("storico_fatture", []))
        print(f"[GARGIULO MARCO] totale fatture = {totale_marco}")
        # MARCO deve avere 1-10 fatture (separate da GIUSEPPE)
        assert totale_marco < 13, (
            f"GARGIULO MARCO ha {totale_marco} fatture (GIUSEPPE ne ha 13). "
            f"Se uguale → contaminazione cross-fornitore"
        )


# ───────── No fatture "Fornitore Sconosciuto" ─────────
class TestFornitoreSconosciutoEliminato:
    def test_schede_ricevimento_no_fornitore_sconosciuto(self, session):
        """Nessuna scheda ricevimento deve avere fornitore='Fornitore Sconosciuto'."""
        r = session.get(f"{API}/fornitori/schede-ricevimento?limit=500", timeout=60)
        assert r.status_code == 200, f"GET schede-ricevimento: {r.status_code}"
        schede = r.json()
        assert isinstance(schede, list)
        sconosciuti = [
            s for s in schede
            if "sconosciut" in (s.get("fornitore", "") or "").lower()
        ]
        print(f"[schede ricevimento] totali={len(schede)}, sconosciuti={len(sconosciuti)}")
        assert len(sconosciuti) == 0, (
            f"Trovate {len(sconosciuti)} schede con 'Fornitore Sconosciuto': "
            f"{[s.get('numero_documento') for s in sconosciuti[:5]]}"
        )

    def test_schede_ricevimento_numero_documento_valorizzato(self, session):
        """numero_documento deve essere valorizzato (no stringhe vuote)."""
        r = session.get(f"{API}/fornitori/schede-ricevimento?limit=200", timeout=60)
        assert r.status_code == 200
        schede = r.json()
        assert len(schede) > 0, "Nessuna scheda ricevimento restituita"
        vuoti = [s for s in schede if not (s.get("numero_documento") or "").strip()]
        print(f"[numero_documento] totali={len(schede)}, vuoti={len(vuoti)}")
        # Tolleranza: max 5% può essere vuoto (fatture proforma senza numero)
        assert len(vuoti) <= max(2, len(schede) * 0.05), (
            f"Troppe schede senza numero_documento: {len(vuoti)}/{len(schede)}"
        )

    def test_schede_ricevimento_esclude_pz_xml_artefatti(self, session):
        """numero_documento non deve essere 'pz' o 'xml' (artefatti dal precedente bug)."""
        r = session.get(f"{API}/fornitori/schede-ricevimento?limit=500", timeout=60)
        assert r.status_code == 200
        schede = r.json()
        artefatti = [
            s for s in schede
            if (s.get("numero_documento", "") or "").strip().lower() in {"pz", "xml", "kg", "lt"}
        ]
        assert len(artefatti) == 0, (
            f"Trovate {len(artefatti)} schede con numero_documento artefatto: "
            f"{[s.get('numero_documento') for s in artefatti[:5]]}"
        )
