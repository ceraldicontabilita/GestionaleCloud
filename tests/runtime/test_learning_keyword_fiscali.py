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


def test_acquisto_condizionatore_taxonomia_cespite_senza_deduzione_immediata():
    righe = [{"descrizione": "Condizionatore split Daikin", "prezzo_totale": 1500}]
    centro, config, confidence = lm.classifica_fattura_per_centro_costo("Fornitore Test Srl", "", righe)
    assert centro == "15.1_ACQUISTO_BENI_STRUMENTALI"
    assert config["detraibilita_iva"] == 1 and config["deducibilita_ires"] == 0
    assert config["deduzione_per_ammortamento"] is True and confidence >= 0.6
    assert lm.contenuto_decide_con_margine("", "", righe) is True


def test_cespite_ordinario_non_confuso_con_manutenzione_noleggio_auto_o_righe_miste():
    for testo in ("Manutenzione condizionatore split Daikin", "Canone noleggio condizionatore split Daikin",
                  "Acquisto autovettura nuova", "Acquisto immobile strumentale",
                  "Computer tablet smartphone iPhone"):
        assert not lm._righe_beni_strumentali([{"descrizione": testo, "prezzo_totale": 1500}])
    assert not lm._righe_beni_strumentali([
        {"descrizione": "Condizionatore split Daikin", "prezzo_totale": 1500},
        {"descrizione": "Articolo non identificato", "prezzo_totale": 1000},
    ])
    assert not lm._righe_beni_strumentali([{"descrizione": "Condizionatore split Daikin", "prezzo_totale": 500}])
    assert not lm._righe_beni_strumentali([{"descrizione": "Condizionatore split Daikin", "prezzo_totale": float("inf")}])


def test_accessori_e_impianti_di_veicoli_non_sono_cespiti_iva_ordinaria():
    for veicolo in ("auto", "autovettura", "vettura", "veicolo", "motociclo", "automezzo", "van", "camion"):
        righe = [{"descrizione": f"Condizionatore split Daikin per {veicolo}", "prezzo_totale": 1500}]
        assert not lm._righe_beni_strumentali(righe)
        centro, _, _ = lm.classifica_fattura_per_centro_costo("Fornitore Test Srl", "", righe)
        assert centro != "15.1_ACQUISTO_BENI_STRUMENTALI"
