"""Due tabelle di codici tributo non possono dire cose diverse.

Il gestionale ne teneva **tre**: `app/constants/codici_tributo_f24.py` (copia
troncata, 89 righe, nessun importatore — rimossa il 19/09/2026),
`app/services/codici_tributo_f24.py` (1.992 righe, quella che legge il parser
F24) e `app/services/codici_tributo_db.py` (466 righe, con le scadenze, letta
dal router email F24).

Le due rimaste avevano 50 codici in comune e **35 discordanti**. Quasi tutte
differenze di parole, ma due no:

- **IRES**: il 19/09/2026 la tabella del parser e' stata «corretta» nel verso
  sbagliato (2001 saldo). La fonte, la ricerca guidata codici tributo
  dell'Agenzia delle Entrate, dice 2001 acconto prima rata, 2002 acconto
  seconda rata o unica soluzione, 2003 saldo.
- **1631** dava «Credito d'imposta art. 3 DL 73/2021» nella tabella del
  router.

Qui si fissano i codici sulla fonte, l'Agenzia delle Entrate, in **entrambe**
le tabelle: finche' convivono, non possono ridivergere in silenzio.
"""
import pytest

from app.services.codici_tributo_db import CODICI_TRIBUTO_ERARIO
from app.services.codici_tributo_f24 import CODICI_TRIBUTO_F24


def _descrizione(voce):
    if isinstance(voce, str):
        return voce
    if isinstance(voce, dict):
        return voce.get("descrizione") or voce.get("nome") or ""
    return str(voce)


# ── I codici IRES ─────────────────────────────────────────────────────────

IRES = [
    ("2001", "acconto prima rata"),
    ("2002", "acconto seconda rata"),
    ("2003", "saldo"),
]


@pytest.mark.parametrize("codice, atteso", IRES)
def test_ires_nella_tabella_del_parser(codice, atteso):
    """Fonte: Agenzia delle Entrate. 2003 e' il SALDO."""
    assert atteso in _descrizione(CODICI_TRIBUTO_F24[codice]).lower()


@pytest.mark.parametrize("codice, atteso", IRES)
def test_ires_nella_tabella_delle_scadenze(codice, atteso):
    assert atteso in _descrizione(CODICI_TRIBUTO_ERARIO[codice]).lower()


def test_il_saldo_ires_non_e_un_acconto():
    assert "acconto" not in _descrizione(CODICI_TRIBUTO_F24["2003"]).lower()
    assert "saldo" not in _descrizione(CODICI_TRIBUTO_F24["2001"]).lower()


# ── Addizionale regionale: 3802 e' quella del sostituto d'imposta ─────────

@pytest.mark.parametrize("tabella", [CODICI_TRIBUTO_F24, CODICI_TRIBUTO_ERARIO])
def test_3802_e_il_sostituto_3801_l_autotassazione(tabella):
    assert "sostituto" in _descrizione(tabella["3802"]).lower()
    assert "autotassazione" in _descrizione(tabella["3801"]).lower()


# ── Il 1631 ───────────────────────────────────────────────────────────────

def test_il_1631_e_un_rimborso_da_assistenza_fiscale():
    testo = _descrizione(CODICI_TRIBUTO_ERARIO["1631"]).lower()
    assert "assistenza fiscale" in testo
    assert "dl 73/2021" not in testo


# ── La copia rimossa non deve tornare ─────────────────────────────────────

def test_la_terza_tabella_non_esiste_piu():
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.constants.codici_tributo_f24")


def test_il_re_export_punta_alla_tabella_canonica():
    from app.constants import CODICI_TRIBUTO_F24 as riesportata

    assert riesportata is CODICI_TRIBUTO_F24


# ── E d'ora in poi non possono ridivergere sui codici che contano ─────────

CODICI_SORVEGLIATI = ("2001", "2002", "2003", "3800", "6001", "6002", "1040")


@pytest.mark.parametrize("codice", CODICI_SORVEGLIATI)
def test_le_due_tabelle_concordano_sui_codici_sorvegliati(codice):
    """Non si pretende la stessa frase: si pretende che non dicano il
    contrario, cioe' che le parole chiave del tributo coincidano."""
    if codice not in CODICI_TRIBUTO_F24 or codice not in CODICI_TRIBUTO_ERARIO:
        pytest.skip(f"{codice} non e' in entrambe le tabelle")

    a = _descrizione(CODICI_TRIBUTO_F24[codice]).lower()
    b = _descrizione(CODICI_TRIBUTO_ERARIO[codice]).lower()

    for parola in ("saldo", "acconto", "prima rata", "seconda rata"):
        assert (parola in a) == (parola in b), (
            f"{codice}: «{parola}» compare in una tabella e non nell'altra "
            f"({a!r} vs {b!r})"
        )
