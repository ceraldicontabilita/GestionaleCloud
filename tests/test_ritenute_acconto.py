"""Sezione RITENUTE (richiesta utente 18/07/2026): estrazione da XML con
DatiRitenuta, scadenza al 16 del mese successivo, associazione all'F24 con
codice 1040 e classificazione del pagamento (puntuale / con ravvedimento
8906+1989 / in ritardo senza ravvedimento)."""
import asyncio

from app.routers import ritenute as mod

XML = """<FatturaElettronica><DatiGeneraliDocumento>
<DatiRitenuta><TipoRitenuta>RT01</TipoRitenuta><ImportoRitenuta>280.00</ImportoRitenuta>
<AliquotaRitenuta>20.00</AliquotaRitenuta><CausalePagamento>A</CausalePagamento></DatiRitenuta>
</DatiGeneraliDocumento></FatturaElettronica>"""


def test_estrazione_dati_ritenuta():
    d = mod._estrai_dati_ritenuta(XML)
    assert d == {"tipo": "RT01", "importo": 280.0, "aliquota": "20.00", "causale": "A"}
    assert mod._estrai_dati_ritenuta("<FatturaElettronica/>") is None


def test_scadenza_16_mese_successivo():
    assert mod._scadenza_16_mese_successivo("2026-03-20") == "2026-04-16"
    assert mod._scadenza_16_mese_successivo("2026-12-05") == "2027-01-16"


class _Cur:
    def __init__(self, docs): self._d = list(docs)
    def __aiter__(self): self._i = iter(self._d); return self
    async def __anext__(self):
        try: return next(self._i)
        except StopIteration: raise StopAsyncIteration


class _Coll:
    def __init__(self, docs=None): self.docs = docs or []
    def find(self, *a, **k): return _Cur(self.docs)


class _Db:
    def __init__(self): self.c = {}
    def __getitem__(self, name): return self.c.setdefault(name, _Coll())


def _run(c):
    loop = asyncio.new_event_loop()
    try: return loop.run_until_complete(c)
    finally: loop.close()


RIT = {"importo": 280.0, "scadenza": "2026-04-16"}


def test_f24_1040_puntuale():
    db = _Db()
    db["f24_unificato"].docs = [{
        "id": "F1", "tributi": [{"codice": "1040", "importo": 280.0}],
        "data_pagamento": "2026-04-16",
    }]
    upd = _run(mod._riconcilia_ritenuta(db, dict(RIT)))
    assert upd["f24_id"] == "F1"
    assert upd["stato"] == "pagata_puntuale"


def test_f24_1040_tardivo_con_ravvedimento():
    db = _Db()
    db["f24_unificato"].docs = [{
        "id": "F2",
        "tributi": [{"codice": "1040", "importo": 280.0},
                    {"codice": "8906", "importo": 3.5},
                    {"codice": "1989", "importo": 0.4}],
        "data_pagamento": "2026-05-02",
    }]
    upd = _run(mod._riconcilia_ritenuta(db, dict(RIT)))
    assert upd["stato"] == "pagata_con_ravvedimento"
    assert upd["data_pagamento"] == "2026-05-02"


def test_f24_1040_tardivo_senza_ravvedimento():
    db = _Db()
    db["f24_unificato"].docs = [{
        "id": "F3", "tributi": [{"codice": "1040", "importo": 280.0}],
        "data_pagamento": "2026-05-02",
    }]
    upd = _run(mod._riconcilia_ritenuta(db, dict(RIT)))
    assert upd["stato"] == "pagata_in_ritardo_senza_ravvedimento"


def test_senza_f24_resta_da_pagare_o_scaduta():
    db = _Db()
    upd = _run(mod._riconcilia_ritenuta(db, {"importo": 280.0, "scadenza": "2099-01-16"}))
    assert upd["stato"] == "da_pagare" and upd["f24_id"] is None
    upd2 = _run(mod._riconcilia_ritenuta(db, {"importo": 280.0, "scadenza": "2020-01-16"}))
    assert upd2["stato"] == "scaduta_da_versare"


def test_f24_associato_ma_non_pagato():
    db = _Db()
    db["f24_unificato"].docs = [{"id": "F4", "tributi": [{"codice": "1040", "importo": 280.0}]}]
    upd = _run(mod._riconcilia_ritenuta(db, dict(RIT)))
    assert upd["stato"] == "f24_associato_da_pagare"
