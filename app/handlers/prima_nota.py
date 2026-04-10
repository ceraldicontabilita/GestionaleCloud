"""
Handler Prima Nota — reagisce a fattura.pagata e cedolino.importato
Scrive automaticamente in prima_nota_banca o prima_nota_cassa.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

METODI_CASSA  = {"cassa", "contanti"}
METODI_BANCA  = {"bonifico", "sepa", "rid", "riba", "assegno", "carta", "altro", "misto", "banca"}


async def handler_prima_nota_fattura(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Quando una fattura viene pagata, scrive il movimento in prima nota.
    Cassa → prima_nota_cassa | Banca → prima_nota_banca
    """
    if db is None:
        return {"skipped": True, "reason": "db non disponibile"}

    fattura_id   = payload.get("fattura_id") or payload.get("id")
    importo      = float(payload.get("importo_totale") or payload.get("total_amount") or 0)
    metodo       = (payload.get("metodo_pagamento") or "").lower()
    numero_doc   = payload.get("numero_documento") or payload.get("invoice_number", "")
    fornitore    = payload.get("fornitore", {})
    data_pag     = payload.get("data_pagamento") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if importo <= 0:
        return {"skipped": True, "reason": "importo zero"}

    # Determina collection
    if metodo in METODI_CASSA:
        collection = "prima_nota_cassa"
    elif metodo in METODI_BANCA:
        collection = "prima_nota_banca"
    else:
        return {"skipped": True, "reason": f"metodo pagamento sconosciuto: {metodo}"}

    # Anti-duplicato
    esistente = await db[collection].find_one({"fattura_id": fattura_id, "source": "fattura_pagata"})
    if esistente:
        return {"skipped": True, "reason": "movimento già presente", "movimento_id": esistente["id"]}

    fornitore_nome = fornitore.get("ragione_sociale") or fornitore.get("nome", "")
    movimento = {
        "id":           str(uuid.uuid4()),
        "fattura_id":   fattura_id,
        "data":         data_pag[:10],
        "tipo":         "uscita",
        "importo":      importo,
        "descrizione":  f"Pagamento fattura {numero_doc} - {fornitore_nome[:40]}",
        "categoria":    "Fornitori",
        "fornitore_id": fornitore.get("id"),
        "fornitore_piva": fornitore.get("partita_iva") or fornitore.get("piva", ""),
        "riferimento":  numero_doc,
        "metodo":       metodo,
        "source":       "fattura_pagata",
        "anno":         int(data_pag[:4]) if data_pag else datetime.now().year,
        "mese":         int(data_pag[5:7]) if len(data_pag) >= 7 else datetime.now().month,
        "created_at":   datetime.now(timezone.utc).isoformat(),
    }

    await db[collection].insert_one(movimento.copy())
    logger.info(f"[HandlerPrimaNota] Fattura {fattura_id} → {collection} €{importo}")
    return {"movimento_id": movimento["id"], "collection": collection, "importo": importo}


async def handler_prima_nota_cedolino(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Quando arriva un cedolino, scrive automaticamente il movimento in prima_nota_salari.
    """
    if db is None:
        return {"skipped": True, "reason": "db non disponibile"}

    cedolino_id   = payload.get("cedolino_id") or payload.get("id")
    dipendente_id = payload.get("dipendente_id")
    nome          = payload.get("nome_dipendente") or payload.get("nome", "")
    cf            = payload.get("codice_fiscale", "")
    netto         = float(payload.get("netto") or payload.get("netto_in_busta") or 0)
    mese          = payload.get("mese")
    anno          = payload.get("anno")
    periodo       = f"{mese:02d}/{anno}" if mese and anno else ""

    if netto <= 0:
        return {"skipped": True, "reason": "netto zero o negativo"}

    # Anti-duplicato
    anti_dup = {"dipendente_id": dipendente_id, "mese": mese, "anno": anno, "source": "cedolino_auto"}
    if dipendente_id and mese and anno:
        esistente = await db["prima_nota_salari"].find_one(anti_dup)
        if esistente:
            return {"skipped": True, "reason": "movimento già presente", "movimento_id": esistente["id"]}

    movimento = {
        "id":             str(uuid.uuid4()),
        "cedolino_id":    cedolino_id,
        "dipendente_id":  dipendente_id,
        "nome_dipendente": nome,
        "codice_fiscale": cf,
        "data":           f"{anno}-{mese:02d}-01" if anno and mese else "",
        "tipo":           "uscita",
        "importo":        netto,
        "descrizione":    f"Stipendio {nome} {periodo}".strip(),
        "categoria":      "Stipendi",
        "mese":           mese,
        "anno":           anno,
        "periodo":        periodo,
        "source":         "cedolino_auto",
        "created_at":     datetime.now(timezone.utc).isoformat(),
    }

    await db["prima_nota_salari"].insert_one(movimento.copy())
    logger.info(f"[HandlerPrimaNota] Cedolino {nome} {periodo} → prima_nota_salari €{netto}")
    return {"movimento_id": movimento["id"], "netto": netto, "periodo": periodo}
