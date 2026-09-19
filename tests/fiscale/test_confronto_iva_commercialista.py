"""Il confronto dice dove divergiamo dal commercialista, senza inventare.

Tre fonti: il nostro calcolo, la LIPE (documento canonico dell'IVA mensile) e
i prospetti F24 da pagare. Le insidie stanno tutte nel non trasformare
un'assenza in uno scostamento:

- un mese che non sappiamo calcolare e' un «non lo so», non uno scarto;
- una LIPE mancante non rende sbagliato il nostro numero;
- una LIPE **a credito** non genera nessun F24: l'assenza del versamento e'
  corretta. Il caso da segnalare e' l'opposto.

I valori sono quelli veri della LIPE 2026 e dei prospetti F24 in archivio.
"""
import asyncio

import pytest

from app.services import confronto_iva_commercialista as mod


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


NOSTRO = {
    "stato_calcolo": "CALCOLATA", "attendibile": True,
    "iva_vendite": 6131.26, "iva_acquisti": 6396.64, "saldo": -265.38,
    "motivi": [], "conteggi": {},
}
LIPE_MARZO = {
    "periodo": "2026-03", "iva_esigibile": 6131.26, "iva_detratta": 6396.64,
    "iva_da_versare_o_credito": 18324.30,
    "iva_da_versare_o_credito_segno": "credito", "quadratura_ok": True,
}


# ── Allineato, e cosa conta come allineato ────────────────────────────────

def test_i_numeri_uguali_danno_allineato():
    riga = mod.confronta_periodo("2026-03", NOSTRO, LIPE_MARZO, None)
    assert riga["esito"] == "allineato"
    assert riga["scarti"] == {"iva_vendite": 0.0, "iva_acquisti": 0.0}


def test_un_centesimo_di_differenza_resta_allineato():
    lipe = dict(LIPE_MARZO, iva_esigibile=6131.27)
    assert mod.confronta_periodo("2026-03", NOSTRO, lipe, None)["esito"] == "allineato"


def test_uno_scostamento_vero_si_vede_e_si_quantifica():
    """Gennaio 2026: la LIPE detrae 12.779,61, noi 7.773,73."""
    nostro = dict(NOSTRO, iva_vendite=5027.88, iva_acquisti=7773.73)
    lipe = dict(LIPE_MARZO, periodo="2026-01",
                iva_esigibile=5047.43, iva_detratta=12779.61)

    riga = mod.confronta_periodo("2026-01", nostro, lipe, None)

    assert riga["esito"] == "scostamento"
    assert riga["scarti"]["iva_vendite"] == -19.55
    assert riga["scarti"]["iva_acquisti"] == -5005.88


# ── Le assenze non sono scostamenti ───────────────────────────────────────

def test_un_mese_che_non_sappiamo_calcolare_non_e_uno_scostamento():
    non_calcolato = {
        "stato_calcolo": "NON_CALCOLATO", "motivi": ["periodo_non_concluso"],
        "iva_vendite": None, "iva_acquisti": None, "saldo": None,
    }
    riga = mod.confronta_periodo("2026-12", non_calcolato, LIPE_MARZO, None)

    assert riga["esito"] == "gestionale_non_calcolabile"
    assert riga["scarti"] == {"iva_vendite": None, "iva_acquisti": None}


def test_senza_lipe_non_si_giudica_il_nostro_numero():
    riga = mod.confronta_periodo("2026-05", NOSTRO, None, None)

    assert riga["esito"] == "lipe_assente"
    assert riga["scarti"]["iva_vendite"] is None


def test_lo_scarto_non_e_mai_zero_per_finta():
    assert mod.scarto(None, 100.0) is None
    assert mod.scarto(100.0, None) is None
    assert mod.scarto(100.0, 100.0) == 0.0


# ── Il versamento ─────────────────────────────────────────────────────────

def test_una_lipe_a_credito_non_deve_avere_nessun_f24():
    """Tutto il 2026 chiude a credito, e infatti non esiste un F24 IVA."""
    riga = mod.confronta_periodo("2026-03", NOSTRO, LIPE_MARZO, None)
    assert riga["f24"]["nota"] == "nessun_versamento_dovuto"
    assert riga["f24"]["dovuto_da_lipe"] is None


def test_una_lipe_a_debito_senza_f24_e_il_caso_da_segnalare():
    lipe = dict(LIPE_MARZO, iva_da_versare_o_credito=2092.27,
                iva_da_versare_o_credito_segno="debito")

    riga = mod.confronta_periodo("2025-09", NOSTRO, lipe, None)

    assert riga["f24"]["nota"] == "f24_mancante"
    assert riga["f24"]["dovuto_da_lipe"] == 2092.27


def test_un_f24_dell_importo_giusto_risulta_versato():
    lipe = dict(LIPE_MARZO, iva_da_versare_o_credito=2092.27,
                iva_da_versare_o_credito_segno="debito")
    f24 = {"importo": 2092.27, "codice_tributo": "6009",
           "documenti": ["F24 IVA 09 2025.PDF"]}

    riga = mod.confronta_periodo("2025-09", NOSTRO, lipe, f24)

    assert riga["f24"]["nota"] == "versato"
    assert riga["f24"]["documenti"] == ["F24 IVA 09 2025.PDF"]


def test_un_f24_di_importo_diverso_si_segnala():
    lipe = dict(LIPE_MARZO, iva_da_versare_o_credito=2092.27,
                iva_da_versare_o_credito_segno="debito")

    riga = mod.confronta_periodo("2025-09", NOSTRO, lipe, {"importo": 1000.0})

    assert riga["f24"]["nota"] == "importo_diverso"


def test_un_versamento_su_un_mese_a_credito_si_segnala():
    riga = mod.confronta_periodo("2026-03", NOSTRO, LIPE_MARZO, {"importo": 500.0})
    assert riga["f24"]["nota"] == "versamento_non_atteso"


# ── La lettura dei prospetti F24 ──────────────────────────────────────────

class _Cursore:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield dict(d)
        return gen()


class _Db:
    def __init__(self, f24):
        self._f24 = f24
        self.letture = 0

    def __getitem__(self, nome):
        db = self

        class _Coll:
            def find(self, query=None, proj=None):
                db.letture += 1
                return _Cursore(db._f24 if nome == mod.COLL_F24 else [])
        return _Coll()


def _modello(codice, anno, importo, nome="F24.pdf", status=None):
    return {
        "file_name": nome, "status": status,
        "sezione_erario": [{
            "codice_tributo": codice, "anno": anno, "importo_debito": importo,
        }],
    }


def test_l_anno_si_legge_sulla_riga_del_tributo():
    """Il periodo di riferimento sta sulla riga, non sul modello: un F24 di
    gennaio 2025 puo' essere stato pagato in un altro momento."""
    db = _Db([_modello("6001", "2025", 534.06, "F24 iva gennaio Ceraldi.PDF")])

    esito = _run(mod.f24_iva_per_periodo(db, 2025))

    assert esito["2025-01"]["importo"] == 534.06
    assert esito["2025-01"]["documenti"] == ["F24 iva gennaio Ceraldi.PDF"]


def test_un_altro_anno_non_entra():
    db = _Db([_modello("6001", "2024", 999.0)])
    assert _run(mod.f24_iva_per_periodo(db, 2025)) == {}


@pytest.mark.parametrize("codice", ["1001", "6031", "600", "60AA", "6013", "6000"])
def test_i_codici_che_non_sono_iva_mensile_restano_fuori(codice):
    db = _Db([_modello(codice, "2025", 100.0)])
    assert _run(mod.f24_iva_per_periodo(db, 2025)) == {}


def test_due_modelli_sullo_stesso_mese_si_sommano():
    """Giugno 2025 ha un F24 ordinario e un ravvedimento."""
    db = _Db([
        _modello("6006", "2025", 5000.00, "F24 IVA +RIT FERRANTINI.pdf"),
        _modello("6006", "2025", 771.48, "F24 ravv iva - cciaa- ritenuta.pdf"),
    ])

    esito = _run(mod.f24_iva_per_periodo(db, 2025))

    assert esito["2025-06"]["importo"] == 5771.48
    assert len(esito["2025-06"]["documenti"]) == 2


def test_un_modello_stornato_non_conta():
    db = _Db([_modello("6001", "2025", 534.06, status="stornato")])
    assert _run(mod.f24_iva_per_periodo(db, 2025)) == {}


def test_i_prospetti_si_leggono_con_un_solo_prefetch():
    """Una query per mese, su dodici mesi, e' proibita dal §4."""
    db = _Db([_modello("6001", "2025", 534.06)])
    _run(mod.f24_iva_per_periodo(db, 2025))
    assert db.letture == 1
