"""P1 §6.2/§6.3 — Coerenza del mapping canonico tra piano numerico e piano CEE puntato
(schema canonico = CEE puntato, scelta utente). Verifica che:
- ogni conto numerico mappato punti a un conto puntato REALMENTE esistente;
- PUNTATO_A_CEE copra tutti i 30 conti puntati del piano base;
- i conti "solo civilistici" siano esplicitamente None (mapping lossy dichiarato)."""
import re
import pathlib

from app.services import mapping_piano_conti as mpc

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _conti_puntati_reali():
    """Estrae i codici puntati dal piano base di piano_conti.py."""
    src = (ROOT / "app" / "routers" / "accounting" / "piano_conti.py").read_text()
    # dentro STRUTTURA_BASE: {"codice": "05.01.01", ...}
    return set(re.findall(r'"codice": "(\d\d\.\d\d\.\d\d)"', src))


def test_ogni_numerico_mappa_a_puntato_esistente():
    reali = _conti_puntati_reali()
    assert reali, "nessun conto puntato estratto: struttura cambiata?"
    for num, punt in mpc.NUMERICO_A_PUNTATO.items():
        if punt is not None:
            assert punt in reali, f"{num} mappa a {punt} inesistente nel piano puntato"


def test_puntato_a_cee_copre_tutto_il_piano():
    reali = _conti_puntati_reali()
    mancanti = reali - set(mpc.PUNTATO_A_CEE)
    assert not mancanti, f"conti puntati senza voce CEE: {sorted(mancanti)}"


def test_voci_cee_hanno_sezione_valida():
    for codice, info in mpc.PUNTATO_A_CEE.items():
        assert info["sezione"] in ("SP", "CE")
        assert info["gruppo"] in ("attivo", "passivo", "patrimonio_netto", "ricavi", "costi")
        assert info["cee"]


def test_solo_civilistici_dichiarati():
    soli = mpc.numerico_solo_civilistici()
    # immobilizzazioni/ratei/riserve dettagliate non hanno equivalente puntato
    assert "110100" in soli  # costi di impianto (immob. immateriale)
    assert "170100" in soli  # ratei attivi
    assert "200200" in soli  # riserva sovrapprezzo
    # gli operativi invece devono mappare
    assert mpc.to_puntato("400100") == "05.01.01"  # materie prime
    assert mpc.to_puntato("160300") == "01.01.01"  # cassa
    assert mpc.to_puntato("230700") == "02.01.01"  # debiti fornitori


def test_helpers():
    assert mpc.voce_cee("05.01.01")["cee"] == "B.6"
    assert mpc.voce_cee("01.01.01")["sezione"] == "SP"
    assert mpc.to_puntato("999999") is None  # ignoto


def test_vista_derivata_cee_aggrega_i_conti():
    # i 3 conti ricavi puntati confluiscono nella voce CEE A.1 sommati
    saldi = {
        "04.01.01": 100.0, "04.01.02": 50.0, "04.01.03": 30.0,  # → A.1 = 180
        "05.01.01": 40.0, "05.01.02": 10.0,                     # → B.6 = 50
        "01.01.01": 500.0,                                       # → C.IV.3
        "ZZ.ZZ.ZZ": 999.0,                                       # ignoto → scartato
    }
    cee = mpc.classifica_saldi_cee(saldi)
    assert cee["A.1"]["saldo"] == 180.0
    assert cee["A.1"]["sezione"] == "CE" and cee["A.1"]["gruppo"] == "ricavi"
    assert set(cee["A.1"]["conti"]) == {"04.01.01", "04.01.02", "04.01.03"}
    assert cee["B.6"]["saldo"] == 50.0
    assert cee["C.IV.3"]["saldo"] == 500.0
    assert "ZZ.ZZ.ZZ" not in [c for v in cee.values() for c in v["conti"]]
