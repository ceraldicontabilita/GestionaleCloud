"""
Coda di verifica per le fatture ESTERE lette dall'AI (mai XML: lo SDI è solo
italiano, i fornitori esteri mandano un semplice PDF via email — vedi
`app/routers/invoices/fatture_upload.py::process_fattura_estera_pdf`).

Scelta utente 14/07/2026: oltre al metodo di pagamento, associare
esplicitamente la P.IVA e costruire un rating di affidabilità per
fornitore — l'utente conferma o corregge i dati letti dall'AI, ogni
conferma/correzione viene registrata in `fatture_estere_verifiche`
(collection dedicata) e usata per calcolare quanto fidarsi delle
letture future dello stesso fornitore.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException

from app.database import Database, Collections
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

# Campi testuali: nome canonico -> campo speculare italiano da tenere in sync
_CAMPI_TESTO = {
    "invoice_number": "numero_fattura",
    "invoice_date": "data_fattura",
    "supplier_name": "cedente_denominazione",
    "supplier_vat": "cedente_piva",
}
# Campi numerici: nome canonico -> campo speculare italiano (None se nessuno)
_CAMPI_NUMERICI = {
    "imponibile": None,
    "iva": None,
    "total_amount": "importo_totale",
}


@router.get("/da-verificare")
@handle_errors
async def lista_da_verificare() -> Dict[str, Any]:
    """Fatture estere importate dall'AI ancora in attesa di conferma/correzione."""
    db = Database.get_db()
    fatture = await db[Collections.INVOICES].find(
        {"verifica_ai": "in_attesa"},
        {"_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1, "data_scadenza": 1,
         "supplier_name": 1, "supplier_vat": 1, "total_amount": 1, "imponibile": 1,
         "iva": 1, "divisa": 1, "documento_inbox_id": 1, "filename": 1, "created_at": 1}
    ).sort("created_at", -1).to_list(200)
    return {"fatture": fatture, "totale": len(fatture)}


@router.get("/affidabilita")
@handle_errors
async def affidabilita_fornitori() -> Dict[str, Any]:
    """Rating di affidabilità della lettura AI per fornitore estero: quante
    verifiche sono state confermate senza correzioni su quante totali."""
    db = Database.get_db()
    pipeline = [
        {"$group": {
            "_id": "$supplier_vat",
            "fornitore_nome": {"$last": "$supplier_name"},
            "totale": {"$sum": 1},
            "corrette": {"$sum": {"$cond": [{"$eq": ["$esito", "confermata"]}, 1, 0]}},
        }},
        {"$sort": {"totale": -1}},
    ]
    risultati = await db["fatture_estere_verifiche"].aggregate(pipeline).to_list(500)
    for r in risultati:
        r["supplier_vat"] = r.pop("_id", "")
        r["percentuale_corrette"] = round(100 * r["corrette"] / r["totale"], 1) if r["totale"] else 0
    return {"fornitori": risultati}


@router.post("/{fattura_id}/verifica")
@handle_errors
async def verifica_fattura(fattura_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """L'utente conferma o corregge i dati letti dall'AI per una fattura
    estera. Se non tocca un campo, quello resta quello letto dall'AI; se lo
    cambia, la correzione viene applicata alla fattura E registrata come
    "lettura sbagliata" per il rating di affidabilità del fornitore.
    """
    db = Database.get_db()
    invoice = await db[Collections.INVOICES].find_one({"id": fattura_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    if invoice.get("verifica_ai") not in ("in_attesa", None):
        raise HTTPException(status_code=409, detail="Fattura già verificata")

    campi_corretti = []
    update_set: Dict[str, Any] = {}

    for campo, mirror in _CAMPI_TESTO.items():
        if campo in data and data[campo] not in (None, ""):
            nuovo = str(data[campo]).strip()
            vecchio = str(invoice.get(campo) or "").strip()
            if nuovo != vecchio:
                campi_corretti.append(campo)
                update_set[campo] = nuovo
                if mirror:
                    update_set[mirror] = nuovo

    for campo, mirror in _CAMPI_NUMERICI.items():
        if campo in data and data[campo] is not None:
            try:
                nuovo = round(float(data[campo]), 2)
            except (TypeError, ValueError):
                continue
            vecchio = round(float(invoice.get(campo) or 0), 2)
            if abs(nuovo - vecchio) > 0.01:
                campi_corretti.append(campo)
                update_set[campo] = nuovo
                if mirror:
                    update_set[mirror] = nuovo

    esito = "corretta" if campi_corretti else "confermata"
    update_set["verifica_ai"] = esito
    update_set["verifica_ai_at"] = datetime.now(timezone.utc).isoformat()
    update_set["verifica_ai_campi_corretti"] = campi_corretti

    # Numero/P.IVA/data cambiati -> la chiave di dedup e la scadenza (data+30gg)
    # vanno ricalcolate, stesso criterio usato all'import (process_xml_bytes).
    if any(c in campi_corretti for c in ("invoice_number", "supplier_vat", "invoice_date")):
        from app.routers.invoices.fatture_upload import generate_invoice_key
        nuovo_numero = update_set.get("invoice_number", invoice.get("invoice_number", ""))
        nuova_piva = update_set.get("supplier_vat", invoice.get("supplier_vat", ""))
        nuova_data = update_set.get("invoice_date", invoice.get("invoice_date", ""))
        update_set["invoice_key"] = generate_invoice_key(nuovo_numero, nuova_piva, nuova_data)
        if "invoice_date" in campi_corretti and nuova_data:
            try:
                update_set["data_scadenza"] = (
                    datetime.strptime(nuova_data, "%Y-%m-%d") + timedelta(days=30)
                ).strftime("%Y-%m-%d")
                update_set["anno"] = int(nuova_data[:4]) if nuova_data[:4].isdigit() else None
            except (ValueError, TypeError):
                pass

    await db[Collections.INVOICES].update_one({"id": fattura_id}, {"$set": update_set})

    # Se l'importo era sbagliato E la partita aperta collegata è ancora
    # integra (nessun pagamento/match ricevuto), aggiorna anche quella.
    # Se è già parzialmente pagata/matchata NON la tocchiamo automaticamente:
    # aggiustare un residuo già in corso è troppo rischioso da fare alla
    # cieca, meglio lasciarlo alla verifica manuale.
    if "total_amount" in campi_corretti:
        try:
            partita = await db["partite_aperte"].find_one(
                {"documento_id": fattura_id, "tipo": "fattura_fornitore"}
            )
            if partita and partita.get("residuo") == partita.get("importo_originale"):
                nuovo_importo = update_set["total_amount"]
                await db["partite_aperte"].update_one(
                    {"id": partita["id"]},
                    {"$set": {"importo_originale": nuovo_importo, "residuo": nuovo_importo}}
                )
        except Exception:
            logger.exception(f"Errore sync partita aperta per fattura {fattura_id}")

    # Storico per il rating di affidabilità del fornitore
    await db["fatture_estere_verifiche"].insert_one({
        "id": str(uuid.uuid4()),
        "fattura_id": fattura_id,
        "supplier_vat": update_set.get("supplier_vat", invoice.get("supplier_vat", "")),
        "supplier_name": update_set.get("supplier_name", invoice.get("supplier_name", "")),
        "esito": esito,
        "campi_corretti": campi_corretti,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    try:
        from app.services.alert_engine import risolvi_alert
        await risolvi_alert("FAT_ESTERA_DA_VERIFICARE", fattura_id, db)
    except Exception:
        logger.exception(f"Errore risoluzione alert verifica per {fattura_id}")

    return {"success": True, "esito": esito, "campi_corretti": campi_corretti}
