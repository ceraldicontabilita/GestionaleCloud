"""
Endpoint aggiuntivi Archivio Bonifici.
Gestisce associazioni fatture/salari ai bonifici, sync IBAN, ricerche per dipendente.
"""

import re
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from app.database import Database, Collections
from app.services.fattura_attiva import FILTRO_FATTURA_ATTIVA
from app.services.stato_pagamento_fattura import FILTRO_NON_PAGATE
from app.utils.id_fattura import filtro_id
from app.services.payment_document_links import (
    collega_bonifico_fatture,
    valuta_fattura_bonifico,
)
from app.services.entity_relations import revoke_entity_relation
from app.services.identity_matching import identita_coincide
from .classification import classifica_bonifico_dipendente

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/archivio-bonifici", tags=["Archivio Bonifici Extra"])


@router.post("/associa-fattura")
async def associa_fattura_a_bonifico(
    bonifico_id: str = Query(...),
    fattura_id: str = Query(...),
    collection: str = Query("invoices")
) -> Dict[str, Any]:
    """Associa una fattura a un bonifico nei registri attivi e storici."""
    db = Database.get_db()

    # Validazione: fattura_id non può essere vuoto
    if not fattura_id or not fattura_id.strip():
        raise HTTPException(status_code=422, detail="fattura_id non può essere vuoto")

    bonifico = await _trova_bonifico(db, bonifico_id)
    if not bonifico:
        raise HTTPException(404, "Bonifico non trovato in nessuna collection")
    destinazione = await classifica_bonifico_dipendente(db, bonifico)
    if destinazione["destinazione_dipendente"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "Bonifico destinato a un dipendente: può essere associato solo a un salario, "
                "non a una fattura."
            ),
        )

    # Su `invoices` l'id e' un numero su meta' delle righe: si cerca con testo e intero.
    fattura = await db[Collections.INVOICES].find_one(filtro_id(fattura_id), {"_id": 0})
    if not fattura:
        raise HTTPException(404, "Fattura non trovata")
    compatibilita = _valuta_fattura_bonifico(bonifico, fattura)
    # Scelta esplicita del titolare fra i candidati: senza il numero in causale bastano
    # identita' del fornitore e importo al centesimo (mai solo l'importo).
    scelta_dal_titolare = (
        not compatibilita["compatibile"]
        and "importo_esatto" in compatibilita["evidenze"]
        and "identita_fornitore" in compatibilita["evidenze"]
    )
    if not compatibilita["compatibile"] and not scelta_dal_titolare:
        raise HTTPException(
            status_code=409,
            detail=(
                "Associazione non confermata: servono numero fattura esplicito nella causale, "
                "importo identico al centesimo e identità del fornitore coerente."
            ),
        )

    # 1) Prova prima su bonifici_transfers (collection moderna, ID stringa UUID)
    # Controlla se il bonifico è già associato a un'altra fattura (blocca doppia associazione)
    existing = await db["bonifici_transfers"].find_one({"id": bonifico_id}, {"_id": 0, "fattura_associata_id": 1})
    if existing and existing.get("fattura_associata_id") and existing["fattura_associata_id"] != fattura_id:
        raise HTTPException(
            status_code=409,
            detail=f"Bonifico già associato alla fattura {existing['fattura_associata_id']}. Disassocia prima."
        )

    if existing:
        await collega_bonifico_fatture(
            db, bonifico, [fattura], auto=False,
            evidenze=compatibilita["evidenze"] if scelta_dal_titolare else None)
        return {"success": True, "message": "Fattura associata al bonifico (transfers)"}

    # 2) Registro storico: gli identificativi sono normalizzati a stringa.
    try:
        result2 = await db["archivio_bonifici"].update_one(
            {"_id": bonifico_id},
            {"$set": {
                "fattura_associata_id": fattura_id,
                "fattura_collection": collection,
                "fattura_associazione_evidenze": compatibilita["evidenze"],
                "fattura_associazione_score": compatibilita["score"],
                "stato_riconciliazione": "associato",
                "data_associazione": datetime.now(timezone.utc).isoformat(),
            }}
        )
        if result2.modified_count > 0:
            return {"success": True, "message": "Fattura associata al bonifico (archivio)"}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[Bonifici] associazione alla fattura non riuscita anche in "
            "archivio_bonifici: %s", exc)

    raise HTTPException(404, "Bonifico non trovato in nessuna collection")


@router.delete("/disassocia-fattura/{bonifico_id}")
async def disassocia_fattura(bonifico_id: str) -> Dict[str, Any]:
    """Rimuove l'associazione fattura da un bonifico. Supporta entrambe le collection."""
    db = Database.get_db()

    rimozione = {
        "fattura_associata_id": "", "fattura_id": "", "fattura_ids": "",
        "fattura_collection": "", "data_associazione": "",
        "fattura_associazione_evidenze": "",
    }

    # 1) Prova bonifici_transfers
    transfer = await db["bonifici_transfers"].find_one({"id": bonifico_id}, {"_id": 0})
    invoice_ids = set((transfer or {}).get("fattura_ids") or [])
    if (transfer or {}).get("fattura_id"):
        invoice_ids.add(transfer["fattura_id"])
    result = await db["bonifici_transfers"].update_one(
        {"id": bonifico_id},
        {"$unset": rimozione, "$set": {"fattura_associata": False, "stato_riconciliazione": "non_riconciliato"}}
    )
    if result.matched_count > 0:
        for invoice_id in invoice_ids:
            await db["invoices"].update_one(
                {"id": invoice_id},
                {"$pull": {"bonifico_ids": bonifico_id, "payment_document_ids": bonifico_id},
                 "$unset": {"bonifico_id": ""}, "$set": {"bonifico_associato": False}},
            )
            await revoke_entity_relation(
                db,
                source_type="bonifico_pdf",
                source_id=bonifico_id,
                relation_type="documents_invoice_payment",
                target_type="invoice",
                target_id=str(invoice_id),
                actor="manual_unlink",
            )
            movement_id = (transfer or {}).get("movimento_estratto_conto_id")
            if movement_id:
                await revoke_entity_relation(
                    db,
                    source_type="bank_movement",
                    source_id=str(movement_id),
                    relation_type="proves_invoice_payment",
                    target_type="invoice",
                    target_id=str(invoice_id),
                    actor="manual_unlink",
                )
        return {"success": True, "message": "Associazione fattura rimossa (transfers)"}

    # 2) Fallback archivio_bonifici
    try:
        result2 = await db["archivio_bonifici"].update_one(
            {"_id": bonifico_id},
            {"$unset": rimozione, "$set": {"stato_riconciliazione": "non_riconciliato"}}
        )
        if result2.modified_count > 0:
            return {"success": True, "message": "Associazione fattura rimossa (archivio)"}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[Bonifici] rimozione dell'associazione alla fattura non riuscita "
            "anche in archivio_bonifici: %s", exc)

    raise HTTPException(404, "Bonifico non trovato")


async def _trova_bonifico(db, bonifico_id: str) -> Optional[Dict[str, Any]]:
    """Cerca un bonifico nei registri attivo e storico tramite ID stringa."""
    bonifico = await db["bonifici_transfers"].find_one({"id": bonifico_id})
    if bonifico:
        return bonifico
    return await db["archivio_bonifici"].find_one({"_id": bonifico_id})


def _nome_salario(operazione: Dict[str, Any]) -> str:
    return str(
        operazione.get("dipendente")
        or operazione.get("dipendente_nome")
        or operazione.get("nome_dipendente")
        or ""
    ).strip()


def _salario_appartiene_al_dipendente(
    operazione: Dict[str, Any], destinazione: Dict[str, Any]
) -> bool:
    """Blocca i candidati basati sul solo importo: prima viene l'identita'."""
    dipendente_id = str(destinazione.get("dipendente_id") or "").strip()
    operazione_dipendente_id = str(
        operazione.get("dipendente_id") or operazione.get("employee_id") or ""
    ).strip()
    if dipendente_id and operazione_dipendente_id:
        return dipendente_id == operazione_dipendente_id

    nome_destinazione = str(destinazione.get("dipendente_nome_rilevato") or "").strip()
    nome_operazione = _nome_salario(operazione)
    return bool(nome_destinazione and nome_operazione) and identita_coincide(
        nome_destinazione, nome_operazione
    )


@router.post("/ripartizione-salari/{bonifico_id}")
async def ripartizione_salario_erp(bonifico_id: str, data: Dict[str, Any] = Body(...)):
    from app.hr.database import Database as HRDatabase
    from app.hr.routers.dipendenti_cloud import _indici_dipendenti
    from app.services.hr_pagamenti_deposito import risolvi_dipendente
    from app.services.associazione_salari import anteprima, pubblica, conferma
    from app.services.conferma_bonifico import chiavi_bonifico, campi_conferma
    db, hr = Database.get_db(), HRDatabase.get_db()
    b = await _trova_bonifico(db, bonifico_id)
    if not b:
        raise HTTPException(404, "Bonifico non trovato")
    ben = b.get("beneficiario") or {}
    nome = ben.get("nome", "") if isinstance(ben, dict) else str(ben)
    dip, _ = risolvi_dipendente(await _indici_dipendenti(hr), f"{nome} {b.get('causale') or ''}")
    if not dip:
        raise HTTPException(409, "Identifica il dipendente nella pagina HR Bonifici da associare")
    pagamento = {"id": "erp-" + bonifico_id, "gestionale_transfer_id": bonifico_id,
                 "importo": b.get("importo"), "data": b.get("data"), "causale": b.get("causale"),
                 "beneficiario": nome, "cro": b.get("cro_trn"), "rif_banca": b.get("rif_interno"),
                 "hash": b.get("document_hash"), "pdf_filename": b.get("source_file"),
                 "gestionale_movimento_id": b.get("movimento_estratto_conto_id")}
    chiavi = chiavi_bonifico(pagamento)
    code = await hr.bonifici_da_associare.find({}, {"_id": 0, "pdf_data": 0}).to_list(None)
    coda = next((c for c in code if chiavi & chiavi_bonifico(c)), None)
    if coda:
        pagamento = {**coda, **pagamento, "id": coda["id"]}
    if not data.get("conferma"):
        return pubblica(await anteprima(hr, pagamento, dip["id"], data.get("destinazioni"), data.get("collega_key")))
    risultato = await conferma(hr, pagamento, dip["id"], data)
    await db["bonifici_transfers"].update_one({"id": bonifico_id}, {"$set": {
        **campi_conferma("admin"), "salario_associato": True, "dipendente_hr_id": dip["id"],
        "pagamento_esito_key": risultato["pagamento_key"], "ripartizione_salari_versione": 1,
        "operazione_salario_desc": risultato["dipendente"] + " · " + str(len(risultato["quote"])) + " cedolini",
        "stato_riconciliazione": "associato_salario"}})
    return risultato


@router.delete("/disassocia-salario/{bonifico_id}")
async def disassocia_salario(bonifico_id: str) -> Dict[str, Any]:
    """Rimuove l'associazione salario da un bonifico. Supporta entrambe le collection."""
    db = Database.get_db()

    bonifico = await _trova_bonifico(db, bonifico_id)
    if bonifico and bonifico.get("ripartizione_salari_versione") == 1:
        from app.hr.database import Database as HRDatabase
        from app.services.associazione_salari import annulla
        await annulla(HRDatabase.get_db(), bonifico.get("pagamento_esito_key"))

    rimozione = {
        "operazione_salario_id": "", "data_associazione": "",
        "operazione_salario_desc": "", "periodo_salario": "",
        "dipendente_id": "", "dipendente_nome": "",
        "pagamento_esito_key": "", "ripartizione_salari_versione": "", "confermato_manuale": "",
    }

    result = await db["bonifici_transfers"].update_one(
        {"id": bonifico_id},
        {"$unset": rimozione, "$set": {"salario_associato": False, "stato_riconciliazione": "non_riconciliato"}}
    )
    if result.modified_count > 0:
        return {"success": True, "message": "Associazione salario rimossa (transfers)"}

    try:
        result2 = await db["archivio_bonifici"].update_one(
            {"_id": bonifico_id},
            {"$unset": rimozione, "$set": {"salario_associato": False, "stato_riconciliazione": "non_riconciliato"}}
        )
        if result2.modified_count > 0:
            return {"success": True, "message": "Associazione salario rimossa (archivio)"}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[Bonifici] rimozione dell'associazione al salario non riuscita "
            "anche in archivio_bonifici: %s", exc)

    raise HTTPException(404, "Bonifico non trovato in nessuna collection")


def _valuta_fattura_bonifico(
    bonifico: Dict[str, Any], fattura: Dict[str, Any]
) -> Dict[str, Any]:
    """Compatibilita' canonica condivisa con import automatico e UI."""
    return valuta_fattura_bonifico(bonifico, fattura)


@router.get("/fatture-compatibili/{bonifico_id}")
async def get_fatture_compatibili(bonifico_id: str) -> Dict[str, Any]:
    """Trova fatture compatibili usando importo e prova del fornitore."""
    db = Database.get_db()

    bonifico = await _trova_bonifico(db, bonifico_id)
    if not bonifico:
        raise HTTPException(404, "Bonifico non trovato")

    destinazione = await classifica_bonifico_dipendente(db, bonifico)
    if destinazione["destinazione_dipendente"]:
        return {
            "fatture_compatibili": [],
            "non_associabile_fattura": True,
            "motivo": destinazione["motivo_destinazione"],
            "dipendente_nome": destinazione.get("dipendente_nome_rilevato"),
        }

    importo = abs(bonifico.get("importo", 0))

    # Preselezione per importo esatto al centesimo. Il filtro semantico sotto
    # richiede inoltre identità fornitore o riferimento esplicito in causale.
    # Solo fatture attive e non pagate: ogni fattura 2026 esiste anche come
    # copia `archived`, e due candidati identici non li sceglie nessuno.
    condizioni: List[Dict[str, Any]] = [dict(FILTRO_FATTURA_ATTIVA), dict(FILTRO_NON_PAGATE)]
    if importo > 0:
        tolerance = 0.004
        condizioni.append({"$or": [
            {"total_amount": {"$gte": importo - tolerance, "$lte": importo + tolerance}},
            {"totale": {"$gte": importo - tolerance, "$lte": importo + tolerance}},
            {"importo_totale": {"$gte": importo - tolerance, "$lte": importo + tolerance}},
            # Una parcella con ritenuta si paga al netto: il lordo non combacia
            # mai, quindi entra e il confronto al centesimo lo fa `valuta`.
            {"importo_ritenuta": {"$gt": 0}},
        ]})
    query = {"$and": condizioni}

    fatture_raw = await db[Collections.INVOICES].find(
        query, {"_id": 0, "id": 1, "fornitore": 1, "supplier_name": 1,
                "cedente_denominazione": 1, "totale": 1, "total_amount": 1,
                "importo_totale": 1, "invoice_number": 1, "invoice_date": 1,
                "fornitore_denominazione": 1, "importo_ritenuta": 1,
                "pagamento_rate_totale": 1, "pagamento_rate": 1}
    ).to_list(500)

    fatture = []
    for f in fatture_raw:
        valutazione = _valuta_fattura_bonifico(bonifico, f)
        evidenze_f = valutazione["evidenze"]
        # Senza il numero in causale (es. «Preventivo N 1908» pagato, fattura emessa dopo)
        # restano candidati da scegliere: stessa identita' del fornitore e importo al
        # centesimo. Mai applicati da soli (score 60 = proposta).
        solo_candidato = (
            not valutazione["compatibile"]
            and "importo_esatto" in evidenze_f
            and "identita_fornitore" in evidenze_f
        )
        if not valutazione["compatibile"] and not solo_candidato:
            continue
        if solo_candidato:
            valutazione = {**valutazione, "score": 60}
        importo_f = valutazione["importo_fattura"]
        fatture.append({
            "id": f.get("id"),
            "numero_fattura": f.get("invoice_number"),
            "fornitore": (f.get("supplier_name") or f.get("fornitore_denominazione")
                           or f.get("fornitore") or f.get("cedente_denominazione")),
            "data_fattura": f.get("invoice_date"),
            "importo": importo_f,
            "collection": "invoices",
            "compatibilita_score": valutazione["score"],
            "evidenze": valutazione["evidenze"],
        })
    fatture.sort(key=lambda x: x["compatibilita_score"], reverse=True)

    return {"fatture_compatibili": fatture, "non_associabile_fattura": False}


@router.post("/sync-iban-anagrafica")
async def sync_iban_anagrafica() -> Dict[str, Any]:
    """Sincronizza IBAN dai bonifici all'anagrafica dipendenti/fornitori."""
    db = Database.get_db()

    # Prendi tutti i bonifici con IBAN dalla collection attiva (bonifici_transfers);
    # la legacy 'archivio_bonifici' non viene più alimentata dal flusso di import corrente.
    bonifici = await db["bonifici_transfers"].find(
        # Bug reale (audit-codice 04/09/2026): "$ne" ripetuto nel dict
        # letterale sovrascriveva se stesso ({"$ne": None} perso).
        {"beneficiario.iban": {"$exists": True, "$nin": [None, ""]}},
        {"beneficiario": 1}
    ).to_list(5000)

    updated_employees = 0
    updated_suppliers = 0

    for b in bonifici:
        beneficiario_obj = b.get("beneficiario") or {}
        iban = (beneficiario_obj.get("iban") or "").strip()
        beneficiario = (beneficiario_obj.get("nome") or "").strip().upper()

        if not iban:
            continue

        # Prova a matchare con dipendenti
        emp = await db[Collections.EMPLOYEES].find_one({
            "$or": [
                {"nome_completo": {"$regex": beneficiario, "$options": "i"}},
                {"cognome": {"$regex": beneficiario.split()[-1] if beneficiario else "", "$options": "i"}},
            ]
        })
        if emp and not emp.get("iban"):
            await db[Collections.EMPLOYEES].update_one(
                {"_id": emp["_id"]},
                {"$set": {"iban": iban}}
            )
            updated_employees += 1

        # Prova con fornitori
        sup = await db[Collections.SUPPLIERS].find_one({
            "denominazione": {"$regex": beneficiario[:10] if len(beneficiario) > 10 else beneficiario, "$options": "i"}
        })
        if sup and not sup.get("iban"):
            await db[Collections.SUPPLIERS].update_one(
                {"_id": sup["_id"]},
                {"$set": {"iban": iban}}
            )
            updated_suppliers += 1

    return {
        "success": True,
        "totale_bonifici_analizzati": len(bonifici),
        "dipendenti_aggiornati": updated_employees,
        "fornitori_aggiornati": updated_suppliers
    }


@router.get("/dipendente/{dipendente_id}")
async def get_bonifici_dipendente(dipendente_id: str) -> List[Dict[str, Any]]:
    """Recupera i bonifici associati a un dipendente."""
    db = Database.get_db()
    # Cerca per ID dipendente o per nome
    employee = await db[Collections.EMPLOYEES].find_one({"$or": [
        {"_id": dipendente_id}, {"id": dipendente_id},
    ]})

    if not employee:
        return []

    nome = employee.get("nome_completo", employee.get("cognome", ""))

    bonifici = await db["archivio_bonifici"].find({
        "$or": [
            {"operazione_salario_id": {"$exists": True}, "dipendente_id": dipendente_id},
            {"beneficiario": {"$regex": re.escape(nome), "$options": "i"}} if nome else {},
        ]
    }).sort("data", -1).to_list(100)

    # Gli ID del registro sono sempre stringhe serializzabili.
    for b in bonifici:
        b["_id"] = str(b["_id"])

    return bonifici
