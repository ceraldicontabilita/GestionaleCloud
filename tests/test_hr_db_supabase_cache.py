"""17/09/2026: cache in memoria dell'adattatore HR Mongo→Postgres.

pg_stat_statements dal 01/09 contava 218.000 letture complete di
app_paghe_mensili e letture da 8 s l'una di app_bonifici (PDF de-toastati per
poi buttarli): ogni find/find_one/count/update rileggeva l'intera tabella.
Qui si prova, con un pool Postgres finto che interpreta le poche forme SQL
dell'adattatore, che dopo la prima lettura la tabella resta in memoria finche'
la sua firma (righe + xmin massimo) non cambia; che una modifica esterna viene
vista; che le scritture del processo aggiornano la copia senza rileggere; che
i PDF arrivano per id solo quando servono e non vengono persi da un update;
che un filtro sul PDF e una firma non disponibile tornano al SQL diretto.
"""
import asyncio
import json
import re

import pytest

from app.hr import db_supabase as hr


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Ctx:
    def __init__(self, pool):
        self.pool = pool

    async def __aenter__(self):
        return _Con(self.pool)

    async def __aexit__(self, *exc):
        return False


class _Con:
    def __init__(self, pool):
        self.pool = pool

    async def fetch(self, sql, *args):
        return self.pool.esegui(sql, args)

    async def execute(self, sql, *args):
        self.pool.esegui(sql, args)
        return "OK"


_TAB = re.compile(r'"hr"\."(app_[a-z0-9_]+)"')


class PoolFinto:
    """Tabelle id → doc, con un contatore di transazione al posto di xmin."""

    def __init__(self, tabelle=None):
        self.tabelle = {}
        self.xmin = {}
        self.tx = 0
        self.log = []
        self.firma_guasta = False
        for tab, docs in (tabelle or {}).items():
            for doc in docs:
                self.scrivi_esterno(tab, doc)

    def scrivi_esterno(self, tab, doc):
        """Scrittura fatta da un altro processo (deposito cedolini, SQL a mano)."""
        self.tx += 1
        self.tabelle.setdefault(tab, {})[str(doc["id"])] = dict(doc)
        self.xmin.setdefault(tab, {})[str(doc["id"])] = self.tx

    def cancella_esterno(self, tab, chiave):
        self.tx += 1
        self.tabelle.get(tab, {}).pop(chiave, None)
        self.xmin.get(tab, {}).pop(chiave, None)

    def acquire(self):
        return _Ctx(self)

    def letture_complete(self):
        return [s for s in self.log if s.startswith("SELECT doc") or s.startswith("SELECT id, (doc")]

    def esegui(self, sql, args):
        self.log.append(sql)
        if sql.startswith("CREATE TABLE") or sql.startswith("ALTER TABLE"):
            return []
        if sql.startswith("SELECT '") and " AS t, count(*)" in sql:
            if self.firma_guasta:
                raise RuntimeError("canceling statement due to statement timeout")
            righe = []
            for tab in _TAB.findall(sql):
                righe.append({
                    "t": tab,
                    "n": len(self.tabelle.get(tab, {})),
                    "x": max(self.xmin.get(tab, {}).values(), default=0),
                })
            return righe
        tab = _TAB.search(sql).group(1)
        righe_tab = self.tabelle.setdefault(tab, {})
        if sql.startswith("SELECT id, (doc - ARRAY["):
            campi = re.findall(r"'([a-z_]+)'", sql.split("FROM")[0])
            pesanti = [c for c in campi if c in hr._CAMPI_PESANTI]
            out = []
            for chiave, doc in righe_tab.items():
                riga = {"id": chiave, "doc": json.dumps({k: v for k, v in doc.items() if k not in pesanti})}
                for i, c in enumerate(hr._CAMPI_PESANTI):
                    riga["p%d" % i] = c in doc
                out.append(riga)
            return out
        if sql.startswith("SELECT id, doc -> "):
            colonne = re.findall(r"doc -> '([a-z_]+)' AS c(\d+)", sql)
            out = []
            for chiave in args[0]:
                doc = righe_tab.get(chiave)
                if doc is None:
                    continue
                riga = {"id": chiave}
                for campo, idx in colonne:
                    riga["c" + idx] = json.dumps(doc[campo]) if campo in doc else None
                out.append(riga)
            return out
        if sql.startswith("SELECT doc - ARRAY["):
            campi = re.findall(r"'([a-z_]+)'", sql.split("FROM")[0])
            return [{"doc": json.dumps({k: v for k, v in d.items() if k not in campi})}
                    for d in righe_tab.values()]
        if sql.startswith("SELECT doc FROM"):
            return [{"doc": json.dumps(d)} for d in righe_tab.values()]
        if sql.startswith("INSERT INTO"):
            chiave, doc = args[0], json.loads(args[1])
            if chiave in righe_tab and "ON CONFLICT" not in sql:
                raise RuntimeError("duplicate key")
            self.tx += 1
            righe_tab[chiave] = doc
            self.xmin.setdefault(tab, {})[chiave] = self.tx
            return []
        if sql.startswith("UPDATE"):
            chiave, doc = args[0], json.loads(args[1])
            self.tx += 1
            righe_tab[chiave] = doc
            self.xmin.setdefault(tab, {})[chiave] = self.tx
            return []
        if sql.startswith("DELETE FROM") and "ANY(" in sql:
            for chiave in args[0]:
                self.tx += 1
                righe_tab.pop(chiave, None)
                self.xmin.get(tab, {}).pop(chiave, None)
            return []
        if sql.startswith("DELETE FROM"):
            self.tx += 1
            righe_tab.pop(args[0], None)
            self.xmin.get(tab, {}).pop(args[0], None)
            return []
        raise AssertionError("SQL non previsto dal pool finto: " + sql)


def _db(pool):
    return hr.SupabaseDatabase(pool, schema="hr")


def _pool():
    return PoolFinto({
        "app_cedolini": [
            {"id": "c1", "anno": 2026, "mese": 7, "netto": 1500.0, "pdf_data": "JVBERi0x"},
            {"id": "c2", "anno": 2026, "mese": 8, "netto": 1600.0},
            {"id": "c3", "anno": 2025, "mese": 12, "netto": 1400.0, "pdf_data": "JVBERi0y"},
        ],
        "app_dipendenti": [
            {"id": "d1", "nome": "Anna", "attivo": True},
            {"id": "d2", "nome": "Bruno", "attivo": False},
        ],
    })


def test_seconda_lettura_non_rilegge_la_tabella():
    pool = _pool()
    db = _db(pool)

    async def scenario():
        prima = await db["cedolini"].find({"anno": 2026}, {"_id": 0, "pdf_data": 0}).to_list(None)
        seconda = await db["cedolini"].find_one({"id": "c2"}, {"_id": 0, "pdf_data": 0})
        conteggio = await db["cedolini"].count_documents({"anno": 2026})
        mesi = await db["cedolini"].distinct("mese", {"anno": 2026})
        return prima, seconda, conteggio, mesi

    prima, seconda, conteggio, mesi = _run(scenario())
    assert [d["id"] for d in prima] == ["c1", "c2"] and all("pdf_data" not in d for d in prima)
    assert seconda["netto"] == 1600.0 and conteggio == 2 and sorted(mesi) == [7, 8]
    # una sola lettura leggera della tabella, una sola firma
    assert len(pool.letture_complete()) == 1
    assert sum(1 for s in pool.log if " AS t, count(*)" in s) == 1


def test_modifica_esterna_viene_vista_dopo_il_ttl(monkeypatch):
    monkeypatch.setattr(hr, "_FIRMA_TTL", 0.0)
    pool = _pool()
    db = _db(pool)

    async def scenario():
        await db["cedolini"].find({}, {"pdf_data": 0}).to_list(None)
        pool.scrivi_esterno("app_cedolini", {"id": "c4", "anno": 2026, "mese": 9, "netto": 1700.0})
        pool.cancella_esterno("app_cedolini", "c3")
        dopo = await db["cedolini"].find({}, {"pdf_data": 0}).to_list(None)
        return sorted(d["id"] for d in dopo)

    assert _run(scenario()) == ["c1", "c2", "c4"]
    assert len(pool.letture_complete()) == 2


def test_scritture_del_processo_aggiornano_la_copia_senza_rileggere(monkeypatch):
    monkeypatch.setattr(hr, "_FIRMA_TTL", 0.0)
    pool = _pool()
    db = _db(pool)

    async def scenario():
        await db["dipendenti"].find({}).to_list(None)
        await db["dipendenti"].insert_one({"id": "d3", "nome": "Carla", "attivo": True})
        await db["dipendenti"].update_one({"id": "d2"}, {"$set": {"attivo": True}})
        await db["dipendenti"].update_many({"attivo": True}, {"$set": {"turno": "mattina"}})
        await db["dipendenti"].delete_one({"id": "d1"})
        attivi = await db["dipendenti"].find({"attivo": True}).to_list(None)
        return attivi

    attivi = _run(scenario())
    assert sorted(d["id"] for d in attivi) == ["d2", "d3"]
    assert all(d.get("turno") == "mattina" for d in attivi)
    # la tabella e' stata letta una volta sola: le scritture hanno aggiornato la copia
    assert len(pool.letture_complete()) == 1
    assert pool.tabelle["app_dipendenti"]["d2"]["turno"] == "mattina"
    assert "d1" not in pool.tabelle["app_dipendenti"]


def test_pdf_letto_per_id_solo_quando_serve_e_mai_perso_da_un_update():
    pool = _pool()
    db = _db(pool)

    async def scenario():
        leggeri = await db["cedolini"].find({}, {"_id": 0, "pdf_data": 0}).to_list(None)
        pool.log.clear()
        pieno = await db["cedolini"].find_one({"id": "c1"})
        idratazioni_uno = [s for s in pool.log if s.startswith("SELECT id, doc -> ")]
        pool.log.clear()
        senza = await db["cedolini"].find_one({"id": "c2"})
        idratazioni_senza = [s for s in pool.log if s.startswith("SELECT id, doc -> ")]
        await db["cedolini"].update_one({"id": "c1"}, {"$set": {"netto": 1550.0}})
        await db["cedolini"].update_one({"id": "c3"}, {"$unset": {"pdf_data": ""}})
        return leggeri, pieno, idratazioni_uno, senza, idratazioni_senza

    leggeri, pieno, idratazioni_uno, senza, idratazioni_senza = _run(scenario())
    assert all("pdf_data" not in d for d in leggeri)
    assert pieno["pdf_data"] == "JVBERi0x" and len(idratazioni_uno) == 1
    assert "pdf_data" not in senza and idratazioni_senza == []
    # il documento riscritto per intero conserva il PDF
    assert pool.tabelle["app_cedolini"]["c1"] == {
        "id": "c1", "anno": 2026, "mese": 7, "netto": 1550.0, "pdf_data": "JVBERi0x"}
    assert "pdf_data" not in pool.tabelle["app_cedolini"]["c3"]
    assert pool.letture_complete() == pool.letture_complete()[:1]


def test_filtro_sul_pdf_legge_direttamente_le_righe_intere():
    pool = _pool()
    db = _db(pool)

    async def scenario():
        await db["cedolini"].find({}, {"pdf_data": 0}).to_list(None)
        pool.log.clear()
        return await db["cedolini"].count_documents({"pdf_data": {"$exists": True}})

    assert _run(scenario()) == 2
    # riga intera dal SQL (il PDF citato dal filtro non viene escluso)
    assert any(s.startswith("SELECT doc - ARRAY['file_data']") or s.startswith("SELECT doc FROM") for s in pool.log)


def test_firma_non_disponibile_torna_al_sql_diretto_oltre_la_grazia(monkeypatch):
    monkeypatch.setattr(hr, "_FIRMA_TTL", 0.0)
    pool = _pool()
    db = _db(pool)

    async def scenario():
        await db["dipendenti"].find({}).to_list(None)
        pool.firma_guasta = True
        pool.scrivi_esterno("app_dipendenti", {"id": "d9", "nome": "Dario", "attivo": True})
        dentro = await db["dipendenti"].find({}).to_list(None)
        monkeypatch.setattr(hr, "_FIRMA_GRAZIA", 0.0)
        fuori = await db["dipendenti"].find({}).to_list(None)
        return sorted(d["id"] for d in dentro), sorted(d["id"] for d in fuori)

    dentro, fuori = _run(scenario())
    # entro la grazia la copia (senza d9) resta in uso; oltre, lettura diretta esatta
    assert dentro == ["d1", "d2"] and fuori == ["d1", "d2", "d9"]
    assert any(s.startswith("SELECT doc FROM") for s in pool.log)


def test_cache_spenta_da_env(monkeypatch):
    monkeypatch.setenv("HR_RUNTIME_CACHE", "0")
    pool = _pool()
    db = _db(pool)

    async def scenario():
        await db["dipendenti"].find({}).to_list(None)
        await db["dipendenti"].find({}).to_list(None)

    _run(scenario())
    assert len([s for s in pool.log if s.startswith("SELECT doc FROM")]) == 2
    assert not any(" AS t, count(*)" in s for s in pool.log)


@pytest.mark.parametrize("tab", ["app_cedolini", "app_dipendenti"])
def test_sql_firma_usa_solo_nomi_validati(tab):
    db = _db(PoolFinto())
    sql = db._sql_firma([tab])
    assert sql.startswith("SELECT '%s' AS t, count(*)::bigint AS n" % tab)
    assert 'FROM "hr"."%s"' % tab in sql
