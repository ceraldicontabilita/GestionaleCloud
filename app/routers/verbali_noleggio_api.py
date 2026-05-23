"""
Router per Verbali Noleggio - Endpoint dettaglio e gestione completa.
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

COLLECTION = "verbali_noleggio"


@router.get("/dettaglio/{numero_verbale:path}")
@handle_errors
async def get_verbale_dettaglio(numero_verbale: str) -> Dict[str, Any]:
    """
    Ottiene il dettaglio completo di un verbale.
    Cerca per numero_verbale in vari formati.
    Supporta numeri con slash come S/2259.
    """
    db = Database.get_db()
    
    # Normalizza il numero verbale
    numero_clean = numero_verbale.strip()
    
    # Cerca in vari modi (incluso vecchio numero)
    verbale = await db[COLLECTION].find_one({
        "$or": [
            {"numero_verbale": numero_clean},
            {"numero_verbale": numero_clean.upper()},
            {"numero_verbale_old": numero_clean},
            {"numero_verbale_old": numero_clean.upper()},
            {"id": numero_clean},
            {"numero_verbale": {"$regex": f"^{numero_clean}$", "$options": "i"}}
        ]
    })
    
    if not verbale:
        # Prova anche nella collection completi
        verbale = await db["verbali_noleggio_completi"].find_one({
            "$or": [
                {"numero_verbale": numero_verbale},
                {"numero_verbale": numero_verbale.upper()},
                {"id": numero_verbale}
            ]
        })
    
    if not verbale:
        raise HTTPException(status_code=404, detail=f"Verbale {numero_verbale} non trovato")
    
    # Rimuovi _id per serializzazione
    verbale.pop("_id", None)
    
    # Arricchisci con dati driver se disponibile
    if verbale.get("driver_id"):
        driver = await db.employees.find_one({"id": verbale["driver_id"]})
        if driver:
            verbale["driver_dettaglio"] = {
                "nome": driver.get("nome"),
                "cognome": driver.get("cognome"),
                "codice_fiscale": driver.get("codice_fiscale")
            }
    
    # Arricchisci con dati veicolo se disponibile
    if verbale.get("targa"):
        veicolo = await db.veicoli_noleggio.find_one({"targa": verbale["targa"]})
        if veicolo:
            veicolo.pop("_id", None)
            verbale["veicolo_dettaglio"] = veicolo
    
    # Costruisci pdf_disponibili dal pdf_data se non esiste pdf_allegati
    if not verbale.get("pdf_disponibili"):
        pdf_list = []
        if verbale.get("pdf_data"):
            pdf_list.append({
                "indice": 0,
                "filename": verbale.get("pdf_filename", "verbale.pdf"),
                "tipo": "verbale",
                "size": verbale.get("pdf_size", 0)
            })
        if verbale.get("quietanza_pdf"):
            pdf_list.append({
                "indice": 1,
                "filename": verbale.get("quietanza_filename", "quietanza.pdf"),
                "tipo": "quietanza",
                "size": 0
            })
        verbale["pdf_disponibili"] = pdf_list
    
    # Cerca fattura associata (per noleggiatori come ARVAL, Leasys, ALD)
    if not verbale.get("fattura_id") and verbale.get("targa"):
        targa = verbale["targa"]
        # Cerca fatture con questa targa nella descrizione
        fattura = await db["invoices"].find_one({
            "$or": [
                {"descrizione": {"$regex": targa, "$options": "i"}},
                {"xml_raw": {"$regex": targa, "$options": "i"} if "xml_raw" in (await db["invoices"].find_one({}, {"xml_raw": 1}) or {}) else None}
            ]
        }, {"_id": 1, "id": 1, "supplier_name": 1, "invoice_number": 1, "total_amount": 1, "invoice_date": 1})
        if fattura:
            # Usa l'id UUID se disponibile, altrimenti l'ObjectId come stringa
            fid = fattura.get("id") or str(fattura.get("_id", ""))
            verbale["fattura_id"] = fid
            verbale["fattura_fornitore"] = fattura.get("supplier_name")
            verbale["fattura_numero"] = fattura.get("invoice_number")
            verbale["fattura_importo"] = fattura.get("total_amount")
    
    # Non inviare pdf_data nel response (troppo grande)
    verbale.pop("pdf_data", None)
    verbale.pop("quietanza_pdf", None)
    
    return verbale


@router.get("/lista")
@handle_errors
async def get_verbali_lista(
    anno: Optional[int] = None,
    stato: Optional[str] = None,
    driver_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Lista verbali con filtri opzionali.
    """
    db = Database.get_db()
    
    query = {}
    
    if anno:
        query["$or"] = [
            {"data": {"$regex": f"^{anno}"}},
            {"data_verbale": {"$regex": f"^{anno}"}},
            {"anno": anno}
        ]
    
    if stato:
        query["stato"] = stato
    
    if driver_id:
        query["driver_id"] = driver_id
    
    verbali = await db[COLLECTION].find(query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    total = await db[COLLECTION].count_documents(query)
    
    return {
        "verbali": verbali,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/pdf/{numero_verbale}")
@handle_errors
async def get_verbale_pdf(
    numero_verbale: str,
    indice: int = Query(0, description="Indice del PDF: 0=verbale, 1=quietanza")
) -> Dict[str, Any]:
    """
    Ottiene il PDF allegato a un verbale.
    Gestisce sia pdf_allegati (vecchio formato) che pdf_data/quietanza_pdf.
    """
    db = Database.get_db()
    
    verbale = await db[COLLECTION].find_one({
        "$or": [
            {"numero_verbale": numero_verbale},
            {"numero_verbale_old": numero_verbale},
            {"id": numero_verbale}
        ]
    })
    
    if not verbale:
        raise HTTPException(status_code=404, detail=f"Verbale {numero_verbale} non trovato")
    
    # Vecchio formato: pdf_allegati array
    pdf_allegati = verbale.get("pdf_allegati", [])
    if pdf_allegati and indice < len(pdf_allegati):
        pdf = pdf_allegati[indice]
        return {
            "filename": pdf.get("filename"),
            "content_base64": pdf.get("content_base64"),
            "content_type": "application/pdf"
        }
    
    # Nuovo formato: pdf_data (verbale) e quietanza_pdf
    if indice == 0 and verbale.get("pdf_data"):
        return {
            "filename": verbale.get("pdf_filename", f"verbale_{numero_verbale}.pdf"),
            "content_base64": verbale["pdf_data"],
            "content_type": "application/pdf"
        }
    
    if indice == 1 and verbale.get("quietanza_pdf"):
        return {
            "filename": verbale.get("quietanza_filename", f"quietanza_{numero_verbale}.pdf"),
            "content_base64": verbale["quietanza_pdf"],
            "content_type": "application/pdf"
        }
    
    raise HTTPException(status_code=404, detail="PDF non trovato per questo verbale")


@router.post("/scarica-posta")
@handle_errors
async def scarica_posta_verbali() -> Dict[str, Any]:
    """
    Placeholder per il download verbali da email PEC.
    In futuro integrerà con il sistema email.
    """
    return {
        "message": "Funzionalità in sviluppo",
        "status": "pending"
    }



@router.get("/alert-pagamenti")
@handle_errors
async def alert_verbali_non_pagati() -> Dict[str, Any]:
    """
    Alert verbali non pagati: senza quietanza in email, estratto conto o PayPal.
    Per ciascuno indica: upload bollettino necessario.
    """
    db = Database.get_db()
    
    verbali = await db[COLLECTION].find(
        {"stato": {"$nin": ["pagato", "riconciliato"]}},
        {"_id": 0, "pdf_data": 0, "quietanza_pdf": 0}
    ).sort("data_verbale", 1).to_list(500)
    
    alerts = []
    for v in verbali:
        importo = float(v.get("importo", 0) or 0)
        alerts.append({
            "id": v.get("id"),
            "numero_verbale": v.get("numero_verbale"),
            "targa": v.get("targa"),
            "driver": v.get("driver"),
            "data_verbale": v.get("data_verbale"),
            "importo": importo,
            "stato": v.get("stato"),
            "azione_richiesta": "upload_bollettino" if importo > 0 else "verifica_importo",
            "messaggio": f"Verbale {v.get('numero_verbale','')} - €{importo:.2f} - Pagamento non trovato in estratto conto/email. Caricare scansione bollettino." if importo > 0 else f"Verbale {v.get('numero_verbale','')} - Importo non determinato. Verificare PDF.",
        })
    
    return {
        "totale_alert": len(alerts),
        "importo_totale_da_pagare": round(sum(a["importo"] for a in alerts), 2),
        "alerts": alerts
    }


@router.post("/{verbale_id}/upload-quietanza")
@handle_errors
async def upload_quietanza_verbale(verbale_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Upload manuale della quietanza/bollettino per un verbale.
    Accetta: pdf_base64, importo_pagato, data_pagamento, metodo.
    """
    db = Database.get_db()
    
    verbale = await db[COLLECTION].find_one({"id": verbale_id})
    if not verbale:
        raise HTTPException(status_code=404, detail="Verbale non trovato")
    
    update = {
        "stato": "pagato",
        "quietanza_ricevuta": True,
        "data_pagamento": data.get("data_pagamento"),
        "metodo_pagamento": data.get("metodo", "bollettino_manuale"),
        "importo_pagato": float(data.get("importo_pagato", 0)),
    }
    
    if data.get("pdf_base64"):
        update["quietanza_pdf"] = data["pdf_base64"]
        update["quietanza_filename"] = data.get("filename", "quietanza.pdf")
    
    await db[COLLECTION].update_one({"id": verbale_id}, {"$set": update})
    
    # Crea nota presenze per consulente del lavoro
    driver_id = verbale.get("driver_id") or verbale.get("driver_cf")
    if driver_id:
        from datetime import datetime, timezone
        dt = datetime.now(timezone.utc)
        mese_nota = dt.month + 1 if dt.month < 12 else 1
        anno_nota = dt.year if dt.month < 12 else dt.year + 1
        
        nota = {
            "id": str(__import__("uuid").uuid4()),
            "dipendente_id": driver_id,
            "dipendente_nome": verbale.get("driver", ""),
            "tipo": "trattenuta_verbale",
            "mese": mese_nota,
            "anno": anno_nota,
            "importo": float(data.get("importo_pagato", 0)),
            "descrizione": f"TRATTENUTA VERBALE {verbale.get('numero_verbale','')} - Targa {verbale.get('targa','')} - Pagato {data.get('data_pagamento','')}",
            "evidenza": True,
            "inviato_consulente": False,
            "verbale_id": verbale_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db["note_presenze_consulente"].insert_one(nota)
        
        # Anche in trattenute_dipendenti
        await db["trattenute_dipendenti"].insert_one({
            **nota,
            "tipo": "verbale_multa",
            "stato": "da_applicare",
            "numero_verbale": verbale.get("numero_verbale"),
            "targa": verbale.get("targa"),
        })
    
    return {"success": True, "message": f"Quietanza caricata per verbale {verbale.get('numero_verbale','')}"}


@router.get("/note-consulente")
@handle_errors
async def get_note_consulente(
    anno: Optional[int] = Query(None),
    mese: Optional[int] = Query(None)
) -> Dict[str, Any]:
    """
    Note da inviare al consulente del lavoro per le presenze.
    Include trattenute verbali da evidenziare.
    """
    db = Database.get_db()
    
    query = {}
    if anno:
        query["anno"] = anno
    if mese:
        query["mese"] = mese
    
    note = await db["note_presenze_consulente"].find(
        query, {"_id": 0}
    ).sort([("anno", -1), ("mese", -1)]).to_list(200)
    
    return {
        "note": note,
        "totale": len(note),
        "importo_totale": round(sum(float(n.get("importo", 0) or 0) for n in note), 2),
        "non_inviate": sum(1 for n in note if not n.get("inviato_consulente"))
    }



@router.put("/{verbale_id}")
@handle_errors
async def update_verbale(verbale_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggiorna un verbale.
    """
    db = Database.get_db()
    
    # Rimuovi campi non modificabili
    data.pop("_id", None)
    data.pop("id", None)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db[COLLECTION].update_one(
        {"$or": [{"id": verbale_id}, {"numero_verbale": verbale_id}]},
        {"$set": data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Verbale {verbale_id} non trovato")
    
    return {"message": "Verbale aggiornato", "modified": result.modified_count}


@router.post("/associa-driver")
@handle_errors
async def associa_driver_verbale(
    verbale_id: str = Query(...),
    driver_id: str = Query(...),
    driver_nome: str = Query(None)
) -> Dict[str, Any]:
    """
    Associa manualmente un driver a un verbale.
    """
    db = Database.get_db()
    
    # Verifica che il driver esista
    driver = await db.employees.find_one({"id": driver_id})
    if not driver:
        raise HTTPException(status_code=404, detail=f"Driver {driver_id} non trovato")
    
    driver_nome_completo = driver_nome or f"{driver.get('nome', '')} {driver.get('cognome', '')}".strip()
    
    result = await db[COLLECTION].update_one(
        {"$or": [{"id": verbale_id}, {"numero_verbale": verbale_id}]},
        {"$set": {
            "driver_id": driver_id,
            "driver": driver_nome_completo,
            "associazione_manuale": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"Verbale {verbale_id} non trovato")
    
    return {"message": "Driver associato", "driver": driver_nome_completo}


@router.get("/stats")
@handle_errors
async def get_verbali_stats() -> Dict[str, Any]:
    """
    Statistiche sui verbali.
    """
    db = Database.get_db()
    
    totale = await db[COLLECTION].count_documents({})
    
    con_driver = await db[COLLECTION].count_documents({
        "driver": {"$exists": True, "$ne": None, "$ne": ""}
    })
    
    senza_driver = totale - con_driver
    
    # Per stato
    pipeline_stato = [
        {"$group": {"_id": "$stato", "count": {"$sum": 1}}}
    ]
    stati = await db[COLLECTION].aggregate(pipeline_stato).to_list(100)
    per_stato = {s["_id"] or "unknown": s["count"] for s in stati}
    
    # Importo totale
    pipeline_importo = [
        {"$group": {"_id": None, "totale": {"$sum": {"$toDouble": {"$ifNull": ["$importo", 0]}}}}}
    ]
    importo_result = await db[COLLECTION].aggregate(pipeline_importo).to_list(1)
    importo_totale = importo_result[0]["totale"] if importo_result else 0
    
    return {
        "totale": totale,
        "con_driver": con_driver,
        "senza_driver": senza_driver,
        "per_stato": per_stato,
        "importo_totale": round(importo_totale, 2),
        "health_score": round((con_driver / totale * 100) if totale > 0 else 0, 1)
    }


# ═══════════════════════════════════════════════════════════════════════════
# FASE 3 + FASE 4: Ricerca pagamento multi-fonte + workflow bidirezionale
# ═══════════════════════════════════════════════════════════════════════════
import os
from fastapi.responses import FileResponse


@router.post("/{verbale_id}/cerca-pagamento")
@handle_errors
async def cerca_pagamento_verbale(verbale_id: str) -> Dict[str, Any]:
    """Cerca in cascata (PayPal → Gmail → E/C) il pagamento del verbale.
    Se trovato, applica al verbale tutti i dati del pagamento."""
    from app.services.verbali_pagamento_finder import (
        trova_pagamento_verbale, applica_pagamento_a_verbale
    )
    db = Database.get_db()
    v = await db[COLLECTION].find_one(
        {"$or": [{"id": verbale_id}, {"numero_verbale": verbale_id}]},
        {"_id": 0, "pdf_data": 0, "quietanza_pdf": 0}
    )
    if not v:
        raise HTTPException(404, "Verbale non trovato")
    match = await trova_pagamento_verbale(db, v)
    if not match:
        return {"trovato": False, "messaggio": "Nessun pagamento trovato."}
    vid = v.get("id") or v.get("numero_verbale") or verbale_id
    await applica_pagamento_a_verbale(db, vid, match)
    return {
        "trovato": True,
        "fonte": match["fonte"],
        "psp": match["psp"],
        "importo": match["importo"],
        "data_pagamento": match["data_pagamento"],
        "metodo_pagamento": match["metodo_pagamento"],
        "pdf_disponibile": bool(match.get("pdf_ricevuta_path")),
        "iuv_usato": match.get("iuv_usato"),
    }


@router.get("/{verbale_id}/ricevuta-pdf")
@handle_errors
async def scarica_ricevuta_verbale(verbale_id: str):
    """Scarica la ricevuta PDF collegata al verbale."""
    db = Database.get_db()
    v = await db[COLLECTION].find_one(
        {"$or": [{"id": verbale_id}, {"numero_verbale": verbale_id}]},
        {"_id": 0, "pdf_data": 0, "quietanza_pdf": 0}
    )
    pdf_path = (v or {}).get("pdf_ricevuta_path") or ""
    # Security: il path DEVE essere sotto /app/uploads/
    safe_path = os.path.realpath(pdf_path) if pdf_path else ""
    if not v or not safe_path or not safe_path.startswith("/tmp/uploads/") or not os.path.exists(safe_path):
        raise HTTPException(404, "PDF non disponibile")
    return FileResponse(
        safe_path,
        media_type="application/pdf",
        filename=f"ricevuta_verbale_{v.get('numero_verbale', verbale_id)}.pdf",
    )


@router.post("/scan-gmail")
@handle_errors
async def scan_gmail(days_back: int = 7) -> Dict[str, Any]:
    """Scansione Gmail per verbali CdS inoltrati (Trigger A)."""
    from app.services.verbali_gmail_scanner import scan_gmail_verbali
    return await scan_gmail_verbali(Database.get_db(), days_back=days_back)


@router.post("/riconcilia-completo")
@handle_errors
async def riconcilia_completo() -> Dict[str, Any]:
    """
    Pipeline completa workflow verbali:
    1. Scan Gmail ultimi 7gg per nuove PEC
    2. Collega verbali ↔ fatture ARVAL/Leasys
    3. Ricerca pagamenti PagoPA in tutte le fonti
    """
    from app.services.verbali_gmail_scanner import scan_gmail_verbali
    from app.services.verbali_fattura_linker import collega_verbali_a_fatture
    from app.services.verbali_pagamento_finder import (
        trova_pagamento_verbale, applica_pagamento_a_verbale
    )
    db = Database.get_db()
    r1 = await scan_gmail_verbali(db, days_back=7)
    r2 = await collega_verbali_a_fatture(db)
    r3 = {"processati": 0, "riconciliati": 0}
    cursor = db[COLLECTION].find({
        "stato": {"$in": ["notificato", "da_verificare", "notifica_attesa"]},
        "riconciliato_paypal": {"$ne": True},
    }, {"_id": 0, "pdf_data": 0, "quietanza_pdf": 0})
    async for v in cursor:
        r3["processati"] += 1
        m = await trova_pagamento_verbale(db, v)
        if m:
            vid = v.get("id") or v.get("numero_verbale")
            ok = await applica_pagamento_a_verbale(db, vid, m)
            if ok:
                r3["riconciliati"] += 1
    return {"scan_gmail": r1, "link_fatture": r2, "ricerca_pagamenti": r3}


@router.post("/bulk-assegna-pagamento")
@handle_errors
async def bulk_assegna_pagamento(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Assegna pagamento PayPal a una lista di verbali con dati noti (da tabella utente
    o import CSV). Ciascun item aggiorna il verbale E la paypal_transactions con IUV e
    numero_verbale_collegato per abilitare ricerche future.

    Body: { "items": [ { "numero_verbale", "iuv", "transaction_id", "importo",
                          "data_pagamento", "psp", "metodo_pagamento", "targa" }, ... ] }
    """
    from datetime import datetime, timezone
    items = body.get("items", [])
    if not isinstance(items, list) or not items:
        raise HTTPException(400, "Body deve contenere 'items' (lista non vuota)")

    db = Database.get_db()
    stats = {"processati": 0, "verbali_aggiornati": 0, "paypal_tx_aggiornate": 0, "errori": []}

    for it in items:
        stats["processati"] += 1
        nv = (it.get("numero_verbale") or "").strip()
        iuv = (it.get("iuv") or "").strip() or None
        txid = (it.get("transaction_id") or "").strip() or None
        if not nv:
            stats["errori"].append({"item": it, "errore": "numero_verbale mancante"})
            continue

        # Verbale update
        v_update = {
            "stato": "pagato",
            "fonte_riconciliazione": it.get("fonte", "manuale_tabella"),
            "riconciliato_paypal": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        for src, dst in [("iuv","iuv"), ("transaction_id","paypal_transaction_id"),
                          ("importo","importo"), ("data_pagamento","data_pagamento"),
                          ("psp","psp"), ("metodo_pagamento","metodo_pagamento"),
                          ("targa","targa")]:
            val = it.get(src)
            if val:
                v_update[dst] = val
        res_v = await db["verbali_noleggio"].update_one(
            {"numero_verbale": nv}, {"$set": v_update}
        )
        if res_v.modified_count:
            stats["verbali_aggiornati"] += 1

        # paypal_transactions: denormalizza iuv + numero_verbale_collegato per future ricerche
        if txid:
            res_tx = await db["paypal_transactions"].update_one(
                {"transaction_id": txid},
                {"$set": {
                    "iuv": iuv,
                    "numero_verbale_collegato": nv,
                    "targa_collegata": it.get("targa"),
                    "verbale_linked_at": datetime.now(timezone.utc).isoformat(),
                }}
            )
            if res_tx.modified_count:
                stats["paypal_tx_aggiornate"] += 1

    return stats
