"""Instradamento Prima Nota all'import per metodo del fornitore (§29, §39).

Decisione del titolare 07/10/2026: cassa -> movimento Cassa subito (data
fattura, pagata); banca -> attesa dell'estratto conto; assegno collegato ->
pagamento dichiarato in attesa di riscontro bancario; misto/mancante -> sospesa.
"""
import asyncio

import pytest

from app.routers.invoices import fatture_upload as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _match(doc, query):
    for k, v in query.items():
        if k == "$and":
            if not all(_match(doc, sub) for sub in v):
                return False
        elif k == "$or":
            if not any(_match(doc, sub) for sub in v):
                return False
        elif isinstance(v, dict):
            if "$exists" in v and (k in doc) != v["$exists"]:
                return False
            if "$ne" in v and doc.get(k) == v["$ne"]:
                return False
            if "$in" in v and doc.get(k) not in v["$in"]:
                return False
            if "$nin" in v and doc.get(k) in v["$nin"]:
                return False
            if "$gte" in v and doc.get(k) < v["$gte"]:
                return False
            if "$lte" in v and doc.get(k) > v["$lte"]:
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

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, *a, **k):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                return

    def find(self, query, *a, **k):
        return _Cursor([dict(d) for d in self.docs if _match(d, query)])


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n):
        return self.docs[:n]


class _Db:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _Coll())


FATTURA = {
    "id": "fatt-1", "invoice_number": "77/A", "invoice_date": "2026-06-01",
    "supplier_vat": "01234567890", "supplier_name": "Dolciaria Acquaviva S.p.A.",
    "total_amount": 122.0, "imponibile": 100.0, "iva": 22.0,
}


def _setup(monkeypatch, metodo, **supplier_extra):
    db = _Db()
    if metodo is not None:
        db["fornitori"].docs = [{
            "partita_iva": "01234567890",
            "metodo_pagamento": metodo,
            **supplier_extra,
        }]
    db["invoices"].docs = [dict(FATTURA)]
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    # registra_pagamento_fattura usa Database.get_db() suo: monkeypatcho il modulo sync
    from app.routers.prima_nota_module import sync as mod_sync
    monkeypatch.setattr(mod_sync.Database, "get_db", staticmethod(lambda: db))
    return db


@pytest.fixture
def eventi(monkeypatch):
    registrati = []

    async def finto_propagate(event_type, payload, _db, source_module="", **_k):
        registrati.append((event_type, payload, source_module))
        return []

    from app.services import event_bus
    monkeypatch.setattr(event_bus, "propagate_event", finto_propagate)
    return registrati


def test_fornitore_cassa_scrive_cassa_e_marca_pagata(monkeypatch, eventi):
    db = _setup(monkeypatch, "contanti")

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update["stato_pagamento"] == "pagata"
    assert update["pagato"] is True
    assert update["provvisorio"] is False
    assert update["decisione_pagamento_richiesta"] is False
    assert update["metodo_pagamento_effettivo"] == "cassa"
    assert update["data_pagamento"] == "2026-06-01"
    assert update["registrata_auto_da_metodo_fornitore"] is True
    assert len(db["prima_nota_cassa"].docs) == 1
    movimento = db["prima_nota_cassa"].docs[0]
    assert movimento["fattura_id"] == "fatt-1"
    assert movimento["data"] == "2026-06-01"
    assert movimento["importo"] == 122.0
    assert update["prima_nota_cassa_id"] == movimento["id"]
    assert db["prima_nota_banca"].docs == []
    assert db["invoices"].docs[0]["stato_pagamento"] == "pagata"
    assert [e[0] for e in eventi] == ["fattura.pagata"]
    assert eventi[0][1]["metodo_pagamento"] == "cassa"


def test_fornitore_banca_senza_estratto_resta_provvisoria(monkeypatch):
    db = _setup(monkeypatch, "bonifico")

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update["prima_nota_tipo"] == "banca"
    assert update["provvisorio"] is True
    assert update["stato_finanziario"] == "in_attesa_estratto_conto"
    # La riga provvisoria e' gia' l'attesa dell'estratto conto: nessuna
    # decisione da chiedere.
    assert update["decisione_pagamento_richiesta"] is False
    assert update.get("pagato") is not True
    assert len(db["prima_nota_banca"].docs) == 1
    movimento = db["prima_nota_banca"].docs[0]
    assert movimento["stato"] == "DA_VERIFICARE"
    assert movimento["canonico"] is False
    assert movimento["fattura_id"] == "fatt-1"
    assert db["prima_nota_cassa"].docs == []


def test_fornitore_assegno_senza_assegno_collegato_va_in_banca_provvisoria(monkeypatch):
    # Metodo abituale «assegno» senza un assegno compilato: e' banca e aspetta
    # l'estratto conto come un bonifico.
    db = _setup(monkeypatch, "assegno")

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update["prima_nota_tipo"] == "banca"
    assert update["provvisorio"] is True
    assert update["decisione_pagamento_richiesta"] is False
    assert len(db["prima_nota_banca"].docs) == 1
    assert db["prima_nota_banca"].docs[0]["metodo_pagamento_effettivo"] == "banca"


def _fattura_con_assegno():
    return {
        **FATTURA,
        # Cosi' la lascia assegni_fattura_intent._collega all'import.
        "metodo_pagamento": "assegno",
        "metodo_pagamento_previsto": "assegno",
        "metodo_pagamento_override_source": "assegno_compilato",
        "stato_finanziario": "in_attesa_estratto_conto",
        "pagato": False,
        "assegni_collegati": [{
            "assegno_id": "ass-1", "numero": "0208769328", "quota": 122.0,
            "banca_confermata": False,
        }],
    }


def test_assegno_collegato_dichiarato_in_attesa_banca_senza_decisione(monkeypatch, eventi):
    db = _setup(monkeypatch, "bonifico")
    db["assegni"].docs = [{"id": "ass-1", "numero": "0208769328", "importo": 122.0,
                          "stato": "assegnato", "fattura_collegata": "fatt-1"}]
    db["invoices"].docs = [_fattura_con_assegno()]

    update = _run(mod.auto_registra_prima_nota(db, _fattura_con_assegno(), None))

    # §39: pagamento dichiarato con assegno, in attesa di riscontro bancario.
    assert update["stato_finanziario"] == "in_attesa_estratto_conto"
    assert update["metodo_pagamento_previsto"] == "assegno"
    assert update["metodo_pagamento_effettivo"] is None
    assert update["provvisorio"] is True
    assert update["decisione_pagamento_richiesta"] is False
    assert update.get("pagato") is not True
    assert db["invoices"].docs[0].get("pagato") is not True
    # Una sola riga di attesa, marcata con l'assegno: la ritrova il riscontro
    # dell'estratto conto (assegni_estratto_conto) invece di scriverne un'altra.
    assert len(db["prima_nota_banca"].docs) == 1
    riga = db["prima_nota_banca"].docs[0]
    assert riga["fattura_id"] == "fatt-1"
    assert riga["assegno_id"] == "ass-1"
    assert riga["assegno_numero"] == "0208769328"
    assert riga["source"] == mod.SOURCE_ATTESA_ASSEGNO
    assert riga["provvisorio"] is True
    assert riga["riconciliato"] is False
    assert update["prima_nota_banca_id"] == riga["id"]
    assert db["prima_nota_cassa"].docs == []
    # Nessun `fattura.pagata`: la prova e' della banca.
    assert eventi == []


def test_assegno_collegato_non_crea_seconda_riga_di_attesa(monkeypatch, eventi):
    db = _setup(monkeypatch, "contanti")  # l'assegno prevale anche sul fornitore cassa
    db["assegni"].docs = [{"id": "ass-1", "numero": "0208769328", "importo": 122.0}]
    db["invoices"].docs = [_fattura_con_assegno()]

    primo = _run(mod.auto_registra_prima_nota(db, _fattura_con_assegno(), None))
    secondo = _run(mod.auto_registra_prima_nota(db, _fattura_con_assegno(), None))

    assert len(db["prima_nota_banca"].docs) == 1
    assert primo["prima_nota_banca_id"] == secondo["prima_nota_banca_id"]
    assert db["prima_nota_cassa"].docs == []
    assert eventi == []


def test_assegno_gia_in_banca_non_crea_attesa(monkeypatch, eventi):
    # L'estratto conto e' arrivato prima dell'XML: il completamento spetta a
    # collega_assegno_riconciliato_a_fattura, qui non si scrive nulla.
    db = _setup(monkeypatch, "bonifico")
    db["assegni"].docs = [{"id": "ass-1", "numero": "0208769328", "importo": 122.0,
                          "movimento_estratto_conto_id": "ec-9",
                          "incassato_confermato_banca": True}]
    db["invoices"].docs = [_fattura_con_assegno()]

    update = _run(mod.auto_registra_prima_nota(db, _fattura_con_assegno(), None))

    assert update["decisione_pagamento_richiesta"] is False
    assert "prima_nota_banca_id" not in update
    assert db["prima_nota_banca"].docs == []
    assert eventi == []


def test_fornitore_misto_resta_provvisoria(monkeypatch, eventi):
    db = _setup(monkeypatch, "misto")

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update is None
    assert db["prima_nota_cassa"].docs == []
    assert db["prima_nota_banca"].docs == []
    assert db["invoices"].docs[0].get("stato_pagamento") != "pagata"
    assert eventi == []


def test_fornitore_senza_metodo_resta_sospesa_con_alert(monkeypatch, eventi):
    db = _setup(monkeypatch, "")

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    # §29: metodo mancante -> sospesa con alert, mai ripiego su Cassa.
    assert update["stato_finanziario"] == mod.STATO_SOSPESA_METODO_MANCANTE
    assert update["decisione_pagamento_richiesta"] is True
    assert update["provvisorio"] is True
    assert db["prima_nota_cassa"].docs == []
    assert db["prima_nota_banca"].docs == []
    assert db["invoices"].docs[0].get("stato_pagamento") != "pagata"
    assert any(a["codice"] == "FAT_MP_NON_DEFINITO" for a in db["alerts"].docs)
    assert eventi == []


def test_reimport_cassa_non_duplica_pagamenti(monkeypatch, eventi):
    db = _setup(monkeypatch, "contanti")

    primo = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))
    secondo = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert len(db["prima_nota_cassa"].docs) == 1
    assert primo["prima_nota_cassa_id"] == secondo["prima_nota_cassa_id"]
    assert [e[0] for e in eventi] == ["fattura.pagata"]


def test_fattura_gia_pagata_non_riceve_un_secondo_pagamento(monkeypatch, eventi):
    # Report del titolare o storia ripristinata: e' gia' pagata in banca.
    db = _setup(monkeypatch, "contanti")
    fattura = {**FATTURA, "stato_pagamento": "pagata", "pagato": True}
    db["invoices"].docs = [dict(fattura)]

    update = _run(mod.auto_registra_prima_nota(db, fattura, None))

    assert update is None
    assert db["prima_nota_cassa"].docs == []
    assert eventi == []


def test_idempotente_banca_su_reimport(monkeypatch):
    db = _setup(monkeypatch, "banca")
    db["estratto_conto_movimenti"].docs = [{
        "id": "ec-1", "tipo": "uscita", "importo": 122.0,
        "data": "2026-06-10",
        "descrizione": "BONIFICO DOLCIARIA ACQUAVIVA FATTURA 77/A",
    }]

    _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))
    _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert len(db["prima_nota_banca"].docs) == 1
    assert db["prima_nota_banca"].docs[0]["estratto_conto_id"] == "ec-1"
    assert db["estratto_conto_movimenti"].docs[0]["riconciliato"] is True


def test_estratto_prima_della_fattura_abbina_solo_uscita_con_identita(monkeypatch):
    db = _setup(monkeypatch, "banca")
    db["estratto_conto_movimenti"].docs = [{
        "id": "ec-1", "tipo": "uscita", "importo": -122.0,
        "data": "2026-06-10",
        "descrizione": "SDD DOLCIARIA ACQUAVIVA FATTURA 77/A",
    }]

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update["prima_nota_tipo"] == "banca"
    assert update["movimento_bancario_id"] == "ec-1"
    assert update["riconciliato_con_ec"] is True


def test_sdd_importato_prima_della_fattura_si_aggancia_senza_numero_in_causale(monkeypatch):
    db = _setup(monkeypatch, "banca")
    db["estratto_conto_movimenti"].docs = [{
        "id": "ec-sdd", "tipo": "uscita", "importo": -122.0,
        "data": "2026-06-10",
        "descrizione_originale": "ADDEBITO DIRETTO SDD DOLCIARIA ACQUAVIVA S.P.A.",
    }]

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update["prima_nota_tipo"] == "banca"
    assert update["movimento_bancario_id"] == "ec-sdd"
    assert update["match_tipo"] == "sdd+fornitore+importo+data"
    assert db["estratto_conto_movimenti"].docs[0]["riconciliato"] is True


def test_stesso_importo_accredito_pos_non_paga_fattura(monkeypatch):
    db = _setup(monkeypatch, "banca")
    db["estratto_conto_movimenti"].docs = [{
        "id": "pos-1", "tipo": "entrata", "importo": 122.0,
        "data": "2026-06-02", "descrizione": "NUMIA POS",
    }]

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update["provvisorio"] is True
    assert update.get("pagato") is not True
    assert len(db["prima_nota_banca"].docs) == 1
    assert db["prima_nota_banca"].docs[0]["riconciliato"] is False
    assert db["estratto_conto_movimenti"].docs[0].get("riconciliato") is not True


def test_fornitore_escluso_non_entra_in_cassa_banca_ma_mantiene_iva(monkeypatch):
    db = _setup(monkeypatch, "banca", esclude_cassa_banca=True)
    fattura = dict(FATTURA)

    update = _run(mod.auto_registra_prima_nota(db, fattura, None))

    assert update is None
    assert db["prima_nota_cassa"].docs == []
    assert db["prima_nota_banca"].docs == []
    assert fattura["esclusa_da_cassa_banca"] is True
    assert fattura["registrazione_fiscale_mantenuta"] is True
    assert db["invoices"].docs[0]["imponibile"] == 100.0
    assert db["invoices"].docs[0]["iva"] == 22.0


def test_fornitore_cessato_e_automaticamente_escluso_solo_finanziariamente(monkeypatch):
    db = _setup(monkeypatch, "contanti", cessato=True)

    update = _run(mod.auto_registra_prima_nota(db, dict(FATTURA), None))

    assert update is None
    assert db["prima_nota_cassa"].docs == []
    assert db["prima_nota_banca"].docs == []
    assert db["invoices"].docs[0]["iva"] == 22.0
