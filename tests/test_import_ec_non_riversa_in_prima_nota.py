"""L'import di un estratto conto non riversa piu' tutto in Prima Nota Banca.

Il test che conta davvero: non la regola in astratto — quella e' coperta da
`test_prima_nota_banca_solo_agganciati.py` — ma il percorso vero, dal file CSV
alle righe scritte. Prima l'import agganciava fatture, cedolini e F24, e poi
scaricava in Prima Nota **tutto il resto** come riga grezza "da verificare":
per questo la pagina sembrava una fotocopia dell'estratto conto.

L'altra meta' del test e' il confine da non superare: competenze bancarie e
prelievi al bancomat devono continuare a entrare. Se sparissero, la Prima Nota
sarebbe piu' corta ma sbagliata, perche' quel denaro dal conto e' uscito.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.routers.bank import estratto_conto as modulo

INTESTAZIONE = ("Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;"
                "Importo;Divisa;Descrizione;Categoria/sottocategoria;Hashtag")

BANCA = "05034 - BANCO BPM S.P.A."
RAPPORTO = "5462 - 03406 - 178800005462"

# Causali reali prese dall'export BPM dell'azienda.
BONIFICO_FORNITORE = (
    "BONIFICO A FAVORE SCARAMUZZA SPA NOTPROVIDE - ADD. FATT 123", "-1807,71",
    "Fornitori - Beni")
COMMISSIONI = ("COMM.SU BONIFICI", "-1,10", "Operazioni Finanziarie - Commissioni")
PRELIEVO = ("PRELIEVO BANCOMAT SPORTELLO 03406", "-500,00", "")
STIPENDIO = ("BONIFICO A FAVORE DIPENDENTE ROSSI", "-1200,00",
             "Risorse Umane - Stipendi")


def _riga(descrizione, importo, categoria, data="17/07/2026"):
    return (f"CERALDI GROUP S.R.L.;{data};{data};{BANCA};{RAPPORTO};"
            f"{importo};EUR;{descrizione};{categoria};")


def _csv(*righe):
    return ("\r\n".join([INTESTAZIONE, *righe]) + "\r\n").encode("utf-8")


class _File:
    """Sostituto di UploadFile: solo quello che l'import usa davvero."""

    skip_duplicate_repairs = True

    def __init__(self, contenuto, filename="ESTRATTO 2026.csv"):
        self.filename = filename
        self._contenuto = contenuto

    async def read(self):
        return self._contenuto


@pytest.fixture
def db(monkeypatch):
    finto = AsyncMongoMockClient()["prima_nota_import_test"]
    monkeypatch.setattr(modulo.Database, "get_db", staticmethod(lambda: finto))
    return finto


def _importa(db, *righe, filename="ESTRATTO 2026.csv"):
    return asyncio.run(modulo.import_estratto_conto(_File(_csv(*righe), filename)))


def _prima_nota(db):
    return asyncio.run(db["prima_nota_banca"].find({}).to_list(100))


def _movimenti_ec(db):
    return asyncio.run(db["estratto_conto_movimenti"].find({}).to_list(100))


# --- Quello che NON deve piu' entrare --------------------------------------

def test_un_bonifico_senza_fattura_non_entra_in_prima_nota(db):
    """Il caso segnalato dall'utente: l'estratto conto riversato in Prima Nota."""
    _importa(db, _riga(*BONIFICO_FORNITORE))

    assert _prima_nota(db) == []


def test_il_movimento_resta_in_attesa_del_documento(db):
    """Non sparisce: aspetta in coda, ed e' li' che lo si aggancia."""
    _importa(db, _riga(*BONIFICO_FORNITORE))

    movimenti = _movimenti_ec(db)
    assert len(movimenti) == 1
    assert movimenti[0]["stato_riconciliazione"] == "in_attesa_documento"
    assert movimenti[0].get("riconciliato") is not True
    assert movimenti[0].get("importato_prima_nota") is False


def test_neanche_gli_stipendi_entrano_senza_cedolino(db):
    _importa(db, _riga(*STIPENDIO))

    assert _prima_nota(db) == []


# --- Quello che DEVE continuare a entrare ----------------------------------

def test_le_competenze_bancarie_entrano_lo_stesso(db):
    """Non avranno mai una fattura: escluderle sballerebbe il saldo."""
    _importa(db, _riga(*COMMISSIONI))

    righe = _prima_nota(db)
    assert len(righe) == 1
    assert righe[0]["categoria"] == "Commissioni bancarie"
    assert righe[0]["importo"] == 1.10
    assert righe[0]["tipo"] == "uscita"


def test_il_prelievo_al_bancomat_entra_lo_stesso(db):
    _importa(db, _riga(*PRELIEVO))

    righe = _prima_nota(db)
    assert len(righe) == 1
    assert righe[0]["categoria"] == "Prelevamento Banca"


# --- Il quadro d'insieme ---------------------------------------------------

def test_di_quattro_movimenti_ne_entrano_due(db):
    """La prova che la Prima Nota smette di essere una copia dell'estratto."""
    esito = _importa(
        db,
        _riga(*BONIFICO_FORNITORE),
        _riga(*COMMISSIONI),
        _riga(*PRELIEVO),
        _riga(*STIPENDIO),
    )

    assert len(_movimenti_ec(db)) == 4       # l'estratto conto resta intero
    assert len(_prima_nota(db)) == 2         # in Prima Nota solo cio' che puo' entrarci

    sync = esito.get("sync_prima_nota") or {}
    assert sync.get("in_attesa_documento") == 2
    assert sync.get("inseriti_banca") == 2


def test_reimportare_lo_stesso_estratto_non_duplica(db):
    righe = (_riga(*BONIFICO_FORNITORE), _riga(*COMMISSIONI))
    _importa(db, *righe)
    _importa(db, *righe)

    assert len(_movimenti_ec(db)) == 2
    assert len(_prima_nota(db)) == 1
