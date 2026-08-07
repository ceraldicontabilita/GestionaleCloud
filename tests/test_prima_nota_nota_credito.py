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
        elif isinstance(v, dict) and "$lt" in v:
            out = out and (str(doc.get(k, "")) < v["$lt"])
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

    def sort(self, *args, **kwargs):
        return self

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


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


def test_cassa_senza_metodo_approvato_richiede_conferma_esplicita(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(metodo_pagamento="banca")]
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc:
        _run(sync_mod.conferma_fattura_provvisoria({
            "fattura_id": "fatt-1", "metodo": "cassa",
        }))

    assert exc.value.status_code == 409
    assert db["prima_nota_cassa"].docs == []


def test_cassa_confermata_sulla_fattura_non_modifica_il_fornitore(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(
        supplier_vat="01234567890", metodo_pagamento="banca",
    )]
    db["suppliers"].docs = [{
        "id": "forn-1", "partita_iva": "01234567890",
        "metodo_pagamento_predefinito": "banca",
    }]
    _patch_db(monkeypatch, db)

    res = _run(sync_mod.conferma_fattura_provvisoria({
        "fattura_id": "fatt-1",
        "metodo": "cassa",
        "approva_metodo_fattura": True,
        "performed_by": "test",
    }))

    assert res["success"] is True
    assert len(db["prima_nota_cassa"].docs) == 1
    fattura = db["invoices"].docs[0]
    assert fattura["metodo_pagamento_previsto"] == "cassa"
    assert fattura["metodo_pagamento_override_source"] == "operatore_prima_nota"
    assert db["suppliers"].docs[0]["metodo_pagamento_predefinito"] == "banca"


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


def test_attendi_banca_sposta_la_fattura_senza_creare_pagamento(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(metodo_pagamento="cassa")]
    _patch_db(monkeypatch, db)

    res = _run(sync_mod.imposta_fattura_in_attesa_banca({
        "fattura_id": "fatt-1", "performed_by": "test",
    }))

    assert res["success"] is True
    assert res["stato"] == "in_attesa_banca"
    assert res["pagato"] is False
    assert db["prima_nota_banca"].docs == []
    fattura = db["invoices"].docs[0]
    assert fattura["metodo_pagamento_previsto"] == "banca"
    assert fattura["metodo_pagamento_override_source"] == "operatore_prima_nota"
    assert fattura["stato_finanziario"] == "aperta_in_attesa_banca"
    assert fattura["pagato"] is False


def test_attesa_banca_puo_tornare_da_decidere_senza_creare_pagamento(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(
        metodo_pagamento_previsto="banca",
        metodo_pagamento_override_source="operatore_prima_nota",
        stato_pagamento="in_attesa_banca",
        pagato=False,
        paid=False,
    )]
    _patch_db(monkeypatch, db)

    res = _run(sync_mod.riporta_fattura_da_decidere({"fattura_id": "fatt-1"}))

    assert res["success"] is True
    assert res["stato"] == "da_decidere"
    assert db["prima_nota_banca"].docs == []
    fattura = db["invoices"].docs[0]
    assert fattura["metodo_pagamento_previsto"] == "da_decidere"
    assert fattura["stato_finanziario"] == "aperta_da_decidere"
    assert fattura["pagato"] is False


def test_attendi_banca_non_riapre_una_fattura_gia_registrata(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura()]
    db["prima_nota_cassa"].docs = [{
        "id": "pn-1", "fattura_id": "fatt-1", "status": "active",
    }]
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc:
        _run(sync_mod.imposta_fattura_in_attesa_banca({"fattura_id": "fatt-1"}))

    assert exc.value.status_code == 409
    assert db["invoices"].docs[0].get("metodo_pagamento_previsto") != "banca"


def test_attendi_banca_compare_nella_lista_dedicata(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(
        supplier_vat="01234567890",
        metodo_pagamento_previsto="banca",
        metodo_pagamento_override_source="operatore_prima_nota",
        stato_pagamento="in_attesa_banca",
        pagato=False,
        paid=False,
    )]
    _patch_db(monkeypatch, db)

    async def _senza_pagamento(_db, fatture):
        return fatture

    monkeypatch.setattr(
        sync_mod,
        "fatture_senza_pagamento_contabile_confermato",
        _senza_pagamento,
    )

    res = _run(sync_mod.get_fatture_provvisorie(anno=2026))

    assert res["provvisori"] == []
    assert len(res["in_attesa_banca"]) == 1
    attesa = res["in_attesa_banca"][0]
    assert attesa["fattura_id"] == "fatt-1"
    assert attesa["fonte_metodo"] == "operatore_prima_nota"
    assert attesa["stato_match"] == "in_attesa_estratto_conto"


def test_rimborso_di_un_doppio_bonifico_lascia_un_riscontro_netto(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(
        id="fatt-passalacqua", invoice_number="V1-2026-007590",
        invoice_date="2026-06-15", supplier_name="S. PASSALACQUA S.P.A.",
        supplier_vat="00123456789", total_amount=1220.0,
        metodo_pagamento_previsto="banca",
        metodo_pagamento_override_source="operatore_prima_nota",
    )]
    db["estratto_conto_movimenti"].docs = [
        {"id": "ec-out-1", "data": "2026-06-15", "tipo": "uscita",
         "importo": 1220.0,
         "descrizione": "FAVORE S. PASSALACQUA S.P.A. fattura 7590"},
        {"id": "ec-out-2", "data": "2026-06-15", "tipo": "uscita",
         "importo": 1220.0,
         "descrizione": "FAVORE S. PASSALACQUA S.P.A. fattura 7590"},
        {"id": "ec-refund", "data": "2026-06-15", "tipo": "entrata",
         "importo": 1220.0,
         "descrizione": "PASSALACQUA RESTITUZIONE IMPORTO DUPLICATO"},
    ]
    _patch_db(monkeypatch, db)

    async def _senza_pagamento(_db, fatture):
        return fatture
    monkeypatch.setattr(
        sync_mod, "fatture_senza_pagamento_contabile_confermato",
        _senza_pagamento,
    )

    res = _run(sync_mod.get_fatture_provvisorie(anno=2026))

    attesa = res["in_attesa_banca"][0]
    assert attesa["movimento_banca"] is not None
    assert attesa["evidenza_banca"]["tipo"] == "pagamento_netto_dopo_rimborso_duplicato"
    assert attesa["evidenza_banca"]["rimborsi_ids"] == ["ec-refund"]


def test_assegno_cumulativo_trova_un_solo_lotto_di_fatture(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [
        _fattura(id="siro-1", invoice_number="2/1485", invoice_date="2026-06-12",
                 supplier_name="SIRO S.R.L.", supplier_vat="04104640612",
                 total_amount=121.37, metodo_pagamento_previsto="banca",
                 metodo_pagamento_override_source="operatore_prima_nota"),
        _fattura(id="siro-2", invoice_number="2/1486", invoice_date="2026-06-12",
                 supplier_name="SIRO S.R.L.", supplier_vat="04104640612",
                 total_amount=943.0, metodo_pagamento_previsto="banca",
                 metodo_pagamento_override_source="operatore_prima_nota"),
        _fattura(id="siro-3", invoice_number="1/778", invoice_date="2026-06-12",
                 supplier_name="SIRO S.R.L.", supplier_vat="04104640612",
                 total_amount=18.15, metodo_pagamento_previsto="banca",
                 metodo_pagamento_override_source="operatore_prima_nota"),
    ]
    db["estratto_conto_movimenti"].docs = [{
        "id": "ec-check", "data": "2026-06-19", "tipo": "uscita",
        "importo": 1082.52,
        "descrizione": "PRELIEVO ASSEGNO NUM: 0208769334",
        "riconciliato": True,
    }]
    _patch_db(monkeypatch, db)

    async def _senza_pagamento(_db, fatture):
        return fatture
    monkeypatch.setattr(
        sync_mod, "fatture_senza_pagamento_contabile_confermato",
        _senza_pagamento,
    )

    res = _run(sync_mod.get_fatture_provvisorie(anno=2026))

    assert len(res["in_attesa_banca"]) == 3
    assert {r["movimento_banca"]["id"] for r in res["in_attesa_banca"]} == {"ec-check"}
    assert all(
        r["evidenza_banca"]["tipo"] == "assegno_cumulativo_lotto_fatture"
        for r in res["in_attesa_banca"]
    )


def test_due_assegni_uguali_seguono_due_fatture_uguali_in_ordine(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [
        _fattura(id="kimbo-old", invoice_number="0070017034",
                 invoice_date="2026-05-20", supplier_name="KIMBO S.P.A.",
                 supplier_vat="00123456789", total_amount=1498.96,
                 metodo_pagamento_previsto="banca",
                 metodo_pagamento_override_source="operatore_prima_nota"),
        _fattura(id="kimbo-new", invoice_number="0070020417",
                 invoice_date="2026-06-16", supplier_name="KIMBO S.P.A.",
                 supplier_vat="00123456789", total_amount=1498.96,
                 metodo_pagamento_previsto="banca",
                 metodo_pagamento_override_source="operatore_prima_nota"),
    ]
    db["estratto_conto_movimenti"].docs = [
        {"id": "check-old", "data": "2026-05-28", "tipo": "uscita",
         "importo": 1498.96, "descrizione": "PRELIEVO ASSEGNO NUM: 0208769323",
         "riconciliato": True},
        {"id": "check-new", "data": "2026-06-24", "tipo": "uscita",
         "importo": 1498.96, "descrizione": "PRELIEVO ASSEGNO NUM: 0208769335",
         "riconciliato": True},
    ]
    _patch_db(monkeypatch, db)

    async def _senza_pagamento(_db, fatture):
        return fatture
    monkeypatch.setattr(
        sync_mod, "fatture_senza_pagamento_contabile_confermato",
        _senza_pagamento,
    )

    res = _run(sync_mod.get_fatture_provvisorie(anno=2026))
    per_id = {r["fattura_id"]: r for r in res["in_attesa_banca"]}

    assert per_id["kimbo-old"]["movimento_banca"]["id"] == "check-old"
    assert per_id["kimbo-new"]["movimento_banca"]["id"] == "check-new"
    assert all(
        r["evidenza_banca"]["tipo"] == "sequenza_assegni_fatture_stesso_fornitore_importo"
        for r in per_id.values()
    )


def test_provvisori_non_taglia_i_primi_mesi_oltre_cinquemila_fatture(monkeypatch):
    """Il limite storico di 5.000 righe eliminava gennaio-maggio quando
    l'anno conteneva piu' documenti, perche' il cursore era ordinato dalla
    fattura piu' recente. La pagina deve ricevere l'intero anno selezionato.
    """
    db = _FakeDb()
    db["invoices"].docs = [
        _fattura(
            id=f"fatt-giugno-{indice}",
            invoice_number=f"G-{indice}",
            invoice_date="2026-06-01",
            total_amount=1.0,
        )
        for indice in range(5000)
    ] + [
        _fattura(
            id="fatt-gennaio-non-tagliata",
            invoice_number="GEN-1",
            invoice_date="2026-01-10",
            total_amount=1.0,
        )
    ]
    _patch_db(monkeypatch, db)

    async def _senza_pagamento(_db, fatture):
        return fatture

    monkeypatch.setattr(
        sync_mod,
        "fatture_senza_pagamento_contabile_confermato",
        _senza_pagamento,
    )

    res = _run(sync_mod.get_fatture_provvisorie(anno=2026))

    tutte = res["provvisori"] + res["in_attesa_banca"]
    assert len(tutte) == 5001
    assert any(
        fattura["fattura_id"] == "fatt-gennaio-non-tagliata"
        for fattura in tutte
    )


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


def test_divisione_registra_solo_cassa_e_lascia_residuo_banca(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(total_amount=100.0)]
    _patch_db(monkeypatch, db)

    res = _run(sync_mod.conferma_divisione_provvisoria({
        "fattura_id": "fatt-1",
        "importo_cassa": 40,
        "importo_banca": 60,
        "performed_by": "test",
    }))

    assert res["success"] is True
    assert res["stato"] == "parzialmente_pagata_in_attesa_banca"
    assert res["movimento_banca_id"] is None
    assert len(db["prima_nota_cassa"].docs) == 1
    assert db["prima_nota_cassa"].docs[0]["importo"] == 40.0
    assert db["prima_nota_banca"].docs == []
    fattura = db["invoices"].docs[0]
    assert fattura["pagato"] is False
    assert fattura["paid"] is False
    assert fattura["payment_status"] == "partial"
    assert fattura["stato_finanziario"] == "aperta_in_attesa_banca"
    assert fattura["importo_pagato"] == 40.0
    assert fattura["importo_residuo"] == 60.0
    assert fattura["metodo_pagamento_previsto"] == "banca"
    assert fattura.get("prima_nota_banca_id") is None
    assert fattura.get("data_pagamento") is None
    assert fattura.get("prima_nota_payment_claim") is None


def test_claim_attivo_blocca_il_doppio_invio(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(
        prima_nota_payment_claim="operazione-in-corso",
        prima_nota_payment_claim_at="2999-01-01T00:00:00+00:00",
    )]
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc:
        _run(sync_mod.conferma_divisione_provvisoria({
            "fattura_id": "fatt-1",
            "importo_cassa": 20,
            "importo_banca": 38,
        }))

    assert exc.value.status_code == 409
    assert db["prima_nota_cassa"].docs == []
    assert db["prima_nota_banca"].docs == []


def test_banca_chiude_esattamente_il_residuo_del_parziale(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(
        total_amount=100.0,
        metodo_pagamento="banca",
        prima_nota_cassa_id="pn-cassa-40",
        stato_pagamento="parzialmente_pagata",
    )]
    db["prima_nota_cassa"].docs = [{
        "id": "pn-cassa-40",
        "fattura_id": "fatt-1",
        "importo": 40.0,
        "status": "active",
    }]
    db["estratto_conto_movimenti"].docs = [{
        "id": "ec-residuo-60",
        "data": "2026-06-10",
        "importo": -60.0,
        "descrizione": "BONIFICO RESIDUO RONDINELLA",
        "riconciliato": False,
    }]
    _patch_db(monkeypatch, db)

    res = _run(sync_mod.conferma_fattura_provvisoria({
        "fattura_id": "fatt-1",
        "metodo": "banca",
        "movimento_banca_id": "ec-residuo-60",
    }))

    assert res["success"] is True
    assert res["importo"] == 60.0
    assert len(db["prima_nota_banca"].docs) == 1
    assert db["prima_nota_banca"].docs[0]["importo"] == 60.0
    fattura = db["invoices"].docs[0]
    assert fattura["paid"] is True
    assert fattura["payment_status"] == "paid"
    assert fattura["importo_pagato"] == 100.0
    assert fattura["importo_residuo"] == 0


def test_cassa_non_puo_chiudere_il_residuo_di_un_parziale_esistente(monkeypatch):
    db = _FakeDb()
    db["invoices"].docs = [_fattura(
        total_amount=100.0,
        metodo_pagamento="cassa",
        prima_nota_cassa_id="pn-cassa-40",
        stato_pagamento="parzialmente_pagata",
    )]
    db["prima_nota_cassa"].docs = [{
        "id": "pn-cassa-40",
        "fattura_id": "fatt-1",
        "importo": 40.0,
        "status": "active",
    }]
    _patch_db(monkeypatch, db)

    with pytest.raises(HTTPException) as exc:
        _run(sync_mod.conferma_fattura_provvisoria({
            "fattura_id": "fatt-1",
            "metodo": "cassa",
        }))

    assert exc.value.status_code == 409
    assert "pagamento parziale" in exc.value.detail
    assert len(db["prima_nota_cassa"].docs) == 1
    fattura = db["invoices"].docs[0]
    assert fattura.get("paid") is not True
    assert fattura.get("prima_nota_payment_claim") is None


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
