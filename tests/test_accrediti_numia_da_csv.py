"""Accrediti NUMIA dal CSV: accorpati per giorno di vendita, mai entrate.

Il caso e' quello segnalato dall'utente il 07/08/2026 con le SUE righe: cinque
accrediti NUMIA dello stesso giorno di vendita (due punti vendita, tre
circuiti carta), arrivati in banca il giorno dopo. Prima finivano in Prima
Nota come "Rimborso" — entrate mai avvenute, perche' quel denaro era gia'
contato nel trasferimento POS del giorno — dato che la riconciliazione
scattava solo con il PDF ufficiale, mentre l'operativita' quotidiana e' il
CSV.

La regola canonica (18/07/2026): l'accredito NON crea un'entrata, RICONCILIA
il trasferimento cassa->banca del giorno di vendita, sommando i circuiti.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.routers.bank import estratto_conto as modulo
from app.services.scritture_contabili import (
    registra_chiusura_pos_reale,
    riconcilia_accredito_pos_ec,
)

INTESTAZIONE = ("Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;"
                "Importo;Divisa;Descrizione;Categoria/sottocategoria;Hashtag")
BANCA = "05034 - BANCO BPM S.P.A."
RAPPORTO = "5462 - 03406 - 178800005462"

# Le cinque righe REALI del 06/08/2026: vendite del 05/08, due PDV, tre
# circuiti. Somma: 14.00 + 16.60 + 16.50 + 523.00 + 244.00 = 814.10.
ACCREDITI_NUMIA = [
    ("INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 05/08/26 PDV 3757283/00011 CERALDI CAFFE NA", "14,00"),
    ("INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 05/08/26 PDV 3757283/00012 CERALDI CAFFE' NA", "16,60"),
    ("INC.POS CARTE CREDIT - NUMIA-AMEX DEL 05/08/26 PDV 3757283/00011 CERALDI CAFFE NA", "16,50"),
    ("INC.POS CARTE CREDIT - NUMIA-INTER DEL 05/08/26 PDV 3757283/00011 CERALDI CAFFE NA", "523,00"),
    ("INC.POS CARTE CREDIT - NUMIA-INTER DEL 05/08/26 PDV 3757283/00012 CERALDI CAFFE' NA", "244,00"),
]
TOTALE_GIORNO = 814.10


def _riga(descrizione, importo, categoria="Ricavi - Incasso tramite POS"):
    return (f"CERALDI GROUP S.R.L.;06/08/2026;06/08/2026;{BANCA};{RAPPORTO};"
            f"{importo};EUR;{descrizione};{categoria};")


def _csv(righe):
    return ("\r\n".join([INTESTAZIONE, *righe]) + "\r\n").encode("utf-8")


class _File:
    skip_duplicate_repairs = True

    def __init__(self, contenuto, filename="ESTRATTO 2026.csv"):
        self.filename = filename
        self._contenuto = contenuto

    async def read(self):
        return self._contenuto


def _run(awaitable):
    return asyncio.run(awaitable)


@pytest.fixture
def db(monkeypatch):
    finto = AsyncMongoMockClient()["accrediti_numia_test"]
    monkeypatch.setattr(modulo.Database, "get_db", staticmethod(lambda: finto))
    return finto


def _prepara_trasferimento(db, importo=TOTALE_GIORNO, gestore="numia"):
    """Il trasferimento del giorno di vendita, come lo crea la Prima Nota
    Cassa quando si registra la chiusura POS reale."""
    _run(registra_chiusura_pos_reale(db, "2026-08-05", importo, gestore=gestore))


def _importa_csv(db, righe):
    return _run(modulo.import_estratto_conto(_File(_csv(righe))))


# --- Il caso dell'utente, per intero ---------------------------------------

def test_i_cinque_accrediti_del_giorno_riconciliano_il_trasferimento(db):
    _prepara_trasferimento(db)
    _importa_csv(db, [_riga(d, i) for d, i in ACCREDITI_NUMIA])

    trasferimento = _run(db["prima_nota_banca"].find_one(
        {"source": "trasferimento_pos"}))
    assert trasferimento["riconciliato"] is True
    assert trasferimento["accreditato_ec"] == TOTALE_GIORNO
    assert len(trasferimento["estratto_conto_ids"]) == 5


def test_gli_accrediti_non_diventano_mai_entrate(db):
    """Era il danno: righe "Rimborso" in Prima Nota per denaro gia' contato."""
    _prepara_trasferimento(db)
    _importa_csv(db, [_riga(d, i) for d, i in ACCREDITI_NUMIA])

    righe = _run(db["prima_nota_banca"].find(
        {"source": {"$ne": "trasferimento_pos"}}).to_list(50))
    assert righe == []


def test_le_righe_ec_risultano_riconciliate_col_giorno_di_vendita(db):
    _prepara_trasferimento(db)
    _importa_csv(db, [_riga(d, i) for d, i in ACCREDITI_NUMIA])

    movimenti = _run(db["estratto_conto_movimenti"].find({}).to_list(50))
    assert len(movimenti) == 5
    assert all(m["riconciliato"] is True for m in movimenti)
    assert all(
        m["dettagli_riconciliazione"]["giorno_vendita"] == "2026-08-05"
        for m in movimenti
    )


def test_un_accredito_parziale_lascia_il_gruppo_da_verificare(db):
    """Se manca un circuito la somma non torna: niente riconciliazione
    d'ufficio, la differenza resta scritta e visibile."""
    _prepara_trasferimento(db)
    _importa_csv(db, [_riga(d, i) for d, i in ACCREDITI_NUMIA[:4]])  # manca INTER 244

    trasferimento = _run(db["prima_nota_banca"].find_one(
        {"source": "trasferimento_pos"}))
    assert trasferimento["riconciliato"] is False
    assert trasferimento["accreditato_ec"] == round(TOTALE_GIORNO - 244.00, 2)


def test_senza_trasferimento_l_accredito_resta_aperto_e_non_inventa_nulla(db):
    """Corrispettivo mai registrato per quel giorno: l'EC resta non
    riconciliato e il collaudo lo evidenzia. Nessuna entrata di ripiego."""
    _importa_csv(db, [_riga(*ACCREDITI_NUMIA[0])])

    assert _run(db["prima_nota_banca"].find({}).to_list(10)) == []
    movimento = _run(db["estratto_conto_movimenti"].find_one({}))
    assert movimento.get("riconciliato") is not True


# --- Multi-gestore: il filtro sul circuito ---------------------------------

def test_l_accredito_numia_non_tocca_il_trasferimento_sumup(db):
    """Dal 07/08/2026 nello stesso giorno convivono trasferimenti Numia e
    SumUp: la causale NUMIA deve agganciare SOLO il suo."""
    _prepara_trasferimento(db, importo=14.00, gestore="numia")
    _prepara_trasferimento(db, importo=200.00, gestore="sumup")

    movimento = {"id": "ec-1", "data": "2026-08-06", "tipo": "entrata",
                 "importo": 14.00,
                 "descrizione_originale": ACCREDITI_NUMIA[0][0]}
    assert _run(riconcilia_accredito_pos_ec(db, movimento)) is True

    numia = _run(db["prima_nota_banca"].find_one(
        {"source": "trasferimento_pos", "gestore": "numia"}))
    sumup = _run(db["prima_nota_banca"].find_one(
        {"source": "trasferimento_pos", "gestore": "sumup"}))
    assert numia["riconciliato"] is True
    assert sumup.get("accreditato_ec") is None
    assert sumup["riconciliato"] is False


def test_le_chiusure_storiche_senza_gestore_restano_agganciabili(db):
    """Le righe pre-07/08 non hanno il campo gestore: sono Nexi/Numia per
    definizione e l'accredito NUMIA deve continuare a trovarle."""
    _run(db["prima_nota_banca"].insert_one({
        "id": "trasf-storico", "source": "trasferimento_pos",
        "data": "2026-08-05", "giorno_vendita": "2026-08-05",
        "tipo": "entrata", "importo": 14.00, "riconciliato": False,
    }))
    movimento = {"id": "ec-1", "data": "2026-08-06", "tipo": "entrata",
                 "importo": 14.00,
                 "descrizione_originale": ACCREDITI_NUMIA[0][0]}

    assert _run(riconcilia_accredito_pos_ec(db, movimento)) is True
