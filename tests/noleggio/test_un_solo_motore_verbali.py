"""Un solo motore riconcilia i verbali, e non associa mai per solo importo.

`riconcilia_verbali_strict` ha sostituito i motori storici, ma nella pipeline
viva era rimasto `_cerca_quietanze_verbali`, che cercava un movimento bancario
**per solo importo** piu' la parola «verbal|multa|sanzione» nella causale e
scriveva `stato: "pagato"`. Non ha mai sparato solo perche' il suo filtro era
rotto in due punti (`quietanza_ricevuta: False` su una chiave assente su
105 righe su 105, e una lista di stati che non conteneva `fattura_ricevuta`):
bastava «sistemare il filtro» per armarlo.

Insieme a lui vivevano due funzioni `_legacy_*_non_usare` (274 righe), tre
involucri senza chiamanti e una docstring che prometteva «importo + data entro
90gg». Cancellati. Questi test impediscono che tornino.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "app/services/post_download_pipeline.py"


@pytest.mark.parametrize("nome", [
    "_cerca_quietanze_verbali",
    "_crea_trattenuta_verbale",
    "_marca_verbale_pagato",
    "riconcilia_verbali_con_banca",
    "riconcilia_verbali_avanzato",
    "_legacy_riconcilia_verbali_con_banca_non_usare",
    "_legacy_riconcilia_verbali_avanzato_non_usare",
])
def test_le_funzioni_morte_non_ci_sono_piu(nome):
    assert nome not in PIPELINE.read_text(encoding="utf-8")


def test_nessuna_funzione_si_chiama_non_usare():
    """Il codice morto si cancella, non si rinomina «non usare».

    (Un `_legacy_*` puo' essere vivo: `_legacy_supplier_view` adatta i
    fornitori del nuovo archivio alla UI storica. Qui si guarda il marcatore
    che non ha altra lettura possibile.)
    """
    colpevoli = []
    for sorgente in (ROOT / "app").rglob("*.py"):
        for riga in sorgente.read_text(encoding="utf-8").splitlines():
            if re.match(r"^(async )?def \w*_non_usare\b", riga):
                colpevoli.append(f"{sorgente.relative_to(ROOT)}: {riga.strip()}")
    assert colpevoli == [], colpevoli


def test_la_pipeline_non_abbina_un_movimento_bancario_per_solo_importo():
    sorgente = PIPELINE.read_text(encoding="utf-8")
    assert "estratto_conto_movimenti" not in sorgente, (
        "la pipeline e' tornata a cercarsi da sola i movimenti bancari"
    )
    assert "verbal|multa|sanzione" not in sorgente


def test_la_riconciliazione_verbali_ha_un_solo_motore():
    """Nessun secondo punto d'ingresso: solo `riconcilia_verbali_strict`."""
    definizioni = []
    for sorgente in (ROOT / "app").rglob("*.py"):
        for riga in sorgente.read_text(encoding="utf-8").splitlines():
            if re.match(r"^async def riconcilia_verbali\w*\(", riga):
                definizioni.append(f"{sorgente.relative_to(ROOT)}: {riga.strip()}")
    # il motore, l'endpoint che lo espone e il ponte PayPal (fonte diversa)
    assert len(definizioni) <= 3, definizioni
    assert any("verbali_pagamento_finder" in d for d in definizioni)


def test_l_endpoint_non_promette_strategie_che_non_esegue():
    sorgente = (ROOT / "app/routers/email_download.py").read_text(encoding="utf-8")
    assert "Importo + data entro 90gg" not in sorgente
    assert "importo uguale al centesimo" in sorgente
