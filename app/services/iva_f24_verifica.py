"""Collegamento mensile Liquidazione IVA -> F24 -> quietanza -> banca.

La funzione non crea F24 e non modifica dati: produce un esito verificabile
che mantiene distinti importo IVA, saldo complessivo del modello e prova
dell'addebito bancario.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional

from app.services.f24_payment_evidence import stato_evidenza_pagamento


CODICE_SANZIONE_IVA = "8904"
CODICE_INTERESSI_IVA = "1991"
CODICI_RAVVEDIMENTO_IVA = {CODICE_SANZIONE_IVA, CODICE_INTERESSI_IVA}


def codice_iva_mensile(mese: int) -> str:
    if mese not in range(1, 13):
        raise ValueError("mese IVA non valido")
    return f"60{mese:02d}"


def scadenza_iva_mensile(anno: int, mese: int) -> date:
    """16 del mese successivo, spostato al lunedi se cade nel weekend."""
    if mese == 12:
        scadenza = date(anno + 1, 1, 16)
    else:
        scadenza = date(anno, mese + 1, 16)
    # I versamenti con scadenza dal 1 al 20 agosto sono differiti al giorno
    # 20 senza maggiorazione (quindi l'IVA di luglio non scade il 16).
    if scadenza.month == 8 and scadenza.day == 16:
        scadenza = scadenza.replace(day=20)
    while scadenza.weekday() >= 5:
        scadenza += timedelta(days=1)
    return scadenza


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _anno_riga(riga: Dict[str, Any], f24: Dict[str, Any]) -> Optional[int]:
    for valore in (
        riga.get("anno_riferimento"),
        riga.get("anno"),
        f24.get("anno"),
        f24.get("reference_year"),
    ):
        if str(valore or "").isdigit() and len(str(valore)) == 4:
            return int(valore)
    periodo = str(riga.get("periodo_riferimento") or riga.get("periodo") or "")
    match = re.search(r"(?:19|20)\d{2}", periodo)
    return int(match.group(0)) if match else None


def _righe_erario(f24: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    yield from (f24.get("sezione_erario") or [])


def _codici(f24: Dict[str, Any]) -> set[str]:
    return {
        str(r.get("codice_tributo") or "").strip()
        for r in _righe_erario(f24)
        if r.get("codice_tributo")
    }


def verifica_versamento_iva_da_documenti(
    *,
    anno: int,
    mese: int,
    f24_docs: Iterable[Dict[str, Any]],
    debito_liquidazione: Optional[float] = None,
    oggi: Optional[date] = None,
) -> Dict[str, Any]:
    codice = codice_iva_mensile(mese)
    scadenza = scadenza_iva_mensile(anno, mese)
    oggi = oggi or date.today()
    candidati: List[Dict[str, Any]] = []

    for f24 in f24_docs:
        for riga in _righe_erario(f24):
            if str(riga.get("codice_tributo") or "").strip() != codice:
                continue
            if _anno_riga(riga, f24) != anno:
                continue
            evidenza = stato_evidenza_pagamento(f24)
            codici = _codici(f24)
            candidati.append({
                "f24_id": f24.get("id"),
                "file": f24.get("file_name") or f24.get("filename"),
                "importo_iva": round(_float(riga.get("importo_debito") or riga.get("importo")), 2),
                "saldo_f24": round(_float((f24.get("totali") or {}).get("saldo_netto") or f24.get("importo_totale")), 2),
                "quietanza_id": f24.get("quietanza_id"),
                "evidenza_pagamento": evidenza,
                "ravvedimento": bool(codici & CODICI_RAVVEDIMENTO_IVA),
                "codici_ravvedimento": sorted(codici & CODICI_RAVVEDIMENTO_IVA),
            })

    priorita = {
        "PAGATO_BANCA": 0,
        "QUIETANZA_PRESENTE_DA_VERIFICARE_BANCA": 1,
        "DICHIARATO_PAGATO_DA_VERIFICARE_BANCA": 2,
        "DA_PAGARE": 3,
    }
    candidati.sort(key=lambda c: priorita.get(c["evidenza_pagamento"]["stato"], 9))
    principale = candidati[0] if candidati else None
    pagato_banca = bool(principale and principale["evidenza_pagamento"]["pagato"])
    scaduto = oggi > scadenza and not pagato_banca

    if not candidati:
        stato = "F24_NON_TROVATO"
    elif len(candidati) > 1:
        stato = "F24_MULTIPLI_DA_VERIFICARE"
    elif pagato_banca:
        stato = "PAGATO_BANCA"
    else:
        stato = principale["evidenza_pagamento"]["stato"]

    importo_f24 = principale["importo_iva"] if principale else None
    scostamento = None
    if importo_f24 is not None and debito_liquidazione is not None:
        scostamento = round(importo_f24 - float(debito_liquidazione), 2)

    return {
        "periodo": f"{anno}-{mese:02d}",
        "codice_tributo": codice,
        "scadenza": scadenza.isoformat(),
        "stato": stato,
        "pagato_banca": pagato_banca,
        "scaduto": scaduto,
        "f24_trovati": len(candidati),
        "f24": principale,
        "candidati": candidati,
        "debito_liquidazione": (
            round(float(debito_liquidazione), 2)
            if debito_liquidazione is not None else None
        ),
        "scostamento_f24_liquidazione": scostamento,
        "ravvedimento": {
            "necessario": scaduto,
            "gia_presente_nel_f24": bool(principale and principale["ravvedimento"]),
            "codice_sanzione": CODICE_SANZIONE_IVA,
            "codice_interessi": CODICE_INTERESSI_IVA,
            "codice_tributo_principale": codice,
            "nota": (
                "Importi di sanzione e interessi da confermare prima del versamento; "
                "il gestionale non genera un pagamento senza revisione professionale."
                if scaduto else None
            ),
        },
    }


async def verifica_versamento_iva(
    db, *, anno: int, mese: int, debito_liquidazione: Optional[float] = None,
) -> Dict[str, Any]:
    docs = await db["f24_unificato"].find(
        {"sezione_erario.codice_tributo": codice_iva_mensile(mese)},
        {"_id": 0, "pdf_data": 0},
    ).to_list(5000)
    return verifica_versamento_iva_da_documenti(
        anno=anno,
        mese=mese,
        f24_docs=docs,
        debito_liquidazione=debito_liquidazione,
    )
