"""Un solo parser buste paga, e un cedolino ordinario non è una tredicesima.

Fino al 19/09/2026 `parsers/busta_paga_multi_template.py` esisteva in due
copie. La copia `app/hr` decideva il tipo di cedolino cercando la parola
«TREDICESIMA» o «13MA» in **tutto** il testo del PDF. Ma quasi ogni cedolino
mensile porta la voce «Rateo 13ma Mensilita», quindi un marzo qualunque
risultava una tredicesima.

Non e' un'etichetta cosmetica: `tipo_cedolino` entra nella chiave documentale
del cedolino (`_cedolino_document_key`) e nella regola «13ma e 14ma restano
buste distinte». Un tipo sbagliato sposta l'identita' del documento.

La copia ERP aveva gia' la correzione, in entrambi i punti in cui il tipo si
determina: controllo limitato alle prime 80 righe, voci di maturazione
escluse (RATEO, MATURAT, ACCANTON...), marcatore di testata richiesto.
"""
import pytest

from app.hr.parsers import busta_paga_multi_template as copia_hr
from app.parsers import busta_paga_multi_template as motore

CEDOLINO_ORDINARIO = """CERALDI GROUP S.R.L.
CEDOLINO PAGA  PERIODO DI PAGA  MARZO 2026
ROSSI MARIO
C00001 Retribuzione 9,54850 79,99992 ORE 763,48
C50000 Rateo 13ma Mensilita 63,62
C50022 Rateo 14ma Mensilita 63,62
NETTO DEL MESE 1.234,56
"""

TREDICESIMA_VERA = """CERALDI GROUP S.R.L.
CEDOLINO PAGA  TREDICESIMA 2026
ROSSI MARIO
C00001 Retribuzione 1.396,08
NETTO DEL MESE 1.234,56
"""


# Deliberatamente dal lato HR: era quello che sbagliava. Se la copia torna,
# questi test tornano rossi.
@pytest.mark.parametrize("nome_parser", [
    "parse_template_csc_napoli",
    "parse_template_zucchetti_new",
])
def test_un_cedolino_ordinario_con_rateo_non_e_una_tredicesima(nome_parser):
    """Il rateo di 13ma sta su quasi ogni busta: non fa la tredicesima."""
    parsa = getattr(copia_hr, nome_parser)
    assert parsa(CEDOLINO_ORDINARIO).get("tipo_cedolino") == "mensile"


@pytest.mark.parametrize("nome_parser", [
    "parse_template_csc_napoli",
    "parse_template_zucchetti_new",
])
def test_una_tredicesima_vera_resta_riconosciuta(nome_parser):
    """La correzione non deve spegnere il riconoscimento buono."""
    parsa = getattr(copia_hr, nome_parser)
    assert parsa(TREDICESIMA_VERA).get("tipo_cedolino") == "tredicesima"


def test_il_lato_hr_usa_lo_stesso_parser():
    for nome in (
        "parse_busta_paga_multi",
        "parse_busta_paga_from_bytes",
        "parse_template_csc_napoli",
        "parse_template_zucchetti_new",
        "detect_cessazione",
        "extract_summary",
    ):
        assert getattr(copia_hr, nome) is getattr(motore, nome), (
            f"{nome} sul lato HR non e' la funzione del modulo unico."
        )


def test_le_tre_funzioni_del_ramo_hr_sono_nel_modulo_unico():
    """Erano l'unica cosa che la copia HR avesse in piu': fondere senza
    portarle avrebbe perso netto verificato, elementi retributivi e acconti."""
    for nome in ("_verifica_netto", "_elementi_retributivi", "_acconti_e_anticipazioni"):
        assert callable(getattr(motore, nome, None)), nome

    import inspect

    corpo = inspect.getsource(motore.parse_busta_paga_multi)
    for nome in ("_verifica_netto(", "_elementi_retributivi(", "_acconti_e_anticipazioni("):
        assert nome in corpo, (
            f"{nome} esiste ma nessuno la chiama: portata senza collegarla."
        )


def test_gli_importi_passano_dal_parser_italiano_canonico():
    """Anche dal lato HR: li' la conversione era scritta a mano."""
    import inspect

    assert "parse_importo_ita" in inspect.getsource(copia_hr.parse_importo)


def test_il_riepilogo_riporta_il_tipo_di_cedolino():
    """`extract_summary` del lato HR lo ometteva: a valle il tipo spariva."""
    riepilogo = copia_hr.extract_summary({"tipo_cedolino": "quattordicesima"})
    assert riepilogo["tipo_cedolino"] == "quattordicesima"
