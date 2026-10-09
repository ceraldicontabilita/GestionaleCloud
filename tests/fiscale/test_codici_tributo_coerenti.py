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


# ── Decisione del titolare (02/10/2026): 1001, 1012, 3802, DM10 ───────────
#
# Descrizioni e scadenze di questi quattro codici vengono dalla fonte AdE
# (ricerca guidata codici tributo) e dalla tabella delle scadenze; un codice
# fuori dal registro versionato NON si contabilizza finche' non e' validato.

from app.engines.tributi_engine import classifica_riga  # noqa: E402
from app.services.codici_tributo_db import CODICI_TRIBUTO_INPS  # noqa: E402
from app.services.codici_tributo_f24 import (  # noqa: E402
    get_descrizione_causale_inps,
)
from app.services.fiscal_accounting_policy import (  # noqa: E402
    build_journal_proposal, tax_code_rule,
)
from app.services.scadenzario_tributi import scadenza_da_regola  # noqa: E402

QUATTRO_CODICI_ADE = [
    # codice, parole chiave della descrizione AdE, tabella del parser, tabella delle scadenze
    ("1001", ("ritenute", "retribuzioni"), CODICI_TRIBUTO_F24, CODICI_TRIBUTO_ERARIO),
    ("1012", ("ritenute", "indennit", "cessazione"), CODICI_TRIBUTO_F24, CODICI_TRIBUTO_ERARIO),
    ("3802", ("addizionale regionale", "sostituto"), CODICI_TRIBUTO_F24, CODICI_TRIBUTO_ERARIO),
    ("DM10", ("contributi", "dipendenti"), None, CODICI_TRIBUTO_INPS),
]


@pytest.mark.parametrize("codice, parole, parser, scadenze", QUATTRO_CODICI_ADE)
def test_i_quattro_codici_del_titolare_hanno_la_descrizione_ade(codice, parole, parser, scadenze):
    testi = [_descrizione(scadenze[codice]).lower()]
    if parser is not None:
        testi.append(_descrizione(parser[codice]).lower())
    else:
        testi.append(get_descrizione_causale_inps(codice).lower())
    for testo in testi:
        for parola in parole:
            assert parola in testo, f"{codice}: manca «{parola}» in {testo!r}"


@pytest.mark.parametrize("codice, parole, parser, scadenze", QUATTRO_CODICI_ADE)
def test_i_quattro_codici_scadono_il_16_del_mese_successivo(codice, parole, parser, scadenze):
    """Ritenute, addizionale trattenuta dal sostituto e contributi: 16 del mese dopo."""
    assert "16 del mese successivo" in scadenze[codice]["scadenza"]
    if parser is not None:
        assert "16 del mese successivo" in parser[codice].get("scadenza", ""), (
            f"{codice}: il registro del parser non dice la scadenza")


def test_le_scadenze_dei_quattro_codici_nello_scadenzario():
    """La stessa regola che usa lo scadenzario (festivi inclusi): agosto 2026 → 16/09/2026."""
    from datetime import date

    assert scadenza_da_regola("sezione_erario", "1001", 2026, 8)[0] == date(2026, 9, 16)
    assert scadenza_da_regola("sezione_erario", "1012", 2026, 8)[0] == date(2026, 9, 16)
    assert scadenza_da_regola("sezione_inps", "DM10", 2026, 8)[0] == date(2026, 9, 16)
    # Addizionale: anno d'imposta o della trattenuta, la piu' vicina alla quietanza.
    assert scadenza_da_regola("sezione_regioni", "3802", 2025, 8, "2026-09-16")[0] == date(2026, 9, 16)
    # Senza regola niente si inventa.
    assert scadenza_da_regola("sezione_erario", "ZZ99", 2026, 8)[0] is None


def test_il_3802_non_e_irap_e_il_dm10_non_e_un_codice_erario():
    assert "irap" not in _descrizione(CODICI_TRIBUTO_F24["3802"]).lower()
    assert "DM10" not in CODICI_TRIBUTO_F24, "DM10 e' una causale INPS, non un codice tributo"
    assert classifica_riga("inps", "DM10")["ente"] == "INPS"


def test_un_codice_fuori_registro_blocca_la_contabilizzazione():
    """`journal_proposal`: codice non validato → blocco esplicito, mai una scrittura."""
    regola = tax_code_rule("9999")
    assert regola["status"] == "NOT_IN_LOCAL_VERSIONED_REGISTRY"
    assert regola["deductibility_ires"] == "DA_VERIFICARE"

    proposta = build_journal_proposal(
        {"id": "q-1", "sezione_erario": [
            {"codice_tributo": "9999", "periodo_riferimento": "08/2026", "importo_debito": 100.0},
        ]},
        document_type="F24_QUIETANZA",
        evidence_state={"quietanza_validata": True},
    )
    assert proposta["journal_proposal_status"] == "BLOCKED_REVIEW"
    assert proposta["posting_allowed"] is False
    assert proposta["definitive_posting_created"] is False
    assert "CODICE_TRIBUTO_NON_VALIDATO:9999" in proposta["blockers"]
    assert proposta["lines"] == []


def test_il_motore_tributi_non_indovina_un_codice_sconosciuto():
    riga = classifica_riga("erario", "9999")
    assert riga["deducibilita"] == "da_verificare"
    assert "verificare" in riga["nota"].lower()
    sconosciuta = classifica_riga("inps", "ZZ99")
    assert sconosciuta["deducibilita"] == "da_verificare"
