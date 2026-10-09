"""15/09/2026: importando l'archivio storico dei cedolini, una busta del 2021
con dicitura di cessazione marcava cessata oggi una persona riassunta (buste
fino al 2026). La cessazione automatica vale solo se non esiste una busta
successiva della stessa persona (registro gestionale o deposito HR)."""
import asyncio

import pytest

from app.services import cessazione_da_cedolino as guardia
from app.services import salari_unificati_v2 as v2


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, n):
        return self

    async def to_list(self, n=None):
        return list(self._docs)


class _Coll:
    def __init__(self):
        self.docs = []
        self.updates = []

    def _match(self, q):
        return [d for d in self.docs if all(d.get(k) == v for k, v in (q or {}).items())]

    async def find_one(self, q=None, *a, **k):
        m = self._match(q)
        return dict(m[0]) if m else None

    def find(self, q=None, *a, **k):
        return _Cursor([dict(d) for d in self._match(q)])

    async def insert_one(self, doc, *a, **k):
        self.docs.append(dict(doc))

    async def update_one(self, q, upd, *a, **k):
        self.updates.append((q, upd))
        for d in self._match(q):
            d.update(upd.get("$set", {}))


class _Db:
    def __init__(self):
        self.c = {}

    def __getitem__(self, n):
        return self.c.setdefault(n, _Coll())


def test_busta_piu_recente_confronta_per_persona():
    docs = [
        {"codice_fiscale": "CRTNNL96P52F839M", "anno": 2026, "mese": 5},
        {"codice_fiscale": "ALTRO", "anno": 2027, "mese": 1},
        {"dipendente_id": "x", "anno": "2021", "mese": "1"},
    ]
    assert guardia.busta_piu_recente(docs, (2021, 1), codice_fiscale="crtnnl96p52f839m") == "2026-05"
    assert guardia.busta_piu_recente(docs, (2026, 5), codice_fiscale="CRTNNL96P52F839M") is None
    assert guardia.busta_piu_recente(docs, (2020, 12), dipendente_id="x") == "2021-01"


@pytest.fixture
def pipeline(monkeypatch):
    eventi = []

    async def _prop(tipo, payload, db, **k):
        eventi.append(str(tipo))
        return {}

    async def _no(*a, **k):
        return False

    monkeypatch.setattr("app.services.event_bus.propagate_event", _prop)
    monkeypatch.setattr("app.services.cedolini_manager.riconcilia_stipendio_automatico", _no)
    monkeypatch.setattr("app.services.hr_cedolini_deposito.dsn_hr", lambda: None)
    db = _Db()
    _run(db["dipendenti"].insert_one({"id": "dip-1", "codice_fiscale": "CRTNNL96P52F839M",
                                      "nome": "Antonella", "cognome": "Carotenuto", "attivo": True}))
    return db, eventi


def _busta(anno, mese):
    return {"codice_fiscale": "CRTNNL96P52F839M", "nome_dipendente": "Carotenuto Antonella",
            "anno": anno, "mese": mese, "netto": 900.0, "lordo": 1200.0,
            "cessato": True, "cessazione_diciture": ["NOME + DATA CESSAZIONE (TeamSystem)"],
            "data_cessazione_rilevata": f"{anno}-{mese:02d}-15"}


def test_busta_storica_non_cessa_chi_ha_buste_successive(pipeline):
    db, eventi = pipeline
    _run(db["cedolini"].insert_one({"codice_fiscale": "CRTNNL96P52F839M", "dipendente_id": "dip-1",
                                    "anno": 2026, "mese": 5}))
    esito = _run(v2.processa_cedolino_v2(db, _busta(2021, 1), pdf_text=""))
    assert esito["success"] is True
    assert esito.get("cessazione_storica_ignorata") == "2026-05"
    assert not esito.get("cessato_auto")
    dip = _run(db["dipendenti"].find_one({"id": "dip-1"}))
    assert dip["attivo"] is True and not dip.get("data_cessazione")
    assert "dipendente.cessato" not in eventi


def test_ultima_busta_cessa_davvero(pipeline):
    db, eventi = pipeline
    esito = _run(v2.processa_cedolino_v2(db, _busta(2026, 7), pdf_text=""))
    assert esito.get("cessato_auto") is True
    dip = _run(db["dipendenti"].find_one({"id": "dip-1"}))
    assert dip["attivo"] is False and dip["data_cessazione"] == "2026-07-15"
    assert "dipendente.cessato" in eventi


def test_guardia_legge_anche_il_deposito_hr(monkeypatch):
    class _Con:
        async def fetchrow(self, sql, cf):
            assert cf == "CRTNNL96P52F839M"
            return {"ultima": "2026-07"}

        async def close(self):
            pass

    async def _conn(dsn):
        return _Con()

    monkeypatch.setattr("app.services.hr_cedolini_deposito.dsn_hr", lambda: "postgres://x")
    monkeypatch.setattr("app.services.hr_cedolini_deposito.connetti_hr", _conn)
    db = _Db()
    out = _run(guardia.busta_successiva(db, dipendente_id="dip-1", codice_fiscale="crtnnl96p52f839m",
                                        anno=2021, mese=1))
    assert out == "2026-07"
    assert _run(guardia.busta_successiva(db, codice_fiscale="crtnnl96p52f839m", anno=2026, mese=7)) is None


def test_riallineamento_segue_l_anagrafica_hr(monkeypatch):
    hr = {
        "CRTNNL96P52F839M": {"stato": "attivo", "attivo": True},
        "DLMVCN59E09F839T": {"stato": "cessato", "attivo": False, "data_cessazione": "2024-06-13"},
    }

    class _Con:
        async def fetch(self, sql, cf):
            return [{"doc": hr[cf]}] if cf in hr else []

        async def close(self):
            pass

    async def _conn(dsn):
        return _Con()

    monkeypatch.setattr("app.services.hr_cedolini_deposito.dsn_hr", lambda: "postgres://x")
    monkeypatch.setattr("app.services.hr_cedolini_deposito.connetti_hr", _conn)
    db = _Db()
    for d in [
        {"id": "car", "cognome": "CAROTENUTO", "nome": "ANTONELLA", "codice_fiscale": "CRTNNL96P52F839M",
         "attivo": False, "in_carico": False, "data_cessazione": "2022-07-12",
         "cessato_automaticamente": True, "cessazione_source": "cedolino_auto_v2"},
        {"id": "dal", "cognome": "D'ALMA", "nome": "VINCENZO", "codice_fiscale": "DLMVCN59E09F839T",
         "attivo": False, "in_carico": False, "data_cessazione": "2020-09-04",
         "cessato_automaticamente": True, "cessazione_source": "cedolino_auto_v2"},
        {"id": "man", "cognome": "ROSSI", "nome": "MARIO", "codice_fiscale": "RSSMRA80A01H501U",
         "attivo": False, "data_cessazione": "2023-01-31"},  # cessato a mano: mai toccato
        {"id": "ign", "cognome": "IGNOTO", "nome": "X", "codice_fiscale": "IGNXXX00A01H501Z",
         "attivo": False, "data_cessazione": "2019-01-31", "cessato_automaticamente": True},
    ]:
        _run(db["dipendenti"].insert_one(d))
    out = _run(guardia.riallinea_cessazioni_automatiche(db))
    assert (out["esaminati"], out["riattivati"], out["date_corrette"], out["senza_hr"]) == (3, 1, 1, 1)
    car = _run(db["dipendenti"].find_one({"id": "car"}))
    assert car["attivo"] is True and car["in_carico"] is True and not car["data_cessazione"]
    dal = _run(db["dipendenti"].find_one({"id": "dal"}))
    assert dal["data_cessazione"] == "2024-06-13" and dal["attivo"] is False
    man = _run(db["dipendenti"].find_one({"id": "man"}))
    assert man["data_cessazione"] == "2023-01-31"
    # secondo giro: niente da fare
    out2 = _run(guardia.riallinea_cessazioni_automatiche(db))
    assert out2["riattivati"] == 0 and out2["date_corrette"] == 0
