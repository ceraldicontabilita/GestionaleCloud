"""Detergenti e frequenze: una fonte sola, quella del manuale.

Le due tabelle — i prodotti con pH, diluizione e tempo di contatto, e ogni
quanto si lava ciascuna area — erano scritte a mano dentro l'HTML del manuale.
Si potevano stampare e basta: il piano di sanificazione non poteva leggerle, e
chi compilava il piano riscriveva a memoria quello che il manuale gia' diceva.

Ora i dati stanno in `servizi/sanificazione_catalogo.py`, il manuale stampa
generando da li', e il piano li propone. Questi test tengono fermo che sia
davvero **una** copia, e che la proposta resti una proposta.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.lotti.servizi.sanificazione_catalogo import (
    DETERGENTI,
    FREQUENZA_SUGGERITA,
    FREQUENZE_MANUALE,
    detergente,
)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def dbmock(monkeypatch):
    import importlib
    import pkgutil

    import app.lotti.routers as routers  # noqa: F401

    db = AsyncMongoMockClient()["Gestionale_Test"]
    for m in pkgutil.iter_modules(routers.__path__):
        try:
            mod = importlib.import_module(f"app.lotti.routers.{m.name}")
        except Exception:
            continue
        if hasattr(mod, "db"):
            monkeypatch.setattr(mod, "db", db, raising=False)
    import app.lotti.db as dbmod

    monkeypatch.setattr(dbmod, "database", db, raising=False)
    return db


# ── una sola copia ─────────────────────────────────────────────────────────

def test_il_manuale_stampa_gli_stessi_prodotti_del_catalogo():
    """Se il manuale tornasse a scriverseli da solo, le due copie divergono."""
    from app.lotti.routers.manuale_haccp_testi import DETERGENTI_SANIFICANTI

    for voce in DETERGENTI:
        assert voce["nome"] in DETERGENTI_SANIFICANTI, (
            f"«{voce['nome']}» non compare nel manuale stampato: le due "
            "tabelle non vengono piu' dalla stessa fonte."
        )


def test_le_condizioni_d_uso_del_cloro_arrivano_in_stampa():
    """Diluizione e tempo di contatto sono la parte che vale: senza, la riga
    dice solo «usa la candeggina»."""
    from app.lotti.routers.manuale_haccp_testi import DETERGENTI_SANIFICANTI

    assert "1-2%" in DETERGENTI_SANIFICANTI
    assert "5-10 minuti" in DETERGENTI_SANIFICANTI


def test_il_manuale_stampa_le_stesse_frequenze_del_catalogo():
    from app.lotti.routers.manuale_haccp_testi import DETERGENTI_SANIFICANTI

    for area, quando in FREQUENZE_MANUALE:
        assert area in DETERGENTI_SANIFICANTI
        assert quando in DETERGENTI_SANIFICANTI


# ── niente e' stato inventato ──────────────────────────────────────────────

def test_i_prodotti_sono_tipologie_non_marche():
    """Il nome commerciale lo scrive il responsabile: e' quello che rimanda
    alla scheda di sicurezza vera, e non si indovina."""
    for voce in DETERGENTI:
        assert voce["utilizzo"], f"{voce['id']}: senza utilizzo non serve a niente"
        # una tipologia non e' un nome proprio: niente ®, ™ o maiuscole di marca
        assert "®" not in voce["nome"] and "™" not in voce["nome"]


def test_la_diluizione_c_e_solo_dove_il_manuale_la_dichiara():
    """Un tempo di contatto inventato e' peggio di una casella vuota."""
    con_diluizione = {v["id"] for v in DETERGENTI if v["diluizione"]}
    assert con_diluizione == {"cloro"}, (
        f"Qualcuno ha aggiunto diluizioni che il manuale non dava: {con_diluizione}"
    )


def test_niente_frequenza_dove_il_manuale_tace():
    """Montacarichi e deposito il manuale non li nomina: nessuna proposta."""
    assert "Montacarichi" not in FREQUENZA_SUGGERITA
    assert "Deposito" not in FREQUENZA_SUGGERITA


def test_ogni_frequenza_suggerita_e_una_frequenza_vera_del_piano():
    """Una proposta che il piano non sa salvare e' un bottone che non funziona."""
    from app.lotti.routers.sanificazione import FREQUENZE

    for area, (frequenza, fonte) in FREQUENZA_SUGGERITA.items():
        assert frequenza in FREQUENZE, f"{area}: «{frequenza}» non e' una frequenza del piano"
        assert fonte, f"{area}: la proposta deve dire da dove viene"


def test_detergente_per_id():
    assert detergente("cloro")["diluizione"] == "1-2%"
    assert detergente("non_esiste") is None


# ── il piano ───────────────────────────────────────────────────────────────

def test_il_piano_offre_i_detergenti_del_manuale(dbmock):
    from app.lotti.routers.sanificazione import leggi_piano_sanificazione

    piano = run(leggi_piano_sanificazione())

    assert piano["detergenti_dal_manuale"] == DETERGENTI


def test_la_frequenza_suggerita_non_compila_il_piano(dbmock):
    """Proposta, non impostazione: il piano resta da completare."""
    from app.lotti.routers.sanificazione import leggi_piano_sanificazione

    piano = run(leggi_piano_sanificazione())
    pavimenti = next(v for v in piano["voci"] if v["area"] == "Pavimentazione")

    assert pavimenti["frequenza_suggerita"] == "giornaliera"
    assert pavimenti["frequenza_suggerita_fonte"]
    assert pavimenti["frequenza"] == "", (
        "La proposta del manuale ha compilato il piano da sola: il responsabile "
        "non ha scelto niente e il piano risulterebbe deciso."
    )
    assert "Pavimentazione" in piano["da_completare"]


def test_dopo_ogni_uso_e_una_frequenza_salvabile(dbmock):
    """Il manuale la usa per taglieri e utensili: il piano deve accettarla."""
    from app.lotti.routers.sanificazione import (
        VoceDelPiano,
        leggi_piano_sanificazione,
        salva_piano_sanificazione,
    )

    run(salva_piano_sanificazione(
        [VoceDelPiano(area="Tagliere, Coltelli", frequenza="dopo_ogni_uso",
                      prodotto="Disinfettante a base di cloro", diluizione="2%")],
        _admin={"ruolo": "admin"},
    ))

    piano = run(leggi_piano_sanificazione())
    voce = next(v for v in piano["voci"] if v["area"] == "Tagliere, Coltelli")
    assert voce["frequenza"] == "dopo_ogni_uso"
    assert voce["frequenza_etichetta"] == "Dopo ogni utilizzo"
    assert "Tagliere, Coltelli" not in piano["da_completare"]
