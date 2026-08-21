"""P0.10 — Lo stato del job batch_reprocessing è persistito su Drive/Sheets
(collezione job_state), quindi sopravvive a restart/multi-worker invece di
vivere in una variabile globale di processo."""
import asyncio
from pathlib import Path

import app.routers.batch_reprocessing as br


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, query, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                return {k: v for k, v in d.items() if k != "_id"}
        return None

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in query.items()):
                d.update(update.get("$set", {}))
                return
        if upsert:
            nd = {}
            nd.update(query)
            nd.update(update.get("$setOnInsert", {}))
            nd.update(update.get("$set", {}))
            self.docs.append(nd)


class _Db:
    def __init__(self):
        self.coll = _Coll()

    def __getitem__(self, name):
        assert name == "job_state"
        return self.coll


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_stato_persistito_e_riletto():
    db = _Db()
    # stato iniziale = default (nessun doc)
    st0 = _run(br._get_state(db))
    assert st0["running"] is False
    # scrivo running=True
    _run(br._set_state(db, {"running": True, "progress": "In corso..."}))
    st1 = _run(br._get_state(db))
    assert st1["running"] is True
    assert st1["progress"] == "In corso..."
    assert st1["updated_at"] is not None
    # un secondo "worker" (nuovo _Db sullo stesso storage) vedrebbe lo stato:
    # qui simulato rileggendo dalla stessa collezione
    assert st1["job_id"] == br.JOB_KEY


def test_niente_variabile_globale_di_stato():
    src = Path("app/routers/batch_reprocessing.py").read_text(encoding="utf-8")
    assert "global _job_state" not in src
    assert "job_state" in src  # collezione persistente


def test_job_stallato_sblocca_dopo_soglia():
    """Un job running con heartbeat vecchio è considerato stale e non blocca."""
    from datetime import datetime, timezone, timedelta
    import app.routers.batch_reprocessing as br2
    # running recente -> NON stallato
    recente = {"running": True, "updated_at": datetime.now(timezone.utc).isoformat()}
    assert br2._job_stallato(recente) is False
    # running vecchio oltre soglia -> stallato
    vecchio = {"running": True, "updated_at": (datetime.now(timezone.utc) - timedelta(minutes=br2.STALE_DOPO_MIN + 5)).isoformat()}
    assert br2._job_stallato(vecchio) is True
    # non running -> mai stallato
    assert br2._job_stallato({"running": False}) is False
    # running senza heartbeat -> stallato (prudenza)
    assert br2._job_stallato({"running": True, "updated_at": None}) is True
