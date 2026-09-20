"""`status` non dice se una fattura e' pagata: chi lo usava per filtrare.

Misurato in produzione il 20/09/2026 su `invoices` (1.457 righe): `status` vale
`imported` (653), `archived` (555) o niente (249). Nessun valore di pagamento.
`app/models/stati.py::STATI_PAGATI` elencava `pagato`, `parziale`, `paid`,
`pagata`, `saldato` e veniva applicata proprio a `status`: sei query la usavano
e **nessuna escludeva una riga**. Due facevano danno vero:

* la ricerca di combinazioni assegni↔fatture la metteva in `$or` con il
  criterio canonico, e un ramo sempre vero disarma l'altro: lavorava anche
  sulle 690 fatture gia' pagate;
* `associa-combinazioni-avanzato` non aveva nemmeno il criterio canonico.

Il file e' stato cancellato: conteneva sei enum e quattro funzioni che nessuno
importava, e diceva «REGOLA D'ORO: usare SEMPRE questi enum».
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_il_vocabolario_parallelo_non_esiste_piu():
    assert not (ROOT / "app/models/stati.py").exists()
    residui = [
        str(p.relative_to(ROOT))
        for p in ROOT.rglob("*.py")
        if "node_modules" not in str(p) and p != Path(__file__)
        and "app.models" ".stati" in p.read_text(encoding="utf-8")
    ]
    assert residui == [], residui


@pytest.mark.parametrize("relativo", [
    "app/routers/bank/assegni.py",
    "app/routers/accounting/bilancio.py",
    "app/routers/accounting/piano_conti.py",
    "app/routers/chiusura_esercizio.py",
    "app/routers/finanziaria.py",
])
def test_chi_cerca_le_fatture_da_pagare_usa_il_criterio_canonico(relativo):
    sorgente = (ROOT / relativo).read_text(encoding="utf-8")
    assert "FILTRO_NON_PAGATE" in sorgente


def test_nessun_criterio_canonico_dentro_un_or_che_lo_annulla():
    """Un `$or` con un ramo sempre vero e' come non aver filtrato."""
    sorgente = (ROOT / "app/routers/bank/assegni.py").read_text(encoding="utf-8")
    for blocco in re.findall(r'"\$or":\s*\[.*?\]', sorgente, flags=re.S):
        assert "FILTRO_NON_PAGATE" not in blocco, blocco[:200]
