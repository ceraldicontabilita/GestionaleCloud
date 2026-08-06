"""KPI e invarianti della riconciliazione per la Dashboard Relazionale."""
from __future__ import annotations

from typing import Any, Dict, Iterable


def calcola_contatori_movimenti(movimenti: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    righe = list(movimenti)
    riconciliati = [m for m in righe if m.get("riconciliato") is True]
    da_riconciliare = [m for m in righe if m.get("riconciliato") is not True]
    importo = lambda items: round(sum(abs(float(m.get("importo") or 0)) for m in items), 2)
    totale = len(righe)
    return {
        "totale": totale,
        "riconciliati": len(riconciliati),
        "da_riconciliare": len(da_riconciliare),
        "importo_totale": importo(righe),
        "importo_riconciliato": importo(riconciliati),
        "importo_da_riconciliare": importo(da_riconciliare),
        "quadratura_ok": totale == len(riconciliati) + len(da_riconciliare),
    }


def verifica_transizione(prima: Dict[str, Any], dopo: Dict[str, Any], quanti: int = 1) -> Dict[str, Any]:
    """Controlla che una conferma sposti righe senza alterare il totale."""
    ok = (
        dopo.get("totale") == prima.get("totale")
        and dopo.get("riconciliati") == prima.get("riconciliati", 0) + quanti
        and dopo.get("da_riconciliare") == prima.get("da_riconciliare", 0) - quanti
        and dopo.get("quadratura_ok") is True
    )
    return {
        "ok": ok,
        "delta_riconciliati": dopo.get("riconciliati", 0) - prima.get("riconciliati", 0),
        "delta_da_riconciliare": dopo.get("da_riconciliare", 0) - prima.get("da_riconciliare", 0),
        "totale_invariato": dopo.get("totale") == prima.get("totale"),
    }
