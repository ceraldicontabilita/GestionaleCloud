"""P0.5 — L'associazione assegno→fattura deve scrivere uno stato presente in
ASSEGNO_STATI. Prima scriveva "associato", valore fuori schema."""
from pathlib import Path

from app.routers.bank.assegni import ASSEGNO_STATI


def test_associato_non_e_stato_valido_e_assegnato_si():
    assert "associato" not in ASSEGNO_STATI
    assert "assegnato" in ASSEGNO_STATI


def test_endpoint_non_scrive_piu_associato():
    src = Path("app/routers/bank/assegni.py").read_text(encoding="utf-8")
    # non deve esistere nessuna assegnazione di stato al valore invalido
    assert '"stato"] = "associato"' not in src
    assert "'stato'] = 'associato'" not in src
