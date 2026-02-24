"""
Router per gestione documenti non associati.
Permette di visualizzare e associare manualmente i documenti.
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid
import re
import logging
import base64

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documenti-non-associati", tags=["Documenti Non Associati"])


def extract_pdf_from_p7s(p7s_data: bytes) -> Optional[bytes]:
    """
    Estrae il PDF contenuto in un file P7S/P7M firmato digitalmente.
    Cerca i marker PDF nel contenuto binario.
    """
    try:
        # Cerca marker PDF start e end
        pdf_start = p7s_data.find(b'%PDF-')
        if pdf_start == -1:
            return None
        
        # Cerca l'ultimo %%EOF
        pdf_end = p7s_data.rfind(b'%%EOF')
        if pdf_end == -1:
            # Prova con altri marker di fine
            pdf_end = p7s_data.rfind(b'endstream')
            if pdf_end == -1:
                pdf_end = len(p7s_data)
            else:
                # Trova la fine corretta dopo endstream
                pdf_end = p7s_data.find(b'%%EOF', pdf_end)
                if pdf_end == -1:
                    pdf_end = len(p7s_data)
        else:
            pdf_end += 5  # Includi %%EOF
        
        # Estrai il PDF
        pdf_content = p7s_data[pdf_start:pdf_end]
        
        # Verifica che sia un PDF valido
        if pdf_content[:4] == b'%PDF':
            return pdf_content
        
        return None
    except Exception as e:
        logger.error(f"Errore estrazione PDF da P7S: {e}")
        return None


# Collezioni target per associazione
TARGET_COLLECTIONS = {
    "fatture": {"collection": "invoices", "label": "Fatture Ricevute"},
    "f24": {"collection": "f24_commercialista", "label": "F24"},
    "cedolini": {"collection": "payslips", "label": "Cedolini/Buste Paga"},
    "verbali": {"collection": "verbali_multe", "label": "Verbali e Multe"},
    "cartelle": {"collection": "cartelle_esattoriali", "label": "Cartelle Esattoriali"},
    "estratti": {"collection": "estratto_conto_movimenti", "label": "Estratti Conto"},
    "bonifici": {"collection": "bonifici", "label": "Bonifici"},
    "quietanze": {"collection": "quietanze", "label": "Quietanze"},
    "contratti": {"collection": "contratti", "label": "Contratti"},
    "certificati": {"collection": "certificati_medici", "label": "Certificati Medici"},
}


@router.get("/lista")
async def lista_documenti_non_associati(
    limit: int = Query(default=50, le=200),
    skip: int = Query(default=0),
    categoria: str = Query(default=None),
    search: str = Query(default=None)
) -> Dict[str, Any]:
    """
    Lista tutti i documenti non associati con proposta intelligente.
    IMPORTANTE: Esclude automaticamente i documenti già associati.
    """
    db = Database.get_db()
    
    # Base query: escludere documenti già associati
    base_filter = {"$or": [{"associato": {"$exists": False}}, {"associato": False}]}
    
    # Costruisci query con filtri aggiuntivi
    conditions = [base_filter]
    
    if categoria:
        conditions.append({"category": categoria})
    
    if search:
        conditions.append({
            "$or": [
                {"filename": {"$regex": search, "$options": "i"}},
                {"email_subject": {"$regex": search, "$options": "i"}}
            ]
        })
    
    # Se ci sono più condizioni, usa $and
    query = {"$and": conditions} if len(conditions) > 1 else base_filter
    
    # Conta totali
    total = await db["documenti_non_associati"].count_documents(query)
    
    # Recupera documenti - usa aggregation per allow_disk_use
    pipeline = [
        {"$match": query},
        {"$project": {"_id": 0, "pdf_data": 0}},
        {"$sort": {"downloaded_at": -1}},
        {"$skip": skip},
        {"$limit": limit}
    ]
    
    documenti = []
    async for doc in db["documenti_non_associati"].aggregate(pipeline, allowDiskUse=True):
        # Proposta intelligente
        proposta = await genera_proposta_associazione(db, doc)
        doc["proposta"] = proposta
        documenti.append(doc)
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "documenti": documenti
    }


async def genera_proposta_associazione(db, doc: Dict) -> Dict[str, Any]:
    """
    Genera una proposta intelligente per l'associazione del documento.
    Analizza filename, subject email e contenuto per suggerire dove associare.
    """
    filename = doc.get("filename", "").lower()
    subject = doc.get("email_subject", "").lower()
    text = f"{filename} {subject}"
    
    proposta = {
        "tipo_suggerito": None,
        "collezione_suggerita": None,
        "anno_suggerito": None,
        "mese_suggerito": None,
        "entita_suggerita": None,  # Nome azienda, dipendente, etc.
        "match_esistenti": [],  # Record esistenti che potrebbero corrispondere
        "campi_proposti": {}
    }
    
    # Estrai anno dal testo
    anno_match = re.search(r'20(1[5-9]|2[0-9])', text)
    if anno_match:
        proposta["anno_suggerito"] = int(f"20{anno_match.group(1)}")
    
    # Estrai mese
    mesi = {
        "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
        "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
        "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12
    }
    for mese_nome, mese_num in mesi.items():
        if mese_nome in text:
            proposta["mese_suggerito"] = mese_num
            break
    
    # Pattern per tipo documento
    if any(p in text for p in ["verbale", "multa", "sanzione", "infrazione", "polizia"]):
        proposta["tipo_suggerito"] = "verbali"
        proposta["collezione_suggerita"] = "verbali_multe"
        
        # Cerca targa auto
        targa_match = re.search(r'([A-Z]{2}\s*\d{3}\s*[A-Z]{2})', text.upper())
        if targa_match:
            proposta["campi_proposti"]["targa"] = targa_match.group(1).replace(" ", "")
        
        # Cerca importo
        importo_match = re.search(r'(?:€|euro)\s*(\d+[.,]\d{2})', text)
        if importo_match:
            proposta["campi_proposti"]["importo"] = float(importo_match.group(1).replace(",", "."))
    
    elif any(p in text for p in ["cartella", "esattoriale", "riscossione", "ader", "equitalia"]):
        proposta["tipo_suggerito"] = "cartelle"
        proposta["collezione_suggerita"] = "cartelle_esattoriali"
    
    elif any(p in text for p in ["f24", "tribut", "agenzia entrate", "iva", "ires", "irpef"]):
        proposta["tipo_suggerito"] = "f24"
        proposta["collezione_suggerita"] = "f24_commercialista"
    
    elif any(p in text for p in ["busta paga", "cedolino", "stipendio", "retribuzione"]):
        proposta["tipo_suggerito"] = "cedolini"
        proposta["collezione_suggerita"] = "payslips"
    
    elif any(p in text for p in ["fattura", "invoice", "ft_", "ft-"]):
        proposta["tipo_suggerito"] = "fatture"
        proposta["collezione_suggerita"] = "invoices"
    
    # Cerca entità (nome azienda, persona)
    # Pattern per nomi di aziende comuni
    azienda_patterns = [
        r'(ceraldi\s*group)', r'(s\.r\.l\.)', r'(s\.p\.a\.)',
        r'([A-Z][a-z]+\s+[A-Z][a-z]+)',  # Nome Cognome
    ]
    for pattern in azienda_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            proposta["entita_suggerita"] = match.group(1).strip().title()
            break
    
    # Cerca match esistenti nel database
    if proposta["tipo_suggerito"]:
        coll = proposta["collezione_suggerita"]
        query = {}
        
        if proposta["anno_suggerito"]:
            query["anno"] = proposta["anno_suggerito"]
        
        if coll and query:
            try:
                matches = await db[coll].find(query, {"_id": 0, "id": 1, "anno": 1, "mese": 1}).limit(5).to_list(5)
                proposta["match_esistenti"] = matches
            except Exception:
                pass
    
    return proposta


@router.post("/associa")
async def associa_documento(
    documento_id: str = Body(...),
    collezione_target: str = Body(...),
    campi_associazione: Dict[str, Any] = Body(default={}),
    crea_nuovo: bool = Body(default=False),
    record_esistente_id: str = Body(default=None)
) -> Dict[str, Any]:
    """
    Associa un documento non associato a una collezione target.
    
    Se crea_nuovo=True, crea un nuovo record nella collezione target.
    Se record_esistente_id è fornito, aggiunge il PDF al record esistente.
    """
    db = Database.get_db()
    
    # Recupera documento
    doc = await db["documenti_non_associati"].find_one({"id": documento_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    pdf_data = doc.get("pdf_data")
    if not pdf_data:
        raise HTTPException(status_code=400, detail="Documento senza PDF")
    
    # Verifica collezione target
    if collezione_target not in [t["collection"] for t in TARGET_COLLECTIONS.values()]:
        # Crea nuova collezione se richiesto
        logger.info(f"Creazione nuova collezione: {collezione_target}")
    
    if crea_nuovo:
        # Crea nuovo record
        nuovo_id = str(uuid.uuid4())
        nuovo_record = {
            "id": nuovo_id,
            "pdf_data": pdf_data,
            "pdf_filename": doc.get("filename"),
            "pdf_hash": doc.get("file_hash"),
            "source": "associazione_manuale",
            "documento_originale_id": documento_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **campi_associazione
        }
        
        await db[collezione_target].insert_one(nuovo_record)
        
        # Marca documento come associato
        await db["documenti_non_associati"].update_one(
            {"id": documento_id},
            {"$set": {
                "associato": True,
                "associato_a": collezione_target,
                "associato_id": nuovo_id,
                "associato_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        return {
            "success": True,
            "azione": "creato_nuovo",
            "collezione": collezione_target,
            "record_id": nuovo_id
        }
    
    elif record_esistente_id:
        # Aggiunge PDF a record esistente
        result = await db[collezione_target].update_one(
            {"id": record_esistente_id},
            {"$set": {
                "pdf_data": pdf_data,
                "pdf_filename": doc.get("filename"),
                "pdf_hash": doc.get("file_hash"),
                "pdf_updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Record target non trovato")
        
        # Marca documento come associato
        await db["documenti_non_associati"].update_one(
            {"id": documento_id},
            {"$set": {
                "associato": True,
                "associato_a": collezione_target,
                "associato_id": record_esistente_id,
                "associato_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        return {
            "success": True,
            "azione": "aggiunto_a_esistente",
            "collezione": collezione_target,
            "record_id": record_esistente_id
        }
    
    else:
        raise HTTPException(status_code=400, detail="Specificare crea_nuovo=True o record_esistente_id")


@router.get("/statistiche")
async def statistiche_non_associati() -> Dict[str, Any]:
    """
    Statistiche sui documenti non associati.
    """
    db = Database.get_db()
    
    pipeline = [
        {"$group": {
            "_id": "$category",
            "count": {"$sum": 1},
            "associati": {"$sum": {"$cond": ["$associato", 1, 0]}}
        }},
        {"$sort": {"count": -1}}
    ]
    
    stats = {"totale": 0, "associati": 0, "per_categoria": {}}
    
    async for doc in db["documenti_non_associati"].aggregate(pipeline):
        cat = doc["_id"] or "altro"
        stats["per_categoria"][cat] = {
            "totale": doc["count"],
            "associati": doc["associati"],
            "da_associare": doc["count"] - doc["associati"]
        }
        stats["totale"] += doc["count"]
        stats["associati"] += doc["associati"]
    
    stats["da_associare"] = stats["totale"] - stats["associati"]
    
    return stats


@router.get("/collezioni-disponibili")
async def lista_collezioni_disponibili() -> List[Dict[str, str]]:
    """Lista collezioni disponibili per l'associazione."""
    return [
        {"value": info["collection"], "label": info["label"]}
        for key, info in TARGET_COLLECTIONS.items()
    ]


@router.get("/pdf/{documento_id}")
async def visualizza_pdf_documento(documento_id: str):
    """
    Restituisce il file del documento per la visualizzazione.
    Supporta PDF, immagini (PNG, JPG, etc.), e file P7S firmati.
    """
    from fastapi.responses import Response
    import base64
    
    db = Database.get_db()
    
    doc = await db["documenti_non_associati"].find_one(
        {"id": documento_id},
        {"_id": 0, "pdf_data": 1, "filename": 1}
    )
    
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    pdf_data = doc.get("pdf_data")
    if not pdf_data:
        raise HTTPException(status_code=404, detail="File non disponibile")
    
    # Decodifica se base64
    if isinstance(pdf_data, str):
        try:
            file_bytes = base64.b64decode(pdf_data)
        except Exception:
            file_bytes = pdf_data.encode()
    else:
        file_bytes = pdf_data
    
    filename = doc.get("filename", "documento.pdf")
    # Sanitize filename - remove newlines and other illegal header characters
    filename = filename.replace('\r', '').replace('\n', ' ').strip()
    # Also remove any other control characters
    filename = ''.join(c for c in filename if ord(c) >= 32 or c in '\t')
    filename_lower = filename.lower()
    
    # Determina il media type in base all'estensione
    media_type_map = {
        '.pdf': 'application/pdf',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.bmp': 'image/bmp',
        '.svg': 'image/svg+xml',
        '.xml': 'application/xml',
        '.txt': 'text/plain',
        '.csv': 'text/csv',
        '.html': 'text/html',
    }
    
    # Trova l'estensione
    ext = ''
    for e in media_type_map.keys():
        if filename_lower.endswith(e):
            ext = e
            break
    
    # Se è un file P7S/P7M firmato, estrai il PDF interno
    if filename_lower.endswith(('.p7s', '.p7m', '.p7c')):
        extracted_pdf = extract_pdf_from_p7s(file_bytes)
        if extracted_pdf:
            file_bytes = extracted_pdf
            filename = filename.rsplit('.', 1)[0]
            if not filename.lower().endswith('.pdf'):
                filename += '.pdf'
            ext = '.pdf'
        else:
            raise HTTPException(
                status_code=422, 
                detail="Impossibile estrarre il PDF dal file firmato digitalmente."
            )
    
    # Se è un PDF, verifica che sia valido
    if ext == '.pdf' or filename_lower.endswith('.pdf'):
        if file_bytes[:4] != b'%PDF':
            # Potrebbe essere un file firmato non riconosciuto
            extracted = extract_pdf_from_p7s(file_bytes)
            if extracted:
                file_bytes = extracted
            else:
                raise HTTPException(
                    status_code=422,
                    detail="Il file non è un PDF valido"
                )
        media_type = 'application/pdf'
    elif ext:
        media_type = media_type_map[ext]
    else:
        # Rileva dal magic number
        if file_bytes[:4] == b'%PDF':
            media_type = 'application/pdf'
        elif file_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            media_type = 'image/png'
        elif file_bytes[:2] == b'\xff\xd8':
            media_type = 'image/jpeg'
        elif file_bytes[:6] in (b'GIF87a', b'GIF89a'):
            media_type = 'image/gif'
        else:
            media_type = 'application/octet-stream'
    
    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-cache"
        }
    )


@router.delete("/{documento_id}")
async def elimina_documento(documento_id: str) -> Dict[str, Any]:
    """Elimina un documento non associato."""
    db = Database.get_db()
    
    result = await db["documenti_non_associati"].delete_one({"id": documento_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    return {"success": True, "deleted": True}
