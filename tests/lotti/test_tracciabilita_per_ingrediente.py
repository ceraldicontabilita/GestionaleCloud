"""«Con quella farina quanti prodotti diversi ho fatto?»

E il verso opposto: «da dove veniva la farina di questo dolce?». E' la domanda
che fa un'ispezione, e fino a oggi non si poteva rispondere: la ricerca sapeva
solo il numero di fattura e il lotto fornitore, campi che **su 84 lotti di
produzione veri erano vuoti in tutti e 84**. L'origine c'era, ma intrappolata
nelle righe di testo dell'etichetta.

Le righe di questi test sono copiate dai dati di produzione, virgole e doppi
spazi compresi: se il formato cambia, questi test se ne accorgono.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi.tracciabilita import (
    normalizza,
    origini_del_lotto,
    scompone_riga_ingrediente,
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


# Righe vere, prese da `lotti.lotti_documents` in produzione.
FARINA = ("FARINA 00 MANITOBA KG 25  non contiene allergeni - "
          "FORNITORE FARINE SRL n° fatt TEST/001 - 21/12/2025")
RICOTTA = ("Ricotta di Pecora Zuccherata Congelata x 6 - Ricocrem-  non contiene allergeni - "
           "GE.FI.AL. SAS DI FIORENZANO GENNARO & C. n° fatt 336 - 16/12/2025")
TUORLO = ("ELITE TUORLO DA ALLEVAMENTO A TERRA PASTORIZZATO (1339) CAT \"A\"\n      \n"
          "  non contiene allergeni - SAIMA S.p.A. n° fatt 1/221071 - 15/12/2025")
SENZA_ORIGINE = "Mix cake nature (4830)"


# ── la lettura della riga ──────────────────────────────────────────────────

def test_legge_ingrediente_fornitore_fattura_e_data():
    voce = scompone_riga_ingrediente(FARINA)

    assert voce["ingrediente"] == "FARINA 00 MANITOBA KG 25"
    assert voce["fornitore"] == "FORNITORE FARINE SRL"
    assert voce["fattura"] == "TEST/001"
    assert voce["data_fattura"] == "21/12/2025"
    assert voce["senza_origine"] is False


def test_un_trattino_dentro_il_nome_non_spezza_il_prodotto():
    """«Ricotta ... x 6 - Ricocrem-»: tagliare sul primo trattino lo spezzava."""
    voce = scompone_riga_ingrediente(RICOTTA)

    assert voce["ingrediente"] == "Ricotta di Pecora Zuccherata Congelata x 6 - Ricocrem-"
    assert voce["fornitore"] == "GE.FI.AL. SAS DI FIORENZANO GENNARO & C."
    assert voce["fattura"] == "336"


def test_gli_a_capo_del_fornitore_non_entrano_nel_nome():
    voce = scompone_riga_ingrediente(TUORLO)

    assert "\n" not in voce["ingrediente"]
    assert voce["ingrediente"].startswith("ELITE TUORLO")
    assert voce["fornitore"] == "SAIMA S.p.A."
    assert voce["fattura"] == "1/221071"


def test_un_ingrediente_senza_fornitore_lo_dice():
    """Non si indovina e non si nasconde: e' il buco da conoscere."""
    voce = scompone_riga_ingrediente(SENZA_ORIGINE)

    assert voce["senza_origine"] is True
    assert voce["ingrediente"] == "Mix cake nature (4830)"
    assert not voce.get("fornitore")


def test_il_confronto_ignora_accenti_maiuscole_e_spazi_doppi():
    assert normalizza("FARINA 00  MANITOBA") == "farina 00 manitoba"
    assert normalizza("Però") == "pero"


# ── le due fonti insieme ───────────────────────────────────────────────────

def test_lo_scarico_vince_sulla_riga_di_testo():
    """Sullo stesso ingrediente il collegamento esatto sostituisce la stima."""
    lotto = {
        "ingredienti_dettaglio": [FARINA],
        "lotti_fornitori": {"lotti_scalati": [{
            "ingrediente": "Farina 00 Manitoba kg 25", "lotto_id": "L-1",
            "lotto_id_fornitore": "LOTTO-A", "fornitore": "Fiorentino",
            "fattura_ref": "2026/417", "quantita_consumata": 12.5, "unita": "KG",
        }]},
    }

    origini = origini_del_lotto(lotto)

    assert len(origini) == 1, f"l'ingrediente e' stato contato due volte: {origini}"
    assert origini[0]["origine"] == "scarico"
    assert origini[0]["fattura"] == "2026/417"
    assert origini[0]["quantita_consumata"] == 12.5


def test_un_lotto_a_meta_strada_non_perde_ne_l_una_ne_l_altra():
    lotto = {
        "ingredienti_dettaglio": [FARINA, RICOTTA],
        "lotti_fornitori": {"lotti_scalati": [{
            "ingrediente": "FARINA 00 MANITOBA KG 25", "fornitore": "Fiorentino",
            "fattura_ref": "2026/417",
        }]},
    }

    origini = origini_del_lotto(lotto)
    per_origine = {o["origine"] for o in origini}

    assert len(origini) == 2
    assert per_origine == {"scarico", "testo"}


# ── le ricerche ────────────────────────────────────────────────────────────

def _popola(db):
    run(db.lotti.insert_many([
        {"id": "L1", "numero_lotto": "CASSATIN-001", "prodotto": "cassatina",
         "data_produzione": "29/12/2025", "ingredienti_dettaglio": [FARINA, RICOTTA, SENZA_ORIGINE]},
        {"id": "L2", "numero_lotto": "BABA-003", "prodotto": "babà misù",
         "data_produzione": "29/12/2025", "ingredienti_dettaglio": [FARINA, TUORLO]},
        {"id": "L3", "numero_lotto": "SFOGLIA-009", "prodotto": "sfogliatella",
         "data_produzione": "30/12/2025", "ingredienti_dettaglio": [RICOTTA]},
    ]))


def test_quanti_prodotti_diversi_con_quella_farina(dbmock):
    from app.lotti.routers.tracciabilita import per_ingrediente

    _popola(dbmock)
    esito = run(per_ingrediente(nome="farina"))

    assert esito["lotti_di_produzione"] == 2
    assert esito["prodotti_diversi"] == 2, (
        "La domanda e' «quanti prodotti DIVERSI»: due lotti dello stesso dolce "
        "non fanno due prodotti."
    )
    assert esito["fatture"] == ["TEST/001"]
    assert esito["fornitori"] == ["FORNITORE FARINE SRL"]


def test_due_lotti_dello_stesso_dolce_contano_un_prodotto(dbmock):
    from app.lotti.routers.tracciabilita import per_ingrediente

    _popola(dbmock)
    run(dbmock.lotti.insert_one(
        {"id": "L4", "numero_lotto": "CASSATIN-002", "prodotto": "cassatina",
         "data_produzione": "31/12/2025", "ingredienti_dettaglio": [FARINA]}))

    esito = run(per_ingrediente(nome="farina"))

    assert esito["lotti_di_produzione"] == 3
    assert esito["prodotti_diversi"] == 2


def test_ricerca_per_fornitore(dbmock):
    from app.lotti.routers.tracciabilita import per_fornitore

    _popola(dbmock)
    esito = run(per_fornitore(nome="SAIMA"))

    assert esito["lotti_di_produzione"] == 1
    assert esito["risultati"][0]["prodotto"] == "babà misù"


def test_ricerca_per_numero_di_fattura(dbmock):
    from app.lotti.routers.tracciabilita import per_fattura

    _popola(dbmock)
    esito = run(per_fattura(numero="336"))

    prodotti = sorted(r["prodotto"] for r in esito["risultati"])
    assert prodotti == ["cassatina", "sfogliatella"]


def test_la_fattura_si_confronta_intera(dbmock):
    """«1/221071» non deve uscire cercando «221071»: e' un identificativo."""
    from app.lotti.routers.tracciabilita import per_fattura

    _popola(dbmock)

    assert run(per_fattura(numero="221071"))["lotti_di_produzione"] == 0
    assert run(per_fattura(numero="1/221071"))["lotti_di_produzione"] == 1


def test_dal_dolce_a_dove_veniva_ogni_ingrediente(dbmock):
    from app.lotti.routers.tracciabilita import origini_di_un_lotto

    _popola(dbmock)
    esito = run(origini_di_un_lotto(numero_lotto="CASSATIN-001"))

    assert esito["prodotto"] == "cassatina"
    assert esito["ingredienti_totali"] == 3
    assert esito["senza_origine"] == ["Mix cake nature (4830)"]
    fornitori = {o["fornitore"] for o in esito["origini"] if o.get("fornitore")}
    assert fornitori == {"FORNITORE FARINE SRL", "GE.FI.AL. SAS DI FIORENZANO GENNARO & C."}


def test_un_lotto_inesistente_non_inventa_una_risposta(dbmock):
    from fastapi import HTTPException

    from app.lotti.routers.tracciabilita import origini_di_un_lotto

    _popola(dbmock)
    with pytest.raises(HTTPException) as errore:
        run(origini_di_un_lotto(numero_lotto="MAI-ESISTITO"))
    assert errore.value.status_code == 404


def test_l_elenco_dei_buchi_di_tracciabilita(dbmock):
    """Dove la catena si spezza, prima che lo chieda un'ispezione."""
    from app.lotti.routers.tracciabilita import ingredienti_senza_origine

    _popola(dbmock)
    esito = run(ingredienti_senza_origine())

    assert esito["lotti_coinvolti"] == 1
    assert esito["piu_frequenti"][0] == {"ingrediente": "Mix cake nature (4830)", "lotti": 1}


def test_l_elenco_dei_buchi_regge_la_chiamata_da_codice(dbmock):
    """`Query(200)` chiamato da codice resta un oggetto, non un numero.

    E' lo stesso difetto che aveva la firma col PIN: l'endpoint funziona dal
    browser e salta ovunque lo chiami qualcos'altro — qui dopo aver gia' fatto
    tutto il lavoro, quindi il costo c'e' e il risultato no.
    """
    from app.lotti.routers.tracciabilita import ingredienti_senza_origine

    _popola(dbmock)
    esito = run(ingredienti_senza_origine())   # senza passare `limite`

    assert esito["lotti_coinvolti"] == 1


def test_si_distingue_la_prova_certa_dalla_ricostruzione(dbmock):
    """Davanti a un'ispezione la differenza conta."""
    from app.lotti.routers.tracciabilita import per_ingrediente

    _popola(dbmock)
    run(dbmock.lotti.insert_one({
        "id": "L5", "numero_lotto": "PASTIERA-001", "prodotto": "pastiera",
        "data_produzione": "02/01/2026",
        "lotti_fornitori": {"lotti_scalati": [{
            "ingrediente": "Farina 00", "fornitore": "Me.Pa.", "fattura_ref": "2026/9",
        }]},
    }))

    esito = run(per_ingrediente(nome="farina"))

    assert esito["lotti_di_produzione"] == 3
    assert esito["origini_certe"] == 1, (
        "Solo la pastiera ha il collegamento esatto dello scarico; le altre due "
        "sono ricostruite dall'etichetta."
    )
