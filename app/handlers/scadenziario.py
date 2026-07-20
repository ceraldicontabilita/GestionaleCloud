"""Crea nello scadenzario il piano di pagamento dichiarato in FatturaPA."""
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

GIORNI_PER_MODALITA = {
    "bonifico": 30, "sepa": 30, "rid": 30, "riba": 30,
    "assegno": 0, "contanti": 0, "cassa": 0, "carta": 0, "altro": 30,
}


def _data_scadenza(rata: Dict[str, Any], data_fattura: str, metodo: str) -> Tuple[str, bool]:
    """Restituisce (data, usa_fallback), privilegiando sempre i dati XML."""
    if rata.get("data_scadenza"):
        return str(rata["data_scadenza"])[:10], False
    riferimento = rata.get("data_riferimento_termini")
    giorni = rata.get("giorni_termini")
    if riferimento and str(giorni or "").strip():
        try:
            base = datetime.strptime(str(riferimento)[:10], "%Y-%m-%d")
            return (base + timedelta(days=int(giorni))).strftime("%Y-%m-%d"), False
        except (ValueError, TypeError):
            pass
    if data_fattura:
        try:
            base = datetime.strptime(str(data_fattura)[:10], "%Y-%m-%d")
            delta = GIORNI_PER_MODALITA.get(str(metodo).lower(), 30)
            return (base + timedelta(days=delta)).strftime("%Y-%m-%d"), True
        except (ValueError, TypeError):
            return str(data_fattura)[:10], True
    return "", True


def _normalizza_rate(payload: Dict[str, Any], totale: Decimal) -> List[Dict[str, Any]]:
    rate = payload.get("pagamento_rate") or []
    if rate:
        return [dict(rata) for rata in rate]
    return [{
        "blocco_indice": 0,
        "rata_indice": 0,
        "importo": format(totale, "f"),
        "data_scadenza": payload.get("data_scadenza_pagamento") or payload.get("data_scadenza"),
        "modalita": "",
        "_legacy": True,
    }]


async def handler_crea_scadenza(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """Crea una scadenza idempotente per ogni DettaglioPagamento XML."""
    if db is None:
        return {"skipped": True, "reason": "db non disponibile"}
    if (payload.get("tipo_documento") or "").upper() in {"TD04", "TD08"}:
        return {"skipped": True, "reason": "nota di credito, nessuna scadenza"}

    fattura_id = payload.get("fattura_id") or payload.get("id")
    if not fattura_id:
        return {"skipped": True, "reason": "fattura_id mancante"}
    try:
        totale = Decimal(str(payload.get("importo_totale") or payload.get("total_amount") or 0))
    except InvalidOperation:
        totale = Decimal("0")
    if totale <= 0:
        return {"skipped": True, "reason": "importo zero o negativo"}

    fornitore = payload.get("fornitore") or {
        "id": payload.get("fornitore_id"),
        "ragione_sociale": payload.get("fornitore_ragione_sociale", ""),
        "partita_iva": payload.get("fornitore_piva", ""),
    }
    data_fattura = payload.get("data_documento") or payload.get("invoice_date", "")
    metodo = payload.get("metodo_pagamento") or "da_configurare"
    numero = payload.get("numero_documento") or payload.get("invoice_number", "")
    piano_coerente = payload.get("pagamento_rate_coerente") is not False
    rate = _normalizza_rate(payload, totale)
    now = datetime.now(timezone.utc).isoformat()
    create_ids, existing_ids, warnings = [], [], []

    for posizione, rata in enumerate(rate):
        blocco = int(rata.get("blocco_indice", 0) or 0)
        indice = int(rata.get("rata_indice", posizione) or 0)
        chiave = f"{fattura_id}::{blocco}::{indice}"
        importo_raw = str(rata.get("importo") or "").strip()
        importo_valido = True
        try:
            importo_dec = Decimal(importo_raw)
            if importo_dec <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            importo_dec = Decimal("0")
            importo_valido = False
            warnings.append(f"rata {blocco}/{indice}: importo non valido")
        data_scadenza, fallback_data = _data_scadenza(rata, data_fattura, metodo)
        richiede_verifica = not piano_coerente or not importo_valido or fallback_data
        motivi = []
        if not piano_coerente:
            motivi.append("somma rate diversa dal totale fattura")
        if not importo_valido:
            motivi.append("importo rata mancante o non valido")
        if fallback_data:
            motivi.append("data scadenza calcolata per fallback")

        scadenza = {
            "id": chiave,
            "scadenza_key": chiave,
            "fattura_id": fattura_id,
            "numero_fattura": numero,
            "fornitore_id": fornitore.get("id"),
            "fornitore_nome": fornitore.get("ragione_sociale") or fornitore.get("nome", ""),
            "fornitore_piva": fornitore.get("partita_iva") or fornitore.get("piva", ""),
            "importo": float(importo_dec.quantize(Decimal("0.01"))),
            "importo_totale": float(importo_dec.quantize(Decimal("0.01"))),
            "importo_rata": format(importo_dec.quantize(Decimal("0.01")), "f"),
            "blocco_indice": blocco,
            "rata_indice": indice,
            "condizioni_pagamento": rata.get("condizioni_pagamento", ""),
            "modalita_rata": rata.get("modalita", ""),
            "metodo_pagamento": metodo,
            "data_riferimento_termini": rata.get("data_riferimento_termini", ""),
            "giorni_termini": rata.get("giorni_termini", ""),
            "data_fattura": str(data_fattura)[:10] if data_fattura else "",
            "data_scadenza": data_scadenza,
            "stato": "aperta",
            "pagato": False,
            "richiede_verifica": richiede_verifica,
            "motivi_verifica": motivi,
            "created_at": now,
        }
        try:
            result = await db["scadenziario_fornitori"].update_one(
                {"scadenza_key": chiave}, {"$setOnInsert": scadenza}, upsert=True,
            )
            (create_ids if getattr(result, "upserted_id", None) is not None else existing_ids).append(chiave)
        except DuplicateKeyError:
            existing_ids.append(chiave)

    logger.info("[HandlerScadenziario] fattura=%s create=%s esistenti=%s", fattura_id, len(create_ids), len(existing_ids))
    return {
        "fattura_id": fattura_id,
        "scadenze_create": len(create_ids),
        "scadenze_esistenti": len(existing_ids),
        "scadenza_ids": create_ids + existing_ids,
        "warnings": warnings,
    }
