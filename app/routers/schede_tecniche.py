"""
Router Schede Tecniche Prodotti
================================
Endpoint per gestire le schede tecniche dei prodotti.
"""

from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import Response
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import base64
import logging

from app.database import Database
from app.services.schede_tecniche_service import (
    get_schede_tecniche_fornitore,
    get_schede_tecniche_prodotto,
    process_scheda_tecnica_from_pdf
)

router = APIRouter(prefix="/schede-tecniche", tags=["Schede Tecniche Prodotti"])
logger = logging.getLogger(__name__)


@router.get("/lista")
async def lista_schede_tecniche(
    fornitore_id: Optional[str] = Query(None),
    prodotto_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200)
) -> Dict[str, Any]:
    """
    Lista schede tecniche con filtri opzionali.
    """
    db = Database.get_db()
    
    query = {}
    if fornitore_id:
        query["fornitore_id"] = fornitore_id
    if prodotto_id:
        query["prodotto_id"] = prodotto_id
    
    total = await db["schede_tecniche_prodotti"].count_documents(query)
    
    schede = await db["schede_tecniche_prodotti"].find(
        query,
        {"_id": 0, "pdf_data": 0, "raw_text": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    return {
        "schede": schede,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/fornitore/{fornitore_id}")
async def schede_per_fornitore(fornitore_id: str) -> Dict[str, Any]:
    """
    Ottiene tutte le schede tecniche di un fornitore.
    """
    db = Database.get_db()
    
    # Verifica che il fornitore esista
    fornitore = await db["suppliers"].find_one(
        {"id": fornitore_id},
        {"_id": 0, "id": 1, "nome": 1, "ragione_sociale": 1}
    )
    
    if not fornitore:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    schede = await get_schede_tecniche_fornitore(db, fornitore_id)
    
    return {
        "fornitore": {
            "id": fornitore.get("id"),
            "nome": fornitore.get("ragione_sociale") or fornitore.get("nome")
        },
        "schede": schede,
        "total": len(schede)
    }


@router.get("/prodotto/{prodotto_id}")
async def schede_per_prodotto(prodotto_id: str) -> Dict[str, Any]:
    """
    Ottiene tutte le schede tecniche di un prodotto.
    """
    db = Database.get_db()
    
    # Verifica che il prodotto esista
    prodotto = await db["magazzino_articoli"].find_one(
        {"id": prodotto_id},
        {"_id": 0, "id": 1, "nome": 1, "codice": 1}
    )
    
    if not prodotto:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    
    schede = await get_schede_tecniche_prodotto(db, prodotto_id)
    
    return {
        "prodotto": prodotto,
        "schede": schede,
        "total": len(schede)
    }


@router.get("/pdf/{scheda_id}")
async def visualizza_pdf_scheda(scheda_id: str):
    """
    Restituisce il PDF della scheda tecnica.
    """
    db = Database.get_db()
    
    scheda = await db["schede_tecniche_prodotti"].find_one(
        {"id": scheda_id},
        {"_id": 0, "pdf_data": 1, "filename": 1}
    )
    
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda tecnica non trovata")
    
    pdf_data = scheda.get("pdf_data")
    if not pdf_data:
        raise HTTPException(status_code=404, detail="PDF non disponibile")
    
    # Decodifica base64
    try:
        if isinstance(pdf_data, str):
            pdf_bytes = base64.b64decode(pdf_data)
        else:
            pdf_bytes = pdf_data
    except Exception as e:
        raise HTTPException(status_code=500, detail="Errore decodifica PDF")
    
    filename = scheda.get("filename", "scheda_tecnica.pdf")
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-cache"
        }
    )


@router.get("/{scheda_id}")
async def dettaglio_scheda(scheda_id: str) -> Dict[str, Any]:
    """
    Dettaglio completo di una scheda tecnica.
    """
    db = Database.get_db()
    
    scheda = await db["schede_tecniche_prodotti"].find_one(
        {"id": scheda_id},
        {"_id": 0, "pdf_data": 0}  # Escludi PDF per ridurre payload
    )
    
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda tecnica non trovata")
    
    return scheda


@router.post("/associa-prodotto")
async def associa_scheda_prodotto(
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Associa manualmente una scheda tecnica a un prodotto.
    """
    scheda_id = data.get("scheda_id")
    prodotto_id = data.get("prodotto_id")
    
    if not scheda_id or not prodotto_id:
        raise HTTPException(status_code=400, detail="scheda_id e prodotto_id sono obbligatori")
    
    db = Database.get_db()
    
    # Verifica scheda
    scheda = await db["schede_tecniche_prodotti"].find_one({"id": scheda_id})
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda tecnica non trovata")
    
    # Verifica prodotto
    prodotto = await db["magazzino_articoli"].find_one(
        {"id": prodotto_id},
        {"_id": 0, "id": 1, "nome": 1}
    )
    if not prodotto:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    
    # Aggiorna scheda
    await db["schede_tecniche_prodotti"].update_one(
        {"id": scheda_id},
        {"$set": {
            "prodotto_id": prodotto_id,
            "prodotto_associato": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Aggiorna prodotto
    await db["magazzino_articoli"].update_one(
        {"id": prodotto_id},
        {
            "$set": {
                "scheda_tecnica_id": scheda_id,
                "scheda_tecnica_data": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {
        "success": True,
        "message": f"Scheda associata al prodotto {prodotto.get('nome')}",
        "scheda_id": scheda_id,
        "prodotto_id": prodotto_id
    }


@router.delete("/{scheda_id}")
async def elimina_scheda(scheda_id: str) -> Dict[str, Any]:
    """
    Elimina una scheda tecnica.
    """
    db = Database.get_db()
    
    scheda = await db["schede_tecniche_prodotti"].find_one({"id": scheda_id})
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda tecnica non trovata")
    
    # Se era associata a un prodotto, rimuovi il riferimento
    if scheda.get("prodotto_id"):
        await db["magazzino_articoli"].update_one(
            {"id": scheda["prodotto_id"]},
            {"$unset": {"scheda_tecnica_id": "", "scheda_tecnica_data": ""}}
        )
    
    await db["schede_tecniche_prodotti"].delete_one({"id": scheda_id})
    
    return {
        "success": True,
        "message": "Scheda tecnica eliminata",
        "deleted_id": scheda_id
    }


@router.get("/statistiche/riepilogo")
async def statistiche_schede() -> Dict[str, Any]:
    """
    Statistiche sulle schede tecniche.
    """
    db = Database.get_db()
    
    total = await db["schede_tecniche_prodotti"].count_documents({})
    associate = await db["schede_tecniche_prodotti"].count_documents({"prodotto_associato": True})
    non_associate = total - associate
    
    # Schede per fornitore (top 10)
    pipeline = [
        {"$match": {"fornitore_nome": {"$ne": None}}},
        {"$group": {"_id": "$fornitore_nome", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10}
    ]
    per_fornitore = await db["schede_tecniche_prodotti"].aggregate(pipeline).to_list(10)
    
    return {
        "totale": total,
        "associate_prodotto": associate,
        "non_associate": non_associate,
        "percentuale_associazione": round(associate / total * 100, 1) if total > 0 else 0,
        "per_fornitore": [{"fornitore": p["_id"], "count": p["count"]} for p in per_fornitore]
    }


@router.post("/scan-email")
async def scan_email_schede_tecniche(
    folders: Optional[List[str]] = Body(None, description="Cartelle da scansionare"),
    limit: int = Body(50, description="Limite email per cartella"),
    days_back: int = Body(60, description="Giorni indietro")
) -> Dict[str, Any]:
    """
    Scansiona le email per scaricare automaticamente schede tecniche.
    
    Le schede vengono identificate da parole chiave come:
    - "scheda tecnica"
    - "technical sheet"  
    - "data sheet"
    - "ingredienti"
    - "allergeni"
    
    Le schede trovate vengono associate automaticamente ai fornitori
    basandosi sull'email del mittente.
    """
    import os
    from app.services.schede_tecniche_service import scan_email_for_schede_tecniche
    
    # Credenziali IMAP da environment
    imap_host = os.environ.get("IMAP_HOST", "imap.gmail.com")
    imap_user = os.environ.get("IMAP_USER", "")
    imap_password = os.environ.get("IMAP_PASSWORD", "")
    
    if not imap_user or not imap_password:
        raise HTTPException(
            status_code=400,
            detail="Credenziali IMAP non configurate. Imposta IMAP_USER e IMAP_PASSWORD in .env"
        )
    
    result = await scan_email_for_schede_tecniche(
        imap_host=imap_host,
        imap_user=imap_user,
        imap_password=imap_password,
        folders=folders,
        limit=limit,
        days_back=days_back
    )
    
    return result


@router.post("/associa-automatico")
async def associa_schede_automatico() -> Dict[str, Any]:
    """
    Tenta di associare automaticamente le schede tecniche non associate
    ai fornitori, basandosi sui nomi nelle fatture XML.
    """
    db = Database.get_db()
    
    # Trova schede non associate
    schede_non_associate = await db["schede_tecniche_prodotti"].find({
        "$or": [
            {"fornitore_id": None},
            {"fornitore_id": ""}
        ]
    }).to_list(200)
    
    associated = 0
    
    for scheda in schede_non_associate:
        email_from = scheda.get('email_from', '').lower()
        
        if not email_from:
            continue
        
        # Estrai dominio email
        domain = email_from.split('@')[-1] if '@' in email_from else ''
        
        # Cerca fornitore con email o dominio simile
        fornitore = None
        
        # Prima cerca per email esatta
        fornitore = await db.fornitori.find_one({
            "$or": [
                {"email": {"$regex": email_from, "$options": "i"}},
                {"pec": {"$regex": email_from, "$options": "i"}}
            ]
        })
        
        if not fornitore and domain:
            # Cerca per dominio
            fornitore = await db.fornitori.find_one({
                "$or": [
                    {"email": {"$regex": domain, "$options": "i"}},
                    {"pec": {"$regex": domain, "$options": "i"}},
                    {"sito_web": {"$regex": domain, "$options": "i"}}
                ]
            })
        
        if not fornitore:
            # Cerca nelle fatture per dominio email
            fattura = await db.invoices.find_one({
                "$or": [
                    {"sender_email": {"$regex": domain, "$options": "i"}},
                    {"fornitore.email": {"$regex": domain, "$options": "i"}}
                ]
            })
            
            if fattura:
                supplier_name = fattura.get('supplier_name') or fattura.get('fornitore', {}).get('denominazione')
                if supplier_name:
                    fornitore = await db.fornitori.find_one({
                        "ragione_sociale": {"$regex": supplier_name[:20], "$options": "i"}
                    })
        
        if fornitore:
            # Aggiorna scheda
            await db["schede_tecniche_prodotti"].update_one(
                {"id": scheda["id"]},
                {"$set": {
                    "fornitore_id": fornitore.get('id'),
                    "fornitore_nome": fornitore.get('ragione_sociale'),
                    "associato_automaticamente": True,
                    "data_associazione": datetime.now(timezone.utc).isoformat()
                }}
            )
            associated += 1
    
    return {
        "schede_analizzate": len(schede_non_associate),
        "schede_associate": associated,
        "non_associate": len(schede_non_associate) - associated
    }
