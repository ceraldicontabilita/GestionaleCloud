"""Carta Nexi (richiesta utente 18/07/2026): le spese carta non arrivano mai
in estratto conto bancario, solo l'addebito mensile — quando appare, il
sistema controlla lo statement carta del periodo (mese precedente) e
segnala se manca o se la quadratura non torna."""
import asyncio

from app.services.nexi_carta import (
    _data,
    _norm_data,
    _periodo_addebito,
    importa_estratto_nexi_pdf,
    is_addebito_nexi,
    verifica_addebiti_nexi,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

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

    def find(self, q=None, proj=None):
        def _match(doc, cond):
            for k, v in (cond or {}).items():
                if k == "$and":
                    if not all(_match(doc, c) for c in v):
                        return False
                elif k == "$or":
                    if not any(_match(doc, c) for c in v):
                        return False
                elif isinstance(v, dict):
                    val = doc.get(k)
                    if "$gte" in v and not (val is not None and val >= v["$gte"]):
                        return False
                    if "$lte" in v and not (val is not None and val <= v["$lte"]):
                        return False
                else:
                    if doc.get(k) != v:
                        return False
            return True
        return _Cursor([d for d in self.docs if _match(d, q)])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, q, update):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(update.get("$set", {}))
                return


class _DB:
    def __init__(self):
        self._c = {}

    def __getitem__(self, name):
        return self._c.setdefault(name, _Coll())


def test_norm_data_riconosce_formato_italiano_legacy():
    """estratto_conto_movimenti ha righe più vecchie in GG/MM/AAAA (import
    legacy) accanto a quelle più recenti già ISO: trovato su prod il
    18/07/2026 (addebito Nexi del 16/03/2026 con periodo calcolato "")."""
    assert _norm_data("16/03/2026") == "2026-03-16"
    assert _norm_data("2026-03-16") == "2026-03-16"
    assert _data({"data_contabile": "16/03/2026"}) == "2026-03-16"


def test_periodo_addebito_da_data_italiana_non_e_vuoto():
    assert _periodo_addebito(_data({"data_contabile": "16/03/2026"})) == "2026-02"


def test_periodo_addebito_mese_precedente():
    assert _periodo_addebito("2026-04-05") == "2026-03"
    assert _periodo_addebito("2026-01-05") == "2025-12"


def test_is_addebito_nexi_riconosce_riga_banca_non_carta():
    riga_banca = {"tipo": "uscita", "descrizione_originale": "ADDEBITO SDD NEXI PAGAMENTI SPA"}
    assert is_addebito_nexi(riga_banca)
    riga_carta = {"tipo": "carta_credito", "banca": "Nexi", "descrizione": "AMAZON EU"}
    assert not is_addebito_nexi(riga_carta)
    riga_entrata = {"tipo": "entrata", "descrizione_originale": "ACCREDITO NEXI RIMBORSO"}
    assert not is_addebito_nexi(riga_entrata)


def test_verifica_segnala_estratto_mancante(monkeypatch):
    alert_calls = []

    async def fake_genera_alert(codice, entita_id, coll, dettaglio, db, extra=None):
        alert_calls.append(codice)
        return {"id": "a1"}

    async def fake_risolvi_alert(codice, entita_id, db, resolved_by="sistema"):
        return 0

    import app.services.alert_engine as alert_engine
    monkeypatch.setattr(alert_engine, "genera_alert", fake_genera_alert)
    monkeypatch.setattr(alert_engine, "risolvi_alert", fake_risolvi_alert)

    db = _DB()
    db["estratto_conto_movimenti"].docs.append({
        "id": "ec1", "data_contabile": "2026-04-05", "tipo": "uscita",
        "importo": 320.50, "descrizione_originale": "ADDEBITO SDD NEXI",
    })
    stats = _run(verifica_addebiti_nexi(db))
    assert stats["addebiti_trovati"] == 1
    assert stats["estratti_mancanti"] == 1
    assert "ESTRATTO_NEXI_MANCANTE" in alert_calls


def test_verifica_riconcilia_quando_quadra(monkeypatch):
    alert_calls = []

    async def fake_genera_alert(codice, entita_id, coll, dettaglio, db, extra=None):
        alert_calls.append(("genera", codice))
        return {"id": "a1"}

    async def fake_risolvi_alert(codice, entita_id, db, resolved_by="sistema"):
        alert_calls.append(("risolvi", codice))
        return 1

    import app.services.alert_engine as alert_engine
    monkeypatch.setattr(alert_engine, "genera_alert", fake_genera_alert)
    monkeypatch.setattr(alert_engine, "risolvi_alert", fake_risolvi_alert)

    db = _DB()
    db["estratto_conto_movimenti"].docs.append({
        "_id": "ec1", "id": "ec1", "data_contabile": "2026-04-05", "tipo": "uscita",
        "importo": 100.0, "descrizione_originale": "ADDEBITO SDD NEXI",
    })
    # Un rimborso (importo negativo, es. reso Amazon) deve SOTTRARSI dal
    # totale carta, non sommarsi in valore assoluto: 60 + 50 - 10 = 100,
    # non 60 + 50 + 10 = 120 (bug 18/07/2026, visto sul primo estratto
    # Nexi reale caricato dall'utente: rimborsi gonfiavano il totale carta
    # e la quadratura con l'addebito bancario non tornava mai).
    db["estratto_conto_movimenti"].docs.extend([
        {"tipo": "carta_credito", "banca": "Nexi", "data": "2026-03-10", "importo": 60.0},
        {"tipo": "carta_credito", "banca": "Nexi", "data": "2026-03-15", "importo": -10.0},
        {"tipo": "carta_credito", "banca": "Nexi", "data": "2026-03-20", "importo": 50.0},
    ])
    stats = _run(verifica_addebiti_nexi(db))
    assert stats["riconciliati"] == 1
    assert stats["non_quadrano"] == 0
    assert ("genera", "NEXI_ADDEBITO_NON_QUADRA") not in alert_calls


def test_importa_pdf_totale_importo_e_netto(monkeypatch):
    """totale_importo deve essere il netto (addebiti - rimborsi), non la
    somma dei valori assoluti — stesso bug del calcolo di verifica."""
    import app.services.nexi_carta as mod

    def fake_parse(pdf_content):
        return {
            "success": True,
            "metadata": {},
            "transazioni": [
                {"data": "2026-01-05", "descrizione": "Fornitore", "importo": 100.0, "categoria": "Altro"},
                {"data": "2026-01-10", "descrizione": "Reso Amazon", "importo": -20.0, "categoria": "E-commerce Amazon"},
            ],
        }

    monkeypatch.setattr(
        "app.parsers.estratto_conto_nexi_parser.parse_estratto_conto_nexi", fake_parse
    )
    db = _DB()
    res = _run(importa_estratto_nexi_pdf(db, "estratto.pdf", b"%PDF-fake"))
    assert res["success"] is True
    assert res["totale_importo"] == 80.0


def test_verifica_segnala_non_quadra(monkeypatch):
    alert_calls = []

    async def fake_genera_alert(codice, entita_id, coll, dettaglio, db, extra=None):
        alert_calls.append(codice)
        return {"id": "a1"}

    async def fake_risolvi_alert(codice, entita_id, db, resolved_by="sistema"):
        return 0

    import app.services.alert_engine as alert_engine
    monkeypatch.setattr(alert_engine, "genera_alert", fake_genera_alert)
    monkeypatch.setattr(alert_engine, "risolvi_alert", fake_risolvi_alert)

    db = _DB()
    db["estratto_conto_movimenti"].docs.append({
        "id": "ec1", "data_contabile": "2026-04-05", "tipo": "uscita",
        "importo": 100.0, "descrizione_originale": "ADDEBITO SDD NEXI",
    })
    db["estratto_conto_movimenti"].docs.append(
        {"tipo": "carta_credito", "banca": "Nexi", "data": "2026-03-10", "importo": 50.0},
    )
    stats = _run(verifica_addebiti_nexi(db))
    assert stats["non_quadrano"] == 1
    assert "NEXI_ADDEBITO_NON_QUADRA" in alert_calls
