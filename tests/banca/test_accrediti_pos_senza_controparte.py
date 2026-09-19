"""Un accredito POS senza trasferimento del suo giorno va detto, non nascosto.

La regola del titolare, confermata dai dati: NUMIA accredita separatamente
bancomat, carte e Amex, anche da terminali (PDV) diversi, e la
riconciliazione certa e' la **somma degli accrediti dello stesso giorno
operativo** (`DEL gg/mm/aa`) contro il trasferimento POS di quel giorno. Sul
2026, su 183 giorni, l'elettronico dichiarato negli XML e gli accrediti NUMIA
sommati per giorno di vendita coincidono al 94,3%.

`riconcilia_accredito_pos_ec` la somma gia' correttamente. Il punto cieco era
un altro: senza il trasferimento di quel giorno l'accredito esce con
`tipo_riconciliazione = "evidenza_senza_attesa"` e la coda «in attesa
documento» mostra «nessun documento con importo al centesimo e identita
univoca» — un messaggio che fa sembrare rotto il confronto sugli importi
quando invece manca proprio la controparte.

Misurato il 19/09/2026: **888 accrediti NUMIA per 342.087,35 EUR** in quello
stato, nessuno riconciliato, perche' in `prima_nota_banca` non esiste nemmeno
un `trasferimento_pos` del circuito NUMIA.
"""
import asyncio

import pytest

from app.services.collaudo_invarianti import (
    CHECKS,
    check_accrediti_pos_senza_controparte,
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
    def __init__(self, movimenti=None, trasferimenti=None):
        self._dati = {
            "estratto_conto_movimenti": movimenti or [],
            "prima_nota_banca": trasferimenti or [],
        }
        self.letture = {}

    def __getitem__(self, nome):
        db = self

        class _Coll:
            def find(self, query=None, proj=None):
                db.letture[nome] = db.letture.get(nome, 0) + 1
                return _Cursore(db._dati.get(nome, []))
        return _Coll()


def _accredito(importo, giorno="13/08/26", data="2026-08-14", pdv="00011",
               circuito="NUMIA-INTER", **extra):
    return {
        "id": f"ec-{importo}-{pdv}",
        "data": data,
        "importo": importo,
        "descrizione_originale": (
            f"INC.POS CARTE CREDIT - {circuito} DEL {giorno} "
            f"PDV 3757283/{pdv} CERALDI CAFFE NA"
        ),
        **extra,
    }


def _trasferimento(giorno_vendita):
    return {"source": "trasferimento_pos", "giorno_vendita": giorno_vendita}


# ── Il caso reale dello screenshot ────────────────────────────────────────

def test_gli_accrediti_dello_stesso_giorno_si_sommano():
    """14/08/2026: quattro accrediti, due circuiti, due terminali."""
    db = _Db(movimenti=[
        _accredito(412.20, giorno="14/08/26", data="2026-08-17", pdv="00011"),
        _accredito(68.00, giorno="14/08/26", data="2026-08-17", pdv="00012"),
        _accredito(23.10, giorno="14/08/26", data="2026-08-17", pdv="00012",
                   circuito="NUMIA-BNCMT"),
        _accredito(2.60, giorno="14/08/26", data="2026-08-17", pdv="00011",
                   circuito="NUMIA-AMEX"),
    ])

    esito = _run(check_accrediti_pos_senza_controparte(db))

    assert esito["violazioni"] == 1, "un solo giorno di vendita, non quattro righe"
    assert esito["esempi"][0] == {
        "giorno_vendita": "2026-08-14", "accrediti": 4, "importo": 505.90,
    }


def test_la_data_che_conta_e_quella_della_causale_non_quella_dell_accredito():
    """Accrediti arrivati il 17/08 ma relativi al 14/08 stanno sul 14/08."""
    db = _Db(movimenti=[_accredito(100.0, giorno="14/08/26", data="2026-08-17")])

    esito = _run(check_accrediti_pos_senza_controparte(db))

    assert esito["esempi"][0]["giorno_vendita"] == "2026-08-14"


def test_due_giorni_diversi_restano_separati():
    db = _Db(movimenti=[
        _accredito(299.50, giorno="13/08/26", data="2026-08-14"),
        _accredito(379.10, giorno="13/08/26", data="2026-08-14", pdv="00012"),
        _accredito(412.20, giorno="14/08/26", data="2026-08-17"),
    ])

    esito = _run(check_accrediti_pos_senza_controparte(db))

    assert esito["violazioni"] == 2
    importi = {e["giorno_vendita"]: e["importo"] for e in esito["esempi"]}
    assert importi == {"2026-08-13": 678.60, "2026-08-14": 412.20}


# ── Quando la controparte c'e', non e' una violazione ─────────────────────

def test_con_il_trasferimento_del_giorno_non_si_segnala_niente():
    db = _Db(
        movimenti=[_accredito(412.20, giorno="14/08/26", data="2026-08-17")],
        trasferimenti=[_trasferimento("2026-08-14")],
    )

    esito = _run(check_accrediti_pos_senza_controparte(db))

    assert esito["violazioni"] == 0 and esito["esempi"] == []


def test_il_trasferimento_di_un_altro_giorno_non_copre():
    db = _Db(
        movimenti=[_accredito(412.20, giorno="14/08/26", data="2026-08-17")],
        trasferimenti=[_trasferimento("2026-08-13")],
    )

    assert _run(check_accrediti_pos_senza_controparte(db))["violazioni"] == 1


def test_un_accredito_gia_riconciliato_non_si_conta():
    db = _Db(movimenti=[
        _accredito(412.20, giorno="14/08/26", data="2026-08-17", riconciliato=True),
    ])

    assert _run(check_accrediti_pos_senza_controparte(db))["violazioni"] == 0


# ── Cosa non e' un accredito POS ──────────────────────────────────────────

@pytest.mark.parametrize("descrizione", [
    "COMMISSIONI SU INCASSI POS NUMIA",           # commissione, non accredito
    "BONIFICO A FORNITORE NUMIA SRL",             # il nome non basta
    "INC.POS CARTE CREDIT - NUMIA-INTER PDV 123",  # senza il giorno operativo
])
def test_le_righe_che_non_sono_accrediti_giornalieri_restano_fuori(descrizione):
    db = _Db(movimenti=[{
        "id": "x", "data": "2026-08-17", "importo": 50.0,
        "descrizione_originale": descrizione,
    }])

    assert _run(check_accrediti_pos_senza_controparte(db))["violazioni"] == 0


def test_le_uscite_non_sono_accrediti():
    """Il filtro sul tipo sta nella query: qui si prova che il check lo passa."""
    db = _Db(movimenti=[])
    assert _run(check_accrediti_pos_senza_controparte(db))["violazioni"] == 0


# ── Igiene ────────────────────────────────────────────────────────────────

def test_il_check_e_registrato_nel_collaudo():
    assert check_accrediti_pos_senza_controparte in CHECKS


def test_legge_ogni_collezione_una_volta_sola():
    """Una query per giorno, su un anno di accrediti, e' proibita dal §4."""
    db = _Db(
        movimenti=[_accredito(10.0 + i, giorno="14/08/26", pdv=f"{i:05d}")
                   for i in range(30)],
        trasferimenti=[_trasferimento("2026-08-14")],
    )

    _run(check_accrediti_pos_senza_controparte(db))

    assert db.letture == {"prima_nota_banca": 1, "estratto_conto_movimenti": 1}


def test_l_importo_complessivo_finisce_nella_descrizione():
    db = _Db(movimenti=[_accredito(412.20, giorno="14/08/26")])
    assert "412.2" in _run(check_accrediti_pos_senza_controparte(db))["descrizione"]
