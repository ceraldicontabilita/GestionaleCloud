"""Identità HR: un alias ambiguo non autorizza ad assegnare denaro a qualcuno."""
from typing import Iterable


def indicizza_alias_univoci(coppie: Iterable[tuple[str, dict]]) -> dict:
    result = {}
    for alias, employee in coppie:
        key = str(alias or "").strip().upper()
        if not key:
            continue
        if key not in result:
            result[key] = employee
        elif result[key] is not None and result[key].get("id") != employee.get("id"):
            result[key] = None
    return result


def dipendente_unico(candidati: Iterable[dict]) -> dict | None:
    records = {str(record["id"]): record for record in candidati if record.get("id")}
    return next(iter(records.values())) if len(records) == 1 else None
