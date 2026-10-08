"""Stato canonico del pagamento F24 basato sulle evidenze disponibili.

Il modello F24 e l'email che lo contiene non provano il versamento. Una
quietanza valida prova invece il versamento documentale del tributo, pur senza
sostituire il movimento dell'estratto conto quando il gestionale deve affermare
che l'uscita finanziaria e' stata verificata anche in banca.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


STATO_PAGATO_BANCA = "PAGATO_BANCA"
STATO_PARZIALMENTE_PAGATO_BANCA = "PARZIALMENTE_PAGATO_BANCA"
STATO_QUIETANZA_DA_VERIFICARE = "QUIETANZA_PRESENTE_DA_VERIFICARE_BANCA"
STATO_DICHIARATO_DA_VERIFICARE = "DICHIARATO_PAGATO_DA_VERIFICARE_BANCA"
STATO_DA_PAGARE = "DA_PAGARE"

_CAMPI_ID_BANCA = (
    "movimento_bancario_id",
    "bank_movement_id",
    "estratto_conto_id",
    "movimento_bancario_ref",
    "evidenza_bancaria_id",
)


def riferimento_bancario(f24: Dict[str, Any]) -> Optional[str]:
    """Restituisce l'identificativo della prova bancaria, se presente."""
    for campo in _CAMPI_ID_BANCA:
        valore = f24.get(campo)
        if valore not in (None, ""):
            return str(valore)
    movimento = f24.get("movimento_bancario")
    if isinstance(movimento, dict):
        valore = movimento.get("id") or movimento.get("movimento_id")
        if valore not in (None, ""):
            return str(valore)
    return None


def data_pagamento_banca(f24: Dict[str, Any]) -> Optional[Any]:
    """Data dell'addebito bancario, mai la data stampata sulla quietanza."""
    for campo in (
        "data_pagamento_effettivo",
        "data_addebito_banca",
        "bank_paid_date",
    ):
        valore = f24.get(campo)
        if valore not in (None, ""):
            return valore
    movimento = f24.get("movimento_bancario")
    if isinstance(movimento, dict):
        return (
            movimento.get("data_contabile")
            or movimento.get("data")
            or movimento.get("booking_date")
        )
    return None


def ha_evidenza_bancaria(f24: Dict[str, Any]) -> bool:
    """True solo con riferimento identificabile e data dell'addebito."""
    return bool(riferimento_bancario(f24) and data_pagamento_banca(f24))


def ha_quietanza(f24: Dict[str, Any]) -> bool:
    return bool(
        f24.get("quietanza_id")
        or f24.get("protocollo_quietanza")
        or f24.get("riconciliato_quietanza") is True
    )


def data_pagamento_quietanza(f24: Dict[str, Any]) -> Optional[Any]:
    """Data risultante dalla quietanza, distinta dalla data bancaria."""
    for campo in (
        "data_pagamento_quietanza",
        "data_versamento_quietanza",
        "quietanza_payment_date",
    ):
        valore = f24.get(campo)
        if valore not in (None, ""):
            return valore
    quietanza = f24.get("quietanza")
    if isinstance(quietanza, dict):
        return quietanza.get("data_pagamento") or quietanza.get("data_versamento")
    return None


def stato_evidenza_pagamento(f24: Dict[str, Any]) -> Dict[str, Any]:
    """Classifica la prova di pagamento senza fidarsi dei flag legacy."""
    from app.services.payment_allocation_validator import to_cents

    residual_cents = int(
        f24.get("importo_residuo_cents")
        if isinstance(f24.get("importo_residuo_cents"), int)
        else to_cents(f24.get("importo_residuo"))
    )
    if f24.get("allocazioni_banca") and residual_cents > 0:
        return {
            "stato": STATO_PARZIALMENTE_PAGATO_BANCA,
            "pagato": False,
            "verificato_banca": True,
            "data_pagamento": None,
            "movimento_bancario_id": None,
            "quietanza_presente": ha_quietanza(f24),
            "versato_documentalmente": False,
            "data_versamento_documentale": None,
            "importo_residuo_cents": residual_cents,
            "importo_residuo": residual_cents / 100,
            "tributi_aperti": [
                r.get("codice") for r in (f24.get("saldo_tributi") or {}).get("righe_aperte", [])
            ],
        }
    if ha_evidenza_bancaria(f24):
        data_banca = data_pagamento_banca(f24)
        return {
            "stato": STATO_PAGATO_BANCA,
            "pagato": True,
            "verificato_banca": True,
            "data_pagamento": data_banca,
            "movimento_bancario_id": riferimento_bancario(f24),
            "quietanza_presente": ha_quietanza(f24),
            "versato_documentalmente": True,
            "data_versamento_documentale": data_banca,
        }
    if ha_quietanza(f24):
        data_quietanza = data_pagamento_quietanza(f24)
        return {
            "stato": STATO_QUIETANZA_DA_VERIFICARE,
            "pagato": False,
            "verificato_banca": False,
            "data_pagamento": None,
            "movimento_bancario_id": None,
            "quietanza_presente": True,
            "versato_documentalmente": True,
            "data_versamento_documentale": data_quietanza,
        }
    if f24.get("pagato_manualmente") or f24.get("pagamento_dichiarato_manualmente"):
        return {
            "stato": STATO_DICHIARATO_DA_VERIFICARE,
            "pagato": False,
            "verificato_banca": False,
            "data_pagamento": None,
            "movimento_bancario_id": None,
            "quietanza_presente": False,
            "versato_documentalmente": False,
            "data_versamento_documentale": None,
        }
    return {
        "stato": STATO_DA_PAGARE,
        "pagato": False,
        "verificato_banca": False,
        "data_pagamento": None,
        "movimento_bancario_id": None,
        "quietanza_presente": False,
        "versato_documentalmente": False,
        "data_versamento_documentale": None,
    }


def patch_quietanza_associata(
    *, quietanza_id: str, protocollo: str = "", data_quietanza: Any = None,
) -> Dict[str, Any]:
    """Campi da salvare quando il documento combacia, senza fingere la banca."""
    return {
        "status": "da_pagare",
        "stato_pagamento": "DA_VERIFICARE_BANCA",
        "pagato": False,
        "quietanza_id": quietanza_id,
        "protocollo_quietanza": protocollo,
        "data_pagamento_quietanza": data_quietanza,
        "riconciliato_quietanza": True,
        "pagamento_verificato_banca": False,
    }


def patch_pagamento_banca(
    *, movimento_id: str, data_pagamento: Any, riferimento: Optional[str] = None,
) -> Dict[str, Any]:
    """Campi canonici da salvare dopo un match univoco con l'estratto conto."""
    return {
        "status": "pagato",
        "stato_pagamento": "PAGATO",
        "pagato": True,
        "pagamento_verificato_banca": True,
        "fonte_prova_pagamento": "estratto_conto",
        "movimento_bancario_id": movimento_id,
        "movimento_bancario_ref": riferimento or movimento_id,
        "data_pagamento_effettivo": data_pagamento,
    }
