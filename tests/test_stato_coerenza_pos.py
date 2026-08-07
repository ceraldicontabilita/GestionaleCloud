"""Catene di controllo POS, indipendenti.

La regola che questi test difendono e' una sola, ed e' quella che l'utente ha
ripetuto due volte: **l'XML RT non riparte i pagamenti elettronici**. Non
esiste da nessuna parte un confronto `XML = Nexi + SumUp`. L'XML si confronta
con la chiusura di cassa, e basta; il POS si ricostruisce dai terminali.

La seconda regola e' che un dato mancante non e' zero: senza un terminale il
contante resta provvisorio, mai stimato con un importo fiscale.
"""
import pytest

from app.services.stato_coerenza_pos import (
    ACCREDITO_ATTESA,
    ACCREDITO_OK,
    ACCREDITO_PARZIALE,
    CASSA_ATTENDE_POS,
    CASSA_OK,
    CASSA_PROVVISORIO,
    COMMISSIONI_DA_VERIFICARE,
    FISCALE_ATTENDE_CASSA,
    FISCALE_ATTENDE_XML,
    FISCALE_DIFFORME,
    FISCALE_OK,
    catena_accredito,
    catena_cassa,
    catena_fiscale,
    catena_pos_reale,
    circuiti_attesi,
    riepiloga,
    stato_giornata,
)


# --- Catena fiscale: cassa contro XML, mai contro il POS -------------------

def test_il_controllo_fiscale_confronta_la_cassa_con_l_xml():
    esito = catena_fiscale(totale_xml=1000.0, chiusura_cassa=1000.0)
    assert esito["stato"] == FISCALE_OK
    assert esito["differenza"] == 0.0


def test_una_difformita_resta_visibile_e_non_viene_appianata():
    esito = catena_fiscale(totale_xml=1000.0, chiusura_cassa=1010.0)
    assert esito["stato"] == FISCALE_DIFFORME
    assert esito["differenza"] == 10.0


@pytest.mark.parametrize(("xml", "cassa", "atteso"), [
    (None, 1000.0, FISCALE_ATTENDE_XML),
    (1000.0, None, FISCALE_ATTENDE_CASSA),
    (None, None, FISCALE_ATTENDE_XML),
])
def test_una_fonte_mancante_mette_in_attesa_non_in_errore(xml, cassa, atteso):
    esito = catena_fiscale(totale_xml=xml, chiusura_cassa=cassa)
    assert esito["stato"] == atteso
    assert esito["differenza"] is None


def test_la_catena_fiscale_non_conosce_i_circuiti():
    """Nessun campo del controllo fiscale parla di Nexi o SumUp: e' la prova
    strutturale che la formula vietata non puo' rientrare da qui."""
    esito = catena_fiscale(totale_xml=1000.0, chiusura_cassa=1000.0)
    assert set(esito) == {"totale_xml", "chiusura_cassa", "differenza",
                          "stato", "stato_etichetta"}


# --- Catena POS reale: solo terminali --------------------------------------

def test_il_pos_reale_e_la_somma_dei_terminali():
    pos = catena_pos_reale({"nexi": 500.0, "sumup": 100.0})
    assert pos["totale_pos_reale"] == 600.0
    assert pos["completo"] is True


def test_un_terminale_muto_rende_il_totale_incompleto():
    pos = catena_pos_reale({"nexi": 500.0, "sumup": None})
    assert pos["circuiti_mancanti"] == ["sumup"]
    assert pos["completo"] is False
    # Il parziale resta leggibile, ma dichiarato tale.
    assert pos["totale_pos_reale"] == 500.0


def test_uno_zero_dichiarato_e_un_dato_valido():
    pos = catena_pos_reale({"nexi": 500.0, "sumup": 0.0})
    assert pos["circuiti_mancanti"] == []
    assert pos["completo"] is True
    assert pos["totale_pos_reale"] == 500.0


# --- Catena cassa: contante ------------------------------------------------

def test_il_contante_atteso_si_calcola_dai_pos_reali():
    """Esempio dell'utente: cassa 1.000 = 400 contanti + 500 Nexi + 100 SumUp."""
    pos = catena_pos_reale({"nexi": 500.0, "sumup": 100.0})
    esito = catena_cassa(chiusura_cassa=1000.0, pos=pos)
    assert esito["contante_atteso"] == 400.0
    assert esito["determinabile"] is True
    assert esito["stato"] == CASSA_OK


def test_senza_un_terminale_il_contante_resta_provvisorio():
    """Non si stima con l'XML: sarebbe una giacenza mai verificata."""
    pos = catena_pos_reale({"nexi": 500.0, "sumup": None})
    esito = catena_cassa(chiusura_cassa=1000.0, pos=pos)
    assert esito["stato"] == CASSA_PROVVISORIO
    assert esito["determinabile"] is False


def test_senza_nessun_pos_il_contante_non_e_determinabile():
    pos = catena_pos_reale({"nexi": None, "sumup": None})
    esito = catena_cassa(chiusura_cassa=1000.0, pos=pos)
    assert esito["stato"] == CASSA_ATTENDE_POS
    assert esito["contante_atteso"] is None


def test_senza_chiusura_di_cassa_non_si_calcola_il_contante():
    pos = catena_pos_reale({"nexi": 500.0, "sumup": 100.0})
    esito = catena_cassa(chiusura_cassa=None, pos=pos)
    assert esito["contante_atteso"] is None


# --- Catena accrediti ------------------------------------------------------

def test_il_credito_non_ancora_versato_resta_in_attesa():
    esito = catena_accredito("sumup", venduto=100.0)
    assert esito["stato"] == ACCREDITO_ATTESA


def test_sumup_quadra_col_netto_piu_le_commissioni():
    """98 sulla Mastercard + 2 di trattenuta = 100 di venduto."""
    esito = catena_accredito("sumup", venduto=100.0,
                             accreditato=98.0, commissioni=2.0)
    assert esito["residuo"] == 0.0
    assert esito["stato"] == ACCREDITO_OK


def test_numia_quadra_col_lordo_senza_commissioni():
    """Numia versa il lordo: le sue commissioni seguono un ciclo separato."""
    esito = catena_accredito("nexi", venduto=500.0, accreditato=500.0)
    assert esito["residuo"] == 0.0
    assert esito["stato"] == ACCREDITO_OK


def test_rimborsi_e_chargeback_riducono_l_accredito_atteso():
    esito = catena_accredito("sumup", venduto=100.0, rimborsi=30.0,
                             chargeback=20.0, accreditato=48.0, commissioni=2.0)
    assert esito["residuo"] == 0.0
    assert esito["stato"] == ACCREDITO_OK


def test_un_accredito_parziale_resta_aperto():
    esito = catena_accredito("sumup", venduto=100.0, accreditato=60.0)
    assert esito["stato"] == ACCREDITO_PARZIALE
    assert esito["residuo"] == 40.0


def test_una_trattenuta_anomala_ha_la_precedenza():
    esito = catena_accredito("sumup", venduto=100.0, accreditato=40.0,
                             anomalia_commissioni=True)
    assert esito["stato"] == COMMISSIONI_DA_VERIFICARE


# --- Giornata intera -------------------------------------------------------

def test_le_catene_non_si_compensano_fra_loro():
    """Il POS quadra perfettamente, ma la cassa non torna con l'XML: la
    giornata NON e' completata. E' il punto che l'utente ha chiesto due volte."""
    giornata = stato_giornata(
        totale_xml=1000.0, chiusura_cassa=1010.0,
        circuiti={"nexi": 500.0, "sumup": 100.0},
        accrediti={"nexi": {"accreditato": 500.0},
                   "sumup": {"accreditato": 98.0, "commissioni": 2.0}},
    )
    assert giornata["pos_reale"]["completo"] is True
    assert giornata["cassa"]["stato"] == CASSA_OK
    assert giornata["fiscale"]["stato"] == FISCALE_DIFFORME
    assert giornata["completata"] is False
    assert giornata["catene_aperte"] == 1


def test_una_giornata_completa_ha_tutte_le_catene_chiuse():
    giornata = stato_giornata(
        totale_xml=1000.0, chiusura_cassa=1000.0,
        circuiti={"nexi": 500.0, "sumup": 100.0},
        accrediti={"nexi": {"accreditato": 500.0},
                   "sumup": {"accreditato": 98.0, "commissioni": 2.0}},
    )
    assert giornata["completata"] is True
    assert [c["stato"] for c in giornata["accrediti"]] == [
        ACCREDITO_OK, ACCREDITO_OK]


def test_nessuna_catena_confronta_l_xml_col_pos():
    """Con XML e POS deliberatamente diversi, nessuna catena se ne accorge:
    e' corretto, perche' non e' un confronto che ha senso fare."""
    giornata = stato_giornata(
        totale_xml=1000.0, chiusura_cassa=1000.0,
        circuiti={"nexi": 500.0, "sumup": 100.0},
        accrediti={"nexi": {"accreditato": 500.0},
                   "sumup": {"accreditato": 98.0, "commissioni": 2.0}},
    )
    # elettronico XML ipotetico 600 vs POS 600: nessun campo lo registra.
    assert "differenza_fiscale" not in giornata
    assert "elettronico_xml" not in giornata["fiscale"]


def test_i_contatori_calano_quando_le_catene_si_chiudono():
    aperta = stato_giornata(totale_xml=1000.0, chiusura_cassa=None,
                            circuiti={"nexi": None})
    chiusa = stato_giornata(
        totale_xml=1000.0, chiusura_cassa=1000.0, circuiti={"nexi": 1000.0},
        accrediti={"nexi": {"accreditato": 1000.0}})

    assert riepiloga([aperta, chiusa])["giornate_aperte"] == 1
    assert riepiloga([chiusa, chiusa])["giornate_aperte"] == 0
    assert riepiloga([chiusa, chiusa])["giornate_complete"] == 2


# --- Lettura delle chiusure ------------------------------------------------

def test_un_circuito_configurato_senza_righe_resta_sconosciuto():
    attesi = circuiti_attesi([{"gestore": "nexi", "importo": 500.0}],
                             ["numia", "sumup"])
    assert attesi == {"numia": 500.0, "sumup": None}


def test_le_righe_storiche_senza_campo_gestore_sono_nexi():
    assert circuiti_attesi([{"importo": 500.0}], ["numia", "sumup"])["numia"] == 500.0


def test_piu_righe_dello_stesso_circuito_si_sommano():
    attesi = circuiti_attesi(
        [{"gestore": "sumup", "importo": 60.0},
         {"gestore": "sumup", "importo": 40.0}], ["sumup"])
    assert attesi == {"sumup": 100.0}


@pytest.mark.parametrize("valore", [0, 0.0])
def test_una_chiusura_a_zero_non_diventa_sconosciuta(valore):
    attesi = circuiti_attesi([{"gestore": "sumup", "importo": valore}],
                             ["numia", "sumup"])
    assert attesi["sumup"] == 0.0
    assert attesi["numia"] is None
