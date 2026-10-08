"""Merce ferma: materie prime comprate e mai scaricate da nessuna produzione.

Sui dati veri (27/09/2026) le 1.115 righe di `lotti_fornitori` (fatture da
aprile a luglio) risultavano tutte disponibili: solo 2 produzioni registrate in
Lotti, nessuna delle due con dosi, quindi niente e' mai stato scalato. Il
magazzino mostrava come presente merce consumata da mesi.

Qui non si indovina niente. Si elenca cio' che e' fermo da piu' di N giorni
(N lo sceglie chi guarda) e lo si chiude solo su richiesta esplicita del
titolare: la riga non si cancella, diventa esaurita con
`chiuso_senza_scarico`, il motivo, chi e quando, e la quantita' che aveva —
cosi' la chiusura si puo' annullare.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

MOTIVO_CHIUSURA = "merce_ferma_senza_scarico"


def data_fattura(lotto: dict) -> Optional[date]:
    valore = str(lotto.get("data_fattura") or "").strip()
    if not valore:
        return None
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(valore[:10], formato).date()
        except ValueError:
            continue
    return None


def _decimale(valore: Any) -> Optional[Decimal]:
    if valore in (None, ""):
        return None
    try:
        return Decimal(str(valore))
    except (InvalidOperation, ValueError):
        return None


def e_ferma(lotto: dict, prima_del: date) -> bool:
    """Disponibile, mai toccata da uno scarico, comprata prima di `prima_del`."""
    if lotto.get("esaurito") or lotto.get("chiuso_senza_scarico"):
        return False
    if lotto.get("storico_utilizzi") or lotto.get("ultimo_utilizzo"):
        return False
    quando = data_fattura(lotto)
    return quando is not None and quando < prima_del


def riepilogo(lotti: Iterable[dict], prima_del: date, esempi: int = 5) -> dict:
    """Merce ferma per mese di fattura, la piu' vecchia prima. Il valore e'
    quantita' x prezzo di fattura; le righe senza prezzo si contano a parte,
    mai come zero."""
    mesi: "OrderedDict[str, dict]" = OrderedDict()
    totale = 0
    valore = Decimal("0")
    senza_prezzo = 0
    ferme = sorted((l for l in lotti if e_ferma(l, prima_del)), key=lambda l: data_fattura(l))
    for l in ferme:
        chiave = data_fattura(l).strftime("%Y-%m")
        mese = mesi.setdefault(chiave, {"mese": chiave, "righe": 0, "valore": Decimal("0"),
                                        "senza_prezzo": 0, "esempi": []})
        mese["righe"] += 1
        totale += 1
        prezzo = _decimale(l.get("prezzo_unitario"))
        qta = _decimale(l.get("quantita_disponibile"))
        if prezzo is None or prezzo <= 0 or qta is None:
            mese["senza_prezzo"] += 1
            senza_prezzo += 1
        else:
            mese["valore"] += prezzo * qta
            valore += prezzo * qta
        if len(mese["esempi"]) < esempi:
            mese["esempi"].append({
                "prodotto": l.get("prodotto_nome"), "fornitore": l.get("fornitore"),
                "data_fattura": l.get("data_fattura"), "quantita": l.get("quantita_disponibile"),
                "unita": l.get("unita_misura"),
            })
    for mese in mesi.values():
        mese["valore"] = str(mese["valore"].quantize(Decimal("0.01")))
    return {
        "prima_del": prima_del.isoformat(),
        "righe": totale,
        "valore": str(valore.quantize(Decimal("0.01"))),
        "valuta": "EUR",
        "senza_prezzo": senza_prezzo,
        "mesi": list(mesi.values()),
        "ids": [l.get("id") for l in ferme if l.get("id")],
    }


def campi_chiusura(lotto: dict, chi: str, adesso: str) -> dict:
    return {
        "esaurito": True,
        "chiuso_senza_scarico": True,
        "motivo_chiusura": MOTIVO_CHIUSURA,
        "chiuso_il": adesso,
        "chiuso_da": chi,
        "quantita_alla_chiusura": lotto.get("quantita_disponibile"),
        "quantita_disponibile": 0,
    }


def campi_riapertura(lotto: dict) -> Optional[dict]:
    if not lotto.get("chiuso_senza_scarico"):
        return None
    return {
        "esaurito": False,
        "chiuso_senza_scarico": False,
        "quantita_disponibile": lotto.get("quantita_alla_chiusura") or 0,
        "riaperto_da_chiusura": lotto.get("chiuso_il"),
    }
