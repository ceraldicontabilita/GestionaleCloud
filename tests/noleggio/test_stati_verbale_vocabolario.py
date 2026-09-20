"""Il vocabolario degli stati di un verbale sta in un posto solo.

Il 20/09/2026, in produzione, tutti e 105 i verbali erano in stato
`fattura_ricevuta`, e ogni punto che li cercava teneva la propria lista:
`post_download_pipeline` guardava `["salvato", "da_pagare", "identificato"]`
e non ne vedeva **nessuno**, `verbali_email_scanner` ne aveva quattro,
`verbali_email_logic` cinque, e la lista dei «gia' pagati» esisteva in quattro
copie. Questi test impediscono che il vocabolario torni a dividersi.
"""
import re
from pathlib import Path

import pytest

from app.constants.stati_verbale import (
    FILTRO_STATO_APERTO,
    FILTRO_STATO_PAGATO,
    STATI_APERTI,
    STATI_PAGATI,
    e_aperto,
    e_pagato,
    varianti,
)

ROOT = Path(__file__).resolve().parents[2]


def test_lo_stato_dei_105_verbali_veri_e_uno_stato_aperto():
    """`fattura_ricevuta` e' lo stato di tutte le righe in archivio."""
    assert e_aperto("fattura_ricevuta")
    assert "fattura_ricevuta" in FILTRO_STATO_APERTO["stato"]["$in"]


def test_il_filtro_conosce_minuscolo_e_maiuscolo():
    """In archivio convivono `da_pagare` e `DA_PAGARE`: li prende entrambi."""
    aperti = FILTRO_STATO_APERTO["stato"]["$in"]
    assert "da_pagare" in aperti and "DA_PAGARE" in aperti
    assert "identificato" in aperti and "IDENTIFICATO" in aperti
    assert varianti(["Pagato"]) == ["PAGATO", "pagato"]


def test_aperto_e_pagato_non_si_sovrappongono():
    assert not STATI_APERTI & STATI_PAGATI
    assert e_pagato("PAGATO") and e_pagato("riconciliato")
    assert not e_pagato("fattura_ricevuta")
    assert not e_aperto("pagato")
    assert not e_aperto(None) and not e_pagato(None)


def test_il_legacy_attesa_fattura_resta_fra_i_pagati_ma_non_si_scrive():
    """E' il nome sbagliato di «attesa quietanza»: si legge, non si scrive.

    CLAUDE.md: «Lo stato corretto dopo un pagamento privo di ricevuta
    ufficiale e' `attesa quietanza`, **mai** `attesa fattura`».
    """
    assert "pagato_attesa_fattura" in STATI_PAGATI
    scrittori = []
    for sorgente in (ROOT / "app").rglob("*.py"):
        testo = sorgente.read_text(encoding="utf-8")
        for blocco in re.findall(r"\$set[^}]*\}", testo, flags=re.S):
            if "pagato_attesa_fattura" in blocco:
                scrittori.append(str(sorgente.relative_to(ROOT)))
    assert scrittori == [], f"qualcuno scrive ancora lo stato legacy: {scrittori}"


@pytest.mark.parametrize("relativo", [
    "app/services/verbali_email_logic.py",
    "app/services/verbali_email_scanner.py",
    "app/services/verbali_evidence.py",
    "app/routers/verbali_riconciliazione.py",
])
def test_nessun_punto_si_tiene_la_propria_lista(relativo):
    sorgente = (ROOT / relativo).read_text(encoding="utf-8")
    # una lista scritta a mano si riconosce perche' nomina due o piu' stati
    # dello stesso insieme dentro la stessa parentesi quadra
    for lista in re.findall(r"\[[^\[\]]*\]", sorgente, flags=re.S):
        citati_aperti = {s for s in STATI_APERTI if f'"{s}"' in lista}
        citati_pagati = {s for s in STATI_PAGATI if f'"{s}"' in lista}
        assert len(citati_aperti) < 2, f"{relativo}: lista di stati aperti a mano -> {sorted(citati_aperti)}"
        assert len(citati_pagati) < 2, f"{relativo}: lista di stati pagati a mano -> {sorted(citati_pagati)}"
