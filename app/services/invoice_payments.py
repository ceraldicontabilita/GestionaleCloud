"""Servizio atomico per i pagamenti manuali delle fatture passive."""
from datetime import datetime, timedelta, timezone
import hashlib
import math
import uuid
from typing import Any, Dict, Literal, Optional
import re

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.services.archivio_documenti_memoria import DuplicateRecordError

from app.services.scritture_contabili import _sessione, _transazione_registro, scrivi_movimento
from app.services.prima_nota_integrity import totale_pagabile_al_fornitore
from app.services.stato_pagamento_fattura import e_annullata, e_pagata
from app.constants.fattura_attiva import fattura_attiva
from app.utils.id_fattura import filtro_id, varianti_id


COL_SCADENZIARIO = "scadenziario_fornitori"
COL_FATTURE_RICEVUTE = "invoices"


class ManualInvoicePaymentRequest(BaseModel):
    # L'`id` di una fattura e' un numero su meta' delle righe e la pagina lo rimanda cosi' com'e'.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, coerce_numbers_to_str=True)

    fattura_id: str = Field(min_length=1, max_length=160)
    scadenza_id: Optional[str] = Field(default=None, max_length=160)
    importo: float
    metodo: Literal["cassa", "banca"] = "banca"
    data_pagamento: Optional[str] = Field(default=None, max_length=10)
    fornitore: str = Field(default="Fornitore", max_length=300)
    numero_fattura: str = Field(default="", max_length=160)
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=200)

    @field_validator("importo")
    @classmethod
    def importo_finito_non_zero(cls, value: float) -> float:
        if not math.isfinite(value) or value == 0:
            raise ValueError("importo deve essere finito e diverso da zero")
        return value

    @field_validator("data_pagamento")
    @classmethod
    def data_iso(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("data_pagamento deve essere YYYY-MM-DD") from exc
        return value


class ManualInvoicePaymentResponse(BaseModel):
    success: bool
    movimento_id: str
    metodo: Literal["cassa", "banca"]
    importo: float
    riconciliato: bool
    collection: Optional[str] = None
    message: Optional[str] = None
    idempotent_replay: bool = False
    stato: Optional[str] = None
    pagamento_confermato: Optional[bool] = None
    in_attesa_estratto_ufficiale: bool = False


class InvoiceBankReconciliationRequest(BaseModel):
    # Come sopra: `fattura_id` puo' arrivare come numero.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, coerce_numbers_to_str=True)

    fattura_id: str = Field(min_length=1, max_length=160)
    movimento_id: str = Field(min_length=1, max_length=200)
    override_reason: Optional[str] = Field(default=None, min_length=12, max_length=500)


class InvoiceBankReconciliationResponse(BaseModel):
    success: bool
    fattura_id: str
    movimento_id: str
    message: str
    idempotent_replay: bool = False


def _operation_key(req: ManualInvoicePaymentRequest) -> str:
    raw = req.idempotency_key or "|".join([
        req.fattura_id,
        req.scadenza_id or "fattura-intera",
        req.metodo,
        f"{req.importo:.2f}",
        req.data_pagamento or "senza-data",
    ])
    return "manual-payment:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def register_manual_invoice_payment(db, req: ManualInvoicePaymentRequest) -> Dict[str, Any]:
    """Registra il contante oppure l'attesa di un riscontro bancario.

    La collection ``pagamenti_operazioni`` usa ``_id`` come chiave di
    idempotenza: retry HTTP e doppio click non incrementano due volte il
    pagato. La banca manuale e' una dichiarazione: il pagamento effettivo
    passa soltanto dal motore canonico delle allocazioni dell'estratto conto.
    """
    invoice = (
        await db["invoices"].find_one(filtro_id(req.fattura_id), {"_id": 0})
        or await db[COL_FATTURE_RICEVUTE].find_one(filtro_id(req.fattura_id), {"_id": 0})
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    rates = invoice.get("pagamento_rate") or []
    if len(rates) > 1 and not req.scadenza_id:
        raise HTTPException(
            status_code=409,
            detail="Fattura rateizzata: seleziona una singola scadenza",
        )
    if not req.data_pagamento:
        raise HTTPException(status_code=422, detail="data_pagamento obbligatoria")

    operation_id = _operation_key(req)
    now = datetime.now(timezone.utc).isoformat()
    collection_name = "prima_nota_cassa" if req.metodo == "cassa" else "prima_nota_banca"
    result: Dict[str, Any]

    try:
        async with _transazione_registro(db) as session:
            skw = _sessione(session)
            # Rilegge la fattura dentro la transazione: la decisione sul
            # residuo deve usare lo stesso snapshot delle scritture che
            # seguono, non il documento letto prima di aprire la sessione.
            current_invoice = await db[COL_FATTURE_RICEVUTE].find_one(
                filtro_id(req.fattura_id), {"_id": 0}, **skw,
            )
            if not current_invoice:
                raise HTTPException(status_code=404, detail="Fattura non trovata")
            invoice = current_invoice

            previous = await db["pagamenti_operazioni"].find_one(
                {"_id": operation_id}, {"_id": 0, "result": 1}, **skw,
            )
            if previous and previous.get("result"):
                replay = dict(previous["result"])
                replay["idempotent_replay"] = True
                return replay

            if req.metodo == "banca" and (
                not fattura_attiva(invoice) or e_annullata(invoice) or e_pagata(invoice)
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Fattura gia' pagata, annullata o archiviata: non creare un'altra attesa bancaria",
                )

            total = abs(float(
                invoice.get("total_amount")
                or invoice.get("importo_totale")
                or req.importo
            ))
            if req.metodo == "banca":
                total = totale_pagabile_al_fornitore(invoice)
            current_paid = abs(float(invoice.get("importo_pagato") or 0))
            remaining = max(0.0, round(total - current_paid, 2))
            if req.importo > 0 and req.importo - remaining > 0.005:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"L'importo supera il residuo della fattura: "
                        f"residuo {remaining:.2f}"
                    ),
                )
            if (
                req.importo > 0
                and remaining - req.importo > 0.005
                and not req.scadenza_id
                and not req.idempotency_key
            ):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Pagamento parziale ambiguo: specifica scadenza_id "
                        "oppure una idempotency_key stabile"
                    ),
                )


            due = None
            if req.scadenza_id:
                due = await db[COL_SCADENZIARIO].find_one(
                    {"id": req.scadenza_id, "fattura_id": {"$in": varianti_id(req.fattura_id)}},
                    {"_id": 0}, **skw,
                )
                if not due:
                    raise HTTPException(status_code=404, detail="Scadenza non trovata per questa fattura")
                due_residual = float(
                    due.get("importo_residuo")
                    if due.get("importo_residuo") is not None
                    else due.get("importo_rata") or due.get("importo") or 0
                )
                if abs(req.importo) - due_residual > 0.005:
                    raise HTTPException(status_code=409, detail="L'importo supera il residuo della scadenza")

            dedup_query = (
                {"scadenza_id": req.scadenza_id}
                if req.scadenza_id else {"payment_operation_id": operation_id}
            )
            if req.metodo == "banca":
                dedup_query = {
                    "fattura_id": {"$in": varianti_id(req.fattura_id)},
                    "scadenza_id": req.scadenza_id,
                    "status": {"$nin": ["deleted", "archived"]},
                    "in_attesa_estratto_ufficiale": True,
                }
            existing_movement = await db[collection_name].find_one(dedup_query, **skw)
            if existing_movement and req.metodo == "banca":
                if (
                    abs(float(existing_movement.get("importo") or 0) - abs(req.importo)) > 0.005
                    or str(existing_movement.get("data") or "")[:10] != req.data_pagamento
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="Esiste gia' una dichiarazione bancaria diversa per questa fattura/scadenza",
                    )
            try:
                await db["pagamenti_operazioni"].insert_one({
                    "_id": operation_id,
                    "status": "in_progress",
                    "fattura_id": req.fattura_id,
                    "scadenza_id": req.scadenza_id,
                    "created_at": now,
                }, **skw)
            except DuplicateRecordError as exc:
                raise HTTPException(
                    status_code=409,
                    detail="Pagamento identico gia' in elaborazione",
                ) from exc

            if existing_movement:
                movement_id = existing_movement["id"]
                if req.metodo == "banca":
                    await db[collection_name].update_one({"id": movement_id}, {"$set": {
                        "dichiarato_titolare": True,
                        "stato": "DA_VERIFICARE",
                        "provvisorio": True,
                        "updated_at": now,
                    }}, **skw)
            else:
                from app.routers.prima_nota_module.sync import costruisci_campi_movimento_fattura

                fields = costruisci_campi_movimento_fattura({
                    "tipo_documento": invoice.get("tipo_documento"),
                    "invoice_number": req.numero_fattura,
                    "supplier_name": req.fornitore,
                    "supplier_vat": invoice.get("supplier_vat"),
                    "cedente_piva": invoice.get("cedente_piva"),
                }, req.importo)
                movement_id = str(uuid.uuid4())
                movement = {
                    "id": movement_id,
                    "data": req.data_pagamento,
                    "descrizione": fields["descrizione"],
                    "causale": "Pagamento fattura fornitore",
                    "importo": fields["importo"],
                    "tipo": fields["tipo"],
                    "categoria": fields["categoria"],
                    "numero_fattura": fields["numero_fattura"],
                    "tipo_documento": fields["tipo_documento"],
                    "stato": "DA_VERIFICARE" if req.metodo == "banca" else "confermato",
                    "fattura_id": req.fattura_id,
                    "scadenza_id": req.scadenza_id,
                    "fattura_collegata": req.fattura_id,
                    "fattura_numero": req.numero_fattura,
                    "fornitore": req.fornitore,
                    "metodo_pagamento": req.metodo,
                    "provvisorio": req.metodo == "banca",
                    "riconciliato": False,
                    "created_at": now,
                    "source": (
                        "manuale_banca_senza_evidenza" if req.metodo == "banca"
                        else "pagamento_manuale"
                    ),
                    "in_attesa_estratto_ufficiale": req.metodo == "banca",
                    "dichiarato_titolare": req.metodo == "banca",
                    "payment_operation_id": operation_id,
                }
                if req.metodo == "banca":
                    movement_id = await scrivi_movimento(db, "banca", movement, session=session)
                else:
                    await db[collection_name].insert_one(movement, **skw)

            if req.metodo == "banca":
                # Nessun campo "pagato", residuo, scadenza o data effettiva:
                # la dichiarazione resta fuori dai saldi e viene assorbita
                # dal writer canonico quando arriva la prova bancaria.
                await db[COL_FATTURE_RICEVUTE].update_one(
                    filtro_id(req.fattura_id), {"$set": {
                        "prima_nota_banca_id": movement_id,
                        "in_attesa_riscontro_banca": True,
                        "stato_finanziario": "in_attesa_estratto_conto",
                        "updated_at": now,
                    }}, **skw,
                )
                result = {
                    "success": True,
                    "movimento_id": movement_id,
                    "metodo": "banca",
                    "importo": req.importo,
                    "riconciliato": False,
                    "collection": collection_name,
                    "idempotent_replay": False,
                    "stato": "DA_VERIFICARE",
                    "pagamento_confermato": False,
                    "in_attesa_estratto_ufficiale": True,
                    "message": (
                        "Dichiarazione bancaria registrata; il pagamento richiede "
                        "il riscontro con un movimento dell'estratto conto ufficiale"
                    ),
                }
                await db["pagamenti_operazioni"].update_one(
                    {"_id": operation_id},
                    {"$set": {"status": "completed", "completed_at": now, "result": result}},
                    **skw,
                )
                return result

            if due:
                installment_amount = float(due.get("importo_rata") or due.get("importo") or abs(req.importo))
                paid_installment = round(float(due.get("importo_pagato") or 0) + abs(req.importo), 2)
                installment_closed = paid_installment + 0.005 >= installment_amount
                await db[COL_SCADENZIARIO].update_one(
                    {"id": req.scadenza_id},
                    {"$set": {
                        "stato": "pagata" if installment_closed else "parziale",
                        "pagato": installment_closed,
                        "importo_pagato": min(paid_installment, installment_amount),
                        "importo_residuo": max(0, round(installment_amount - paid_installment, 2)),
                        "data_pagamento": req.data_pagamento,
                        "metodo_effettivo": req.metodo,
                        "movimento_id": movement_id,
                        "updated_at": now,
                    }}, **skw,
                )

            paid = round(current_paid + abs(req.importo), 2)
            closed = paid + 0.005 >= total
            update_fields = {
                "status": "paid" if closed else "partial",
                "payment_status": "paid" if closed else "partial",
                "pagato": closed,
                "stato_pagamento": "pagata" if closed else "parziale",
                "importo_pagato": min(paid, total),
                "importo_residuo": max(0, round(total - paid, 2)),
                "riconciliato": False,
                "data_pagamento": req.data_pagamento,
                "metodo_pagamento_effettivo": req.metodo,
                "metodo_pagamento": req.metodo,
                "updated_at": now,
                "payment_operation_id": operation_id,
            }
            # Un pagamento parziale puo' usare metodi diversi. Non cancellare
            # mai il riferimento dell'altro registro quando arriva una quota.
            update_fields[
                "prima_nota_cassa_id" if req.metodo == "cassa" else "prima_nota_banca_id"
            ] = movement_id
            for name in {"invoices", COL_FATTURE_RICEVUTE}:
                await db[name].update_one(
                    filtro_id(req.fattura_id), {"$set": update_fields}, **skw,
                )

            result = {
                "success": True,
                "movimento_id": movement_id,
                "metodo": req.metodo,
                "importo": req.importo,
                "riconciliato": False,
                "collection": collection_name,
                "idempotent_replay": False,
                "stato": "confermato",
                "pagamento_confermato": True,
                "in_attesa_estratto_ufficiale": False,
            }
            await db["pagamenti_operazioni"].update_one(
                {"_id": operation_id},
                {"$set": {"status": "completed", "completed_at": now, "result": result}},
                **skw,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Pagamento non registrato: transazione annullata") from exc

    return result


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _supplier_payable_residual(invoice: Dict[str, Any]) -> float:
    payable = totale_pagabile_al_fornitore(invoice)
    try:
        paid = abs(float(invoice.get("importo_pagato") or 0))
    except (TypeError, ValueError):
        paid = 0.0
    return max(0.0, round(payable - paid, 2))


def _invoice_supplier(invoice: Dict[str, Any]) -> str:
    return str(
        invoice.get("supplier_name")
        or invoice.get("fornitore_ragione_sociale")
        or invoice.get("cedente_nome")
        or invoice.get("fornitore")
        or ""
    )


def _meaningful_supplier_tokens(value: Any) -> list[str]:
    ignored = {
        "srl", "spa", "sas", "snc", "societa", "ditta", "group", "italia",
        "di", "del", "della", "dei", "e",
    }
    return [
        token for token in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if len(token) >= 4 and token not in ignored
    ]


async def find_invoice_bank_candidates(db, fattura_id: str) -> Dict[str, Any]:
    """Restituisce bonifici compatibili senza trasformarli in pagamenti.

    L'importo al centesimo e' il filtro di ingresso. Numero fattura, identita'
    del fornitore, P.IVA e IBAN sono prove ulteriori esposte all'operatore.
    Nessun candidato viene riconciliato da questa lettura.
    """
    invoice = await db[COL_FATTURE_RICEVUTE].find_one(
        filtro_id(fattura_id), {"_id": 0},
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    residual = _supplier_payable_residual(invoice)
    if residual <= 0:
        return {"fattura_id": fattura_id, "importo_residuo": 0, "candidati": []}

    invoice_date = str(invoice.get("invoice_date") or invoice.get("data_fattura") or "")[:10]
    query: Dict[str, Any] = {"riconciliato": {"$ne": True}}
    try:
        start = datetime.strptime(invoice_date, "%Y-%m-%d")
        query["data"] = {
            "$gte": invoice_date,
            "$lte": (start + timedelta(days=370)).strftime("%Y-%m-%d"),
        }
    except ValueError:
        pass

    movements = await db["estratto_conto_movimenti"].find(
        query, {"_id": 0},
    ).sort("data", -1).to_list(10000)

    number = str(
        invoice.get("invoice_number") or invoice.get("numero_documento")
        or invoice.get("numero_fattura") or ""
    )
    supplier = _invoice_supplier(invoice)
    supplier_tokens = _meaningful_supplier_tokens(supplier)
    vat = _compact(invoice.get("supplier_vat") or invoice.get("fornitore_partita_iva"))
    iban = _compact(
        invoice.get("supplier_iban") or invoice.get("fornitore_iban")
        or invoice.get("iban")
    )
    candidates = []
    for movement in movements:
        try:
            amount = abs(float(movement.get("importo") or movement.get("amount") or 0))
        except (TypeError, ValueError):
            continue
        if abs(amount - residual) > 0.005:
            continue
        movement_type = str(movement.get("tipo") or "").lower()
        raw_amount = float(movement.get("importo") or movement.get("amount") or 0)
        if movement_type in {"entrata", "accredito", "incasso"} or (
            raw_amount > 0 and movement_type and movement_type not in {"uscita", "addebito", "pagamento"}
        ):
            continue

        description = " ".join(str(movement.get(key) or "") for key in (
            "descrizione_originale", "descrizione", "causale", "beneficiario",
            "controparte", "iban_beneficiario",
        ))
        compact_description = _compact(description)
        reasons = ["importo_residuo_esatto"]
        number_match = bool(_compact(number)) and _compact(number) in compact_description
        matched_tokens = [token for token in supplier_tokens if token in compact_description]
        supplier_match = bool(matched_tokens) and (
            len(supplier_tokens) == 1 or len(matched_tokens) >= min(2, len(supplier_tokens))
        )
        vat_match = bool(vat) and vat in compact_description
        movement_iban = _compact(
            movement.get("iban_beneficiario") or movement.get("iban_controparte")
            or movement.get("iban")
        )
        iban_match = bool(iban) and (iban == movement_iban or iban in compact_description)
        if number_match:
            reasons.append("numero_fattura_in_causale")
        if supplier_match:
            reasons.append("fornitore_in_causale")
        if vat_match:
            reasons.append("partita_iva_in_causale")
        if iban_match:
            reasons.append("iban_fornitore")

        level = "verificato" if number_match else (
            "forte" if supplier_match or vat_match or iban_match else "solo_importo"
        )
        candidates.append({
            "movimento_id": movement.get("id"),
            "data": str(movement.get("data") or "")[:10],
            "importo": amount,
            "descrizione": description.strip(),
            "livello": level,
            "motivi": reasons,
            "numero_fattura_presente": number_match,
            "richiede_conferma": not number_match,
        })

    order = {"verificato": 0, "forte": 1, "solo_importo": 2}
    candidates.sort(key=lambda item: item["data"], reverse=True)
    candidates.sort(key=lambda item: order[item["livello"]])
    return {
        "fattura_id": fattura_id,
        "numero_fattura": number,
        "fornitore": supplier,
        "importo_residuo": residual,
        "candidati": candidates[:50],
        "totale_candidati": len(candidates),
    }


async def reconcile_invoice_bank_movement(
    db, req: InvoiceBankReconciliationRequest,
) -> Dict[str, Any]:
    """Collega una fattura a una prova bancaria senza falsi positivi.

    Il percorso uno-a-uno richiede importo al centesimo e numero fattura
    nella causale. I pagamenti cumulativi devono usare il motore multi-fattura;
    un override manuale resta possibile, ma richiede una motivazione auditabile.
    """
    from app.services.bank_payment_allocations import (
        _controparte_incompatibile,
        persist_bank_invoice_allocations,
        validate_bank_invoice_allocations,
    )
    from app.services.riscontro_estratto_prima_nota import evidenza_ufficiale, _escluso

    async with _transazione_registro(db) as session:
        skw = _sessione(session)
        invoice = await db[COL_FATTURE_RICEVUTE].find_one(
            filtro_id(req.fattura_id), {"_id": 0}, **skw,
        )
        if not invoice:
            raise HTTPException(status_code=404, detail="Fattura non trovata")
        movement = await db["estratto_conto_movimenti"].find_one(
            {"id": req.movimento_id}, {"_id": 0}, **skw,
        )
        if not movement:
            raise HTTPException(status_code=404, detail="Movimento non trovato")
        if (_escluso(movement) or not evidenza_ufficiale(movement)
                or movement.get("provvisorio") is True):
            raise HTTPException(
                status_code=409,
                detail="Serve un movimento attivo dell'estratto conto ufficiale, non un export provvisorio",
            )

        linked_invoice = movement.get("fattura_id")
        if str(linked_invoice or "") == str(invoice.get("id")) and movement.get("riconciliato") is True:
            return {
                "success": True, "fattura_id": req.fattura_id,
                "movimento_id": req.movimento_id,
                "message": "Riconciliazione gia' presente",
                "idempotent_replay": True,
            }
        if linked_invoice not in (None, "") or movement.get("riconciliato") is True:
            raise HTTPException(status_code=409, detail="Movimento gia' utilizzato in un'altra riconciliazione")

        residual = _supplier_payable_residual(invoice)
        bank_amount = abs(float(movement.get("importo") or movement.get("amount") or 0))
        if residual <= 0 or not math.isfinite(bank_amount) or abs(residual - bank_amount) > 0.005:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Importo non univoco: usa il motore multi-fattura per pagamenti "
                    "cumulativi o parziali"
                ),
            )
        if _controparte_incompatibile(movement, invoice):
            raise HTTPException(status_code=409, detail="Beneficiario o IBAN bancario incompatibile con il fornitore")

        invoice_number = (
            invoice.get("invoice_number") or invoice.get("numero_documento")
            or invoice.get("numero_fattura") or ""
        )
        description = " ".join(str(movement.get(key) or "") for key in (
            "descrizione_originale", "descrizione", "causale",
        ))
        number_matches = bool(_compact(invoice_number)) and _compact(invoice_number) in _compact(description)
        if not number_matches and not req.override_reason:
            raise HTTPException(
                status_code=409,
                detail="Numero fattura assente dalla causale bancaria: associazione non univoca",
            )

        # Unico writer bancario: quote, fattura, rate, partita aperta,
        # relazione, estratto e Prima Nota si aggiornano nello stesso motore.
        allocations = await validate_bank_invoice_allocations(
            db, movement, [{"fattura_id": req.fattura_id, "quota": bank_amount}],
        )
        await persist_bank_invoice_allocations(
            db, movement, allocations, actor="manuale_numero_importo",
        )
        await db["audit_riconciliazioni"].insert_one({
            "id": str(uuid.uuid4()),
            "azione": "riconciliazione_fattura_banca",
            "fattura_id": req.fattura_id,
            "movimento_id": req.movimento_id,
            "importo": bank_amount,
            "numero_fattura": invoice_number,
            "numero_in_causale": number_matches,
            "override_reason": req.override_reason,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, **skw)

    return {
        "success": True, "fattura_id": req.fattura_id,
        "movimento_id": req.movimento_id,
        "message": "Riconciliazione completata con prova bancaria ufficiale",
        "idempotent_replay": False,
    }
