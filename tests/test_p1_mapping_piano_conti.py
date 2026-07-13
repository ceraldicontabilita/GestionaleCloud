"""P1 §6.2/§6.3 — Mapping verso il piano dei conti UFFICIALE CEE (unico canonico,
scelta utente). Verifica che ogni codice operativo interno mappi a un conto ufficiale
REALMENTE esistente nel bilancio, e che la vista derivata classifichi correttamente."""
from app.services import mapping_piano_conti as mpc
from app.services import piano_conti_ufficiale as pcu


def test_ogni_operativo_mappa_a_conto_ufficiale_esistente():
    for op, uff in mpc.OPERATIVO_A_UFFICIALE.items():
        # target valido: conto ufficiale a codice pieno OPPURE macro-gruppo (2 cifre)
        assert uff in pcu.CONTI_UFFICIALI or uff in pcu.MACRO_UFFICIALE, \
            f"{op} → {uff} non esiste nel piano ufficiale"


def test_corrispondenze_chiave_dal_bilancio_reale():
    # verifiche puntuali sui codici reali del bilancio Ceraldi
    assert mpc.operativo_a_ufficiale("01.01.02") == "19.01.01"   # Banca c/c
    assert mpc.operativo_a_ufficiale("01.01.01") == "19.03.03"   # Cassa contanti
    assert mpc.operativo_a_ufficiale("02.01.01") == "33.03.01"   # Fornitori terzi Italia
    assert mpc.operativo_a_ufficiale("02.04.01") == "29.01.01"   # Fondo TFR
    assert mpc.operativo_a_ufficiale("05.01.01") == "55.01.07"   # Acquisti merci
    assert mpc.operativo_a_ufficiale("05.03.01") == "67.01.01"   # Retribuzioni lorde
    assert mpc.operativo_a_ufficiale("04.01.01") == "47.01.03"   # Vendita merci
    assert mpc.descrizione_ufficiale("55.01.07") == "Acquisti merci"


def test_piano_ufficiale_caricato():
    assert len(pcu.CONTI_UFFICIALI) > 150
    assert pcu.CONTI_UFFICIALI["19.01.01"] == "Banca c/c"
    assert pcu.sezione_di("55.01.07")[1] == "costi"
    assert pcu.sezione_di("19.01.01")[0] == "SP"


def test_vista_derivata_ufficiale():
    # saldi operativi → raggruppati sui conti ufficiali
    saldi = {
        "05.01.01": 100.0,   # → 55.01.07 Acquisti merci (costi)
        "05.01.02": 40.0,    # → 55.01.01 Acquisti materie prime (costi)
        "04.01.01": 500.0,   # → 47.01.03 Vendita merci (ricavi)
        "04.01.02": 50.0,    # → 47.01.03 Vendita merci (ricavi) — stesso conto
        "01.01.02": 3000.0,  # → 19.01.01 Banca (attivo)
        "ZZ.ZZ.ZZ": 999.0,   # ignoto → scartato
    }
    cee = mpc.classifica_saldi_ufficiale(saldi)
    assert cee["47.01.03"]["saldo"] == 550.0   # 500 + 50 sullo stesso conto ufficiale
    assert cee["47.01.03"]["gruppo"] == "ricavi"
    assert set(cee["47.01.03"]["conti_operativi"]) == {"04.01.01", "04.01.02"}
    assert cee["55.01.07"]["saldo"] == 100.0
    assert cee["19.01.01"]["sezione"] == "SP"
    assert "ZZ.ZZ.ZZ" not in [c for v in cee.values() for c in v["conti_operativi"]]
