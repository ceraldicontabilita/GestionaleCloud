import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi import lotto_acquaviva as la
from app.lotti.servizi import ordini_hotel as oh


def _db(monkeypatch, nome):
    db = AsyncMongoMockClient()[nome]
    monkeypatch.setattr(la, "db", db)
    monkeypatch.setattr(oh, "db", db)
    return db


def _fattura(numero, data, fornitore="Dolciaria Acquaviva S.p.A. sog. all'att. di dir. e coord. di Vandemoortele NV"):
    return {"id": f"f-{numero}", "numero_fattura": numero, "data_fattura": data, "fornitore": fornitore}


async def _carica(db, fatture):
    for f in fatture:
        await db.fatture.insert_one(dict(f))
    await db.fatture.insert_one({"id": "x", "numero_fattura": "1", "data_fattura": "01/10/2026", "fornitore": "Altro Srl"})


def test_numero_lotto_unisce_nome_giorno_e_fattura():
    assert la.numero_lotto("Croissant Vuoto", "2026-10-07", "8528027010") == "CROISSANT-VUOTO-20261007-8528027010"
    assert la.numero_lotto("Maritozzo à la crème", "2026-10-07", " 12 ") == "MARITOZZO-A-LA-CREME-20261007-12"
    assert la.data_iso("30/12/2025") == "2025-12-30" and la.data_iso("2025-12-02") == "2025-12-02" and la.data_iso("boh") == ""


def test_fattura_in_uso_parte_dall_ultima_poi_la_sceglie_il_titolare_in_ordine_fifo(monkeypatch):
    db = _db(monkeypatch, "lotto_acq_fifo")

    async def prova():
        await _carica(db, [_fattura("100", "10/09/2026"), _fattura("200", "23/09/2026"),
                           _fattura("100", "10/09/2026"),  # doppione della stessa fattura
                           _fattura("300", "01/10/2026", "VANDEMOORTELE EUROPE NV")])
        s = await la.stato_fattura_in_uso("2026-10-07")
        assert s["automatica"] is True and s["in_uso"]["numero_fattura"] == "300" and s["totale"] == 3
        # il giorno prima della terza fattura vale la seconda
        assert (await la.stato_fattura_in_uso("2026-09-30"))["in_uso"]["numero_fattura"] == "200"
        # il titolare torna indietro: la piu' vecchia ancora da usare
        s = await la.sposta_fattura_in_uso("precedente")
        s = await la.sposta_fattura_in_uso("precedente")
        assert s["in_uso"]["numero_fattura"] == "100" and s["automatica"] is False and s["precedente"] is None
        try:
            await la.sposta_fattura_in_uso("precedente")
            raise AssertionError("non doveva esistere una fattura piu' vecchia")
        except ValueError:
            pass
        s = await la.sposta_fattura_in_uso("successiva")
        assert s["in_uso"]["numero_fattura"] == "200"

    asyncio.run(prova())


def test_lotto_per_prodotto_e_idempotente_e_senza_fatture_non_si_inventa(monkeypatch):
    db = _db(monkeypatch, "lotto_acq_idem")

    async def prova():
        assert await la.lotto_per_prodotto("Croissant Vuoto", "2026-10-07") is None
        await _carica(db, [_fattura("8528027010", "23/09/2026")])
        a = await la.lotto_per_prodotto("Croissant Vuoto", "2026-10-07")
        b = await la.lotto_per_prodotto("Croissant Vuoto", "2026-10-07")
        assert a["lotto"]["numero_lotto"] == "CROISSANT-VUOTO-20261007-8528027010"
        assert a["lotto"]["id"] == b["lotto"]["id"]
        assert await db.lotti_fornitori.count_documents({"numero_lotto": a["lotto"]["numero_lotto"]}) == 1
        assert a["lotto"]["fattura_ref"] == "8528027010" and a["lotto"]["data_fattura"] == "23/09/2026"

    asyncio.run(prova())


def test_ordine_con_prodotto_acquaviva_nasce_con_il_lotto_associato(monkeypatch):
    db = _db(monkeypatch, "lotto_acq_ordine")

    async def prova():
        await _carica(db, [_fattura("8528027010", "23/09/2026")])
        await la.imposta_prodotto_acquaviva(152788, True)
        catalogo = {
            "menu:152788": {"chiave": "menu:152788", "nome": "Croissant Vuoto", "prezzo": 2.5},
            "menu:153816": {"chiave": "menu:153816", "nome": "Croissant & Brioche Mignon", "prezzo": 1.0},
        }
        righe = [{"chiave": "menu:152788", "quantita": 2}, {"chiave": "menu:153816", "quantita": 1}]
        ordine = await oh.crea_ordine(struttura_id="s", struttura_nome="Hotel", data_consegna="2026-10-07",
                                      catalogo=catalogo, righe=righe, ora_ritiro="07:00")
        acq, altro = ordine["righe"]
        assert acq["tracciabilita_stato"] == "lotto_associato" and acq["lotto_creato_automaticamente"] is True
        assert acq["lotti_associati"][0]["numero_lotto"] == "CROISSANT-VUOTO-20261007-8528027010"
        assert acq["fatture_origine"][0]["numero_fattura"] == "8528027010"
        assert altro["tracciabilita_stato"] == "origine_da_verificare" and not altro["lotti_associati"]
        # un secondo ordine dello stesso giorno riusa lo stesso lotto
        ordine2 = await oh.crea_ordine(struttura_id="s", struttura_nome="Hotel", data_consegna="2026-10-07",
                                       catalogo=catalogo, righe=righe[:1], ora_ritiro="07:00")
        assert ordine2["righe"][0]["lotti_associati"][0]["id"] == acq["lotti_associati"][0]["id"]
        assert await db.lotti_fornitori.count_documents({"origine": "automatico_acquaviva"}) == 1
        # tolto il segno Acquaviva, il prodotto torna da verificare
        await la.imposta_prodotto_acquaviva(152788, False)
        ordine3 = await oh.crea_ordine(struttura_id="s", struttura_nome="Hotel", data_consegna="2026-10-08",
                                       catalogo=catalogo, righe=righe[:1], ora_ritiro="07:00")
        assert ordine3["righe"][0]["tracciabilita_stato"] == "origine_da_verificare"

    asyncio.run(prova())


def test_prodotto_acquaviva_senza_fatture_resta_da_associare_con_il_motivo(monkeypatch):
    _db(monkeypatch, "lotto_acq_senza")

    async def prova():
        await la.imposta_prodotto_acquaviva(1, True)
        r = await oh._arricchisci_riga({"chiave": "menu:1", "nome": "Cornetto", "prezzo": 1}, 1, {}, "2026-10-07")
        assert r["tracciabilita_stato"] == "lotto_fornitore_da_associare" and not r["lotti_associati"]
        assert "nessuna fattura" in r["lotto_automatico_motivo"]

    asyncio.run(prova())
