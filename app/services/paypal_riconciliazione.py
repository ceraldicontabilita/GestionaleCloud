"""
Supporto PayPal per identita' fornitori e pagamenti PagoPA.

Il collegamento commerciale e bancario canonico vive in
``paypal_reconciliation_links``. Qui restano soltanto gli helper ancora
usati dal mapping anagrafico e dai verbali PagoPA.
"""

import re
import logging
from typing import Dict, Any, List
from app.services.sheets_document_store import SheetDatabase

logger = logging.getLogger(__name__)


# Mappatura beneficiari PayPal → Fornitori nel sistema
PAYPAL_TO_FORNITORE_MAP = {
    "infocert spa": ["infocert", "info cert"],
    "spotify ab": ["spotify"],
    "intesa sanpaolo": ["intesa", "sanpaolo"],
    "aruba spa": ["aruba"],
    "register spa": ["register"],
    "hp italy": ["hp", "hewlett"],
    "adobe": ["adobe"],
    "f.lli casolaro": ["casolaro", "f.lli casolaro", "casolaro hotellerie"],
    "elmax srl": ["elmax"],
    "erredi forniture": ["erredi"],
    "detertecnica": ["detertecnica"],
    "ristofast": ["ristofast"],
    "nuova bever-li": ["beverli", "bever-li", "nuova bever"],
    "erretre": ["erretre", "erre4m"],
    "laspillatura": ["laspillatura", "spillatura"],
    "coltelleria zoppi": ["zoppi", "coltelleria"],
    "bellerofonte": ["bellerofonte"],
    "timbri.it": ["timbri"],
    "indors": ["indors"],
    "wps group": ["wps"],
    "van berkel": ["van berkel", "berkel"],
    "fattura 24": ["fattura24", "fattura 24"],
    "mooney": ["mooney"],
    "lab19": ["lab19"],
    "express checkout": ["express"],  # Generico PayPal
    "pagamento cellulare": [],  # Non mappabile
    "pagamento sito web": [],  # Non mappabile
}


def normalize_string(s: str) -> str:
    """Normalizza stringa per confronto."""
    if not s:
        return ""
    return re.sub(r'[^a-z0-9]', '', s.lower())


def match_fornitore(paypal_name: str, fornitore_name: str) -> float:
    """
    Calcola score di matching tra nome PayPal e fornitore.

    Returns:
        Float 0-1, dove 1 è match perfetto
    """
    if not paypal_name or not fornitore_name:
        return 0.0

    paypal_norm = normalize_string(paypal_name)
    fornitore_norm = normalize_string(fornitore_name)

    # Match esatto
    if paypal_norm == fornitore_norm:
        return 1.0

    # Uno contiene l'altro
    if paypal_norm in fornitore_norm or fornitore_norm in paypal_norm:
        return 0.9

    # Check mappatura conosciuta
    for paypal_key, fornitore_variants in PAYPAL_TO_FORNITORE_MAP.items():
        if normalize_string(paypal_key) in paypal_norm:
            for variant in fornitore_variants:
                if normalize_string(variant) in fornitore_norm:
                    return 0.95

    # Check parole comuni
    paypal_words = set(paypal_norm.split())
    fornitore_words = set(fornitore_norm.split())
    common = paypal_words & fornitore_words
    if common:
        return len(common) / max(len(paypal_words), len(fornitore_words))

    return 0.0


async def riconcilia_multe_pagopa(db: SheetDatabase, transazioni_pagopa: List[Dict[str, Any]]) -> Dict[str, int]:
    """Le multe CdS non vanno su invoices, ma su verbali_noleggio (fase 3)."""
    from app.services.verbali_pagamento_finder import trova_pagamento_verbale, applica_pagamento_a_verbale
    stats = {"totale": len(transazioni_pagopa), "riconciliati": 0}
    for tx in transazioni_pagopa:
        subj = tx.get("transaction_subject", "") or ""
        m_verb = re.search(r'([A-Z]\d{10,12})', subj)
        if m_verb:
            verbale = await db["verbali_noleggio"].find_one({"numero_verbale": m_verb.group(1)})
            if verbale:
                match = await trova_pagamento_verbale(db, verbale)
                if match:
                    vid = verbale.get("id") or verbale.get("numero_verbale")
                    ok = await applica_pagamento_a_verbale(db, vid, match)
                    if ok:
                        stats["riconciliati"] += 1
    return stats
