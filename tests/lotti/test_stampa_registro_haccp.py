"""Guardia: la pagina di stampa e l'elenco delle sezioni restano allineati.

Il manuale sapeva gia' filtrare per sezione (`?sezioni=a,b,c`), ma quei nomi
vivevano solo dentro il generatore: per stamparne una parte bisognava
conoscerli a memoria. Ora sono un dato (`SEZIONI_MANUALE`) e c'e' la pagina
dove spuntare cosa mettere nel fascicolo.

Il pericolo e' che le due liste si separino: una sezione rinominata nel
generatore e non nell'elenco diventa una casella che non stampa niente — e ci
si accorge del vuoto davanti all'ispettore, non prima.
"""
import asyncio
import re
from pathlib import Path

import pytest

from app.lotti.routers.manuale_haccp import SEZIONI_MANUALE

SORGENTE = (Path(__file__).resolve().parents[2]
            / "app/lotti/routers/manuale_haccp.py").read_text(encoding="utf-8")


def test_ogni_sezione_dichiarata_esiste_nel_generatore():
    nel_generatore = set(re.findall(r'includi\("([a-z_]+)"\)', SORGENTE))
    dichiarate = {s["id"] for s in SEZIONI_MANUALE}

    assert dichiarate - nel_generatore == set(), (
        f"Caselle che non stampano niente: {sorted(dichiarate - nel_generatore)}"
    )
    assert nel_generatore - dichiarate == set(), (
        "Sezioni stampabili che nessuno puo' scegliere: "
        f"{sorted(nel_generatore - dichiarate)}"
    )


def test_ogni_sezione_ha_titolo_gruppo_e_descrizione():
    for s in SEZIONI_MANUALE:
        assert s["titolo"] and s["descrizione"], s
        assert s["gruppo"] in ("Manuale", "Registrazioni"), s


def test_i_registri_obbligatori_sono_stampabili():
    """Temperature, sanificazione e rintracciabilita' sono quelli che
    un'ispezione chiede per primi."""
    dichiarate = {s["id"] for s in SEZIONI_MANUALE}
    for obbligatoria in ("temperature", "sanificazione", "lotti", "allergeni", "anomalie"):
        assert obbligatoria in dichiarate, f"manca la pagina «{obbligatoria}»"


def test_la_pagina_mostra_una_casella_per_sezione():
    from app.lotti.routers.manuale_haccp import pagina_stampa

    html = asyncio.run(pagina_stampa()).body.decode()

    assert html.count('name="sezione"') == len(SEZIONI_MANUALE)
    for s in SEZIONI_MANUALE:
        assert f'value="{s["id"]}"' in html, f"«{s['titolo']}» non e' spuntabile"


COLORI_VIETATI = ["bg-blue", "text-blue", "indigo", "violet", "#64748b",
                  "slate-", "#1e293b", "#0f172a"]


@pytest.mark.parametrize("vietato", COLORI_VIETATI)
def test_la_pagina_rispetta_i_colori_del_progetto(vietato):
    """Salvia su crema: niente blu, indaco, viola o grigi freddi (CLAUDE.md)."""
    html = asyncio.run(
        __import__("app.lotti.routers.manuale_haccp", fromlist=["pagina_stampa"]).pagina_stampa()
    ).body.decode()

    assert vietato not in html


def test_la_pagina_e_usabile_col_dito():
    """Tablet del negozio: tocco minimo 44px, nessuno scroll orizzontale."""
    html = asyncio.run(
        __import__("app.lotti.routers.manuale_haccp", fromlist=["pagina_stampa"]).pagina_stampa()
    ).body.decode()

    assert "min-height:44px" in html and "min-height:48px" in html
    assert "width=device-width" in html
    assert "auto-fill,minmax(260px,1fr)" in html, (
        "La griglia deve riadattarsi: a larghezza telefono una griglia fissa "
        "manda la pagina in scroll orizzontale."
    )


def test_un_solo_font_quello_del_gruppo():
    html = asyncio.run(
        __import__("app.lotti.routers.manuale_haccp", fromlist=["pagina_stampa"]).pagina_stampa()
    ).body.decode()

    assert "Plus+Jakarta+Sans" in html
    # Cerca il font DICHIARATO, non la sottostringa: «Interventi» contiene
    # «Inter» e farebbe fallire il controllo su un testo innocente.
    famiglie = re.findall(r"font-family\s*:\s*([^;}]+)", html)
    assert famiglie, "nessuna famiglia dichiarata"
    for famiglia in famiglie:
        assert "Plus Jakarta Sans" in famiglia, (
            f"Seconda famiglia di caratteri: {famiglia.strip()}. Un titolo si "
            "distingue dal peso, mai dal carattere (CLAUDE.md)."
        )
