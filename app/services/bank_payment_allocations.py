"""Allocazioni canoniche movimento bancario -> una o piu' fatture."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List
from uuid import uuid4
import logging
import re

from fastapi import HTTPException

from app.services.accounting_relation_writers import record_bank_invoice_allocation
from app.services.identity_matching import (
    alias_fornitore,
    soggetto_causale_bancaria,
    soggetto_pagante_coerente,
)
from app.services.payment_allocation_validator import (
    existing_invoice_allocations_cents,
    invoice_total_cents,
    to_cents,
    validate_invoice_allocation,
)
from app.services.bank_reconciliation_rules import classify_bank_movement
from app.services.mapping_piano_conti import completa_conti_prima_nota
from app.services.scadenze_rate_service import applica_quota_scadenze
from app.services.scritture_contabili import FILTRO_MOVIMENTO_ATTIVO, scrivi_movimento_se_assente
from app.services.sumup_conto import collezione_del_movimento
from app.services.prima_nota_integrity import assorbi_righe_dichiarate, totale_pagabile_al_fornitore
from app.services.stato_pagamento_fattura import FILTRO_DA_RISCONTRARE, FILTRO_NON_PAGATE

logger = logging.getLogger(__name__)

# Chiave di idempotenza della riga di Prima Nota Banca scritta dal motore
# canonico per un movimento: una sola uscita per prova bancaria, anche se
# ripartita su piu' fatture (le quote stanno in ``allocazioni_fatture``).
def chiave_idempotenza_pagamento_banca(movement_id: str) -> str:
    return f"banca:{movement_id}:pagamento_fatture"


def evidenza_scadenza_id(movement_id: str, invoice_id: str) -> str:
    """Stessa evidenza usata dallo storico (``banca:<ec>:<fattura>``): una
    quota gia' applicata alle rate non viene applicata due volte."""
    return f"banca:{movement_id}:{invoice_id}"


def _e_spesa_con_carta(movement: Dict[str, Any]) -> bool:
    """Pagamento con una carta (Nexi, Mastercard SumUp), non un bonifico."""
    if movement.get("tipo") == "carta_credito" or movement.get("banca") == "Nexi":
        return True
    return (
        str(movement.get("id") or "").startswith("sumup_conto:")
        and "bonifico" not in str(movement.get("tipo_transazione") or "").lower()
    )


def _metodo_pagamento(movement: Dict[str, Any]) -> str:
    from app.services.riconciliazione_bancaria import classifica_strumento_bancario

    if _e_spesa_con_carta(movement):
        return "Carta"
    strumento = classifica_strumento_bancario(
        str(movement.get("descrizione_originale") or movement.get("descrizione") or "")
    )
    if strumento["codice"] in {"riba", "bonifico", "addebito_diretto", "assegno", "paypal"}:
        return strumento["label"]
    return "Bonifico"


async def _aggiorna_partita_aperta(
    db, *, invoice_id: str, quota_cents: int, movement_id: str, now: str,
    movement_collection: str = "estratto_conto_movimenti",
) -> Dict[str, Any] | None:
    """Chiude (o riduce) la partita aperta della fattura, una sola volta per
    movimento, e registra il match nella collezione letta dalla Dashboard
    Relazionale (``riconciliazioni_match``)."""
    from app.services.partite_aperte_engine import COLL_PARTITE, chiudi_partita

    match_id = f"bank:{movement_id}:{invoice_id}"
    partita = await db[COLL_PARTITE].find_one(
        {"documento_id": invoice_id, "tipo": "fattura_fornitore",
         "stato": {"$in": ["aperta", "parziale"]}},
        {"_id": 0},
    )
    if not partita or match_id in (partita.get("match_ids") or []):
        return None
    esito = await chiudi_partita(partita["id"], match_id, quota_cents / 100, db)
    await db["riconciliazioni_match"].update_one(
        {"id": match_id},
        {"$setOnInsert": {
            "id": match_id,
            "movimento_id": movement_id,
            "movimento_collection": movement_collection,
            "partita_id": partita["id"],
            "partita_collection": COLL_PARTITE,
            "tipo_match": "fattura_fornitore",
            "importo_riconciliato": quota_cents / 100,
            "confidenza": 1.0,
            "origine": "auto",
            "stato": "confermato",
            "created_at": now,
            "confirmed_at": now,
            "confirmed_by": "sistema",
        }},
        upsert=True,
    )
    return esito


async def _propaga_fattura_pagata(
    db, *, invoice_id: str, metodo: str, data_pagamento: str,
    movement_id: str, quota_cents: int, actor: str,
) -> None:
    """Evento FATTURA_PAGATA: alert risolti e audit ("Fattura pagata via ...").
    Best-effort, mai bloccante."""
    try:
        from app.services.event_bus import EventTypes, propagate_event

        await propagate_event(EventTypes.FATTURA_PAGATA, {
            "fattura_id": invoice_id,
            "metodo_pagamento": metodo,
            "data_pagamento": data_pagamento,
            "movimento_id": movement_id,
            "importo": quota_cents / 100,
        }, db, source_module=f"bank_payment_allocations:{actor}")
    except Exception:
        logger.exception("Propagazione fattura.pagata non riuscita per %s", invoice_id)


async def _proietta_prima_nota_banca(
    db, movement: Dict[str, Any], invoice_ids: List[str],
    public_allocations: List[Dict[str, Any]], *, now: str, operation_id: str,
    metodo: str, automatic: bool, numeri_fattura: List[str],
) -> List[str]:
    """Una sola riga di Prima Nota Banca per movimento: se l'import dell'EC o
    un motore precedente l'hanno gia' scritta viene completata (mai
    affiancata da una seconda uscita), altrimenti nasce dal writer unico."""
    movement_id = str(movement.get("id") or "")
    pn_query = {"$or": [
        {"estratto_conto_id": movement_id},
        {"movimento_bancario_id": movement_id},
        {"movimento_estratto_conto_id": movement_id},
    ]}
    comuni = {
        "fattura_id": invoice_ids[0] if len(invoice_ids) == 1 else None,
        "invoice_id": invoice_ids[0] if len(invoice_ids) == 1 else None,
        "fattura_ids": invoice_ids,
        "allocazioni_fatture": public_allocations,
        "estratto_conto_id": movement_id,
        "movimento_bancario_id": movement_id,
        "movimento_estratto_conto_id": movement_id,
        "operation_id": operation_id,
        "riconciliato": True,
        "riconciliazione_automatica": automatic,
        "data_riconciliazione": str(movement.get("data") or "")[:10],
        "updated_at": now,
    }
    # Il conto di tesoreria lo dice il movimento: un pagamento dalla carta
    # SumUp esce da 19.01.05, non dal conto BPM che il writer darebbe di
    # ripiego a una riga senza conto.
    if movement.get("conto_contabile"):
        comuni["conto_contabile"] = movement["conto_contabile"]
    descrizione = (
        f"Pagamento {metodo} fattura {', '.join(n for n in numeri_fattura if n)}".strip()
    )
    cursor = db["prima_nota_banca"].find({"$and": [pn_query, dict(FILTRO_MOVIMENTO_ATTIVO)]})
    esistenti = await cursor.to_list(100) if hasattr(cursor, "to_list") else [r async for r in cursor]
    ids: List[str] = []
    for riga in esistenti:
        campi = dict(comuni)
        gia_documentata = bool(riga.get("fattura_id") or riga.get("invoice_id"))
        if not gia_documentata and str(riga.get("categoria") or "") != "Assegni":
            # riga generica dell'import EC / proiezione semantica: diventa la
            # riga del pagamento fattura, come faceva il motore storico.
            campi.update({"categoria": "Fatture", "category": "Fatture",
                          "descrizione": descrizione, "description": descrizione})
        # Conti CEE (PR 7) anche sulle righe storiche completate qui: solo i
        # campi mancanti, mai un conto fuori dal piano ufficiale.
        try:
            campi.update(completa_conti_prima_nota("banca", {**riga, **campi}))
        except ValueError as exc:
            logger.warning("Conti CEE non assegnati alla riga %s: %s", riga.get("id"), exc)
        await db["prima_nota_banca"].update_one({"id": riga.get("id")}, {"$set": campi})
        ids.append(str(riga.get("id")))
    if ids:
        return ids
    pn_id, _ = await scrivi_movimento_se_assente(db, "banca", pn_query, {
        "id": str(uuid4()),
        "data": str(movement.get("data") or "")[:10],
        "tipo": "uscita" if to_cents(movement.get("importo")) < 0 or str(
            movement.get("tipo") or "").lower() == "uscita" else "entrata",
        "importo": abs(to_cents(movement.get("importo"))) / 100,
        "categoria": "Fatture",
        "descrizione": descrizione or (movement.get("descrizione_originale") or movement.get("descrizione")),
        "source": (
            "riconciliazione_automatica_fattura_identita"
            if automatic else "riconciliazione_manual_allocations"
        ),
        "idempotency_key": chiave_idempotenza_pagamento_banca(movement_id),
        "created_at": now,
        **comuni,
    })
    return [str(pn_id)]


def invoice_payable_cents(invoice: Dict[str, Any]) -> int:
    """Debito verso il fornitore, esclusa la ritenuta dovuta all'Erario."""
    return to_cents(totale_pagabile_al_fornitore(invoice))


def _supplier_key(invoice: Dict[str, Any]) -> str:
    vat = str(
        invoice.get("supplier_vat") or invoice.get("fornitore_piva")
        or invoice.get("cedente_piva") or ""
    ).strip().upper()
    name = str(
        invoice.get("supplier_name") or invoice.get("fornitore")
        or invoice.get("fornitore_ragione_sociale")
        or invoice.get("cedente_denominazione") or invoice.get("cedente_nome") or ""
    ).strip().upper()
    return vat or name


def _requested_cents(item: Dict[str, Any], invoice: Dict[str, Any]) -> int:
    if isinstance(item.get("quota_cents"), int):
        return int(item["quota_cents"])
    if item.get("quota") not in (None, ""):
        return to_cents(item["quota"])
    total = invoice_payable_cents(invoice)
    return max(0, total - existing_invoice_allocations_cents(invoice))


async def validate_bank_invoice_allocations(
    db, movement: Dict[str, Any], associations: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Valida l'intero prospetto prima di qualunque scrittura."""
    items = list(associations or [])
    if not items:
        raise HTTPException(status_code=409, detail="Selezionare almeno una fattura")
    ids = [str(item.get("id") or item.get("fattura_id") or "").strip() for item in items]
    if any(not invoice_id for invoice_id in ids) or len(set(ids)) != len(ids):
        raise HTTPException(status_code=409, detail="Fatture mancanti o duplicate nel prospetto")

    # Le fatture del vecchio import hanno l'id numerico (1785229945876): cercate
    # solo come testo non si trovavano, e il bonifico che le paga restava sospeso.
    cercati = ids + [int(invoice_id) for invoice_id in ids if invoice_id.isdigit()]
    invoices = await db["invoices"].find({"id": {"$in": cercati}}).to_list(len(cercati))
    by_id = {str(invoice.get("id")): invoice for invoice in invoices}
    if len(by_id) != len(ids):
        missing = [invoice_id for invoice_id in ids if invoice_id not in by_id]
        raise HTTPException(status_code=404, detail=f"Fatture non trovate: {', '.join(missing)}")

    suppliers = {_supplier_key(by_id[invoice_id]) for invoice_id in ids}
    if "" in suppliers or len(suppliers) != 1:
        raise HTTPException(
            status_code=409,
            detail="Allocazione multipla bloccata: le fatture devono appartenere allo stesso fornitore identificato",
        )

    result: List[Dict[str, Any]] = []
    for item, invoice_id in zip(items, ids):
        invoice = by_id[invoice_id]
        quota_cents = _requested_cents(item, invoice)
        allocation_id = f"bank:{movement.get('id')}:{invoice_id}"
        validation = validate_invoice_allocation(
            invoice, quota_cents, allocation_id=allocation_id,
        )
        if not validation["allowed"]:
            raise HTTPException(
                status_code=409,
                detail=f"Fattura {invoice_id}: {validation['reason']}",
            )
        result.append({
            "allocation_id": allocation_id,
            # L'id com'e' salvato: le scritture che seguono lo cercano per uguaglianza.
            "fattura_id": invoice.get("id"),
            "fattura_numero": invoice.get("invoice_number") or invoice.get("numero_fattura"),
            "fornitore": invoice.get("supplier_name") or invoice.get("fornitore"),
            "quota_cents": quota_cents,
            "totale_fattura_cents": invoice_total_cents(invoice),
            "totale_pagabile_fornitore_cents": invoice_payable_cents(invoice),
            "residuo_precedente_cents": max(
                0, invoice_payable_cents(invoice)
                - existing_invoice_allocations_cents(invoice),
            ),
            "residuo_successivo_cents": max(
                0, invoice_payable_cents(invoice)
                - existing_invoice_allocations_cents(invoice) - quota_cents,
            ),
            "invoice": invoice,
        })

    movement_cents = abs(to_cents(movement.get("importo")))
    allocated_cents = sum(item["quota_cents"] for item in result)
    if movement_cents <= 0 or allocated_cents != movement_cents:
        raise HTTPException(
            status_code=409,
            detail=(
                "Quadratura bloccata: quote fatture "
                f"{allocated_cents} centesimi, movimento {movement_cents} centesimi"
            ),
        )
    return result


async def persist_bank_invoice_allocations(
    db, movement: Dict[str, Any], allocations: List[Dict[str, Any]], *, actor: str,
) -> Dict[str, Any]:
    """Persiste quote e collegamenti reciproci in modo idempotente.

    E' l'UNICO motore "fattura pagata da banca" (audit del commercialista
    03/09/2026 §1, PR 2): in un solo giro, con lo stesso ``operation_id``,
    aggiorna i cinque oggetti che prima divergevano — fattura, scadenza
    (rate del ``scadenziario_fornitori``), partita aperta, movimento di
    estratto conto e riga di Prima Nota Banca — e registra la relazione in
    ``entity_relations`` tramite ``accounting_relation_writers``. Ogni
    scrittura e' idempotente sull'identita' ``bank:<movimento>:<fattura>``.
    """
    movement_id = str(movement.get("id") or "")
    automatic = str(actor).startswith("automatic")
    allocation_rule = (
        "bank.invoice_allocations.identity.v1"
        if automatic else "bank.invoice_allocations.manual.v1"
    )
    now = datetime.now(timezone.utc).isoformat()
    operation_id = str(movement.get("operation_id") or f"bank:{movement_id}")
    movement_date = str(movement.get("data") or "")[:10]
    metodo = _metodo_pagamento(movement)
    public_allocations = []
    for item in allocations:
        public = {key: value for key, value in item.items() if key != "invoice"}
        public.update({
            "movimento_id": movement_id,
            "operation_id": operation_id,
            "metodo_pagamento": metodo,
            "data_pagamento": movement_date,
            "status": "confirmed",
            "rule_id": allocation_rule,
            "confirmed_by": actor,
            "confirmed_at": now,
        })
        public_allocations.append(public)
        existing = await db["bank_payment_allocations"].find_one({"allocation_id": public["allocation_id"]})
        if existing and int(existing.get("quota_cents") or 0) != public["quota_cents"]:
            raise HTTPException(status_code=409, detail="Allocazione esistente con quota differente")
        await db["bank_payment_allocations"].update_one(
            {"allocation_id": public["allocation_id"]},
            {"$setOnInsert": public},
            upsert=True,
        )

    invoice_ids = [item["fattura_id"] for item in allocations]
    numeri_fattura = [str(item.get("fattura_numero") or "") for item in allocations]
    prima_nota_ids = await _proietta_prima_nota_banca(
        db, movement, invoice_ids, public_allocations, now=now,
        operation_id=operation_id, metodo=metodo, automatic=automatic,
        numeri_fattura=numeri_fattura,
    )
    prima_nota_id = prima_nota_ids[0] if len(prima_nota_ids) == 1 else None
    # Le righe che il titolare aveva dichiarato per queste fatture lasciano il
    # posto a quella con la prova: lo stesso pagamento non esce due volte.
    quote_per_fattura: Dict[str, float] = {}
    for item in allocations:
        quote_per_fattura[item["fattura_id"]] = round(
            quote_per_fattura.get(item["fattura_id"], 0.0)
            + int(item.get("quota_cents") or 0) / 100, 2,
        )
    await assorbi_righe_dichiarate(
        db, quote_per_fattura, sostituita_da=prima_nota_ids[0] if prima_nota_ids else "",
        movimento_id=movement_id,
    )

    for item in allocations:
        invoice_id = item["fattura_id"]
        invoice_allocations = await db["bank_payment_allocations"].find(
            {"fattura_id": invoice_id, "status": {"$ne": "reversed"}}, {"_id": 0}
        ).to_list(1000)
        invoice = item["invoice"]
        legacy_without_bank = max(
            0,
            existing_invoice_allocations_cents(invoice)
            - sum(int(link.get("quota_cents") or 0) for link in invoice.get("payment_allocations") or []),
        )
        paid_cents = legacy_without_bank + sum(int(link.get("quota_cents") or 0) for link in invoice_allocations)
        total_cents = invoice_payable_cents(invoice)
        gross_cents = invoice_total_cents(invoice)
        withholding_cents = max(0, gross_cents - total_cents)
        paid = total_cents > 0 and paid_cents >= total_cents
        movement_ids = sorted({
            str(link.get("movimento_id"))
            for link in invoice_allocations
            if link.get("movimento_id")
        })
        # Pagata per intero con la prova bancaria: non e' piu' provvisoria ne'
        # in attesa di riscontro, anche se non c'era una riga dichiarata da
        # assorbire. Lasciata in attesa, restava fra le candidate di un altro
        # movimento dello stesso importo.
        chiusura = {
            "in_attesa_riscontro_banca": False,
            "riscontro_banca_at": now,
            "riscontro_banca_movimento_id": movement_id,
            "stato_finanziario": "riconciliato",
            "provvisorio": False,
            "residuo_da_pagare": 0,
        } if paid else {}
        await db["invoices"].update_one(
            {"id": invoice_id},
            {"$set": {
                **chiusura,
                "payment_allocations": invoice_allocations,
                "importo_pagato": min(paid_cents, total_cents) / 100,
                "importo_residuo": max(0, total_cents - paid_cents) / 100,
                "totale_pagabile_fornitore": total_cents / 100,
                "ritenuta_non_pagabile_fornitore": withholding_cents / 100,
                "pagato": paid,
                "paid": paid,
                "stato_pagamento": "pagata" if paid else "parzialmente_pagata",
                "payment_status": "paid" if paid else "partial",
                "payment_allocation_status": "valid",
                "movimento_bancario_id": movement_ids[0] if len(movement_ids) == 1 else None,
                "movimento_bancario_ids": movement_ids,
                "metodo_pagamento": metodo,
                "data_pagamento": movement_date,
                "in_banca": True,
                "riconciliato_con_ec": movement_id,
                "riconciliato_automaticamente": automatic,
                "payment_operation_id": operation_id,
                "prima_nota_id": prima_nota_id,
                "prima_nota_banca_id": prima_nota_id,
                "prima_nota_tipo": "banca" if prima_nota_id else None,
                "updated_at": now,
            }},
        )
        # Scadenze (rate) e partita aperta: la stessa evidenza non viene
        # applicata due volte (evidenza_id / match_id deterministici).
        try:
            await applica_quota_scadenze(
                db, fattura_id=invoice_id, quota=item["quota_cents"] / 100,
                evidenza_id=evidenza_scadenza_id(movement_id, invoice_id),
                metodo=metodo, data_pagamento=movement_date,
            )
        except Exception:
            logger.exception("Scadenze non aggiornate per la fattura %s", invoice_id)
        try:
            await _aggiorna_partita_aperta(
                db, invoice_id=invoice_id, quota_cents=item["quota_cents"],
                movement_id=movement_id, now=now,
                movement_collection=collezione_del_movimento(movement),
            )
        except Exception:
            logger.exception("Partita aperta non aggiornata per la fattura %s", invoice_id)
        await record_bank_invoice_allocation(
            db, movement=movement, invoice=invoice,
            allocation={**{k: v for k, v in item.items() if k != "invoice"},
                        "operation_id": operation_id},
            prima_nota_id=prima_nota_id, actor=actor,
        )
        if paid:
            await _propaga_fattura_pagata(
                db, invoice_id=invoice_id, metodo=metodo, data_pagamento=movement_date,
                movement_id=movement_id, quota_cents=item["quota_cents"], actor=actor,
            )

    movement_update = {
        "riconciliato": True,
        "abbinato": True,
        "tipo_riconciliazione": (
            "automatico_fattura_identita" if automatic else "manuale_allocazione"
        ),
        "fattura_id": invoice_ids[0] if len(invoice_ids) == 1 else None,
        "fattura_ids": invoice_ids,
        "allocazioni_fatture": public_allocations,
        "operation_id": operation_id,
        "prima_nota_banca_id": prima_nota_id,
        "prima_nota_banca_ids": prima_nota_ids,
        "data_riconciliazione": now,
        "updated_at": now,
    }
    await db[collezione_del_movimento(movement)].update_one(
        {"id": movement_id}, {"$set": movement_update},
    )
    # Il movimento ora e' riconciliato: i suoi «senza match», «ambiguo» e
    # «pagamento multiplo» restavano aperti per sempre.
    from app.services.alert_engine import chiudi_alert_movimento_riconciliato

    await chiudi_alert_movimento_riconciliato(db, movement_id)

    return {
        "success": True,
        "movimento_id": movement_id,
        "operation_id": operation_id,
        "fattura_ids": invoice_ids,
        "prima_nota_ids": prima_nota_ids,
        "allocazioni": public_allocations,
        "quadratura": {
            "movimento_cents": abs(to_cents(movement.get("importo"))),
            "allocato_cents": sum(item["quota_cents"] for item in allocations),
            "stato": "verificata",
        },
    }


def _invoice_refs(movement: Dict[str, Any]) -> List[str]:
    text = " ".join(str(movement.get(field) or "") for field in (
        "descrizione_originale", "descrizione", "causale", "numero_fattura",
    ))
    match = re.search(r"saldo\s+fattur[ea]s?\s+([\d\s,;/-]+)", text, re.IGNORECASE)
    source = match.group(1) if match else str(movement.get("numero_fattura") or "")
    refs = re.findall(r"\d{5,12}", source)
    return list(dict.fromkeys(refs))


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _supplier_tokens(invoice: Dict[str, Any]) -> List[str]:
    ignored = {
        "srl", "spa", "sas", "snc", "societa", "ditta", "group", "italia",
        "di", "del", "della", "dei", "degli", "e",
    }
    name = str(
        invoice.get("supplier_name") or invoice.get("fornitore")
        or invoice.get("fornitore_ragione_sociale")
        or invoice.get("cedente_denominazione") or invoice.get("cedente_nome") or ""
    )
    return [
        token for token in re.findall(r"[a-z0-9]+", name.lower())
        if len(token) >= 4 and token not in ignored
    ]


def _movement_text(movement: Dict[str, Any]) -> str:
    return " ".join(str(movement.get(field) or "") for field in (
        "descrizione_originale", "descrizione", "causale", "beneficiario",
        "controparte", "iban_beneficiario", "iban_controparte",
    ))


def _is_outgoing_invoice_candidate(movement: Dict[str, Any]) -> bool:
    movement_type = str(movement.get("tipo") or "").strip().lower()
    if movement_type in {"entrata", "accredito", "incasso"}:
        return False
    amount = to_cents(movement.get("importo"))
    if amount >= 0 and movement_type not in {"uscita", "addebito", "pagamento"}:
        return False
    classification = classify_bank_movement(movement)
    if classification and classification.get("tipo") not in {"fattura_sdd"}:
        return False
    return amount != 0


def _identity_evidence(
    movement: Dict[str, Any], invoice: Dict[str, Any],
) -> Dict[str, Any] | None:
    """Valuta identita' documentale oltre alla quadratura dell'importo."""
    movement_cents = abs(to_cents(movement.get("importo")))
    residual_cents = max(
        0, invoice_payable_cents(invoice) - existing_invoice_allocations_cents(invoice),
    )
    if movement_cents <= 0 or movement_cents != residual_cents:
        return None
    invoice_type = str(invoice.get("document_type") or invoice.get("tipo_documento") or "").upper()
    if invoice_type in {"TD04", "TD08"}:
        return None
    invoice_date = str(invoice.get("invoice_date") or invoice.get("data_fattura") or "")[:10]
    movement_date = str(movement.get("data") or "")[:10]
    try:
        start = datetime.strptime(invoice_date, "%Y-%m-%d")
        paid_at = datetime.strptime(movement_date, "%Y-%m-%d")
        if paid_at < start or paid_at > start + timedelta(days=370):
            return None
    except ValueError:
        return None

    text = _compact(_movement_text(movement))
    number = _compact(
        invoice.get("invoice_number") or invoice.get("numero_documento")
        or invoice.get("numero_fattura")
    )
    number_match = len(number) >= 5 and number in text
    vat = _compact(
        invoice.get("supplier_vat") or invoice.get("fornitore_piva")
        or invoice.get("fornitore_partita_iva") or invoice.get("cedente_piva")
    )
    vat_match = len(vat) >= 8 and vat in text
    iban = _compact(
        invoice.get("supplier_iban") or invoice.get("fornitore_iban")
        or invoice.get("iban")
    )
    movement_iban = _compact(
        movement.get("iban_beneficiario") or movement.get("iban_controparte")
        or movement.get("iban")
    )
    iban_match = len(iban) >= 15 and (iban == movement_iban or iban in text)
    tokens = _supplier_tokens(invoice)
    matched_tokens = [token for token in tokens if token in text]
    supplier_match = bool(matched_tokens) and (
        len(tokens) == 1 or len(matched_tokens) >= min(2, len(tokens))
    )
    if not any((number_match, vat_match, iban_match, supplier_match)):
        return None
    if number_match:
        priority, rule = 3, "numero_fattura+importo"
    elif iban_match or vat_match:
        priority, rule = 2, "iban_o_piva+importo"
    else:
        priority, rule = 1, "fornitore+importo"
    evidence = {
        "priority": priority,
        "rule": rule,
        "quota_cents": residual_cents,
        "proposta": False,
    }
    if priority == 1:
        # Audit 03/09/2026 (PR 4): con la sola identita' "token del fornitore"
        # il soggetto pagante scritto in causale deve essere lo stesso
        # fornitore della fattura. "AMAZON PAYMENTS EUROPE S.C.A." non paga
        # in automatico una fattura di "Amazon Business EU S.a.r.l": resta
        # una proposta da confermare in "Scegli fattura".
        movement_text = _movement_text(movement)
        supplier_name = str(
            invoice.get("supplier_name") or invoice.get("fornitore")
            or invoice.get("fornitore_ragione_sociale")
            or invoice.get("cedente_denominazione") or invoice.get("cedente_nome") or ""
        )
        coerente = soggetto_pagante_coerente(
            supplier_name, movement_text, alias=alias_fornitore(invoice),
        )
        evidence["soggetto_causale"] = soggetto_causale_bancaria(movement_text)
        evidence["soggetto_coerente"] = coerente
        if coerente is False:
            evidence.update({
                "priority": 0,
                "rule": "fornitore+importo:soggetto_pagante_diverso",
                "proposta": True,
            })
    return evidence


async def _proponi_scelta_fattura(
    db, movement: Dict[str, Any], invoices: List[Dict[str, Any]], soggetto: Any,
) -> bool:
    """Coda "Scegli fattura" per gli abbinamenti con soggetto pagante diverso.

    Riusa l'unico scrittore di ``operazioni_da_confermare`` del motore
    storico (idempotente per movimento, alert solo alla creazione).
    """
    from app.services.riconciliazione_bancaria import proponi_scelta_fattura

    fornitori = ", ".join(dict.fromkeys(
        str(
            invoice.get("supplier_name") or invoice.get("fornitore")
            or invoice.get("cedente_denominazione") or ""
        )
        for invoice in invoices
    ))
    motivo = (
        f"Importo al centesimo ma soggetto pagante diverso: la causale dichiara "
        f"'{soggetto or '?'}', la fattura e' di '{fornitori}'. Conferma manuale necessaria."
    )
    return await proponi_scelta_fattura(
        db, movement, invoices, motivo=motivo, match_type="soggetto_pagante_diverso",
    )


async def _reconcile_unique_identity_matches(
    db, movements: List[Dict[str, Any]], *, excluded_movement_ids=None,
    proponi: bool = True,
) -> Dict[str, Any]:
    """Abbina solo archi univoci movimento-fattura con identita' forte.

    ``proponi=False`` non scrive la coda «Scegli fattura», che sa aprire
    solo movimenti del conto BPM: le proposte tornano nell'esito.
    """
    excluded = {str(value) for value in (excluded_movement_ids or [])}
    eligible_movements = [
        movement for movement in movements
        if str(movement.get("id")) not in excluded and _is_outgoing_invoice_candidate(movement)
    ]
    invoices = await db["invoices"].find({"$or": [
        {**FILTRO_NON_PAGATE, "stato_pagamento": {"$ne": "pagata"}},
        {"in_attesa_riscontro_banca": True},
    ]}, {"_id": 0}).to_list(50000)
    invoices_by_residual: Dict[int, List[Dict[str, Any]]] = {}
    for invoice in invoices:
        residual = max(
            0, invoice_payable_cents(invoice) - existing_invoice_allocations_cents(invoice),
        )
        if residual:
            invoices_by_residual.setdefault(residual, []).append(invoice)

    choices = []
    ambiguous_movements = 0
    proposed_movements = 0
    proposte: List[Dict[str, Any]] = []
    for movement in eligible_movements:
        edges = []
        proposals = []
        movement_cents = abs(to_cents(movement.get("importo")))
        for invoice in invoices_by_residual.get(movement_cents, []):
            evidence = _identity_evidence(movement, invoice)
            if not evidence:
                continue
            edge = {"movement": movement, "invoice": invoice, **evidence}
            (proposals if evidence.get("proposta") else edges).append(edge)
        if not edges:
            if proposals:
                # Nessuna prova forte: il candidato con soggetto pagante
                # diverso va scelto da un operatore, mai applicato.
                if proponi:
                    await _proponi_scelta_fattura(
                        db, movement, [edge["invoice"] for edge in proposals],
                        proposals[0].get("soggetto_causale"),
                    )
                proposte.append({
                    "movimento_id": movement.get("id"),
                    "fatture_candidate": [
                        edge["invoice"].get("id") for edge in proposals
                    ],
                })
                proposed_movements += 1
            continue
        best_priority = max(edge["priority"] for edge in edges)
        best = [edge for edge in edges if edge["priority"] == best_priority]
        if len(best) != 1:
            ambiguous_movements += 1
            continue
        choices.append(best[0])

    # Seconda unicita': la stessa fattura non puo' essere candidata migliore
    # per due bonifici distinti. In quel caso nessuno dei due viene applicato.
    best_by_invoice: Dict[str, List[Dict[str, Any]]] = {}
    for edge in choices:
        best_by_invoice.setdefault(str(edge["invoice"].get("id")), []).append(edge)

    linked = []
    ambiguous_invoices = 0
    for invoice_id, edges in best_by_invoice.items():
        top_priority = max(edge["priority"] for edge in edges)
        top = [edge for edge in edges if edge["priority"] == top_priority]
        if len(top) != 1:
            ambiguous_invoices += 1
            continue
        edge = top[0]
        try:
            allocations = await validate_bank_invoice_allocations(
                db, edge["movement"], [{
                    "id": invoice_id,
                    "quota_cents": edge["quota_cents"],
                }],
            )
            await persist_bank_invoice_allocations(
                db, edge["movement"], allocations,
                actor=f"automatic_identity:{edge['rule']}",
            )
            linked.append({
                "movimento_id": edge["movement"].get("id"),
                "fattura_id": invoice_id,
                "regola": edge["rule"],
            })
        except HTTPException:
            ambiguous_invoices += 1
    return {
        "collegati": linked,
        "collegati_count": len(linked),
        "ambigui_movimento": ambiguous_movements,
        "ambigui_fattura": ambiguous_invoices,
        "proposte_soggetto_diverso": proposed_movements,
        "proposte": proposte,
    }


_PAROLA_FATTURA = re.compile(r"\b(?:fattur[ae]|fatt|ft|fvl?)\b", re.IGNORECASE)
_GIORNI_GRUPPO_CITAZIONI = 30


def _numeri_citati(movement: Dict[str, Any]) -> set:
    """Parole della causale che possono essere numeri di fattura.

    Solo se la causale parla di fatture («Pagamento Fatture 386, 738»,
    «Saldo fatture fvl824 fvl968», «FT. 8528015144»): un numero qualsiasi
    in una causale non e' un riferimento.
    """
    testo = _movement_text(movement)
    if not _PAROLA_FATTURA.search(testo):
        return set()
    return {
        parola.lower() for parola in re.findall(r"[A-Za-z]*\d[A-Za-z0-9]*", testo)
        if len(parola) >= 3
    }


def _numero_citato(invoice: Dict[str, Any], citati: set) -> bool:
    numero = str(
        invoice.get("invoice_number") or invoice.get("numero_documento")
        or invoice.get("numero_fattura") or ""
    ).strip().lower()
    if not numero:
        return False
    # «1/11358» si cita «11358»: conta l'ultimo pezzo, non le cifre sciolte.
    return _compact(numero) in citati or numero.split("/")[-1] in citati


def _fornitore_del_movimento(movement: Dict[str, Any], invoice: Dict[str, Any]) -> bool:
    """Il beneficiario del bonifico e' il fornitore della fattura (IBAN,
    P.IVA o nome): senza, un numero uguale di un altro fornitore passerebbe."""
    text = _compact(_movement_text(movement))
    iban = _compact(invoice.get("supplier_iban") or invoice.get("fornitore_iban") or invoice.get("iban"))
    movement_iban = _compact(movement.get("iban_beneficiario") or movement.get("iban_controparte"))
    if len(iban) >= 15 and (iban == movement_iban or iban in text):
        return True
    vat = _compact(invoice.get("supplier_vat") or invoice.get("fornitore_piva") or invoice.get("cedente_piva"))
    if len(vat) >= 8 and vat in text:
        return True
    tokens = _supplier_tokens(invoice)
    matched = [token for token in tokens if token in text]
    if matched and (len(tokens) == 1 or len(matched) >= min(2, len(tokens))):
        return True
    # «2M ITALIA S.R.L.» non ha parole utili: vale il nome intero, senza la
    # forma societaria, dentro il beneficiario («2MITALIA S.R.L.»).
    nome = re.sub(
        r"\b(s\.?\s?r\.?\s?l|s\.?\s?p\.?\s?a|s\.?\s?a\.?\s?s|s\.?\s?n\.?\s?c)\.?\b", " ",
        str(invoice.get("supplier_name") or invoice.get("fornitore") or ""), flags=re.IGNORECASE,
    )
    nome = _compact(nome)
    return len(nome) >= 6 and nome in text


def _residuo_cents(invoice: Dict[str, Any]) -> int:
    return max(0, invoice_payable_cents(invoice) - existing_invoice_allocations_cents(invoice))


def _ripartisci_in_ordine(
    movimenti: List[Dict[str, Any]], fatture: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]] | None:
    """Quote per movimento, pagando le fatture dalla piu' vecchia.

    Ogni bonifico paga le fatture in ordine di data finche' non esaurisce il
    suo importo; l'ultima puo' restare pagata in parte e la chiude il bonifico
    dopo. Una fattura emessa dopo il bonifico che dovrebbe pagarla fa saltare
    tutto: il conto non torna per caso.
    """
    residui = [[fattura, _residuo_cents(fattura)] for fattura in fatture]
    quote: Dict[str, List[Dict[str, Any]]] = {}
    indice = 0
    for movimento in movimenti:
        da_coprire = abs(to_cents(movimento.get("importo")))
        righe: List[Dict[str, Any]] = []
        while da_coprire > 0 and indice < len(residui):
            fattura, residuo = residui[indice]
            data_fattura = str(fattura.get("invoice_date") or "")[:10]
            if data_fattura > str(movimento.get("data") or "")[:10]:
                return None
            quota = min(residuo, da_coprire)
            righe.append({"id": fattura["id"], "quota_cents": quota})
            da_coprire -= quota
            residui[indice][1] -= quota
            if residui[indice][1] == 0:
                indice += 1
        if da_coprire:
            return None
        quote[str(movimento.get("id"))] = righe
    if indice != len(residui):
        return None
    return quote


def _raggruppa_bonifici(
    movimenti: List[Dict[str, Any]], citazioni: Dict[str, List[Dict[str, Any]]],
) -> List[List[Dict[str, Any]]]:
    """Un bonifico che quadra da solo fa gruppo a se'. Gli altri dello stesso
    fornitore si sommano in ordine di data, entro 30 giorni dal primo, finche'
    la somma dei bonifici non fa quella delle fatture citate da tutti."""
    def importo(m):
        return abs(to_cents(m.get("importo")))

    def giorno(m):
        return datetime.strptime(str(m.get("data") or "")[:10], "%Y-%m-%d")

    gruppi: List[List[Dict[str, Any]]] = []
    corrente: List[Dict[str, Any]] = []
    for movimento in movimenti:
        citate = citazioni[str(movimento.get("id"))]
        if sum(_residuo_cents(f) for f in citate) == importo(movimento):
            gruppi.append([movimento])
            continue
        if corrente and (giorno(movimento) - giorno(corrente[0])).days > _GIORNI_GRUPPO_CITAZIONI:
            gruppi.append(corrente)
            corrente = []
        corrente.append(movimento)
        unione = {str(f["id"]): f for m in corrente for f in citazioni[str(m.get("id"))]}
        if sum(importo(m) for m in corrente) == sum(_residuo_cents(f) for f in unione.values()):
            gruppi.append(corrente)
            corrente = []
    if corrente:
        gruppi.append(corrente)
    return gruppi


async def reconcile_cited_invoices(db, movements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Bonifici che citano in causale le fatture che pagano.

    Il bonifico paga le fatture che nomina, dello stesso fornitore, se la
    somma dei residui fa l'importo al centesimo. Quando un fornitore riceve
    piu' bonifici che si citano a vicenda («Si aggancia a bonifico del
    06/08») vale lo stesso per il gruppo: somma dei bonifici uguale alla
    somma delle fatture citate, ripartita in ordine di data. Un numero che
    corrisponde a due fatture, o un totale che non torna, non collega niente.
    """
    candidati = [m for m in movements if _is_outgoing_invoice_candidate(m) and not m.get("riconciliato")]
    citati_per_mov = {str(m.get("id")): _numeri_citati(m) for m in candidati}
    candidati = [m for m in candidati if citati_per_mov[str(m.get("id"))]]
    if not candidati:
        return {"collegati": [], "collegati_count": 0, "sospesi": 0}
    fatture = await db["invoices"].find(FILTRO_DA_RISCONTRARE, {"_id": 0}).to_list(50000)
    fatture = [
        f for f in fatture
        if str(f.get("status") or "").lower() not in {"deleted", "archived", "archiviata"}
        and str(f.get("tipo_documento") or f.get("document_type") or "").upper() not in {"TD04", "TD08"}
        and _residuo_cents(f) > 0
    ]

    # Per ogni bonifico: le fatture del suo fornitore che la causale nomina.
    citazioni: Dict[str, List[Dict[str, Any]]] = {}
    sospesi = 0
    for movimento in candidati:
        citati = citati_per_mov[str(movimento.get("id"))]
        trovate = [
            f for f in fatture
            if _numero_citato(f, citati) and _fornitore_del_movimento(movimento, f)
        ]
        per_numero: Dict[str, List[Dict[str, Any]]] = {}
        for fattura in trovate:
            per_numero.setdefault(_compact(fattura.get("invoice_number")), []).append(fattura)
        if not trovate or any(len(v) > 1 for v in per_numero.values()) \
                or len({_supplier_key(f) for f in trovate}) != 1:
            sospesi += bool(trovate)
            continue
        citazioni[str(movimento.get("id"))] = trovate

    per_fornitore: Dict[str, List[Dict[str, Any]]] = {}
    for movimento in candidati:
        trovate = citazioni.get(str(movimento.get("id")))
        if trovate:
            per_fornitore.setdefault(_supplier_key(trovate[0]), []).append(movimento)

    collegati = []
    for movimenti in per_fornitore.values():
        movimenti.sort(key=lambda m: (str(m.get("data") or ""), str(m.get("id"))))
        gruppi = _raggruppa_bonifici(movimenti, citazioni)
        for gruppo in gruppi:
            fatture_gruppo: Dict[str, Dict[str, Any]] = {}
            for movimento in gruppo:
                for fattura in citazioni[str(movimento.get("id"))]:
                    fatture_gruppo[str(fattura["id"])] = fattura
            ordinate = sorted(
                fatture_gruppo.values(),
                key=lambda f: (str(f.get("invoice_date") or ""), _compact(f.get("invoice_number"))),
            )
            quote = _ripartisci_in_ordine(gruppo, ordinate)
            if quote is None:
                sospesi += len(gruppo)
                continue
            try:
                prospetti = [
                    (m, await validate_bank_invoice_allocations(db, m, quote[str(m.get("id"))]))
                    for m in gruppo
                ]
            except HTTPException as exc:
                logger.info("Fatture citate non collegate (%s): %s", type(exc).__name__, exc.detail)
                sospesi += len(gruppo)
                continue
            for movimento, allocations in prospetti:
                await persist_bank_invoice_allocations(
                    db, movimento, allocations, actor="automatic_identity:fatture_citate",
                )
                collegati.append({
                    "movimento_id": movimento.get("id"),
                    "fatture": [a["fattura_id"] for a in allocations],
                    "regola": "fatture_citate_in_causale",
                })
    return {"collegati": collegati, "collegati_count": len(collegati), "sospesi": sospesi}


# Acconti (titolare, 28/09/2026): una fattura pagata in piu' bonifici allo
# stesso fornitore, nessuno dei quali quadra da solo. FEP 7_26 di A 2000
# Costruzioni (24.400,00) = 15.000,00 del 12/02 + 9.400,00 del 26/02.
_GIORNI_ACCONTI = 90
_MAX_BONIFICI_ACCONTO = 4
_MAX_CANDIDATI_ACCONTO = 12


def _combinazioni_che_quadrano(
    movimenti: List[Dict[str, Any]], obiettivo: int,
) -> List[List[Dict[str, Any]]]:
    """Gruppi di 2..4 bonifici la cui somma fa ``obiettivo`` al centesimo."""
    from itertools import combinations

    trovate = []
    for n in range(2, min(_MAX_BONIFICI_ACCONTO, len(movimenti)) + 1):
        for gruppo in combinations(movimenti, n):
            if sum(abs(to_cents(m.get("importo"))) for m in gruppo) == obiettivo:
                trovate.append(list(gruppo))
    return trovate


async def reconcile_acconti_fornitore(
    db, movements: List[Dict[str, Any]], *, excluded_movement_ids=None,
    proponi: bool = True,
) -> Dict[str, Any]:
    """Piu' bonifici allo stesso fornitore che sommano al centesimo una sola
    fattura aperta la pagano. Il beneficiario deve essere il fornitore della
    fattura (IBAN, P.IVA o nome, ``_fornitore_del_movimento``), i bonifici
    vengono dopo la fattura ed entro 90 giorni. Mai per solo importo: una
    combinazione che vale per due fatture, o due combinazioni per la stessa
    fattura, non collega niente e va in «Scegli fattura»."""
    excluded = {str(value) for value in (excluded_movement_ids or [])}
    candidati = [
        m for m in movements
        if str(m.get("id")) not in excluded and not m.get("riconciliato")
        and not (m.get("fattura_id") or m.get("fattura_ids"))
        and _is_outgoing_invoice_candidate(m)
    ]
    esito: Dict[str, Any] = {"collegati": [], "collegati_count": 0, "ambigui": 0, "proposte": 0}
    if len(candidati) < 2:
        return esito
    fatture = await db["invoices"].find({"$or": [
        {**FILTRO_NON_PAGATE, "stato_pagamento": {"$ne": "pagata"}},
        {"in_attesa_riscontro_banca": True},
    ]}, {"_id": 0}).to_list(50000)
    fatture = [
        f for f in fatture
        if str(f.get("status") or "").lower() not in {"deleted", "archived", "archiviata"}
        and str(f.get("tipo_documento") or f.get("document_type") or "").upper() not in {"TD04", "TD08"}
        and _residuo_cents(f) > 0 and _supplier_key(f)
    ]

    soluzioni = []
    for fattura in fatture:
        data_fattura = str(fattura.get("invoice_date") or "")[:10]
        try:
            inizio = datetime.strptime(data_fattura, "%Y-%m-%d")
        except ValueError:
            continue
        fine = (inizio + timedelta(days=_GIORNI_ACCONTI)).strftime("%Y-%m-%d")
        residuo = _residuo_cents(fattura)
        suoi = sorted(
            (
                m for m in candidati
                if data_fattura <= str(m.get("data") or "")[:10] <= fine
                and 0 < abs(to_cents(m.get("importo"))) < residuo
                and _fornitore_del_movimento(m, fattura)
            ),
            key=lambda m: (str(m.get("data") or ""), str(m.get("id"))),
        )
        if len(suoi) < 2 or len(suoi) > _MAX_CANDIDATI_ACCONTO:
            continue
        combinazioni = _combinazioni_che_quadrano(suoi, residuo)
        if combinazioni:
            soluzioni.append((fattura, combinazioni))

    # Univoca da tutti e due i lati: una sola combinazione per la fattura, e
    # nessun bonifico conteso da un'altra fattura.
    contesi: Dict[str, int] = {}
    for _fattura, combinazioni in soluzioni:
        for gruppo in combinazioni:
            for m in gruppo:
                contesi[str(m.get("id"))] = contesi.get(str(m.get("id")), 0) + 1
    for fattura, combinazioni in soluzioni:
        gruppo = combinazioni[0]
        univoca = len(combinazioni) == 1 and all(contesi[str(m.get("id"))] == 1 for m in gruppo)
        if not univoca:
            esito["ambigui"] += 1
            if proponi:
                from app.services.riconciliazione_bancaria import proponi_scelta_fattura

                for m in {str(m.get("id")): m for g in combinazioni for m in g}.values():
                    creata = await proponi_scelta_fattura(
                        db, m, [fattura],
                        motivo=(
                            "Acconto: piu' combinazioni di bonifici allo stesso fornitore "
                            f"fanno il totale della fattura {fattura.get('invoice_number')}. "
                            "Scegli quali la pagano."
                        ),
                        match_type="acconti_ambigui",
                    )
                    esito["proposte"] += bool(creata)
            continue
        try:
            prospetti = [
                (m, await validate_bank_invoice_allocations(db, m, [{
                    "id": fattura["id"], "quota_cents": abs(to_cents(m.get("importo"))),
                }]))
                for m in gruppo
            ]
        except HTTPException as exc:
            logger.info("Acconti non collegati (%s): %s", type(exc).__name__, exc.detail)
            esito["ambigui"] += 1
            continue
        for movimento, allocations in prospetti:
            await persist_bank_invoice_allocations(
                db, movimento, allocations, actor="automatic_identity:acconti_fornitore",
            )
            esito["collegati"].append({
                "movimento_id": movimento.get("id"),
                "fattura_id": fattura.get("id"),
                "regola": "acconti_stesso_fornitore",
            })
    esito["collegati_count"] = len(esito["collegati"])
    return esito


async def riconcilia_acconti_in_sospeso(db) -> Dict[str, Any]:
    """Acconti per il job bancario corto.

    In coda a ``reconcile_deterministic_invoice_allocations`` stanno nel giro
    «Automazioni», che dura ore e riparte a ogni deploy: il 28/09/2026 FEP 7_26
    aspettava i suoi due bonifici da un giorno. Qui girano da soli, sugli
    stessi movimenti non riconciliati."""
    movements = await db["estratto_conto_movimenti"].find(
        {"riconciliato": {"$ne": True}}, {"_id": 0},
    ).to_list(5000)
    return await reconcile_acconti_fornitore(db, movements)


async def reconcile_deterministic_invoice_allocations(
    db, *, movement_ids=None, anno=None,
) -> Dict[str, Any]:
    """Collega automaticamente solo distinte con riferimenti univoci e quadrati."""
    query: Dict[str, Any] = {"riconciliato": {"$ne": True}}
    if movement_ids:
        query["id"] = {"$in": [str(value) for value in movement_ids if value]}
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    movements = await db["estratto_conto_movimenti"].find(query, {"_id": 0}).to_list(5000)
    stats = {"esaminati": len(movements), "allocati": 0, "sospesi": 0, "errori": []}
    allocated_movement_ids = set()
    for movement in movements:
        classification = classify_bank_movement(movement)
        refs = _invoice_refs(movement)
        if not classification or classification["tipo"] != "fattura_sdd" or not refs:
            continue
        associations = []
        ambiguous = False
        for ref in refs:
            candidates = await db["invoices"].find({
                "$and": [
                    {"$or": [{"invoice_number": ref}, {"numero_fattura": ref}]},
                    FILTRO_DA_RISCONTRARE,
                ],
            }, {"_id": 0}).to_list(2)
            if len(candidates) != 1:
                ambiguous = True
                break
            invoice = candidates[0]
            if str(invoice.get("invoice_date") or "")[:10] > str(movement.get("data") or "")[:10]:
                ambiguous = True
                break
            residual = max(
            0, invoice_payable_cents(invoice) - existing_invoice_allocations_cents(invoice),
            )
            associations.append({"id": invoice["id"], "quota_cents": residual})
        if ambiguous or len(associations) != len(refs):
            stats["sospesi"] += 1
            continue
        try:
            allocations = await validate_bank_invoice_allocations(db, movement, associations)
            await persist_bank_invoice_allocations(
                db, movement, allocations, actor="automatic_import",
            )
            stats["allocati"] += 1
            allocated_movement_ids.add(str(movement.get("id")))
        except HTTPException as exc:
            stats["sospesi"] += 1
            stats["errori"].append({"movimento_id": movement.get("id"), "motivo": exc.detail})
    identity = await _reconcile_unique_identity_matches(
        db, movements, excluded_movement_ids=allocated_movement_ids,
    )
    stats["allocati_identita"] = identity["collegati_count"]
    stats["abbinamenti_identita"] = identity["collegati"]
    stats["ambigui_identita"] = (
        identity["ambigui_movimento"] + identity["ambigui_fattura"]
    )
    stats["proposte_soggetto_diverso"] = identity["proposte_soggetto_diverso"]
    gia_collegati = allocated_movement_ids | {
        str(voce["movimento_id"]) for voce in identity["collegati"]
    }
    acconti = await reconcile_acconti_fornitore(
        db, movements, excluded_movement_ids=gia_collegati,
    )
    stats["allocati_acconti"] = acconti["collegati_count"]
    stats["abbinamenti_acconti"] = acconti["collegati"]
    stats["ambigui_acconti"] = acconti["ambigui"]
    return stats
