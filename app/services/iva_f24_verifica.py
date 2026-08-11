"""Collegamento mensile Liquidazione IVA -> F24 -> quietanza -> banca.

La funzione non crea F24 e non modifica dati: produce un esito verificabile
che mantiene distinti importo IVA, saldo complessivo del modello e prova
dell'addebito bancario.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

from app.services.f24_payment_evidence import stato_evidenza_pagamento
from app.services.f24_canonico import normalizza_righe_tributo


CODICE_SANZIONE_IVA = "8904"
CODICE_INTERESSI_IVA = "1991"
CODICI_RAVVEDIMENTO_IVA = {CODICE_SANZIONE_IVA, CODICE_INTERESSI_IVA}


def codice_iva_mensile(mese: int) -> str:
    if mese not in range(1, 13):
        raise ValueError("mese IVA non valido")
    return f"60{mese:02d}"


def scadenza_iva_mensile(anno: int, mese: int) -> date:
    """Compatibilita': restituisce la data legale dal calendario canonico."""
    from app.services.fiscal_deadlines import monthly_deadline

    return date.fromisoformat(monthly_deadline(anno, mese)["scadenza_legale"])


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
    for row in normalizza_righe_tributo(f24):
        if row["section"] == "ERARIO":
            yield row


def _codici(f24: Dict[str, Any]) -> set[str]:
    return {
        str(r.get("tax_code") or "").strip()
        for r in _righe_erario(f24)
        if r.get("tax_code")
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
    from app.services.fiscal_deadlines import monthly_deadline
    from app.services.iva_liquidation_query import euros, money_cents

    deadline = monthly_deadline(anno, mese)
    scadenza = date.fromisoformat(deadline["scadenza_legale"])
    oggi = oggi or date.today()
    candidati: List[Dict[str, Any]] = []

    for f24 in f24_docs:
        for riga in _righe_erario(f24):
            if str(riga.get("tax_code") or "").strip() != codice:
                continue
            source = riga.get("source_fields") or {}
            periodo = riga.get("reference_period")
            anno_riga = int(str(periodo)[:4]) if periodo else _anno_riga(source, f24)
            if anno_riga != anno:
                continue
            evidenza = stato_evidenza_pagamento(f24)
            codici = _codici(f24)
            importo_iva_cents = int(riga.get("debit_cents") or money_cents(riga.get("debit_amount")))
            saldo_f24_cents = int(
                (f24.get("totali") or {}).get("saldo_netto_cents")
                or money_cents((f24.get("totali") or {}).get("saldo_netto") or f24.get("importo_totale"))
            )
            candidati.append({
                "f24_id": f24.get("id"),
                "file": f24.get("file_name") or f24.get("filename"),
                "importo_iva_cents": importo_iva_cents,
                "importo_iva": euros(importo_iva_cents),
                "saldo_f24_cents": saldo_f24_cents,
                "saldo_f24": euros(saldo_f24_cents),
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
    versato_documentalmente = bool(
        principale and principale["evidenza_pagamento"].get("versato_documentalmente")
    )
    data_versamento = (
        principale["evidenza_pagamento"].get("data_versamento_documentale")
        if principale else None
    )
    data_versamento_iso = str(data_versamento)[:10] if data_versamento else None
    tardivo = bool(data_versamento_iso and data_versamento_iso > scadenza.isoformat())
    scaduto = oggi > scadenza and not versato_documentalmente

    if not candidati:
        stato = "F24_NON_TROVATO"
    elif len(candidati) > 1:
        stato = "F24_MULTIPLI_DA_VERIFICARE"
    elif pagato_banca:
        stato = "PAGATO_BANCA"
    else:
        stato = principale["evidenza_pagamento"]["stato"]

    importo_f24 = principale["importo_iva"] if principale else None
    importo_f24_cents = principale["importo_iva_cents"] if principale else None
    debito_liquidazione_cents = (
        money_cents(debito_liquidazione) if debito_liquidazione is not None else None
    )
    scostamento = None
    scostamento_cents = None
    if importo_f24_cents is not None and debito_liquidazione_cents is not None:
        scostamento_cents = importo_f24_cents - debito_liquidazione_cents
        scostamento = euros(scostamento_cents)

    return {
        "periodo": f"{anno}-{mese:02d}",
        "codice_tributo": codice,
        "scadenza": scadenza.isoformat(),
        **deadline,
        "stato": stato,
        "pagato_banca": pagato_banca,
        "versato_documentalmente": versato_documentalmente,
        "data_versamento_documentale": data_versamento_iso,
        "scaduto": scaduto,
        "f24_trovati": len(candidati),
        "f24": principale,
        "candidati": candidati,
        "debito_liquidazione": (
            euros(debito_liquidazione_cents)
            if debito_liquidazione is not None else None
        ),
        "debito_liquidazione_cents": debito_liquidazione_cents,
        "importo_f24_cents": importo_f24_cents,
        "scostamento_f24_liquidazione": scostamento,
        "scostamento_f24_liquidazione_cents": scostamento_cents,
        "ravvedimento": {
            "necessario": bool(
                scaduto
                or (versato_documentalmente and tardivo and not (principale and principale["ravvedimento"]))
            ),
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
    from app.services.tax_payment_query import TaxPaymentQueryService

    docs = await TaxPaymentQueryService(db).list_documents()
    return verifica_versamento_iva_da_documenti(
        anno=anno,
        mese=mese,
        f24_docs=docs,
        debito_liquidazione=debito_liquidazione,
    )
