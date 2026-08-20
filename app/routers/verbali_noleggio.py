"""
Router Verbali Noleggio - Scarica verbali dalla posta e li associa alle fatture.

Cerca nelle cartelle email i verbali (pattern Bxxxxxxxxxx) e li associa
alle righe corrispondenti nelle fatture noleggio.

Endpoint rimossi il 14/07/2026 (piano residuo op.10, zero chiamanti verificati):
associa-fatture, cartelle-verbali, classifica-verbali-posta, operazioni-sospese,
riclassifica-verbale, riconcilia, risolvi-sospeso, scansiona-fatture,
scarica-tutti, stats, tutti-verbali, verbale/{numero_verbale}, verbali,
verbali-attesa-fattura, verbali-privati, verifica-nuove-fatture — codice
conservato nella cronologia git.
"""
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile
from typing import Dict, Any
import base64
import hashlib
from datetime import datetime, timezone

from app.database import Database
from app.utils.error_handler import handle_errors
from app.utils.dependencies import get_current_admin_user

router = APIRouter(prefix="/api/verbali-noleggio", tags=["Verbali Noleggio"])

# Collection
COLLECTION_VERBALI = "verbali_noleggio"


async def _find_verbale(db, numero_verbale: str):
    query = {"$or": [
        {"numero_verbale": numero_verbale}, {"numero_verbale_old": numero_verbale},
        {"numero_verbale": numero_verbale.upper()}, {"numero_verbale_old": numero_verbale.upper()},
    ]}
    for collection in ("verbali_noleggio", "verbali_noleggio_completi"):
        item = await db[collection].find_one(query, {"_id": 0})
        if item:
            return collection, item
    return None, None


@router.post("/associa-pdf/{numero_verbale:path}")
@handle_errors
async def associa_pdf_verbale(
    numero_verbale: str,
    file: UploadFile = File(...),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Conserva e collega un PDF originale al verbale, con hash e provenienza."""
    from app.utils.upload_validation import verifica_pdf_reale
    from app.services.verbali_document_import import process_verbale_document, _extract_text, _extract_numero

    db = Database.get_db()
    collection, verbale = await _find_verbale(db, numero_verbale)
    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")
    content = await file.read()
    filename = file.filename or f"verbale_{numero_verbale}.pdf"
    verifica_pdf_reale(content, filename)
    extracted_number = _extract_numero(f"{filename}\n{_extract_text(content)}")
    accepted = {str(verbale.get("numero_verbale") or "").upper(), str(verbale.get("numero_verbale_old") or "").upper()}
    if extracted_number and extracted_number.upper() not in accepted:
        raise HTTPException(status_code=409, detail=f"Il PDF indica il verbale {extracted_number}, non {numero_verbale}")
    digest = hashlib.sha256(content).hexdigest()
    existing = await db["documents_inbox"].find_one({"file_hash": digest}, {"_id": 0, "id": 1})
    doc_id = (existing or {}).get("id") or f"verbale_pdf_{digest[:24]}"
    now = datetime.now(timezone.utc).isoformat()
    if not existing:
        await db["documents_inbox"].insert_one({
            "id": doc_id, "filename": filename, "pdf_data": base64.b64encode(content).decode("ascii"),
            "file_hash": digest, "sha256": digest, "size": len(content), "category": "verbale_codice_strada",
            "tipo_documento": "verbale", "evidence_role": "obbligazione", "source": "upload_dettaglio_verbale",
            "numero_verbale": verbale.get("numero_verbale"), "verbale_id": verbale.get("id"),
            "created_at": now, "updated_at": now, "processed": False, "status": "da_elaborare",
        })
    await db[collection].update_one(
        {"id": verbale.get("id")} if verbale.get("id") else {"numero_verbale": verbale.get("numero_verbale")},
        {"$addToSet": {"document_ids": doc_id}, "$set": {"updated_at": now}},
    )
    outcome = await process_verbale_document(db, document_id=doc_id, content=content,
        filename=filename, source="upload_dettaglio_verbale",
        parsed_metadata={"numero_verbale": verbale.get("numero_verbale")})
    return {"success": True, "duplicate": bool(existing), "document_id": doc_id, "elaborazione": outcome}


@router.post("/ricalcola-pdf/{numero_verbale:path}")
@handle_errors
async def ricalcola_verbale_da_pdf(
    numero_verbale: str,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Rilegge i PDF gia collegati e corregge soltanto conflitti documentali certi."""
    from app.services.verbali_pdf_service import collect_verbale_pdfs
    from app.services.verbali_document_import import process_verbale_document
    db = Database.get_db()
    _collection, verbale = await _find_verbale(db, numero_verbale)
    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")
    pdfs = await collect_verbale_pdfs(db, verbale, include_content=True)
    results = []
    for index, pdf in enumerate(pdfs):
        encoded = pdf.get("content_base64")
        if not encoded or pdf.get("tipo") == "quietanza":
            continue
        content = base64.b64decode(encoded)
        doc_id = pdf.get("document_id") or verbale.get("source_document_id") or f"ricalcolo_{hashlib.sha256(content).hexdigest()[:24]}"
        results.append(await process_verbale_document(db, document_id=doc_id, content=content,
            filename=pdf.get("filename") or f"verbale_{index + 1}.pdf", source="ricalcolo_pdf_collegato",
            parsed_metadata={"numero_verbale": verbale.get("numero_verbale")}))
    refreshed = await db["verbali_noleggio"].find_one({"numero_verbale": verbale.get("numero_verbale")}, {"_id": 0}) or verbale
    return {"success": True, "pdf_elaborati": len(results), "importo": refreshed.get("importo"), "risultati": results}


@router.get("/pdf/{numero_verbale:path}")
@handle_errors
async def get_pdf_verbale(numero_verbale: str, indice: int = 0) -> Dict[str, Any]:
    """
    Ottiene il PDF del verbale in base64.
    indice: quale PDF se ce ne sono più di uno (default primo)
    """
    db = Database.get_db()

    verbale = await db[COLLECTION_VERBALI].find_one(
        {"$or": [
            {"numero_verbale": numero_verbale},
            {"numero_verbale_old": numero_verbale},
        ]},
        {"_id": 0}
    )

    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")

    from app.services.verbali_pdf_service import collect_verbale_pdfs

    pdfs = await collect_verbale_pdfs(db, verbale)
    pdf = next((item for item in pdfs if item.get("indice") == indice), None)
    if pdf and pdf.get("content_base64"):
        return {
            "numero_verbale": verbale.get("numero_verbale", numero_verbale),
            "filename": pdf.get("filename"),
            "content_base64": pdf.get("content_base64"),
            "size": pdf.get("size") or 0,
            "document_id": pdf.get("document_id"),
        }

    raise HTTPException(status_code=404, detail="PDF non trovato")


@router.get("/verbali-completi")
@handle_errors
async def get_verbali_completi(
    anno: int = None,
    targa: str = None,
    stato_pagamento: str = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Restituisce i verbali con tutte le associazioni.

    Filtri opzionali:
    - anno: Anno del verbale
    - targa: Filtra per targa veicolo
    - stato_pagamento: da_verificare, pagato, sospeso
    """
    # ATTENZIONE: import locale con nome diverso dalla costante di modulo
    # COLLECTION_VERBALI (riga 23, = "verbali_noleggio") — questo endpoint
    # legge invece "verbali_noleggio_completi" (alimentata dalle fatture,
    # vedi app/services/verbali_service.py). Rinominato per non shadoware
    # in modo fuorviante lo stesso identificatore con due valori diversi
    # (piano residuo op.15, indagine 14/07/2026 — nessun cambio di
    # comportamento, solo leggibilità).
    from app.services.verbali_service import COLLECTION_VERBALI as COLLECTION_VERBALI_COMPLETI
    db = Database.get_db()

    query = {}
    if anno:
        query["anno"] = str(anno)
    if targa:
        query["targa"] = targa.upper()
    if stato_pagamento:
        query["stato_pagamento"] = stato_pagamento

    cursor = db[COLLECTION_VERBALI_COMPLETI].find(query, {"_id": 0}).sort("data_fattura", -1).limit(limit)
    verbali = await cursor.to_list(limit)

    # Statistiche
    totale = await db[COLLECTION_VERBALI_COMPLETI].count_documents(query if query else {})
    pagati = await db[COLLECTION_VERBALI_COMPLETI].count_documents({"stato_pagamento": "pagato"})
    sospesi = await db[COLLECTION_VERBALI_COMPLETI].count_documents({"stato_pagamento": "sospeso"})
    da_verificare = await db[COLLECTION_VERBALI_COMPLETI].count_documents({"stato_pagamento": "da_verificare"})

    return {
        "verbali": verbali,
        "count": len(verbali),
        "totale": totale,
        "statistiche": {
            "pagati": pagati,
            "sospesi": sospesi,
            "da_verificare": da_verificare
        }
    }


# NOTA: esiste un secondo /dettaglio/{numero_verbale} in verbali_noleggio_api.py
# (stesso prefisso /api/verbali-noleggio, registrato dopo questo). Non è duplicato
# morto: questo usa un path-param str che non matcha "/", quindi i numeri verbale
# CON slash (es. "S/2259") cadono sull'altra route che usa {numero_verbale:path}.
@router.get("/dettaglio/{numero_verbale}")
@handle_errors
async def get_dettaglio_verbale(numero_verbale: str) -> Dict[str, Any]:
    """
    Restituisce il dettaglio completo di un verbale con tutti i documenti associati.
    """
    # Vedi nota in get_verbali_completi sopra: nome rinominato per non
    # shadoware COLLECTION_VERBALI di modulo con un valore diverso.
    from app.services.verbali_service import COLLECTION_VERBALI as COLLECTION_VERBALI_COMPLETI
    db = Database.get_db()

    # Cerca nel nuovo sistema (incluso vecchio numero)
    verbale = await db[COLLECTION_VERBALI_COMPLETI].find_one(
        {"$or": [
            {"numero_verbale": numero_verbale},
            {"numero_verbale_old": numero_verbale},
            {"numero_verbale": numero_verbale.upper()},
            {"numero_verbale_old": numero_verbale.upper()},
        ]},
        {"_id": 0}
    )

    if not verbale:
        # Cerca nel vecchio sistema
        verbale = await db["verbali_noleggio"].find_one(
            {"$or": [
                {"numero_verbale": numero_verbale},
                {"numero_verbale_old": numero_verbale},
            ]},
            {"_id": 0}
        )

    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")

    # Carica info aggiuntive
    risultato = {**verbale}

    # Carica info veicolo se presente
    if verbale.get("targa"):
        veicolo = await db["veicoli_noleggio"].find_one(
            {"targa": verbale["targa"]},
            {"_id": 0}
        )
        risultato["veicolo_info"] = veicolo

    # Carica fattura se presente
    if verbale.get("fattura_id"):
        fattura = await db["invoices"].find_one(
            {"id": verbale["fattura_id"]},
            {"_id": 0, "linee": 0}  # Escludi linee per non appesantire
        )
        risultato["fattura_info"] = fattura

    # Carica movimento bancario se riconciliato
    if verbale.get("movimento_banca_id"):
        movimento = await db["prima_nota_banca"].find_one(
            {"id": verbale["movimento_banca_id"]},
            {"_id": 0}
        )
        risultato["movimento_info"] = movimento

    from app.services.verbali_pdf_service import collect_verbale_pdfs, pdf_metadata
    risultato["pdf_disponibili"] = pdf_metadata(
        await collect_verbale_pdfs(db, verbale, include_content=False)
    )

    # Non inviare dati binari pesanti nel response JSON
    risultato.pop("pdf_data", None)
    risultato.pop("quietanza_pdf", None)

    return risultato


# NB: l'endpoint POST /unifica-verbali che era qui è stato rimosso: il corpo
# del loop era vuoto (endpoint tronco che rispondeva sempre null senza fare
# nulla — bug #16 audit memoria/endpoints/README.md), zero chiamanti.
