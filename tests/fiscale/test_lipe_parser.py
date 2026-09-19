"""La LIPE si legge per posizione, e l'aritmetica del modulo fa da prova.

Il livello testo del PDF restituisce le celle mescolate alle caselle di
spunta. Su VP14 di febbraio 2026 la sequenza grezza e'
`1 , o a credito 2 18.058, 9 2`: `1` e `2` sono spunte, il valore e'
18.058,92. Un parser che legge in ordine scrive **218.058,92** — un errore da
200.000 EUR su un numero che finisce in dichiarazione.

Le righe qui sotto riproducono le ascisse vere del modulo ministeriale,
misurate sulla LIPE 2026 del titolare (`LIPE_2026_407141844.pdf`, tre
periodi, tutti quadrati). Il PDF vero non entra nel repository: porta codice
fiscale e partita IVA.
"""
import pytest

from app.services import lipe_parser as mod


def _p(testo, x0, top=280.0):
    """Una parola nel formato di pdfplumber."""
    return {"text": testo, "x0": x0, "x1": x0 + 6.0 * len(testo), "top": top}


def _cella_debiti(intero, dec1, dec2, top=280.0):
    """Una cella della colonna DEBITI alle sue ascisse reali."""
    return [
        {"text": intero, "x0": 388.0 - 6.0 * len(intero), "x1": 388.0, "top": top},
        _p(dec1, 392.5, top), _p(dec2, 407.5, top),
    ]


def _cella_crediti(intero, dec1, dec2, top=280.0):
    return [
        {"text": intero, "x0": 532.0 - 6.0 * len(intero), "x1": 532.0, "top": top},
        _p(dec1, 536.0, top), _p(dec2, 551.0, top),
    ]


#: Le spunte e le diciture che stanno sulla stessa riga dei valori.
ARREDO_RIGA = [_p("1", 323.0), _p("o", 429.0), _p("a", 435.0),
               _p("credito", 441.0), _p("2", 467.0)]


# ── La trappola delle caselle di spunta ────────────────────────────────────

def test_la_spunta_non_si_attacca_al_numero():
    """Il caso reale di VP14 febbraio 2026."""
    riga = ARREDO_RIGA + _cella_crediti("18.058,", "9", "2")

    debiti, crediti = mod.valori_riga(riga, top=280.0)

    assert crediti == 18058.92, (
        "La spunta «2» a x=467 e' finita dentro il valore: 218.058,92 invece "
        "di 18.058,92. Le celle si leggono alle loro ascisse, non in ordine."
    )
    assert debiti is None


def test_la_riga_metodo_non_e_un_valore():
    """VP13 porta «Metodo 1 2» e una virgola: nessun importo."""
    riga = [_p("Metodo", 377.0), _p("1", 402.0), _p("2", 467.0),
            {"text": ",", "x0": 530.0, "x1": 532.0, "top": 280.0}]

    assert mod.valori_riga(riga, top=280.0) == (None, None)


# ── Le due colonne ─────────────────────────────────────────────────────────

def test_un_importo_a_debito_finisce_nella_colonna_debiti():
    riga = _cella_debiti("5.047,", "4", "3")
    assert mod.valori_riga(riga, top=280.0) == (5047.43, None)


def test_un_importo_a_credito_finisce_nella_colonna_crediti():
    riga = _cella_crediti("12.779,", "6", "1")
    assert mod.valori_riga(riga, top=280.0) == (None, 12779.61)


def test_le_due_colonne_convivono_sulla_stessa_riga():
    riga = _cella_debiti("10,", "8", "2") + _cella_crediti("7.732,", "1", "8")
    assert mod.valori_riga(riga, top=280.0) == (10.82, 7732.18)


# ── Celle vuote: mai zero ──────────────────────────────────────────────────

def test_una_cella_vuota_resta_nulla():
    """Febbraio 2026 ha VP2 in bianco: e' un fatto del documento."""
    riga = [{"text": ",", "x0": 386.0, "x1": 388.0, "top": 280.0}]
    assert mod.valori_riga(riga, top=280.0) == (None, None)


def test_una_riga_di_un_altro_rigo_non_viene_letta():
    """La tolleranza verticale non deve pescare la riga sopra o sotto."""
    riga = _cella_debiti("999,", "9", "9", top=256.0)
    assert mod.valori_riga(riga, top=280.0) == (None, None)


@pytest.mark.parametrize("intero,dec1,dec2,atteso", [
    ("50.278,", "9", "0", 50278.90),
    ("61.312,", "7", "8", 61312.78),
    ("10,", "8", "2", 10.82),
    ("265,", "3", "8", 265.38),
])
def test_le_cifre_separate_si_ricompongono(intero, dec1, dec2, atteso):
    assert mod.valore_cella(_cella_debiti(intero, dec1, dec2), mod.ANCORA_DEBITI) == atteso


# ── L'aritmetica del modulo come prova ─────────────────────────────────────

GENNAIO = {
    "iva_esigibile": 5047.43, "iva_detratta": 12779.61,
    "iva_dovuta_o_credito": 7732.18,
    "debito_periodo_precedente": None, "credito_periodo_precedente": None,
    "iva_da_versare_o_credito": 7732.18,
}
FEBBRAIO = {
    "iva_esigibile": 10.82, "iva_detratta": 10337.56,
    "iva_dovuta_o_credito": 10326.74,
    "debito_periodo_precedente": None, "credito_periodo_precedente": 7732.18,
    "iva_da_versare_o_credito": 18058.92,
}
MARZO = {
    "iva_esigibile": 6131.26, "iva_detratta": 6396.64,
    "iva_dovuta_o_credito": 265.38,
    "debito_periodo_precedente": None, "credito_periodo_precedente": 18058.92,
    "iva_da_versare_o_credito": 18324.30,
}


@pytest.mark.parametrize("periodo", [GENNAIO, FEBBRAIO, MARZO])
def test_i_tre_periodi_veri_quadrano(periodo):
    """I valori misurati sulla LIPE 2026 del titolare."""
    assert mod.quadra(periodo) is True


def test_la_quadratura_smaschera_la_spunta_attaccata():
    """Il numero sbagliato che il parser ingenuo produceva non quadra."""
    rotto = dict(FEBBRAIO, iva_da_versare_o_credito=218058.92)
    assert mod.quadra(rotto) is False


def test_la_quadratura_smaschera_un_rigo_letto_male():
    assert mod.quadra(dict(MARZO, iva_detratta=63966.40)) is False
