"""Registro unico delle destinazioni documentali su Google Drive.

Gmail, Import Documenti e ingest Drive devono usare questa stessa mappa. Una
sorgente diversa non cambia mai la cartella canonica del documento.

Le destinazioni non contengono ID Drive: gli ID restano nel registry/configurazione.
Quando una cartella canonica e' una *sorella* di un'area gia' configurata (es.
PAGAMENTI_E_BOLLETTINI_VERBALI accanto a VERBALI_AUTO), il resolver puo'
individuarla tramite il parent osservato su Drive, senza hardcodare la radice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DocumentDestination:
    area: str
    label: str
    sibling_name: Optional[str] = None
    processed_child: Optional[str] = "ELABORATE"


_DESTINATIONS: dict[str, DocumentDestination] = {
    "f24": DocumentDestination("f24", "F24"),
    "quietanza": DocumentDestination("quietanze", "F24_QUIETANZE_PAGAMENTO"),
    "quietanza_f24": DocumentDestination("quietanze", "F24_QUIETANZE_PAGAMENTO"),
    "cedolino": DocumentDestination("cedolini", "CEDOLINI PAGA"),
    "busta_paga": DocumentDestination("cedolini", "CEDOLINI PAGA"),
    "libro_unico": DocumentDestination("cedolini", "CEDOLINI PAGA"),
    "riepilogo_paghe": DocumentDestination("cedolini", "CEDOLINI PAGA"),
    "bonifico": DocumentDestination("bonifici_dipendenti", "BONIFICI DIPENDENTI"),
    "bonifico_dipendente": DocumentDestination("bonifici_dipendenti", "BONIFICI DIPENDENTI"),
    "certificazione_unica": DocumentDestination(
        "cedolini", "CERTIFICAZIONI UNICHE", sibling_name="CERTIFICAZIONI UNICHE", processed_child=None
    ),
    "contributi_inps": DocumentDestination(
        "cedolini", "INPS", sibling_name="INPS", processed_child=None
    ),
    "inps": DocumentDestination("cedolini", "INPS", sibling_name="INPS", processed_child=None),
    "inail": DocumentDestination("cedolini", "INAIL", sibling_name="INAIL", processed_child=None),
    "cartella_esattoriale": DocumentDestination("cartelle_esattoriali", "Cartelle esattoriali"),
    "cartella_rateizzata": DocumentDestination("cartelle_esattoriali", "Cartelle esattoriali"),
    "rottamazione": DocumentDestination("cartelle_esattoriali", "Cartelle esattoriali"),
    "avviso_bonario": DocumentDestination("avvisi_bonari", "Avvisi bonari"),
    "dichiarazione_iva": DocumentDestination("dichiarazioni_iva", "Dichiarazioni IVA"),
    "estratto_conto": DocumentDestination("estratti_conto", "ESTRATTI CONTO"),
    "verbale": DocumentDestination("verbali_auto", "VERBALI_AUTO"),
    "verbale_auto": DocumentDestination("verbali_auto", "VERBALI_AUTO"),
    "pagopa": DocumentDestination(
        "verbali_auto", "PAGAMENTI_E_BOLLETTINI_VERBALI",
        sibling_name="PAGAMENTI_E_BOLLETTINI_VERBALI", processed_child=None,
    ),
    "ricevuta_pagopa": DocumentDestination(
        "verbali_auto", "PAGAMENTI_E_BOLLETTINI_VERBALI",
        sibling_name="PAGAMENTI_E_BOLLETTINI_VERBALI", processed_child=None,
    ),
    "partenopay": DocumentDestination(
        "verbali_auto", "PAGAMENTI_E_BOLLETTINI_VERBALI",
        sibling_name="PAGAMENTI_E_BOLLETTINI_VERBALI", processed_child=None,
    ),
    "noleggio": DocumentDestination("noleggio", "FINANZIAMENTI E NOLEGGI"),
    "finanziamento": DocumentDestination("noleggio", "FINANZIAMENTI E NOLEGGI"),
    "mutuo": DocumentDestination("noleggio", "FINANZIAMENTI E NOLEGGI"),
    "avviso_pagamento_mutuo": DocumentDestination("noleggio", "FINANZIAMENTI E NOLEGGI"),
    "paypal": DocumentDestination("paypal", "PayPal"),
    "fattura": DocumentDestination("fatture", "Fatture"),
    "fattura_xml": DocumentDestination("fatture", "Fatture"),
    "fattura_estera_pdf": DocumentDestination("fatture", "Fatture estere"),
}

_ALIASES = {
    "busta paga": "busta_paga",
    "payslip": "cedolino",
    "cu": "certificazione_unica",
    "cartella": "cartella_esattoriale",
    "avviso": "avviso_bonario",
    "ricevuta pago pa": "ricevuta_pagopa",
    "ricevuta pago-pa": "ricevuta_pagopa",
}


def normalize_document_type(value: str) -> str:
    key = str(value or "").strip().lower().replace("-", "_")
    key = "_".join(part for part in key.replace("/", " ").split() if part)
    return _ALIASES.get(key.replace("_", " "), key)


def destination_for_document_type(value: str) -> Optional[DocumentDestination]:
    return _DESTINATIONS.get(normalize_document_type(value))


def supported_document_types() -> tuple[str, ...]:
    return tuple(sorted(_DESTINATIONS))
