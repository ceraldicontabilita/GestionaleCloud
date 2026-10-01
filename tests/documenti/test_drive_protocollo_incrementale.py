"""Giro incrementale del protocollo Drive (app/services/drive_protocollo.py).

Dal 17/09/2026 il giro completo e' spento (RAM) e nessun file nuovo entrava
nel protocollo: ogni quietanza arrivata dopo risultava `senza_origine`
(«nessun file Drive con la stessa impronta»). Il giro incrementale registra
solo i file nuovi o modificati dall'ultimo giro riuscito, una pagina alla
volta, e rifa la prova dei documenti il cui file e' ora presente.

Nessuna rete: Drive, Postgres e il registro documentale sono finti.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.services import drive_protocollo as modulo
from app.services import postgres_diretto

CARTELLA = modulo.CARTELLA_MIME
ULTIMO_GIRO = datetime(2026, 9, 17, 0, 38, 30, tzinfo=timezone.utc)


def _run(coro):
    return asyncio.run(coro)


# ── finti ────────────────────────────────────────────────────────────────────

class _Lista:
    def __init__(self, drive, kw):
        self.drive, self.kw = drive, kw

    def execute(self):
        self.drive.richieste.append(self.kw)
        if self.drive.errore:
            raise self.drive.errore
        q = self.kw["q"]
        if f"mimeType = '{CARTELLA}'" in q:
            return {"files": self.drive.cartelle}
        pagine = self.drive.pagine
        idx = int(self.kw.get("pageToken") or 0)
        out = {"files": pagine[idx]}
        if idx + 1 < len(pagine):
            out["nextPageToken"] = str(idx + 1)
        return out


class _Files:
    def __init__(self, drive):
        self.drive = drive

    def list(self, **kw):
        return _Lista(self.drive, kw)


class DriveFinto:
    def __init__(self, cartelle, pagine, errore=None):
        self.cartelle, self.pagine, self.errore = cartelle, pagine, errore
        self.richieste = []

    def files(self):
        return _Files(self)

    def richieste_file(self):
        return [r for r in self.richieste if f"mimeType != '{CARTELLA}'" in r["q"]]


def _cartella(id_, nome, padre):
    return {"id": id_, "name": nome, "parents": [padre]}


def _file(id_, nome, padre, md5="aa"):
    return {"id": id_, "name": nome, "mimeType": "application/pdf", "parents": [padre], "size": "1000",
            "md5Checksum": md5, "createdTime": "2026-09-30T10:00:00Z", "modifiedTime": "2026-09-30T10:00:00Z",
            "webViewLink": f"https://drive/{id_}"}


CARTELLE = [
    _cartella("DATI", "DATI SOCIETA CERALDI", "ROOT"),
    _cartella("DAE", "DA ELABORARE", "DATI"),
    _cartella("ALTRA", "Altra cartella", "ESTERNA"),     # fuori dalla radice
]


class ConnFinta:
    def __init__(self, ultimo_ok=ULTIMO_GIRO, esistenti=()):
        self.ultimo_ok, self.esistenti = ultimo_ok, set(esistenti)
        self.sql, self.chiamate, self.upsert = [], [], []
        self.presenti = []
        self.chiusa = False

    async def fetchval(self, sql, *args):
        self.sql.append(sql)
        self.chiamate.append((sql, args))
        if "max(avvio)" in sql:
            return self.ultimo_ok
        if "insert into gestionale.protocollo_drive_giri" in sql:
            return 67
        return None

    async def execute(self, sql, *args):
        self.sql.append(sql)
        self.chiamate.append((sql, args))
        if "duplicato_di = case" in sql:
            return "UPDATE 2"
        if "set collegamento_tipo" in sql:
            return "UPDATE 1"
        return "OK"

    async def fetch(self, sql, *args):
        self.sql.append(sql)
        self.chiamate.append((sql, args))
        if sql.startswith("insert into gestionale.protocollo_drive ("):
            self.upsert.append(list(zip(*args[:len(modulo._COLONNE)])))
            return [{"inserito": i not in self.esistenti} for i in args[0]]
        if "from gestionale.protocollo_drive where rimosso_il is null" in sql:
            return self.presenti
        return []

    async def close(self):
        self.chiusa = True

    def testo(self):
        return " || ".join(self.sql)


def _configura(monkeypatch, conn, incrementale=True, radice="ROOT"):
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_GESTIONALE_ROOT_FOLDER_ID", radice)
    monkeypatch.setattr(settings, "PROTOCOLLO_DRIVE_ENABLED", False)          # il giro completo resta spento
    monkeypatch.setattr(settings, "PROTOCOLLO_DRIVE_INCREMENTALE", incrementale)
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://finto:finto@localhost/gc")

    async def connetti(dsn):
        return conn

    monkeypatch.setattr(postgres_diretto, "connetti", connetti)


# ── percorso ──────────────────────────────────────────────────────────────────

def test_percorso_dalle_cartelle_fino_alla_radice():
    cartelle = modulo._elenca_cartelle(DriveFinto(CARTELLE, []))
    assert modulo.percorso_cartelle("ROOT", cartelle, "ROOT") == []                    # file nella radice
    assert modulo.percorso_cartelle("DAE", cartelle, "ROOT") == ["DATI SOCIETA CERALDI", "DA ELABORARE"]
    assert modulo.percorso_cartelle("ALTRA", cartelle, "ROOT") is None                 # fuori dall'albero
    assert modulo.percorso_cartelle("SCONOSCIUTA", cartelle, "ROOT") is None
    assert modulo.percorso_cartelle(None, cartelle, "ROOT") is None
    ciclo = {"A": ("a", "B"), "B": ("b", "A")}
    assert modulo.percorso_cartelle("A", ciclo, "ROOT") is None                        # niente giri a vuoto


# ── giro incrementale ─────────────────────────────────────────────────────────

def test_registra_solo_i_file_dentro_la_radice_una_pagina_alla_volta(monkeypatch):
    conn = ConnFinta(esistenti={"F1"})
    _configura(monkeypatch, conn)
    drive = DriveFinto(CARTELLE, [
        [_file("F1", "Quietanza_A (2).pdf", "DAE", md5="m1"), _file("F2", "Quietanza_A (3).pdf", "DAE", md5="m2")],
        [_file("F3", "estraneo.pdf", "ALTRA"), _file("F4", "radice.pdf", "ROOT", md5="m4")],
    ])
    esito = _run(modulo.sincronizza_incrementale(service=drive, conn=conn))
    assert esito["esito"] == "ok" and esito["modo"] == "incrementale"
    assert esito["file_visti"] == 4 and esito["fuori_radice"] == 1
    assert esito["nuovi"] == 2 and esito["aggiornati"] == 1 and esito["giro_id"] == 67
    assert esito["duplicati_marcati"] == 2 and esito["collegati"] == 1
    # memoria costante: un upsert per pagina, mai l'intero elenco insieme
    assert [len(u) for u in conn.upsert] == [2, 1]
    righe = {r[0]: r for u in conn.upsert for r in u}
    assert set(righe) == {"F1", "F2", "F4"}                       # F3 sta fuori dalla radice
    col = {c: i for i, c in enumerate(modulo._COLONNE)}
    assert righe["F2"][col["percorso"]] == "DATI SOCIETA CERALDI/DA ELABORARE/Quietanza_A (3).pdf"
    assert righe["F2"][col["area"]] == "DATI SOCIETA CERALDI" and righe["F2"][col["categoria"]] == "DA ELABORARE"
    assert righe["F4"][col["percorso"]] == "radice.pdf" and righe["F4"][col["area"]] is None
    assert not conn.chiusa                                          # connessione passata: non la chiude lui


def test_chiede_a_drive_solo_i_file_modificati_dopo_l_ultimo_giro_con_margine(monkeypatch):
    conn = ConnFinta()
    _configura(monkeypatch, conn)
    drive = DriveFinto(CARTELLE, [[]])
    _run(modulo.sincronizza_incrementale(service=drive, conn=conn))
    (richiesta,) = drive.richieste_file()
    atteso = (ULTIMO_GIRO - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    assert f"modifiedTime > '{atteso}'" in richiesta["q"]
    assert "trashed = false" in richiesta["q"] and richiesta["pageSize"] == 1000


def test_non_marca_rimossi_e_chiude_il_giro_ok_con_rimossi_zero(monkeypatch):
    conn = ConnFinta()
    _configura(monkeypatch, conn)
    _run(modulo.sincronizza_incrementale(service=DriveFinto(CARTELLE, [[_file("F1", "a.pdf", "DAE")]]), conn=conn))
    testo = conn.testo()
    assert "stato = 'rimosso'" not in testo.replace("set fine=now(), esito='interrotto'", "")
    assert "rimossi=0" in testo and "esito='ok'" in testo
    # ordine: giro aperto, upsert, duplicati, collegamento, chiusura
    assert testo.index("insert into gestionale.protocollo_drive_giri") < testo.index("insert into gestionale.protocollo_drive (")
    assert testo.index("duplicato_di = case") < testo.index("set collegamento_tipo") < testo.index("esito='ok'")


def test_chiude_come_interrotto_un_giro_rimasto_aperto_da_ore(monkeypatch):
    conn = ConnFinta()
    _configura(monkeypatch, conn)
    _run(modulo.sincronizza_incrementale(service=DriveFinto(CARTELLE, [[]]), conn=conn))
    prima = conn.sql[0]
    assert "esito='interrotto'" in prima and "esito='in_corso'" in prima and "interval '3 hours'" in prima


def test_senza_un_giro_riuscito_chiede_il_giro_completo_e_non_scrive(monkeypatch):
    conn = ConnFinta(ultimo_ok=None)
    _configura(monkeypatch, conn)
    drive = DriveFinto(CARTELLE, [[_file("F1", "a.pdf", "DAE")]])
    esito = _run(modulo.sincronizza_incrementale(service=drive, conn=conn))
    assert esito["esito"] == "serve_giro_completo"
    assert conn.upsert == [] and drive.richieste == []
    assert "insert into gestionale.protocollo_drive_giri" not in conn.testo()


def test_disattivato_e_non_configurato_non_toccano_il_database(monkeypatch):
    conn = ConnFinta()
    _configura(monkeypatch, conn, incrementale=False)
    assert _run(modulo.sincronizza_incrementale(service=DriveFinto(CARTELLE, []), conn=conn))["esito"] == "disattivato"
    _configura(monkeypatch, conn, radice=None)
    assert _run(modulo.sincronizza_incrementale(service=DriveFinto(CARTELLE, []), conn=conn))["esito"] == "non_configurato"
    assert conn.sql == []


def test_gira_anche_con_il_giro_completo_spento(monkeypatch):
    conn = ConnFinta()
    _configura(monkeypatch, conn)
    assert settings.PROTOCOLLO_DRIVE_ENABLED is False
    assert _run(modulo.sincronizza_incrementale(service=DriveFinto(CARTELLE, [[]]), conn=conn))["esito"] == "ok"
    assert _run(modulo.sincronizza(service=DriveFinto(CARTELLE, [[]]), conn=conn))["esito"] == "disattivato"


def test_un_errore_di_drive_chiude_il_giro_con_il_tipo_dell_errore_e_si_rilancia(monkeypatch):
    conn = ConnFinta()
    _configura(monkeypatch, conn)
    drive = DriveFinto(CARTELLE, [[]], errore=TimeoutError(""))
    with pytest.raises(TimeoutError):
        _run(modulo.sincronizza_incrementale(service=drive, conn=conn))
    chiusura = [a for s, a in conn.chiamate if "esito='errore'" in s]
    assert chiusura and chiusura[0][1].startswith("TimeoutError")        # il messaggio vuoto non nasconde il tipo


def test_chiude_la_connessione_che_ha_aperto(monkeypatch):
    conn = ConnFinta()
    _configura(monkeypatch, conn)
    _run(modulo.sincronizza_incrementale(service=DriveFinto(CARTELLE, [[]])))
    assert conn.chiusa


# ── prove d'origine ───────────────────────────────────────────────────────────

class _Cursore:
    def __init__(self, righe):
        self.righe = righe

    async def to_list(self, _n):
        return list(self.righe)


class _Coll:
    def __init__(self, righe):
        self.righe, self.aggiornati, self.filtri = righe, [], []

    def find(self, filtro, proiezione=None):
        self.filtri.append(filtro)
        return _Cursore(self.righe)

    async def update_one(self, filtro, aggiornamento):
        self.aggiornati.append((filtro, aggiornamento))


class _Db:
    def __init__(self, **collezioni):
        self.c = collezioni

    def __getitem__(self, nome):
        return self.c[nome]


def test_riallinea_solo_i_documenti_il_cui_file_e_ora_nel_protocollo(monkeypatch):
    conn = ConnFinta()
    conn.presenti = [{"drive_id": "DRV-OK", "md5": "m-ok"}, {"drive_id": "ALTRO", "md5": "m-cedolino"}]
    _configura(monkeypatch, conn)
    db = _Db(
        quietanze_f24=_Coll([
            {"_id": "q1-riga", "id": "uuid-diverso-q1", "drive_file_id": "DRV-OK", "prova": {"stato": "senza_origine"}},     # per id Drive
            {"_id": "q2-riga", "id": "uuid-q2", "drive_file_id": "DRV-MANCA", "prova": {"stato": "senza_origine"}},  # file ancora assente
        ]),
        cedolini=_Coll([
            {"_id": "c1-riga", "id": "uuid-c1", "source_file_hash_md5": "m-cedolino", "prova": {"stato": "senza_origine"}},  # per MD5
        ]),
    )
    esito = _run(modulo.riallinea_prove(db, conn=conn))
    assert esito == {"esito": "ok", "senza_origine": 3, "con_file_ora_presente": 2, "riallineati": 2}
    assert [f for f, _ in db["quietanze_f24"].aggiornati] == [{"_id": "q1-riga"}]       # per _id, non per il campo id
    assert [f for f, _ in db["cedolini"].aggiornati] == [{"_id": "c1-riga"}]
    nome, valore = next(iter(db["quietanze_f24"].aggiornati[0][1]["$set"].items()))
    assert nome == "prova_riallineata_il" and "T" in valore                       # solo un marcatore: la prova la rifa il trigger
    assert db["quietanze_f24"].filtri == [{"prova.stato": "senza_origine"}]
    assert not conn.chiusa


def test_riallinea_niente_se_nessun_documento_e_senza_origine(monkeypatch):
    conn = ConnFinta()
    _configura(monkeypatch, conn)
    db = _Db(quietanze_f24=_Coll([]), cedolini=_Coll([]))
    assert _run(modulo.riallinea_prove(db, conn=conn)) == {"esito": "ok", "senza_origine": 0, "riallineati": 0}
    assert not any("protocollo_drive" in s for s in conn.sql)                      # nemmeno una query al protocollo


def test_riallinea_rispetta_il_limite_per_giro(monkeypatch):
    conn = ConnFinta()
    conn.presenti = [{"drive_id": f"D{i}", "md5": None} for i in range(5)]
    _configura(monkeypatch, conn)
    db = _Db(quietanze_f24=_Coll([{"_id": f"q{i}", "drive_file_id": f"D{i}"} for i in range(5)]), cedolini=_Coll([]))
    esito = _run(modulo.riallinea_prove(db, conn=conn, limite=2))
    assert esito["riallineati"] == 2 and esito["con_file_ora_presente"] == 5
    assert len(db["quietanze_f24"].aggiornati) == 2


# ── scheduler ─────────────────────────────────────────────────────────────────

class _SchedulerFinto:
    def __init__(self):
        self.jobs = []
        self.running = False

    def add_job(self, fn, *args, **kwargs):
        self.jobs.append((fn, args, kwargs))

    def start(self):
        self.running = True


def test_il_giro_incrementale_e_registrato_ogni_20_minuti(monkeypatch):
    import app.scheduler as scheduler_mod

    finto = _SchedulerFinto()
    monkeypatch.setattr(scheduler_mod, "scheduler", finto)
    scheduler_mod.start_scheduler()
    job = [j for j in finto.jobs if isinstance(j[2], dict) and j[2].get("id") == "protocollo_drive_incrementale"]
    assert len(job) == 1
    assert job[0][1][0] == "interval" and job[0][2]["minutes"] == 20
    # il giro completo non e' stato riacceso da nessuna parte
    assert not [j for j in finto.jobs if isinstance(j[2], dict) and j[2].get("id") == "protocollo_drive"]


def test_il_job_non_riallinea_le_prove_se_il_giro_non_e_riuscito(monkeypatch):
    import asyncio as _a

    import app.scheduler as scheduler_mod
    from app.database import Database

    finto = _SchedulerFinto()
    monkeypatch.setattr(scheduler_mod, "scheduler", finto)
    scheduler_mod.start_scheduler()
    job = next(j for j in finto.jobs if isinstance(j[2], dict) and j[2].get("id") == "protocollo_drive_incrementale")[0]

    chiamate = []

    async def giro(*a, **k):
        chiamate.append("giro")
        return {"esito": "serve_giro_completo"}

    async def prove(*a, **k):
        chiamate.append("prove")
        return {}

    monkeypatch.setattr(modulo, "sincronizza_incrementale", giro)
    monkeypatch.setattr(modulo, "riallinea_prove", prove)
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: object()))
    monkeypatch.setattr(settings, "PROTOCOLLO_DRIVE_INCREMENTALE", True)
    _a.run(job())
    assert chiamate == ["giro"]


def test_un_giro_senza_file_nuovi_non_rifa_duplicati_impronte_e_collegamenti(monkeypatch):
    conn = ConnFinta()
    _configura(monkeypatch, conn)
    esito = _run(modulo.sincronizza_incrementale(service=DriveFinto(CARTELLE, [[]]), conn=conn))
    assert esito["file_visti"] == 0 and esito["nuovi"] == 0 and esito["aggiornati"] == 0
    testo = conn.testo()
    assert "duplicato_di = case" not in testo and "protocollo_impronte" not in testo and "set collegamento_tipo" not in testo
    assert "esito='ok'" in testo                                   # il giro si chiude comunque: sposta in avanti la finestra


def test_riallinea_con_il_motore_documentale_vero_filtro_annidato_e_chiave_di_riga(monkeypatch):
    """Stesso percorso di produzione, con l'archivio in memoria al posto di Supabase:
    il filtro `prova.stato`, la proiezione senza payload, la riscrittura per `_id`."""
    from app.services.archivio_documenti_memoria import ClientArchivioMemoria

    conn = ConnFinta()
    conn.presenti = [{"drive_id": "D1", "md5": None}]
    _configura(monkeypatch, conn)
    db = ClientArchivioMemoria()["prova"]

    async def scenario():
        await db["quietanze_f24"].insert_one({"_id": "riga-1", "id": "uuid-1", "drive_file_id": "D1", "pdf_data": "AAAA",
                                              "prova": {"stato": "senza_origine"}})
        await db["quietanze_f24"].insert_one({"_id": "riga-2", "id": "uuid-2", "drive_file_id": "D1",
                                              "prova": {"stato": "da_rileggere"}})            # gia' con origine
        esito = await modulo.riallinea_prove(db, conn=conn)
        riga = await db["quietanze_f24"].find_one({"_id": "riga-1"})
        altra = await db["quietanze_f24"].find_one({"_id": "riga-2"})
        return esito, riga, altra

    esito, riga, altra = _run(scenario())
    assert esito["senza_origine"] == 1 and esito["riallineati"] == 1
    assert "prova_riallineata_il" in riga and riga["pdf_data"] == "AAAA"       # il payload non si perde
    assert "prova_riallineata_il" not in altra                                # chi ha gia' l'origine non si riscrive
