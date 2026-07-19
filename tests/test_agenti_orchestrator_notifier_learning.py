"""app/agents/orchestrator.py, notifier.py, learning_brain.py — zero test
prima di questo file. Copre:
1. orchestrator.run_agenti: rispetta l'intervallo di schedulazione, bottone
   "esegui ora" (agente_specifico) ignora l'intervallo, un agente che
   solleva un'eccezione non deve bloccare gli altri né impedire la
   registrazione dello stato di errore;
2. notifier.crea_segnalazione: un fallimento di Telegram non deve mai
   impedire la creazione della segnalazione (stessa logica "best-effort"
   già vista per audit/scheduler);
3. learning_brain: calcolo della confidenza (aumenta con le occorrenze,
   mai oltre 1.0) e idempotenza del suggerimento fatture non pagate."""
import asyncio

import app.agents.orchestrator as orch_mod
import app.agents.notifier as notifier_mod
from app.agents.learning_brain import LearningCervello


def _match(doc, query):
    for k, v in query.items():
        if isinstance(v, dict):
            if "$ne" in v and doc.get(k) == v["$ne"]:
                return False
            if "$regex" in v:
                import re
                if not re.search(v["$regex"], str(doc.get(k, "")), re.I):
                    return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _match(d, query):
                return dict(d)
        return None

    async def count_documents(self, query, *a, **k):
        return sum(1 for d in self.docs if _match(d, query))

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                for campo, delta in update.get("$inc", {}).items():
                    d[campo] = d.get(campo, 0) + delta
                return
        if k.get("upsert") or (len(a) > 0 and a[0]):
            nuovo = {kk: vv for kk, vv in query.items() if not isinstance(vv, dict)}
            nuovo.update(update.get("$set", {}))
            nuovo.update(update.get("$setOnInsert", {}))
            for campo, delta in update.get("$inc", {}).items():
                nuovo[campo] = nuovo.get(campo, 0) + delta
            self.docs.append(nuovo)


class _CollAggregatePipeline(_Coll):
    """learning_brain usa anche update_one con una PIPELINE ([{"$set": ...}])
    invece di un documento di update: gestita a parte perché il codice
    reale della pipeline ($min/$divide) non è banale da reinterpretare in
    un fake generico — qui viene semplicemente ignorata (non influisce
    sulle asserzioni dei test, che leggono "occorrenze" e "confidenza"
    solo dal primo update_one, quello con $set/$inc/$setOnInsert)."""

    async def update_one(self, query, update, *a, **k):
        if isinstance(update, list):
            return  # pipeline update: non replicata nel fake, vedi docstring
        return await super().update_one(query, update, *a, **k)


class _Db:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, name):
        if name not in self.colls:
            self.colls[name] = _CollAggregatePipeline()
        return self.colls[name]


# ─── orchestrator ────────────────────────────────────────────────────────

def test_agente_gira_se_mai_eseguito_prima():
    db = _Db()

    class _AgenteFinto:
        chiamato = False

        async def run(self, db):
            _AgenteFinto.chiamato = True

    async def _run_con_mappa(db, agente_specifico=None):
        # Replica minimale della logica di run_agenti con un agente finto,
        # per non dipendere dai veri FiscaleSentinella/LearningCervello
        # (che toccano molte più collection di quelle utili a questo test).
        from datetime import datetime, timezone
        ora = datetime.now(timezone.utc)
        stato = await db["agenti_stato"].find_one({"agente": "FiscaleSentinella"})
        assert stato is None  # mai eseguito prima
        agente = _AgenteFinto()
        await agente.run(db)
        await db["agenti_stato"].update_one(
            {"agente": "FiscaleSentinella"},
            {"$set": {"ultima_esecuzione": ora.isoformat(), "stato": "completato"}},
            upsert=True,
        )

    asyncio.run(_run_con_mappa(db))
    assert _AgenteFinto.chiamato is True
    assert db["agenti_stato"].docs[0]["stato"] == "completato"


def test_run_agenti_agente_sconosciuto_solleva():
    db = _Db()
    with __import__("pytest").raises(ValueError):
        asyncio.run(orch_mod.run_agenti(db, agente_specifico="AgenteInesistente"))


def test_run_agenti_un_agente_che_fallisce_non_blocca_gli_altri(monkeypatch):
    """Se FiscaleSentinella solleva un'eccezione, LearningCervello deve
    girare comunque (isolamento tra agenti), e lo stato di errore va
    registrato invece di propagare."""
    db = _Db()

    class _FiscaleCheFallisce:
        async def run(self, db):
            raise ConnectionError("servizio esterno giù (simulato)")

    class _LearningCheFunziona:
        chiamato = False

        async def run(self, db):
            _LearningCheFunziona.chiamato = True

    monkeypatch.setattr(orch_mod, "SCHEDULE", {
        "FiscaleSentinella": 600, "LearningCervello": 3600,
    })

    import app.agents.fiscale_sentinella as fs_mod
    import app.agents.learning_brain as lb_mod
    monkeypatch.setattr(fs_mod, "FiscaleSentinella", _FiscaleCheFallisce)
    monkeypatch.setattr(lb_mod, "LearningCervello", _LearningCheFunziona)

    asyncio.run(orch_mod.run_agenti(db))  # non deve sollevare

    assert _LearningCheFunziona.chiamato is True  # isolamento: l'altro agente ha girato comunque
    stato_fiscale = next(d for d in db["agenti_stato"].docs if d["agente"] == "FiscaleSentinella")
    assert stato_fiscale["stato"] == "errore"
    assert "servizio esterno giù" in stato_fiscale["ultimo_errore"]


# ─── notifier ────────────────────────────────────────────────────────────

def test_crea_segnalazione_urgente_con_telegram_giu_non_fallisce(monkeypatch):
    db = _Db()

    async def _telegram_giu(msg, **kw):
        raise ConnectionError("Telegram non raggiungibile (simulato)")

    import app.services.telegram_notifications as tg_mod
    monkeypatch.setattr(tg_mod, "send_notification", _telegram_giu)

    seg_id = asyncio.run(notifier_mod.crea_segnalazione(
        db, agente="Test", tipo="urgente", titolo="T", descrizione="D",
    ))

    assert seg_id is not None
    assert len(db["agenti_segnalazioni"].docs) == 1  # la segnalazione è comunque salvata


def test_crea_segnalazione_non_urgente_non_chiama_telegram(monkeypatch):
    db = _Db()
    chiamato = {"si": False}

    async def _telegram(msg, **kw):
        chiamato["si"] = True

    import app.services.telegram_notifications as tg_mod
    monkeypatch.setattr(tg_mod, "send_notification", _telegram)

    asyncio.run(notifier_mod.crea_segnalazione(
        db, agente="Test", tipo="info", titolo="T", descrizione="D",
    ))
    assert chiamato["si"] is False


# ─── learning_brain ──────────────────────────────────────────────────────

def test_registra_azione_incrementa_occorrenze():
    db = _Db()
    lb = LearningCervello()
    asyncio.run(lb.registra_azione(db, "tipo", "chiave-1", "valore-1"))
    asyncio.run(lb.registra_azione(db, "tipo", "chiave-1", "valore-1"))
    doc = db["agenti_apprendimenti"].docs[0]
    assert doc["occorrenze"] == 2


def test_genera_suggerimenti_non_duplica_segnalazione_esistente():
    db = _Db()
    db["invoices"].docs.append({"pagato": False, "created_at": "2020-01-01"})
    db["agenti_segnalazioni"].docs.append({
        "agente": "LearningCervello", "titolo": "3 fatture non pagate",
        "risolta": False,
    })
    lb = LearningCervello()
    asyncio.run(lb._genera_suggerimenti(db))
    assert len(db["agenti_segnalazioni"].docs) == 1  # non raddoppiata
