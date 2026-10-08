"""L'unico posto che sa se una fattura è attiva, e con che segno pesa.

In `invoices` ogni fattura 2026 esiste due volte: la copia `archived`
dell'import XML e quella attiva da Drive (misurato il 27/09/2026: 563
`archived`, 706 `imported`, 249 senza `status`). Chi legge l'archivio senza
questo filtro conta ogni fattura due volte, e un motore di abbinamento trova
due candidati identici e si rifiuta di scegliere.

Il filtro sta in `app/constants/fattura_attiva.py`; qui il segno e l'importo.

Il segno: una nota di credito ricevuta (TD04/TD08) riduce il debito verso il
fornitore, non lo aumenta. Un totale che la somma in positivo gonfia la spesa
di due volte il suo importo. Per un **pagamento** conta il netto: una
parcella con ritenuta si paga al netto della ritenuta, che va in F24
(`totale_pagabile_al_fornitore`).
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.payment_allocation_validator import is_credit_note
from app.services.prima_nota_integrity import totale_pagabile_al_fornitore

__all__ = [
    "FILTRO_FATTURA_ATTIVA",
    "STATI_DOCUMENTO_NON_ATTIVI",
    "STATI_IMPORT_NON_ATTIVI",
    "e_fattura_attiva",
    "e_nota_credito",
    "segno_documento",
    "importo_documento_con_segno",
    "importo_pagabile_con_segno",
]

# Il filtro vive in `app/constants/fattura_attiva.py` (senza dipendenze, lo
# leggono anche i moduli di base): qui si riespone, non si ricopia.
from app.constants.fattura_attiva import (  # noqa: E402
    FILTRO_FATTURA_ATTIVA,
    STATI_FATTURA_NON_ATTIVA as STATI_DOCUMENTO_NON_ATTIVI,
    STATI_IMPORT_NON_ATTIVI,
    fattura_attiva as e_fattura_attiva,
)


def e_nota_credito(fattura: Mapping[str, Any]) -> bool:
    """TD04/TD08 (o `document_role` nota di credito): riduce, non aggiunge."""
    return is_credit_note(dict(fattura))


def segno_documento(fattura: Mapping[str, Any]) -> int:
    return -1 if e_nota_credito(fattura) else 1


def _numero(valore: Any) -> float:
    if valore in (None, ""):
        return 0.0
    if isinstance(valore, str):
        testo = valore.strip().replace(" ", "")
        if "," in testo:
            testo = testo.replace(".", "").replace(",", ".")
        valore = testo
    try:
        return float(valore)
    except (TypeError, ValueError):
        return 0.0


def importo_documento_con_segno(fattura: Mapping[str, Any], importo: Any = None) -> float:
    """Il totale del documento, negativo per una nota di credito.

    `importo` permette a chi legge il totale da campi propri di applicare
    soltanto il segno; senza, si legge `total_amount` (campo canonico).
    Il valore assoluto evita il doppio negativo delle note gia' scritte con
    il meno dall'XML.
    """
    base = abs(_numero(fattura.get("total_amount") if importo is None else importo))
    return round(-base if e_nota_credito(fattura) else base, 2)


def importo_pagabile_con_segno(fattura: Mapping[str, Any]) -> float:
    """Quanto esce (o rientra) davvero: netto della ritenuta, con segno."""
    base = totale_pagabile_al_fornitore(dict(fattura))
    return round(-base if e_nota_credito(fattura) else base, 2)
