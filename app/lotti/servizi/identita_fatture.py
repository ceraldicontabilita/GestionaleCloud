"""Identità canonica delle fatture operative di Lotti."""

from __future__ import annotations

from typing import Any, Optional


def query_identita_fattura(
    *,
    numero: Any,
    piva: Any = "",
    fornitore: Any = "",
    data: Any = "",
    source_id: Any = "",
) -> Optional[dict[str, Any]]:
    """Restituisce solo identità complete, mai chiavi con componenti vuoti.

    Le identità ammesse sono numero + P.IVA oppure numero + fornitore + data.
    Il riferimento sorgente è una terza identità forte solo per documenti già
    collegati dal ponte GestionaleCloud. Se nessuna identità è completa non si
    tenta una deduplica: un dato incompleto non deve fondere fatture diverse.
    """
    numero = str(numero or "").strip()
    piva = str(piva or "").strip()
    fornitore = str(fornitore or "").strip()
    data = str(data or "").strip()
    source_id = str(source_id or "").strip()

    identita: list[dict[str, Any]] = []
    if numero and piva:
        identita.append({"numero_fattura": numero, "piva": piva})
    if numero and fornitore and data:
        identita.append({
            "numero_fattura": numero,
            "fornitore": fornitore,
            "data_fattura": data,
        })
    if source_id:
        identita.append({"gestionale_source_id": source_id})
    if not identita:
        return None
    if len(identita) == 1:
        return identita[0]
    return {"$or": identita}
