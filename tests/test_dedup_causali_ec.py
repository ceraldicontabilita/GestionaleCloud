"""Doppioni EC da causali con prefisso: chiave normalizzata + bonifica storica.

Il rischio da non correre e' l'opposto del bug: collassare tre addebiti VERI
da 1,79 dello stesso giorno in uno solo. La regola difesa qui: la verita' e'
il singolo file — il numero reale di operazioni di un gruppo e' il massimo di
righe che UN file porta; solo l'eccedenza cross-file e' doppione.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.routers.bank import estratto_conto as modulo_import
from app.routers.bank.estratto_conto import normalizza_descrizione_ec
from app.services import dedup_causali_ec

SDD_CORTO = "SDD CORE: M-100286973-3908993102489156 WORLDPAY"
SDD_LUNGO = "ADDEBITO DIRETTO SDD - SDD CORE: M-100286973-3908993102489156 WORLDPAY"

INTESTAZIONE = ("Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;"
                "Importo;Divisa;Descrizione;Categoria/sottocategoria;Hashtag")


def _run(awaitable):
    return asyncio.run(awaitable)


# --- La normalizzazione ----------------------------------------------------

def test_le_due_forme_della_stessa_operazione_hanno_la_stessa_chiave():
    assert normalizza_descrizione_ec(SDD_CORTO) == normalizza_descrizione_ec(SDD_LUNGO)


def test_il_contenuto_non_viene_mai_normalizzato():
    """Mandati diversi = operazioni diverse, anche con lo stesso prefisso."""
    altro = SDD_LUNGO.replace("100286973", "999999999")
    assert normalizza_descrizione_ec(SDD_LUNGO) != normalizza_descrizione_ec(altro)


# --- L'import non crea piu' il doppione ------------------------------------

class _File:
    skip_duplicate_repairs = True

    def __init__(self, righe, filename):
        self.filename = filename
        self._contenuto = ("\r\n".join([INTESTAZIONE, *righe]) + "\r\n").encode()

    async def read(self):
        return self._contenuto


def _riga(descrizione, importo="-1,79"):
    return (f"CERALDI GROUP S.R.L.;31/03/2026;31/03/2026;05034 - BANCO BPM;"
            f"5462;{importo};EUR;{descrizione};Utenze - Servizi;")


@pytest.fixture
def db(monkeypatch):
    finto = AsyncMongoMockClient()["dedup_causali_test"]
    monkeypatch.setattr(modulo_import.Database, "get_db", staticmethod(lambda: finto))
    return finto


def test_il_secondo_file_con_prefisso_diverso_non_duplica(db):
    _run(modulo_import.import_estratto_conto(_File([_riga(SDD_CORTO)], "ElencoEntrateUscite.csv")))
    _run(modulo_import.import_estratto_conto(_File([_riga(SDD_LUNGO)], "ESTRATTO 2026.csv")))

    assert _run(db["estratto_conto_movimenti"].count_documents({})) == 1


def test_tre_addebiti_veri_nello_stesso_giorno_restano_tre(db):
    """Il file li dichiara tre volte: sono tre operazioni, non un errore."""
    righe = [_riga(SDD_LUNGO)] * 3
    _run(modulo_import.import_estratto_conto(_File(righe, "ESTRATTO 2026.csv")))

    assert _run(db["estratto_conto_movimenti"].count_documents({})) == 3


# --- La bonifica dello storico ---------------------------------------------

def _semina_storico(db, *righe):
    _run(db["estratto_conto_movimenti"].insert_many([dict(r) for r in righe]))


def _ec(id_, descrizione, file, **extra):
    return {"id": id_, "data": "2026-03-31", "importo": 1.79, "tipo": "uscita",
            "descrizione_originale": descrizione, "source_filename": file,
            "created_at": f"2026-04-0{id_[-1]}", "riconciliato": False, **extra}


def test_la_bonifica_marca_solo_l_eccedenza_cross_file():
    db = AsyncMongoMockClient()["bonifica_test"]
    # File A dichiara DUE operazioni; file B le ridichiara col prefisso.
    _semina_storico(
        db,
        _ec("a1", SDD_CORTO, "ElencoEntrateUscite.csv"),
        _ec("a2", SDD_CORTO, "ElencoEntrateUscite.csv"),
        _ec("b1", SDD_LUNGO, "ESTRATTO 2026.csv"),
        _ec("b2", SDD_LUNGO, "ESTRATTO 2026.csv"),
    )

    esito = _run(dedup_causali_ec.applica(db))

    assert esito["righe_marcate"] == 2          # 4 righe, 2 reali
    doppioni = _run(db["estratto_conto_movimenti"].find(
        {"tipo_riconciliazione": "duplicato_causale"}).to_list(10))
    assert len(doppioni) == 2
    assert all(d["riconciliato"] is True for d in doppioni)
    assert all(d["dettagli_riconciliazione"]["riga_conservata_id"] for d in doppioni)
    # Nessuna riga cancellata: sono tutte ancora li'.
    assert _run(db["estratto_conto_movimenti"].count_documents({})) == 4


def test_un_gruppo_con_una_sola_forma_non_viene_toccato():
    """N righe identiche dallo stesso file = N operazioni dichiarate."""
    db = AsyncMongoMockClient()["bonifica_test2"]
    _semina_storico(
        db,
        _ec("a1", SDD_LUNGO, "ESTRATTO 2026.csv"),
        _ec("a2", SDD_LUNGO, "ESTRATTO 2026.csv"),
        _ec("a3", SDD_LUNGO, "ESTRATTO 2026.csv"),
    )

    esito = _run(dedup_causali_ec.applica(db))
    assert esito["righe_marcate"] == 0


def test_la_riga_gia_lavorata_e_quella_che_resta():
    """Se una copia e' gia' in Prima Nota, si marca l'altra."""
    db = AsyncMongoMockClient()["bonifica_test3"]
    _semina_storico(
        db,
        _ec("a1", SDD_CORTO, "ElencoEntrateUscite.csv"),
        _ec("b1", SDD_LUNGO, "ESTRATTO 2026.csv", importato_prima_nota=True),
    )

    _run(dedup_causali_ec.applica(db))

    marcata = _run(db["estratto_conto_movimenti"].find_one(
        {"tipo_riconciliazione": "duplicato_causale"}))
    assert marcata["id"] == "a1"


def test_l_analisi_non_scrive_niente():
    db = AsyncMongoMockClient()["bonifica_test4"]
    _semina_storico(
        db,
        _ec("a1", SDD_CORTO, "ElencoEntrateUscite.csv"),
        _ec("b1", SDD_LUNGO, "ESTRATTO 2026.csv"),
    )

    esito = _run(dedup_causali_ec.analizza(db))

    assert esito["righe_da_marcare"] == 1
    assert _run(db["estratto_conto_movimenti"].count_documents(
        {"tipo_riconciliazione": "duplicato_causale"})) == 0
