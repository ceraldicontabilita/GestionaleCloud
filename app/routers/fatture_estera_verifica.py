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
from datetime import datetime, timezone
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


_PROIEZIONE_VERIFICATA = {
    "_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1, "supplier_name": 1,
    "supplier_vat": 1, "total_amount": 1, "imponibile": 1, "iva": 1, "divisa": 1,
    "documento_inbox_id": 1, "filename": 1, "verifica_ai": 1, "verifica_ai_at": 1,
    "verifica_ai_campi_corretti": 1, "metodo_pagamento": 1, "metodo_pagamento_dichiarato": 1,
    "stato": 1, "stato_pagamento": 1, "payment_status": 1, "pagato": 1, "paid": 1,
    "stato_finanziario": 1, "data_pagamento": 1, "paypal_transaction_id": 1,
    "prima_nota_banca_id": 1, "prima_nota_cassa_id": 1, "in_attesa_riscontro_banca": 1,
    "riconciliato": 1,
}


def _stato_pagamento_verificata(fattura: Dict[str, Any]) -> Dict[str, Any]:
    """Cosa si sa del pagamento, in parole: nessuna prova = «da collegare»."""
    from app.services.stato_pagamento_fattura import e_pagata

    if fattura.get("paypal_transaction_id"):
        pagata = e_pagata(fattura)
        return {"codice": "paypal", "pagata": pagata,
                "testo": "PayPal · addebito in banca trovato" if pagata
                else "PayPal collegato · addebito in banca da trovare"}
    if fattura.get("prima_nota_cassa_id"):
        return {"codice": "cassa", "pagata": True, "testo": "Pagata in cassa"}
    if fattura.get("prima_nota_banca_id"):
        if fattura.get("in_attesa_riscontro_banca"):
            return {"codice": "banca_dichiarata", "pagata": True,
                    "testo": "Banca dichiarata · movimento da trovare"}
        return {"codice": "banca", "pagata": True, "testo": "Banca · movimento collegato"}
    if e_pagata(fattura):
        return {"codice": "pagata", "pagata": True, "testo": "Pagata"}
    return {"codice": "da_collegare", "pagata": False, "testo": "Pagamento da collegare"}


@router.get("/verificate")
@handle_errors
async def lista_verificate(limit: int = 50) -> Dict[str, Any]:
    """Fatture estere gia' confermate dal titolare, le piu' recenti prima.

    Dopo «Conferma / Correggi» la fattura esce dalla coda: qui si vede che la
    conferma c'e' stata e come e' stata pagata. Se nessun pagamento e'
    collegato, la riga porta i pagamenti PayPal candidati (importo al
    centesimo) da scegliere; il bonifico si cerca nell'estratto conto.
    """
    from app.services.paypal_reconciliation_links import candidati_paypal_per_fattura

    db = Database.get_db()
    limite = max(1, min(int(limit or 50), 200))
    fatture = await db[Collections.INVOICES].find(
        {"verifica_ai": {"$in": ["confermata", "corretta"]}}, _PROIEZIONE_VERIFICATA,
    ).sort("verifica_ai_at", -1).to_list(limite)
    for fattura in fatture:
        fattura["pagamento"] = _stato_pagamento_verificata(fattura)
        fattura["candidati_paypal"] = []
        if fattura["pagamento"]["codice"] == "da_collegare":
            try:
                fattura["candidati_paypal"] = await candidati_paypal_per_fattura(db, fattura)
            except Exception as exc:  # una riga rotta non svuota la pagina
                logger.warning("Candidati PayPal della fattura estera %s non letti: %s: %s",
                               fattura.get("id"), type(exc).__name__, exc)
    return {"fatture": fatture, "totale": len(fatture)}


@router.post("/{fattura_id}/collega-paypal")
@handle_errors
async def collega_paypal(fattura_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Il titolare sceglie il pagamento PayPal fra i candidati della fattura."""
    from app.services.paypal_reconciliation_links import collega_paypal_scelto_dal_titolare

    transaction_id = str(data.get("transaction_id") or "").strip()
    if not transaction_id:
        raise HTTPException(status_code=400, detail="Scegli il pagamento PayPal")
    db = Database.get_db()
    fattura = await db[Collections.INVOICES].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    esito = await collega_paypal_scelto_dal_titolare(db, fattura, transaction_id)
    if not esito.get("collegata"):
        raise HTTPException(status_code=409, detail={
            "code": "PAYPAL_NON_COLLEGABILE",
            "message": "Pagamento PayPal non collegabile a questa fattura",
            "details": {"motivo": esito.get("motivo")},
        })
    fattura = await db[Collections.INVOICES].find_one({"id": fattura_id}, _PROIEZIONE_VERIFICATA) or {}
    return {"success": True, "pagamento": _stato_pagamento_verificata(fattura),
            "finalizzazione": esito.get("finalizzazione")}


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
        from app.services.fatture_canonico import invoice_key
        nuovo_numero = update_set.get("invoice_number", invoice.get("invoice_number", ""))
        nuova_piva = update_set.get("supplier_vat", invoice.get("supplier_vat", ""))
        nuova_data = update_set.get("invoice_date", invoice.get("invoice_date", ""))
        update_set["invoice_key"] = invoice_key(nuovo_numero, nuova_piva, nuova_data)
        # Nessuna scadenza: le fatture fornitore non ne hanno (titolare, 19/09/2026).
        if "invoice_date" in campi_corretti and nuova_data[:4].isdigit():
            update_set["anno"] = int(nuova_data[:4])

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
        contabilita = await ricalcola_contabilita_fattura_estera(db, fattura_id, esito)
    except Exception as exc:  # la verifica resta salvata: il ricalcolo si ripete
        logger.exception("Ricalcolo contabile della fattura estera %s fallito", fattura_id)
        contabilita = {"stato": "errore", "errore": f"{type(exc).__name__}: {exc}"}

    # Dati confermati: il pagamento PayPal si cerca adesso, non al prossimo giro.
    paypal: Dict[str, Any] = {}
    try:
        from app.services.paypal_reconciliation_links import collega_fattura_paypal_appena_importata
        fattura_verificata = await db[Collections.INVOICES].find_one({"id": fattura_id}, {"_id": 0})
        if fattura_verificata and not fattura_verificata.get("paypal_transaction_id"):
            paypal = await collega_fattura_paypal_appena_importata(db, fattura_verificata)
    except Exception as exc:
        logger.warning("Ricerca PayPal della fattura estera %s non riuscita: %s: %s",
                       fattura_id, type(exc).__name__, exc)
        paypal = {"collegata": False, "motivo": f"errore: {type(exc).__name__}"}

    try:
        from app.services.alert_engine import risolvi_alert
        await risolvi_alert("FAT_ESTERA_DA_VERIFICARE", fattura_id, db)
    except Exception:
        logger.exception(f"Errore risoluzione alert verifica per {fattura_id}")

    return {"success": True, "esito": esito, "campi_corretti": campi_corretti,
            "contabilita": contabilita, "paypal": {"collegata": bool(paypal.get("collegata")),
                                                   "motivo": paypal.get("motivo")}}


async def ricalcola_contabilita_fattura_estera(db, fattura_id: str, esito: str) -> Dict[str, Any]:
    """Dopo la verifica i dati sono del titolare, non piu' dell'AI.

    Si rifanno con i motori unici la classificazione (centro di costo, IVA
    detraibile) e, se il conto di costo o gli importi della scrittura non
    tornano piu', la scrittura del libro giornale: si storna e si registra di
    nuovo, mai si corregge sul posto.
    """
    from app.handlers.learning import handler_classifica_cdc
    from app.routers.accounting.piano_conti import determina_conti_fattura
    from app.services.eventi_fattura import costruisci_evento_fattura_created
    from app.services.manutenzione_giornale import _riregistra
    from app.services.registrazione_contabile import (
        COLL_MOVIMENTI, FILTRO_SCRITTURA_ATTIVA, storna_registrazione_fattura,
    )

    fattura = await db[Collections.INVOICES].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        return {"stato": "saltato", "motivo": "fattura non trovata"}
    classificazione = await handler_classifica_cdc(costruisci_evento_fattura_created(fattura), db)
    fattura = await db[Collections.INVOICES].find_one({"id": fattura_id}, {"_id": 0}) or fattura

    scrittura = await db[COLL_MOVIMENTI].find_one(
        {"tipo": "fattura_acquisto", "fattura_id": fattura_id,
         "stato": {"$ne": "stornato"}, **FILTRO_SCRITTURA_ATTIVA}, {"_id": 0})
    if not scrittura:
        return {"classificazione": classificazione, "giornale": "nessuna scrittura"}
    conto_costo = (await determina_conti_fattura(db, fattura))["costo"]["codice"]
    conti_scritti = {r.get("conto_codice") for r in scrittura.get("righe") or [] if r.get("dare")}
    totale_scritto = round(sum(float(r.get("dare") or 0) for r in scrittura.get("righe") or []), 2)
    totale_fattura = round(float(fattura.get("total_amount") or 0), 2)
    if conto_costo in conti_scritti and abs(totale_scritto - totale_fattura) < 0.01:
        return {"classificazione": classificazione, "giornale": "invariato"}
    if esito == "riallineata":
        motivo = (f"fattura estera riallineata alle regole di classificazione: conto {conto_costo}, "
                  f"totale {totale_fattura:.2f}")
    else:
        motivo = f"fattura estera {esito} dal titolare: conto {conto_costo}, totale {totale_fattura:.2f}"
    storno = await storna_registrazione_fattura(db, fattura_id, motivo)
    nuova = await _riregistra(db, fattura_id)
    return {"classificazione": classificazione, "giornale": "riregistrato",
            "storno": storno, "nuova_registrazione": nuova.get("stato")}


async def riallinea_fatture_estere_in_attesa(db) -> Dict[str, Any]:
    """Le fatture estere ancora da confermare seguono le regole attuali.

    La classificazione di una fattura letta dal PDF si decide all'import; se le
    regole cambiano dopo (i terminali SumUp erano finiti su «commissioni POS» e
    la scrittura su «acquisto merci»), la fattura restava sbagliata finche'
    qualcuno non la confermava. Qui si ripassa con lo stesso motore della
    conferma: classificazione rifatta e, se il conto non torna, storno e nuova
    registrazione. ``verifica_ai`` resta ``in_attesa``: i dati letti dall'AI li
    conferma sempre il titolare. Idempotente: una fattura gia' allineata da'
    «invariato».
    """
    fatture = await db[Collections.INVOICES].find(
        {"verifica_ai": "in_attesa"}, {"_id": 0, "id": 1},
    ).to_list(500)
    esito: Dict[str, Any] = {"esaminate": 0, "riregistrate": [], "errori": []}
    for fattura in fatture:
        esito["esaminate"] += 1
        try:
            ricalcolo = await ricalcola_contabilita_fattura_estera(db, fattura["id"], "riallineata")
        except Exception as exc:  # una fattura rotta non ferma le altre
            logger.warning("Riallineamento fattura estera %s non riuscito: %s: %s",
                           fattura["id"], type(exc).__name__, exc)
            esito["errori"].append({"fattura_id": fattura["id"], "errore": f"{type(exc).__name__}: {exc}"})
            continue
        if ricalcolo.get("giornale") == "riregistrato":
            esito["riregistrate"].append(fattura["id"])
    return esito
