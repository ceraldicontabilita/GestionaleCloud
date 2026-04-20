"""
Fatture Module - CRUD e Visualizzazione fatture.
"""
from fastapi import HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import base64
import calendar

from app.database import Database
from .common import COL_FORNITORI, COL_FATTURE_RICEVUTE, COL_DETTAGLIO_RIGHE, COL_ALLEGATI, logger
from .helpers import generate_invoice_html


def _normalizza_da_invoices(doc: dict) -> dict:
    """Mappa un documento della collection `invoices` nel formato unificato archivio."""
    try:
        importo_totale = float(doc.get("total_amount") or 0)
    except (ValueError, TypeError):
        importo_totale = 0.0
    try:
        imponibile = float(doc.get("taxable_amount") or 0)
    except (ValueError, TypeError):
        imponibile = 0.0
    try:
        iva = float(doc.get("vat_amount") or 0)
    except (ValueError, TypeError):
        iva = 0.0
    if not imponibile and importo_totale > 0:
        imponibile = round(importo_totale / 1.22, 2)
        iva = round(importo_totale - imponibile, 2)

    stato_raw = doc.get("stato", "importata")
    pagato = bool(
        doc.get("pagato")
        or stato_raw in ("pagata", "paid")
        or doc.get("payment_status") == "paid"
    )
    created_at = doc.get("imported_at")
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()

    return {
        "id": doc.get("id", ""),
        "numero_documento": doc.get("invoice_number"),
        "data_documento": doc.get("invoice_date"),
        "importo_totale": importo_totale,
        "imponibile": imponibile,
        "iva": iva,
        "fornitore_ragione_sociale": doc.get("supplier_name") or doc.get("cedente_denominazione"),
        "fornitore_partita_iva": doc.get("supplier_vat"),
        "stato": "pagata" if pagato else stato_raw,
        "metodo_pagamento": doc.get("payment_method"),
        "metodo_pagamento_effettivo": doc.get("payment_method"),
        "pagato": pagato,
        "riconciliato": bool(doc.get("riconciliato")),
        "prima_nota_cassa_id": doc.get("prima_nota_cassa_id"),
        "prima_nota_banca_id": doc.get("prima_nota_banca_id"),
        "has_pdf": False,
        "email_associata": doc.get("email_from"),
        "anno": doc.get("anno") or (int(doc["invoice_date"][:4]) if doc.get("invoice_date") else None),
        "created_at": created_at,
        "data_pagamento": doc.get("data_pagamento"),
        "fonte": doc.get("fonte", "aruba_pec"),
        "_xml_filename": doc.get("xml_filename"),   # usato solo per dedup
    }


def _normalizza_da_fatture_passive(doc: dict) -> dict:
    """Mappa un documento della collection `fatture_passive` nel formato unificato archivio."""
    try:
        importo_totale = float(doc.get("importo_totale") or 0)
    except (ValueError, TypeError):
        importo_totale = 0.0
    try:
        imponibile = float(doc.get("imponibile") or 0)
    except (ValueError, TypeError):
        imponibile = 0.0
    try:
        iva = float(doc.get("iva") or 0)
    except (ValueError, TypeError):
        iva = 0.0
    if not imponibile and importo_totale > 0:
        imponibile = round(importo_totale / 1.22, 2)
        iva = round(importo_totale - imponibile, 2)

    stato_raw = doc.get("stato", "da_confermare")
    pagato = bool(doc.get("pagato") or stato_raw == "pagata")
    created_at = doc.get("created_at")
    if hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()

    return {
        "id": doc.get("dedup_key", ""),
        "numero_documento": doc.get("numero"),
        "data_documento": doc.get("data"),
        "importo_totale": importo_totale,
        "imponibile": imponibile,
        "iva": iva,
        "fornitore_ragione_sociale": doc.get("fornitore_denominazione"),
        "fornitore_partita_iva": doc.get("fornitore_piva"),
        "stato": "pagata" if pagato else stato_raw,
        "metodo_pagamento": doc.get("metodo_pagamento"),
        "metodo_pagamento_effettivo": doc.get("metodo_pagamento"),
        "pagato": pagato,
        "riconciliato": bool(doc.get("riconciliato")),
        "prima_nota_cassa_id": doc.get("prima_nota_cassa_id"),
        "prima_nota_banca_id": doc.get("prima_nota_banca_id"),
        "has_pdf": False,
        "email_associata": None,
        "anno": doc.get("anno") or (int(doc["data"][:4]) if doc.get("data") else None),
        "created_at": created_at,
        "data_pagamento": doc.get("data_pagamento"),
        "fonte": doc.get("source", "pec_auto"),
        "_xml_filename": doc.get("xml_filename"),   # usato solo per dedup
    }


async def get_archivio_fatture(
    anno: Optional[int] = Query(None),
    mese: Optional[int] = Query(None),
    fornitore_piva: Optional[str] = Query(None),
    fornitore_nome: Optional[str] = Query(None),
    stato: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(default=200, le=6000),
    skip: int = Query(default=0)
) -> Dict[str, Any]:
    """
    Archivio Fatture Ricevute — legge da ENTRAMBE le collection:
      - invoices (111 doc: fatture XML da Aruba PEC, schema inglese)
      - fatture_passive (73 doc: formato gestionale, schema italiano)
    I risultati vengono unificati, deduplicati per xml_filename e ordinati per data.
    Gli insert/upsert da upload XML restano su fatture_passive (invariati).
    """
    db = Database.get_db()

    # ── Costruisci filtri per `invoices` ─────────────────────────────────────
    q_inv: dict = {}
    if anno:
        q_inv["anno"] = anno
        if mese:
            mese_str = str(mese).zfill(2)
            last_day = calendar.monthrange(anno, mese)[1]
            q_inv["invoice_date"] = {
                "$gte": f"{anno}-{mese_str}-01",
                "$lte": f"{anno}-{mese_str}-{last_day:02d}"
            }
    if fornitore_piva:
        q_inv["supplier_vat"] = {"$regex": fornitore_piva.strip(), "$options": "i"}
    if fornitore_nome:
        q_inv["$or"] = [
            {"supplier_name": {"$regex": fornitore_nome.strip(), "$options": "i"}},
            {"cedente_denominazione": {"$regex": fornitore_nome.strip(), "$options": "i"}}
        ]
    if stato:
        q_inv["stato"] = stato
    if search:
        q_inv["$or"] = [
            {"invoice_number": {"$regex": search, "$options": "i"}},
            {"supplier_name": {"$regex": search, "$options": "i"}},
            {"supplier_vat": {"$regex": search, "$options": "i"}},
        ]

    # ── Costruisci filtri per `fatture_passive` ───────────────────────────────
    q_fp: dict = {}
    if anno:
        q_fp["anno"] = anno
        if mese:
            mese_str = str(mese).zfill(2)
            last_day = calendar.monthrange(anno, mese)[1]
            q_fp["data"] = {
                "$gte": f"{anno}-{mese_str}-01",
                "$lte": f"{anno}-{mese_str}-{last_day:02d}"
            }
    if fornitore_piva:
        q_fp["fornitore_piva"] = {"$regex": fornitore_piva.strip(), "$options": "i"}
    if fornitore_nome:
        q_fp["fornitore_denominazione"] = {"$regex": fornitore_nome.strip(), "$options": "i"}
    if stato:
        q_fp["stato"] = stato
    if search:
        q_fp["$or"] = [
            {"numero": {"$regex": search, "$options": "i"}},
            {"fornitore_denominazione": {"$regex": search, "$options": "i"}},
            {"fornitore_piva": {"$regex": search, "$options": "i"}},
        ]

    # ── Esegui le query in parallelo ─────────────────────────────────────────
    import asyncio as _asyncio
    docs_inv_raw, docs_fp_raw = await _asyncio.gather(
        db["invoices"].find(q_inv, {"_id": 0}).sort("invoice_date", -1).to_list(3000),
        db["fatture_passive"].find(q_fp, {"_id": 0}).sort("data", -1).to_list(3000),
    )

    # ── Normalizza ────────────────────────────────────────────────────────────
    normalized_inv = [_normalizza_da_invoices(d) for d in docs_inv_raw]
    normalized_fp  = [_normalizza_da_fatture_passive(d) for d in docs_fp_raw]

    # ── Deduplica: se stesso xml_filename in entrambe, preferisce invoices ───
    xml_filenames_in_inv = {
        d["_xml_filename"] for d in normalized_inv if d.get("_xml_filename")
    }
    normalized_fp = [
        d for d in normalized_fp
        if not (d.get("_xml_filename") and d["_xml_filename"] in xml_filenames_in_inv)
    ]

    # ── Unisci e ordina per data_documento decrescente ────────────────────────
    all_fatture = normalized_inv + normalized_fp
    all_fatture.sort(
        key=lambda f: f.get("data_documento") or "",
        reverse=True
    )

    # Rimuovi il campo interno di dedup prima di rispondere
    for f in all_fatture:
        f.pop("_xml_filename", None)

    # ── Arricchisci con metodo_pagamento DEL FORNITORE ────────────────────────
    # Legge l'anagrafica fornitori per P.IVA e popola `fornitore_metodo_pagamento`
    # Così il frontend può decidere di mostrare un solo bottone (Cassa o Banca)
    # quando il fornitore ha un metodo predefinito.
    pive = list({(f.get("fornitore_partita_iva") or "").strip() for f in all_fatture if f.get("fornitore_partita_iva")})
    if pive:
        fornitori_docs = await db["fornitori"].find(
            {"partita_iva": {"$in": pive}},
            {"_id": 0, "partita_iva": 1, "metodo_pagamento": 1, "metodo_pagamento_predefinito": 1}
        ).to_list(len(pive) + 10)
        map_metodo = {}
        for fdoc in fornitori_docs:
            piva = (fdoc.get("partita_iva") or "").strip()
            metodo = fdoc.get("metodo_pagamento_predefinito") or fdoc.get("metodo_pagamento") or ""
            if piva:
                map_metodo[piva] = metodo
        for f in all_fatture:
            piva = (f.get("fornitore_partita_iva") or "").strip()
            f["fornitore_metodo_pagamento"] = map_metodo.get(piva, "")

    total = len(all_fatture)

    # Applica paginazione
    paginated = all_fatture[skip: skip + limit]

    return {"fatture": paginated, "total": total, "limit": limit, "skip": skip}


async def view_fattura_assoinvoice(fattura_id: str) -> HTMLResponse:
    """
    Visualizza fattura nel formato ASSO Software (FoglioStileAssoSoftware.xsl).
    1. Cerca la fattura in `invoices` (poi fallback `indice_documenti`)
    2. Legge il file XML dal disco (gestisce .p7m estraendo l'XML interno)
    3. Applica la trasformazione XSLT con il foglio ASSO
    4. Restituisce l'HTML trasformato
    """
    import os
    from lxml import etree as LET

    db = Database.get_db()

    # ── Trova fattura ────────────────────────────────────────────────────────
    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        fattura = await db[COL_FATTURE_RICEVUTE].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        # Fallback: cerca per _id (MongoDB ObjectId) — usato nei link frontend legacy
        try:
            from bson import ObjectId
            fattura = await db["invoices"].find_one({"_id": ObjectId(fattura_id)})
            if fattura:
                fattura.pop("_id", None)
        except Exception:
            pass
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    xml_file_path = fattura.get("xml_file_path")
    xml_raw_content = fattura.get("xml_raw")  # stringa XML se già estratta

    xml_bytes: bytes | None = None

    # ── Prova a leggere XML dal disco ────────────────────────────────────────
    if xml_file_path and os.path.exists(xml_file_path):
        with open(xml_file_path, "rb") as f:
            raw = f.read()

        filename = xml_file_path.lower()
        if filename.endswith(".p7m"):
            # Estrai XML dall'envelope P7M cercando il tag <?xml
            xml_start = raw.find(b"<?xml")
            if xml_start == -1:
                xml_start = raw.find(b"<FatturaElettronica")
            if xml_start != -1:
                xml_bytes = raw[xml_start:]
                # Taglia il trailing padding/footer DER
                xml_end = xml_bytes.rfind(b">")
                if xml_end != -1:
                    xml_bytes = xml_bytes[: xml_end + 1]
            else:
                xml_bytes = raw
        else:
            xml_bytes = raw

    elif xml_raw_content:
        xml_bytes = xml_raw_content.encode("utf-8") if isinstance(xml_raw_content, str) else xml_raw_content

    # ── Applica ASSO XSL se abbiamo l'XML ────────────────────────────────────
    if xml_bytes:
        try:
            xsl_path = "/app/app/static/FoglioStileAssoSoftware.xsl"
            xsl_doc = LET.parse(xsl_path)
            transform = LET.XSLT(xsl_doc)

            # Parse XML (tolera namespace con p7m cleanup)
            xml_doc = LET.fromstring(xml_bytes)
            html_result = transform(xml_doc)
            html_str = LET.tostring(html_result, pretty_print=True, encoding="unicode")

            # Inietta un wrapper minimal se l'XSL non emette <html>
            if "<html" not in html_str[:200].lower():
                html_str = (
                    "<!DOCTYPE html><html><head>"
                    "<meta charset='UTF-8'>"
                    "<style>body{font-family:Arial,sans-serif;font-size:12px;margin:20px;}</style>"
                    "</head><body>" + html_str + "</body></html>"
                )

            return HTMLResponse(content=html_str)
        except Exception as xsl_err:
            logger.warning(f"Errore XSLT per {fattura_id}: {xsl_err} — fallback HTML generico")

    # ── Fallback: HTML generico se XML non disponibile ────────────────────────
    righe = await db[COL_DETTAGLIO_RIGHE].find({"fattura_id": fattura_id}, {"_id": 0}).to_list(1000)
    if not righe and fattura.get("linee"):
        righe = fattura.get("linee", [])
    html = generate_invoice_html(fattura, righe)
    return HTMLResponse(content=html)


async def download_pdf_allegato(fattura_id: str, allegato_id: str) -> Response:
    """Download PDF allegato fattura."""
    db = Database.get_db()
    
    allegato = await db[COL_ALLEGATI].find_one({"id": allegato_id, "fattura_id": fattura_id})
    if not allegato:
        raise HTTPException(status_code=404, detail="Allegato non trovato")
    
    try:
        pdf_data = base64.b64decode(allegato["base64_data"])
    except Exception:
        raise HTTPException(status_code=500, detail="Errore decodifica PDF")
    
    filename = allegato.get("nome_file", f"allegato_{allegato_id}.pdf")
    
    return Response(
        content=pdf_data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


async def get_fattura_dettaglio(fattura_id: str) -> Dict[str, Any]:
    """Dettaglio singola fattura con righe e allegati."""
    db = Database.get_db()
    
    fattura = await db[COL_FATTURE_RICEVUTE].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        try:
            from bson import ObjectId
            fattura = await db["invoices"].find_one({"_id": ObjectId(fattura_id)})
            if fattura:
                fattura.pop("_id", None)
        except Exception:
            pass
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    righe = await db[COL_DETTAGLIO_RIGHE].find({"fattura_id": fattura_id}, {"_id": 0}).to_list(1000)
    allegati = await db[COL_ALLEGATI].find({"fattura_id": fattura_id}, {"_id": 0, "base64_data": 0}).to_list(10)
    
    return {"fattura": fattura, "righe": righe, "allegati": allegati}


async def update_fattura(fattura_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Aggiorna una fattura."""
    db = Database.get_db()
    
    fattura = await db[COL_FATTURE_RICEVUTE].find_one({"id": fattura_id})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    update_fields = {}
    for field in ["pagato", "data_pagamento", "metodo_pagamento", "riconciliato", "note"]:
        if field in data:
            update_fields[field] = data[field]
    
    if update_fields:
        update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db[COL_FATTURE_RICEVUTE].update_one({"id": fattura_id}, {"$set": update_fields})
    
    return {"success": True, "updated": list(update_fields.keys())}


async def get_fornitori(
    search: Optional[str] = Query(None),
    con_fatture: bool = Query(default=False),
    limit: int = Query(default=100, le=500)
) -> Dict[str, Any]:
    """Lista fornitori con filtri."""
    db = Database.get_db()
    
    query = {}
    if search:
        query["$or"] = [
            {"ragione_sociale": {"$regex": search, "$options": "i"}},
            {"partita_iva": {"$regex": search, "$options": "i"}}
        ]
    if con_fatture:
        query["fatture_count"] = {"$gt": 0}
    
    fornitori = await db[COL_FORNITORI].find(query, {"_id": 0}).sort("ragione_sociale", 1).limit(limit).to_list(limit)
    return {"items": fornitori, "total": len(fornitori)}


async def get_statistiche(anno: Optional[int] = Query(None)) -> Dict[str, Any]:
    """
    Statistiche fatture ricevute — legge da `invoices` (collection principale).
    Tutti i 73 doc di fatture_passive sono già presenti in invoices (stesso xml_filename),
    quindi invoices è la fonte unica per evitare duplicati.
    """
    db = Database.get_db()

    # Filtro per anno (invoices ha campo `anno` numerico e `invoice_date` ISO)
    query: dict = {}
    if anno:
        query["anno"] = anno

    import asyncio as _asyncio
    pipeline_inv = [
        {"$match": query},
        {"$group": {
            "_id": None,
            "totale_fatture": {"$sum": 1},
            "importo_totale": {"$sum": {"$toDouble": {"$ifNull": ["$total_amount", 0]}}},
            "fornitori_unici": {"$addToSet": "$supplier_vat"},
            "pagate": {"$sum": {"$cond": [
                {"$in": ["$stato", ["pagata", "paid"]]}, 1, 0
            ]}},
            "importo_pagato": {"$sum": {"$cond": [
                {"$in": ["$stato", ["pagata", "paid"]]},
                {"$toDouble": {"$ifNull": ["$total_amount", 0]}},
                0
            ]}},
        }}
    ]
    result = await db["invoices"].aggregate(pipeline_inv).to_list(1)
    stats = result[0] if result else {}
    stats.pop("_id", None)

    totale = stats.get("totale_fatture", 0)
    importo = round(stats.get("importo_totale", 0), 2)
    fornitori = len(stats.get("fornitori_unici", []))
    pagate = stats.get("pagate", 0)
    importo_pagato = round(stats.get("importo_pagato", 0), 2)
    da_pagare = totale - pagate
    importo_da_pagare = round(importo - importo_pagato, 2)

    return {
        "totale_fatture": totale,
        "importo_totale": importo,
        "totale_importo": importo,
        "pagate": pagate,
        "importo_pagato": importo_pagato,
        "da_pagare": da_pagare,
        "importo_da_pagare": importo_da_pagare,
        "fornitori_unici": fornitori,
        "fatture_anomale": 0,
        "anno": anno,
    }
