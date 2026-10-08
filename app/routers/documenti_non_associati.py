"""
Router per gestione documenti non associati.
Permette di visualizzare e associare manualmente i documenti.
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List
from datetime import datetime, timezone
import uuid
import re
import logging

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Documenti Non Associati"])


# Collezioni target per associazione
TARGET_COLLECTIONS = {
    "fatture": {"collection": "invoices", "label": "Fatture Ricevute"},
    "f24": {"collection": "f24_unificato", "label": "F24"},
    "cedolini": {"collection": "payslips", "label": "Cedolini/Buste Paga"},
    "verbali": {"collection": "verbali_multe", "label": "Verbali e Multe"},
    "cartelle": {"collection": "cartelle_esattoriali", "label": "Cartelle Esattoriali"},
    "estratti": {"collection": "estratto_conto_movimenti", "label": "Estratti Conto"},
    "bonifici": {"collection": "bonifici", "label": "Bonifici"},
    "quietanze": {"collection": "quietanze", "label": "Quietanze"},
    "contratti": {"collection": "contratti", "label": "Contratti"},
    "certificati": {"collection": "certificati_medici", "label": "Certificati Medici"},
}



@router.get("/categorie-mittente")
async def get_categorie_mittente() -> Dict[str, Any]:
    """Statistiche documenti per categoria mittente (INPS, Agenzia Entrate, ecc.)"""
    return await stats_per_categoria_mittente()


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
    Mostra SOLO documenti provenienti da mittenti attendibili.
    """
    db = Database.get_db()
    
    # Carica mittenti attendibili per filtrare
    mittenti_attivi = []
    async for m in db["mittenti_email"].find({"attivo": True}, {"_id": 0, "pattern": 1}):
        if m.get("pattern"):
            mittenti_attivi.append(m["pattern"].lower())
    
    # Base query: escludere documenti già associati
    base_filter = {"$or": [{"associato": {"$exists": False}}, {"associato": False}]}
    
    # Filtro mittenti attendibili: email_from deve contenere almeno un pattern
    if mittenti_attivi:
        mittenti_conditions = [{"email_from": {"$regex": p, "$options": "i"}} for p in mittenti_attivi]
        # Includi anche documenti con categoria specifica (f24, cedolino, ecc.) - sono già classificati
        mittenti_conditions.append({"category": {"$in": ["f24", "cedolino", "busta_paga", "fattura", "estratto_conto", "quietanza", "bonifico", "verbale", "cartella_esattoriale"]}})
        base_filter = {"$and": [
            base_filter,
            {"$or": mittenti_conditions}
        ]}
    
    # Costruisci query con filtri aggiuntivi
    conditions = [base_filter]
    
    if categoria:
        # Supporta sia category (tipo doc) che categoria_mittente
        conditions.append({"$or": [
            {"category": categoria},
            {"categoria_mittente": categoria}
        ]})
    
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



async def stats_per_categoria_mittente() -> Dict[str, Any]:
    """
    Statistiche documenti raggruppati per categoria mittente.
    Per la pagina documenti divisa per: INPS, Agenzia Entrate, 
    Comune di Napoli, Consulente Lavoro, Commercialista, etc.
    """
    db = Database.get_db()
    
    # Carica mittenti per filtrare
    mittenti_attivi = []
    async for m in db["mittenti_email"].find({"attivo": True}, {"_id": 0, "pattern": 1}):
        if m.get("pattern"):
            mittenti_attivi.append(m["pattern"].lower())
    
    # Filter solo mittenti attendibili
    mittenti_conditions = [{"email_from": {"$regex": p, "$options": "i"}} for p in mittenti_attivi]
    mittenti_conditions.append({"category": {"$in": ["f24", "cedolino", "busta_paga", "fattura", "estratto_conto", "quietanza", "bonifico", "verbale", "cartella_esattoriale", "inps", "pagopa", "fiscale", "assicurazione"]}})
    
    base_filter = {
        "$and": [
            {"$or": [{"associato": {"$exists": False}}, {"associato": False}]},
            {"$or": mittenti_conditions}
        ]
    }
    
    pipeline = [
        {"$match": base_filter},
        {"$group": {
            "_id": {"$ifNull": ["$categoria_mittente", "Non classificato"]},
            "count": {"$sum": 1},
            "documenti_recenti": {"$push": {"filename": "$filename", "email_subject": "$email_subject", "email_from": "$email_from"}}
        }},
        {"$sort": {"count": -1}}
    ]
    
    categorie = []
    totale = 0
    async for r in db["documenti_non_associati"].aggregate(pipeline):
        cat = r["_id"] or "Non classificato"
        count = r["count"]
        totale += count
        
        # Icon per categoria
        icons = {
            "INPS": "🏛️", "Agenzia Entrate": "🏢", "Comune di Napoli": "🏙️",
            "Consulente Lavoro": "👔", "Commercialista": "📊", "PayPal": "💳",
            "INAIL": "🏗️", "Assicurazione": "🛡️", "SDI Fatture": "📄"
        }
        
        categorie.append({
            "nome": cat,
            "icon": icons.get(cat, "📁"),
            "count": count,
            "sample": r["documenti_recenti"][:3]  # primi 3 per preview
        })
    
    return {
        "categorie": categorie,
        "totale": totale
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
        proposta["collezione_suggerita"] = "f24_unificato"
    
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


@router.post("/de-associa")
async def de_associa_documento(documento_id: str = Body(..., embed=True)) -> Dict[str, Any]:
    """Annulla un'associazione sbagliata (richiesta utente 18/07/2026:
    "ho cliccato F24 ed ho sbagliato, come riclassifico?" — non c'era modo
    di tornare indietro: il documento spariva dall'elenco "da associare" e
    restava un record estraneo nella collezione sbagliata, es. un F24
    fantasma per un documento che era in realtà una Cartella Esattoriale).

    Elimina il record creato per errore (se `crea_nuovo`) nella collezione
    target e rimette il documento tra i "da associare", pronto per essere
    riclassificato con la collezione giusta."""
    db = Database.get_db()
    doc = await db["documenti_non_associati"].find_one({"id": documento_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    if not doc.get("associato"):
        raise HTTPException(status_code=400, detail="Il documento non risulta associato")

    collezione = doc.get("associato_a")
    record_id = doc.get("associato_id")
    record_rimosso = False
    if collezione and record_id:
        target = await db[collezione].find_one({"id": record_id}, {"_id": 0})
        # Rimuove il record SOLO se creato da questa stessa associazione
        # manuale (source="associazione_manuale" collegato a questo
        # documento): mai toccare un record esistente arricchito col PDF
        # (crea_nuovo=False, associa a record_esistente_id).
        if target and target.get("source") == "associazione_manuale" \
                and target.get("documento_originale_id") == documento_id:
            await db[collezione].delete_one({"id": record_id})
            record_rimosso = True

    await db["documenti_non_associati"].update_one(
        {"id": documento_id},
        {"$unset": {"associato": "", "associato_a": "", "associato_id": "", "associato_at": ""}}
    )

    return {
        "success": True,
        "collezione_precedente": collezione,
        "record_rimosso": record_rimosso,
    }


@router.get("/associati-di-recente")
async def documenti_associati_di_recente(limit: int = Query(default=20, le=100)) -> Dict[str, Any]:
    """Ultimi documenti associati manualmente, per poter annullare
    un'associazione sbagliata (vedi /de-associa)."""
    db = Database.get_db()
    documenti = await db["documenti_non_associati"].find(
        {"associato": True},
        {"_id": 0, "pdf_data": 0}
    ).sort("associato_at", -1).limit(limit).to_list(limit)
    return {"documenti": documenti}


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


@router.delete("/{documento_id}")
async def elimina_documento(documento_id: str) -> Dict[str, Any]:
    """Elimina un documento non associato."""
    db = Database.get_db()
    
    result = await db["documenti_non_associati"].delete_one({"id": documento_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    
    return {"success": True, "deleted": True}
