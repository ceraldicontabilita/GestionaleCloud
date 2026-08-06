"""POS reale con piu' terminali (Nexi + SumUp).

Il POS reale del giorno e' la somma dei gestori. Il rischio piu' grave e' il
doppio conteggio: le chiusure gia' in produzione non hanno il campo gestore,
e trattarle come righe di un terminale diverso raddoppierebbe l'incasso.
"""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services.scritture_contabili import (
    GESTORE_POS_DEFAULT,
    chiusura_pos_del_giorno,
    filtro_gestore_pos,
    normalizza_gestore_pos,
)


def _run(awaitable):
    return asyncio.run(awaitable)


def _db():
    return AsyncMongoMockClient()["pos_multi_gestore_test"]


def _chiusura(importo, gestore=None, source="inserimento_manuale_terminale"):
    riga = {"data": "2026-08-06", "importo": importo, "source": source}
    if gestore is not None:
        riga["gestore"] = gestore
    return riga


# --- Normalizzazione -------------------------------------------------------

def test_una_riga_storica_senza_gestore_e_nexi():
    assert normalizza_gestore_pos(None) == GESTORE_POS_DEFAULT
    assert normalizza_gestore_pos("") == GESTORE_POS_DEFAULT
    assert normalizza_gestore_pos("  SumUp ") == "sumup"


def test_il_filtro_nexi_intercetta_anche_le_righe_senza_campo():
    """Altrimenti un nuovo inserimento Nexi creerebbe una riga parallela."""
    filtro = filtro_gestore_pos("nexi")
    alternative = filtro["$or"]
    assert {"gestore": {"$exists": False}} in alternative
    assert {"gestore": "nexi"} in alternative
    # Per gli altri gestori il filtro resta secco.
    assert filtro_gestore_pos("sumup") == {"gestore": "sumup"}


# --- Totale del giorno -----------------------------------------------------

def test_il_totale_somma_i_due_terminali():
    db = _db()
    _run(db.chiusure_pos_manuali.insert_many([
        _chiusura(300.0, "nexi"),
        _chiusura(120.50, "sumup"),
    ]))
    assert _run(chiusura_pos_del_giorno(db, "2026-08-06")) == 420.50


def test_una_chiusura_storica_non_viene_contata_due_volte():
    """Riga senza gestore (Nexi storico) + riga Nexi esplicita: e' lo stesso
    terminale, quindi vale la correzione manuale, non la somma."""
    db = _db()
    _run(db.chiusure_pos_manuali.insert_many([
        _chiusura(300.0),            # storica, senza campo gestore
        _chiusura(280.0, "nexi"),    # correzione dello stesso terminale
    ]))
    assert _run(chiusura_pos_del_giorno(db, "2026-08-06")) == 280.0


def test_la_correzione_di_un_terminale_non_cancella_l_altro():
    db = _db()
    _run(db.chiusure_pos_manuali.insert_many([
        _chiusura(500.0, "nexi", source="import_csv"),
        _chiusura(450.0, "nexi"),     # correzione manuale su Nexi
        _chiusura(80.0, "sumup"),     # SumUp resta intatto
    ]))
    assert _run(chiusura_pos_del_giorno(db, "2026-08-06")) == 530.0


def test_zero_su_un_terminale_resta_un_valore_valido():
    """Zero significa 'quel terminale non ha incassato', non 'dato assente'."""
    db = _db()
    _run(db.chiusure_pos_manuali.insert_many([
        _chiusura(0.0, "sumup"),
        _chiusura(200.0, "nexi"),
    ]))
    assert _run(chiusura_pos_del_giorno(db, "2026-08-06")) == 200.0


def test_senza_chiusure_resta_none_per_il_fallback_xml():
    db = _db()
    assert _run(chiusura_pos_del_giorno(db, "2026-08-06")) is None


def test_il_comportamento_di_nexi_da_solo_non_cambia():
    """Nessuna regressione per chi ha un solo terminale."""
    db = _db()
    _run(db.chiusure_pos_manuali.insert_many([
        _chiusura(1000.0, source="import_csv"),
        _chiusura(950.0),  # correzione manuale, prevale
    ]))
    assert _run(chiusura_pos_del_giorno(db, "2026-08-06")) == 950.0
