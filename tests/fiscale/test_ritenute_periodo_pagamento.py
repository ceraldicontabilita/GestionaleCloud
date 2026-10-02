"""Ritenuta 1040 di una parcella: il periodo e' il MESE DEL PAGAMENTO al professionista.

Decisione del titolare (02/10/2026; art. 25 DPR 600/1973, la ritenuta nasce
all'atto del pagamento): una parcella di marzo pagata ad aprile va nel 1040
di aprile, da versare entro il 16 maggio. Finche' la fattura non e' pagata il
periodo resta vuoto («in attesa del pagamento»), mai il mese della fattura.
"""
import asyncio

from app.routers import ritenute as mod
from app.services import tributi_per_codice as tributi

XML = """<FatturaElettronica><DatiGeneraliDocumento>
<DatiRitenuta><TipoRitenuta>RT01</TipoRitenuta><ImportoRitenuta>280.00</ImportoRitenuta>
<AliquotaRitenuta>20.00</AliquotaRitenuta><CausalePagamento>A</CausalePagamento></DatiRitenuta>
</DatiGeneraliDocumento></FatturaElettronica>"""


def _match(doc, query):
    for k, v in query.items():
        campo = doc.get(k)
        if isinstance(v, dict):
            if "$in" in v and campo not in v["$in"]:
                return False
            if "$nin" in v and campo in v["$nin"]:
                return False
            if "$ne" in v and campo == v["$ne"]:
                return False
        elif campo != v:
            return False
    return True


class _Cur:
    def __init__(self, docs):
        self._d = docs

    async def to_list(self, n=None):
        return [dict(d) for d in self._d]

    def sort(self, *a, **k):
        return self


class _Res:
    modified_count = 1


class _Coll:
    def __init__(self):
        self.docs = []

    def find(self, query=None, projection=None):
        return _Cur([d for d in self.docs if _match(d, query or {})])

    async def find_one(self, query, *a, **k):
        for d in self.docs:
            if _match(d, query):
                return dict(d)
        return None

    async def count_documents(self, query):
        return sum(1 for d in self.docs if _match(d, query))

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
                return _Res()
        if upsert:
            self.docs.append(dict(update.get("$set", {})))
        return _Res()

    async def update_many(self, query, update):
        for d in self.docs:
            if _match(d, query):
                d.update(update.get("$set", {}))
        return _Res()


class _Db:
    def __init__(self):
        self.c = {}

    def __getitem__(self, name):
        return self.c.setdefault(name, _Coll())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _fattura_di_marzo(**extra):
    return {"id": 4321, "invoice_number": "12/2026", "invoice_date": "2026-03-10",
            "supplier_name": "Studio Rossi", "supplier_vat": "01234567890",
            "xml_raw": XML, **extra}


def _senza_telegram(monkeypatch):
    async def muto(*a, **k):
        return {}
    import app.services.telegram_notifications as tg
    monkeypatch.setattr(tg, "send_notification", muto)


def test_parcella_non_pagata_resta_in_attesa_del_pagamento(monkeypatch):
    _senza_telegram(monkeypatch)
    db = _Db()
    rit = _run(mod.upsert_ritenuta_da_fattura(db, _fattura_di_marzo()))
    assert rit["data_fattura"] == "2026-03-10"
    assert rit["periodo_ritenuta"] is None, "mai il mese della fattura"
    assert rit["scadenza"] is None and rit["scadenza_legale"] is None
    assert rit["periodo_fonte"] == mod.STATO_PERIODO_IN_ATTESA_PAGAMENTO

    # La riconciliazione non cerca nessun F24 1040 (nemmeno uno di marzo).
    db["f24_unificato"].docs = [{
        "id": "F-MARZO", "sezione_erario": [
            {"codice_tributo": "1040", "periodo_riferimento": "03/2026", "importo_debito": 280.0}],
        "quietanza_id": "q-3", "data_pagamento_quietanza": "2026-04-16",
    }]
    upd = _run(mod._riconcilia_ritenuta(db, rit, f24_docs=db["f24_unificato"].docs))
    assert upd["stato"] == "in_attesa_pagamento" and upd["f24_id"] is None

    # L'alert «ritenuta da versare» dice che il periodo non e' ancora fissato.
    (alert,) = db["alerts"].docs
    assert alert["codice"] == "RITENUTA_DA_VERSARE"
    assert "in attesa del pagamento" in alert["dettaglio"]
    assert "16/04/2026" not in alert["dettaglio"]

    # Nel registro Tributi non compare in nessun mese.
    voci = tributi.costruisci({"f24": [], "quietanze": [], "movimenti": [], "quietanze_per_f24": {},
                               "quietanze_per_id": {}, "movimenti_per_f24": {}}, [rit])
    assert [v for v in voci if v["codice"] == "1040"] == []


def test_fattura_di_marzo_pagata_ad_aprile_va_nel_1040_di_aprile(monkeypatch):
    _senza_telegram(monkeypatch)
    db = _Db()
    rit = _run(mod.upsert_ritenuta_da_fattura(db, _fattura_di_marzo()))
    assert rit["periodo_ritenuta"] is None

    # Il titolare paga la parcella con bonifico il 20/04/2026.
    db["invoices"].docs = [_fattura_di_marzo(stato="pagata", data_pagamento="2026-04-20")]
    cambiate = _run(mod._allinea_periodo_al_pagamento(db, db["ritenute_acconto"].docs))
    assert cambiate == 1
    (rit,) = db["ritenute_acconto"].docs
    assert rit["periodo_ritenuta"] == "2026-04"
    assert rit["data_pagamento_fattura"] == "2026-04-20"
    assert rit["scadenza"] == "2026-05-16"            # versamento entro il 16/05
    assert rit["scadenza_legale"] == "2026-05-18"     # il 16/05/2026 e' sabato
    assert rit["periodo_fonte"] == mod.STATO_PERIODO_DA_PAGAMENTO
    assert rit["data_fattura"] == "2026-03-10"        # la data della fattura resta, non comanda

    # Il 1040 di marzo (mese della fattura) NON e' il suo; quello di aprile si'.
    f24_docs = [
        {"id": "F-MARZO", "sezione_erario": [
            {"codice_tributo": "1040", "periodo_riferimento": "03/2026", "importo_debito": 280.0}],
         "quietanza_id": "q-3", "data_pagamento_quietanza": "2026-04-16"},
        {"id": "F-APRILE", "sezione_erario": [
            {"codice_tributo": "1040", "periodo_riferimento": "04/2026", "importo_debito": 280.0}],
         "quietanza_id": "q-4", "data_pagamento_quietanza": "2026-05-15"},
    ]
    upd = _run(mod._riconcilia_ritenuta(db, rit, ritenute_periodo=[rit], f24_docs=f24_docs))
    assert upd["f24_id"] == "F-APRILE"
    assert upd["f24_periodo"] == "2026-04"
    assert upd["stato"] == "pagata_puntuale"
    assert upd["data_pagamento"] == "2026-05-15"

    # Secondo riallineamento: niente cambia (idempotente).
    assert _run(mod._allinea_periodo_al_pagamento(db, db["ritenute_acconto"].docs)) == 0

    # Nel registro Tributi la ritenuta attesa sta in aprile, non in marzo.
    voci = tributi.costruisci({"f24": [], "quietanze": [], "movimenti": [], "quietanze_per_f24": {},
                               "quietanze_per_id": {}, "movimenti_per_f24": {}}, [rit])
    (voce,) = [v for v in voci if v["codice"] == "1040"]
    assert (voce["anno"], voce["mese"]) == (2026, 4)


def test_pagamento_al_professionista_vale_solo_se_la_fattura_e_pagata():
    """Un `data_pagamento` rimasto su una fattura riaperta non fissa il periodo."""
    assert mod.data_pagamento_fattura({"data_pagamento": "2026-04-20"}) is None
    assert mod.data_pagamento_fattura({"data_pagamento": "2026-04-20", "stato": "da_pagare"}) is None
    assert mod.data_pagamento_fattura({"data_pagamento": "2026-04-20", "pagato": True}) == "2026-04-20"
    assert mod.data_pagamento_fattura({"data_pagamento": "2026-04-20T10:00:00", "stato": "pagata"}) == "2026-04-20"
    pagata_senza_data = mod.periodo_da_pagamento({"stato": "pagata"})
    assert pagata_senza_data["periodo_ritenuta"] is None
    assert pagata_senza_data["periodo_fonte"] == mod.STATO_PERIODO_PAGATA_SENZA_DATA


def test_il_periodo_non_ricade_mai_sulla_data_fattura():
    assert mod._periodo_ritenuta({"data_fattura": "2026-03-10"}) is None
    assert mod._periodo_ritenuta({"periodo_ritenuta": "2026-04", "data_fattura": "2026-03-10"}) == "2026-04"
    # Anche il registro Tributi non legge piu' `data_fattura` come periodo.
    voci = tributi.costruisci({"f24": [], "quietanze": [], "movimenti": [], "quietanze_per_f24": {},
                               "quietanze_per_id": {}, "movimenti_per_f24": {}},
                              [{"id": "r", "data_fattura": "2026-03-10", "importo_cents": 28000}])
    assert [v for v in voci if v["codice"] == "1040"] == []
