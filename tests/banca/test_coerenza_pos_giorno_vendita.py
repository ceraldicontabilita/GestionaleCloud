"""FIX 18/07/2026 Coerenza POS: gli accrediti NUMIA riportano in
descrizione il giorno di VENDITA ("INC.POS ... DEL 02/04/26 ..."), che è
quello da confrontare con il corrispettivo XML — non il giorno di
accredito (weekend e festivi arrivano accumulati il lunedì)."""
from app.routers.pos_corrispettivi_check import _giorno_operazione_pos


def test_giorno_vendita_dalla_descrizione():
    assert _giorno_operazione_pos(
        "INC.POS CARTE CREDIT - NUMIA-INTER  DEL 02/04/26 PDV 3757283/00011 CERALDI CAFFE NA",
        "2026-04-03") == "2026-04-02"
    assert _giorno_operazione_pos(
        "INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 16/07/26 PDV 3757283/00012",
        "2026-07-17") == "2026-07-16"


def test_fallback_data_accredito():
    assert _giorno_operazione_pos("VERSAMENTO CONTANTI", "2026-04-05") == "2026-04-05"
    assert _giorno_operazione_pos(None, "2026-04-05") == "2026-04-05"
