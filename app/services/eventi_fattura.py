"""Il payload di `fattura.created`, costruito in un posto solo.

Fino al 19/09/2026 `fatture_upload.py` lo componeva due volte, a mano, in due
punti lontani (upload manuale e import automatico). Le due copie erano quasi
identiche, e il «quasi» era un difetto: quella dell'upload manuale leggeva
`supplier_result["nuovo"]`, una chiave che `ensure_supplier_exists` non
restituisce (torna `supplier_created`). Un nome di campo sbagliato non da'
errore, da' silenzio: `fornitore_nuovo` era **sempre** falso su quel
percorso, e l'alert `FORN_NUOVO_INCOMPLETO` non e' mai scattato per una
fattura caricata a mano.

Da qui passano tutti: i due punti di import e il replay del pregresso.
"""
from typing import Any, Dict, List, Optional

from app.services.stato_pagamento_fattura import e_pagata

__all__ = [
    "CAMPI_RATA_EVENTO",
    "pagamento_rate_per_evento",
    "costruisci_evento_fattura_created",
]

#: Della rata viaggia solo cio' che serve allo scadenzario: mai IBAN,
#: mai beneficiario.
CAMPI_RATA_EVENTO = (
    "blocco_indice", "rata_indice", "condizioni_pagamento", "modalita",
    "importo", "data_scadenza", "data_riferimento_termini", "giorni_termini",
)


def pagamento_rate_per_evento(rate: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Propaga solo i dati necessari allo scadenzario, mai IBAN o beneficiario."""
    return [{campo: rata.get(campo) for campo in CAMPI_RATA_EVENTO} for rata in (rate or [])]


def costruisci_evento_fattura_created(
    invoice: Dict[str, Any],
    *,
    supplier_result: Optional[Dict[str, Any]] = None,
    fornitore_id: Optional[str] = None,
    metodo_pagamento: Optional[str] = None,
    data_scadenza: Optional[str] = None,
) -> Dict[str, Any]:
    """Il payload di `fattura.created` a partire dalla fattura salvata.

    `supplier_result` e' l'esito di `ensure_supplier_exists`, quando c'e':
    da li' vengono l'id del fornitore e il flag «creato adesso». I parametri
    espliciti vincono su quanto e' scritto sulla fattura, perche' all'import
    `metodo_pagamento` e `data_scadenza` sono appena stati calcolati e
    possono non essere ancora stati salvati.

    La data del documento e' `invoice_date`: e' il campo che l'import scrive
    per primo. `data_documento` lo **deriva** il motore IVA, quindi su una
    fattura mai passata di li' non c'e'.
    """
    esito = supplier_result or {}
    fornitore_data = invoice.get("fornitore") or {}
    if not isinstance(fornitore_data, dict):
        fornitore_data = {}

    if metodo_pagamento is None:
        metodo_pagamento = invoice.get("metodo_pagamento")
    if data_scadenza is None:
        data_scadenza = invoice.get("data_scadenza")
    if fornitore_id is None:
        fornitore_id = esito.get("supplier_id") or invoice.get("supplier_id")

    return {
        "fattura_id": invoice["id"],
        "numero_documento": invoice.get("invoice_number", ""),
        "tipo_documento": invoice.get("tipo_documento") or "TD01",
        "importo_totale": invoice.get("total_amount", 0),
        "fornitore_id": fornitore_id,
        "fornitore_ragione_sociale": invoice.get("supplier_name", ""),
        "fornitore_piva": invoice.get("supplier_vat", ""),
        "fornitore_nuovo": bool(esito.get("supplier_created", False)),
        "fornitore_iban": fornitore_data.get("iban"),
        "metodo_pagamento": metodo_pagamento,
        "data_documento": invoice.get("invoice_date", ""),
        "data_scadenza": data_scadenza,
        "stato": invoice.get("status", "imported"),
        # «E' pagata?» si chiede in un posto solo: lo stato vive in cinque
        # campi e il solo `stato_pagamento` apriva una partita su una pagata.
        "pagato": e_pagata(invoice),
        "righe_linee": invoice.get("linee", []),
        # Solo le fatture estere lette dal PDF: senza righe XML e' l'unico
        # testo che dice cosa si e' comprato (un lettore SumUp non e' una
        # commissione). Vuoto per le fatture XML.
        "descrizione": " · ".join(invoice.get("descrizione_righe_ai") or []),
        "imponibile": invoice.get("imponibile", 0),
        "iva": invoice.get("iva", 0),
        "pagamento_rate": pagamento_rate_per_evento(invoice.get("pagamento_rate", [])),
        "pagamento_rate_coerente": invoice.get("pagamento_rate_coerente"),
    }
