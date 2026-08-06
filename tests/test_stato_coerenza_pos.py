"""Stati di riconciliazione POS.

La regola che questi test difendono e': un dato mancante non e' zero. Se
l'XML non e' arrivato, la giornata "attende XML" — non e' un ammanco di
tutto l'incasso. Un controllo che grida al lupo ogni mattina smette di
essere letto, e a quel punto non protegge piu' nulla.
"""
import pytest

from app.services.stato_coerenza_pos import (
    ACCREDITO_PARZIALE,
    ATTENDE_DATI,
    ATTENDE_XML,
    ATTESA_ACCREDITO,
    COMMISSIONI_DA_VERIFICARE,
    NON_QUADRATO,
    RICONCILIATO,
    circuiti_attesi,
    riepiloga,
    stato_giornata,
)


def _credito(importo, accreditato=0.0, commissioni=0.0, stato=None):
    riga = {"importo": importo, "accreditato_ec": accreditato,
            "commissioni": commissioni}
    if stato:
        riga["stato_riconciliazione"] = stato
    return riga


# --- Fase fiscale ----------------------------------------------------------

def test_senza_xml_la_giornata_attende_non_e_un_ammanco():
    esito = stato_giornata(elettronico_xml=None,
                           circuiti={"nexi": 500.0, "sumup": 100.0})
    assert esito["stato"] == ATTENDE_XML
    assert esito["differenza_fiscale"] is None   # NON -600
    assert esito["pos_complessivo"] == 600.0


def test_un_circuito_che_non_ha_risposto_e_dichiarato_mancante():
    esito = stato_giornata(elettronico_xml=600.0,
                           circuiti={"nexi": 500.0, "sumup": None})
    assert esito["stato"] == ATTENDE_DATI
    assert esito["circuiti_mancanti"] == ["sumup"]
    # 500 non viene spacciato per il totale del giorno.
    assert esito["differenza_fiscale"] is None


def test_uno_zero_dichiarato_e_un_dato_valido():
    """Diverso da 'non ha risposto': il terminale non ha incassato."""
    esito = stato_giornata(elettronico_xml=500.0,
                           circuiti={"nexi": 500.0, "sumup": 0.0})
    assert esito["circuiti_mancanti"] == []
    assert esito["differenza_fiscale"] == 0.0


def test_xml_uguale_alla_somma_dei_circuiti_quadra():
    """Esempio dell'utente: elettronico 600 = Nexi 500 + SumUp 100."""
    esito = stato_giornata(elettronico_xml=600.0,
                           circuiti={"nexi": 500.0, "sumup": 100.0})
    assert esito["differenza_fiscale"] == 0.0
    assert esito["stato"] == RICONCILIATO


def test_il_non_battuto_emerge_come_differenza_positiva():
    esito = stato_giornata(elettronico_xml=580.0,
                           circuiti={"nexi": 500.0, "sumup": 100.0})
    assert esito["stato"] == NON_QUADRATO
    assert esito["differenza_fiscale"] == 20.0


# --- Fase bancaria ---------------------------------------------------------

def test_credito_non_ancora_accreditato():
    esito = stato_giornata(elettronico_xml=100.0, circuiti={"sumup": 100.0},
                           crediti=[_credito(100.0)])
    assert esito["stato"] == ATTESA_ACCREDITO
    assert esito["accredito_atteso"] == 100.0


def test_accredito_al_netto_delle_commissioni_quadra():
    """98 accreditati + 2 di commissioni = 100 attesi."""
    esito = stato_giornata(elettronico_xml=100.0, circuiti={"sumup": 100.0},
                           crediti=[_credito(100.0, accreditato=98.0,
                                             commissioni=2.0)])
    assert esito["differenza_residua"] == 0.0
    assert esito["stato"] == RICONCILIATO


def test_accredito_parziale_resta_aperto():
    esito = stato_giornata(elettronico_xml=100.0, circuiti={"sumup": 100.0},
                           crediti=[_credito(100.0, accreditato=60.0)])
    assert esito["stato"] == ACCREDITO_PARZIALE
    assert esito["differenza_residua"] == 40.0


def test_una_trattenuta_anomala_ha_la_precedenza():
    esito = stato_giornata(
        elettronico_xml=100.0, circuiti={"sumup": 100.0},
        crediti=[_credito(100.0, accreditato=40.0,
                          stato=COMMISSIONI_DA_VERIFICARE)])
    assert esito["stato"] == COMMISSIONI_DA_VERIFICARE


def test_la_fase_fiscale_ha_la_precedenza_su_quella_bancaria():
    """Senza sapere l'importo giusto non ha senso attenderne l'accredito."""
    esito = stato_giornata(elettronico_xml=None, circuiti={"sumup": 100.0},
                           crediti=[_credito(100.0)])
    assert esito["stato"] == ATTENDE_XML


# --- Contatori -------------------------------------------------------------

def test_i_contatori_calano_quando_la_riconciliazione_avanza():
    prima = [
        stato_giornata(elettronico_xml=100.0, circuiti={"sumup": 100.0},
                       crediti=[_credito(100.0)]),
        stato_giornata(elettronico_xml=None, circuiti={"sumup": 100.0}),
    ]
    assert riepiloga(prima)["aperti"] == 2

    dopo = [
        stato_giornata(elettronico_xml=100.0, circuiti={"sumup": 100.0},
                       crediti=[_credito(100.0, accreditato=98.0,
                                         commissioni=2.0)]),
        stato_giornata(elettronico_xml=100.0, circuiti={"sumup": 100.0},
                       crediti=[_credito(100.0, accreditato=100.0)]),
    ]
    riepilogo = riepiloga(dopo)
    assert riepilogo["aperti"] == 0
    assert riepilogo["riconciliati"] == 2


# --- Lettura delle chiusure ------------------------------------------------

def test_un_circuito_configurato_senza_righe_resta_sconosciuto():
    attesi = circuiti_attesi([{"gestore": "nexi", "importo": 500.0}],
                             ["nexi", "sumup"])
    assert attesi == {"nexi": 500.0, "sumup": None}


def test_le_righe_storiche_senza_campo_gestore_sono_nexi():
    attesi = circuiti_attesi([{"importo": 500.0}], ["nexi", "sumup"])
    assert attesi["nexi"] == 500.0


def test_piu_righe_dello_stesso_circuito_si_sommano():
    attesi = circuiti_attesi(
        [{"gestore": "sumup", "importo": 60.0},
         {"gestore": "sumup", "importo": 40.0}],
        ["sumup"])
    assert attesi == {"sumup": 100.0}


@pytest.mark.parametrize("valore", [0, 0.0])
def test_una_chiusura_a_zero_non_diventa_sconosciuta(valore):
    attesi = circuiti_attesi([{"gestore": "sumup", "importo": valore}],
                             ["nexi", "sumup"])
    assert attesi["sumup"] == 0.0
    assert attesi["nexi"] is None
