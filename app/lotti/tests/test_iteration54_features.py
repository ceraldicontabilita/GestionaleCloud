"""
Iteration 54 Backend Tests — HACCP Compliance App
Tests:
  B04: GET /api/materie-prime/da-fatture — aggregate from lotti_fornitori
  B05: GET /api/report-haccp/ingredienti-non-mappati — fixed NameError ROOT_DIR
  AUTO-QUALIFICA: POST /api/fornitori/qualifica/auto-qualifica-tutti
  RICEZIONE-MERCE filtro esclusi: GET /api/ricezione-merce/da-fatture/ultimi-arrivi
  TIMAS DEDUP: check single TIMAS ASCENSORI S.R.L. in fornitori
  ANOMALIE REPORT-PDF: GET /api/anomalie/report-pdf/2022 — real data
  ANOMALIE TIPI: GET /api/anomalie/tipi
  ANOMALIE STATISTICHE: GET /api/anomalie/statistiche
"""

import pytest
import requests
import os

# Use localhost for new endpoints (ceraldiapp.it production not yet deployed)
BASE_URL = "http://localhost:8001"


# ─────────────────────────────────────────────────────
# B04: GET /api/materie-prime/da-fatture
# ─────────────────────────────────────────────────────
class TestB04MateriePrimeDaFatture:
    """B04: materie-prime/da-fatture should return 200 with groups from lotti_fornitori"""

    def test_da_fatture_200(self):
        """Should return HTTP 200"""
        res = requests.get(f"{BASE_URL}/api/materie-prime/da-fatture?mesi=12", timeout=30)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text[:300]}"

    def test_da_fatture_returns_list(self):
        """Should return a list"""
        res = requests.get(f"{BASE_URL}/api/materie-prime/da-fatture?mesi=12", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list), f"Expected list, got {type(data).__name__}"

    def test_da_fatture_has_at_least_one_group(self):
        """Should have at least 1 group (262 docs in lotti_fornitori)"""
        res = requests.get(f"{BASE_URL}/api/materie-prime/da-fatture?mesi=12", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 1, f"Expected at least 1 group, got {len(data)}"

    def test_da_fatture_group_has_fornitore_field(self):
        """Each group should have 'fornitore' field"""
        res = requests.get(f"{BASE_URL}/api/materie-prime/da-fatture?mesi=12", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 1
        group = data[0]
        assert "fornitore" in group, f"Missing 'fornitore' in group: {group}"
        assert group["fornitore"], "fornitore should not be empty"

    def test_da_fatture_group_has_totale_prodotti(self):
        """Each group should have 'totale_prodotti' field with positive integer"""
        res = requests.get(f"{BASE_URL}/api/materie-prime/da-fatture?mesi=12", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 1
        group = data[0]
        assert "totale_prodotti" in group, f"Missing 'totale_prodotti' in group: {group}"
        assert group["totale_prodotti"] >= 1, f"totale_prodotti should be >= 1, got {group['totale_prodotti']}"

    def test_da_fatture_group_has_prodotti_list(self):
        """Each group should have 'prodotti' as a non-empty list"""
        res = requests.get(f"{BASE_URL}/api/materie-prime/da-fatture?mesi=12", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 1
        group = data[0]
        assert "prodotti" in group, f"Missing 'prodotti' in group: {group}"
        assert isinstance(group["prodotti"], list)
        assert len(group["prodotti"]) >= 1

    def test_da_fatture_mesi_6(self):
        """Should work with mesi=6 as well"""
        res = requests.get(f"{BASE_URL}/api/materie-prime/da-fatture?mesi=6", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)

    def test_da_fatture_mesi_24(self):
        """Should work with mesi=24 - larger window"""
        res = requests.get(f"{BASE_URL}/api/materie-prime/da-fatture?mesi=24", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 1, f"With 24 months should have at least 1 group"


# ─────────────────────────────────────────────────────
# B05: GET /api/report-haccp/ingredienti-non-mappati
# ─────────────────────────────────────────────────────
class TestB05IngredentiNonMappati:
    """B05: ingredienti-non-mappati should return 200 (was 500 before ROOT_DIR fix)"""

    def test_ingredienti_non_mappati_200(self):
        """Should return HTTP 200 (not 500)"""
        res = requests.get(f"{BASE_URL}/api/report-haccp/ingredienti-non-mappati", timeout=30)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text[:300]}"

    def test_ingredienti_non_mappati_response_structure(self):
        """Should return dict with totale_ingredienti, trovati, non_trovati"""
        res = requests.get(f"{BASE_URL}/api/report-haccp/ingredienti-non-mappati", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, dict), f"Expected dict, got {type(data).__name__}"
        required_fields = ["totale_ingredienti", "trovati", "non_trovati", "percentuale_copertura", "ingredienti_mancanti"]
        for f in required_fields:
            assert f in data, f"Missing field '{f}' in response: {list(data.keys())}"

    def test_ingredienti_non_mappati_numeric_fields(self):
        """Numeric fields should be integers/floats"""
        res = requests.get(f"{BASE_URL}/api/report-haccp/ingredienti-non-mappati", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data["totale_ingredienti"], int)
        assert isinstance(data["trovati"], int)
        assert isinstance(data["non_trovati"], int)
        assert isinstance(data["percentuale_copertura"], (int, float))
        assert isinstance(data["ingredienti_mancanti"], list)


# ─────────────────────────────────────────────────────
# Auto-qualifica: POST /api/fornitori/qualifica/auto-qualifica-tutti
# ─────────────────────────────────────────────────────
class TestAutoQualificaTutti:
    """Auto-qualifica endpoint returns 200 with aggiornati field"""

    def test_auto_qualifica_200(self):
        """Should return HTTP 200"""
        res = requests.post(f"{BASE_URL}/api/fornitori/qualifica/auto-qualifica-tutti", timeout=30)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text[:300]}"

    def test_auto_qualifica_has_aggiornati(self):
        """Response should have 'aggiornati' field"""
        res = requests.post(f"{BASE_URL}/api/fornitori/qualifica/auto-qualifica-tutti", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert "aggiornati" in data, f"Missing 'aggiornati' field: {data}"
        assert isinstance(data["aggiornati"], int)

    def test_auto_qualifica_has_messaggio(self):
        """Response should have 'messaggio' field"""
        res = requests.post(f"{BASE_URL}/api/fornitori/qualifica/auto-qualifica-tutti", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert "messaggio" in data, f"Missing 'messaggio' field: {data}"
        assert isinstance(data["messaggio"], str)
        assert len(data["messaggio"]) > 0


# ─────────────────────────────────────────────────────
# Fornitori esclusi nel ricezione-merce
# ─────────────────────────────────────────────────────
class TestRicezioneMerceFiltroEsclusi:
    """GET /api/ricezione-merce/da-fatture/ultimi-arrivi should return 200 without fornitori esclusi"""

    def test_ultimi_arrivi_200(self):
        """Should return HTTP 200"""
        res = requests.get(f"{BASE_URL}/api/ricezione-merce/da-fatture/ultimi-arrivi", timeout=30)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text[:300]}"

    def test_ultimi_arrivi_returns_list(self):
        """Should return a list"""
        res = requests.get(f"{BASE_URL}/api/ricezione-merce/da-fatture/ultimi-arrivi", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list), f"Expected list, got {type(data).__name__}"

    def test_ultimi_arrivi_no_fornitori_esclusi(self):
        """Should not contain fornitori with escluso=True"""
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path('/app/backend/.env'))

        async def get_esclusi():
            client = AsyncIOMotorClient(os.environ.get('MONGO_URL'))
            db = client[os.environ.get('DB_NAME')]
            docs = await db.fornitori.find({"escluso": True}, {"_id": 0, "nome": 1}).to_list(500)
            client.close()
            return {d["nome"].strip().lower() for d in docs}

        esclusi = asyncio.run(get_esclusi())

        res = requests.get(f"{BASE_URL}/api/ricezione-merce/da-fatture/ultimi-arrivi", timeout=30)
        assert res.status_code == 200
        data = res.json()

        for item in data:
            fornitore = (item.get("fornitore") or "").strip().lower()
            assert fornitore not in esclusi, \
                f"Fornitore escluso '{item.get('fornitore')}' trovato negli ultimi arrivi"

    def test_ultimi_arrivi_default_giorni(self):
        """Should work with default giorni=30"""
        res = requests.get(f"{BASE_URL}/api/ricezione-merce/da-fatture/ultimi-arrivi?giorni=30", timeout=30)
        assert res.status_code == 200

    def test_ultimi_arrivi_giorni_365(self):
        """Should work with giorni=365"""
        res = requests.get(f"{BASE_URL}/api/ricezione-merce/da-fatture/ultimi-arrivi?giorni=365", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)


# ─────────────────────────────────────────────────────
# TIMAS ASCENSORI S.R.L. dedup check
# ─────────────────────────────────────────────────────
class TestTimasDedup:
    """TIMAS ASCENSORI S.R.L. should have only 1 record in fornitori collection"""

    def test_timas_single_record(self):
        """Should return single TIMAS record from GET /api/fornitori endpoint"""
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path('/app/backend/.env'))

        async def count_timas():
            client = AsyncIOMotorClient(os.environ.get('MONGO_URL'))
            db = client[os.environ.get('DB_NAME')]
            docs = await db.fornitori.find({}, {"_id": 0, "nome": 1}).to_list(1000)
            client.close()
            return [d for d in docs if "TIMAS" in (d.get("nome") or "").upper()]

        timas_records = asyncio.run(count_timas())
        assert len(timas_records) == 1, \
            f"Expected 1 TIMAS record, found {len(timas_records)}: {timas_records}"

    def test_timas_name_content(self):
        """The TIMAS record should contain the correct name"""
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path('/app/backend/.env'))

        async def get_timas():
            client = AsyncIOMotorClient(os.environ.get('MONGO_URL'))
            db = client[os.environ.get('DB_NAME')]
            docs = await db.fornitori.find({}, {"_id": 0, "nome": 1}).to_list(1000)
            client.close()
            return [d for d in docs if "TIMAS" in (d.get("nome") or "").upper()]

        timas_records = asyncio.run(get_timas())
        assert len(timas_records) == 1
        assert "TIMAS" in timas_records[0]["nome"].upper()
        assert "ASCENSORI" in timas_records[0]["nome"].upper()


# ─────────────────────────────────────────────────────
# Anomalie Report PDF
# ─────────────────────────────────────────────────────
class TestAnomalieReportPdf:
    """GET /api/anomalie/report-pdf/2022 should return 200 with real data"""

    def test_report_pdf_2022_200(self):
        """Should return HTTP 200"""
        res = requests.get(f"{BASE_URL}/api/anomalie/report-pdf/2022", timeout=30)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text[:300]}"

    def test_report_pdf_2022_is_html(self):
        """Should return HTML content"""
        res = requests.get(f"{BASE_URL}/api/anomalie/report-pdf/2022", timeout=30)
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", ""), \
            f"Expected HTML content-type, got: {res.headers.get('content-type')}"

    def test_report_pdf_2022_not_all_zeros(self):
        """Should have non-zero anomalie count (not all zeros for 2022)"""
        res = requests.get(f"{BASE_URL}/api/anomalie/report-pdf/2022", timeout=30)
        assert res.status_code == 200
        html = res.text

        # Check that the totale section doesn't show 0 anomalie
        # The HTML has a stat-value div for totale
        # If fixed, it should show the actual count > 0 for 2022
        # The HTML contains: <div class="stat-value">{totale}</div>
        import re
        totale_match = re.search(r'TOTALE ANOMALIE.*?</div>.*?<div class="stat-value">\s*(\d+)\s*</div>',
                                 html, re.DOTALL)
        # Alternative search pattern
        stat_values = re.findall(r'<div class="stat-value">(\d+)</div>', html)
        assert len(stat_values) >= 1, "No stat values found in HTML"
        # First stat value is the totale
        totale = int(stat_values[0])
        assert totale > 0, f"Report for 2022 shows 0 anomalie (all zeros!). stat_values={stat_values}"

    def test_report_pdf_2022_has_azienda_info(self):
        """Should contain company info"""
        res = requests.get(f"{BASE_URL}/api/anomalie/report-pdf/2022", timeout=30)
        assert res.status_code == 200
        assert "Ceraldi Group" in res.text, "Company name not found in report"
        assert "2022" in res.text

    def test_report_pdf_2023_200(self):
        """Should also work for 2023"""
        res = requests.get(f"{BASE_URL}/api/anomalie/report-pdf/2023", timeout=30)
        assert res.status_code == 200

    def test_report_pdf_2026_200(self):
        """Should work for current year 2026"""
        res = requests.get(f"{BASE_URL}/api/anomalie/report-pdf/2026", timeout=30)
        assert res.status_code == 200


# ─────────────────────────────────────────────────────
# Anomalie Tipi
# ─────────────────────────────────────────────────────
class TestAnomalietipi:
    """GET /api/anomalie/tipi should return 200 with array of tipi"""

    def test_tipi_200(self):
        """Should return HTTP 200"""
        res = requests.get(f"{BASE_URL}/api/anomalie/tipi", timeout=30)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text[:300]}"

    def test_tipi_returns_list(self):
        """Should return a list"""
        res = requests.get(f"{BASE_URL}/api/anomalie/tipi", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list), f"Expected list, got {type(data).__name__}: {data}"

    def test_tipi_non_empty(self):
        """Should return non-empty list"""
        res = requests.get(f"{BASE_URL}/api/anomalie/tipi", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert len(data) >= 1, f"Expected at least 1 tipo, got {len(data)}"

    def test_tipi_are_strings(self):
        """All tipi should be strings"""
        res = requests.get(f"{BASE_URL}/api/anomalie/tipi", timeout=30)
        assert res.status_code == 200
        data = res.json()
        for t in data:
            assert isinstance(t, str), f"Tipo should be string, got {type(t).__name__}: {t}"


# ─────────────────────────────────────────────────────
# Anomalie Statistiche
# ─────────────────────────────────────────────────────
class TestAnomalieStatistiche:
    """GET /api/anomalie/statistiche should return 200"""

    def test_statistiche_200(self):
        """Should return HTTP 200"""
        res = requests.get(f"{BASE_URL}/api/anomalie/statistiche", timeout=30)
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text[:300]}"

    def test_statistiche_response_structure(self):
        """Should return dict with totale, per_stato, per_categoria, aperte, risolte"""
        res = requests.get(f"{BASE_URL}/api/anomalie/statistiche", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, dict)
        required_fields = ["totale", "per_stato", "per_categoria", "aperte", "risolte"]
        for f in required_fields:
            assert f in data, f"Missing field '{f}': {list(data.keys())}"

    def test_statistiche_totale_positive(self):
        """totale should be >= 0"""
        res = requests.get(f"{BASE_URL}/api/anomalie/statistiche", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert data["totale"] >= 0
        # We know there are 18 anomalies
        assert data["totale"] >= 18, f"Expected >= 18 anomalie, got {data['totale']}"

    def test_statistiche_anno_filter(self):
        """Should work with anno filter"""
        res = requests.get(f"{BASE_URL}/api/anomalie/statistiche?anno=2022", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert data["totale"] >= 0
        # 2022 should have some anomalies
        assert data["totale"] > 0, f"Expected > 0 anomalie for 2022, got {data['totale']}"


# ─────────────────────────────────────────────────────
# Smoke tests for other key endpoints
# ─────────────────────────────────────────────────────
class TestSmokeTests:
    """Quick smoke tests for endpoints that should still work"""

    def test_anomalie_lista_200(self):
        """GET /api/anomalie/lista should return 200"""
        res = requests.get(f"{BASE_URL}/api/anomalie/lista", timeout=30)
        assert res.status_code == 200

    def test_anomalie_lista_has_data(self):
        """GET /api/anomalie/lista should return at least 18 anomalie"""
        res = requests.get(f"{BASE_URL}/api/anomalie/lista", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 18, f"Expected >= 18 anomalie, got {len(data)}"

    def test_anomalie_lista_anno_2022(self):
        """GET /api/anomalie/lista?anno=2022 should return anomalie for 2022"""
        res = requests.get(f"{BASE_URL}/api/anomalie/lista?anno=2022", timeout=30)
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) > 0, f"Expected anomalie for 2022, got 0"

    def test_fornitori_endpoint_200(self):
        """GET /api/fornitori should return 200"""
        res = requests.get(f"{BASE_URL}/api/fornitori", timeout=30)
        assert res.status_code == 200

    def test_materie_prime_storico_200(self):
        """GET /api/materie-prime/storico should return 200"""
        res = requests.get(f"{BASE_URL}/api/materie-prime/storico", timeout=30)
        assert res.status_code == 200

    def test_report_haccp_mensile_200(self):
        """GET /api/report-haccp/mensile should return 200"""
        res = requests.get(f"{BASE_URL}/api/report-haccp/mensile?anno=2026&mese=1", timeout=30)
        assert res.status_code == 200
