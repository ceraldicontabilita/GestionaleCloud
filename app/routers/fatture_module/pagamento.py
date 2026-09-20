"""
Fatture Module - Operazioni di pagamento e riconciliazione.
"""
from fastapi import HTTPException, File, UploadFile, Body
from typing import Dict, Any
from datetime import datetime, timezone

from app.database import Database
from app.routers.fatture_module.ciclo_utils import COL_SCADENZIARIO
from .common import COL_FORNITORI, COL_FATTURE_RICEVUTE, logger


from app.services.invoice_payments import (
    InvoiceBankReconciliationRequest,
    ManualInvoicePaymentRequest,
    register_manual_invoice_payment,
)


async def paga_fattura_manuale(
    payload: ManualInvoicePaymentRequest,
) -> Dict[str, Any]:
    """API rigorosa e atomica per il pagamento manuale."""
    if isinstance(payload, dict):
        try:
            payload = ManualInvoicePaymentRequest.model_validate(payload)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Payload pagamento non valido") from exc
    return await register_manual_invoice_payment(Database.get_db(), payload)


async def cambia_metodo_pagamento_fattura(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Modifica il metodo di pagamento di una fattura."""
    db = Database.get_db()
    
    fattura_id = payload.get("fattura_id")
    nuovo_metodo = payload.get("metodo")
    
    if not fattura_id or not nuovo_metodo:
        raise HTTPException(status_code=400, detail="fattura_id e metodo sono obbligatori")
    
    fattura = await db[COL_FATTURE_RICEVUTE].find_one({"id": fattura_id})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    metodo_precedente = fattura.get("metodo_pagamento")
    
    # Aggiorna fattura
    await db[COL_FATTURE_RICEVUTE].update_one(
        {"id": fattura_id},
        {"$set": {
            "metodo_pagamento": nuovo_metodo,
            "metodo_pagamento_precedente": metodo_precedente,
            "metodo_pagamento_modificato_manualmente": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Aggiorna scadenze collegate
    await db[COL_SCADENZIARIO].update_many(
        {"fattura_id": fattura_id},
        {"$set": {"metodo_pagamento": nuovo_metodo, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    # Aggiorna metodo predefinito fornitore se richiesto
    piva = fattura.get("fornitore_partita_iva") or fattura.get("supplier_vat")
    if piva and payload.get("aggiorna_fornitore"):
        await db[COL_FORNITORI].update_one(
            {"partita_iva": piva},
            {"$set": {
                "metodo_pagamento": nuovo_metodo,
                "metodo_pagamento_predefinito": nuovo_metodo,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
    
    return {
        "success": True,
        "fattura_id": fattura_id,
        "metodo_precedente": metodo_precedente,
        "metodo_nuovo": nuovo_metodo
    }


async def riconcilia_fattura_con_estratto_conto(
    payload: InvoiceBankReconciliationRequest,
) -> Dict[str, Any]:
    """API atomica: numero fattura e importo al centesimo sono obbligatori."""
    from app.services.invoice_payments import reconcile_invoice_bank_movement

    if isinstance(payload, dict):
        try:
            payload = InvoiceBankReconciliationRequest.model_validate(payload)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Payload riconciliazione non valido") from exc
    return await reconcile_invoice_bank_movement(Database.get_db(), payload)


async def candidati_bancari_fattura(fattura_id: str) -> Dict[str, Any]:
    """Elenca movimenti bancari compatibili; non crea collegamenti."""
    from app.services.invoice_payments import find_invoice_bank_candidates

    return await find_invoice_bank_candidates(Database.get_db(), fattura_id)


async def verifica_incoerenze_estratto_conto() -> Dict[str, Any]:
    """Verifica incoerenze tra fatture e estratto conto."""
    db = Database.get_db()
    
    fatture_banca = await db[COL_FATTURE_RICEVUTE].find(
        {"metodo_pagamento": {"$in": ["bonifico", "banca", "sepa"]}, "pagato": True, "riconciliato": {"$ne": True}},
        {"_id": 0, "id": 1, "numero_documento": 1, "importo_totale": 1, "fornitore_ragione_sociale": 1, "data_pagamento": 1}
    ).to_list(1000)
    
    incoerenze = []
    for f in fatture_banca:
        importo = f.get("importo_totale", 0)
        data = f.get("data_pagamento", "")
        
        movimento = await db["estratto_conto_movimenti"].find_one({
            "importo": {"$gte": importo - 0.5, "$lte": importo + 0.5},
            "data": {"$gte": data[:10] if data else "", "$lte": (data[:10] if data else "") + "T23:59:59"} if data else {},
            "riconciliato": {"$ne": True}
        })
        
        if not movimento:
            incoerenze.append({
                "fattura_id": f.get("id"),
                "numero": f.get("numero_documento"),
                "importo": importo,
                "fornitore": f.get("fornitore_ragione_sociale"),
                "data_pagamento": data,
                "problema": "Nessun movimento bancario corrispondente"
            })
    
    return {
        "totale_fatture_banca_pagate": len(fatture_banca),
        "incoerenze": len(incoerenze),
        "dettagli": incoerenze[:50]
    }


async def aggiorna_metodi_pagamento_da_fornitori() -> Dict[str, Any]:
    """Aggiorna SOLO il metodo di pagamento delle fatture dal fornitore
    (ricopia metodo_pagamento quando la fattura non ce l'ha ancora).

    Il metodo del fornitore decide il lato Cassa/Banca, ma non costituisce
    una riconciliazione bancaria: il flag ``riconciliato`` viene impostato
    soltanto dopo il riscontro con un movimento reale dell'estratto conto.
    L'eventuale scrittura automatica in Prima Nota e' gestita dal writer
    canonico di importazione, non da questa sincronizzazione anagrafica.
    """
    db = Database.get_db()

    fatture = await db[COL_FATTURE_RICEVUTE].find(
        {"metodo_pagamento": {"$in": [None, "", "da_configurare"]}},
        {"_id": 0, "id": 1, "fornitore_partita_iva": 1, "supplier_vat": 1, "fornitore_piva": 1}
    ).to_list(10000)

    aggiornate = 0

    # OTTIMIZZAZIONE: carica TUTTI i fornitori in una sola query (no N+1)
    pive_necessarie = set()
    for f in fatture:
        p = f.get("fornitore_partita_iva") or f.get("supplier_vat") or f.get("fornitore_piva")
        if p:
            pive_necessarie.add(p)
    
    fornitori_map = {}
    if pive_necessarie:
        async for forn in db[COL_FORNITORI].find(
            {"$or": [
                {"partita_iva": {"$in": list(pive_necessarie)}},
                {"piva": {"$in": list(pive_necessarie)}}
            ]},
            {"_id": 0, "partita_iva": 1, "piva": 1, "metodo_pagamento": 1}
        ):
            p1 = forn.get("partita_iva")
            p2 = forn.get("piva")
            if p1:
                fornitori_map[p1] = forn
            if p2 and p2 != p1:
                fornitori_map[p2] = forn

    for f in fatture:
        piva = f.get("fornitore_partita_iva") or f.get("supplier_vat") or f.get("fornitore_piva")
        if not piva:
            continue
        
        fornitore = fornitori_map.get(piva)
        if not fornitore:
            continue
        
        metodo = (fornitore.get("metodo_pagamento") or "").lower()
        if not metodo:
            continue

        update = {
            "metodo_pagamento": metodo,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        await db[COL_FATTURE_RICEVUTE].update_one({"id": f["id"]}, {"$set": update})
        aggiornate += 1

    return {
        "success": True,
        "fatture_aggiornate": aggiornate,
        "fatture_riconciliate_auto": 0,  # rimosso: il metodo di pagamento non è mai prova di riconciliazione
        "totale_analizzate": len(fatture)
    }




async def riconcilia_fatture_paypal() -> Dict[str, Any]:
    """Alias storico del motore PayPal canonico e idempotente."""
    from app.services.paypal_reconciliation_links import riprocessa_collegamenti_paypal
    from app.routers.paypal_statements import _auto_riconcilia
    db = Database.get_db()
    try:
        collegamenti_prima = await riprocessa_collegamenti_paypal(db)
        banca = await _auto_riconcilia(db, applica=True)
        collegamenti_dopo = await riprocessa_collegamenti_paypal(db)
        return {
            "success": True,
            "collegamenti_prima": collegamenti_prima,
            "banca": banca,
            "collegamenti_dopo": collegamenti_dopo,
        }
    except Exception as e:
        logger.error(f"Errore riconciliazione PayPal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def lista_fatture_paypal() -> Dict[str, Any]:
    """
    Restituisce la lista delle fatture riconciliate via PayPal.
    """
    db = Database.get_db()
    
    try:
        # Cerca nelle invoices le fatture con riconciliato_paypal o metodo PayPal
        fatture = await db["invoices"].find(
            {"$or": [
                {"riconciliato_paypal": True},
                {"metodo_pagamento": "PayPal"}
            ]},
            {"_id": 0}
        ).sort("invoice_date", -1).to_list(500)
        
        totale_importo = sum(f.get("total_amount", f.get("importo_totale", 0)) or 0 for f in fatture)
        
        return {
            "fatture": fatture,
            "totale": len(fatture),
            "importo_totale": totale_importo
        }
    except Exception as e:
        logger.error(f"Errore lista fatture PayPal: {e}")
        return {"fatture": [], "totale": 0, "importo_totale": 0}


async def import_paypal_file(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Alias compatibile verso l'unica pipeline di import PayPal."""
    from app.routers.paypal_statements import import_paypal_csv, import_paypal_pdf
    try:
        filename = file.filename.lower()
        if filename.endswith('.csv'):
            return await import_paypal_csv(file)
        elif filename.endswith('.pdf'):
            return await import_paypal_pdf(file)
        raise HTTPException(status_code=400, detail="Formato file non supportato. Usa CSV o PDF.")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        logger.error(f"Errore import PayPal: {e}")
        raise HTTPException(status_code=500, detail=str(e))
