"""
Test end-to-end della pipeline Corrispettivi:
- POST /api/documenti/upload-auto (XML corrispettivo)
- POST /api/corrispettivi/upload-xml
- POST /api/corrispettivi/upload-xml-bulk
- POST /api/corrispettivi/upload-zip
- POST /api/corrispettivi/rebuild-prima-nota?anno=2099
- POST /api/corrispettivi/cleanup-duplicati-forte?anno=2099

Anti-duplicato rigoroso + propagazione automatica in Prima Nota (cassa + banca POS).

IMPORTANTE: usa anno 2099 e matricola_rt con prefisso TEST_ per non sporcare i dati reali.
Cleanup a fine test con motor direttamente su MongoDB Atlas.
"""
from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path

import pytest
import requests

# Carica env da backend/.env (MONGO_URL, DB_NAME)
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except ImportError:
    pass

# BASE_URL del backend pubblico (ingress k8s)
sys.path.insert(0, "/app")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback su frontend/.env
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

if not BASE_URL:
    pytest.skip(
        "REACT_APP_BACKEND_URL non configurato: test integrazione pubblica disabilitato in locale",
        allow_module_level=True,
    )

# Collezioni che vengono toccate
TEST_MATRICOLA = "TESTRT0001"  # prefissi test
TEST_PIVA = "99999999901"
TEST_YEAR = 2099


# ---------- XML BUILDER ----------
def build_xml(
    data: str = "2099-01-05",
    matricola: str = TEST_MATRICOLA,
    progressivo: str = "0001",
    piva: str = TEST_PIVA,
    pagato_contanti: float = 80.00,
    pagato_elettronico: float = 20.00,
    imponibile: float = 90.91,
    imposta: float = 9.09,
) -> str:
    """Costruisce un XML COR10 sintetico valido per il parser."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Corrispettivo xmlns="urn:www.agenziaentrate.gov.it:specificheTecniche:sco:telematici">
  <Trasmissione>
    <Progressivo>{progressivo}</Progressivo>
    <Formato>COR10</Formato>
    <Dispositivo>
      <Tipo>RT</Tipo>
      <IdDispositivo>{matricola}</IdDispositivo>
    </Dispositivo>
    <CodiceFiscaleEsercente>{piva}</CodiceFiscaleEsercente>
    <PIVAEsercente>{piva}</PIVAEsercente>
    <DataOraTrasmissione>{data}T20:14:42+01:00</DataOraTrasmissione>
  </Trasmissione>
  <DataOraRilevazione>{data}T20:14:42+01:00</DataOraRilevazione>
  <DatiRT>
    <Riepilogo>
      <IVA>
        <AliquotaIVA>10.00</AliquotaIVA>
        <Imposta>{imposta:.2f}</Imposta>
      </IVA>
      <Ammontare>{imponibile:.2f}</Ammontare>
      <ImportoParziale>{(imponibile + imposta):.2f}</ImportoParziale>
    </Riepilogo>
    <Totali>
      <NumeroDocCommerciali>5</NumeroDocCommerciali>
      <PagatoContanti>{pagato_contanti:.2f}</PagatoContanti>
      <PagatoElettronico>{pagato_elettronico:.2f}</PagatoElettronico>
    </Totali>
  </DatiRT>
</Corrispettivo>"""


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    return s


@pytest.fixture(scope="session", autouse=True)
def cleanup_before_and_after():
    """Pulizia sincrona tramite pymongo dei record di test (matricola TEST + anno 2099)."""
    from pymongo import MongoClient

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]

    def purge():
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=20000)
        try:
            db = client[db_name]
            # Trova tutti i corrispettivi di test
            test_corr = list(
                db["corrispettivi"].find(
                    {"$or": [
                        {"matricola_rt": TEST_MATRICOLA},
                        {"data": {"$regex": f"^{TEST_YEAR}"}},
                        {"partita_iva": TEST_PIVA},
                    ]},
                    {"id": 1, "data": 1},
                )
            )
            corr_ids = [c.get("id") for c in test_corr if c.get("id")]
            corr_dates = list({c.get("data") for c in test_corr if c.get("data")})

            if corr_ids:
                db["prima_nota_cassa"].delete_many({"corrispettivo_id": {"$in": corr_ids}})
                db["prima_nota_banca"].delete_many({"corrispettivo_id": {"$in": corr_ids}})
            if corr_dates:
                db["prima_nota_cassa"].delete_many({"data": {"$in": corr_dates}})
                db["prima_nota_banca"].delete_many({"data": {"$in": corr_dates}})
            db["corrispettivi"].delete_many(
                {"$or": [
                    {"matricola_rt": TEST_MATRICOLA},
                    {"data": {"$regex": f"^{TEST_YEAR}"}},
                    {"partita_iva": TEST_PIVA},
                ]}
            )
        finally:
            client.close()

    purge()
    yield
    purge()


@pytest.fixture
def mongo_db():
    """Client MongoDB diretto (solo lettura, per verifica stato)."""
    from pymongo import MongoClient

    client = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=20000)
    db = client[os.environ["DB_NAME"]]
    yield db
    client.close()


# ---------- HELPERS ----------
def _post_xml(session, url: str, xml: str, filename: str, field_name: str = "file"):
    files = {field_name: (filename, xml.encode("utf-8"), "application/xml")}
    return session.post(url, files=files, timeout=60)


def _count_prima_nota(db, corr_id: str):
    cassa = db["prima_nota_cassa"].count_documents({"corrispettivo_id": corr_id})
    banca = db["prima_nota_banca"].count_documents({"corrispettivo_id": corr_id})
    return cassa, banca


# =========================================================================
# TEST 1 - POST /api/documenti/upload-auto con XML corrispettivo
# =========================================================================
class TestDocumentiUploadAuto:
    def test_corrispettivo_creation_and_duplicate(self, session, mongo_db):
        xml = build_xml(data="2099-01-05", progressivo="A001",
                        pagato_contanti=80.00, pagato_elettronico=20.00)
        url = f"{BASE_URL}/api/documenti/upload-auto"

        # 1° upload -> created
        r1 = _post_xml(session, url, xml, "cor_test_001.xml")
        assert r1.status_code == 200, f"HTTP {r1.status_code}: {r1.text[:500]}"
        j1 = r1.json()
        assert j1.get("tipo_rilevato") == "corrispettivo", j1
        assert j1.get("action") == "created", j1
        corr_id = j1["corrispettivo_id"]
        assert corr_id
        assert j1.get("prima_nota_cassa_id"), "Manca prima_nota_cassa_id"
        assert j1.get("prima_nota_banca_id"), "Manca prima_nota_banca_id"

        # Verifica persistenza
        corr = mongo_db["corrispettivi"].find_one({"id": corr_id}, {"_id": 0})
        assert corr is not None
        assert corr["matricola_rt"] == TEST_MATRICOLA
        assert abs(corr["totale"] - 100.00) < 0.01

        cassa = mongo_db["prima_nota_cassa"].find_one(
            {"corrispettivo_id": corr_id}, {"_id": 0}
        )
        assert cassa is not None
        assert cassa["source"] == "corrispettivo_import"
        assert cassa["categoria"] == "Corrispettivi"
        assert abs(cassa["importo"] - 100.00) < 0.01

        uscita_pos = mongo_db["prima_nota_cassa"].find_one(
            {"corrispettivo_id": corr_id, "categoria": "POS Verso Banca"}, {"_id": 0}
        )
        assert uscita_pos is not None
        assert uscita_pos["source"] == "corrispettivo_import"
        assert abs(uscita_pos["importo"] - 20.00) < 0.01

        banca = mongo_db["prima_nota_banca"].find_one(
            {"corrispettivo_id": corr_id}, {"_id": 0}
        )
        assert banca is not None
        assert banca["source"] == "trasferimento_pos"
        assert abs(banca["importo"] - 20.00) < 0.01
        assert banca["riconciliato"] is False

        # 2° upload dello stesso XML -> duplicate (non deve duplicare prima nota)
        r2 = _post_xml(session, url, xml, "cor_test_001.xml")
        assert r2.status_code == 200
        j2 = r2.json()
        assert j2.get("action") == "duplicate", j2
        cassa_n, banca_n = _count_prima_nota(mongo_db, corr_id)
        assert cassa_n == 2, f"Prima Nota Cassa duplicata: {cassa_n} record"
        assert banca_n == 1, f"Prima Nota Banca duplicata: {banca_n} record"


# =========================================================================
# TEST 2 - POST /api/corrispettivi/upload-xml (singolo)
# =========================================================================
class TestUploadXmlSingolo:
    def test_upload_xml_creation_and_duplicate(self, session, mongo_db):
        xml = build_xml(data="2099-01-06", progressivo="B001",
                        pagato_contanti=50.00, pagato_elettronico=30.00,
                        imponibile=72.73, imposta=7.27)
        url = f"{BASE_URL}/api/corrispettivi/upload-xml"

        # force_update default = True, ma con corrispettivo nuovo -> created
        r1 = _post_xml(session, url, xml, "cor_singolo_001.xml")
        assert r1.status_code == 200, f"HTTP {r1.status_code}: {r1.text[:500]}"
        j1 = r1.json()
        assert j1["success"] is True
        assert j1["action"] == "created"
        corr_id = j1["corrispettivo_id"]
        assert j1["prima_nota_cassa_id"]
        assert j1["prima_nota_banca_id"]

        # Verifica DB
        cassa_n, banca_n = _count_prima_nota(mongo_db, corr_id)
        assert cassa_n == 2
        assert banca_n == 1

        # 2° upload con force_update=True -> action=updated, no duplicati
        r2 = session.post(
            url,
            files={"file": ("cor_singolo_001.xml", xml.encode(), "application/xml")},
            params={"force_update": "true"},
            timeout=60,
        )
        assert r2.status_code == 200
        j2 = r2.json()
        assert j2["action"] in ("updated", "duplicate"), j2
        cassa_n, banca_n = _count_prima_nota(mongo_db, corr_id)
        assert cassa_n == 2, f"Prima Nota Cassa duplicata: {cassa_n}"
        assert banca_n == 1, f"Prima Nota Banca duplicata: {banca_n}"

        # 3° upload con force_update=False -> duplicate
        r3 = session.post(
            url,
            files={"file": ("cor_singolo_001.xml", xml.encode(), "application/xml")},
            params={"force_update": "false"},
            timeout=60,
        )
        assert r3.status_code == 200
        j3 = r3.json()
        assert j3["action"] == "duplicate", j3
        cassa_n, banca_n = _count_prima_nota(mongo_db, corr_id)
        assert cassa_n == 2
        assert banca_n == 1


# =========================================================================
# TEST 3 - POST /api/corrispettivi/upload-xml-bulk
# =========================================================================
class TestUploadXmlBulk:
    def test_bulk_upload_mixed_new_and_duplicate(self, session, mongo_db):
        # 2 nuovi + 1 duplicato del primo
        xml_a = build_xml(data="2099-02-01", progressivo="BULK_A",
                          pagato_contanti=40.00, pagato_elettronico=10.00,
                          imponibile=45.45, imposta=4.55)
        xml_b = build_xml(data="2099-02-02", progressivo="BULK_B",
                          pagato_contanti=30.00, pagato_elettronico=0.00,
                          imponibile=27.27, imposta=2.73)
        url = f"{BASE_URL}/api/corrispettivi/upload-xml-bulk"

        files = [
            ("files", ("cor_bulk_a.xml", xml_a.encode(), "application/xml")),
            ("files", ("cor_bulk_b.xml", xml_b.encode(), "application/xml")),
            ("files", ("cor_bulk_a_dup.xml", xml_a.encode(), "application/xml")),
        ]
        r = session.post(url, files=files, timeout=120)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:500]}"
        j = r.json()
        assert j["total"] == 3
        assert j["imported"] == 2, j
        assert j["skipped"] == 1, j
        assert len(j["duplicates"]) == 1

        # Verifica movimenti Prima Nota: per data 2099-02-01 deve esserci 1 cassa + 1 banca;
        # per 2099-02-02 solo 1 cassa (pagato elettronico = 0).
        n_cassa_a = mongo_db["prima_nota_cassa"].count_documents({"data": "2099-02-01"})
        n_banca_a = mongo_db["prima_nota_banca"].count_documents({"data": "2099-02-01"})
        n_cassa_b = mongo_db["prima_nota_cassa"].count_documents({"data": "2099-02-02"})
        n_banca_b = mongo_db["prima_nota_banca"].count_documents({"data": "2099-02-02"})
        assert n_cassa_a == 1, f"Cassa 02-01: {n_cassa_a}"
        assert n_banca_a == 1, f"Banca 02-01: {n_banca_a}"
        assert n_cassa_b == 1, f"Cassa 02-02: {n_cassa_b}"
        assert n_banca_b == 0, f"Banca 02-02: {n_banca_b} (non doveva crearsi)"


# =========================================================================
# TEST 4 - POST /api/corrispettivi/upload-zip
# =========================================================================
class TestUploadZip:
    def test_zip_upload_with_duplicate(self, session, mongo_db):
        xml_c = build_xml(data="2099-03-10", progressivo="ZIP_C",
                          pagato_contanti=60.00, pagato_elettronico=40.00,
                          imponibile=90.91, imposta=9.09)
        xml_d = build_xml(data="2099-03-11", progressivo="ZIP_D",
                          pagato_contanti=20.00, pagato_elettronico=80.00,
                          imponibile=90.91, imposta=9.09)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("cor_zip_c.xml", xml_c)
            zf.writestr("cor_zip_d.xml", xml_d)
            zf.writestr("cor_zip_c_dup.xml", xml_c)  # duplicato
        buf.seek(0)

        url = f"{BASE_URL}/api/corrispettivi/upload-zip"
        r = session.post(
            url,
            files={"file": ("test_corrispettivi.zip", buf.getvalue(), "application/zip")},
            timeout=120,
        )
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:500]}"
        j = r.json()
        assert j["total"] == 3
        assert j["imported"] == 2, j
        assert j["skipped_duplicates"] == 1, j

        # Prima Nota coerente
        n_cassa_c = mongo_db["prima_nota_cassa"].count_documents({"data": "2099-03-10"})
        n_banca_c = mongo_db["prima_nota_banca"].count_documents({"data": "2099-03-10"})
        n_cassa_d = mongo_db["prima_nota_cassa"].count_documents({"data": "2099-03-11"})
        n_banca_d = mongo_db["prima_nota_banca"].count_documents({"data": "2099-03-11"})
        assert n_cassa_c == 1, n_cassa_c
        assert n_banca_c == 1, n_banca_c
        assert n_cassa_d == 1, n_cassa_d
        assert n_banca_d == 1, n_banca_d


# =========================================================================
# TEST 5 - POST /api/corrispettivi/rebuild-prima-nota?anno=2099
# =========================================================================
class TestRebuildPrimaNota:
    def test_rebuild_creates_movements_for_year(self, session, mongo_db):
        # Precondizione: dopo tutti i test precedenti abbiamo diversi corrispettivi in 2099.
        # Chiamiamo rebuild anno=2099 e verifichiamo che il numero di movimenti creati
        # corrisponde al numero di corrispettivi con totale > 0.
        corr_validi = mongo_db["corrispettivi"].count_documents({
            "data": {"$regex": f"^{TEST_YEAR}"},
            "totale": {"$gt": 0},
            "entity_status": {"$ne": "deleted"},
        })

        url = f"{BASE_URL}/api/corrispettivi/rebuild-prima-nota"
        r = session.post(url, params={"anno": TEST_YEAR}, timeout=120)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:500]}"
        j = r.json()
        assert j["success"] is True
        assert j["anno"] == TEST_YEAR
        # Ogni corrispettivo di test ha sia contanti che elettronico > 0 tranne BULK_B
        # -> prima_nota_cassa = tutti; prima_nota_banca = tutti tranne quelli con elettronico 0
        assert j["corrispettivi_processati"] == corr_validi
        # cassa creati = corr_validi (perché tutti hanno contanti > 0 o totale > 0)
        assert j["prima_nota_cassa_creati"] == corr_validi, j

        # Dopo rebuild, le vecchie source legacy NON devono esistere per quell'anno
        legacy_sources = [
            "corrispettivi_sync", "xml_import", "sincronizzazione",
            "zip_upload", "manual_entry", "manual", "corrispettivo_manuale",
        ]
        residui = mongo_db["prima_nota_cassa"].count_documents({
            "data": {"$regex": f"^{TEST_YEAR}"},
            "categoria": "Corrispettivi",
            "source": {"$in": legacy_sources},
        })
        assert residui == 0, f"Residui legacy cassa: {residui}"


# =========================================================================
# TEST 6 - POST /api/corrispettivi/cleanup-duplicati-forte?anno=2099
# =========================================================================
class TestCleanupDuplicatiForte:
    def test_cleanup_removes_duplicates_keeps_oldest(self, session, mongo_db):
        # Crea a mano 2 duplicati in DB (stessa data, matricola, totale) -> cleanup deve tenerne 1.
        from datetime import datetime, timezone
        import uuid
        base = {
            "data": "2099-04-15",
            "matricola_rt": TEST_MATRICOLA,
            "totale": 123.45,
            "pagato_contanti": 100.00,
            "pagato_elettronico": 23.45,
            "anno": TEST_YEAR,
            "mese": 4,
            "source": "xml",
            "status": "imported",
        }
        d1 = {**base, "id": str(uuid.uuid4()),
              "created_at": "2099-04-15T10:00:00+00:00",
              "corrispettivo_key": "DUP_A_OLDEST"}
        d2 = {**base, "id": str(uuid.uuid4()),
              "created_at": "2099-04-15T11:00:00+00:00",
              "corrispettivo_key": "DUP_A_NEWER1"}
        d3 = {**base, "id": str(uuid.uuid4()),
              "created_at": "2099-04-15T12:00:00+00:00",
              "corrispettivo_key": "DUP_A_NEWER2"}
        mongo_db["corrispettivi"].insert_many([d1.copy(), d2.copy(), d3.copy()])

        before = mongo_db["corrispettivi"].count_documents({
            "data": "2099-04-15", "matricola_rt": TEST_MATRICOLA,
        })
        assert before == 3

        url = f"{BASE_URL}/api/corrispettivi/cleanup-duplicati-forte"
        r = session.post(url, params={"anno": TEST_YEAR}, timeout=120)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:500]}"
        j = r.json()
        assert j["success"] is True
        assert j["gruppi_duplicati"] >= 1
        assert j["corrispettivi_eliminati"] >= 2

        after = mongo_db["corrispettivi"].count_documents({
            "data": "2099-04-15", "matricola_rt": TEST_MATRICOLA,
        })
        assert after == 1, f"Dopo cleanup resta {after} record"
        # Deve restare il più vecchio (DUP_A_OLDEST)
        restante = mongo_db["corrispettivi"].find_one({
            "data": "2099-04-15", "matricola_rt": TEST_MATRICOLA,
        }, {"_id": 0})
        assert restante["corrispettivo_key"] == "DUP_A_OLDEST"


# =========================================================================
# TEST 7 - Coerenza importi secondo il modello trasferimento Cassa -> Banca
# =========================================================================
class TestCoerenzaImporti:
    def test_totale_cassa_e_trasferimento_pos_quadrano(self, session, mongo_db):
        # Prima rebuild, per partire da stato pulito.
        session.post(
            f"{BASE_URL}/api/corrispettivi/rebuild-prima-nota",
            params={"anno": TEST_YEAR}, timeout=120,
        )

        corr = list(mongo_db["corrispettivi"].find(
            {"data": {"$regex": f"^{TEST_YEAR}"}, "entity_status": {"$ne": "deleted"}},
            {"_id": 0, "totale": 1, "pagato_contanti": 1, "pagato_elettronico": 1},
        ))
        tot_corr = round(sum(c.get("totale", 0) for c in corr), 2)
        tot_contanti_expected = round(sum(c.get("pagato_contanti", 0) for c in corr), 2)
        tot_elettronico_expected = round(sum(c.get("pagato_elettronico", 0) for c in corr), 2)

        pipe_cassa = [
            {"$match": {
                "data": {"$regex": f"^{TEST_YEAR}"},
                "categoria": "Corrispettivi",
                "source": "corrispettivo_import",
            }},
            {"$group": {"_id": None, "tot": {"$sum": "$importo"}}},
        ]
        pipe_banca = [
            {"$match": {
                "data": {"$regex": f"^{TEST_YEAR}"},
                "source": "trasferimento_pos",
            }},
            {"$group": {"_id": None, "tot": {"$sum": "$importo"}}},
        ]
        pipe_uscita_pos = [
            {"$match": {
                "data": {"$regex": f"^{TEST_YEAR}"},
                "categoria": "POS Verso Banca",
                "source": "corrispettivo_import",
            }},
            {"$group": {"_id": None, "tot": {"$sum": "$importo"}}},
        ]
        cassa_agg = list(mongo_db["prima_nota_cassa"].aggregate(pipe_cassa))
        uscita_pos_agg = list(mongo_db["prima_nota_cassa"].aggregate(pipe_uscita_pos))
        banca_agg = list(mongo_db["prima_nota_banca"].aggregate(pipe_banca))
        tot_cassa = round(cassa_agg[0]["tot"], 2) if cassa_agg else 0.0
        tot_uscita_pos = round(uscita_pos_agg[0]["tot"], 2) if uscita_pos_agg else 0.0
        tot_banca = round(banca_agg[0]["tot"], 2) if banca_agg else 0.0

        assert abs(tot_cassa - tot_corr) < 0.05, (
            f"Entrata Cassa attesa {tot_corr}, trovata {tot_cassa}"
        )
        assert abs(tot_uscita_pos - tot_elettronico_expected) < 0.05
        assert abs(tot_banca - tot_elettronico_expected) < 0.05, (
            f"Banca atteso {tot_elettronico_expected}, trovato {tot_banca}"
        )
        assert abs((tot_cassa - tot_uscita_pos) - tot_contanti_expected) < 0.05, (
            f"Cassa netta ({tot_cassa - tot_uscita_pos}) != contanti ({tot_contanti_expected})"
        )
