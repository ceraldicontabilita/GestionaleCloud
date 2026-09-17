"""P0.2 — Il job auto-riconcilia deve trovare le uscite dell'estratto conto in
ENTRAMBE le convenzioni di segno: importo positivo con tipo="uscita" (canonica)
e importo negativo (legacy). Prima filtrava solo importo<0 e non trovava mai le
uscite salvate come positive → zero candidati."""
from app.routers.batch_operations import filtro_uscite_da_riconciliare


def _match(d, q):
    for k, cond in q.items():
        if k == "$or":
            if not any(_match(d, sub) for sub in cond):
                return False
        elif isinstance(cond, dict):
            for op, val in cond.items():
                v = d.get(k)
                if op == "$nin" and v in val:
                    return False
                if op == "$lt" and not (isinstance(v, (int, float)) and v < val):
                    return False
        else:
            if d.get(k) != cond:
                return False
    return True


def test_trova_uscite_in_entrambe_le_convenzioni():
    f = filtro_uscite_da_riconciliare()
    movimenti = [
        {"id": "A", "tipo": "uscita", "importo": 120.0, "riconciliato": None},   # canonica
        {"id": "B", "importo": -80.0, "riconciliato": None},                     # legacy
        {"id": "C", "tipo": "entrata", "importo": 200.0, "riconciliato": None},  # entrata -> no
        {"id": "D", "tipo": "uscita", "importo": 50.0, "riconciliato": "riconciliato"},  # già ric. -> no
        {"id": "E", "tipo": "uscita", "importo": 50.0, "riconciliato": True},     # già ric. bool -> no
    ]
    trovati = [m["id"] for m in movimenti if _match(m, f)]
    assert trovati == ["A", "B"], f"attese le uscite A (positiva) e B (negativa), trovate {trovati}"
