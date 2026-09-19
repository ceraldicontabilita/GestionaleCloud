"""Un solo catalogo alert, e nessun codice emesso fuori catalogo.

`genera_alert` non solleva su un codice sconosciuto: scrive una riga di log e
torna `None`. Un alert emesso col codice sbagliato **sparisce in silenzio** —
nessun errore, nessuna riga in `alerts`, nessuno che se ne accorge.

Fino al 19/09/2026 i cataloghi erano due e divergevano in entrambe le
direzioni: 60 codici in comune, 15 solo sul lato ERP, 5 solo su quello HR. Si
vedeva da fuori: `app/services/dimissioni_adempimenti.py`, codice dell'ERP,
importava `genera_alert` dal ramo HR perche' `DIP_DIMISSIONI_RICEVUTE`
esisteva solo in quel catalogo.
"""
import re
from pathlib import Path

import pytest

from app.services.alert_engine import ALERT_CATALOG, genera_alert

RADICE = Path(__file__).resolve().parents[2]
MOTORI = {
    RADICE / "app" / "services" / "alert_engine.py",
    RADICE / "app" / "hr" / "services" / "alert_engine.py",
}

def _codici_emessi() -> dict:
    """Codici passati a `genera_alert`/`risolvi_alert` nel codice di `app/`."""
    chiamata = re.compile(
        r"(?:genera_alert|risolvi_alert|risolvi_alert_multi|ignora_alert)\s*\(\s*\n?\s*"
        r"""["']([A-Z][A-Z0-9_]+)["']"""
    )
    trovati = {}
    for percorso in (RADICE / "app").rglob("*.py"):
        if percorso in MOTORI:
            continue
        try:
            testo = percorso.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for codice in chiamata.findall(testo):
            trovati.setdefault(codice, set()).add(
                percorso.relative_to(RADICE).as_posix()
            )
    return trovati


def test_ogni_codice_emesso_esiste_nel_catalogo():
    emessi = _codici_emessi()
    assert emessi, "nessuna chiamata a genera_alert trovata: il test non sta guardando nulla"

    fuori = {c: sorted(f) for c, f in emessi.items() if c not in ALERT_CATALOG}
    assert not fuori, (
        "Codici alert emessi ma assenti dal catalogo: `genera_alert` li scarta "
        "con una riga di log e l'alert non arriva mai.\n"
        + "\n".join(f"  {c}: {', '.join(f)}" for c, f in sorted(fuori.items()))
    )


def test_i_cinque_codici_del_ramo_hr_sono_nel_catalogo_unico():
    """Erano solo nella copia `app/hr`: fondendo si sarebbero persi."""
    for codice in (
        "CED_CONTESTATA",
        "DIP_DIMISSIONI_RICEVUTE",
        "DIP_CONTRATTO_IN_SCADENZA",
        "DIP_PERIODO_PROVA_IN_SCADENZA",
        "MAG_SOTTO_SCORTA",
    ):
        assert codice in ALERT_CATALOG, codice


def test_la_copia_hr_e_un_re_export_del_modulo_unico():
    from app.hr.services import alert_engine as copia_hr

    assert copia_hr.ALERT_CATALOG is ALERT_CATALOG
    assert copia_hr.genera_alert is genera_alert


def test_le_dimissioni_non_importano_piu_dal_ramo_gemello():
    sorgente = (RADICE / "app" / "services" / "dimissioni_adempimenti.py").read_text(
        encoding="utf-8"
    )
    assert "from app.hr.services.alert_engine import" not in sorgente, (
        "Codice dell'ERP che importa il motore alert del ramo HR: era il "
        "sintomo del catalogo doppio."
    )


@pytest.mark.parametrize("campo", ["modulo", "severita", "titolo", "condizione_chiusura"])
def test_ogni_definizione_e_completa(campo):
    """`genera_alert` legge questi quattro campi senza default: uno mancante
    farebbe KeyError al momento di emettere l'alert, non prima."""
    incomplete = [c for c, d in ALERT_CATALOG.items() if not d.get(campo)]
    assert not incomplete, f"definizioni senza «{campo}»: {incomplete}"
