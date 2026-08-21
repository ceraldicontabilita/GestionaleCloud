"""Regola trasversale fatto -> obblighi -> attese -> evidenze.

Un fatto autorevole crea immediatamente le proprie attese obbligatorie. Le
evidenze successive possono soltanto soddisfarle o segnalarne l'ambiguita':
non possono inventare a posteriori l'obbligo che dovrebbero provare.
"""
from enum import Enum
from typing import Any, Dict, Iterable, Mapping


class ExpectationStatus(str, Enum):
    ATTESO = "ATTESO"
    DA_VERIFICARE = "DA_VERIFICARE"
    IN_ELABORAZIONE = "IN_ELABORAZIONE"
    ERRORE = "ERRORE"
    SODDISFATTO = "SODDISFATTO"
    NON_APPLICABILE = "NON_APPLICABILE"
    SUPERATO = "SUPERATO"


OPEN_EXPECTATION_STATES = frozenset({
    ExpectationStatus.ATTESO.value,
    ExpectationStatus.DA_VERIFICARE.value,
    ExpectationStatus.IN_ELABORAZIONE.value,
    ExpectationStatus.ERRORE.value,
})
TERMINAL_POSITIVE_STATES = frozenset({
    ExpectationStatus.SODDISFATTO.value,
    ExpectationStatus.NON_APPLICABILE.value,
    ExpectationStatus.SUPERATO.value,
})


def expectation_fields(
    *,
    expectation_type: str,
    owner: str,
    source_fact_id: str,
    satisfied: bool = False,
) -> Dict[str, Any]:
    """Metadati minimi obbligatori di una nuova attesa."""
    if not expectation_type or not owner or not source_fact_id:
        raise ValueError("tipo, owner e fatto sorgente dell'attesa sono obbligatori")
    return {
        "record_role": "expectation",
        "expectation_type": expectation_type,
        "expectation_owner": owner,
        "source_fact_id": source_fact_id,
        "expectation_status": (
            ExpectationStatus.SODDISFATTO.value
            if satisfied else ExpectationStatus.ATTESO.value
        ),
    }


def expectation_evidence_fields(
    *,
    satisfied: bool,
    evidence_ids: Iterable[str],
) -> Dict[str, Any]:
    """Transizione deterministica prodotta da una o piu' evidenze."""
    ids = list(dict.fromkeys(str(item) for item in evidence_ids if item))
    return {
        "expectation_status": (
            ExpectationStatus.SODDISFATTO.value
            if satisfied else ExpectationStatus.DA_VERIFICARE.value
        ),
        "expectation_evidence_ids": ids,
    }


def mandatory_expectations_closed(expectations: Iterable[Mapping[str, Any]]) -> bool:
    """Un processo chiude solo se tutte le attese obbligatorie sono positive."""
    mandatory = [item for item in expectations if item.get("mandatory", True)]
    return bool(mandatory) and all(
        item.get("expectation_status") in TERMINAL_POSITIVE_STATES
        for item in mandatory
    )
