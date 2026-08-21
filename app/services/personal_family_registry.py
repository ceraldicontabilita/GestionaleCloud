"""Anagrafica documentale dei familiari e relativi identificatori.

Il registro non decide da solo la natura contabile del documento: la veste
aziendale esplicita (dipendente, amministratore o intestazione Ceraldi Group)
ha precedenza. Ogni identificatore certo conserva la fonte da cui e' stato
letto; i valori ancora ignoti non vengono ricostruiti o inventati.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


FAMILY_PROFILES: dict[str, dict[str, Any]] = {
    "marina-liuzza": {
        "display_name": "Marina Liuzza",
        "aliases": ("Marina Liuzza", "Liuzza Marina"),
        "identifiers": {"codice_fiscale": ("LZZMRN75L47F839Y",)},
        "evidence": ("cedolino Drive",),
    },
    "ceraldi-valerio": {
        "display_name": "Ceraldi Valerio",
        "aliases": ("Ceraldi Valerio", "Valerio Ceraldi"),
        "identifiers": {"codice_fiscale": ("CRLVLR88H14F839O",)},
        "evidence": ("cedolino Drive",),
    },
    "ceraldi-vincenzo": {
        "display_name": "Ceraldi Vincenzo",
        "aliases": ("Ceraldi Vincenzo", "Vincenzo Ceraldi"),
        "identifiers": {"codice_fiscale": ("CRLVCN74L15F839W",)},
        "evidence": ("cedolino Drive", "dimissione Drive"),
    },
    "ceraldi-michele": {
        "display_name": "Ceraldi Michele",
        "aliases": ("Ceraldi Michele", "Michele Ceraldi"),
        "identifiers": {},
        "evidence": ("F24 personale Drive; CF da verificare",),
    },
    "ceraldi-antonietta": {
        "display_name": "Ceraldi Antonietta",
        "aliases": ("Ceraldi Antonietta", "Antonietta Ceraldi"),
        "identifiers": {
            "codice_fiscale": ("CRLNNT75M55F352C",),
            "codice_contribuente": ("1804135",),
        },
        "evidence": ("cedolino Drive", "avviso TARI Drive"),
    },
    "pane-giuseppina": {
        "display_name": "Pane Giuseppina",
        "aliases": ("Pane Giuseppina", "Giuseppina Pane"),
        "identifiers": {"codice_fiscale": ("PNAGPP58D48F839K",)},
        "evidence": ("modello fiscale Drive",),
        "company_roles": ("legale rappresentante", "amministratrice"),
    },
    "francesco-iazzetta": {
        "display_name": "Francesco Iazzetta",
        "aliases": ("Francesco Iazzetta", "Iazzetta Francesco"),
        "identifiers": {},
        "evidence": ("relazione familiare confermata dall'utente; identificativi da acquisire",),
    },
}

# Campi supportati quando un parser legge una nuova fattura/utenza. Questi
# valori sono relazioni persona-fornitore, non identificatori fiscali globali.
SUPPORTED_ACCOUNT_IDENTIFIERS = (
    "partita_iva", "codice_contribuente", "codice_cliente", "numero_cliente",
    "numero_utente", "numero_contratto", "posizione", "pod", "pdr",
    "codice_fornitura", "targa",
)

_EMPLOYMENT_TERMS = (
    "dimission", "unilav", "cedolin", "busta paga", "buste paga",
    "documenti dipendenti", "contratti dipendenti", "certificazioni dipendenti",
    "lavoro dipendente", "compenso amministratore",
)
_COMPANY_TERMS = ("ceraldi group", "04523831214")


def normalize(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", raw.upper()).split())


def is_employment_context(text: Any) -> bool:
    value = normalize(text)
    return any(normalize(term) in value for term in _EMPLOYMENT_TERMS)


def is_company_context(text: Any) -> bool:
    value = normalize(text)
    return any(normalize(term) in value for term in _COMPANY_TERMS)


def match_family_person(text: Any) -> dict[str, Any] | None:
    """Ritorna una persona solo per nome completo o identificatore esatto."""
    value = normalize(text)
    compact = value.replace(" ", "")
    if not value:
        return None
    for person_id, profile in FAMILY_PROFILES.items():
        matched_by: list[str] = []
        for alias in profile.get("aliases", ()):
            if normalize(alias) in value:
                matched_by.append(f"nome:{alias}")
        for kind, identifiers in profile.get("identifiers", {}).items():
            for identifier in identifiers:
                if normalize(identifier).replace(" ", "") in compact:
                    matched_by.append(f"{kind}:{identifier}")
        if matched_by:
            return {"person_id": person_id, **profile, "matched_by": matched_by}
    return None


def family_search_terms(query: Any) -> set[str]:
    """Espande nome/alias/identificatore per la ricerca documentale."""
    match = match_family_person(query)
    if not match:
        raw = str(query or "").strip().casefold()
        return {raw} if raw else set()
    terms = {normalize(alias) for alias in match.get("aliases", ())}
    for identifiers in match.get("identifiers", {}).values():
        terms.update(normalize(identifier) for identifier in identifiers)
    return {term.casefold() for term in terms if term}


def public_profiles() -> list[dict[str, Any]]:
    return [
        {
            "id": person_id,
            "display_name": profile["display_name"],
            "aliases": list(profile.get("aliases", ())),
            "identifiers": {key: list(values) for key, values in profile.get("identifiers", {}).items()},
            "supported_account_identifiers": list(SUPPORTED_ACCOUNT_IDENTIFIERS),
            "evidence": list(profile.get("evidence", ())),
            "company_roles": list(profile.get("company_roles", ())),
        }
        for person_id, profile in FAMILY_PROFILES.items()
    ]
