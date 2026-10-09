"""Gli avvisi dicono quanto resta, non «sotto scorta».

Richiesta del titolare: impostata la soglia (per esempio 50 kg di farina 00),
al calare della giacenza devono uscire avvisi che dicono il numero vero —
«rimangono 45 kg», poi «rimangono 30 kg, ordinare immediatamente».

Due cose che questi test tengono ferme:

1. **la soglia la sceglie lui.** Un prodotto senza soglia non genera avvisi, e
   la soglia dell'«ordinare immediatamente» e' un secondo numero impostato, non
   una percentuale del primo: una frazione inventata direbbe «ordina subito» a
   un numero che nessuno ha scelto, e su prodotti con tempi di consegna diversi
   sbaglierebbe sempre da una parte;
2. **la giacenza e' quella del magazzino**, non un secondo conteggio: l'avviso
   legge `prodotti_unificati`, che somma i lotti di tutti i fornitori.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.lotti.routers.magazzino_unificato import (
    LIVELLO_CRITICO,
    LIVELLO_ESAURITO,
    LIVELLO_SCORTA,
    stato_scorta,
)


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


# ── il giudizio, senza database ────────────────────────────────────────────

def test_sopra_la_soglia_non_disturba():
    assert stato_scorta("Farina 00", 80, "kg", soglia=50, critica=30) is None


def test_sotto_la_soglia_dice_quanto_ne_resta():
    avviso = stato_scorta("Farina 00", 45, "kg", soglia=50, critica=30)

    assert avviso["livello"] == LIVELLO_SCORTA
    assert "rimangono 45 kg" in avviso["messaggio"], (
        f"L'avviso deve portare il numero vero: {avviso['messaggio']}"
    )


def test_alla_soglia_critica_si_ordina_subito():
    avviso = stato_scorta("Farina 00", 30, "kg", soglia=50, critica=30)

    assert avviso["livello"] == LIVELLO_CRITICO
    assert "rimangono 30 kg" in avviso["messaggio"]
    assert "ordinare immediatamente" in avviso["messaggio"]


def test_a_zero_e_esaurito():
    avviso = stato_scorta("Farina 00", 0, "kg", soglia=50, critica=30)

    assert avviso["livello"] == LIVELLO_ESAURITO
    assert "ordinare immediatamente" in avviso["messaggio"]


def test_senza_soglia_nessun_avviso():
    """20 kg sono tanti per una casa e niente per un laboratorio."""
    assert stato_scorta("Farina 00", 20, "kg", soglia=0, critica=0) is None


def test_senza_soglia_critica_resta_il_solo_avviso_di_scorta():
    """Non si inventa una frazione della scorta minima."""
    avviso = stato_scorta("Farina 00", 5, "kg", soglia=50, critica=0)

    assert avviso["livello"] == LIVELLO_SCORTA
    assert "ordinare immediatamente" not in avviso["messaggio"]


# ── dal magazzino vero ─────────────────────────────────────────────────────

def _lotto(id_, fornitore, quantita):
    return {
        "id": id_, "fornitore": fornitore, "prodotto_nome": "FARINA 00",
        "prodotto_nome_norm": "farina 00", "quantita_disponibile": quantita,
        "unita_misura": "KG", "data_fattura": "01/03/2026", "esaurito": False,
    }


def test_la_giacenza_dell_avviso_somma_i_lotti_di_tutti_i_fornitori(dbmock):
    from app.lotti.routers.magazzino_unificato import avvisi_scorte

    run(dbmock.lotti_fornitori.insert_one(_lotto("A", "Fiorentino", 20)))
    run(dbmock.lotti_fornitori.insert_one(_lotto("B", "Me.Pa.", 25)))
    run(dbmock.dizionario_prodotti.insert_one(
        {"nome_normalizzato": "farina 00", "scorta_minima": 50, "scorta_critica": 30}
    ))

    esito = run(avvisi_scorte())

    assert esito["totale"] == 1, f"atteso un solo avviso: {esito}"
    avviso = esito["avvisi"][0]
    assert avviso["giacenza"] == 45, (
        "L'avviso deve leggere la stessa giacenza del magazzino (20 + 25), "
        "non un secondo conteggio."
    )
    assert avviso["livello"] == LIVELLO_SCORTA


def test_un_prodotto_senza_soglia_non_compare(dbmock):
    from app.lotti.routers.magazzino_unificato import avvisi_scorte

    run(dbmock.lotti_fornitori.insert_one(_lotto("A", "Fiorentino", 1)))

    assert run(avvisi_scorte())["totale"] == 0


def test_solo_critici_lascia_fuori_la_scorta_semplice(dbmock):
    from app.lotti.routers.magazzino_unificato import avvisi_scorte

    run(dbmock.lotti_fornitori.insert_one(_lotto("A", "Fiorentino", 45)))
    run(dbmock.dizionario_prodotti.insert_one(
        {"nome_normalizzato": "farina 00", "scorta_minima": 50, "scorta_critica": 30}
    ))

    assert run(avvisi_scorte(solo_critici=True))["totale"] == 0


def test_la_soglia_critica_non_puo_stare_sopra_la_scorta_minima(dbmock):
    """Scatterebbe per prima e la scorta minima non direbbe piu' niente."""
    from fastapi import HTTPException

    from app.lotti.routers.magazzino_unificato import SogliaPayload, set_soglia

    with pytest.raises(HTTPException) as errore:
        run(set_soglia(SogliaPayload(
            prodotto_nome_norm="farina 00", soglia_minima=30, soglia_critica=50
        )))

    assert errore.value.status_code == 400


def test_impostare_la_scorta_minima_non_cancella_quella_critica(dbmock):
    """`soglia_critica` non inviata = non toccarla."""
    from app.lotti.routers.magazzino_unificato import SogliaPayload, get_soglie, set_soglia

    run(set_soglia(SogliaPayload(
        prodotto_nome_norm="farina 00", soglia_minima=50, soglia_critica=30)))
    run(set_soglia(SogliaPayload(prodotto_nome_norm="farina 00", soglia_minima=60)))

    soglie = {s["prodotto_nome_norm"]: s for s in run(get_soglie())}
    assert soglie["farina 00"]["soglia_minima"] == 60
    assert soglie["farina 00"]["soglia_critica"] == 30, (
        "Salvare la scorta minima ha cancellato la soglia dell'«ordinare subito»."
    )
