"""Identita' canoniche dei mittenti email amministrativi.

Un mittente attendibile e' atomico: un indirizzo email esatto, normalizzato.
Non usiamo ``pattern in From`` e non consideriamo il relay PEC (Legalmail/Aruba)
come identita' del mittente quando l'header contiene ``Per conto di:``.

Le regole qui sotto sono il baseline Ceraldi richiesto dal titolare. La tabella
``mittenti_email`` resta configurabile, ma ogni record deve essere normalizzato
con queste funzioni e puo' autorizzare soltanto i tipi documentali dichiarati.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from email.utils import parseaddr
from typing import Iterable, Optional

_EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
_PER_CONTO_DI_RE = re.compile(
    r"per\s+conto\s+di\s*:\s*([^\"<>\s]+@[^\"<>\s]+)",
    re.I,
)


@dataclass(frozen=True)
class CanonicalSenderRule:
    address: str
    label: str
    allowed_types: frozenset[str]
    active: bool = True
    note: str = ""


def normalize_email_address(value: str) -> str:
    """Restituisce un singolo indirizzo RFC normalizzato, oppure stringa vuota."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    _name, parsed = parseaddr(raw)
    candidate = (parsed or raw).strip().strip("<>").lower()
    match = _EMAIL_RE.fullmatch(candidate)
    return candidate if match else ""


def canonical_sender_from_header(value: str) -> str:
    """Estrae il vero mittente, compreso il caso relay PEC ``Per conto di``."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    delegated = _PER_CONTO_DI_RE.search(raw)
    if delegated:
        return normalize_email_address(delegated.group(1))
    return normalize_email_address(raw)


def canonical_sender_pattern(value: str) -> str:
    """Normalizza una regola configurata. Sono ammessi solo indirizzi esatti."""
    return normalize_email_address(value)


def sender_matches_rule(from_header: str, configured_address: str) -> bool:
    actual = canonical_sender_from_header(from_header)
    expected = canonical_sender_pattern(configured_address)
    return bool(actual and expected and actual == expected)


def normalize_document_type(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


# Regole confermate dal titolare. Anthirat e' intenzionalmente esclusa.
DEFAULT_CANONICAL_SENDER_RULES: tuple[CanonicalSenderRule, ...] = (
    CanonicalSenderRule(
        "rosaria.marotta@email.it",
        "Rosaria Marotta - commercialista",
        frozenset({"f24", "quietanza", "comunicazione_pagamento", "dichiarazione_iva"}),
        note="Non usare come fonte ordinaria di estratti conto bancari.",
    ),
    CanonicalSenderRule(
        "f.ferrantini@email.it",
        "Fulvio Ferrantini - consulente del lavoro",
        frozenset({
            "busta_paga", "cedolino", "libro_unico", "riepilogo_paghe", "f24",
            "certificazione_unica", "contributi_inps", "inps", "inail",
        }),
    ),
    CanonicalSenderRule(
        "f.ferrantini@consulentidellavoropec.it",
        "Fulvio Ferrantini - PEC consulente del lavoro",
        frozenset({
            "busta_paga", "cedolino", "libro_unico", "riepilogo_paghe", "f24",
            "certificazione_unica", "contributi_inps", "inps", "inail",
        }),
    ),
    CanonicalSenderRule(
        "grazia.studioferrantini@email.it",
        "Studio Ferrantini - paghe",
        frozenset({
            "busta_paga", "cedolino", "libro_unico", "riepilogo_paghe", "f24",
            "certificazione_unica", "contributi_inps", "inps", "inail",
        }),
    ),
    CanonicalSenderRule(
        "ceraldigroupsrl@gmail.com",
        "Ceraldi Group - posta inviata",
        frozenset({
            "avviso_bonario", "cartella_esattoriale", "cartella_rateizzata",
            "rottamazione", "estratto_conto", "bonifico", "f24", "quietanza",
            "verbale", "pagopa", "ricevuta_pagopa", "altro_amministrativo",
        }),
        note="Serve anche a leggere la Posta inviata verso il commercialista.",
    ),
    CanonicalSenderRule(
        "vincenzoceraldi@gmail.com",
        "Vincenzo Ceraldi - posta inoltrata",
        frozenset({
            "avviso_bonario", "cartella_esattoriale", "cartella_rateizzata",
            "rottamazione", "estratto_conto", "busta_paga", "cedolino",
            "certificazione_unica", "verbale", "pagopa", "ricevuta_pagopa",
        }),
    ),
    CanonicalSenderRule(
        "partenopay@ext.comune.napoli.it",
        "PartenoPay Comune di Napoli",
        frozenset({"pagopa", "ricevuta_pagopa", "verbale"}),
    ),
    CanonicalSenderRule(
        "notifica.acc.campania@pec.agenziariscossione.gov.it",
        "Agenzia Entrate-Riscossione Campania",
        frozenset({"cartella_esattoriale", "cartella_rateizzata", "rottamazione"}),
    ),
    CanonicalSenderRule(
        "tari.avvisibonari@pec.comune.napoli.it",
        "Comune di Napoli - TARI",
        frozenset({"avviso_bonario", "pagopa", "ricevuta_pagopa"}),
    ),
    CanonicalSenderRule(
        "noreply.entrate.tributiminori@pec.comune.napoli.it",
        "Comune di Napoli - Entrate e tributi minori",
        frozenset({"avviso_bonario", "pagopa", "ricevuta_pagopa"}),
    ),
)

EXCLUDED_CANONICAL_SENDERS = frozenset({
    "gestionecredito@anthiratcontrol.it",
})


def is_excluded_sender(from_header: str) -> bool:
    return canonical_sender_from_header(from_header) in EXCLUDED_CANONICAL_SENDERS


def default_rule_for_sender(from_header: str) -> Optional[CanonicalSenderRule]:
    address = canonical_sender_from_header(from_header)
    if not address or address in EXCLUDED_CANONICAL_SENDERS:
        return None
    for rule in DEFAULT_CANONICAL_SENDER_RULES:
        if rule.active and rule.address == address:
            return rule
    return None


def rule_allows_document_type(rule: CanonicalSenderRule, document_type: str) -> bool:
    tipo = normalize_document_type(document_type)
    return tipo in {normalize_document_type(item) for item in rule.allowed_types}


def exact_allowed_addresses(rules: Iterable[CanonicalSenderRule] = DEFAULT_CANONICAL_SENDER_RULES) -> list[str]:
    return [rule.address for rule in rules if rule.active and rule.address not in EXCLUDED_CANONICAL_SENDERS]
