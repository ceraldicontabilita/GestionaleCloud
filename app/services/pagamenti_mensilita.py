"""Mensilità saldate da un unico bonifico, senza inventare quote mensili."""
from datetime import date


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
