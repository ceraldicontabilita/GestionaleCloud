"""Alert «F24 pagato in ritardo» (decisione del titolare, 02/10/2026).

Il giorno DOPO la scadenza (modello o regola del codice, festivi inclusi) un
modello F24 a debito senza quietanza ne' addebito CERTO in banca apre
`F24_PAGAMENTO_IN_RITARDO` nel catalogo unico; il messaggio porta i giorni di
ritardo e il ravvedimento dello scadenzario (sanzione ridotta per fascia +
interessi legali), che cresce ogni giorno; si chiude da solo con la quietanza
o l'addebito; un alert ignorato non rinasce; il secondo giro non duplica.
Gira nel job delle 08:00 (`invia_notifiche_scadenze`), non in un giro nuovo.
"""
import asyncio
from datetime import date

import pytest

from app.services import f24_scadenze_notifiche as mod
from app.services.alert_engine import ALERT_CATALOG


def _match(doc, query):
    for k, v in query.items():
        campo = doc.get(k)
        if isinstance(v, dict):
            if "$nin" in v and campo in v["$nin"]:
                return False
            if "$in" in v and campo not in v["$in"]:
                return False
            if "$ne" in v and campo == v["$ne"]:
                return False
        elif campo != v:
            return False
    return True


class _Cur:
    def __init__(self, docs):
        self._d = docs

    async def to_list(self, n=None):
        return [dict(d) for d in self._d]


class _Res:
    def __init__(self, n):
        self.modified_count = n


class _Coll:
    def __init__(self):
        self.docs = []

    def find(self, query=None, projection=None):
        return _Cur([d for d in self.docs if _match(d, query or {})])

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _match(d, query):
                return dict(d)
        return None

    async def count_documents(self, query):
        return sum(1 for d in self.docs if _match(d, query))

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                return _Res(1)
        if upsert:
            self.docs.append(dict(update.get("$set", {})))
        return _Res(0)

    async def update_many(self, query, update):
        n = 0
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                n += 1
        return _Res(n)


class _Db:
    def __init__(self):
        self.c = {}

    def __getitem__(self, name):
        return self.c.setdefault(name, _Coll())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


OGGI = date(2026, 10, 2)  # 1001 di agosto 2026: scadenza 16/09/2026, 16 giorni di ritardo


def _modello(id_="M1", **extra):
    return {
        "id": id_, "status": "da_pagare", "descrizione": "F24 agosto 2026",
        "sezione_erario": [{"codice_tributo": "1001", "periodo_riferimento": "08/2026",
                            "importo_debito": 1000.0}],
        **extra,
    }


def _alert_aperti(db):
    return [a for a in db["alerts"].docs if a["codice"] == "F24_PAGAMENTO_IN_RITARDO" and a["stato"] == "aperto"]


def test_il_codice_e_nel_catalogo_unico():
    assert ALERT_CATALOG["F24_PAGAMENTO_IN_RITARDO"]["modulo"] == "f24"
    assert ALERT_CATALOG["F24_PAGAMENTO_IN_RITARDO"]["severita"] == "critical"


def test_scatta_il_giorno_dopo_la_scadenza_non_prima():
    db = _Db()
    db["f24_unificato"].docs = [_modello()]
    # Il 16/09 (giorno di scadenza) e' ancora in tempo: niente alert.
    esito = _run(mod.segnala_f24_in_ritardo(db, oggi=date(2026, 9, 16)))
    assert esito["aperti"] == 0 and not _alert_aperti(db)
    # Il 17/09, un giorno dopo: alert con 1 giorno di ritardo.
    esito = _run(mod.segnala_f24_in_ritardo(db, oggi=date(2026, 9, 17)))
    assert esito["aperti"] == 1
    (alert,) = _alert_aperti(db)
    assert alert["entita_id"] == "M1" and alert["entita_collection"] == "f24_unificato"
    assert alert["extra"]["giorni_ritardo"] == 1
    assert alert["extra"]["scadenza"] == "2026-09-16"
    assert "1 giorni di ritardo" in alert["dettaglio"]


def test_messaggio_con_ravvedimento_dello_scadenzario_che_cresce_ogni_giorno():
    db = _Db()
    db["f24_unificato"].docs = [_modello()]
    esito = _run(mod.segnala_f24_in_ritardo(db, oggi=OGGI))
    assert esito["aperti"] == 1
    (alert,) = _alert_aperti(db)
    r = alert["extra"]["ravvedimento"]
    # 16 giorni: fascia 15–30 → 1,25% di 1.000,00 = 12,50; interessi 1,6% × 16/365 = 0,70
    assert r["giorni_ritardo"] == 16
    assert r["sanzione_cents"] == 1250 and r["interessi_cents"] == 70
    assert r["totale_cents"] == 100000 + 1250 + 70
    assert "12,50 €" in alert["dettaglio"] and "0,70 €" in alert["dettaglio"]
    assert "cresce ogni giorno" in alert["dettaglio"]

    # Dieci giorni dopo: stesso alert (nessun doppione), ravvedimento piu' alto.
    esito = _run(mod.segnala_f24_in_ritardo(db, oggi=date(2026, 10, 12)))
    assert esito["aperti"] == 0 and esito["aggiornati"] == 1
    (alert2,) = _alert_aperti(db)
    assert alert2["id"] == alert["id"]
    assert alert2["extra"]["giorni_ritardo"] == 26
    assert alert2["extra"]["ravvedimento"]["interessi_cents"] > r["interessi_cents"]
    assert alert2["extra"]["ravvedimento"]["sanzione_cents"] == 1250  # stessa fascia 15–30


def test_secondo_giro_nello_stesso_giorno_non_duplica():
    db = _Db()
    db["f24_unificato"].docs = [_modello()]
    _run(mod.segnala_f24_in_ritardo(db, oggi=OGGI))
    esito = _run(mod.segnala_f24_in_ritardo(db, oggi=OGGI))
    assert esito["aperti"] == 0 and esito["aggiornati"] == 1
    assert len(_alert_aperti(db)) == 1


@pytest.mark.parametrize("prova", [
    {"quietanza_id": "q-1", "data_pagamento_quietanza": "2026-09-30"},
    {"movimento_bancario_id": "ec-1", "data_pagamento_effettivo": "2026-09-30"},
])
def test_si_chiude_da_solo_con_quietanza_o_addebito_certo(prova):
    db = _Db()
    db["f24_unificato"].docs = [_modello()]
    _run(mod.segnala_f24_in_ritardo(db, oggi=OGGI))
    assert len(_alert_aperti(db)) == 1
    db["f24_unificato"].docs[0].update(prova)
    esito = _run(mod.segnala_f24_in_ritardo(db, oggi=OGGI))
    assert esito["chiusi"] == 1 and esito["chiusi_ids"] == ["M1"]
    assert not _alert_aperti(db)
    (chiuso,) = db["alerts"].docs
    assert chiuso["stato"] == "risolto" and chiuso["resolved_by"] == "quietanza_o_addebito_banca"


def test_la_quietanza_agganciata_dal_suo_lato_chiude_anche_senza_quietanza_id_sul_modello():
    db = _Db()
    db["f24_unificato"].docs = [_modello()]
    db["quietanze_f24"].docs = [{"id": "q-9", "f24_associati": ["M1"]}]
    esito = _run(mod.segnala_f24_in_ritardo(db, oggi=OGGI))
    assert esito["aperti"] == 0 and not _alert_aperti(db)


def test_un_alert_ignorato_dal_titolare_non_rinasce():
    db = _Db()
    db["f24_unificato"].docs = [_modello()]
    _run(mod.segnala_f24_in_ritardo(db, oggi=OGGI))
    (alert,) = _alert_aperti(db)
    alert["stato"] = "ignorato"
    esito = _run(mod.segnala_f24_in_ritardo(db, oggi=date(2026, 10, 12)))
    assert esito["aperti"] == 0 and esito["aggiornati"] == 0 and esito["ignorati"] == 1
    assert not _alert_aperti(db)
    assert len(db["alerts"].docs) == 1


def test_senza_prova_bancaria_certa_la_relazione_pending_non_basta():
    """PROBABILE/PARZIALE sono relazioni pending, non una prova: l'alert resta."""
    db = _Db()
    db["f24_unificato"].docs = [_modello(movimento_bancario_candidato="ec-7")]
    esito = _run(mod.segnala_f24_in_ritardo(db, oggi=OGGI))
    assert esito["aperti"] == 1


def test_fuori_dal_giro_quietanze_ravvedimenti_eliminati_e_pagati():
    db = _Db()
    db["f24_unificato"].docs = [
        _modello("ELIM", status="eliminato"),
        _modello("PAG", status="pagato"),
        _modello("RAVV", etichetta="RAVVEDIMENTO"),
        {"id": "Q", "status": "da_pagare", "tipo_documento": "quietanza_f24",
         "sezione_erario": [{"codice_tributo": "1001", "periodo_riferimento": "08/2026", "importo_debito": 5.0}]},
        _modello("SOLO_CREDITO", sezione_erario=[
            {"codice_tributo": "1001", "periodo_riferimento": "08/2026", "importo_credito": 100.0}]),
    ]
    esito = _run(mod.segnala_f24_in_ritardo(db, oggi=OGGI))
    assert esito["aperti"] == 0 and not _alert_aperti(db)
    assert esito["senza_scadenza"] == 1  # il modello a solo credito non ha scadenza, non si inventa


def test_righe_inps_restano_da_verificare_mai_stimate():
    db = _Db()
    db["f24_unificato"].docs = [_modello(sezione_inps=[
        {"causale": "DM10", "periodo_riferimento": "08/2026", "importo_debito": 500.0,
         "sede": "4900", "matricola": "1234567890"}])]
    _run(mod.segnala_f24_in_ritardo(db, oggi=OGGI))
    (alert,) = _alert_aperti(db)
    r = alert["extra"]["ravvedimento"]
    assert [x["codice"] for x in r["righe_da_verificare"]] == ["DM10"]
    assert r["tributo_cents"] == 100000  # solo il 1001 entra nel ravvedimento art. 13
    assert "sanzioni civili" in alert["dettaglio"]


def test_data_scadenza_del_modello_vince_sulla_regola():
    db = _Db()
    db["f24_unificato"].docs = [_modello(data_scadenza="2026-10-01")]
    assert _run(mod.segnala_f24_in_ritardo(db, oggi=date(2026, 10, 1)))["aperti"] == 0
    esito = _run(mod.segnala_f24_in_ritardo(db, oggi=OGGI))
    assert esito["aperti"] == 1
    (alert,) = _alert_aperti(db)
    assert alert["extra"]["scadenza_fonte"] == "data_scadenza del modello"


def test_oltre_la_finestra_si_conta_non_si_segnala():
    db = _Db()
    db["f24_unificato"].docs = [_modello(sezione_erario=[
        {"codice_tributo": "1001", "periodo_riferimento": "08/2019", "importo_debito": 1000.0}])]
    esito = _run(mod.segnala_f24_in_ritardo(db, oggi=OGGI))
    assert esito["aperti"] == 0 and esito["oltre_finestra"] == 1


def test_gira_nel_job_delle_8_e_non_in_un_secondo_giro(monkeypatch):
    """`invia_notifiche_scadenze` (job `f24_scadenze_check`) chiama il motore del ritardo."""
    db = _Db()
    db["f24_unificato"].docs = [_modello()]
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    chiamate = []

    async def finto(db_, oggi=None):
        chiamate.append(db_)
        return {"aperti": 1, "aggiornati": 0, "chiusi": 0, "ignorati": 0}

    monkeypatch.setattr(mod, "segnala_f24_in_ritardo", finto)
    esito = _run(mod.invia_notifiche_scadenze())
    assert chiamate == [db]
    assert esito["ritardi"]["aperti"] == 1

    from pathlib import Path
    scheduler = (Path(__file__).resolve().parents[2] / "app" / "scheduler.py").read_text(encoding="utf-8")
    assert "segnala_f24_in_ritardo" not in scheduler, "il ritardo gira dentro il job delle 08:00, non in un job suo"
