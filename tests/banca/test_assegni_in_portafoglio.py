"""Gli assegni non incassati della chiusura d'esercizio.

La chiusura sommava gli assegni in stato `["emesso", "consegnato"]` con
`{"incassato": {"$ne": True}}`. Misurato in produzione il 20/09/2026:

* `consegnato` **non e' uno stato di questa tabella** (ASSEGNO_STATI ne ha
  nove e non lo contiene) e nessuna riga lo porta;
* il campo booleano `incassato` non esiste: 0 righe su 109 lo hanno, quindi
  quel filtro passava sempre — una riga morta;
* `assegnato` e `parzialmente_assegnato`, quelli che scrive il collegamento
  a fattura, restavano fuori: un assegno consegnato al fornitore e non ancora
  incassato valeva zero in chiusura.

Oggi tutti i 109 assegni sono `incassato` e il totale e' corretto per caso.
"""
from pathlib import Path

from app.constants.stati_assegno import ASSEGNI_STATI_IN_PORTAFOGLIO
from app.routers.bank.assegni import ASSEGNO_STATI

ROOT = Path(__file__).resolve().parents[2]
CHIUSURA = ROOT / "app/routers/chiusura_esercizio.py"


def test_gli_stati_del_portafoglio_esistono_tutti():
    assert set(ASSEGNI_STATI_IN_PORTAFOGLIO) <= set(ASSEGNO_STATI)


def test_un_assegno_consegnato_a_fornitore_conta_in_chiusura():
    assert "assegnato" in ASSEGNI_STATI_IN_PORTAFOGLIO
    assert "parzialmente_assegnato" in ASSEGNI_STATI_IN_PORTAFOGLIO
    assert "emesso" in ASSEGNI_STATI_IN_PORTAFOGLIO


def test_un_assegno_chiuso_o_annullato_non_conta():
    for stato in ("incassato", "annullato", "stornato", "scaduto", "vuoto", "compilato"):
        assert stato not in ASSEGNI_STATI_IN_PORTAFOGLIO


def test_la_chiusura_usa_il_vocabolario_e_non_il_booleano_morto():
    sorgente = CHIUSURA.read_text(encoding="utf-8")
    assert "ASSEGNI_STATI_IN_PORTAFOGLIO" in sorgente
    assert '"consegnato"' not in sorgente
    assert '"incassato": {"$ne": True}' not in sorgente
