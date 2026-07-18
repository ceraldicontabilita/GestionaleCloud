"""Test del completamento degli stub verbali email (audit 18/07/2026, P1-4).

Le quattro funzioni di verbali_email_logic non sono più stub:
- cerca_quietanza_per_verbale delega a trova_pagamento_verbale (PayPal/
  PagoPA-Gmail/estratto conto) e applica il pagamento al verbale;
- cerca_pdf_per_verbale recupera il PDF dagli allegati già scaricati su
  disco (o via IMAP) e lo salva in pdf_data;
- cerca_nuovi_verbali delega allo scanner Gmail strutturato (+ IMAP);
- cerca_nuove_quietanze associa quietanze recenti ai verbali esistenti.
L'orchestratore scan_email_con_priorita (FASE 1 completa, FASE 2 aggiungi)
è agganciato allo scheduler orario.
"""
import asyncio
import base64
import pathlib
import re
from types import SimpleNamespace

import app.services.verbali_email_logic as mod
from app.services.verbali_email_logic import (
    VerbaliPendingManager,
    cerca_nuovi_verbali,
    cerca_pdf_per_verbale,
    cerca_quietanza_per_verbale,
    scan_email_con_priorita,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------- fake Motor

def _match(doc, cond):
    for k, v in (cond or {}).items():
        if k == "$or":
            if not any(_match(doc, c) for c in v):
                return False
        elif isinstance(v, dict) and ("$in" in v or "$exists" in v):
            if "$in" in v and doc.get(k) not in v["$in"]:
                return False
            if "$exists" in v and v["$exists"] != (k in doc):
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self):
        self.docs = []

    def find(self, q=None, projection=None):
        return _Cursor([d for d in self.docs if _match(d, q)])

    async def find_one(self, q, projection=None):
        for d in self.docs:
            if _match(d, q):
                return d
        return None

    async def update_one(self, q, update):
        for d in self.docs:
            if _match(d, q):
                d.update(update.get("$set", {}))
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return SimpleNamespace(inserted_id="x")


class _DB:
    def __init__(self):
        self._colls = {}

    def __getitem__(self, name):
        return self._colls.setdefault(name, _Coll())


# ------------------------------------------------------------------- FASE 1

def test_cerca_quietanza_applica_match(monkeypatch):
    db = _DB()
    db["verbali_noleggio"].docs.append(
        {"id": "v1", "numero_verbale": "A25111540620", "stato": "da_pagare"}
    )
    match = {"fonte": "paypal", "importo": 42.5}
    applicati = []

    async def fake_trova(_db, verbale):
        assert verbale["numero_verbale"] == "A25111540620"
        return match

    async def fake_applica(_db, verbale_id, m):
        applicati.append((verbale_id, m))
        return True

    monkeypatch.setattr(mod, "trova_pagamento_verbale", fake_trova)
    monkeypatch.setattr(mod, "applica_pagamento_a_verbale", fake_applica)

    res = _run(cerca_quietanza_per_verbale(db, None, "A25111540620"))
    assert res == match
    assert applicati == [("v1", match)]


def test_cerca_quietanza_salta_verbale_gia_pagato(monkeypatch):
    db = _DB()
    db["verbali_noleggio"].docs.append(
        {"numero_verbale": "A25111540620", "stato": "pagato"}
    )

    async def esplodi(*a, **k):  # non deve mai essere chiamata
        raise AssertionError("trova_pagamento_verbale chiamata su verbale pagato")

    monkeypatch.setattr(mod, "trova_pagamento_verbale", esplodi)
    assert _run(cerca_quietanza_per_verbale(db, None, "A25111540620")) is None


def test_cerca_pdf_da_allegato_locale(tmp_path):
    contenuto = b"%PDF-1.4 finto"
    pdf = tmp_path / "verbale_A25111540620.pdf"
    pdf.write_bytes(contenuto)

    db = _DB()
    db["verbali_noleggio"].docs.append({
        "numero_verbale": "A25111540620",
        "stato": "notificato",
        "allegati": [
            {"filename": "altro.txt", "path": "/non/esiste"},
            {"filename": "verbale_A25111540620.pdf", "path": str(pdf)},
        ],
    })

    res = _run(cerca_pdf_per_verbale(db, None, "A25111540620"))
    assert res == contenuto
    doc = db["verbali_noleggio"].docs[0]
    assert base64.b64decode(doc["pdf_data"]) == contenuto
    assert doc["pdf_filename"] == "verbale_A25111540620.pdf"
    assert doc["pdf_fonte"] == "allegato_gmail_scanner"


def test_cerca_pdf_non_sovrascrive_esistente():
    db = _DB()
    db["verbali_noleggio"].docs.append(
        {"numero_verbale": "A1", "pdf_data": "GIA_PRESENTE"}
    )
    assert _run(cerca_pdf_per_verbale(db, None, "A1")) is None
    assert db["verbali_noleggio"].docs[0]["pdf_data"] == "GIA_PRESENTE"


# ------------------------------------------------------------------- FASE 2

def test_cerca_nuovi_verbali_conta_scanner_gmail(monkeypatch):
    async def fake_scan(_db, days_back=7):
        return {"verbali_nuovi": 2, "verbali_aggiornati": 1}

    monkeypatch.setattr(mod, "scan_gmail_verbali", fake_scan)
    nuovi = _run(cerca_nuovi_verbali(_DB(), None, days_back=10))
    assert len(nuovi) == 2


# ------------------------------------------------------------- orchestratore

def test_scan_email_con_priorita_fasi(monkeypatch):
    db = _DB()
    db["verbali_noleggio"].docs.append({
        "id": "v1", "numero_verbale": "A25111540620", "stato": "da_pagare",
    })
    match = {"fonte": "estratto_conto", "importo": 100.0}

    async def fake_trova(_db, verbale):
        return match

    async def fake_applica(_db, verbale_id, m):
        await db["verbali_noleggio"].update_one(
            {"id": verbale_id}, {"$set": {"stato": "pagato"}}
        )
        return True

    async def fake_scan(_db, days_back=7):
        return {"verbali_nuovi": 1}

    monkeypatch.setattr(mod, "trova_pagamento_verbale", fake_trova)
    monkeypatch.setattr(mod, "applica_pagamento_a_verbale", fake_applica)
    monkeypatch.setattr(mod, "scan_gmail_verbali", fake_scan)
    monkeypatch.setattr(mod, "_crea_scanner_connesso", lambda _db: None)
    # manager pulito (istanza globale condivisa tra i test)
    monkeypatch.setattr(mod, "pending_manager", VerbaliPendingManager())

    res = _run(scan_email_con_priorita(db, days_back=30))
    f1 = res["fase_1_completamenti"]
    f2 = res["fase_2_nuovi"]
    assert f1["quietanze_cercate"] == 1
    assert f1["quietanze_trovate"] == 1
    # il verbale senza pdf_data viene cercato ma senza allegati/IMAP resta 0
    assert f1["pdf_cercati"] == 1
    assert f1["pdf_trovati"] == 0
    assert f2["verbali_nuovi"] == 1
    assert f2["quietanze_nuove"] == 0
    assert res["imap_disponibile"] is False
    assert res["errori"] == []
    assert db["verbali_noleggio"].docs[0]["stato"] == "pagato"


def test_pending_manager_ignora_verbali_senza_numero():
    db = _DB()
    db["verbali_noleggio"].docs.extend([
        {"numero_verbale": "A1", "stato": "da_pagare"},
        {"stato": "da_pagare"},  # legacy senza numero: non deve rompere
    ])
    pm = VerbaliPendingManager()
    stato = _run(pm.load_pending_from_db(db))
    assert stato["senza_quietanza"] == 1
    assert pm.verbali_senza_quietanza == ["A1"]


# ------------------------------------------------------------------- guardia

def test_niente_stub_todo_nel_modulo():
    """L'audit P1-4 segnalava 'return None' con TODO: non devono tornare."""
    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    assert "TODO: Implementare ricerca effettiva" not in src
    corpo = src.split('"""', 2)[2]  # esclude il docstring di modulo
    assert not re.search(r"# TODO", corpo)
