"""Una fattura mai passata dal motore IVA non deve sparire dal riepilogo.

Il riepilogo annuale (`_fatture_anno`, §16) univa due rami: le fatture con
`periodo_iva_attribuito` dell'anno, e quelle con periodo nullo ma stato
`DA_VERIFICARE`. Una fattura che non e' MAI passata dal motore ha **entrambi**
i campi assenti: niente periodo e niente stato. Non rientrava nel primo ramo
ne' nel secondo, quindi non compariva da nessuna parte.

Misurato in produzione il 19/09/2026: **366 fatture attive** in quello stato,
per **28.742,08 EUR** di IVA, tutte con data entro il 20/05/2026 — contro 574
regolarmente attribuite. Non erano zero euro nascosti in un angolo: erano
l'IVA di un anno e mezzo di acquisti che il riepilogo non contava.

Lo stato assente vale come «da verificare»: e' il caso piu' da verificare di
tutti, non uno da nascondere.
"""
import asyncio
import re

import pytest

from app.routers import iva as mod


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def _corrisponde(doc, query):
    """Valutazione minima del filtro: $or, $in, $regex e uguaglianza."""
    if "$or" in query:
        rami = query["$or"]
        resto = {k: v for k, v in query.items() if k != "$or"}
        return any(_corrisponde(doc, r) for r in rami) and (
            not resto or _corrisponde(doc, resto)
        )
    for campo, atteso in query.items():
        valore = doc.get(campo)
        if isinstance(atteso, dict):
            if "$in" in atteso and valore not in atteso["$in"]:
                return False
            if "$regex" in atteso and not re.match(atteso["$regex"], str(valore or "")):
                return False
        elif valore != atteso:
            return False
    return True


class _Cursore:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n):
        return self._docs


class _Collection:
    def __init__(self, docs):
        self._docs = docs
        self.query_ricevuta = None

    def find(self, query, proj=None):
        self.query_ricevuta = query
        return _Cursore([d for d in self._docs if _corrisponde(d, query)])


class _Db:
    def __init__(self, docs):
        self.coll = _Collection(docs)

    def __getitem__(self, nome):
        return self.coll


MAI_CLASSIFICATA = {
    "id": "f-mai", "iva": 1000.0,
    "data_documento": "2026-03-14",
    # nessun periodo_iva_attribuito, nessuno stato_detrazione_iva
}
DA_VERIFICARE_SENZA_PERIODO = {
    "id": "f-dv", "iva": 500.0,
    "data_documento": "2026-04-02",
    "stato_detrazione_iva": "DA_VERIFICARE",
}
ATTRIBUITA = {
    "id": "f-ok", "iva": 200.0,
    "data_documento": "2026-05-09",
    "periodo_iva_attribuito": "2026-05",
    "stato_detrazione_iva": "DA_VERIFICARE",
}
ALTRO_ANNO = {
    "id": "f-2024", "iva": 900.0,
    "data_documento": "2024-07-01",
}


def test_la_fattura_mai_classificata_entra_nel_riepilogo():
    db = _Db([MAI_CLASSIFICATA, DA_VERIFICARE_SENZA_PERIODO, ATTRIBUITA, ALTRO_ANNO])

    trovate = {f["id"] for f in _run(mod._fatture_anno(db, 2026))}

    assert "f-mai" in trovate, (
        "Una fattura senza periodo E senza stato non rientrava in nessuno dei "
        "due rami: spariva dal riepilogo annuale invece di finire fra quelle "
        "da verificare."
    )


def test_il_riepilogo_continua_a_prendere_gli_altri_casi():
    db = _Db([MAI_CLASSIFICATA, DA_VERIFICARE_SENZA_PERIODO, ATTRIBUITA, ALTRO_ANNO])

    trovate = {f["id"] for f in _run(mod._fatture_anno(db, 2026))}

    assert {"f-dv", "f-ok"} <= trovate


def test_non_pesca_le_fatture_di_un_altro_anno():
    """Allargare il ramo non deve tirare dentro anni che non c'entrano."""
    db = _Db([MAI_CLASSIFICATA, ALTRO_ANNO])

    trovate = {f["id"] for f in _run(mod._fatture_anno(db, 2026))}

    assert "f-2024" not in trovate


@pytest.mark.parametrize("stato", [None, ""])
def test_stato_assente_o_vuoto_valgono_come_da_verificare(stato):
    doc = dict(MAI_CLASSIFICATA, id="f-x")
    if stato is not None:
        doc["stato_detrazione_iva"] = stato
    db = _Db([doc])

    assert {f["id"] for f in _run(mod._fatture_anno(db, 2026))} == {"f-x"}
