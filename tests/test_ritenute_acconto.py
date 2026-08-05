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


def test_estrazione_dati_ritenuta_isola_il_body_giusto_in_file_raggruppato():
    """Review Codex su PR #71 (5° giro): un file FatturaPA raggruppato
    condivide lo stesso xml_raw fra più fatture (xml_body_index). Se solo
    la PRIMA fattura ha una ritenuta, la SECONDA (senza ritenuta) non deve
    ereditarla — bug reale: senza isolare il body giusto, il regex trovava
    sempre e solo il primo <DatiRitenuta> del file, indipendentemente da
    quale fattura si stesse processando."""
    xml_raggruppato = (
        "<FatturaElettronica>"
        "<FatturaElettronicaBody><DatiGeneraliDocumento><Numero>20</Numero>"
        "<DatiRitenuta><TipoRitenuta>RT01</TipoRitenuta><ImportoRitenuta>280.00</ImportoRitenuta>"
        "<AliquotaRitenuta>20.00</AliquotaRitenuta><CausalePagamento>A</CausalePagamento></DatiRitenuta>"
        "</DatiGeneraliDocumento></FatturaElettronicaBody>"
        "<FatturaElettronicaBody><DatiGeneraliDocumento><Numero>21</Numero>"
        "</DatiGeneraliDocumento></FatturaElettronicaBody>"
        "</FatturaElettronica>"
    )

    d0 = mod._estrai_dati_ritenuta(xml_raggruppato, 0)
    assert d0 == {"tipo": "RT01", "importo": 280.0, "aliquota": "20.00", "causale": "A"}

    d1 = mod._estrai_dati_ritenuta(xml_raggruppato, 1)
    assert d1 is None


def test_estrazione_dati_ritenuta_isola_il_body_giusto_con_prefisso_namespace():
    """Review Codex su PR #71 (6° giro): xml_raw è il testo ORIGINALE non
    ripulito dai prefissi di namespace (a differenza della copia di lavoro
    interna del parser) — un file con <p:FatturaElettronicaBody> deve
    essere isolato correttamente quanto uno senza prefisso."""
    xml_raggruppato = (
        '<p:FatturaElettronica xmlns:p="ns">'
        "<p:FatturaElettronicaBody><DatiGeneraliDocumento><Numero>20</Numero>"
        "<DatiRitenuta><TipoRitenuta>RT01</TipoRitenuta><ImportoRitenuta>280.00</ImportoRitenuta>"
        "<AliquotaRitenuta>20.00</AliquotaRitenuta><CausalePagamento>A</CausalePagamento></DatiRitenuta>"
        "</DatiGeneraliDocumento></p:FatturaElettronicaBody>"
        "<p:FatturaElettronicaBody><DatiGeneraliDocumento><Numero>21</Numero>"
        "</DatiGeneraliDocumento></p:FatturaElettronicaBody>"
        "</p:FatturaElettronica>"
    )

    assert mod._estrai_dati_ritenuta(xml_raggruppato, 0) is not None
    assert mod._estrai_dati_ritenuta(xml_raggruppato, 1) is None


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
        "movimento_bancario_id": "ec-1",
        "data_pagamento_effettivo": "2026-04-16",
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
        "movimento_bancario_id": "ec-2",
        "data_pagamento_effettivo": "2026-05-02",
    }]
    upd = _run(mod._riconcilia_ritenuta(db, dict(RIT)))
    assert upd["stato"] == "pagata_con_ravvedimento"
    assert upd["data_pagamento"] == "2026-05-02"


def test_f24_1040_tardivo_senza_ravvedimento():
    db = _Db()
    db["f24_unificato"].docs = [{
        "id": "F3", "tributi": [{"codice": "1040", "importo": 280.0}],
        "movimento_bancario_id": "ec-3",
        "data_pagamento_effettivo": "2026-05-02",
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


def test_f24_con_sola_quietanza_non_chiude_la_ritenuta():
    db = _Db()
    db["f24_unificato"].docs = [{
        "id": "F5", "tributi": [{"codice": "1040", "importo": 280.0}],
        "quietanza_id": "q-1", "data_pagamento_quietanza": "2026-04-16",
    }]
    upd = _run(mod._riconcilia_ritenuta(db, dict(RIT)))
    assert upd["stato"] == "f24_associato_da_pagare"


def test_f24_multi_tributo_associa_solo_riga_1040_aggregata_del_periodo():
    db = _Db()
    r1 = {"id": "r1", "importo": 280.0, "periodo_ritenuta": "2026-03", "scadenza": "2026-04-16"}
    r2 = {"id": "r2", "importo": 210.0, "periodo_ritenuta": "2026-03", "scadenza": "2026-04-16"}
    f24 = {
        "id": "F-MULTI",
        "sezione_erario": {"righe": [
            {"codice_tributo": "1040", "periodo_riferimento": "03/2026", "importo_debito": "490,00"},
            {"codice_tributo": "6003", "periodo_riferimento": "03/2026", "importo_debito": "1.250,00"},
        ]},
    }
    upd = _run(mod._riconcilia_ritenuta(
        db, r1, ritenute_periodo=[r1, r2], f24_docs=[f24]
    ))
    assert upd["f24_id"] == "F-MULTI"
    assert upd["f24_associazione_tipo"] == "aggregata"
    assert upd["f24_importo_tributo"] == 490.0
    assert upd["f24_quota_ritenuta"] == 280.0
    assert upd["f24_multi_tributo"] is True
    assert upd["stato"] == "f24_associato_da_pagare"


def test_due_f24_equivalenti_restano_ambigui():
    db = _Db()
    rit = {"importo": 280.0, "periodo_ritenuta": "2026-03", "scadenza": "2026-04-16"}
    docs = [
        {"id": "F-A", "sezione_erario": [{"codice_tributo": "1040", "mese": "03", "anno": "2026", "importo_debito": 280}]},
        {"id": "F-B", "sezione_erario": [{"codice_tributo": "1040", "mese": "03", "anno": "2026", "importo_debito": 280}]},
    ]
    upd = _run(mod._riconcilia_ritenuta(db, rit, ritenute_periodo=[rit], f24_docs=docs))
    assert upd["stato"] == "da_verificare_associazione_f24"
    assert upd["f24_id"] is None
    assert upd["f24_candidati"] == ["F-A", "F-B"]
