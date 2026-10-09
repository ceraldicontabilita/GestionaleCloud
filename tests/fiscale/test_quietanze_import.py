"""
Motore unico import quietanze F24 (app/services/quietanze_import.py):
dedup per impronta, salvataggio e matching automatico con gli F24.
Usato sia dall'upload manuale che dal canale Google Drive.
"""
import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.services import quietanze_import as qi
from tests.document_preview_helpers import confirmed_preview_headers


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n):
        return self._docs[:n]


class _FakeCollection:
    def __init__(self):
        self.docs = []
        self.updates = []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if all(d.get(k2) == v for k2, v in query.items()):
                return d
        return None

    def find(self, query, *a, **k):
        out = []
        for d in self.docs:
            if all(d.get(k2) == v for k2, v in query.items()):
                out.append(d)
        return _FakeCursor(out)

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        self.updates.append((query, update))
        for d in self.docs:
            if all(d.get(k2) == v for k2, v in query.items()):
                for k2, v in update.get("$set", {}).items():
                    d[k2] = v
                for k2, v in update.get("$push", {}).items():
                    d.setdefault(k2, []).append(v)


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


PARSED_OK = {
    "dati_generali": {
        "protocollo_telematico": "24123456789012345678",
        "saldo_delega": 1500.0,
        "data_pagamento": "2026-06-16",
        "codice_fiscale": "01879020517",
    },
    "sezione_erario": [
        {"codice_tributo": "1001", "periodo_riferimento": "05/2026", "importo_debito": 1000.0},
        {"codice_tributo": "1040", "periodo_riferimento": "05/2026", "importo_debito": 500.0},
    ],
    "sezione_inps": [],
    "sezione_regioni": [],
    "sezione_tributi_locali": [],
    "sezione_inail": [],
    "totali": {"saldo_netto": 1500.0},
    "validazione": {
        "saldo_quadrato": True,
        "differenza_saldo": 0.0,
        "parser_version": "test-v1",
    },
}


def _patch_parser(monkeypatch, parsed):
    import app.services.f24_parser as f24_parser
    monkeypatch.setattr(f24_parser, "parse_quietanza_f24", lambda pdf_content: parsed)


def test_import_e_matching_automatico(monkeypatch):
    """La quietanza collega il modello ma non sostituisce la prova bancaria."""
    _patch_parser(monkeypatch, PARSED_OK)
    db = _FakeDb()
    # F24 del commercialista in attesa con gli stessi tributi
    asyncio.run(db[qi.COLL_F24_COMMERCIALISTA].insert_one({
        "id": "f24-1", "status": "da_pagare", "riconciliato": False,
        "file_name": "F24_giugno.pdf",
        "sezione_erario": [
            {"codice_tributo": "1001", "periodo_riferimento": "05/2026", "importo_debito": 1000.0},
            {"codice_tributo": "1040", "periodo_riferimento": "05/2026", "importo_debito": 500.0},
        ],
        "totali": {"saldo_netto": 1500.0},
    }))

    esito = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-finto", "quietanza.pdf", fonte="test"))

    assert esito["success"] and not esito["duplicate"]
    assert len(esito["f24_matchati"]) == 1  # tolleranza €0.50 sul singolo tributo
    f24 = db[qi.COLL_F24_COMMERCIALISTA].docs[0]
    assert f24["status"] == "da_pagare"
    assert f24["stato_pagamento"] == "DA_VERIFICARE_BANCA"
    assert f24["pagato"] is False
    assert f24["quietanza_id"] == esito["quietanza_id"]
    quietanza = db[qi.COLL_QUIETANZE].docs[0]
    assert quietanza["pdf_hash"]
    assert quietanza["f24_associati"] == ["f24-1"]


def test_dedup_per_impronta(monkeypatch):
    """Lo stesso PDF importato due volte non crea doppioni."""
    _patch_parser(monkeypatch, PARSED_OK)
    db = _FakeDb()
    primo = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-finto", "q.pdf"))
    secondo = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-finto", "q.pdf"))
    assert primo["duplicate"] is False
    assert secondo["duplicate"] is True
    assert secondo["quietanza_id"] == primo["quietanza_id"]
    assert len(db[qi.COLL_QUIETANZE].docs) == 1


def test_quietanza_drive_conserva_solo_riferimento(monkeypatch):
    _patch_parser(monkeypatch, PARSED_OK)
    db = _FakeDb()
    esito = asyncio.run(qi.importa_quietanza_bytes(
        db, b"%PDF-drive", "quietanza.pdf", fonte="drive_quietanze",
        source_metadata={
            "drive_file_id": "drive-q-1",
            "drive_parent_id": "folder-q",
            "drive_path": "ELABORATE/quietanza.pdf",
        },
    ))

    assert esito["success"] is True
    doc = db[qi.COLL_QUIETANZE].docs[0]
    assert doc["drive_file_id"] == "drive-q-1"
    assert doc["original_storage"] == "google_drive"
    assert doc["idempotency_key"].startswith("quietanza_f24:")
    assert "pdf_data" not in doc


def test_senza_match_crea_alert(monkeypatch):
    """Nessun F24 corrispondente → warning + alert quietanza_senza_match."""
    _patch_parser(monkeypatch, PARSED_OK)
    db = _FakeDb()
    esito = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-altro", "q2.pdf"))
    assert esito["success"]
    assert esito["f24_matchati"] == []
    assert esito.get("warning")
    alerts = db[qi.COLL_F24_ALERTS].docs
    assert len(alerts) == 1 and alerts[0]["tipo"] == "quietanza_senza_match"


def test_quietanza_senza_f24_stato_canonico_e_nessuna_ricostruzione(monkeypatch):
    """§9.3 (regola cardine): quietanza senza F24 → stato canonico
    QUIETANZA_PRESENTE_F24_MANCANTE, alert bloccante, calcolo sospeso e NESSUN
    F24 ricostruito automaticamente."""
    _patch_parser(monkeypatch, PARSED_OK)
    db = _FakeDb()
    esito = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-altro", "q3.pdf"))

    assert esito.get("stato_quietanza") == "QUIETANZA_PRESENTE_F24_MANCANTE"
    quietanza = db[qi.COLL_QUIETANZE].docs[0]
    assert quietanza["stato_quietanza"] == "QUIETANZA_PRESENTE_F24_MANCANTE"
    assert quietanza["calcolo_fiscale_sospeso"] is True
    # alert bloccante
    alerts = db[qi.COLL_F24_ALERTS].docs
    assert alerts and alerts[0].get("bloccante") is True
    # NESSUN F24 ricostruito in automatico (regola cardine CLAUDE.md)
    assert db["f24_unificato"].docs == []
    assert db["f24_models"].docs == []


def test_parsing_fallito_non_salva(monkeypatch):
    _patch_parser(monkeypatch, {"error": "PDF illeggibile"})
    db = _FakeDb()
    esito = asyncio.run(qi.importa_quietanza_bytes(db, b"non-pdf", "rotto.pdf"))
    assert esito["success"] is False
    assert db[qi.COLL_QUIETANZE].docs == []


def test_saldo_non_quadrato_non_salva(monkeypatch):
    parsed = {**PARSED_OK, "validazione": {
        "saldo_quadrato": False,
        "differenza_saldo": 12.34,
        "parser_version": "test-v1",
    }}
    _patch_parser(monkeypatch, parsed)
    db = _FakeDb()
    esito = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-non-quadrato", "non-quadrato.pdf"))
    assert esito["success"] is False
    assert esito["stato_quietanza"] == "PARSING_DA_VERIFICARE"
    assert db[qi.COLL_QUIETANZE].docs == []


def test_quietanza_reale_1040_8948_marca_ravvedimento(monkeypatch):
    parsed = {
        **PARSED_OK,
        "dati_generali": {
            **PARSED_OK["dati_generali"],
            "saldo_delega": 286.0,
            "data_pagamento": "2026-07-21",
        },
        "sezione_erario": [
            {"codice_tributo": "1040", "periodo_riferimento": "06/2026", "importo_debito": 284.0},
            {"codice_tributo": "8948", "periodo_riferimento": "06/2026", "importo_debito": 2.0},
        ],
        "totali": {"totale_debito": 286.0, "totale_credito": 0.0, "saldo_netto": 286.0},
    }
    _patch_parser(monkeypatch, parsed)
    db = _FakeDb()
    asyncio.run(db[qi.COLL_F24_COMMERCIALISTA].insert_one({
        "id": "f24-1040-06-2026",
        "status": "da_pagare",
        "riconciliato": False,
        "sezione_erario": [{
            "codice_tributo": "1040",
            "periodo_riferimento": "06/2026",
            "importo_debito": 284.0,
        }],
        "totali": {"saldo_netto": 284.0},
    }))

    esito = asyncio.run(qi.importa_quietanza_bytes(
        db, b"%PDF-caso-reale-anonimizzato", "quietanza_2026-07-21.pdf", fonte="test"
    ))

    assert esito["f24_matchati"][0]["ravveduto"] is True
    f24 = db[qi.COLL_F24_COMMERCIALISTA].docs[0]
    assert f24["codici_ravvedimento"] == ["8948"]
    assert f24["importo_ravvedimento"] == 2.0


def test_upload_auto_endpoint_usa_il_servizio_canonico_quietanze(monkeypatch):
    """Integrazione HTTP reale: multipart -> router -> servizio -> DB fake."""
    from app.routers import documenti
    from app.utils import upload_validation

    _patch_parser(monkeypatch, PARSED_OK)
    db = _FakeDb()
    asyncio.run(db[qi.COLL_F24_COMMERCIALISTA].insert_one({
        "id": "f24-upload-auto",
        "status": "da_pagare",
        "riconciliato": False,
        "file_name": "F24 giugno 2026.pdf",
        "sezione_erario": PARSED_OK["sezione_erario"],
        "totali": PARSED_OK["totali"],
    }))
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(documenti, "detect_document_type", lambda *_: "quietanza_f24")
    monkeypatch.setattr(upload_validation, "verifica_pdf_reale", lambda *_: None)

    test_app = FastAPI()
    test_app.include_router(documenti.router, prefix="/api/documenti")
    with TestClient(test_app) as client:
        response = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("quietanza_1040.pdf", b"%PDF-1.4 fixture anonima", "application/pdf")},
            headers=confirmed_preview_headers(b"%PDF-1.4 fixture anonima", "quietanza_f24"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["workflow"] == "F24_CANONICO"
    assert payload["imported"] == 1
    assert payload["data"]["f24_matchati"][0]["f24_id"] == "f24-upload-auto"
    assert len(db[qi.COLL_QUIETANZE].docs) == 1
    assert db[qi.COLL_F24_COMMERCIALISTA].docs[0]["quietanza_id"] == payload["data"]["quietanza_id"]


def test_upload_auto_endpoint_importa_modello_nella_sola_collezione_canonica(monkeypatch):
    from app.routers import documenti
    from app.utils import upload_validation
    import app.services.parser_f24 as parser

    parsed = {
        "dati_generali": {"codice_fiscale": "CF-ANONIMO", "data_versamento": "2026-07-16"},
        "sezione_erario": [
            {"codice_tributo": "1040", "periodo_riferimento": "06/2026", "importo_debito": 284.0},
            {"codice_tributo": "1704", "periodo_riferimento": "06/2026", "importo_credito": 20.0},
        ],
        "totali": {"totale_debito": 284.0, "totale_credito": 20.0, "saldo_netto": 264.0},
        "validazione": {"saldo_quadrato": True, "parser_version": "test-v1"},
    }
    db = _FakeDb()
    monkeypatch.setattr(documenti.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(documenti, "detect_document_type", lambda *_: "f24")
    monkeypatch.setattr(upload_validation, "verifica_pdf_reale", lambda *_: None)
    monkeypatch.setattr(parser, "parse_f24_commercialista", lambda pdf_content: parsed)

    test_app = FastAPI()
    test_app.include_router(documenti.router, prefix="/api/documenti")
    with TestClient(test_app) as client:
        response = client.post(
            "/api/documenti/upload-auto",
            files={"file": ("modello_f24.pdf", b"%PDF-1.4 fixture anonima", "application/pdf")},
            headers=confirmed_preview_headers(b"%PDF-1.4 fixture anonima", "f24"),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["workflow"] == "F24_CANONICO"
    assert payload["data"]["righe_tributo"] == 2
    assert payload["data"]["righe_credito"] == 1
    assert len(db["f24_unificato"].docs) == 1
    assert db["f24_pagamenti"].docs == []
    assert db["tributi_pagati"].docs == []
    assert db["distinte_f24"].docs == []


def test_upload_quietanza_aggiorna_subito_ritenuta_reale_1040(monkeypatch):
    parsed = {
        "dati_generali": {
            "protocollo_telematico": "PROTO-1040-062026",
            "saldo_delega": 286.0,
            "data_pagamento": "2026-07-21",
            "codice_fiscale": "CF-ANONIMO",
        },
        "sezione_erario": [
            {"codice_tributo": "1040", "periodo_riferimento": "06/2026", "importo_debito": 284.0},
            {"codice_tributo": "8948", "periodo_riferimento": "06/2026", "importo_debito": 2.0},
        ],
        "sezione_inps": [], "sezione_regioni": [],
        "sezione_tributi_locali": [], "sezione_inail": [],
        "totali": {"saldo_netto": 286.0},
        "validazione": {"saldo_quadrato": True, "differenza_saldo": 0.0},
    }
    _patch_parser(monkeypatch, parsed)
    db = ClientArchivioMemoria()["quietanza-ritenuta-real-case"]
    asyncio.run(db[qi.COLL_F24_COMMERCIALISTA].insert_one({
        "id": "F24-1040-06-2026", "status": "da_pagare", "riconciliato": False,
        "codice_fiscale": "CF-ANONIMO",
        "sezione_erario": [{
            "codice_tributo": "1040", "periodo_riferimento": "06/2026", "importo_debito": 284.0,
        }],
        "totali": {"saldo_netto": 284.0},
    }))
    asyncio.run(db["ritenute_acconto"].insert_one({
        "id": "rit-1040-06-2026", "importo": 284.0,
        "periodo_ritenuta": "2026-06", "scadenza": "2026-07-16",
        "data_fattura": "2026-06-30", "stato": "scaduta_da_versare",
    }))

    result = asyncio.run(qi.importa_quietanza_bytes(
        db, b"%PDF-real-case-anonimo", "quietanza_1040_2026-07-21.pdf",
        fonte="documenti_upload_auto",
    ))

    assert result["success"] is True
    assert result["ritenute_aggiornate"]["analizzate"] == 1
    ritenuta = asyncio.run(db["ritenute_acconto"].find_one({"id": "rit-1040-06-2026"}))
    assert ritenuta["f24_id"] == "F24-1040-06-2026"
    assert ritenuta["data_pagamento"] == "2026-07-21"
    assert ritenuta["stato"] == "pagata_con_ravvedimento"
    assert ritenuta["stato_evidenza_pagamento"] == "QUIETANZA_PRESENTE_DA_VERIFICARE_BANCA"
    assert ritenuta["movimento_bancario_f24_id"] is None


def _con_saldo(saldo, righe):
    parsed = {**PARSED_OK, "dati_generali": {**PARSED_OK["dati_generali"], "saldo_delega": saldo},
              "sezione_erario": righe, "totali": {"saldo_netto": saldo}}
    return parsed


def test_stesso_protocollo_stesso_saldo_da_un_altro_pdf_e_un_doppione(monkeypatch):
    _patch_parser(monkeypatch, PARSED_OK)
    db = _FakeDb()
    primo = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-uno", "q.pdf"))
    secondo = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-due", "q (2).pdf"))
    assert secondo["duplicate"] is True and secondo["quietanza_id"] == primo["quietanza_id"]
    assert len(db[qi.COLL_QUIETANZE].docs) == 1


def test_stesso_protocollo_saldo_diverso_e_un_altro_pagamento(monkeypatch):
    """04/11/2022: dallo stesso PDF escono il saldo IRAP (2.946,31) e il suo
    ravvedimento (22,47) col protocollo uguale. Scartare il secondo toglieva
    un pagamento vero: si importa e si annota, da confermare a vista."""
    db = _FakeDb()
    _patch_parser(monkeypatch, _con_saldo(2946.31, [
        {"codice_tributo": "3800", "periodo_riferimento": "2021", "importo_debito": 2946.31}]))
    primo = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-uno", "a.pdf"))
    _patch_parser(monkeypatch, _con_saldo(22.47, [
        {"codice_tributo": "8907", "periodo_riferimento": "2021", "importo_debito": 22.47}]))
    secondo = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-due", "b.pdf"))
    assert secondo["duplicate"] is False
    docs = {d["id"]: d for d in db[qi.COLL_QUIETANZE].docs}
    assert len(docs) == 2
    assert docs[secondo["quietanza_id"]]["protocollo_condiviso_con"] == [primo["quietanza_id"]]


def test_la_pulizia_doppioni_non_fonde_saldi_diversi():
    from app.services.doppioni_archivio import gruppi_doppioni, identita_quietanza, _punteggio_quietanza

    docs = [
        {"id": "a", "protocollo_telematico": "22110435162612174/000001", "saldo": 2946.31},
        {"id": "b", "protocollo_telematico": "22110435162612174/000001", "saldo": 2946.31},
        {"id": "c", "protocollo_telematico": "22110435162612174/000001", "saldo": 22.47},
    ]
    gruppi = gruppi_doppioni(docs, identita_quietanza, _punteggio_quietanza)
    assert len(gruppi) == 1
    resta, copie = gruppi[0]
    assert {resta["id"], *[c["id"] for c in copie]} == {"a", "b"}


def test_ricevuta_senza_righe_tributo_non_e_una_quietanza(monkeypatch):
    # Quietanza mutuo o ricevuta di bonifico: quadra (zero = zero) ma non ha righe.
    _patch_parser(monkeypatch, {**PARSED_OK, "sezione_erario": [],
                                "dati_generali": {**PARSED_OK["dati_generali"], "saldo_delega": 0},
                                "totali": {"saldo_netto": 0}})
    db = _FakeDb()
    esito = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-mutuo", "quietanza_mutuo.pdf"))
    assert esito["success"] is False and esito["stato_quietanza"] == "NON_QUIETANZA_F24"
    assert db[qi.COLL_QUIETANZE].docs == []


def test_f24_a_saldo_zero_entra_come_compensazione_senza_alert(monkeypatch):
    parsed = {
        **PARSED_OK,
        "dati_generali": {**PARSED_OK["dati_generali"], "saldo_delega": 0,
                          "protocollo_telematico": "20100536070838682-000001", "data_pagamento": "2020-10-05"},
        "sezione_erario": [
            {"codice_tributo": "1012", "periodo_riferimento": "09/2020", "importo_debito": 395.73},
            {"codice_tributo": "1631", "periodo_riferimento": "09/2020", "importo_credito": 395.73},
        ],
        "totali": {"saldo_netto": 0},
    }
    _patch_parser(monkeypatch, parsed)
    db = _FakeDb()
    esito = asyncio.run(qi.importa_quietanza_bytes(db, b"%PDF-zero", "f24_zero.pdf"))
    assert esito["success"] and esito["stato_quietanza"] == "QUIETANZA_COMPENSAZIONE_TOTALE"
    q = db[qi.COLL_QUIETANZE].docs[0]
    assert q["compensazione_totale"] is True and q["calcolo_fiscale_sospeso"] is False
    assert db[qi.COLL_F24_ALERTS].docs == []
    assert "compensazione" in esito["riscontro_banca"].get("saltato", "")


# ── copia del Cassetto (senza data) e quietanza con la data: la stessa delega ─────────

def _riga(sez, codice, periodo, deb, cred):
    return {"codice_tributo": codice, "periodo_riferimento": periodo,
            "importo_debito_cents": deb, "importo_credito_cents": cred, **({"causale": codice} if sez == "inps" else {})}


def _delega(data):
    return {
        "dati_generali": {"protocollo_telematico": "", "saldo_delega": 4272.67, "data_pagamento": data,
                          "codice_fiscale": ""},
        "sezione_erario": [_riga("erario", "1655", "12/2018", 0, 222507), _riga("erario", "1627", "2018", 0, 83207)],
        "sezione_inps": [_riga("inps", "DM10", "12/2018", 686700, 0)],
        "sezione_regioni": [_riga("regioni", "3802", "12/2018", 44272, 0)],
        "sezione_tributi_locali": [_riga("locali", "3848", "12/2018", 44272, 0)],
        "sezione_inail": [],
        "validazione": {"saldo_quadrato": True},
        "totali": {"saldo_netto": 4272.67},
    }


def _importa_in_ordine(monkeypatch, *documenti):
    """documenti: (nome, contenuto, delega letta). Ritorna (db, esiti)."""
    from mongomock_motor import AsyncMongoMockClient
    import app.services.f24_parser as fp

    letti = {contenuto: delega for _nome, contenuto, delega in documenti}
    monkeypatch.setattr(fp, "parse_quietanza_f24", lambda pdf_content=None, **_: letti[pdf_content])
    db = AsyncMongoMockClient()["quietanze"]

    async def run():
        return [await qi.importa_quietanza_bytes(db, c, n, fonte="upload_manuale") for n, c, _d in documenti]
    return db, asyncio.run(run())


def test_copia_del_cassetto_senza_data_e_quietanza_con_data_sono_una_sola_delega(monkeypatch):
    cassetto = ("cassetto.pdf", b"%PDF-cassetto", _delega(None))
    datata = ("quietanza.pdf", b"%PDF-datata", _delega("2019-01-16"))
    for ordine in ((datata, cassetto), (cassetto, datata)):
        db, esiti = _importa_in_ordine(monkeypatch, *ordine)
        assert all(e["success"] for e in esiti)
        quietanze = asyncio.run(db["quietanze_f24"].find({}).to_list(10))
        assert len(quietanze) == 1                                   # mai due quietanze per lo stesso pagamento
        assert quietanze[0]["data_pagamento"] == "2019-01-16"          # la data arriva dal pezzo che la porta
        assert len(quietanze[0]["source_occurrences"]) == 2            # le due provenienze restano


def test_due_deleghe_con_saldo_o_righe_diversi_non_si_fondono(monkeypatch):
    altra = _delega("2019-02-18")
    altra["sezione_regioni"] = [_riga("regioni", "3802", "01/2019", 15329, 0)]
    altra["dati_generali"]["saldo_delega"] = 4272.67
    db, esiti = _importa_in_ordine(
        monkeypatch, ("a.pdf", b"%PDF-a", _delega("2019-01-16")), ("b.pdf", b"%PDF-b", altra))
    assert len(asyncio.run(db["quietanze_f24"].find({}).to_list(10))) == 2


def test_la_stampa_del_cassetto_si_riconosce_dall_intestazione():
    from app.services.f24_parser import e_stampa_cassetto

    testo = ("DELEGA IRREVOCABILE A:\nData: 01/10/2026 - Ore: 07:57:11 - Utente: 04523831214\n"
             "Soggetto: CERALDI GROUP S.R.L.\n( 04523831214 )\n")
    assert e_stampa_cassetto(testo)
    assert not e_stampa_cassetto("DELEGA IRREVOCABILE A:\nSoggetto: CERALDI GROUP S.R.L.\n( 04523831214 )\n")
    assert not e_stampa_cassetto("Data: 01/10/2026 - Ore: 07:57:11 - Utente: 04523831214\nrata mutuo\n")


def test_import_riconosce_la_stampa_del_cassetto_come_quietanza(monkeypatch):
    from app.routers import documenti

    testo = ("Delega irrevocabile a:\nModello di pagamento unificato\nCodice fiscale\nCodice tributo\nSaldo finale\n"
             "Sezione erario\n1655 12 2018\nData: 01/10/2026 - Ore: 07:57:11 - Utente: 04523831214\n"
             "Soggetto: CERALDI GROUP S.R.L.\n( 04523831214 )\n")
    monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda _c: testo)
    assert documenti.detect_document_type("stampa.pdf", b"%PDF-x") == "quietanza_f24"
    # lo stesso modello senza l'intestazione del Cassetto resta un modello da pagare
    monkeypatch.setattr(documenti, "_pdf_text_for_detection", lambda _c: testo.split("Data:")[0])
    assert documenti.detect_document_type("stampa.pdf", b"%PDF-x") == "f24"
