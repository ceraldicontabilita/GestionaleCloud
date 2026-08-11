"""Vista applicativa unica per modelli F24, quietanze e righe tributo.

Le collezioni restano distinte perche' descrivono documenti diversi. Tutte le
pagine fiscali devono pero' leggere da questo adapter, che applica una sola
normalizzazione e una sola semantica della prova di pagamento.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.services.f24_canonico import normalizza_righe_tributo
from app.services.f24_payment_evidence import stato_evidenza_pagamento


async def _read_all(collection, projection: Dict[str, Any] | None = None) -> list[dict]:
    cursor = collection.find({}, projection or {"_id": 0})
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(10000)
    return [item async for item in cursor]


async def _read_many(
    collection, query: Dict[str, Any], projection: Dict[str, Any] | None = None,
) -> list[dict]:
    cursor = collection.find(query, projection or {"_id": 0})
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(50000)
    return [item async for item in cursor]


class TaxPaymentQueryService:
    """Unico accesso in lettura usato da Ritenute, IVA e viste fiscali."""

    def __init__(self, db):
        self.db = db

    async def list_documents(self, *, include_pdf: bool = False) -> List[Dict[str, Any]]:
        projection = {"_id": 0} if include_pdf else {"_id": 0, "pdf_data": 0}
        models = await _read_all(self.db["f24_unificato"], projection)
        receipts = await _read_all(self.db["quietanze_f24"], projection)
        receipts_by_id = {str(item.get("id")): item for item in receipts if item.get("id")}
        relations = await _read_many(
            self.db["entity_relations"], {"status": "confirmed"}, {"_id": 0}
        )
        known_bank_ids = {
            str(endpoint.get("id"))
            for relation in relations
            for endpoint in (relation.get("source") or {}, relation.get("target") or {})
            if endpoint.get("type") == "bank_movement" and endpoint.get("id")
        }
        known_bank_ids.update(
            str(model.get(field))
            for model in models
            for field in ("movimento_bancario_id", "bank_movement_id", "estratto_conto_id")
            if model.get(field)
        )
        bank_records = await _read_many(
            self.db["estratto_conto_movimenti"],
            {"$or": [
                {"id": {"$in": sorted(known_bank_ids)}},
                {"fingerprint": {"$in": sorted(known_bank_ids)}},
            ]} if known_bank_ids else {"id": {"$in": []}},
            {
                "_id": 0, "id": 1, "fingerprint": 1, "data_contabile": 1,
                "data": 1, "booking_date": 1, "prima_nota_banca_id": 1,
                "prima_nota_id": 1,
            },
        )
        banks_by_id: Dict[str, Dict[str, Any]] = {}
        for bank_record in bank_records:
            for field in ("id", "fingerprint"):
                if bank_record.get(field):
                    banks_by_id[str(bank_record[field])] = bank_record

        relations_by_f24: Dict[str, List[Dict[str, Any]]] = {}
        for relation in relations:
            source = relation.get("source") or {}
            target = relation.get("target") or {}
            f24_ids = set()
            if source.get("type") == "f24_model" and source.get("id"):
                f24_ids.add(str(source["id"]))
            if target.get("type") == "f24_model" and target.get("id"):
                f24_ids.add(str(target["id"]))
            for endpoint in (source, target):
                endpoint_id = str(endpoint.get("id") or "")
                if endpoint.get("type") == "tax_row" and ":tax:" in endpoint_id:
                    f24_ids.add(endpoint_id.rsplit(":tax:", 1)[0])
            for f24_id in f24_ids:
                relations_by_f24.setdefault(f24_id, []).append(relation)

        result = []
        for source in models:
            doc = dict(source)
            f24_id = str(doc.get("id") or "")
            rows = normalizza_righe_tributo(doc)
            tax_rows = [{
                "id": f"{f24_id}:tax:{row['ordinal']}",
                "ordinal": row["ordinal"],
                "tax_code": row["tax_code"],
                "reference_period": row["reference_period"],
                "debit_cents": row["debit_cents"],
                "credit_cents": row["credit_cents"],
            } for row in rows]
            chain_relations = relations_by_f24.get(f24_id, [])

            receipt_ids = {
                str(endpoint.get("id"))
                for relation in chain_relations
                for endpoint in (relation.get("source") or {}, relation.get("target") or {})
                if endpoint.get("type") == "f24_receipt" and endpoint.get("id")
            }
            if doc.get("quietanza_id"):
                receipt_ids.add(str(doc["quietanza_id"]))
            receipt_candidates = [
                receipts_by_id[receipt_id]
                for receipt_id in sorted(receipt_ids)
                if receipt_id in receipts_by_id
            ]
            receipt = receipt_candidates[0] if len(receipt_candidates) == 1 else None
            if receipt:
                doc["quietanza_id"] = receipt.get("id")
                if not doc.get("protocollo_quietanza"):
                    doc["protocollo_quietanza"] = receipt.get("protocollo_telematico")
                if not doc.get("data_pagamento_quietanza"):
                    doc["data_pagamento_quietanza"] = receipt.get("data_pagamento")
                if not doc.get("quietanza_filename"):
                    doc["quietanza_filename"] = receipt.get("filename")
            bank_ids = {
                str(endpoint.get("id"))
                for relation in chain_relations
                for endpoint in (relation.get("source") or {}, relation.get("target") or {})
                if endpoint.get("type") == "bank_movement" and endpoint.get("id")
            }
            initial_evidence = stato_evidenza_pagamento(doc)
            if initial_evidence.get("movimento_bancario_id"):
                bank_ids.add(str(initial_evidence["movimento_bancario_id"]))
            bank_settlements = {
                str(relation.get("relation_key")): int(relation.get("amount_cents") or 0)
                for relation in chain_relations
                if relation.get("relation_type") == "settles_f24_model"
            }
            settled_cents = sum(bank_settlements.values())
            expected_cents = max(0, sum(
                int(row.get("debit_cents") or 0) - int(row.get("credit_cents") or 0)
                for row in rows
            ))
            bank_records_for_document = [
                banks_by_id[movement_id]
                for movement_id in sorted(bank_ids)
                if movement_id in banks_by_id
            ]
            if (
                not initial_evidence.get("verificato_banca")
                and settled_cents
                and expected_cents
                and settled_cents == expected_cents
                and len(bank_ids) == 1
                and len(bank_records_for_document) == 1
            ):
                bank_record = bank_records_for_document[0]
                bank_date = (
                    bank_record.get("data_contabile")
                    or bank_record.get("data")
                    or bank_record.get("booking_date")
                )
                if bank_date:
                    doc["movimento_bancario_id"] = next(iter(bank_ids))
                    doc["data_pagamento_effettivo"] = bank_date
            evidence = stato_evidenza_pagamento(doc)

            if evidence.get("verificato_banca"):
                bank_axis = "VERIFICATA"
            elif settled_cents and expected_cents and settled_cents == expected_cents:
                bank_axis = "EVIDENZA_INCOMPLETA"
            elif settled_cents and expected_cents and settled_cents < expected_cents:
                bank_axis = "PARZIALE"
            elif settled_cents and expected_cents and settled_cents > expected_cents:
                bank_axis = "CONFLITTO"
            else:
                bank_axis = "NON_VERIFICATA"
            bank_verified = bank_axis == "VERIFICATA"

            prima_nota_ids = {
                str(endpoint.get("id"))
                for relation in chain_relations
                for endpoint in (relation.get("source") or {}, relation.get("target") or {})
                if endpoint.get("type") == "prima_nota_entry" and endpoint.get("id")
            }
            if doc.get("prima_nota_banca_id"):
                prima_nota_ids.add(str(doc["prima_nota_banca_id"]))
            for bank_record in bank_records_for_document:
                prima_nota_id = (
                    bank_record.get("prima_nota_banca_id")
                    or bank_record.get("prima_nota_id")
                )
                if prima_nota_id:
                    prima_nota_ids.add(str(prima_nota_id))
            bank_movements = [{
                "id": movement_id,
                "verified": bank_verified,
                "collection": "estratto_conto_movimenti",
                "date": (
                    (banks_by_id.get(movement_id) or {}).get("data_contabile")
                    or (banks_by_id.get(movement_id) or {}).get("data")
                    or (banks_by_id.get(movement_id) or {}).get("booking_date")
                ),
            } for movement_id in sorted(bank_ids)]
            prima_nota_entries = [{
                "id": entry_id, "collection": "prima_nota_banca"
            } for entry_id in sorted(prima_nota_ids)]
            payment_chain = {
                "f24_model": {"id": f24_id, "collection": "f24_unificato"},
                "tax_rows": tax_rows,
                "receipt": ({
                    "id": receipt.get("id"),
                    "protocol": receipt.get("protocollo_telematico"),
                    "collection": "quietanze_f24",
                } if receipt else None),
                "receipt_candidates": [{
                    "id": item.get("id"),
                    "protocol": item.get("protocollo_telematico"),
                    "collection": "quietanze_f24",
                } for item in receipt_candidates],
                "bank_movement": bank_movements[0] if len(bank_movements) == 1 else None,
                "bank_movements": bank_movements,
                "prima_nota": prima_nota_entries[0] if len(prima_nota_entries) == 1 else None,
                "prima_nota_entries": prima_nota_entries,
                "settled_cents": settled_cents,
                "expected_cents": expected_cents,
                "relations": chain_relations,
                "axes": {
                    "obligation": "F24_MODELLO_PRESENTE",
                    "document_evidence": (
                        "VERSATO_DOCUMENTALMENTE" if evidence["versato_documentalmente"]
                        else "QUIETANZA_AMBIGUA" if len(receipt_candidates) > 1
                        else "QUIETANZA_NON_PRESENTE"
                    ),
                    "bank": bank_axis,
                },
            }
            doc.update({
                "righe_tributo_normalizzate": rows,
                "righe_credito": [row for row in rows if row["credit_amount"] > 0],
                "evidenza_pagamento": evidence,
                "versato_documentalmente": evidence["versato_documentalmente"],
                "banca_verificata": bank_verified,
                "quietanza": receipt,
                "payment_chain": payment_chain,
                "canonical_query_source": "tax_payment_query_service",
            })
            result.append(doc)
        return result

    async def list_rows(
        self, *, tax_code: str | None = None, reference_period: str | None = None,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for document in await self.list_documents():
            for row in document["righe_tributo_normalizzate"]:
                if tax_code and row.get("tax_code") != tax_code:
                    continue
                if reference_period and row.get("reference_period") != reference_period:
                    continue
                rows.append({
                    **row,
                    "f24_id": document.get("id"),
                    "filename": document.get("file_name") or document.get("filename"),
                    "quietanza_id": document.get("quietanza_id"),
                    "protocollo_quietanza": document.get("protocollo_quietanza"),
                    "evidenza_pagamento": document["evidenza_pagamento"],
                })
        return rows
