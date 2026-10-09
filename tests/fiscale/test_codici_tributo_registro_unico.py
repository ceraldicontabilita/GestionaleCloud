"""Le descrizioni dei codici tributo F24 vengono da un registro solo.

Fino al 27/09/2026 le tabelle erano sei: il registro
(`codici_tributo_f24.py`), la tabella delle scadenze (`codici_tributo_db.py`),
una terza dentro `routers/f24/f24_main.py` e tre dizionari locali nei due
parser (`f24_parser.py` per le quietanze, `parser_f24.py` per i modelli).
Dicevano cose diverse: RC01 «artigiani/commercianti» (e' la regolarizzazione
contributiva), 3844 «addizionale regionale» (e' comunale), 3919 «IMU
interessi» (e' altri fabbricati, quota Stato), 1671 «trattenuta del
sostituto» (e' un credito), e la TEFA non aveva etichetta.

Fonti: Agenzia delle Entrate, Ris. 35/E 2012 (IMU), 45/E 2014 (TARI),
5/E 2021 (TEFA, TEFN, TEFZ).
"""
from pathlib import Path

import pytest

from app.services import f24_parser, parser_f24
from app.services.codici_tributo_db import CODICI_TRIBUTO_ERARIO
from app.services.codici_tributo_f24 import (
    CODICI_TRIBUTO_F24, get_descrizione_causale_inps, get_descrizione_tributo,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("codice, parola", [
    ("TEFA", "tutela"), ("TEFN", "interessi"), ("TEFZ", "sanzioni"),
    ("3944", "tassa"), ("3945", "interessi"), ("3946", "sanzioni"),
    ("3950", "tariffa"), ("3951", "interessi"), ("3952", "sanzioni"),
    ("3919", "stato"), ("3923", "interessi"), ("3924", "sanzioni"),
    ("1671", "eccedenza"), ("3843", "comunale"), ("3844", "comunale"),
    ("8902", "sanzione"),
])
def test_descrizioni_verificate(codice, parola):
    assert parola in get_descrizione_tributo(codice).lower()


def test_rc01_e_la_regolarizzazione():
    assert "regolarizzazione" in get_descrizione_causale_inps("RC01").lower()
    assert "artigiani" not in CODICI_TRIBUTO_F24["RC01"]["descrizione"].lower()


def test_causale_ignota_resta_dichiarata():
    assert get_descrizione_causale_inps("ZZ99") == "Causale INPS ZZ99"


def test_i_parser_non_tengono_tabelle_proprie():
    for modulo in (f24_parser, parser_f24):
        for nome in ("get_descrizione_tributo_erario", "get_descrizione_tributo_regioni",
                     "get_descrizione_tributo_locale"):
            assert not hasattr(modulo, nome), f"{modulo.__name__}.{nome} e' tornata"
        testo = Path(modulo.__file__).read_text(encoding="utf-8")
        assert "descrizioni = {" not in testo, f"{modulo.__name__} ha di nuovo un dizionario locale"


def test_il_router_f24_non_ha_una_terza_tabella():
    testo = (ROOT / "app/routers/f24/f24_main.py").read_text(encoding="utf-8")
    assert "CODICI_TRIBUTO_F24 = {" not in testo


@pytest.mark.parametrize("codice, parola", [
    ("1671", "eccedenza"), ("8902", "sanzione"), ("8907", "irap"),
])
def test_la_tabella_delle_scadenze_concorda(codice, parola):
    assert parola in CODICI_TRIBUTO_ERARIO[codice]["descrizione"].lower()
