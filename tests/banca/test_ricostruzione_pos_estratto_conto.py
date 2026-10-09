"""NUMIA non ha API: la chiusura del giorno si ricostruisce dalla banca.

La regola del titolare (19/09/2026): «vanno sommati con la data di accredito
dell'estratto conto, in descrizione c'e' un incasso del giorno; sommati tutti
gli importi dello stesso giorno dovranno quadrare con la registrazione XML
pagamento elettronico». Misurato sul 2026: su 30 giornate in cui NUMIA e'
l'unico circuito, la somma per giorno operativo e l'elettronico dell'XML
coincidono **al centesimo**.

Senza questa ricostruzione 180 giornate su 183 restano
`attende_chiusura_pos_reale` e 888 accrediti per 342.087,35 EUR non hanno
nessun trasferimento da riconciliare.
"""
import asyncio

import pytest

from app.services import conti_pos, ricostruzione_pos_estratto_conto as ricostruzione
from app.services.scritture_contabili import (
    FONTE_ESTRATTO_CONTO,
    PRIORITA_FONTE,
    FONTE_API,
    FONTE_MANUALE,
    FONTE_TERMINALE,
    metadati_fonte_pos,
)


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class _Cursore:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield dict(d)
        return gen()


class _Db:
    def __init__(self, movimenti=None, chiusure=None):
        self._dati = {
            "estratto_conto_movimenti": movimenti or [],
            "chiusure_pos_manuali": chiusure or [],
        }
        self.letture = {}

    def __getitem__(self, nome):
        db = self

        class _Coll:
            def find(self, query=None, proj=None):
                db.letture[nome] = db.letture.get(nome, 0) + 1
                return _Cursore(db._dati.get(nome, []))
        return _Coll()


def _accredito(importo, giorno="14/08/26", data="2026-08-17", pdv="00011",
               circuito="NUMIA-INTER"):
    return {
        "id": f"ec-{circuito}-{pdv}-{importo}",
        "data": data, "importo": importo,
        "descrizione_originale": (
            f"INC.POS CARTE CREDIT - {circuito} DEL {giorno} "
            f"PDV 3757283/{pdv} CERALDI CAFFE NA"
        ),
    }


# ── La somma per giorno operativo ─────────────────────────────────────────

def test_somma_gli_accrediti_del_giorno_di_vendita():
    """14/08/2026, caso reale: quattro accrediti, due circuiti, due terminali."""
    db = _Db([
        _accredito(412.20), _accredito(68.00, pdv="00012"),
        _accredito(23.10, pdv="00012", circuito="NUMIA-BNCMT"),
        _accredito(2.60, circuito="NUMIA-AMEX"),
    ])

    incassi = _run(ricostruzione.incassi_numia_per_giorno_vendita(db))

    assert incassi == {"2026-08-14": {"importo": 505.90, "accrediti": 4}}


def test_conta_il_giorno_della_causale_non_quello_dell_accredito():
    db = _Db([_accredito(100.0, giorno="14/08/26", data="2026-08-17")])

    assert list(_run(ricostruzione.incassi_numia_per_giorno_vendita(db))) == [
        "2026-08-14"]


def test_uno_storno_si_sottrae_dall_incasso_del_giorno():
    """Un rimborso arriva sulla stessa causale con segno meno: ignorarlo
    gonfierebbe l'incasso dichiarato al POS."""
    db = _Db([_accredito(412.20), _accredito(-12.20, pdv="00099")])

    incassi = _run(ricostruzione.incassi_numia_per_giorno_vendita(db))

    assert incassi["2026-08-14"]["importo"] == 400.00


def test_il_filtro_per_anno_non_prende_gli_altri():
    db = _Db([_accredito(10.0, giorno="14/08/26"),
              _accredito(20.0, giorno="14/08/25", pdv="00012")])

    incassi = _run(ricostruzione.incassi_numia_per_giorno_vendita(db, anno="2026"))

    assert list(incassi) == ["2026-08-14"]


@pytest.mark.parametrize("descrizione", [
    "COMMISSIONI SU INCASSI POS NUMIA",
    "BONIFICO A FORNITORE NUMIA SRL",
    "INC.POS CARTE CREDIT - NUMIA-INTER PDV 123",
])
def test_cosa_non_e_un_accredito_giornaliero(descrizione):
    db = _Db([{"id": "x", "data": "2026-08-17", "importo": 50.0,
               "descrizione_originale": descrizione}])

    assert _run(ricostruzione.incassi_numia_per_giorno_vendita(db)) == {}


def test_legge_la_descrizione_anche_quando_l_originale_manca():
    """Su 2.017 movimenti solo 160 hanno `descrizione_originale`: leggere
    soltanto quella perderebbe in silenzio quasi tutti gli accrediti."""
    db = _Db([{"id": "x", "data": "2026-08-17", "importo": 99.0,
               "descrizione": "INC.POS CARTE CREDIT - NUMIA-INTER DEL 14/08/26 PDV 1"}])

    incassi = _run(ricostruzione.incassi_numia_per_giorno_vendita(db))

    assert incassi["2026-08-14"]["importo"] == 99.0


# ── Cosa si ricostruisce e cosa si salta ──────────────────────────────────

def test_in_dry_run_conta_e_non_scrive(monkeypatch):
    scritte = []
    monkeypatch.setattr(ricostruzione, "registra_chiusura_pos_reale",
                        lambda *a, **k: scritte.append(a))

    db = _Db([_accredito(412.20)])
    esito = _run(ricostruzione.ricostruisci_chiusure_numia(db, dry_run=True))

    assert esito["giorni_da_ricostruire"] == 1
    assert esito["importo_da_ricostruire"] == 412.20
    assert esito["scritti"] == 0 and scritte == []


def test_scrive_la_chiusura_col_totale_del_giorno(monkeypatch):
    scritte = []

    async def _spia(db, data, importo, **k):
        scritte.append((data, importo, k.get("gestore"), k.get("fonte")))

    monkeypatch.setattr(ricostruzione, "registra_chiusura_pos_reale", _spia)

    db = _Db([_accredito(412.20), _accredito(68.00, pdv="00012")])
    esito = _run(ricostruzione.ricostruisci_chiusure_numia(db, dry_run=False))

    assert esito["scritti"] == 1
    assert scritte == [("2026-08-14", 480.20, conti_pos.NUMIA, FONTE_ESTRATTO_CONTO)]


def test_un_giorno_gia_coperto_non_si_riscrive(monkeypatch):
    """Idempotente: ripassarlo non deve creare una seconda chiusura."""
    scritte = []
    monkeypatch.setattr(ricostruzione, "registra_chiusura_pos_reale",
                        lambda *a, **k: scritte.append(a))

    db = _Db([_accredito(412.20)],
             chiusure=[{"data": "2026-08-14", "gestore": "numia",
                        "fonte_dato": "manuale"}])
    esito = _run(ricostruzione.ricostruisci_chiusure_numia(db, dry_run=False))

    assert esito["giorni_gia_coperti"] == 1 and esito["scritti"] == 0
    assert scritte == []


def test_una_chiusura_sumup_non_copre_il_giorno_numia(monkeypatch):
    """SumUp e NUMIA hanno due chiusure distinte: la presenza dell'una non
    puo' far saltare l'altra, o resterebbe il buco che si sta chiudendo."""
    scritte = []

    async def _spia(db, data, importo, **k):
        scritte.append(data)

    monkeypatch.setattr(ricostruzione, "registra_chiusura_pos_reale", _spia)

    db = _Db([_accredito(412.20)],
             chiusure=[{"data": "2026-08-14", "gestore": "sumup",
                        "fonte_dato": "api"}])
    esito = _run(ricostruzione.ricostruisci_chiusure_numia(db, dry_run=False))

    assert esito["scritti"] == 1 and scritte == ["2026-08-14"]


def test_un_giorno_di_soli_storni_non_diventa_una_chiusura(monkeypatch):
    """Un incasso negativo non esiste: meglio dichiararlo saltato che
    scrivere una chiusura che `registra_chiusura_pos_reale` rifiuta."""
    monkeypatch.setattr(ricostruzione, "registra_chiusura_pos_reale",
                        lambda *a, **k: pytest.fail("non deve scrivere"))

    db = _Db([_accredito(-30.0)])
    esito = _run(ricostruzione.ricostruisci_chiusure_numia(db, dry_run=False))

    assert esito["giorni_da_ricostruire"] == 0
    assert esito["giorni_saltati_senza_incasso"] == ["2026-08-14"]


def test_un_errore_su_un_giorno_non_ferma_gli_altri(monkeypatch):
    async def _forse_esplode(db, data, importo, **k):
        if data == "2026-08-14":
            raise ValueError("data rifiutata")

    monkeypatch.setattr(ricostruzione, "registra_chiusura_pos_reale", _forse_esplode)

    db = _Db([_accredito(412.20, giorno="14/08/26"),
              _accredito(99.0, giorno="15/08/26", pdv="00012")])
    esito = _run(ricostruzione.ricostruisci_chiusure_numia(db, dry_run=False))

    assert esito["scritti"] == 1 and esito["errori"] == 1
    assert "2026-08-14" in esito["motivi_errore"][0]


def test_legge_ogni_collezione_una_volta_sola():
    db = _Db([_accredito(10.0 + i, pdv=f"{i:05d}") for i in range(30)],
             chiusure=[{"data": "2026-08-14", "gestore": "numia"}])

    _run(ricostruzione.ricostruisci_chiusure_numia(db, dry_run=True))

    assert db.letture == {"estratto_conto_movimenti": 1, "chiusure_pos_manuali": 1}


# ── La fonte nuova sta al posto giusto nella scala ────────────────────────

def test_l_estratto_conto_non_sovrascrive_terminale_ne_api():
    """Il denaro in banca e' solido, ma il terminale vede resi e storni prima
    che la banca li compensi: sotto di lui, e sotto l'API."""
    assert PRIORITA_FONTE[FONTE_ESTRATTO_CONTO] < PRIORITA_FONTE[FONTE_TERMINALE]
    assert PRIORITA_FONTE[FONTE_ESTRATTO_CONTO] < PRIORITA_FONTE[FONTE_API]


def test_l_estratto_conto_batte_il_numero_digitato_a_mano():
    assert PRIORITA_FONTE[FONTE_ESTRATTO_CONTO] > PRIORITA_FONTE[FONTE_MANUALE]


def test_la_fonte_si_riconosce_dai_metadati():
    """Senza una `source` sua, la ricostruzione si confonderebbe con una
    chiusura digitata e non si potrebbe piu' rifare ne' disfare."""
    meta = metadati_fonte_pos(FONTE_ESTRATTO_CONTO, conti_pos.NUMIA)

    assert meta["source"] == "ricostruzione_estratto_conto"
    assert meta["quota_pos_fonte"] == "accrediti_estratto_conto"
    assert meta["expectation_owner"] == "numia_bank_statement"


def test_una_fonte_sconosciuta_resta_manuale():
    """Controprova: senza la voce nuova la ricostruzione sarebbe caduta qui,
    cioe' nella fonte piu' forte, sovrascrivendo le chiusure vere."""
    assert metadati_fonte_pos("inventata", conti_pos.NUMIA)["source"] == (
        "inserimento_manuale_terminale")
