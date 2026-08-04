"""Bug segnalato dall'utente 14/07/2026: una nota di credito fornitore
(TD04/TD08) confermata da Prima Nota Provvisori (o dalla sincronizzazione
fatture pagate) veniva registrata come una normale fattura in USCITA,
categoria "Fatture" — invece deve essere ENTRATA (segno +), categoria
"Nota credito fornitore", stessa regola già usata da
registra_pagamento_fattura/determina_tipo_movimento_fattura."""
import asyncio
import pytest
from fastapi import HTTPException

from app.routers.prima_nota_module import sync as sync_mod
from app.routers.prima_nota_module import common as common_mod


def _matches(doc, query):
    if not query:
        return True
    if "$or" in query:
        return any(_matches(doc, q) for q in query["$or"])
    if "$nin" in str(query):
        pass
    out = True
    for k, v in query.items():
        if isinstance(v, dict) and "$nin" in v:
            out = out and (doc.get(k) not in v["$nin"])
        elif isinstance(v, dict) and "$gte" in v:
            out = out and (str(doc.get(k, "")) >= v["$gte"])
        elif isinstance(v, dict) and "$lte" in v:
            out = out and (str(doc.get(k, "")) <= v["$lte"])
        elif isinstance(v, dict) and "$regex" in v:
            out = out and str(v["$regex"]).strip("^") in str(doc.get(k, ""))
        elif isinstance(v, dict) and "$exists" in v:
            out = out and (k in doc) == v["$exists"]
        elif isinstance(v, dict) and "$in" in v:
            out = out and doc.get(k) in v["$in"]
        else:
            out = out and doc.get(k) == v
    return out


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                return dict(d)
        return None

    async def find_one_and_update(self, query, update, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                return dict(d)
        return None

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if _matches(d, query):
                d.update(update.get("$set", {}))
                for kk in update.get("$unset", {}):
                    d.pop(kk, None)
                return

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    def find(self, query=None, *a, **k):
        return _FakeCursor([d for d in self.docs if _matches(d, query or {})])


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


def _patch_db(monkeypatch, db):
    monkeypatch.setattr(sync_mod.Database, "get_db", staticmethod(lambda: db))


def _fattura(**over):
    base = {
        "id": "fatt-1", "invoice_number": "4", "invoice_date": "2026-06-05",
        "supplier_name": "RONDINELLA MARKET S.R.L.", "total_amount": 58.0,
        "tipo_documento": "TD01", "metodo_pagamento": "cassa",
    }
    base.update(over)
    return base


def test_determina_tipo_movimento_nota_credito():
    tipo, categoria, prefisso = sync_mod.determina_tipo_movimento_fattura(
        _fattura(tipo_documento="TD04")
    )
    assert tipo == "entrata"
    assert categoria == "Nota credito fornitore"
    assert prefisso == "Nota credito"


def test_determina_tipo_movimento_fattura_normale():
    tipo, categoria, prefisso = sync_mod.determina_tipo_movimento_fattura(
        _fattura(tipo_documento="TD01")
    )
    assert tipo == "uscita"
    assert categoria == "Fatture"


def test_campi_movimento_espongono_numero_e_fornitore_per_filtri():
    campi = sync_mod.costruisci_campi_movimento_fattura(_fattura(), 58.0)
    assert campi["numero_fattura"] == "4"
    assert campi["fornitore"] == "RONDINELLA MARKET S.R.L."


def test_arricchisce_movimento_storico_dalla_fattura_collegata():
    db = _FakeDb()
    db["invoices"].docs = [_fattura()]
    movimenti = [{
        "id": "mov-1", "fattura_id": "fatt-1", "data": "2026-06-05",
        "descrizione": "Pagamento fattura 4 - RONDINELLA MARKET",
    }]

    _run(common_mod.arricchisci_movimenti_fattura(db, movimenti))

    assert movimenti[0]["numero_fattura"] == "4"
    assert movimenti[0]["fornitore"] == "RONDINELLA MARKET S.R.L."
    assert movimenti[0]["data_fattura"] == "2026-06-05"


def test_determina_tipo_movimento_td26_fornitore_terzo_resta_uscita():
    """Caso 'fattura 20 - DI MASSA' (utente 19/07/2026): TD26 ("Cessione beni
    ammortizzabili") indica il TIPO di cessione, non la direzione. Un
    fornitore reale (P.IVA diversa dalla nostra) che vende un macchinario
    con questo codice resta un ACQUISTO (uscita), non un "Incasso cliente"
    (entrata) come accadeva prima — TD24-27 venivano trattati come fattura
    attiva a prescindere da chi fosse il cedente."""
    tipo, categoria, prefisso = sync_mod.determina_tipo_movimento_fattura(
        _fattura(tipo_documento="TD26", supplier_vat="07338881217")
    )
    assert tipo == "uscita"
    assert categoria == "Fatture"
    assert prefisso == "Pagamento fattura"


def test_determina_tipo_movimento_td24_cedente_noi_resta_incasso_cliente():
    """Una vera fattura attiva (emessa DA Ceraldi, cedente = P.IVA nostra)
    deve restare 'Incasso cliente' — la correzione non deve rompere le
    fatture attive genuine."""
    tipo, categoria, prefisso = sync_mod.determina_tipo_movimento_fattura(
        _fattura(tipo_documento="TD24", supplier_vat="04523831214")
    )
    assert tipo == "entrata"
    assert categoria == "Incasso cliente"
    assert prefisso == "Incasso fattura"


def test_determina_tipo_movimento_td24_cedente_noi_con_prefisso_it_resta_incasso():
    """Review Codex su PR #72: la P.IVA nostra può essere salvata con
    prefisso 'IT' o spazi a seconda del canale di import (stessa
    convenzione di suppliers_module/base.py::_varianti_piva). Un confronto
    esatto avrebbe trattato 'IT04523831214' come fornitore terzo,
    capovolgendo per errore una fattura attiva genuina."""
    tipo, categoria, _ = sync_mod.determina_tipo_movimento_fattura(
        _fattura(tipo_documento="TD24", supplier_vat="IT04523831214")
    )
    assert tipo == "entrata"
    assert categoria == "Incasso cliente"

    tipo, categoria, _ = sync_mod.determina_tipo_movimento_fattura(
        _fattura(tipo_documento="TD24", supplier_vat=" IT 04523831214 ")
    )
    assert tipo == "entrata"
    assert categoria == "Incasso cliente"


def test_determina_tipo_movimento_td26_terzo_con_prefisso_it_resta_uscita():
    """Stesso normalizzatore lato fornitore terzo: un cedente reale con
    P.IVA salvata come 'IT07338881217' deve comunque essere riconosciuto
    come terzo (non confuso con la nostra IT04523831214)."""
    tipo, categoria, _ = sync_mod.determina_tipo_movimento_fattura(
        _fattura(tipo_documento="TD26", supplier_vat="IT07338881217")
    )
    assert tipo == "uscita"
    assert categoria == "Fatture"


def test_determina_tipo_movimento_td26_senza_cedente_noto_comportamento_storico():
    """Se il cedente non è noto (dato mancante), nessuna regressione: si
    resta sul comportamento storico basato solo sul codice TD."""
    tipo, categoria, prefisso = sync_mod.determina_tipo_movimento_fattura(
        _fattura(tipo_documento="TD26", supplier_vat="")
    )
    assert tipo == "entrata"
    assert categoria == "Incasso cliente"


def test_conferma_fattura_provvisoria_nota_credito_entrata_categoria_corretta(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(tipo_documento="TD04")]
    _patch_db(monkeypatch, db)

    res = _run(sync_mod.conferma_fattura_provvisoria({"fattura_id": "fatt-1", "metodo": "cassa"}))

    assert res["success"] is True
    cassa = db["prima_nota_cassa"].docs
    assert len(cassa) == 1
    assert cassa[0]["tipo"] == "entrata"
    assert cassa[0]["categoria"] == "Nota credito fornitore"
    assert cassa[0]["importo"] == 58.0  # segno +, mai negativo
    assert "Nota credito" in cassa[0]["descrizione"]


def test_conferma_fattura_provvisoria_fattura_normale_resta_uscita(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(tipo_documento="TD01")]
    _patch_db(monkeypatch, db)

    _run(sync_mod.conferma_fattura_provvisoria({"fattura_id": "fatt-1", "metodo": "cassa"}))

    cassa = db["prima_nota_cassa"].docs
    assert cassa[0]["tipo"] == "uscita"
    assert cassa[0]["categoria"] == "Fatture"


def test_conferma_banca_senza_estratto_conto_resta_provvisoria(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(metodo_pagamento="banca")]
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc:
        _run(sync_mod.conferma_fattura_provvisoria({
            "fattura_id": "fatt-1", "metodo": "banca",
        }))

    assert exc.value.status_code == 409
    assert db["prima_nota_banca"].docs == []
    assert db["invoices"].docs[0].get("stato_pagamento") != "pagata"


def test_conferma_banca_con_riga_reale_marca_riconciliata(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(metodo_pagamento="banca")]
    db["estratto_conto_movimenti"].docs = [{
        "id": "ec-1", "data": "2026-06-10", "importo": -58.0,
        "descrizione": "BONIFICO RONDINELLA", "riconciliato": False,
    }]
    _patch_db(monkeypatch, db)

    res = _run(sync_mod.conferma_fattura_provvisoria({
        "fattura_id": "fatt-1", "metodo": "banca", "movimento_banca_id": "ec-1",
    }))

    assert res["success"] is True
    assert res["riconciliato"] is True
    banca = db["prima_nota_banca"].docs
    assert len(banca) == 1
    assert banca[0]["estratto_conto_id"] == "ec-1"
    assert banca[0]["riconciliato"] is True
    fattura = db["invoices"].docs[0]
    assert fattura["stato_finanziario"] == "pagata_e_riconciliata"
    assert fattura["estratto_conto_id"] == "ec-1"
    assert db["estratto_conto_movimenti"].docs[0]["fattura_id"] == "fatt-1"


def test_sync_fatture_pagate_nota_credito_entrata(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(
        tipo_documento="TD04", stato_pagamento="pagata",
        invoice_date="2026-06-05", metodo_pagamento="contanti",
    )]
    _patch_db(monkeypatch, db)

    res = _run(sync_mod.sync_fatture_pagate(anno=2026))

    assert res["importati_cassa"] == 1
    cassa = db["prima_nota_cassa"].docs
    assert cassa[0]["tipo"] == "entrata"
    assert cassa[0]["categoria"] == "Nota credito fornitore"
