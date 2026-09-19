"""Audit 19/09/2026, punto 2 — classify_asset() riconosceva solo 7 delle 11
categorie di CATEGORIE_CESPITI: mancavano fabbricati, automezzi, autovetture,
software. Le nuove keyword devono riconoscere gli acquisti veri SENZA creare
falsi positivi sui costi ricorrenti già esclusi (canone/abbonamento/noleggio/
leasing per software e auto, affitto/locazione per gli immobili)."""
from app.routers.cespiti import classify_asset, CATEGORIE_CESPITI


def test_tutte_le_categorie_hanno_almeno_una_keyword_dedicata():
    """Nessuna delle 11 categorie del registro deve restare senza copertura
    nella classificazione automatica."""
    riconoscibili = {
        "capannone acquisto immobile strumentale fabbricato",
        "impianto climatizzazione",
        "sfogliatrice planetaria",
        "lavastoviglie industriale",
        "mobile arredo poltroncina",
        "veicolo commerciale furgone automezzo autocarro",
        "acquisto autovettura nuova vettura aziendale",
        "computer stampante monitor",
        "licenza software perpetua",
        "frigo congelatore abbattitore",
        "forno piastra cottura",
    }
    categorie_trovate = set()
    for testo in riconoscibili:
        cat = classify_asset(testo, 10000)
        if cat:
            categorie_trovate.add(cat)
    assert categorie_trovate == set(CATEGORIE_CESPITI.keys())


# ---------------------------------------------------------------- software

def test_licenza_software_perpetua_e_un_cespite():
    assert classify_asset("Licenza software gestionale uso perpetuo", 2000.0) == "software"


def test_canone_software_saas_non_e_un_cespite():
    """Un canone ricorrente (SaaS) resta un costo, mai un cespite, anche se
    parla di 'software'."""
    assert classify_asset("Canone software gestionale mensile", 2000.0) is None


def test_abbonamento_software_non_e_un_cespite():
    assert classify_asset("Abbonamento annuale software contabilità", 900.0) is None


# ---------------------------------------------------------------- automezzi/autovetture

def test_acquisto_furgone_e_un_automezzo():
    assert classify_asset("Fornitura e trasporto furgone Fiat Ducato nuovo", 22000.0) == "automezzi"


def test_acquisto_autovettura_e_unautovettura():
    assert classify_asset("Acquisto autovettura Fiat Panda Hybrid", 16000.0) == "autovetture"


def test_noleggio_auto_lungo_termine_non_e_un_cespite():
    assert classify_asset("Noleggio auto lungo termine Fiat Panda gennaio 2026", 500.0) is None


def test_leasing_autovettura_non_e_un_cespite():
    assert classify_asset("Leasing autovettura Audi A3 canone mensile", 600.0) is None


# ---------------------------------------------------------------- fabbricati

def test_acquisto_immobile_strumentale_e_un_fabbricato():
    assert classify_asset("Acquisto immobile strumentale Via Roma 12", 180000.0) == "fabbricati"


def test_capannone_e_un_fabbricato():
    assert classify_asset("Capannone artigianale zona industriale", 220000.0) == "fabbricati"


def test_affitto_locale_commerciale_non_e_un_cespite():
    assert classify_asset("Affitto locale commerciale mese di gennaio", 1200.0) is None


def test_locazione_capannone_non_e_un_cespite():
    assert classify_asset("Locazione capannone deposito merci", 2500.0) is None


# ---------------------------------------------------------------- regressione categorie esistenti

def test_regressione_categorie_esistenti_restano_riconosciute():
    assert classify_asset("Forno industriale 6 teglie", 3500.0) == "forni"
    assert classify_asset("Frigo bar 400 litri", 900.0) == "frigoriferi"
    assert classify_asset("Lavastoviglie industriale a cesti", 3000.0) == "attrezzature"


def test_regressione_esclusioni_esistenti_restano_escluse():
    assert classify_asset("Caffè in grani 1kg Kimbo", 900.0) is None
    assert classify_asset("Consulenza fiscale mensile", 900.0) is None
