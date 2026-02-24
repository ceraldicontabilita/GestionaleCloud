"""
Router Gestione Avanzata F24
- Archivio F24 Originali e Ravveduti
- Database Codici Tributo Pagati
- Report Mensili
- Alert Scadenze
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone
import logging

from app.database import Database
from app.services.f24_gestione_avanzata import (
    StatoF24, TipoF24, CategoriaArchivio,
    identifica_f24_correlati,
    riconcilia_f24_avanzato,
    genera_report_mensile
)

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# UPLOAD E CLASSIFICAZIONE F24
# =============================================================================

@router.post("/classifica-f24/{f24_id}")
async def classifica_f24(f24_id: str):
    """
    Analizza un F24 e lo classifica:
    - Identifica se è un ravvedimento
    - Trova l'F24 originale correlato
    - Suggerisce la categorizzazione
    """
    db = Database.get_db()
    
    # Recupera F24
    f24 = await db["f24_unificato"].find_one({"id": f24_id}, {"_id": 0})
    if not f24:
        raise HTTPException(status_code=404, detail="F24 non trovato")
    
    # Recupera tutti gli F24 per confronto
    f24_esistenti = await db["f24_unificato"].find(
        {"id": {"$ne": f24_id}},
        {"_id": 0}
    ).to_list(1000)
    
    # Analizza correlazioni
    analisi = identifica_f24_correlati(f24, f24_esistenti)
    
    return {
        "f24_id": f24_id,
        "file_name": f24.get("file_name"),
        "has_ravvedimento": f24.get("has_ravvedimento", False),
        "codici_ravvedimento": f24.get("codici_ravvedimento", []),
        "analisi": analisi,
        "azioni_suggerite": []
    }


@router.post("/imposta-tipo-f24/{f24_id}")
async def imposta_tipo_f24(
    f24_id: str,
    tipo: TipoF24,
    f24_originale_id: Optional[str] = None
):
    """
    Imposta il tipo di un F24 (ORIGINALE, RAVVEDIMENTO, SOSTITUTIVO).
    Se è un ravvedimento, collega all'F24 originale.
    """
    db = Database.get_db()
    
    update_data = {
        "tipo_f24": tipo.value,
        "updated_at": datetime.now(timezone.utc)
    }
    
    if tipo == TipoF24.RAVVEDIMENTO and f24_originale_id:
        # Verifica che l'originale esista
        originale = await db["f24_unificato"].find_one({"id": f24_originale_id})
        if not originale:
            raise HTTPException(status_code=404, detail="F24 originale non trovato")
        
        update_data["f24_originale_sostituito"] = f24_originale_id
        
        # Marca l'originale come "potenzialmente sostituito"
        await db["f24_unificato"].update_one(
            {"id": f24_originale_id},
            {"$set": {
                "ha_ravvedimento_collegato": f24_id,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
    
    result = await db["f24_unificato"].update_one(
        {"id": f24_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="F24 non trovato")
    
    return {
        "success": True,
        "f24_id": f24_id,
        "tipo": tipo.value,
        "f24_originale_collegato": f24_originale_id
    }


# =============================================================================
# RICONCILIAZIONE AVANZATA
# =============================================================================

@router.post("/riconcilia-avanzato")
async def esegui_riconciliazione_avanzata():
    """
    Esegue la riconciliazione avanzata:
    1. Match F24 con estratto conto
    2. Gestisce F24 originali vs ravveduti
    3. Popola database tributi pagati
    4. Genera alert
    """
    db = Database.get_db()
    
    # Recupera dati
    f24_list = await db["f24_unificato"].find({}, {"_id": 0}).to_list(1000)
    movimenti_f24 = await db["movimenti_f24_banca"].find({}, {"_id": 0}).to_list(1000)
    quietanze = await db["quietanze_f24"].find({}, {"_id": 0}).to_list(1000)
    
    if not f24_list:
        return {"success": False, "message": "Nessun F24 caricato"}
    
    # Esegui riconciliazione
    result = riconcilia_f24_avanzato(f24_list, movimenti_f24, quietanze)
    
    # Aggiorna stato F24 nel database
    for f24_pagato in result["f24_pagati"]:
        await db["f24_unificato"].update_one(
            {"id": f24_pagato.get("id")},
            {"$set": {
                "stato": StatoF24.PAGATO.value,
                "data_pagamento": f24_pagato.get("data_pagamento"),
                "movimento_bancario": f24_pagato.get("movimento_bancario"),
                "updated_at": datetime.now(timezone.utc)
            }}
        )
    
    for f24_da_pagare in result["f24_da_pagare"]:
        await db["f24_unificato"].update_one(
            {"id": f24_da_pagare.get("id")},
            {"$set": {
                "stato": StatoF24.DA_PAGARE.value,
                "scadenza_stimata": f24_da_pagare.get("scadenza_stimata"),
                "updated_at": datetime.now(timezone.utc)
            }}
        )
    
    # Archivia F24 sostituiti
    for f24_sost in result["f24_sostituiti"]:
        await db["f24_unificato"].update_one(
            {"id": f24_sost.get("id")},
            {"$set": {
                "stato": StatoF24.SOSTITUITO.value,
                "categoria_archivio": CategoriaArchivio.ORIGINALI_SOSTITUITI.value,
                "sostituito_da": f24_sost.get("sostituito_da"),
                "data_sostituzione": f24_sost.get("data_sostituzione"),
                "updated_at": datetime.now(timezone.utc)
            }}
        )
    
    # Salva tributi pagati nel database dedicato
    if result["tributi_pagati"]:
        for tributo in result["tributi_pagati"]:
            tributo["created_at"] = datetime.now(timezone.utc)
            # Upsert per evitare duplicati
            await db["tributi_pagati"].update_one(
                {
                    "codice_tributo": tributo.get("codice_tributo"),
                    "periodo": tributo.get("periodo"),
                    "f24_id": tributo.get("f24_id")
                },
                {"$set": tributo},
                upsert=True
            )
    
    # Salva alert
    if result["alert"]:
        for alert in result["alert"]:
            alert["created_at"] = datetime.now(timezone.utc)
            alert["letto"] = False
            await db["alert_f24"].update_one(
                {"f24_id": alert.get("f24_id"), "tipo": alert.get("tipo")},
                {"$set": alert},
                upsert=True
            )
    
    return {
        "success": True,
        "stats": result["stats"],
        "f24_pagati": [{
            "id": f.get("id"),
            "file_name": f.get("file_name"),
            "importo": f.get("totali", {}).get("saldo_netto"),
            "data_pagamento": f.get("data_pagamento"),
            "is_ravvedimento": f.get("has_ravvedimento", False)
        } for f in result["f24_pagati"]],
        "f24_da_pagare": [{
            "id": f.get("id"),
            "file_name": f.get("file_name"),
            "importo": f.get("totali", {}).get("saldo_netto"),
            "scadenza": f.get("scadenza_stimata")
        } for f in result["f24_da_pagare"]],
        "f24_sostituiti": [{
            "id": f.get("id"),
            "file_name": f.get("file_name"),
            "sostituito_da": f.get("sostituito_da")
        } for f in result["f24_sostituiti"]],
        "alert": result["alert"],
        "tributi_registrati": len(result["tributi_pagati"])
    }


# =============================================================================
# DATABASE CODICI TRIBUTO
# =============================================================================

@router.get("/tributi-pagati")
async def get_tributi_pagati(
    anno: Optional[int] = None,
    tipo: Optional[str] = None,  # ERARIO, INPS, INAIL, REGIONI, TRIBUTI_LOCALI
    codice_tributo: Optional[str] = None,
    codice_regione: Optional[str] = None,
    codice_comune: Optional[str] = None,
    is_ravvedimento: Optional[bool] = None,
    limit: int = Query(default=100, le=1000)
):
    """
    Recupera i tributi pagati con filtri avanzati.
    """
    db = Database.get_db()
    
    query = {}
    
    if anno:
        query["anno"] = str(anno)
    if tipo:
        query["tipo"] = tipo.upper()
    if codice_tributo:
        query["codice_tributo"] = codice_tributo
    if codice_regione:
        query["codice_regione"] = codice_regione
    if codice_comune:
        query["codice_comune"] = codice_comune
    if is_ravvedimento is not None:
        query["is_ravvedimento"] = is_ravvedimento
    
    tributi = await db["tributi_pagati"].find(
        query,
        {"_id": 0}
    ).sort("data_pagamento", -1).limit(limit).to_list(limit)
    
    # Calcola totali
    totale_debito = sum(t.get("importo_debito", 0) for t in tributi)
    totale_credito = sum(t.get("importo_credito", 0) for t in tributi)
    
    # Raggruppa per tipo
    per_tipo = {}
    for t in tributi:
        tipo_t = t.get("tipo", "ALTRO")
        if tipo_t not in per_tipo:
            per_tipo[tipo_t] = 0
        per_tipo[tipo_t] += t.get("importo_debito", 0) - t.get("importo_credito", 0)
    
    return {
        "tributi": tributi,
        "count": len(tributi),
        "totale_debito": round(totale_debito, 2),
        "totale_credito": round(totale_credito, 2),
        "totale_netto": round(totale_debito - totale_credito, 2),
        "riepilogo_per_tipo": {k: round(v, 2) for k, v in per_tipo.items()},
        "filtri_applicati": query
    }


@router.get("/tributi-per-anno/{anno}")
async def get_tributi_per_anno(anno: int):
    """
    Riepilogo annuale tributi pagati, raggruppati per tipo e mese.
    """
    db = Database.get_db()
    
    # Aggregazione per mese e tipo
    pipeline = [
        {"$match": {"anno": str(anno)}},
        {"$addFields": {
            "mese": {"$substr": ["$data_pagamento", 5, 2]}
        }},
        {"$group": {
            "_id": {"tipo": "$tipo", "mese": "$mese"},
            "totale_debito": {"$sum": "$importo_debito"},
            "totale_credito": {"$sum": "$importo_credito"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id.mese": 1, "_id.tipo": 1}}
    ]
    
    results = await db["tributi_pagati"].aggregate(pipeline).to_list(200)
    
    # Riorganizza per tipo e mese
    per_tipo = {}
    per_mese = {}
    
    for r in results:
        tipo = r["_id"]["tipo"]
        mese = r["_id"]["mese"]
        netto = r["totale_debito"] - r["totale_credito"]
        
        if tipo not in per_tipo:
            per_tipo[tipo] = {"totale": 0, "count": 0, "mesi": {}}
        per_tipo[tipo]["totale"] += netto
        per_tipo[tipo]["count"] += r["count"]
        per_tipo[tipo]["mesi"][mese] = round(netto, 2)
        
        if mese not in per_mese:
            per_mese[mese] = 0
        per_mese[mese] += netto
    
    # Round totali
    for tipo in per_tipo:
        per_tipo[tipo]["totale"] = round(per_tipo[tipo]["totale"], 2)
    per_mese = {k: round(v, 2) for k, v in per_mese.items()}
    
    totale_anno = sum(t["totale"] for t in per_tipo.values())
    
    return {
        "anno": anno,
        "totale_anno": round(totale_anno, 2),
        "per_tipo": per_tipo,
        "per_mese": per_mese
    }


# =============================================================================
# ARCHIVI F24
# =============================================================================

@router.get("/archivio/originali-sostituiti")
async def get_f24_originali_sostituiti():
    """
    Lista F24 originali che sono stati sostituiti da ravvedimenti.
    """
    db = Database.get_db()
    
    f24_list = await db["f24_unificato"].find(
        {"stato": StatoF24.SOSTITUITO.value},
        {"_id": 0}
    ).sort("data_sostituzione", -1).to_list(100)
    
    return {
        "archivio": "ORIGINALI_SOSTITUITI",
        "f24_list": [{
            "id": f.get("id"),
            "file_name": f.get("file_name"),
            "importo": f.get("totali", {}).get("saldo_netto"),
            "sostituito_da": f.get("sostituito_da"),
            "data_sostituzione": f.get("data_sostituzione")
        } for f in f24_list],
        "count": len(f24_list)
    }


@router.get("/archivio/ravveduti")
async def get_f24_ravveduti():
    """
    Lista F24 pagati con ravvedimento.
    """
    db = Database.get_db()
    
    f24_list = await db["f24_unificato"].find(
        {
            "has_ravvedimento": True,
            "stato": StatoF24.PAGATO.value
        },
        {"_id": 0}
    ).sort("data_pagamento", -1).to_list(100)
    
    return {
        "archivio": "RAVVEDUTI",
        "f24_list": [{
            "id": f.get("id"),
            "file_name": f.get("file_name"),
            "importo": f.get("totali", {}).get("saldo_netto"),
            "codici_ravvedimento": f.get("codici_ravvedimento", []),
            "f24_originale": f.get("f24_originale_sostituito"),
            "data_pagamento": f.get("data_pagamento")
        } for f in f24_list],
        "count": len(f24_list)
    }


# =============================================================================
# ALERT E REPORT
# =============================================================================

@router.get("/alert")
async def get_alert_f24(
    solo_non_letti: bool = True,
    priorita: Optional[str] = None  # ALTA, MEDIA, BASSA
):
    """
    Recupera gli alert F24 attivi.
    """
    db = Database.get_db()
    
    query = {}
    if solo_non_letti:
        query["letto"] = False
    if priorita:
        query["priorita"] = priorita.upper()
    
    alert = await db["alert_f24"].find(
        query,
        {"_id": 0}
    ).sort([("priorita", 1), ("created_at", -1)]).to_list(100)
    
    return {
        "alert": alert,
        "count": len(alert),
        "alert_alta_priorita": len([a for a in alert if a.get("priorita") == "ALTA"])
    }


@router.post("/alert/{alert_id}/letto")
async def segna_alert_letto(alert_id: str):
    """Segna un alert come letto."""
    db = Database.get_db()
    
    result = await db["alert_f24"].update_one(
        {"f24_id": alert_id},
        {"$set": {"letto": True, "letto_il": datetime.now(timezone.utc)}}
    )
    
    return {"success": result.modified_count > 0}


@router.get("/report-mensile/{anno}/{mese}")
async def get_report_mensile(anno: int, mese: int):
    """
    Genera report mensile completo.
    """
    db = Database.get_db()
    
    # Recupera dati
    tributi = await db["tributi_pagati"].find({}, {"_id": 0}).to_list(10000)
    f24_pagati = await db["f24_unificato"].find(
        {"stato": StatoF24.PAGATO.value},
        {"_id": 0}
    ).to_list(1000)
    f24_da_pagare = await db["f24_unificato"].find(
        {"stato": StatoF24.DA_PAGARE.value},
        {"_id": 0}
    ).to_list(1000)
    
    report = genera_report_mensile(tributi, f24_pagati, f24_da_pagare, anno, mese)
    
    return report


@router.get("/dashboard-f24")
async def dashboard_f24():
    """
    Dashboard completa stato F24.
    """
    db = Database.get_db()
    
    # Conta per stato
    totale = await db["f24_unificato"].count_documents({})
    pagati = await db["f24_unificato"].count_documents({"stato": StatoF24.PAGATO.value})
    da_pagare = await db["f24_unificato"].count_documents({"stato": StatoF24.DA_PAGARE.value})
    sostituiti = await db["f24_unificato"].count_documents({"stato": StatoF24.SOSTITUITO.value})
    ravvedimenti = await db["f24_unificato"].count_documents({"has_ravvedimento": True})
    
    # Alert non letti
    alert_count = await db["alert_f24"].count_documents({"letto": False})
    alert_alta = await db["alert_f24"].count_documents({"letto": False, "priorita": "ALTA"})
    
    # Totali importi
    pipeline = [
        {"$group": {
            "_id": "$stato",
            "totale": {"$sum": "$totali.saldo_netto"}
        }}
    ]
    totali = {doc["_id"]: doc["totale"] async for doc in db["f24_unificato"].aggregate(pipeline)}
    
    # Tributi per tipo (anno corrente)
    anno_corrente = str(datetime.now().year)
    pipeline_tributi = [
        {"$match": {"anno": anno_corrente}},
        {"$group": {
            "_id": "$tipo",
            "totale": {"$sum": {"$subtract": ["$importo_debito", "$importo_credito"]}}
        }}
    ]
    tributi_per_tipo = {
        doc["_id"]: round(doc["totale"], 2) 
        async for doc in db["tributi_pagati"].aggregate(pipeline_tributi)
    }
    
    return {
        "f24": {
            "totale": totale,
            "pagati": pagati,
            "da_pagare": da_pagare,
            "sostituiti": sostituiti,
            "ravvedimenti": ravvedimenti
        },
        "importi": {
            "pagati": round(totali.get(StatoF24.PAGATO.value, 0), 2),
            "da_pagare": round(totali.get(StatoF24.DA_PAGARE.value, 0), 2)
        },
        "alert": {
            "totale": alert_count,
            "alta_priorita": alert_alta
        },
        "tributi_anno_corrente": tributi_per_tipo,
        "anno_corrente": anno_corrente
    }
