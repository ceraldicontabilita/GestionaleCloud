"""Motore universale di rielaborazione dei documenti archiviati.

Lavora sui documenti originali gia presenti in ``documents_inbox`` e non crea
nuovi eventi economici. In simulazione non scrive nulla; in esecuzione salva
solo l'esito della nuova lettura accanto al documento originale.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.database import Database
from app.services.ai_document_parser import parse_document_with_ai

COLLEZIONE = "documents_inbox"
VERSIONE_RIELABORAZIONE = "universale-v1"


def _categoria(doc: Dict[str, Any]) -> str:
    return str(
        doc.get("document_type")
        or doc.get("category")
        or doc.get("tipo_documento")
        or doc.get("category_label")
        or "non_classificato"
    ).strip().lower()


def _tipo_parser(categoria: str) -> str:
    c = categoria.lower()
    if any(x in c for x in ("fattura", "nota_credito", "nota-debito", "nota_debito")):
        return "fattura"
    if "f24" in c:
        return "f24"
    if any(x in c for x in ("cedolino", "busta_paga", "busta-paga", "lul")):
        return "busta_paga"
    if any(x in c for x in ("verbale", "pagopa", "multa", "sanzione")):
        return "verbale"
    return "auto"


def _contenuto(doc: Dict[str, Any]) -> Optional[bytes]:
    for campo in ("pdf_data", "file_base64", "pdf_base64"):
        valore = doc.get(campo)
        if valore:
            try:
                return base64.b64decode(valore)
            except Exception:
                continue
    raw = doc.get("content") or doc.get("raw_content")
    if isinstance(raw, bytes):
        return raw
    return None


def _mime(doc: Dict[str, Any]) -> str:
    return str(doc.get("mime_type") or doc.get("content_type") or "application/pdf")


class RielaborazioneDocumentiService:
    def __init__(self, db=None):
        self.db = db

    async def _db(self):
        if self.db is None:
            self.db = Database.get_db()
        if self.db is None:
            raise RuntimeError("Database non connesso")
        return self.db

    async def anteprima(self) -> Dict[str, Any]:
        db = await self._db()
        pipeline = [
            {"$match": {"$or": [
                {"pdf_data": {"$exists": True, "$ne": None}},
                {"file_base64": {"$exists": True, "$ne": None}},
                {"pdf_base64": {"$exists": True, "$ne": None}},
                {"content": {"$exists": True, "$ne": None}},
                {"raw_content": {"$exists": True, "$ne": None}},
            ]}},
            {"$project": {
                "categoria": {"$ifNull": [
                    "$document_type",
                    {"$ifNull": ["$category", {"$ifNull": ["$tipo_documento", "non_classificato"]}]},
                ]}
            }},
            {"$group": {"_id": "$categoria", "totale": {"$sum": 1}}},
            {"$sort": {"totale": -1, "_id": 1}},
        ]
        categorie = {}
        async for riga in db[COLLEZIONE].aggregate(pipeline):
            categorie[str(riga.get("_id") or "non_classificato")] = int(riga.get("totale") or 0)
        return {
            "categorie": categorie,
            "totale": sum(categorie.values()),
            "versione": VERSIONE_RIELABORAZIONE,
            "fonte": COLLEZIONE,
        }

    async def rielabora(self, *, dry_run: bool = True, categoria: Optional[str] = None) -> Dict[str, Any]:
        db = await self._db()
        query: Dict[str, Any] = {"$or": [
            {"pdf_data": {"$exists": True, "$ne": None}},
            {"file_base64": {"$exists": True, "$ne": None}},
            {"pdf_base64": {"$exists": True, "$ne": None}},
            {"content": {"$exists": True, "$ne": None}},
            {"raw_content": {"$exists": True, "$ne": None}},
        ]}
        if categoria:
            query = {"$and": [query, {"$or": [
                {"document_type": categoria},
                {"category": categoria},
                {"tipo_documento": categoria},
            ]}]}

        stats = {
            "totale_documenti": 0,
            "totale_processati": 0,
            "totale_successi": 0,
            "totale_errori": 0,
            "categorie": {},
            "errors": [],
            "dry_run": dry_run,
            "categoria": categoria,
            "versione": VERSIONE_RIELABORAZIONE,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        cursor = db[COLLEZIONE].find(query)
        async for doc in cursor:
            stats["totale_documenti"] += 1
            cat = _categoria(doc)
            voce = stats["categorie"].setdefault(cat, {"totale": 0, "successi": 0, "errori": 0})
            voce["totale"] += 1
            contenuto = _contenuto(doc)
            if not contenuto:
                voce["errori"] += 1
                stats["totale_errori"] += 1
                continue

            stats["totale_processati"] += 1
            try:
                tipo_parser = _tipo_parser(cat)
                risultato = await parse_document_with_ai(
                    file_bytes=contenuto,
                    document_type=tipo_parser,
                    mime_type=_mime(doc),
                )
                success = bool(risultato.get("success"))
                if success:
                    stats["totale_successi"] += 1
                    voce["successi"] += 1
                else:
                    stats["totale_errori"] += 1
                    voce["errori"] += 1

                if not dry_run:
                    await db[COLLEZIONE].update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "rielaborazione": {
                                "versione": VERSIONE_RIELABORAZIONE,
                                "categoria_precedente": cat,
                                "parser_usato": tipo_parser,
                                "success": success,
                                "risultato": risultato,
                                "rielaborato_at": datetime.now(timezone.utc).isoformat(),
                            }
                        }},
                    )
                if not success and len(stats["errors"]) < 100:
                    stats["errors"].append({
                        "document_id": str(doc.get("id") or doc.get("_id")),
                        "type": cat,
                        "error": risultato.get("error") or "Rielaborazione non riuscita",
                    })
            except Exception as exc:
                stats["totale_errori"] += 1
                voce["errori"] += 1
                if len(stats["errors"]) < 100:
                    stats["errors"].append({
                        "document_id": str(doc.get("id") or doc.get("_id")),
                        "type": cat,
                        "error": str(exc),
                    })

        stats["ended_at"] = datetime.now(timezone.utc).isoformat()
        return stats
