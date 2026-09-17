"""Bug segnalato dall'utente 15/07/2026: la card "IVA da versare" nella
pagina Scadenze sommava semplicemente il campo "iva" di TUTTE le fatture
ricevute/emesse nel mese, senza applicare le regole di
memoria/SPECIFICA_IVA.md (§10-11): niente esclusione delle fatture già
utilizzate in una liquidazione precedente, delle note di credito, dei
documenti annullati/duplicati, né attribuzione per periodo IVA di
competenza (regola del giorno 15). Poteva mostrare un "IVA da versare"
diverso da quello confermato nella pagina Gestione IVA — due formule
diverse sulle stesse fatture.

_iva_acquisti_ufficiale ora riusa lo stesso motore
(liquidazione_iva_engine.seleziona_fatture_per_liquidazione) usato da
POST /api/iva/liquidazioni/calcola, con precedenza alla liquidazione già
CONFERMATA quando esiste."""
import asyncio

from app.routers import scadenze as mod


def _matches(doc, query):
    for k, v in query.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, query=None, projection=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])

    async def find_one(self, query, *a, sort=None, **k):
        candidati = [d for d in self.docs if _matches(d, query)]
        if not candidati:
            return None
        if sort:
            campo, direzione = sort[0]
            candidati.sort(key=lambda d: d.get(campo, 0), reverse=(direzione == -1))
        return dict(candidati[0])

    def aggregate(self, pipeline, *a, **k):
        match = pipeline[0].get("$match", {}) if pipeline else {}
        matched = [d for d in self.docs if _matches_aggregate(d, match)]
        totale = sum(d.get("totale_iva", 0) for d in matched)
        return _FakeCursor([{"_id": None, "totale": totale}] if matched else [])


def _matches_aggregate(doc, match):
    for k, v in match.items():
        if k == "data" and isinstance(v, dict) and "$regex" in v:
            if not str(doc.get("data", "")).startswith(v["$regex"].lstrip("^")):
                return False
        elif doc.get(k) != v:
            return False
    return True


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeDb:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def test_esclude_fattura_gia_utilizzata_in_liquidazione_precedente():
    db = _FakeDb()
    db["invoices"].docs = [
        # Attribuita a gennaio ma già inclusa/confermata nella liquidazione
        # di gennaio: il vecchio codice la avrebbe comunque sommata di
        # nuovo a febbraio se la data di ricezione era a febbraio.
        {"id": "f1", "periodo_iva_attribuito": "2026-01", "iva_detraibile": 220.0,
         "iva_utilizzata": True, "periodo_iva_utilizzato": "2026-01",
         "stato_detrazione_iva": "INSERITA_IN_LIQUIDAZIONE"},
        # Genuinamente disponibile per gennaio.
        {"id": "f2", "periodo_iva_attribuito": "2026-01", "iva_detraibile": 100.0,
         "iva_utilizzata": False, "stato_detrazione_iva": "DA_INSERIRE"},
        # Nota di credito: mai un acquisto detraibile in positivo.
        {"id": "f3", "periodo_iva_attribuito": "2026-01", "iva_detraibile": 50.0,
         "iva_utilizzata": False, "stato_detrazione_iva": "DA_INSERIRE",
         "tipo_documento": "TD04"},
    ]

    esito = _run(mod._iva_acquisti_ufficiale(db, "2026-01"))

    assert esito["iva_acquisti"] == 100.0  # solo f2
    assert esito["fonte"] == "stima"


def test_usa_liquidazione_confermata_quando_esiste():
    db = _FakeDb()
    db["invoices"].docs = [
        {"id": "f1", "periodo_iva_attribuito": "2026-02", "iva_detraibile": 999.0,
         "iva_utilizzata": False, "stato_detrazione_iva": "DA_INSERIRE"},
    ]
    db["liquidazioni_iva"].docs = [
        {"id": "liq1", "periodo": "2026-02", "stato": "CONFERMATA",
         "versione": 1, "iva_acquisti": 350.0},
    ]

    esito = _run(mod._iva_acquisti_ufficiale(db, "2026-02"))

    # Il valore confermato vince, non il ricalcolo dalle fatture (che darebbe 999).
    assert esito["iva_acquisti"] == 350.0
    assert esito["fonte"] == "liquidazione_confermata"


def test_get_scadenze_iva_mensile_marca_fonte_stima(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    db["corrispettivi"].docs = [
        {"data": "2026-03-10", "totale_iva": 500.0},
    ]
    db["invoices"].docs = [
        {"id": "f1", "periodo_iva_attribuito": "2026-03", "iva_detraibile": 120.0,
         "iva_utilizzata": False, "stato_detrazione_iva": "DA_INSERIRE"},
    ]

    esito = _run(mod.get_scadenze_iva_mensile(2026))

    marzo = next(s for s in esito["scadenze"] if s["mese"] == 3)
    assert marzo["iva_credito"] == 120.0
    assert marzo["fonte"] == "stima"
