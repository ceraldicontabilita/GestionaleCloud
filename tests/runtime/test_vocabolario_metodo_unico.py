"""Nessuno si riscrive la lista dei «metodo non configurato».

CLAUDE.md lo dice gia': «Metodo di pagamento non configurato» ha un
vocabolario solo, `app/constants/metodi_pagamento.py`. Chi tiene la propria
lista si perde il caso piu' frequente — e infatti oggi (20/09/2026) se ne
perdevano due, tutti e due sul valore `"sospesa"`, che e' quello che scrive
l'import:

- `on_fornitore_aggiornato_risolvi` **chiudeva** FORN_MP_MANCANTE e
  FAT_MP_NON_DEFINITO su fornitori ancora senza metodo. E' lo specchio del
  difetto gia' corretto in emissione: li' l'alert non partiva, qui spariva —
  che e' peggio, perche' un alert chiuso dice che il problema non c'e' piu';
- `aggiorna_metodi_pagamento_da_fornitori` cercava le fatture da sistemare
  con `$in [None, "", "da_configurare"]` e ne saltava **619 su 1.457**.
"""
import pathlib
import re

import pytest

from app.constants.metodi_pagamento import (
    FILTRO_METODO_NON_CONFIGURATO,
    METODI_NON_CONFIGURATI,
    metodo_non_configurato,
)

RADICE = pathlib.Path(__file__).resolve().parents[2] / "app"


def test_sospesa_e_il_valore_che_scrive_l_import():
    assert metodo_non_configurato("sospesa") is True
    assert metodo_non_configurato("SOSPESA ") is True
    assert metodo_non_configurato(None) is True
    assert metodo_non_configurato("bonifico") is False


def test_il_filtro_di_archivio_copre_anche_il_campo_assente():
    valori = FILTRO_METODO_NON_CONFIGURATO["metodo_pagamento"]["$in"]

    assert None in valori, "senza None non intercetta le righe senza il campo"
    assert set(METODI_NON_CONFIGURATI).issubset(set(valori))


# Chi ha il diritto di nominare i valori: il file che li definisce, e i test.
AMMESSI = {"constants/metodi_pagamento.py"}


def _file_con_lista_propria():
    """File che elencano a mano piu' di un valore di «non configurato»."""
    colpevoli = []
    for percorso in sorted(RADICE.rglob("*.py")):
        relativo = str(percorso.relative_to(RADICE))
        if relativo in AMMESSI:
            continue
        testo = percorso.read_text(encoding="utf-8")
        # righe di codice (non commenti) che citano due o piu' valori insieme
        for numero, riga in enumerate(testo.splitlines(), 1):
            nuda = riga.split("#")[0]
            citati = {v for v in ("da_configurare", "sospesa", "none", "null")
                      if f'"{v}"' in nuda or f"'{v}'" in nuda}
            if len(citati) >= 2:
                colpevoli.append(f"{relativo}:{numero}  {riga.strip()[:90]}")
    return colpevoli


def test_nessun_file_si_riscrive_la_lista():
    colpevoli = _file_con_lista_propria()

    assert not colpevoli, (
        "Vocabolario duplicato: usare `metodo_non_configurato()` o "
        "`FILTRO_METODO_NON_CONFIGURATO`.\n" + "\n".join(colpevoli)
    )


CASI_RISOLUZIONE = [
    ("app/services/handlers/fattura_handlers.py", "metodo_non_configurato"),
    ("app/routers/fatture_module/pagamento.py", "FILTRO_METODO_NON_CONFIGURATO"),
    ("app/routers/suppliers_module/validation.py", "mancanti"),
]


@pytest.mark.parametrize("percorso,atteso", CASI_RISOLUZIONE,
                         ids=[c[0].split("/")[-1] for c in CASI_RISOLUZIONE])
def test_i_tre_punti_corretti_usano_il_motore_condiviso(percorso, atteso):
    sorgente = (RADICE.parent / percorso).read_text(encoding="utf-8")

    assert atteso in sorgente


def test_la_risoluzione_non_chiude_un_alert_ancora_aperto():
    """Con `"sospesa"` la vecchia condizione era vera e chiudeva l'alert."""
    sorgente = (RADICE / "services" / "handlers" / "fattura_handlers.py").read_text(
        encoding="utf-8")

    assert 'metodo not in ("", "da_configurare")' not in sorgente
    assert sorgente.count("if not metodo_non_configurato(metodo):") == 2
