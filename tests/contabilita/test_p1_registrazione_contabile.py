"""P1 §6.1 — Motore UNICO di registrazione contabile (partita doppia, schema CEE).
Idempotenza, numero registrazione progressivo, fonte documento, data competenza,
DARE/AVERE quadrati, centro di costo, aggiornamento saldi. Mock async del DB."""
import asyncio

import app.services.registrazione_contabile as motore


class _Coll:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def find_one(self, query, proj=None, sort=None):
        cand = [d for d in self.docs if all(_match(d, k, v) for k, v in query.items())]
        if sort:
            key, direction = sort[0]
            cand.sort(key=lambda d: d.get(key) or 0, reverse=(direction < 0))
        return dict(cand[0]) if cand else None

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if all(_match(d, k, v) for k, v in query.items()):
                d.update(update.get("$set", {}))
                return
        if upsert:
            nd = dict(query)
            nd.update(update.get("$set", {}))
            self.docs.append(nd)


def _match(doc, k, v):
    if isinstance(v, dict) and "$exists" in v:
        return (k in doc) == v["$exists"]
    return doc.get(k) == v


class _Db:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, name):
        return self.colls.setdefault(name, _Coll())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _prepara(db, monkeypatch):
    # piano_conti con i conti usati
    pc = db["piano_conti"]
    for codice, cat in [("05.01.01", "costi"), ("01.04.01", "attivo"),
                        ("02.01.01", "passivo"), ("01.01.01", "attivo"),
                        ("01.01.02", "attivo"), ("04.01.02", "ricavi"),
                        ("02.03.01", "passivo")]:
        pc.docs.append({"codice": codice, "categoria": cat, "saldo": 0.0})

    async def _det(_db, _fatt):
        return {"costo": {"codice": "05.01.01", "nome": "Acquisto merci"},
                "iva_credito": {"codice": "01.04.01", "nome": "IVA a credito"},
                "debito_fornitore": {"codice": "02.01.01", "nome": "Debiti v/fornitori"}}

    async def _saldo(_db, codice, importo, verso):
        for d in pc.docs:
            if d["codice"] == codice:
                cat = d["categoria"]
                if cat in ("attivo", "costi"):
                    d["saldo"] += importo if verso == "dare" else -importo
                else:
                    d["saldo"] += importo if verso == "avere" else -importo

    import app.routers.accounting.piano_conti as pcmod
    monkeypatch.setattr(pcmod, "determina_conti_fattura", _det)
    monkeypatch.setattr(pcmod, "aggiorna_saldo_conto", _saldo)


def test_registra_fattura_idempotente_e_quadrata(monkeypatch):
    db = _Db()
    _prepara(db, monkeypatch)
    fattura = {"id": "F1", "total_amount": 122.0, "total_tax": 22.0,
               "iva_detraibile": 22.0,
               "invoice_number": "1/2026", "invoice_date": "2026-03-10",
               "supplier_name": "ACME"}

    r1 = _run(motore.registra_fattura(db, fattura))
    assert r1["stato"] == "registrato"
    mov = r1["movimento"]
    # quadratura DARE=AVERE
    assert round(mov["totale_dare"], 2) == round(mov["totale_avere"], 2) == 122.0
    # requisiti §6.1
    assert mov["numero_registrazione"] == 1
    assert mov["fonte_documento"]["id"] == "F1"
    assert mov["data_competenza"] == "2026-03-10"
    assert mov["anno"] == 2026
    assert {r["conto_codice"] for r in mov["righe"]} == {"05.01.01", "01.04.01", "02.01.01"}

    # idempotenza: seconda chiamata non registra di nuovo
    r2 = _run(motore.registra_fattura(db, fattura))
    assert r2["stato"] == "gia_registrato"
    assert len(db["movimenti_contabili"].docs) == 1

    # saldi aggiornati una sola volta
    saldi = {d["codice"]: d["saldo"] for d in db["piano_conti"].docs}
    assert saldi["05.01.01"] == 100.0   # costo (dare)
    assert saldi["01.04.01"] == 22.0    # iva credito (dare)
    assert saldi["02.01.01"] == 122.0   # debito fornitore (avere)


def test_numero_registrazione_progressivo(monkeypatch):
    db = _Db()
    _prepara(db, monkeypatch)
    r1 = _run(motore.registra_fattura(db, {"id": "A", "total_amount": 10, "total_tax": 0,
                                           "invoice_date": "2026-01-01"}))
    r2 = _run(motore.registra_fattura(db, {"id": "B", "total_amount": 20, "total_tax": 0,
                                           "invoice_date": "2026-01-02"}))
    assert r1["movimento"]["numero_registrazione"] == 1
    assert r2["movimento"]["numero_registrazione"] == 2


def test_iva_indetraibile_aumenta_il_costo_non_il_credito_iva(monkeypatch):
    db = _Db()
    _prepara(db, monkeypatch)
    fattura = {
        "id": "AUTO1", "total_amount": 122.0, "total_tax": 22.0,
        "iva_detraibile": 8.80, "invoice_date": "2026-03-10",
    }

    mov = _run(motore.registra_fattura(db, fattura))["movimento"]
    righe = {r["conto_codice"]: r for r in mov["righe"]}

    assert righe["01.04.01"]["dare"] == 8.80
    assert righe["05.01.01"]["dare"] == 113.20
    assert mov["iva_indetraibile"] == 13.20
    assert mov["totale_dare"] == mov["totale_avere"] == 122.0


def test_fattura_con_iva_non_classificata_non_crea_credito(monkeypatch):
    db = _Db()
    _prepara(db, monkeypatch)
    fattura = {
        "id": "REVIEW1", "total_amount": 122.0, "total_tax": 22.0,
        "invoice_date": "2026-03-10",
    }

    result = _run(motore.registra_fattura(db, fattura))

    assert result == {
        "stato": "da_verificare",
        "motivo": "IVA detraibile non classificata",
    }
    assert db["movimenti_contabili"].docs == []


def test_registra_corrispettivo_scorporo(monkeypatch):
    db = _Db()
    _prepara(db, monkeypatch)
    r = _run(motore.registra_corrispettivo(db, {"id": "C1", "totale": 110.0,
                                                "data": "2026-04-01"}))
    assert r["stato"] == "registrato"
    mov = r["movimento"]
    assert round(mov["totale_dare"], 2) == round(mov["totale_avere"], 2) == 110.0
    assert mov["iva"] == 10.0 and mov["imponibile"] == 100.0
    # idempotenza
    r2 = _run(motore.registra_corrispettivo(db, {"id": "C1", "totale": 110.0}))
    assert r2["stato"] == "gia_registrato"


def test_registra_corrispettivo_usa_iva_xml_esplicita(monkeypatch):
    db = _Db()
    _prepara(db, monkeypatch)
    result = _run(motore.registra_corrispettivo(db, {
        "id": "XML1", "totale": 122.0, "totale_imponibile": 100.0,
        "totale_iva": 22.0, "pagato_contante": 20.0,
        "pagato_elettronico": 102.0, "data": "2026-04-02",
    }))

    assert result["stato"] == "registrato"
    assert result["movimento"]["imponibile"] == 100.0
    assert result["movimento"]["iva"] == 22.0
    assert result["movimento"]["totale_dare"] == result["movimento"]["totale_avere"] == 122.0


def test_registra_corrispettivo_non_registra_ripartizione_non_quadrata(monkeypatch):
    db = _Db()
    _prepara(db, monkeypatch)
    result = _run(motore.registra_corrispettivo(db, {
        "id": "BAD1", "totale": 100.0, "totale_imponibile": 90.91,
        "totale_iva": 9.09, "pagato_contante": 10.0,
        "pagato_elettronico": 20.0, "data": "2026-04-02",
    }))

    assert result["stato"] == "da_verificare"
    assert db["movimenti_contabili"].docs == []
