"""
date_utils.py — Gestione centralizzata delle date per Gestionale.

Standard interno:
  - Storage DB: ISO 8601 → "YYYY-MM-DD"
  - Display UI: formato italiano → "DD/MM/YYYY"
  - Datetime: ISO 8601 → "YYYY-MM-DDTHH:MM:SS+00:00"

Tutte le funzioni di conversione data passano da qui.
"""

from datetime import datetime, timezone, date


def oggi_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def ora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_to_it(d: str) -> str:
    if not d:
        return ""
    try:
        if "T" in d:
            d = d[:10]
        y, m, day = d.split("-")
        return f"{day}/{m}/{y}"
    except Exception:
        return d


def it_to_iso(d: str) -> str:
    if not d:
        return ""
    d = d.strip()
    if "/" in d:
        parts = d.split("/")
        if len(parts) == 3:
            dd, mm, yyyy = parts
            if len(yyyy) == 2:
                yyyy = "20" + yyyy
            try:
                return f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d}"
            except Exception:
                return d
    return d


def parse_iso(d: str) -> date | None:
    try:
        return date.fromisoformat(d[:10])
    except Exception:
        return None


def anno_da_iso(d: str) -> int:
    try:
        return int(d[:4])
    except Exception:
        return 0
