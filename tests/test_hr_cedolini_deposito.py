"""Deposito dei cedolini del gestionale nell'archivio dell'app HR (app_cedolini).

Nessuna rete: la connessione asyncpg e' sostituita da una finta che risponde
alle tre query del servizio (anagrafica HR, cedolini esistenti, INSERT).
"""
import asyncio
import base64
import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import hr_cedolini_deposito as modulo

CF = "RSSMRA80A01H501U"
DSN_FINTA = "postgresql://finto:finto@localhost/hr"


def _run(coro):
    return asyncio.run(coro)


class ConnessioneFinta:
    """Risponde come asyncpg alle sole query usate dal servizio."""

    def __init__(self, cedolini=None, dipendenti=None):
        self.cedolini = list(cedolini or [])
        self.dipendenti = list(dipendenti or [])
        self.inseriti = []
        self.chiusa = False

    async def fetch(self, sql, *args):
        if "app_dipendenti" in sql:
            (cf,) = args
            trovati = [d for d in self.dipendenti if (d.get("codice_fiscale") or "").upper() == cf]
            return [{"doc": json.dumps(d)} for d in trovati[:1]]
        if "app_cedolini" in sql:
            cf, anno, mese, dedup = args
            righe = []
            for d in self.cedolini:
                stesso_periodo = (
                    str(d.get("codice_fiscale", "")).upper() == cf
                    and int(d["anno"]) == anno and int(d["mese"]) == mese
                )
                if stesso_periodo or (dedup and d.get("cedolino_dedup_key") == dedup):
                    righe.append({
                        "id": d["id"], "tipo": d.get("tipo_cedolino"),
                        "dedup_key": d.get("cedolino_dedup_key"),
                    })
            return righe
        raise AssertionError("query inattesa: " + sql)

    async def execute(self, sql, *args):
        assert "INSERT INTO" in sql and "app_cedolini" in sql
        chiave, doc = args
        doc = json.loads(doc)
        assert doc["id"] == chiave
        self.inseriti.append(doc)
        return "INSERT 0 1"

    async def close(self):
        self.chiusa = True


def _configura(monkeypatch, connessione):
    monkeypatch.setenv("HR_SUPABASE_DB_URL", DSN_FINTA)
    aperture = []

    async def connetti(dsn):
        aperture.append(dsn)
        return connessione

    monkeypatch.setattr(modulo, "connetti_hr", connetti)
    return aperture


def _cedolino_erp(**extra):
    """Record come lo scrive processa_cedolino_v2 nel registro `cedolini`."""
    base = {
        "id": "erp-ced-1",
        "dipendente_id": "erp-dip-1",
        "nome_dipendente": "ROSSI MARIO",
        "codice_fiscale": CF.lower(),
        "mese": 6,
        "anno": 2026,
        "periodo": "06/2026",
        "tipo_cedolino": "mensile",
        "cedolino_dedup_key": "ced_key_1",
        "netto": 1500.0,
        "netto_mese": 1500.0,
        "lordo": 2000.0,
        "totale_competenze": 2000.0,
        "totale_trattenute": 500.0,
        "ore_lavorate": 160,
        "giorni_lavorati": 22,
        "livello": "6",
        "filename": "Busta paga - Rossi Mario - Giugno 2026.pdf",
        "formato": "zucchetti_new",
        "source": "cedolino_v2",
        "pdf_data": base64.b64encode(b"%PDF-1.4 finto").decode("ascii"),
    }
    base.update(extra)
    return base


DIPENDENTE_HR = {
    "id": "hr-dip-1", "codice_fiscale": CF, "nome": "Mario", "cognome": "Rossi",
    "nome_completo": "Rossi Mario", "attivo": True,
}


# ── mapping ──────────────────────────────────────────────────────────────────

def test_deposito_scrive_il_cedolino_nella_forma_dell_app_hr(monkeypatch):
    con = ConnessioneFinta(dipendenti=[DIPENDENTE_HR])
    aperture = _configura(monkeypatch, con)

    esito = _run(modulo.deposita_cedolino_in_hr(_cedolino_erp()))

    assert esito["esito"] == "inserito"
    assert aperture == [DSN_FINTA]
    assert con.chiusa is True
    assert len(con.inseriti) == 1
    doc = con.inseriti[0]
    assert esito["id"] == doc["id"] and len(doc["id"]) == 36
    # identita' e periodo come nei 1291 documenti gia' in HR
    assert doc["codice_fiscale"] == CF
    assert doc["anno"] == 2026 and doc["mese"] == 6
    assert isinstance(doc["anno"], int) and isinstance(doc["mese"], int)
    assert doc["competenza"] == "2026-06"
    assert doc["tipo_cedolino"] == "ordinario"          # "mensile" del gestionale
    # anagrafica risolta dall'HR, non dagli id del gestionale
    assert doc["dipendente_id"] == "hr-dip-1"
    assert doc["nome_dipendente"] == "Rossi Mario"
    assert doc["dipendente_nome"] == "Rossi Mario"
    # importi
    assert doc["netto"] == 1500.0 and doc["lordo"] == 2000.0
    assert doc["competenze"] == 2000.0 and doc["trattenute"] == 500.0
    assert doc["giorni_lavorati"] == 22 and doc["ore_lavorate"] == 160
    assert doc["livello"] == "6"
    # file e PDF base64 intatto
    assert doc["filename"] == "Busta paga - Rossi Mario - Giugno 2026.pdf"
    assert doc["pdf_filename"] == doc["filename"]
    assert base64.b64decode(doc["pdf_data"]) == b"%PDF-1.4 finto"
    # provenienza
    assert doc["fonte"] == "gestionale_cloud"
    assert doc["parser_template"] == "zucchetti_new"
    assert doc["cedolino_dedup_key"] == "ced_key_1"
    assert doc["gestionale_cedolino_id"] == "erp-ced-1"
    assert doc["created_at"]


def test_mapping_accetta_le_forme_dei_diversi_writer_del_gestionale():
    # upload AI: CF in dipendente_cf, periodo dict, importi con altri nomi
    doc = modulo.mappa_cedolino_per_hr({
        "dipendente_cf": "rssmra80a01h501u", "periodo": {"mese": 3, "anno": 2025},
        "netto_pagato": 1200, "lordo_totale": 1700, "dipendente_nome": "Rossi Mario",
        "pdf_data": b"%PDF-bytes",
    })
    assert (doc["codice_fiscale"], doc["anno"], doc["mese"]) == (CF, 2025, 3)
    assert doc["netto"] == 1200.0 and doc["lordo"] == 1700.0 and doc["competenze"] == 1700.0
    assert base64.b64decode(doc["pdf_data"]) == b"%PDF-bytes"
    assert doc["tipo_cedolino"] == "ordinario"
    assert "parser_template" not in doc          # modello ignoto: non inventato

    # busta manuale: periodo "YYYY-MM"; 13a resta tredicesima
    doc = modulo.mappa_cedolino_per_hr({
        "codice_fiscale": CF, "periodo": "2025-12", "tipo_cedolino": "tredicesima", "netto": "900,5",
    })
    assert (doc["anno"], doc["mese"], doc["tipo_cedolino"]) == (2025, 12, "tredicesima")

    # senza identita' HR non si deposita nulla
    assert modulo.mappa_cedolino_per_hr({"dipendente_id": "x", "mese": 1, "anno": 2025}) is None
    assert modulo.mappa_cedolino_per_hr({"codice_fiscale": CF}) is None


def test_dati_insufficienti_non_apre_connessioni(monkeypatch):
    async def mai(dsn):
        raise AssertionError("non deve connettersi")

    monkeypatch.setenv("HR_SUPABASE_DB_URL", DSN_FINTA)
    monkeypatch.setattr(modulo, "connetti_hr", mai)
    esito = _run(modulo.deposita_cedolino_in_hr({"dipendente_id": "erp-1", "netto": 10}))
    assert esito == {"esito": "dati_insufficienti", "id": None}


# ── dedup ────────────────────────────────────────────────────────────────────

def test_cedolino_gia_in_hr_non_viene_sovrascritto(monkeypatch):
    esistente = {"id": "hr-ced-1", "codice_fiscale": CF, "anno": 2026, "mese": 6,
                 "tipo_cedolino": "ordinario", "netto": 1499}
    con = ConnessioneFinta(cedolini=[esistente], dipendenti=[DIPENDENTE_HR])
    _configura(monkeypatch, con)

    esito = _run(modulo.deposita_cedolino_in_hr(_cedolino_erp(netto=1500)))

    assert esito["esito"] == "gia_presente"
    assert esito["id"] == "hr-ced-1"
    assert con.inseriti == []


def test_dedup_riconosce_la_chiave_documentale_anche_con_periodo_diverso(monkeypatch):
    esistente = {"id": "hr-ced-2", "codice_fiscale": CF, "anno": 2026, "mese": 5,
                 "tipo_cedolino": "ordinario", "cedolino_dedup_key": "ced_key_1"}
    con = ConnessioneFinta(cedolini=[esistente], dipendenti=[DIPENDENTE_HR])
    _configura(monkeypatch, con)

    esito = _run(modulo.deposita_cedolino_in_hr(_cedolino_erp()))

    assert esito["esito"] == "gia_presente" and esito["id"] == "hr-ced-2"
    assert con.inseriti == []


def test_tredicesima_dello_stesso_mese_e_un_cedolino_distinto(monkeypatch):
    esistente = {"id": "hr-ced-3", "codice_fiscale": CF, "anno": 2026, "mese": 12,
                 "tipo_cedolino": "ordinario"}
    con = ConnessioneFinta(cedolini=[esistente], dipendenti=[DIPENDENTE_HR])
    _configura(monkeypatch, con)

    esito = _run(modulo.deposita_cedolino_in_hr(
        _cedolino_erp(mese=12, tipo_cedolino="tredicesima", cedolino_dedup_key="ced_key_13")
    ))

    assert esito["esito"] == "inserito"
    assert con.inseriti[0]["tipo_cedolino"] == "tredicesima"


def test_dipendente_hr_assente_lascia_il_cf_per_il_portale(monkeypatch):
    con = ConnessioneFinta()
    _configura(monkeypatch, con)

    esito = _run(modulo.deposita_cedolino_in_hr(_cedolino_erp()))

    assert esito["esito"] == "inserito"
    assert con.inseriti[0]["dipendente_id"] is None
    assert con.inseriti[0]["codice_fiscale"] == CF
    assert con.inseriti[0]["nome_dipendente"] == "ROSSI MARIO"


def test_dry_run_non_scrive(monkeypatch):
    con = ConnessioneFinta(dipendenti=[DIPENDENTE_HR])
    _configura(monkeypatch, con)

    esito = _run(modulo.deposita_cedolino_in_hr(_cedolino_erp(), dry_run=True))

    assert esito["esito"] == "da_inserire"
    assert con.inseriti == []


# ── configurazione assente / errori ──────────────────────────────────────────

def test_senza_dsn_il_deposito_e_un_no_op_segnalato_una_volta(monkeypatch, caplog):
    for nome in modulo.ENV_DSN_HR:
        monkeypatch.delenv(nome, raising=False)

    async def mai(dsn):
        raise AssertionError("non deve connettersi")

    monkeypatch.setattr(modulo, "connetti_hr", mai)
    monkeypatch.setattr(modulo, "_avviso_non_configurato_emesso", False)

    with caplog.at_level(logging.WARNING, logger=modulo.__name__):
        primo = _run(modulo.deposita_cedolino_in_hr(_cedolino_erp()))
        secondo = _run(modulo.deposita_cedolino_in_hr(_cedolino_erp()))

    assert primo == {"esito": "hr_non_configurato", "id": None}
    assert secondo == primo
    avvisi = [r for r in caplog.records if "nessuna DSN HR" in r.getMessage()]
    assert len(avvisi) == 1


def test_errore_di_rete_non_solleva(monkeypatch):
    monkeypatch.setenv("HR_SUPABASE_DB_URL", DSN_FINTA)

    async def connessione_rotta(dsn):
        raise ConnectionRefusedError("HR irraggiungibile")

    monkeypatch.setattr(modulo, "connetti_hr", connessione_rotta)
    esito = _run(modulo.deposita_cedolino_in_hr(_cedolino_erp()))
    assert esito["esito"] == "errore"
    assert "irraggiungibile" in esito["errore"]


# ── il flusso di ingestione chiama il deposito e sopravvive al suo fallimento ─

def _matches(doc, query):
    if "$or" in query:
        return any(_matches(doc, branch) for branch in query["$or"])
    for key, value in query.items():
        if key.startswith("$"):
            return False
        if isinstance(value, dict) and "$exists" in value:
            if (key in doc) != value["$exists"]:
                return False
        elif isinstance(value, dict) and "$in" in value:
            if doc.get(key) not in value["$in"]:
                return False
        elif doc.get(key) != value:
            return False
    return True


class _Collection:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, *args, **kwargs):
        return next((dict(d) for d in self.docs if _matches(d, query)), None)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False, **kwargs):
        for doc in self.docs:
            if _matches(doc, query):
                doc.update(update.get("$set", {}))
                return
        if upsert:
            self.docs.append(dict(update.get("$set", {})))


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Collection())


def _ingestione_v2(monkeypatch, deposito):
    from app.services import salari_unificati_v2 as v2
    import app.services.event_bus as event_bus

    async def no_match(*args, **kwargs):
        return False

    async def no_event(*args, **kwargs):
        return None

    import app.services.cedolini_manager as manager
    monkeypatch.setattr(manager, "riconcilia_stipendio_automatico", no_match)
    monkeypatch.setattr(event_bus, "propagate_event", no_event)
    monkeypatch.setattr(modulo, "deposita_cedolino_in_hr", deposito)

    db = _Db()
    pdf = base64.b64encode(b"%PDF-1.4 cedolino").decode()
    dati = {
        "codice_fiscale": CF, "nome_dipendente": "Rossi Mario", "mese": 6, "anno": 2026,
        "netto_mese": 1500, "lordo": 2000, "tipo_cedolino": "mensile",
        "giorni_lavorati": 22, "livello": "6",
    }
    res = _run(v2.processa_cedolino_v2(db, dati, "", "giugno.pdf", pdf))
    return db, res, pdf


def test_ingestione_v2_deposita_la_busta_letta_in_hr(monkeypatch):
    chiamate = []

    async def deposito(cedolino, **kwargs):
        chiamate.append(cedolino)
        return {"esito": "inserito", "id": "hr-nuovo"}

    db, res, pdf = _ingestione_v2(monkeypatch, deposito)

    assert res["success"] is True
    assert res["deposito_hr"] == "inserito"
    assert len(chiamate) == 1
    inviato = chiamate[0]
    assert inviato["codice_fiscale"] == CF
    assert (inviato["anno"], inviato["mese"]) == (2026, 6)
    assert inviato["pdf_data"] == pdf
    assert inviato["netto"] == 1500 and inviato["lordo"] == 2000
    assert inviato["giorni_lavorati"] == 22 and inviato["livello"] == "6"
    assert inviato["cedolino_dedup_key"]
    # il registro del gestionale resta scritto (Prima Nota salari lo usa)
    assert len(db["cedolini"].docs) == 1
    assert len(db["prima_nota_salari"].docs) == 1


def test_ingestione_v2_sopravvive_al_fallimento_del_deposito(monkeypatch):
    async def deposito_rotto(cedolino, **kwargs):
        raise RuntimeError("HR giu'")

    db, res, _ = _ingestione_v2(monkeypatch, deposito_rotto)

    assert res["success"] is True
    assert res["errore"] is None
    assert "deposito_hr" not in res
    assert len(db["cedolini"].docs) == 1
    assert len(db["prima_nota_salari"].docs) == 1


# ── backfill: endpoint admin e conteggi ──────────────────────────────────────

def _client_e_db(monkeypatch):
    from app.database import Database
    from app.routers.accounting import prima_nota_salari
    from app.services.sheets_document_store import SheetDatabase

    db = SheetDatabase("test")
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: db))
    app = FastAPI()
    app.include_router(prima_nota_salari.router, prefix="/api/prima-nota-salari")
    return TestClient(app), db


def _header_admin():
    from app.utils.auth_tokens import create_access_token

    return {"Authorization": "Bearer " + create_access_token(user_id="admin-test", role="admin")}


def test_backfill_endpoint_conta_gli_esiti(monkeypatch):
    client, db = _client_e_db(monkeypatch)
    _run(db["cedolini"].insert_one(_cedolino_erp(id="erp-1")))
    _run(db["cedolini"].insert_one(_cedolino_erp(id="erp-2", mese=7, cedolino_dedup_key="k2")))
    _run(db["cedolini"].insert_one(_cedolino_erp(id="erp-3", mese=8, cedolino_dedup_key="k3")))
    _run(db["cedolini"].insert_one({"id": "erp-4", "dipendente_id": "solo-id", "netto": 5}))

    con = ConnessioneFinta()
    _configura(monkeypatch, con)
    esiti = {"erp-1": "inserito", "erp-2": "gia_presente", "erp-3": "errore"}
    ricevuti = []

    async def deposito(cedolino, con=None, dry_run=False):
        ricevuti.append((cedolino["id"], con is not None, dry_run))
        return {"esito": esiti.get(cedolino.get("id"), "dati_insufficienti"),
                "id": None, "errore": "x", "codice_fiscale": CF, "anno": 2026, "mese": 1}

    monkeypatch.setattr(modulo, "deposita_cedolino_in_hr", deposito)

    risposta = client.post("/api/prima-nota-salari/deposita-cedolini-in-hr", headers=_header_admin())

    assert risposta.status_code == 200, risposta.text
    corpo = risposta.json()
    assert corpo["hr_configurato"] is True
    assert corpo["totale"] == 4
    assert (corpo["inseriti"], corpo["gia_presenti"], corpo["errori"], corpo["saltati"]) == (1, 1, 1, 1)
    assert corpo["dettagli"][0]["gestionale_cedolino_id"] == "erp-3"
    # una sola connessione riusata per tutto il giro, poi chiusa
    assert all(usa_con for _, usa_con, _ in ricevuti)
    assert con.chiusa is True
    assert sorted(cid for cid, _, _ in ricevuti) == ["erp-1", "erp-2", "erp-3", "erp-4"]


def test_backfill_endpoint_richiede_admin(monkeypatch):
    client, _ = _client_e_db(monkeypatch)
    from app.utils.auth_tokens import create_access_token

    assert client.post("/api/prima-nota-salari/deposita-cedolini-in-hr").status_code == 401
    operatore = {"Authorization": "Bearer " + create_access_token(user_id="op", role="operatore")}
    assert client.post("/api/prima-nota-salari/deposita-cedolini-in-hr", headers=operatore).status_code == 403


def test_backfill_senza_dsn_non_tocca_nulla(monkeypatch):
    for nome in modulo.ENV_DSN_HR:
        monkeypatch.delenv(nome, raising=False)

    async def mai(dsn):
        raise AssertionError("non deve connettersi")

    monkeypatch.setattr(modulo, "connetti_hr", mai)
    db = _Db()
    _run(db["cedolini"].insert_one(_cedolino_erp()))

    class _Cursor:
        def __init__(self, docs):
            self.docs = docs

        async def to_list(self, _n):
            return list(self.docs)

    db["cedolini"].find = lambda *a, **k: _Cursor(db["cedolini"].docs)
    risultato = _run(modulo.deposita_tutti_i_cedolini(db))
    assert risultato["hr_configurato"] is False
    assert risultato["totale"] == 1
    assert risultato["inseriti"] == 0 and risultato["errori"] == 0
