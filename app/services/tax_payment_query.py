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


class TaxPaymentQueryService:
    """Unico accesso in lettura usato da Ritenute, IVA e viste fiscali."""

    def __init__(self, db):
        self.db = db

    async def list_documents(self, *, include_pdf: bool = False) -> List[Dict[str, Any]]:
        projection = {"_id": 0} if include_pdf else {"_id": 0, "pdf_data": 0}
        models = await _read_all(self.db["f24_unificato"], projection)
        receipts = await _read_all(self.db["quietanze_f24"], projection)
        receipts_by_id = {str(item.get("id")): item for item in receipts if item.get("id")}

        result = []
        for source in models:
            doc = dict(source)
            receipt = receipts_by_id.get(str(doc.get("quietanza_id") or ""))
            if receipt:
                if not doc.get("protocollo_quietanza"):
                    doc["protocollo_quietanza"] = receipt.get("protocollo_telematico")
                if not doc.get("data_pagamento_quietanza"):
                    doc["data_pagamento_quietanza"] = receipt.get("data_pagamento")
                if not doc.get("quietanza_filename"):
                    doc["quietanza_filename"] = receipt.get("filename")
            rows = normalizza_righe_tributo(doc)
            evidence = stato_evidenza_pagamento(doc)
            doc.update({
                "righe_tributo_normalizzate": rows,
                "righe_credito": [row for row in rows if row["credit_amount"] > 0],
                "evidenza_pagamento": evidence,
                "versato_documentalmente": evidence["versato_documentalmente"],
                "banca_verificata": evidence["verificato_banca"],
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
