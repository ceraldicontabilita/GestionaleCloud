"""Regressione reale: EXTREME sulle caramelle non significa operatore TRE."""
from app.services import learning_machine_cdc as lm


def test_perfetti_frisk_extreme_non_e_telefonia():
    righe = [{"descrizione": "FRISK EXTREME BLACK X12"},
             {"descrizione": "ST.GOLIA EXTRAFORTE NEW ST. X 24"}]
    centro, config, _ = lm.classifica_fattura_per_centro_costo(
        "Perfetti Van Melle S.p.A.", "", righe)
    assert centro == "1.6_PRODOTTI_CONFEZIONATI"
    assert config["detraibilita_iva"] == 1.0
    assert "10.1_TELEFONIA" not in lm.punteggi_contenuto("", "", righe)


def test_sigle_corte_non_corrispondono_a_parti_di_parole():
    for descrizione in ("EXTREME", "ULTIMATE", "VITAMINE", "VETRERIA"):
        assert not lm._keyword_presente("tre", descrizione)
        assert not lm._keyword_presente("tim", descrizione)
    assert lm._keyword_presente("tre", "Canone WIND TRE")
    assert lm._keyword_presente("tim", "TIM S.p.A.")
    assert lm._keyword_presente("gas", "Fornitura GAS")


def test_telefonia_reale_restera_telefonia():
    centro, _, _ = lm.classifica_fattura_per_centro_costo("TIM S.p.A.", "Canone fibra internet")
    assert centro == "10.1_TELEFONIA"
