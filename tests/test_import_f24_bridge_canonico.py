"""Bug trovato nell'audit funzionale del 15/07/2026: POST /import-f24 (usato
dal workflow "F24_COMPLETO" della pagina Import Documenti quando un PDF
viene classificato come F24) salvava SOLO nella collezione f24_pagamenti
(sottosistema parser paghe, volutamente separato — vedi f24_canonico.py).
Un F24 caricato da lì non compariva MAI nella lista F24 (f24_main.py,
legge solo f24_unificato) né nel conteggio "F24 da pagare" di Scadenze
(scadenze.py::conta_f24_da_pagare, stessa collezione).

Il fix aggiunge un bridge additivo verso f24_unificato via
f24_canonico.salva_f24(), senza toccare il flusso f24_pagamenti esistente
(tributi/distinte/riconciliazione bancaria restano identici)."""
import asyncio
import io

from app.routers import f24_parser as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _matches(doc, query):
    for k, v in query.items():
        if isinstance(v, dict) and "$or" in v:
            continue
        if doc.get(k) != v:
            return False
    return True


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, upsert=False, **k):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                return type("R", (), {"matched_count": 1})()
        if upsert:
            new_doc = dict(query)
            new_doc.update(update.get("$set", {}))
            self.docs.append(new_doc)
        return type("R", (), {"matched_count": 0})()

    async def update_many(self, query, update, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))


class _AttrDb:
    """Simula sia db["collection"] sia db.collection (usati entrambi nel file)."""
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())

    def __getattr__(self, name):
        return self[name]


class _FakeUploadFile:
    def __init__(self, filename, content):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


_PARSED_ESEMPIO = {
    "tipo_documento": "F24",
    "contribuente": {"codice_fiscale": "04523831214", "ragione_sociale": "CERALDI GROUP S.R.L."},
    "domicilio_fiscale": {},
    "scadenza": "16/08/2026",
    "sezione_erario": {"righe": [{"codice_tributo": "6001", "importo_debito": 100.0}], "totale_debito": 100.0, "totale_credito": 0.0, "saldo": 100.0},
    "sezione_inps": {"righe": [], "totale": 0.0},
    "sezione_regioni": {"righe": [], "totale_debito": 0.0, "totale_credito": 0.0},
    "sezione_imu": {"righe": [], "totale": 0.0},
    "sezione_inail": {"righe": [], "totale": 0.0},
    "totale_da_pagare": 100.0,
    "pagamento": {},
}


def test_import_f24_crea_anche_il_bridge_in_f24_unificato(monkeypatch):
    db = _AttrDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(mod, "parse_f24_pdf", lambda path: dict(_PARSED_ESEMPIO))

    upload = _FakeUploadFile("modello_f24.pdf", b"%PDF-1.4 finto contenuto")
    esito = _run(mod.import_f24(file=upload, aggiorna_esistente=True))

    assert esito["success"] is True
    # Il flusso storico esiste ancora, invariato.
    assert len(db["f24_pagamenti"].docs) == 1

    # Il bug: prima questo restava sempre vuoto.
    bridge_docs = db["f24_unificato"].docs
    assert len(bridge_docs) == 1
    assert bridge_docs[0]["codice_fiscale"] == "04523831214"
    assert bridge_docs[0]["importo_totale"] == 100.0
    assert bridge_docs[0]["status"] == "da_pagare"
    assert bridge_docs[0]["pagato"] is False


def test_import_f24_bridge_non_duplica_su_reimport_stesso_pdf(monkeypatch):
    db = _AttrDb()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(mod, "parse_f24_pdf", lambda path: dict(_PARSED_ESEMPIO))

    upload1 = _FakeUploadFile("modello_f24.pdf", b"%PDF-1.4 stesso contenuto")
    upload2 = _FakeUploadFile("modello_f24.pdf", b"%PDF-1.4 stesso contenuto")
    _run(mod.import_f24(file=upload1, aggiorna_esistente=True))
    _run(mod.import_f24(file=upload2, aggiorna_esistente=True))

    assert len(db["f24_unificato"].docs) == 1
