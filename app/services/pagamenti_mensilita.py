"""Mensilità saldate da un unico bonifico, senza inventare quote mensili."""
from datetime import date
import re


def competenza_in_causale(testo):
    """Una sola mensilità esplicita; date bancarie e causali cumulative escluse."""
    testo = str(testo or "").casefold()
    testo = re.sub(r"\b\d{1,2}[/.-]\d{1,2}[/.-]20\d{2}\b|\b20\d{2}-\d{2}-\d{2}\b", " ", testo)
    if re.search(r"\b\d{1,2}(?:\s*[-+,]\s*\d{1,2}){1,}\s+20\d{2}\b", testo):
        return None
    periodi = {(int(m), int(a)) for m, a in re.findall(r"(?<![\d/\-])(0?[1-9]|1[0-4])[/\-](20\d{2})\b", testo)}
    mesi = "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre tredicesima quattordicesima".split()
    for m, nome in enumerate(mesi, 1):
        periodi.update((m, int(a)) for a in re.findall(rf"\b{nome}\b(?:\s+|[/\-])(20\d{{2}})\b", testo))
    return next(iter(periodi)) if len(periodi) == 1 else None


def periodi_saldati(esito):
    if not esito.get("confermato_manuale") or not esito.get("dipendente_id"):
        return []
    try:
        date.fromisoformat(str(esito.get("data")))
        if float(esito.get("importo") or 0) <= 0:
            return []
        periodi = {(int(p["anno"]), int(p["mese"])) for p in esito.get("periodi_saldati", [])}
    except (ValueError, TypeError, KeyError):
        return []
    return sorted((a, m) for a, m in periodi if 2018 <= a <= 2100 and 1 <= m <= 14)


def indice_coperture(esiti):
    indice = {}
    for e in esiti:
        for anno, mese in periodi_saldati(e):
            prova = {k: e.get(k) for k in ("id", "key", "data", "importo", "cro", "causale", "bonifico_da_associare_id")}
            prova["nota"] = "Stipendio pagato con bonifico del " + date.fromisoformat(e["data"]).strftime("%d/%m/%Y")
            indice.setdefault((e["dipendente_id"], anno, mese), []).append(prova)
    return indice


def stato_copertura(prove):
    # Saldo del MESE chiuso da prova esplicita. Il progressivo resta invece
    # somma dei debiti noti meno il singolo bonifico alla sua data reale.
    return {"stato_pagamento": "pagato_documentato", "saldo": 0.0,
            "pagamenti_copertura": prove}
