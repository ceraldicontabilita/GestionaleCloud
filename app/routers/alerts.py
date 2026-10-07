"""
Router per gestione Alert di sistema.
Include alert per fornitori senza metodo pagamento, scadenze, etc.
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from urllib.parse import quote
import logging

from app.database import Database
from app.middleware.performance import istantanea

logger = logging.getLogger(__name__)
router = APIRouter()


# I deep-link canonici letti dalle pagine (CLAUDE.md, «Navigazione tra
# contropartite»): un alert si apre sul record, non sulla pagina generica.
_LINK_PER_COLLEZIONE = {
    "invoices": "/fatture?invoice_id={id}",
    "fatture": "/fatture?invoice_id={id}",
    "estratto_conto_movimenti": "/riconciliazione/banca?movimento={id}",
    "prima_nota_banca": "/prima-nota#sezione=banca&selected={id}",
}


def link_record(collezione: Any, record_id: Any) -> Optional[str]:
    """Il deep-link canonico di un record, o None se la collezione non ne ha."""
    modello = _LINK_PER_COLLEZIONE.get(str(collezione or ""))
    if not modello or record_id in (None, ""):
        return None
    return modello.format(id=quote(str(record_id), safe=""))


def arricchisci_alert(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Aggiunge all'alert il collegamento al record e i record coinvolti.

    6.527 alert su 6.536 non avevano ``link``: la pagina diceva «verificare la
    fonte indicata nel dettaglio» anche quando l'alert sapeva benissimo di
    quale fattura o movimento parlava (``entita_collection``/``entita_id``).
    Le fatture candidate di un pagamento cumulativo stavano in ``extra`` e
    non si vedevano: escono come lista, ognuna col suo collegamento.
    """
    item = dict(alert)
    record_link = link_record(item.get("entita_collection"), item.get("entita_id"))
    if not item.get("link") and record_link:
        item["link"] = record_link
    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    candidate = extra.get("fatture_candidate")
    fatture: List[Dict[str, Any]] = []
    if isinstance(candidate, list):
        for fattura in candidate:
            if not isinstance(fattura, dict):
                continue
            fatture.append({
                "id": fattura.get("id"),
                "numero": fattura.get("numero"),
                "importo": fattura.get("importo"),
                "link": link_record("invoices", fattura.get("id")),
            })
    item["fatture_candidate"] = fatture
    record: List[Dict[str, Any]] = []
    if item.get("entita_id"):
        record.append({
            "collezione": item.get("entita_collection"),
            "id": item.get("entita_id"),
            "link": record_link,
        })
    if extra.get("fattura_id") and not any(f["id"] == extra["fattura_id"] for f in fatture):
        record.append({
            "collezione": "invoices",
            "id": extra["fattura_id"],
            "link": link_record("invoices", extra["fattura_id"]),
        })
    item["record_coinvolti"] = record
    return item


@router.get("/summary")
@istantanea(ttl=30, max_eta=600)
async def alerts_summary() -> Dict[str, Any]:
    """
    Summary degli alert APERTI del sistema relazionale, aggregati per severità e modulo.
    Usato dal badge nella topnav per mostrare il conteggio visibile all'utente.

    Compatibile con entrambi gli schemi alert:
    - Schema legacy: {letto: bool, risolto: bool}
    - Schema relazionale: {stato: "aperto"|"risolto", severita: "critical"|"warning"|"info"}
    """
    db = Database.get_db()

    # Query: alert aperti nello schema relazionale (stato="aperto")
    # OR alert legacy non risolti (risolto=false)
    query_open = {
        "$or": [
            {"stato": "aperto"},
            {"$and": [
                {"stato": {"$exists": False}},
                {"risolto": {"$ne": True}}
            ]}
        ]
    }

    # Conteggio per severità
    per_severita: Dict[str, int] = {"critical": 0, "warning": 0, "info": 0}
    pipeline_sev = [
        {"$match": query_open},
        {"$group": {"_id": "$severita", "count": {"$sum": 1}}}
    ]
    async for doc in db["alerts"].aggregate(pipeline_sev):
        # Si SOMMA: gli alert senza gravita' contano come info, e prima il loro
        # conteggio (8) sovrascriveva quello degli info veri (3.201) — la
        # campana diceva 3.023 aperti, la pagina 6.224 (25/09/2026).
        sev = doc["_id"] if doc["_id"] in per_severita else "info"
        per_severita[sev] += doc["count"]

    # Conteggio per modulo
    per_modulo: Dict[str, int] = {}
    pipeline_mod = [
        {"$match": query_open},
        {"$group": {"_id": "$modulo", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    async for doc in db["alerts"].aggregate(pipeline_mod):
        if doc["_id"]:
            per_modulo[doc["_id"]] = doc["count"]

    # Top 5 alert critici recenti (per dropdown)
    critical_recenti = await db["alerts"].find(
        {**query_open, "severita": "critical"},
        {"_id": 0, "id": 1, "codice": 1, "titolo": 1, "dettaglio": 1,
         "modulo": 1, "severita": 1, "created_at": 1, "entita_id": 1,
         "entita_collection": 1, "link": 1}
    ).sort("created_at", -1).limit(5).to_list(5)
    critical_recenti = [arricchisci_alert(alert) for alert in critical_recenti]

    # Il totale e' un conteggio diretto con lo stesso filtro della lista:
    # campana e pagina non possono piu' dire due numeri diversi.
    totale = await db["alerts"].count_documents(query_open)

    return {
        "totale_aperti": totale,
        "per_severita": per_severita,
        "per_modulo": per_modulo,
        "critical_recenti": critical_recenti,
    }

@router.get("/lista")
async def lista_alerts(
    tipo: Optional[str] = Query(None, description="Filtra per tipo alert"),
    severita: Optional[str] = Query(None, description="Filtra per severità"),
    modulo: Optional[str] = Query(None, description="Filtra per modulo"),
    alert_id: Optional[str] = Query(None, description="Apre un alert preciso"),
    stato: Optional[str] = Query(None, pattern="^(aperto|risolto)$"),
    letto: Optional[bool] = Query(None, description="Filtra per letto/non letto"),
    risolto: Optional[bool] = Query(None, description="Filtra per risolto/non risolto"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """
    Lista tutti gli alert di sistema.
    """
    db = Database.get_db()
    
    query: Dict[str, Any] = {}
    if tipo:
        query["tipo"] = tipo
    if severita:
        query["severita"] = severita
    if modulo:
        query["modulo"] = modulo
    if alert_id:
        query["id"] = alert_id
    if stato == "aperto":
        query["$or"] = [
            {"stato": "aperto"},
            {"stato": {"$exists": False}, "risolto": {"$ne": True}},
        ]
    elif stato == "risolto":
        query["$or"] = [{"stato": "risolto"}, {"risolto": True}]
    if letto is not None:
        query["letto"] = letto
    if risolto is not None:
        query["risolto"] = risolto

    totale_filtrato = await db["alerts"].count_documents(query)
    alerts = await db["alerts"].find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).skip(offset).limit(limit).to_list(limit)
    alerts = [arricchisci_alert(alert) for alert in alerts]

    # Statistiche
    totale = await db["alerts"].count_documents({})
    non_letti = await db["alerts"].count_documents({"letto": False})
    non_risolti = await db["alerts"].count_documents({"risolto": False})
    
    # Conta per tipo
    pipeline = [
        {"$group": {"_id": "$tipo", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    per_tipo = {}
    async for doc in db["alerts"].aggregate(pipeline):
        if doc["_id"]:
            per_tipo[doc["_id"]] = doc["count"]
    
    return {
        "alerts": alerts,
        "stats": {
            "totale": totale,
            "totale_filtrato": totale_filtrato,
            "non_letti": non_letti,
            "non_risolti": non_risolti,
            "per_tipo": per_tipo
        },
        "pagination": {
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(alerts) < totale_filtrato,
        },
    }


@router.get("/fornitori-senza-metodo")
async def alerts_fornitori_senza_metodo() -> Dict[str, Any]:
    """
    Lista alert specifici per fornitori senza metodo pagamento configurato.
    """
    db = Database.get_db()
    
    alerts = await db["alerts"].find(
        {"tipo": "fornitore_senza_metodo_pagamento", "risolto": False},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    return {
        "alerts": alerts,
        "count": len(alerts)
    }


@router.post("/{alert_id}/segna-letto")
async def segna_alert_letto(alert_id: str) -> Dict[str, Any]:
    """Segna un alert come letto."""
    db = Database.get_db()
    
    result = await db["alerts"].update_one(
        {"id": alert_id},
        {"$set": {"letto": True, "letto_il": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert non trovato")
    
    return {"success": True, "message": "Alert segnato come letto"}


@router.post("/{alert_id}/risolvi")
async def risolvi_alert(alert_id: str) -> Dict[str, Any]:
    """Segna un alert come risolto."""
    db = Database.get_db()
    
    result = await db["alerts"].update_one(
        {"id": alert_id},
        {"$set": {
            "risolto": True, 
            "risolto_il": datetime.now(timezone.utc).isoformat(),
            "letto": True
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert non trovato")
    
    return {"success": True, "message": "Alert risolto"}


@router.delete("/{alert_id}")
async def elimina_alert(alert_id: str) -> Dict[str, Any]:
    """Elimina un alert."""
    db = Database.get_db()
    
    result = await db["alerts"].delete_one({"id": alert_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Alert non trovato")
    
    return {"success": True, "message": "Alert eliminato"}


@router.post("/risolvi-fornitore/{fornitore_piva}")
async def risolvi_alerts_fornitore(fornitore_piva: str) -> Dict[str, Any]:
    """
    Risolve automaticamente tutti gli alert per un fornitore 
    quando viene configurato il metodo di pagamento.
    """
    db = Database.get_db()
    
    result = await db["alerts"].update_many(
        {
            "tipo": "fornitore_senza_metodo_pagamento",
            "fornitore_piva": fornitore_piva,
            "risolto": False
        },
        {"$set": {
            "risolto": True,
            "risolto_il": datetime.now(timezone.utc).isoformat(),
            "note_risoluzione": "Metodo pagamento configurato"
        }}
    )
    
    return {
        "success": True,
        "alerts_risolti": result.modified_count
    }
