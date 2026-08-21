"""Servizio atomico per i pagamenti manuali delle fatture passive."""
from datetime import datetime, timezone
import hashlib
import math
import uuid
from typing import Any, Dict, Literal, Optional
import re

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.services.sheets_document_store import DuplicateRecordError

from app.services.scritture_contabili import _sessione, _transazione_registro


COL_SCADENZIARIO = "scadenziario_fornitori"
COL_FATTURE_RICEVUTE = "invoices"


class ManualInvoicePaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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


class InvoiceBankReconciliationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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
    """Registra movimento, scadenza e fattura in una singola transazione.

    La collection ``pagamenti_operazioni`` usa ``_id`` come chiave di
    idempotenza: retry HTTP e doppio click non incrementano due volte il
    pagato. Su Atlas tutte le mutazioni fanno commit o rollback insieme.
    """
    invoice = (
        await db["invoices"].find_one({"id": req.fattura_id}, {"_id": 0})
        or await db[COL_FATTURE_RICEVUTE].find_one({"id": req.fattura_id}, {"_id": 0})
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
                {"id": req.fattura_id}, {"_id": 0}, **skw,
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

            total = abs(float(
                invoice.get("total_amount")
                or invoice.get("importo_totale")
                or req.importo
            ))
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

            due = None
            if req.scadenza_id:
                due = await db[COL_SCADENZIARIO].find_one(
                    {"id": req.scadenza_id, "fattura_id": req.fattura_id},
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
            existing_movement = await db[collection_name].find_one(dedup_query, **skw)
            if existing_movement:
                movement_id = existing_movement["id"]
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
                await db[collection_name].insert_one({
                    "id": movement_id,
                    "data": req.data_pagamento,
                    "descrizione": fields["descrizione"],
                    "causale": "Pagamento fattura fornitore",
                    "importo": fields["importo"],
                    "tipo": fields["tipo"],
                    "categoria": fields["categoria"],
                    "numero_fattura": fields["numero_fattura"],
                    "tipo_documento": fields["tipo_documento"],
                    "stato": "confermato",
                    "fattura_id": req.fattura_id,
                    "scadenza_id": req.scadenza_id,
                    "fattura_collegata": req.fattura_id,
                    "fattura_numero": req.numero_fattura,
                    "fornitore": req.fornitore,
                    "metodo_pagamento": req.metodo,
                    "provvisorio": False,
                    "riconciliato": False,
                    "created_at": now,
                    "source": "pagamento_manuale",
                    "payment_operation_id": operation_id,
                }, **skw)

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
                    {"id": req.fattura_id}, {"$set": update_fields}, **skw,
                )

            result = {
                "success": True,
                "movimento_id": movement_id,
                "metodo": req.metodo,
                "importo": req.importo,
                "riconciliato": False,
                "collection": collection_name,
                "idempotent_replay": False,
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


async def reconcile_invoice_bank_movement(
    db, req: InvoiceBankReconciliationRequest,
) -> Dict[str, Any]:
    """Collega una fattura a una prova bancaria senza falsi positivi.

    Il percorso uno-a-uno richiede importo al centesimo e numero fattura
    nella causale. I pagamenti cumulativi devono usare il motore multi-fattura;
    un override manuale resta possibile, ma richiede una motivazione auditabile.
    """
    invoice = (
        await db[COL_FATTURE_RICEVUTE].find_one({"id": req.fattura_id}, {"_id": 0})
        or await db["invoices"].find_one({"id": req.fattura_id}, {"_id": 0})
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    movement = await db["estratto_conto_movimenti"].find_one(
        {"id": req.movimento_id}, {"_id": 0},
    )
    if not movement:
        raise HTTPException(status_code=404, detail="Movimento non trovato")

    linked_invoice = movement.get("fattura_id")
    if linked_invoice == req.fattura_id and movement.get("riconciliato") is True:
        return {
            "success": True, "fattura_id": req.fattura_id,
            "movimento_id": req.movimento_id,
            "message": "Riconciliazione gia' presente",
            "idempotent_replay": True,
        }
    if linked_invoice and linked_invoice != req.fattura_id:
        raise HTTPException(status_code=409, detail="Movimento gia' collegato a un'altra fattura")

    residual = abs(float(
        invoice.get("importo_residuo")
        if invoice.get("importo_residuo") is not None
        else invoice.get("total_amount") or invoice.get("importo_totale") or 0
    ))
    bank_amount = abs(float(movement.get("importo") or movement.get("amount") or 0))
    if residual <= 0 or abs(residual - bank_amount) > 0.005:
        raise HTTPException(
            status_code=409,
            detail=(
                "Importo non univoco: usa il motore multi-fattura per pagamenti "
                "cumulativi o parziali"
            ),
        )

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

    now = datetime.now(timezone.utc).isoformat()
    first_note_id = invoice.get("prima_nota_banca_id")
    audit = {
        "id": str(uuid.uuid4()),
        "azione": "riconciliazione_fattura_banca",
        "fattura_id": req.fattura_id,
        "movimento_id": req.movimento_id,
        "importo": bank_amount,
        "numero_fattura": invoice_number,
        "numero_in_causale": number_matches,
        "override_reason": req.override_reason,
        "created_at": now,
    }
    async with _transazione_registro(db) as session:
        skw = _sessione(session)
        invoice_updates = {
            "riconciliato": True,
            "movimento_bancario_id": req.movimento_id,
            "data_riconciliazione": now,
            "provvisorio": False,
            "pagato": True,
            "status": "paid",
            "payment_status": "paid",
            "stato_pagamento": "pagata",
            "importo_pagato": residual,
            "importo_residuo": 0,
            "updated_at": now,
        }
        for name in {COL_FATTURE_RICEVUTE, "invoices"}:
            await db[name].update_one(
                {"id": req.fattura_id}, {"$set": invoice_updates}, **skw,
            )
        await db["estratto_conto_movimenti"].update_one(
            {"id": req.movimento_id},
            {"$set": {
                "riconciliato": True,
                "fattura_id": req.fattura_id,
                "tipo_riconciliazione": "fattura_numero_importo_esatti",
                "updated_at": now,
            }}, **skw,
        )
        if first_note_id:
            await db["prima_nota_banca"].update_one(
                {"id": first_note_id},
                {"$set": {
                    "riconciliato": True,
                    "movimento_bancario_id": req.movimento_id,
                    "provvisorio": False,
                    "updated_at": now,
                }}, **skw,
            )
        await db["audit_riconciliazioni"].insert_one(audit, **skw)

    return {
        "success": True, "fattura_id": req.fattura_id,
        "movimento_id": req.movimento_id,
        "message": "Riconciliazione completata con prova numero+importo",
        "idempotent_replay": False,
    }
