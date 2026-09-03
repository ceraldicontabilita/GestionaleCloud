"""
Router per Download Completo Email e Gestione Documenti Non Associati
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Body, Depends
from app.utils.dependencies import get_current_admin_user
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

from app.database import Database
from app.services.email_full_download import (
    EmailFullDownloader,
    get_documenti_non_associati,
    associate_pdf_to_document,
    smart_auto_associate,
    smart_auto_associate_v2,
    populate_payslips_pdf_data,
    get_documents_inbox_stats,
    sync_filesystem_pdfs_to_db,
    associate_f24_from_filesystem,
    process_cedolini_to_prima_nota,
    CATEGORY_COLLECTIONS
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Email Download"])

# Stato del download in corso
download_status = {
    "in_progress": False,
    "started_at": None,
    "stats": None,
    "error": None
}


@router.get("/status")
async def get_download_status() -> Dict[str, Any]:
    """Ottiene lo stato del download in corso."""
    return download_status


@router.post("/start-full-download")
async def start_full_download(
    background_tasks: BackgroundTasks,
    days_back: int = Query(default=1, description="Giorni indietro da scaricare (default 1 giorno)"),
    folder: str = Query(default="INBOX", description="Cartella IMAP")
) -> Dict[str, Any]:
    """
    Avvia il download completo di tutte le email con PDF.
    Il processo viene eseguito in background.
    """
    global download_status

    if download_status["in_progress"]:
        raise HTTPException(status_code=400, detail="Download già in corso")

    download_status["in_progress"] = True
    download_status["started_at"] = datetime.now(timezone.utc).isoformat()
    download_status["stats"] = None
    download_status["error"] = None

    async def run_download():
        global download_status
        try:
            db = Database.get_db()
            downloader = EmailFullDownloader(db)
            result = await downloader.download_all_emails(
                folder=folder,
                days_back=days_back
            )
            download_status["stats"] = result.get("stats")
            if not result.get("success"):
                download_status["error"] = result.get("error")
        except Exception as e:
            logger.error(f"Errore download: {e}")
            download_status["error"] = str(e)
        finally:
            download_status["in_progress"] = False

    background_tasks.add_task(run_download)

    return {
        "message": "Download avviato in background",
        "days_back": days_back,
        "folder": folder
    }


@router.post("/download-single-day")
async def download_single_day(
    date: str = Query(..., description="Data nel formato YYYY-MM-DD")
) -> Dict[str, Any]:
    """
    Scarica email di un singolo giorno.
    """
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato data non valido. Usa YYYY-MM-DD")

    db = Database.get_db()
    downloader = EmailFullDownloader(db)
    result = await downloader.download_single_day(target_date)

    return result


@router.get("/documenti-non-associati")
async def list_documenti_non_associati(
    category: Optional[str] = Query(default=None, description="Filtra per categoria"),
    limit: int = Query(default=100, le=500)
) -> Dict[str, Any]:
    """
    Lista i documenti PDF scaricati ma non ancora associati.
    """
    db = Database.get_db()
    docs = await get_documenti_non_associati(db, category, limit)

    return {
        "count": len(docs),
        "documenti": docs
    }


@router.post("/associa-documento")
async def associa_documento(
    pdf_id: str,
    source_collection: str,
    target_document_id: str,
    target_collection: str
) -> Dict[str, Any]:
    """
    Associa manualmente un PDF a un documento esistente.
    """
    db = Database.get_db()

    success = await associate_pdf_to_document(
        db,
        pdf_id,
        source_collection,
        target_document_id,
        target_collection
    )

    if success:
        return {"success": True, "message": "PDF associato con successo"}
    else:
        raise HTTPException(status_code=400, detail="Associazione fallita")


@router.post("/auto-associa")
async def auto_associa_documenti() -> Dict[str, Any]:
    """
    Tenta di associare automaticamente i PDF ai documenti esistenti
    usando logica intelligente.
    """
    db = Database.get_db()
    stats = await smart_auto_associate(db)

    return {
        "success": True,
        "stats": stats
    }


@router.post("/auto-associa-v2")
async def auto_associa_documenti_v2() -> Dict[str, Any]:
    """
    Versione migliorata dell'auto-associazione che:
    1. Popola pdf_data nei payslips dal filesystem
    2. Associa documenti di documents_inbox
    3. Gestisce fatture, F24 e buste paga
    """
    db = Database.get_db()
    stats = await smart_auto_associate_v2(db)

    return {
        "success": True,
        "message": "Auto-associazione v2 completata",
        "stats": stats
    }


@router.post("/popola-pdf-payslips")
async def popola_pdf_payslips() -> Dict[str, Any]:
    """
    Popola il campo pdf_data in tutti i payslips che hanno filepath
    ma non hanno ancora pdf_data.
    """
    db = Database.get_db()
    stats = await populate_payslips_pdf_data(db)

    return {
        "success": True,
        "message": "Popolazione PDF payslips completata",
        "stats": stats
    }


@router.get("/documents-inbox-stats")
async def get_inbox_stats() -> Dict[str, Any]:
    """
    Statistiche dettagliate sulla collezione documents_inbox.
    """
    db = Database.get_db()
    stats = await get_documents_inbox_stats(db)

    return stats


@router.post("/sync-filesystem")
async def sync_filesystem() -> Dict[str, Any]:
    """
    Sincronizza i PDF dal filesystem con documents_inbox.
    Scansiona /app/documents e aggiunge/aggiorna i record nel database.
    """
    db = Database.get_db()
    stats = await sync_filesystem_pdfs_to_db(db)

    return {
        "success": True,
        "message": "Sincronizzazione filesystem completata",
        "stats": stats
    }


@router.post("/associa-f24-filesystem")
async def associa_f24_filesystem() -> Dict[str, Any]:
    """
    Associa i PDF F24 dal filesystem ai record f24_commercialista.
    """
    db = Database.get_db()
    stats = await associate_f24_from_filesystem(db)

    return {
        "success": True,
        "message": "Associazione F24 completata",
        "stats": stats
    }


@router.post("/processa-cedolini")
async def processa_cedolini() -> Dict[str, Any]:
    """
    Processa i cedolini scaricati ed estrae i dati per prima_nota_salari.
    Legge i PDF, estrae nomi dipendenti, importi netti/lordi, e crea record automaticamente.
    """
    db = Database.get_db()
    stats = await process_cedolini_to_prima_nota(db)

    return {
        "success": True,
        "message": "Processamento cedolini completato",
        "stats": stats
    }



@router.post("/processa-pipeline")
async def processa_pipeline_completa() -> Dict[str, Any]:
    """
    Esegue il pipeline completo di processamento post-download.
    Processa: F24, Cedolini, Verbali, Quietanze.
    Collega verbali a veicoli/dipendenti, crea trattenute busta paga.
    """
    from app.services.post_download_pipeline import esegui_pipeline_completa
    db = Database.get_db()
    risultati = await esegui_pipeline_completa(db)
    return {
        "success": True,
        "message": "Pipeline post-download completata",
        "risultati": risultati
    }


@router.post("/parse-verbali-llm")
async def parse_verbali_con_llm(
    limit: int = Query(default=50, description="Max verbali da processare")
) -> Dict[str, Any]:
    """
    Parsing LLM dei verbali senza targa.
    Estrae: targa, importo, data, ente emittente dal PDF.
    Collega automaticamente a veicolo e dipendente (driver).
    """
    from app.services.llm_document_parser import batch_parse_verbali
    db = Database.get_db()
    stats = await batch_parse_verbali(db, limit=limit)
    return {"success": True, "stats": stats}


@router.post("/parse-f24-llm")
async def parse_f24_con_llm(
    limit: int = Query(default=50, description="Max F24 da processare")
) -> Dict[str, Any]:
    """
    Parsing LLM degli F24 PDF.
    Estrae: codici tributo, periodi, importi, sezioni.
    Salva in f24_commercialista per riconciliazione con banca.
    """
    from app.services.llm_document_parser import batch_parse_f24
    db = Database.get_db()
    stats = await batch_parse_f24(db, limit=limit)
    return {"success": True, "stats": stats}



@router.post("/riconcilia-verbali")
async def riconcilia_verbali_banca() -> Dict[str, Any]:
    """
    Riconcilia verbali con estratto conto bancario, PagoPA e PayPal.
    Match per: numero verbale nella descrizione, importo esatto, quietanze email.
    Crea trattenute busta paga per verbali pagati con driver assegnato.
    """
    from app.services.verbali_pagamento_finder import riconcilia_verbali_strict
    db = Database.get_db()
    stats = await riconcilia_verbali_strict(db)
    return {"success": True, "stats": stats}


@router.post("/scarica-pdf-verbali-mancanti")
async def scarica_pdf_mancanti() -> Dict[str, Any]:
    """
    Scarica i PDF dei verbali che hanno il nome cartella Gmail
    ma non hanno il pdf_data allegato.
    """
    from app.services.post_download_pipeline import scarica_pdf_verbali_mancanti
    db = Database.get_db()
    stats = await scarica_pdf_verbali_mancanti(db)
    return {"success": True, "stats": stats}


@router.post("/riconcilia-verbali-avanzato")
async def riconcilia_verbali_avanzato() -> Dict[str, Any]:
    """
    Riconciliazione avanzata verbali con banca (5 strategie):
    1. Numero verbale in descrizione bancaria
    2. Importo + beneficiario "Comune"
    3. Importo + data entro 90gg
    4. Quietanze email PagoPA/PayPal
    5. Importi multipli
    """
    from app.services.verbali_pagamento_finder import riconcilia_verbali_strict
    db = Database.get_db()
    stats = await riconcilia_verbali_strict(db)
    return {"success": True, "stats": stats}


@router.post("/riconcilia-paypal")
async def riconcilia_paypal() -> Dict[str, Any]:
    """
    Scarica transazioni PayPal e riconcilia con verbali non pagati.
    Cerca match per importo e riferimento nel subject.
    """
    from app.services.paypal_integration import riconcilia_verbali_con_paypal
    db = Database.get_db()
    stats = await riconcilia_verbali_con_paypal(db)
    return {"success": True, "stats": stats}


@router.get("/paypal-transazioni")
async def lista_transazioni_paypal(days_back: int = Query(default=31)) -> Dict[str, Any]:
    """Lista transazioni PayPal recenti."""
    from app.services.paypal_integration import cerca_transazioni_paypal
    result = await cerca_transazioni_paypal(days_back=days_back)
    return result



@router.post("/riconciliazione-completa")
async def riconciliazione_completa_endpoint(anno: int = Query(default=2026)) -> Dict[str, Any]:
    """
    Riconciliazione completa: PagoPA, Agenzia Entrate, ADER, TARI + Confronto POS.
    """
    from app.services.riconciliazione_completa import riconciliazione_completa
    db = Database.get_db()
    return {"success": True, "risultati": await riconciliazione_completa(db, anno)}


@router.get("/confronto-pos")
async def confronto_pos_endpoint(anno: int = Query(default=2026)) -> Dict[str, Any]:
    """
    Confronta pagamento elettronico corrispettivi vs inserimento manuale serale.
    Evidenzia discrepanze per evitare sanzioni fiscali.
    """
    from app.services.riconciliazione_completa import confronta_pos_corrispettivi
    db = Database.get_db()
    return await confronta_pos_corrispettivi(db, anno)




@router.post("/estrai-importi-verbali")
async def estrai_importi_verbali(
    limit: int = Query(default=76, description="Max verbali da processare")
) -> Dict[str, Any]:
    """
    Estrae importi dai verbali PDF che non hanno importo.
    Usa regex + LLM per estrarre l'importo della sanzione.
    """
    from app.services.llm_document_parser import batch_extract_importi_verbali
    db = Database.get_db()
    stats = await batch_extract_importi_verbali(db, limit=limit)
    return {"success": True, "stats": stats}


@router.post("/fix-numeri-verbali")
async def fix_numeri_verbali(
    limit: int = Query(default=102, description="Max verbali da processare")
) -> Dict[str, Any]:
    """
    Corregge numeri verbale PEC-xxx/DOC-xxx estraendo il vero numero
    dal contenuto PDF con regex + LLM.
    """
    from app.services.llm_document_parser import batch_fix_numeri_verbali
    db = Database.get_db()
    stats = await batch_fix_numeri_verbali(db, limit=limit)
    return {"success": True, "stats": stats}






@router.get("/statistiche")
async def get_statistiche_allegati() -> Dict[str, Any]:
    """
    Statistiche sui PDF scaricati e associati.
    """
    db = Database.get_db()
    stats = {}

    for category, collection in CATEGORY_COLLECTIONS.items():
        total = await db[collection].count_documents({})
        associati = await db[collection].count_documents({"associato": True})
        non_associati = await db[collection].count_documents({"associato": False})

        if total > 0:
            stats[category] = {
                "totale": total,
                "associati": associati,
                "non_associati": non_associati,
                "percentuale_associati": round(associati / total * 100, 1)
            }

    return stats


@router.get("/pdf/{collection}/{pdf_id}")
async def get_pdf_content(collection: str, pdf_id: str):
    """
    Recupera il contenuto di un PDF specifico.
    """
    from fastapi.responses import Response
    import base64

    db = Database.get_db()

    # Verifica che la collezione sia valida
    valid_collections = list(CATEGORY_COLLECTIONS.values()) + ["documents_inbox"]
    if collection not in valid_collections:
        raise HTTPException(status_code=400, detail="Collezione non valida")

    doc = await db[collection].find_one({"id": pdf_id})
    if not doc:
        raise HTTPException(status_code=404, detail="PDF non trovato")

    pdf_data = doc.get("pdf_data")
    if not pdf_data:
        raise HTTPException(status_code=404, detail="Contenuto PDF non disponibile")

    pdf_bytes = base64.b64decode(pdf_data)
    # CR/LF nel nome file rendono l'header invalido → 502 (fix 18/07/2026)
    import re as _re
    filename = _re.sub(r'[\r\n"]+', " ", doc.get("filename") or "documento.pdf").strip()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )


@router.get("/inbox-documents")
async def list_inbox_documents(
    category: str = Query(default=None),
    status: str = Query(default=None),
    limit: int = Query(default=50, le=200)
) -> Dict[str, Any]:
    """Lista documenti in documents_inbox con PDF salvato in Drive/Sheets."""
    db = Database.get_db()

    query = {}
    if category:
        query["category"] = category
    if status:
        query["status"] = status

    # Solo documenti con pdf_data (salvati su Drive/Sheets)
    query["pdf_data"] = {"$exists": True, "$ne": None}

    cursor = db["documents_inbox"].find(
        query,
        {"_id": 0, "pdf_data": 0}  # Escludi PDF dalla lista
    ).sort("downloaded_at", -1).limit(limit)

    docs = await cursor.to_list(limit)
    total = await db["documents_inbox"].count_documents({"pdf_data": {"$exists": True}})

    return {
        "count": len(docs),
        "total_in_sheets": total,
        "documents": docs
    }


@router.delete("/pulisci-duplicati")
async def pulisci_duplicati() -> Dict[str, Any]:
    """
    Rimuove i PDF duplicati basandosi sull'hash.
    """
    db = Database.get_db()
    deleted_count = 0

    for collection in CATEGORY_COLLECTIONS.values():
        # Trova hash duplicati
        pipeline = [
            {"$group": {
                "_id": "$pdf_hash",
                "count": {"$sum": 1},
                "ids": {"$push": "$id"}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]

        async for group in db[collection].aggregate(pipeline):
            # Mantieni il primo, elimina gli altri
            ids_to_delete = group["ids"][1:]
            result = await db[collection].delete_many({"id": {"$in": ids_to_delete}})
            deleted_count += result.deleted_count

    return {
        "success": True,
        "duplicati_rimossi": deleted_count
    }


# ============================================
# Gestione Mittenti Email
# ============================================

@router.get("/mittenti")
async def list_mittenti() -> Dict[str, Any]:
    """Lista tutti i mittenti configurati (PEC + Gmail)."""
    db = Database.get_db()
    mittenti = await db["mittenti_email"].find({}, {"_id": 0}).to_list(200)
    return {
        "mittenti": mittenti,
        "count": len(mittenti),
        "pec":   [m for m in mittenti if m.get("canale") == "pec"],
        "gmail": [m for m in mittenti if m.get("canale") == "gmail"],
    }


@router.post("/mittenti/migra-legacy")
async def migra_mittenti_legacy_endpoint(dry_run: bool = True, _admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    """Migra i mittenti dalla vecchia collezione `mittenti_attendibili` alla
    canonica `mittenti_email` (P2-2). Idempotente e non distruttiva. Con
    `dry_run=true` (default) riporta solo cosa farebbe."""
    from app.services.mittenti import migra_mittenti_legacy
    db = Database.get_db()
    r = await migra_mittenti_legacy(db, dry_run=dry_run)
    return {"success": True, **r}


@router.get("/mittenti/check")
async def check_mittente(from_addr: str, canale: str = "gmail") -> Dict[str, Any]:
    """
    Verifica se un indirizzo email è attendibile.
    Match: if pattern in from_addr.lower() (contenimento stringa).

    Args:
        from_addr: indirizzo mittente completo
        canale:    'pec' o 'gmail'
    """
    db = Database.get_db()
    from_lower = from_addr.lower()

    mittenti = await db["mittenti_email"].find(
        {"canale": canale, "attivo": True}, {"_id": 0}
    ).to_list(200)

    for m in mittenti:
        pattern = m.get("pattern", "").lower()
        if pattern and pattern in from_lower:
            return {
                "attendibile": True,
                "tipo_documento": m.get("tipo_documento", "generico"),
                "pattern":        m["pattern"],
                "descrizione":    m.get("descrizione", ""),
                "canale":         canale,
            }

    return {"attendibile": False, "tipo_documento": None, "pattern": None, "canale": canale}


@router.post("/mittenti")
async def add_mittente(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiunge un nuovo mittente personalizzato."""
    import uuid
    db = Database.get_db()

    pattern = payload.get("pattern", "").strip().lower()
    canale  = payload.get("canale", "gmail").lower()
    tipo    = payload.get("tipo_documento", "generico")

    if not pattern:
        raise HTTPException(status_code=400, detail="Campo 'pattern' obbligatorio")
    if canale not in ("pec", "gmail"):
        raise HTTPException(status_code=400, detail="canale deve essere 'pec' o 'gmail'")

    existing = await db["mittenti_email"].find_one({"pattern": pattern, "canale": canale})
    if existing:
        raise HTTPException(status_code=409, detail="Pattern già presente per questo canale")

    doc = {
        "id":             str(uuid.uuid4()),
        "pattern":        pattern,
        "canale":         canale,
        "tipo_documento": tipo,
        "descrizione":    payload.get("descrizione", ""),
        "attivo":         True,
        "builtin":        False,
        "created_at":     datetime.now(timezone.utc).isoformat(),
    }
    await db["mittenti_email"].insert_one(dict(doc))
    return {"success": True, "mittente": doc}


@router.delete("/mittenti/{mittente_id}")
async def delete_mittente(mittente_id: str) -> Dict[str, Any]:
    """Elimina un mittente. I builtin non possono essere eliminati."""
    db = Database.get_db()

    doc = await db["mittenti_email"].find_one(
        {"$or": [{"id": mittente_id}, {"pattern": mittente_id}]}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Mittente non trovato")
    if doc.get("builtin"):
        raise HTTPException(status_code=403, detail="I mittenti builtin non possono essere eliminati. Puoi solo disattivarli.")

    await db["mittenti_email"].delete_one({"id": doc["id"]})
    return {"success": True, "eliminato": doc["pattern"]}


@router.put("/mittenti/{mittente_id}")
async def update_mittente(mittente_id: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiorna un mittente (attivo, descrizione). I builtin non possono cambiare pattern/tipo."""
    db = Database.get_db()

    doc = await db["mittenti_email"].find_one(
        {"$or": [{"id": mittente_id}, {"pattern": mittente_id}]}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Mittente non trovato")

    update: Dict[str, Any] = {}

    # Campi sempre modificabili
    for field in ["attivo", "descrizione"]:
        if field in payload:
            update[field] = payload[field]

    # Campi modificabili solo per non-builtin
    if not doc.get("builtin"):
        for field in ["tipo_documento", "canale", "pattern"]:
            if field in payload:
                update[field] = payload[field]

    if update:
        await db["mittenti_email"].update_one(
            {"$or": [{"id": mittente_id}, {"pattern": mittente_id}]},
            {"$set": update}
        )

    return {"success": True, "modificato": doc["pattern"], "fields": list(update.keys())}


@router.get("/dizionario-email")
async def get_dizionario_email(limit: int = 100) -> Dict[str, Any]:
    """Visualizza il dizionario delle email già scaricate (Message-ID index)."""
    db = Database.get_db()
    totale = await db["email_message_index"].count_documents({})
    recenti = await db["email_message_index"].find(
        {}, {"_id": 0}
    ).sort("seen_at", -1).limit(limit).to_list(limit)
    return {"totale": totale, "recenti": recenti}


@router.delete("/dizionario-email/reset")
async def reset_dizionario_email(_admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    """Resetta il dizionario email (forza re-download di tutte le email)."""
    db = Database.get_db()
    result = await db["email_message_index"].delete_many({})
    return {"success": True, "eliminati": result.deleted_count}


@router.post("/sync-email-now")
async def trigger_email_sync(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """Trigger manuale per il sync email."""
    db = Database.get_db()

    async def run_sync():
        from app.services.email_monitor_service import sync_email_documents
        return await sync_email_documents(db, giorni=30)

    background_tasks.add_task(run_sync)
    return {"success": True, "message": "Sync email avviato in background"}


@router.post("/pulizia-non-attendibili")
async def pulizia_documenti_mittenti_non_attendibili(
    dry_run: bool = Query(True, description="Solo conteggio, non elimina"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """REGOLA UTENTE 18/07/2026: 'la lista è il vangelo per scaricare la
    posta — elimina tutto quello che viene da mittenti non comunicati, ed
    elimina gli alert associati' (es. saveris2.net, pec.kimbo.it,
    legalmail via pec.fatturapa.it mai autorizzati)."""
    from app.services.email_full_download import CATEGORY_COLLECTIONS
    from app.services.email_document_downloader import FILE_TECNICI_PEC_RE, FILE_FATTURA_SDI_RE
    from app.services.mittenti import _addr

    db = Database.get_db()

    trusted = set()
    async for m in db["mittenti_email"].find({"attivo": True}):
        a = _addr(m)
        if a:
            trusted.add(a.lower())

    def mittente_ok(indirizzo: str) -> bool:
        low = (indirizzo or "").lower()
        return bool(low) and any(s in low for s in trusted)

    def file_tecnico(nome: str) -> bool:
        # trasporto PEC/SDI (daticert, metadati MT) e fatture SDI grezze:
        # le fatture vivono in `invoices`, mai nell'archivio documenti
        n = (nome or "").strip()
        return bool(n) and bool(FILE_TECNICI_PEC_RE.search(n) or FILE_FATTURA_SDI_RE.match(n))

    collezioni = sorted(set(CATEGORY_COLLECTIONS.values())) + ["documents_inbox"]
    report: Dict[str, Any] = {}
    ids_eliminati: list = []
    esempi_mittenti: set = set()
    file_tecnici_eliminati = 0

    for coll in collezioni:
        docs = await db[coll].find(
            {}, {"_id": 0, "id": 1, "email_from": 1, "from": 1, "mittente": 1, "sender": 1,
                 "filename": 1, "file_name": 1, "nome_file": 1},
        ).to_list(20000)
        da_eliminare = []
        for d in docs:
            nome_file = d.get("filename") or d.get("file_name") or d.get("nome_file") or ""
            if file_tecnico(nome_file):
                if d.get("id"):
                    da_eliminare.append(d["id"])
                    file_tecnici_eliminati += 1
                continue
            mittente = d.get("email_from") or d.get("from") or d.get("mittente") or d.get("sender") or ""
            if not mittente:
                continue  # senza mittente non si giudica: resta
            if not mittente_ok(mittente):
                if d.get("id"):
                    da_eliminare.append(d["id"])
                if len(esempi_mittenti) < 20:
                    esempi_mittenti.add(mittente[:60])
        if da_eliminare:
            report[coll] = len(da_eliminare)
            ids_eliminati.extend(da_eliminare)
            if not dry_run:
                await db[coll].delete_many({"id": {"$in": da_eliminare}})

    alerts_eliminati = 0
    if ids_eliminati:
        filtro_alert = {"entita_id": {"$in": ids_eliminati}}
        if dry_run:
            alerts_eliminati = await db["alerts"].count_documents(filtro_alert)
        else:
            r = await db["alerts"].delete_many(filtro_alert)
            alerts_eliminati = r.deleted_count

    return {
        "dry_run": dry_run,
        "mittenti_in_lista": len(trusted),
        "documenti_eliminati" if not dry_run else "documenti_da_eliminare": len(ids_eliminati),
        "di_cui_file_tecnici_sdi": file_tecnici_eliminati,
        "per_collezione": report,
        "alerts_eliminati": alerts_eliminati,
        "esempi_mittenti_esclusi": sorted(esempi_mittenti),
    }
