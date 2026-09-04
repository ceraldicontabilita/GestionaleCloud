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
from app.services.prima_nota_integrity import totale_pagabile_al_fornitore

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


def _metodo_pagamento(movement: Dict[str, Any]) -> str:
    from app.services.riconciliazione_bancaria import classifica_strumento_bancario

    strumento = classifica_strumento_bancario(
        str(movement.get("descrizione_originale") or movement.get("descrizione") or "")
    )
    if strumento["codice"] in {"riba", "bonifico", "addebito_diretto", "assegno", "paypal"}:
        return strumento["label"]
    return "Bonifico"


async def _aggiorna_partita_aperta(
    db, *, invoice_id: str, quota_cents: int, movement_id: str, now: str,
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
            "movimento_collection": "estratto_conto_movimenti",
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

    invoices = await db["invoices"].find({"id": {"$in": ids}}).to_list(len(ids))
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
            "fattura_id": invoice_id,
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
        await db["invoices"].update_one(
            {"id": invoice_id},
            {"$set": {
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
    await db["estratto_conto_movimenti"].update_one({"id": movement_id}, {"$set": movement_update})

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
) -> Dict[str, Any]:
    """Abbina solo archi univoci movimento-fattura con identita' forte."""
    excluded = {str(value) for value in (excluded_movement_ids or [])}
    eligible_movements = [
        movement for movement in movements
        if str(movement.get("id")) not in excluded and _is_outgoing_invoice_candidate(movement)
    ]
    invoices = await db["invoices"].find({
        "pagato": {"$ne": True},
        "stato_pagamento": {"$ne": "pagata"},
    }, {"_id": 0}).to_list(50000)
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
                await _proponi_scelta_fattura(
                    db, movement, [edge["invoice"] for edge in proposals],
                    proposals[0].get("soggetto_causale"),
                )
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
    }


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
                "$or": [
                    {"invoice_number": ref},
                    {"numero_fattura": ref},
                ],
                "pagato": {"$ne": True},
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
    return stats
