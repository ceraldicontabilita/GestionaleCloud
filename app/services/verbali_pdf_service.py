"""Vista unica dei PDF collegati a un verbale, inclusi documents_inbox."""

from __future__ import annotations

from typing import Any, Dict, List


def _metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in item.items() if key != "content_base64"}


async def collect_verbale_pdfs(
    db, verbale: Dict[str, Any], *, include_content: bool = True
) -> List[Dict[str, Any]]:
    """Unisce formati storici e documenti importati senza duplicare gli ID."""
    results: List[Dict[str, Any]] = []
    seen_document_ids = set()

    allegati = verbale.get("pdf_allegati") or []
    for index, pdf in enumerate(allegati):
        results.append({
            "indice": index,
            "filename": pdf.get("filename") or f"verbale_{index + 1}.pdf",
            "tipo": pdf.get("tipo") or "allegato",
            "size": pdf.get("size") or 0,
            "source": "verbale_legacy",
            **({"content_base64": pdf.get("content_base64") or pdf.get("pdf_data")}
               if include_content else {}),
        })

    if not allegati and verbale.get("pdf_data"):
        results.append({
            "indice": 0,
            "filename": verbale.get("pdf_filename") or "verbale.pdf",
            "tipo": "verbale",
            "size": verbale.get("pdf_size") or 0,
            "source": "verbale_legacy",
            **({"content_base64": verbale.get("pdf_data")} if include_content else {}),
        })

    if verbale.get("quietanza_pdf"):
        used = {item["indice"] for item in results}
        quietanza_index = 1 if 1 not in used else max(used, default=0) + 1
        results.append({
            "indice": quietanza_index,
            "filename": verbale.get("quietanza_filename") or "quietanza.pdf",
            "tipo": "quietanza",
            "size": 0,
            "source": "verbale_legacy",
            **({"content_base64": verbale.get("quietanza_pdf")}
               if include_content else {}),
        })

    clauses = []
    document_ids = {
        str(value) for value in (verbale.get("document_ids") or []) if value
    }
    if verbale.get("source_document_id"):
        document_ids.add(str(verbale["source_document_id"]))
    if document_ids:
        clauses.append({"id": {"$in": sorted(document_ids)}})
    if verbale.get("id"):
        clauses.append({"verbale_id": verbale["id"]})
    for numero in {verbale.get("numero_verbale"), verbale.get("numero_verbale_old")}:
        if numero:
            clauses.extend([
                {"numero_verbale": numero},
                {"numero_verbale_estratto": numero},
            ])

    if clauses:
        projection = {
            "_id": 0, "id": 1, "filename": 1, "file_hash": 1,
            "size": 1, "tipo_documento": 1, "category": 1, "created_at": 1,
        }
        if include_content:
            projection["pdf_data"] = 1
        documents = await db["documents_inbox"].find(
            {"$and": [{"$or": clauses}, {"pdf_data": {"$exists": True, "$ne": ""}}]},
            projection,
        ).sort("created_at", 1).limit(50).to_list(50)
        next_index = max((item["indice"] for item in results), default=-1) + 1
        for document in documents:
            document_id = str(document.get("id") or "")
            if not document_id or document_id in seen_document_ids:
                continue
            seen_document_ids.add(document_id)
            results.append({
                "indice": next_index,
                "id": document_id,
                "document_id": document_id,
                "filename": document.get("filename") or f"verbale_{next_index + 1}.pdf",
                "tipo": document.get("tipo_documento") or document.get("category") or "verbale",
                "size": document.get("size") or 0,
                **({"content_base64": document.get("pdf_data")} if include_content else {}),
                "source": "documents_inbox",
                "file_hash": document.get("file_hash"),
            })
            next_index += 1

    return results


def pdf_metadata(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rimuove il contenuto base64 dalla risposta di dettaglio."""
    return [_metadata(item) for item in items]
