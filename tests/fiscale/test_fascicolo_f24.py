"""Test della materializzazione del fascicolo F24 (§21): costruzione da F24 +
quietanze + cedolini e persistenza per chiave. Usa un piccolo fake DB async che
supporta $or, chiavi puntate e update_one(upsert)."""
import asyncio

from app.services import fascicolo_f24 as fasc


# ─── mini fake DB async ──────────────────────────────────────────────────────
def _get(doc, dotted):
    cur = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _match(doc, query):
    for k, cond in query.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        val = _get(doc, k)
        if isinstance(cond, dict):
            for op, arg in cond.items():
                if op == "$ne" and val == arg:
                    return False
        elif val != cond:
            return False
    return True


class _Cur:
    def __init__(self, items):
        self._items = items

    async def to_list(self, n):
        return [dict(x) for x in self._items[:n]]


class _Coll:
    def __init__(self):
        self.docs = []

    def find(self, query, proj=None):
        return _Cur([dict(d) for d in self.docs if _match(d, query)])

    async def find_one(self, query, proj=None):
        for d in self.docs:
            if _match(d, query):
                return dict(d)
        return None

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                return
        if upsert:
            self.docs.append(dict(update.get("$set", {})))


class _Db:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, name):
        return self.colls.setdefault(name, _Coll())


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _f24(id_, cf, mese, anno, righe_inps=None, righe_erario=None):
    return {
        "id": id_, "status": "attivo",
        "dati_generali": {"codice_fiscale": cf},
        "sezione_inps": righe_inps or [],
        "sezione_erario": righe_erario or [],
    }


def test_costruisci_e_salva_fascicolo():
    db = _Db()
    cf = "12345678901"
    periodo_txt = "06/2026"
    # F24 ordinario DM10 (capitale INPS) + F24 RC01 (regolarizzazione)
    db["f24_unificato"].docs = [
        _f24("ord1", cf, 6, 2026,
             righe_inps=[{"causale": "DM10", "matricola": "M1", "codice_sede": "7300",
                          "importo_debito": 1000, "periodo_riferimento": "06/2026"}]),
        _f24("rc1", cf, 6, 2026,
             righe_inps=[{"causale": "RC01", "matricola": "M1", "codice_sede": "7300",
                          "importo_debito": 1000, "periodo_riferimento": "06/2026"},
                         {"causale": "8918", "matricola": "M1",
                          "importo_debito": 50, "periodo_riferimento": "06/2026"}]),
        # F24 di altro periodo: non deve entrare
        _f24("altro", cf, 5, 2026,
             righe_inps=[{"causale": "DM10", "importo_debito": 999,
                          "periodo_riferimento": "05/2026"}]),
    ]
    db["quietanze_f24"].docs = [{"id": "q1", "codice_fiscale": cf}]
    db["cedolini"].docs = [{"id": "ced1", "anno": 2026, "mese": 6, "matricola": "M1"}]

    fascicolo = _run(fasc.costruisci_e_salva(db, cf, (6, 2026)))

    # Solo gli F24 del periodo 06/2026
    assert set(fascicolo["f24_ids"]) == {"ord1", "rc1"}
    assert fascicolo["f24_ordinari_ids"] == ["ord1"]
    assert fascicolo["f24_rc01_ids"] == ["rc1"]
    # Relazione DM10↔RC01 rilevata
    assert len(fascicolo["relazioni_dm10_rc01"]) == 1
    rel = fascicolo["relazioni_dm10_rc01"][0]
    assert rel["f24_ordinario_id"] == "ord1" and rel["f24_rc01_id"] == "rc1"
    # Quietanza e cedolino collegati
    assert fascicolo["quietanza_ids"] == ["q1"]
    assert fascicolo["cedolino_ids"] == ["ced1"]
    # Totali classificati: 8918 è sanzione/interesse
    assert fascicolo["totali"]["sanzioni_interessi"] == 50
    # Persistito e rileggibile per chiave
    letto = _run(fasc.leggi_fascicolo(db, cf, (6, 2026)))
    assert letto is not None and letto["chiave"] == fascicolo["chiave"]


def test_parse_periodo_mm_aaaa_valido_e_invalido():
    from app.routers.f24.f24_main import _parse_periodo_mm_aaaa
    from fastapi import HTTPException
    assert _parse_periodo_mm_aaaa("06/2026") == (6, 2026)
    assert _parse_periodo_mm_aaaa("6-2026") == (6, 2026)
    for bad in ("2026-06", "13/2026", "", "abc"):
        try:
            _parse_periodo_mm_aaaa(bad)
            assert False, f"atteso 400 per {bad!r}"
        except HTTPException as e:
            assert e.status_code == 400
