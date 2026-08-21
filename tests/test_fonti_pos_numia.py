"""Evidenze successive dello stesso incasso: manuale, Excel, terminale.

Il rischio non e' sbagliare un importo: e' che il disaccordo fra due fonti
sparisca. L'inserimento serale alimenta subito la Prima Nota, ma quando
arriva l'Excel ufficiale la nuova evidenza deve CONFERMARE se coincide e
SEGNALARE se no — mai sovrascrivere in silenzio, mai creare un secondo
movimento: e' sempre lo stesso ciclo di vendita.
"""
import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.services.scritture_contabili import (
    STATO_CONFERMATO,
    STATO_DIFFERENZA,
    STATO_PROVVISORIO,
    registra_chiusura_pos_reale,
    valuta_evidenza,
)

DATA = "2026-05-31"


def _run(awaitable):
    return asyncio.run(awaitable)


def _db():
    return MemorySheetsClient()["fonti_pos_test"]


def _chiusura(db):
    return _run(db.chiusure_pos_manuali.find_one({"data": DATA}))


# --- La regola, isolata ----------------------------------------------------

def test_il_manuale_alimenta_subito_ma_resta_provvisorio():
    esito = valuta_evidenza(None, 500.0, "manuale")
    assert esito["importo"] == 500.0
    assert esito["stato_dato"] == STATO_PROVVISORIO


def test_l_excel_che_coincide_conferma():
    esito = valuta_evidenza(
        {"importo": 500.0, "fonte_dato": "manuale"}, 500.0, "excel")
    assert esito["stato_dato"] == STATO_CONFERMATO
    assert esito["importo"] == 500.0


def test_l_excel_che_diverge_segnala_e_conserva_entrambi():
    """Il valore inserito la sera non deve sparire: e' l'unica traccia di
    cosa aveva letto l'operatore sul terminale."""
    esito = valuta_evidenza(
        {"importo": 500.0, "fonte_dato": "manuale"}, 520.0, "excel")
    assert esito["stato_dato"] == STATO_DIFFERENZA
    assert esito["differenza"] == 20.0
    assert esito["valori_per_fonte"] == {"manuale": 500.0, "excel": 520.0}
    # Vince la fonte piu' attendibile, ma il disaccordo resta scritto.
    assert esito["importo"] == 520.0


def test_il_terminale_prevale_sull_excel():
    esito = valuta_evidenza(
        {"importo": 520.0, "fonte_dato": "excel",
         "valori_per_fonte": {"manuale": 500.0, "excel": 520.0}},
        515.0, "terminale")
    assert esito["importo"] == 515.0
    assert esito["stato_dato"] == STATO_DIFFERENZA
    assert esito["valori_per_fonte"] == {
        "manuale": 500.0, "excel": 520.0, "terminale": 515.0}


def test_la_stessa_fonte_che_si_corregge_non_e_un_disaccordo():
    """Ricontrollo lo scontrino e correggo: non e' una fonte che smentisce."""
    esito = valuta_evidenza(
        {"importo": 500.0, "fonte_dato": "manuale"}, 480.0, "manuale")
    assert esito["importo"] == 480.0
    assert esito["stato_dato"] == STATO_PROVVISORIO


def test_un_precedente_senza_tracciatura_non_perde_il_suo_valore():
    """Le righe gia' in produzione non hanno valori_per_fonte."""
    esito = valuta_evidenza(
        {"importo": 500.0, "fonte_dato": "manuale"}, 520.0, "excel")
    assert esito["valori_per_fonte"]["manuale"] == 500.0


# --- Il percorso completo --------------------------------------------------

def test_manuale_poi_excel_conferma_senza_secondo_movimento():
    db = _db()
    _run(registra_chiusura_pos_reale(db, DATA, 500.0, gestore="nexi",
                                     fonte="manuale"))
    esito = _run(registra_chiusura_pos_reale(db, DATA, 500.0, gestore="nexi",
                                             fonte="excel"))

    assert esito["stato_dato"] == STATO_CONFERMATO
    assert len(_run(db.chiusure_pos_manuali.find({}).to_list(10))) == 1
    uscite = _run(db.prima_nota_cassa.find(
        {"source": "corrispettivo_import"}).to_list(10))
    assert len(uscite) == 1 and uscite[0]["importo"] == 500.0


def test_manuale_poi_excel_diverso_segnala_e_non_duplica():
    db = _db()
    _run(registra_chiusura_pos_reale(db, DATA, 500.0, gestore="nexi",
                                     fonte="manuale"))
    esito = _run(registra_chiusura_pos_reale(db, DATA, 520.0, gestore="nexi",
                                             fonte="excel"))

    assert esito["stato_dato"] == STATO_DIFFERENZA
    assert esito["differenza_fonti"] == 20.0

    chiusura = _chiusura(db)
    assert chiusura["valori_per_fonte"] == {"manuale": 500.0, "excel": 520.0}
    assert chiusura["importo"] == 520.0
    # Una sola riga, una sola uscita: evidenze dello stesso ciclo.
    assert len(_run(db.chiusure_pos_manuali.find({}).to_list(10))) == 1
    uscite = _run(db.prima_nota_cassa.find(
        {"source": "corrispettivo_import"}).to_list(10))
    assert len(uscite) == 1 and uscite[0]["importo"] == 520.0


def test_manuale_poi_terminale_percorre_tutta_la_catena():
    db = _db()
    _run(registra_chiusura_pos_reale(db, DATA, 500.0, gestore="nexi",
                                     fonte="manuale"))
    _run(registra_chiusura_pos_reale(db, DATA, 520.0, gestore="nexi",
                                     fonte="excel"))
    esito = _run(registra_chiusura_pos_reale(db, DATA, 515.0, gestore="nexi",
                                             fonte="terminale"))

    assert esito["importo"] == 515.0
    assert _chiusura(db)["valori_per_fonte"] == {
        "manuale": 500.0, "excel": 520.0, "terminale": 515.0}


def test_il_doppio_caricamento_dello_stesso_excel_non_cambia_nulla():
    db = _db()
    _run(registra_chiusura_pos_reale(db, DATA, 520.0, gestore="nexi",
                                     fonte="excel"))
    esito = _run(registra_chiusura_pos_reale(db, DATA, 520.0, gestore="nexi",
                                             fonte="excel"))

    assert esito["action"] == "noop"
    assert len(_run(db.chiusure_pos_manuali.find({}).to_list(10))) == 1


def test_sumup_e_numia_non_si_confermano_a_vicenda():
    """Sono circuiti diversi: l'evidenza di uno non dice nulla dell'altro."""
    db = _db()
    _run(registra_chiusura_pos_reale(db, DATA, 500.0, gestore="nexi",
                                     fonte="manuale"))
    _run(registra_chiusura_pos_reale(db, DATA, 100.0, gestore="sumup",
                                     fonte="api"))

    righe = _run(db.chiusure_pos_manuali.find({"data": DATA}).to_list(10))
    per_gestore = {r["gestore"]: r for r in righe}
    assert per_gestore["numia"]["stato_dato"] == STATO_PROVVISORIO
    assert per_gestore["sumup"]["stato_dato"] == STATO_CONFERMATO
    assert per_gestore["numia"]["importo"] == 500.0


# --- Identita' del punto di incasso ----------------------------------------

def test_il_punto_vendita_si_normalizza():
    """Negli export reali lo stesso negozio compare con e senza apostrofo
    finale: come chiave spaccherebbe in due i raggruppamenti."""
    from app.services.pos_terminal_import import _normalizza_row

    def _riga(nome):
        return _normalizza_row({
            "Data e ora": "31/05/2026 20:33:50.000", "Importo": "96,50",
            "Stato operazione": "Acquisto approvato", "Punto vendita": nome,
            "ID Terminale / TML": "40086700", "MID": "8009890",
            "Circuito": "MASTERCARD", "ID Transazione": "581110431069267914",
        }, "export.csv")

    assert _riga("CERALDI CAFFE")["punto_vendita"] == "CERALDI CAFFE"
    assert _riga("CERALDI CAFFE'")["punto_vendita"] == "CERALDI CAFFE"
    assert _riga("CERALDI CAFFE’")["punto_vendita"] == "CERALDI CAFFE"


def test_la_riga_porta_l_identita_del_terminale():
    from app.services.pos_terminal_import import _normalizza_row

    riga = _normalizza_row({
        "Data e ora": "31/05/2026 20:33:50.000", "Importo": "96,50",
        "Stato operazione": "Acquisto approvato", "Punto vendita": "CERALDI CAFFE",
        "ID Terminale / TML": "40086700", "MID": "8009890",
        "Circuito": "MASTERCARD", "ID Transazione": "581110431069267914",
    }, "export.csv")

    assert riga["provider"] == "numia"
    assert riga["terminale"] == "40086700"
    assert riga["mid"] == "8009890"
    # Il "circuito" dell'export e' quello della CARTA, non il gestore.
    assert riga["circuito_carta"] == "MASTERCARD"
