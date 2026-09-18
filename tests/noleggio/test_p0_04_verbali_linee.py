"""P0.4 — La ricerca del numero verbale dentro una fattura deve guardare il campo
canonico `linee` (le righe fattura), NON `items` (che non esiste su invoices).
Prima cercava `items.descrizione` → non trovava mai il verbale nelle righe."""
import re

from app.routers.verbali_riconciliazione import campi_ricerca_verbale_in_fattura


def _match_or(doc, or_list):
    for cond in or_list:
        (field, spec), = cond.items()
        rx = re.compile(spec["$regex"], re.I)
        # supporta path con array: linee.descrizione
        parts = field.split(".")
        vals = [doc]
        for p in parts:
            nxt = []
            for v in vals:
                if isinstance(v, list):
                    nxt.extend(x.get(p) for x in v if isinstance(x, dict))
                elif isinstance(v, dict):
                    nxt.append(v.get(p))
            vals = [x for x in nxt if x is not None]
        if any(isinstance(v, str) and rx.search(v) for v in vals):
            return True
    return False


def test_trova_verbale_nelle_righe_linee():
    numero = "V-2026-0099"
    orq = campi_ricerca_verbale_in_fattura(numero)
    # campo canonico presente
    assert any("linee.descrizione" in c for c in orq)
    # campo errato ASSENTE
    assert not any("items" in list(c.keys())[0] for c in orq)

    fattura = {"linee": [{"descrizione": f"Spese notifica verbale {numero}"}]}
    assert _match_or(fattura, orq), "il verbale nelle righe `linee` deve essere trovato"

    # una fattura con il numero solo in items NON deve matchare (items non è canonico)
    fattura_items = {"items": [{"descrizione": f"verbale {numero}"}]}
    assert not _match_or(fattura_items, orq)


def test_numero_verbale_regex_escaped():
    # caratteri speciali non devono rompere la regex
    orq = campi_ricerca_verbale_in_fattura("V.2026(1)")
    fattura = {"descrizione": "pagamento V.2026(1)"}
    assert _match_or(fattura, orq)
