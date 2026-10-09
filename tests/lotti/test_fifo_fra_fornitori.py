"""Il FIFO consuma sempre la fattura piu' vecchia, anche cambiando fornitore.

La farina puo' arrivare da Fiorentino e da Me.Pa.: sono due lotti diversi dello
stesso ingrediente. La ricetta deve partire dal piu' vecchio, finirlo, e
continuare sul successivo — senza guardare da chi viene.

Qui c'era un difetto vero. L'ordinamento aveva una finestra di 60 giorni: i
lotti piu' vecchi di due mesi finivano **in coda** e, fra loro, ordinati **dal
piu' recente**. Cioe' l'opposto del FIFO: la giacenza vecchia restava ferma a
invecchiare mentre si consumava quella nuova. La finestra rispondeva a un'altra
domanda — quale fornitore scrivere in etichetta — e quella risposta sta in
`peek_lotto_fifo_attivo`, che ora guarda la testa della stessa coda.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def dbmock(monkeypatch):
    import importlib
    import pkgutil

    import app.lotti.routers as routers  # noqa: F401

    db = AsyncMongoMockClient()["Gestionale_Test"]
    for m in pkgutil.iter_modules(routers.__path__):
        try:
            mod = importlib.import_module(f"app.lotti.routers.{m.name}")
        except Exception:
            continue
        if hasattr(mod, "db"):
            monkeypatch.setattr(mod, "db", db, raising=False)
    import app.lotti.db as dbmod

    monkeypatch.setattr(dbmod, "database", db, raising=False)
    return db


def _lotto(id_, fornitore, data_fattura, quantita, *, scadenza="", fattura="F/1"):
    """Un lotto fornitore di farina 00, nel formato che scrive l'import."""
    return {
        "id": id_,
        "lotto_id_fornitore": f"L-{id_}",
        "fornitore": fornitore,
        "prodotto_nome": "FARINA 00",
        "prodotto_nome_norm": "farina 00",
        "nome_canonico": "farina 00",
        "quantita_disponibile": quantita,
        "unita_misura": "KG",
        "data_fattura": data_fattura,
        "data_scadenza": scadenza,
        "fattura_ref": fattura,
        "esaurito": False,
    }


RICETTA = {
    "nome": "Pasta frolla",
    "ingredienti_dettaglio": [{"nome": "Farina 00", "quantita": 30, "unita_misura": "kg"}],
}


def _prepara(db, lotti):
    for l in lotti:
        run(db.lotti_fornitori.insert_one(dict(l)))


def _scarica(ricetta=RICETTA, moltiplicatore=1.0, lotto_produzione="P-1"):
    from app.lotti.routers.lotti_produzione import scala_lotti_fornitori_per_ricetta

    return run(scala_lotti_fornitori_per_ricetta(ricetta, moltiplicatore, lotto_produzione))


def test_finito_un_fornitore_si_prosegue_col_successivo(dbmock):
    """20 kg da Fiorentino + 30 da Me.Pa., ne servono 30: 20 + 10."""
    _prepara(dbmock, [
        _lotto("A", "Fiorentino", "01/03/2026", 20),
        _lotto("B", "Me.Pa.", "15/06/2026", 30),
    ])

    esito = _scarica()

    presi = [(s["fornitore"], s["quantita_consumata"]) for s in esito["lotti_scalati"]]
    assert presi == [("Fiorentino", 20.0), ("Me.Pa.", 10.0)], (
        "Lo scarico deve finire il lotto piu' vecchio e proseguire sul successivo, "
        f"anche di un altro fornitore. Ha fatto: {presi}"
    )
    assert not esito["ingredienti_insufficienti"]
    assert run(dbmock.lotti_fornitori.find_one({"id": "A"}))["esaurito"] is True
    assert run(dbmock.lotti_fornitori.find_one({"id": "B"}))["quantita_disponibile"] == 20.0


def test_un_lotto_di_mesi_fa_si_consuma_prima_di_uno_recente(dbmock):
    """La regressione: con la finestra di 60 giorni il vecchio restava fermo."""
    _prepara(dbmock, [
        _lotto("RECENTE", "Me.Pa.", "10/09/2026", 50),
        _lotto("VECCHIO", "Fiorentino", "02/01/2026", 50),
    ])

    esito = _scarica()

    assert esito["lotti_scalati"][0]["lotto_id"] == "VECCHIO", (
        "La giacenza piu' vecchia deve uscire per prima: e' la piu' vicina a "
        "scadere. Tenerla ferma mentre si consuma la nuova e' l'opposto del FIFO."
    )


def test_un_lotto_scaduto_non_finisce_in_un_dolce(dbmock):
    """Non si consuma: si segnala da smaltire, e si passa al successivo."""
    _prepara(dbmock, [
        _lotto("SCADUTO", "Fiorentino", "01/02/2026", 50, scadenza="01/03/2026"),
        _lotto("BUONO", "Me.Pa.", "01/08/2026", 50, scadenza="31/12/2027"),
    ])

    esito = _scarica()

    usati = [s["lotto_id"] for s in esito["lotti_scalati"]]
    assert usati == ["BUONO"], f"Un lotto scaduto non si consuma. Usati: {usati}"
    assert run(dbmock.lotti_fornitori.find_one({"id": "SCADUTO"}))["quantita_disponibile"] == 50
    da_smaltire = [d["lotto_id"] for d in esito["lotti_da_smaltire"]]
    assert da_smaltire == ["SCADUTO"], (
        "Lo scaduto non va ignorato in silenzio: chi produce deve vederlo e smaltirlo."
    )


def test_una_scadenza_assente_non_vale_come_scaduto(dbmock):
    """Senza data non c'e' la prova che sia scaduto: il lotto resta usabile."""
    _prepara(dbmock, [_lotto("SENZA_DATA", "Fiorentino", "01/03/2026", 50, scadenza="")])

    esito = _scarica()

    assert [s["lotto_id"] for s in esito["lotti_scalati"]] == ["SENZA_DATA"]
    assert not esito["lotti_da_smaltire"]


def test_l_etichetta_dice_il_lotto_che_si_sta_consumando(dbmock):
    """Se le due risposte divergono, l'etichetta e' falsa."""
    from app.lotti.routers.lotti_produzione import peek_lotto_fifo_attivo

    _prepara(dbmock, [
        _lotto("RECENTE", "Me.Pa.", "10/09/2026", 50),
        _lotto("VECCHIO", "Fiorentino", "02/01/2026", 50),
    ])

    in_etichetta = run(peek_lotto_fifo_attivo({"nome": "Farina 00"}))
    primo_consumato = _scarica()["lotti_scalati"][0]

    assert in_etichetta["id"] == primo_consumato["lotto_id"] == "VECCHIO"
    assert in_etichetta["fornitore"] == primo_consumato["fornitore"] == "Fiorentino"


def test_lo_scarico_scrive_la_fattura_che_la_ricerca_interroga(dbmock):
    """`cerca-universale` filtra su `lotti_scalati.fattura_ref`.

    Quel campo non veniva mai scritto: cercare un numero di fattura non
    trovava niente e non dava nessun errore — il silenzio della chiave
    sbagliata. Da qui un'ispezione risale al documento di acquisto.
    """
    from app.lotti.routers.lotti import cerca_universale

    _prepara(dbmock, [_lotto("A", "Fiorentino", "01/03/2026", 50, fattura="2026/417")])
    esito = _scarica()

    scalato = esito["lotti_scalati"][0]
    assert scalato["fattura_ref"] == "2026/417"
    assert scalato["data_fattura"] == "01/03/2026"

    run(dbmock.lotti.insert_one({
        "id": "prod-1", "numero_lotto": "FROLLA-001", "prodotto": "Pasta frolla",
        "lotti_fornitori": esito,
    }))

    trovati = run(cerca_universale(q="2026/417"))
    assert trovati["totale"] == 1, (
        "Dal numero di fattura si deve risalire ai prodotti finiti che la contengono."
    )
    assert trovati["risultati"][0]["numero_lotto"] == "FROLLA-001"


def test_dal_lotto_del_fornitore_ai_prodotti_finiti(dbmock):
    """Tracciabilita' inversa: quella farina, in quali dolci e' finita."""
    from app.lotti.routers.lotti import cerca_universale

    _prepara(dbmock, [_lotto("A", "Fiorentino", "01/03/2026", 100)])
    for numero, prodotto in (("FROLLA-001", "Pasta frolla"), ("BABA-002", "Baba'")):
        esito = _scarica(lotto_produzione=numero)
        run(dbmock.lotti.insert_one({
            "id": numero, "numero_lotto": numero, "prodotto": prodotto,
            "lotti_fornitori": esito,
        }))

    trovati = run(cerca_universale(q="L-A"))

    prodotti = sorted(r["prodotto"] for r in trovati["risultati"])
    assert prodotti == ["Baba'", "Pasta frolla"], (
        f"Da un lotto fornitore devono uscire tutti i prodotti che lo contengono: {prodotti}"
    )
