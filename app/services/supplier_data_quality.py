"""Regole condivise per qualità anagrafica fornitori.

La qualità fiscale e quella dei contatti sono assi distinti.  Nessun router
deve più inventare una propria definizione di ``dati_incompleti``.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


FISCAL_FIELDS = ("ragione_sociale", "partita_iva", "comune")
CONTACT_FIELDS = ("email", "telefono")


def _value(record: Dict[str, Any], field: str) -> Any:
    aliases = {
        "ragione_sociale": ("ragione_sociale", "denominazione", "nome", "name"),
        "partita_iva": ("partita_iva", "piva", "vat_number", "vat"),
        "comune": ("comune", "city"),
        "email": ("email", "pec"),
        "telefono": ("telefono", "phone", "telephone"),
    }
    return next((record.get(key) for key in aliases[field] if record.get(key)), None)


def supplier_incomplete_fields(record: Dict[str, Any], *, include_contacts: bool = True) -> Dict[str, List[str]]:
    fiscal = [field for field in FISCAL_FIELDS if not str(_value(record, field) or "").strip()]
    contacts = [field for field in CONTACT_FIELDS if not str(_value(record, field) or "").strip()]
    return {"fiscali": fiscal, "contatti": contacts if include_contacts else []}


def is_supplier_incomplete(record: Dict[str, Any], *, include_contacts: bool = True) -> bool:
    fields = supplier_incomplete_fields(record, include_contacts=include_contacts)
    return bool(fields["fiscali"] or fields["contatti"])


def apply_supplier_quality(record: Dict[str, Any]) -> Dict[str, Any]:
    fields = supplier_incomplete_fields(record)
    return {
        "dati_incompleti": bool(fields["fiscali"]),
        "campi_fiscali_mancanti": fields["fiscali"],
        "contatti_incompleti": bool(fields["contatti"]),
        "campi_contatto_mancanti": fields["contatti"],
    }
