"""
Router API per Riconciliazione Intelligente
=============================================

Endpoint per gestione conferma pagamenti e riconciliazione automatica.

Endpoints:
- GET /dashboard - Dashboard operazioni da verificare
- POST /conferma-pagamento - Conferma metodo pagamento fattura
- POST /applica-spostamento - Applica spostamento Cassa→Banca
- POST /rianalizza - Ri-analizza operazioni dopo nuovo estratto
- GET /fatture-da-confermare - Lista fatture in attesa conferma
- GET /spostamenti-proposti - Lista spostamenti proposti
- GET /stato-estratto - Info su copertura estratto conto
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any
from datetime import datetime, timezone

from app.database import Database
from app.services.riconciliazione_intelligente import (
    get_riconciliazione_service,
    StatoRiconciliazione
)

import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# DASHBOARD
# =============================================================================


@router.get("/stats")
async def get_stats_riconciliazione() -> Dict[str, Any]:
    """Statistiche rapide riconciliazione intelligente."""
    db = Database.get_db()
    
    # Conta fatture per stato riconciliazione
    pipeline = [
        {"$group": {"_id": "$stato_riconciliazione", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    stati = await db["invoices"].aggregate(pipeline).to_list(20)
    
    totale = await db["invoices"].count_documents({})
    da_confermare = await db["invoices"].count_documents(
        {"stato_riconciliazione": {"$in": ["attesa_conferma", "incerto", "sospeso"]}}
    )
    
    return {
        "totale_fatture": totale,
        "da_confermare": da_confermare,
        "stati": {s["_id"] or "non_classificato": s["count"] for s in stati},
        "aggiornato_al": __import__("datetime").datetime.now().isoformat()
    }

@router.get("/dashboard")
async def get_dashboard_riconciliazione() -> Dict[str, Any]:
    """
    Dashboard completa delle operazioni da verificare.
    
    Ritorna conteggi e liste per:
    - Fatture in attesa conferma metodo
    - Spostamenti proposti (cassa→banca)
    - Match incerti da verificare
    - Operazioni sospese (attesa estratto)
    - Anomalie
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    # Ultima data estratto
    ultima_data_estratto = await service.get_ultima_data_estratto()
    
    # Conteggi per stato
    stati_count = {}
    for stato in StatoRiconciliazione:
        count = await db["invoices"].count_documents({
            "stato_riconciliazione": stato.value
        })
        stati_count[stato.value] = count
    
    # Fatture in attesa conferma (limit 50)
    # Nota: I campi possono essere sia nel formato standard che nel formato legacy
    in_attesa_raw = await db["invoices"].find(
        {"stato_riconciliazione": StatoRiconciliazione.IN_ATTESA_CONFERMA.value},
        {"_id": 0}
    ).sort([("data_documento", -1), ("invoice_date", -1)]).to_list(50)
    
    # Normalizza i campi
    in_attesa = []
    for f in in_attesa_raw:
        in_attesa.append({
            "id": f.get("id"),
            "numero_documento": f.get("numero_documento") or f.get("invoice_number"),
            "data_documento": f.get("data_documento") or f.get("invoice_date"),
            "importo_totale": f.get("importo_totale") or f.get("total_amount", 0),
            "fornitore_ragione_sociale": f.get("fornitore_ragione_sociale") or f.get("supplier_name"),
            "metodo_pagamento": f.get("metodo_pagamento")
        })
    
    # Spostamenti proposti (limit 50)
    spostamenti_raw = await db["invoices"].find(
        {"stato_riconciliazione": StatoRiconciliazione.DA_VERIFICARE_SPOSTAMENTO.value},
        {"_id": 0}
    ).sort([("data_documento", -1), ("invoice_date", -1)]).to_list(50)
    
    spostamenti = []
    for f in spostamenti_raw:
        spostamenti.append({
            "id": f.get("id"),
            "numero_documento": f.get("numero_documento") or f.get("invoice_number"),
            "data_documento": f.get("data_documento") or f.get("invoice_date"),
            "importo_totale": f.get("importo_totale") or f.get("total_amount", 0),
            "fornitore_ragione_sociale": f.get("fornitore_ragione_sociale") or f.get("supplier_name"),
            "match_estratto_proposto": f.get("match_estratto_proposto")
        })
    
    # Match incerti (limit 50)
    match_incerti_raw = await db["invoices"].find(
        {"stato_riconciliazione": StatoRiconciliazione.DA_VERIFICARE_MATCH_INCERTO.value},
        {"_id": 0}
    ).sort([("data_documento", -1), ("invoice_date", -1)]).to_list(50)
    
    match_incerti = []
    for f in match_incerti_raw:
        match_incerti.append({
            "id": f.get("id"),
            "numero_documento": f.get("numero_documento") or f.get("invoice_number"),
            "data_documento": f.get("data_documento") or f.get("invoice_date"),
            "importo_totale": f.get("importo_totale") or f.get("total_amount", 0),
            "fornitore_ragione_sociale": f.get("fornitore_ragione_sociale") or f.get("supplier_name"),
            "match_estratto_proposto": f.get("match_estratto_proposto")
        })
    
    # Sospese (limit 50)
    sospese_raw = await db["invoices"].find(
        {"stato_riconciliazione": StatoRiconciliazione.SOSPESA_ATTESA_ESTRATTO.value},
        {"_id": 0}
    ).sort([("data_documento", -1), ("invoice_date", -1)]).to_list(50)
    
    sospese = []
    for f in sospese_raw:
        sospese.append({
            "id": f.get("id"),
            "numero_documento": f.get("numero_documento") or f.get("invoice_number"),
            "data_documento": f.get("data_documento") or f.get("invoice_date"),
            "importo_totale": f.get("importo_totale") or f.get("total_amount", 0),
            "fornitore_ragione_sociale": f.get("fornitore_ragione_sociale") or f.get("supplier_name")
        })
    
    # Anomalie (limit 50)
    anomalie_raw = await db["invoices"].find(
        {"stato_riconciliazione": StatoRiconciliazione.ANOMALIA_NON_IN_ESTRATTO.value},
        {"_id": 0}
    ).sort([("data_documento", -1), ("invoice_date", -1)]).to_list(50)
    
    anomalie = []
    for f in anomalie_raw:
        anomalie.append({
            "id": f.get("id"),
            "numero_documento": f.get("numero_documento") or f.get("invoice_number"),
            "data_documento": f.get("data_documento") or f.get("invoice_date"),
            "importo_totale": f.get("importo_totale") or f.get("total_amount", 0),
            "fornitore_ragione_sociale": f.get("fornitore_ragione_sociale") or f.get("supplier_name"),
            "metodo_pagamento_confermato": f.get("metodo_pagamento_confermato")
        })
    
    return {
        "success": True,
        "ultima_data_estratto": ultima_data_estratto,
        "conteggi": stati_count,
        "totale_da_verificare": (
            stati_count.get(StatoRiconciliazione.IN_ATTESA_CONFERMA.value, 0) +
            stati_count.get(StatoRiconciliazione.DA_VERIFICARE_SPOSTAMENTO.value, 0) +
            stati_count.get(StatoRiconciliazione.DA_VERIFICARE_MATCH_INCERTO.value, 0) +
            stati_count.get(StatoRiconciliazione.SOSPESA_ATTESA_ESTRATTO.value, 0) +
            stati_count.get(StatoRiconciliazione.ANOMALIA_NON_IN_ESTRATTO.value, 0)
        ),
        "fatture_in_attesa_conferma": in_attesa,
        "spostamenti_proposti": spostamenti,
        "match_incerti": match_incerti,
        "sospese_attesa_estratto": sospese,
        "anomalie": anomalie
    }


# =============================================================================
# CONFERMA PAGAMENTO
# =============================================================================

@router.post("/conferma-pagamento")
async def conferma_pagamento(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Conferma il metodo di pagamento per una fattura.
    
    Payload:
    {
        "fattura_id": "uuid",
        "metodo": "cassa" | "banca",
        "data_pagamento": "YYYY-MM-DD" (opzionale, default: data fattura),
        "note": "Note aggiuntive" (opzionale)
    }
    
    Returns:
        Risultato con nuovo stato, movimento creato, eventuali warning
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    fattura_id = payload.get("fattura_id")
    metodo = payload.get("metodo", "").lower()
    data_pagamento = payload.get("data_pagamento")
    note = payload.get("note", "")
    
    if not fattura_id:
        raise HTTPException(status_code=400, detail="fattura_id obbligatorio")
    
    if metodo not in ["cassa", "banca"]:
        raise HTTPException(status_code=400, detail="metodo deve essere 'cassa' o 'banca'")
    
    risultato = await service.conferma_pagamento(
        fattura_id=fattura_id,
        metodo=metodo,
        data_pagamento=data_pagamento,
        note=note
    )
    
    if not risultato.get("success"):
        raise HTTPException(status_code=400, detail=risultato.get("error", "Errore sconosciuto"))
    
    return risultato


@router.post("/conferma-multipla")
async def conferma_pagamento_multipla(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Conferma il metodo di pagamento per multiple fatture.
    
    Payload:
    {
        "fatture": [
            {"fattura_id": "uuid1", "metodo": "cassa"},
            {"fattura_id": "uuid2", "metodo": "banca"},
            ...
        ]
    }
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    fatture = payload.get("fatture", [])
    if not fatture:
        raise HTTPException(status_code=400, detail="Lista fatture vuota")
    
    risultati = {
        "success": True,
        "processate": 0,
        "errori": 0,
        "dettagli": []
    }
    
    for item in fatture:
        fattura_id = item.get("fattura_id")
        metodo = item.get("metodo", "").lower()
        
        if not fattura_id or metodo not in ["cassa", "banca"]:
            risultati["errori"] += 1
            risultati["dettagli"].append({
                "fattura_id": fattura_id,
                "success": False,
                "error": "Dati non validi"
            })
            continue
        
        try:
            ris = await service.conferma_pagamento(
                fattura_id=fattura_id,
                metodo=metodo
            )
            risultati["processate"] += 1
            risultati["dettagli"].append({
                "fattura_id": fattura_id,
                "success": ris.get("success"),
                "stato": ris.get("stato_riconciliazione"),
                "warnings": ris.get("warnings", [])
            })
        except Exception as e:
            risultati["errori"] += 1
            risultati["dettagli"].append({
                "fattura_id": fattura_id,
                "success": False,
                "error": str(e)
            })
    
    return risultati


# =============================================================================
# SPOSTAMENTO CASSA → BANCA
# =============================================================================

@router.post("/applica-spostamento")
async def applica_spostamento(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Applica o rifiuta lo spostamento da Cassa a Banca.
    
    Payload:
    {
        "fattura_id": "uuid",
        "movimento_estratto_id": "uuid",
        "conferma": true | false  // true = sposta, false = mantieni cassa (lock)
    }
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    fattura_id = payload.get("fattura_id")
    movimento_estratto_id = payload.get("movimento_estratto_id")
    conferma = payload.get("conferma", True)
    
    if not fattura_id:
        raise HTTPException(status_code=400, detail="fattura_id obbligatorio")
    
    if conferma and not movimento_estratto_id:
        raise HTTPException(status_code=400, detail="movimento_estratto_id obbligatorio per conferma")
    
    risultato = await service.applica_spostamento(
        fattura_id=fattura_id,
        movimento_estratto_id=movimento_estratto_id,
        conferma=conferma
    )
    
    if not risultato.get("success"):
        raise HTTPException(status_code=400, detail=risultato.get("error", "Errore sconosciuto"))
    
    return risultato


# =============================================================================
# RI-ANALISI (dopo nuovo estratto)
# =============================================================================

@router.post("/rianalizza")
async def rianalizza_operazioni() -> Dict[str, Any]:
    """
    Ri-analizza tutte le operazioni sospese dopo caricamento nuovo estratto conto.
    
    Chiamare dopo ogni upload di estratto conto.
    
    Returns:
        Report con spostamenti proposti, riconciliate, ancora sospese, anomalie
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    risultato = await service.rianalizza_operazioni_sospese()
    
    return {
        "success": True,
        **risultato
    }


# =============================================================================
# LISTE E QUERY
# =============================================================================

@router.get("/fatture-da-confermare")
async def get_fatture_da_confermare(
    limit: int = Query(100, ge=1, le=500),
    anno: int = Query(None)
) -> Dict[str, Any]:
    """
    Lista fatture in attesa di conferma metodo pagamento.
    """
    db = Database.get_db()
    
    query = {"stato_riconciliazione": StatoRiconciliazione.IN_ATTESA_CONFERMA.value}
    
    if anno:
        query["data_documento"] = {"$regex": f"^{anno}"}
    
    fatture = await db["invoices"].find(
        query,
        {"_id": 0, "xml_content": 0, "linee": 0}
    ).sort("data_documento", -1).to_list(limit)
    
    return {
        "success": True,
        "count": len(fatture),
        "fatture": fatture
    }


@router.get("/spostamenti-proposti")
async def get_spostamenti_proposti() -> Dict[str, Any]:
    """
    Lista fatture con spostamento Cassa→Banca proposto.
    """
    db = Database.get_db()
    
    fatture = await db["invoices"].find(
        {"stato_riconciliazione": StatoRiconciliazione.DA_VERIFICARE_SPOSTAMENTO.value},
        {"_id": 0, "xml_content": 0, "linee": 0}
    ).sort("data_documento", -1).to_list(100)
    
    return {
        "success": True,
        "count": len(fatture),
        "fatture": fatture
    }


@router.get("/anomalie")
async def get_anomalie() -> Dict[str, Any]:
    """
    Lista fatture con anomalie (banca non trovata in estratto).
    """
    db = Database.get_db()
    
    fatture = await db["invoices"].find(
        {"stato_riconciliazione": StatoRiconciliazione.ANOMALIA_NON_IN_ESTRATTO.value},
        {"_id": 0, "xml_content": 0, "linee": 0}
    ).sort("data_documento", -1).to_list(100)
    
    return {
        "success": True,
        "count": len(fatture),
        "fatture": fatture
    }


@router.get("/stato-estratto")
async def get_stato_estratto() -> Dict[str, Any]:
    """
    Info sullo stato dell'estratto conto.
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    ultima_data = await service.get_ultima_data_estratto()
    
    # Conteggio movimenti per anno
    pipeline = [
        {"$group": {
            "_id": {"$substr": ["$data", 0, 4]},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": -1}}
    ]
    movimenti_per_anno = await db["estratto_conto_movimenti"].aggregate(pipeline).to_list(10)
    
    # Totale movimenti
    totale_movimenti = await db["estratto_conto_movimenti"].count_documents({})
    
    # Movimenti non riconciliati
    non_riconciliati = await db["estratto_conto_movimenti"].count_documents({
        "fattura_id": {"$exists": False}
    })
    
    return {
        "success": True,
        "ultima_data_movimento": ultima_data,
        "totale_movimenti": totale_movimenti,
        "movimenti_non_riconciliati": non_riconciliati,
        "movimenti_per_anno": {item["_id"]: item["count"] for item in movimenti_per_anno}
    }


# =============================================================================
# LOCK MANUALE
# =============================================================================

@router.post("/lock-manuale")
async def lock_manuale(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Blocca una fattura per evitare verifiche automatiche.
    
    Payload:
    {
        "fattura_id": "uuid",
        "motivo": "Motivo del blocco"
    }
    """
    db = Database.get_db()
    
    fattura_id = payload.get("fattura_id")
    motivo = payload.get("motivo", "Blocco manuale utente")
    
    if not fattura_id:
        raise HTTPException(status_code=400, detail="fattura_id obbligatorio")
    
    result = await db["invoices"].update_one(
        {"id": fattura_id},
        {"$set": {
            "stato_riconciliazione": StatoRiconciliazione.LOCK_MANUALE.value,
            "lock_manuale": True,
            "lock_manuale_motivo": motivo,
            "lock_manuale_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    return {
        "success": True,
        "message": "Fattura bloccata. Non verrà più verificata automaticamente.",
        "motivo": motivo
    }


@router.post("/sblocca")
async def sblocca_fattura(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sblocca una fattura e la rimette in verifica.
    
    Payload:
    {
        "fattura_id": "uuid"
    }
    """
    db = Database.get_db()
    
    fattura_id = payload.get("fattura_id")
    
    if not fattura_id:
        raise HTTPException(status_code=400, detail="fattura_id obbligatorio")
    
    # Recupera fattura per determinare nuovo stato
    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    # Determina stato in base al metodo confermato
    metodo = fattura.get("metodo_pagamento_confermato", "")
    if metodo == "cassa":
        nuovo_stato = StatoRiconciliazione.CONFERMATA_CASSA.value
    elif metodo == "banca":
        nuovo_stato = StatoRiconciliazione.CONFERMATA_BANCA.value
    else:
        nuovo_stato = StatoRiconciliazione.IN_ATTESA_CONFERMA.value
    
    result = await db["invoices"].update_one(
        {"id": fattura_id},
        {"$set": {
            "stato_riconciliazione": nuovo_stato,
            "lock_manuale": False,
            "updated_at": datetime.now(timezone.utc).isoformat()
        },
        "$unset": {
            "lock_manuale_motivo": "",
            "lock_manuale_at": ""
        }}
    )
    
    return {
        "success": True,
        "message": "Fattura sbloccata",
        "nuovo_stato": nuovo_stato
    }


# =============================================================================
# STATISTICHE
# =============================================================================

@router.get("/statistiche")
async def get_statistiche() -> Dict[str, Any]:
    """
    Statistiche complete sulla riconciliazione.
    """
    db = Database.get_db()
    
    # Conteggi per stato
    stati_count = {}
    for stato in StatoRiconciliazione:
        count = await db["invoices"].count_documents({
            "stato_riconciliazione": stato.value
        })
        stati_count[stato.value] = count
    
    # Totale fatture con stato riconciliazione
    totale_gestite = sum(stati_count.values())
    
    # Fatture senza stato (legacy)
    totale_fatture = await db["invoices"].count_documents({})
    legacy = totale_fatture - totale_gestite
    
    # Importi
    pipeline_importi = [
        {"$match": {"stato_riconciliazione": {"$exists": True}}},
        {"$group": {
            "_id": "$stato_riconciliazione",
            "totale_importo": {"$sum": "$importo_totale"},
            "count": {"$sum": 1}
        }}
    ]
    importi_per_stato = await db["invoices"].aggregate(pipeline_importi).to_list(20)
    
    return {
        "success": True,
        "conteggi_per_stato": stati_count,
        "totale_fatture": totale_fatture,
        "totale_gestite_sistema": totale_gestite,
        "fatture_legacy": legacy,
        "importi_per_stato": {
            item["_id"]: {
                "count": item["count"],
                "importo_totale": round(item["totale_importo"], 2)
            }
            for item in importi_per_stato
        }
    }



# =============================================================================
# MIGRAZIONE FATTURE ESISTENTI
# =============================================================================

@router.post("/migra-fatture-legacy")
async def migra_fatture_legacy(payload: Dict[str, Any] = {}) -> Dict[str, Any]:
    """
    Migra le fatture esistenti al nuovo sistema di riconciliazione intelligente.
    
    Payload (opzionale):
    {
        "anno": 2025,  // Solo anno specifico
        "limit": 100   // Limite fatture da migrare
    }
    
    LOGICA MIGRAZIONE:
    - Fatture con pagato=True e prima_nota_cassa_id → confermata_cassa
    - Fatture con pagato=True e prima_nota_banca_id → confermata_banca  
    - Fatture con riconciliato=True → riconciliata
    - Altre fatture → in_attesa_conferma
    """
    db = Database.get_db()
    
    anno = payload.get("anno")
    limit = payload.get("limit", 500)
    
    # Query per fatture senza stato_riconciliazione
    query = {"stato_riconciliazione": {"$exists": False}}
    if anno:
        query["data_documento"] = {"$regex": f"^{anno}"}
    
    fatture = await db["invoices"].find(
        query,
        {"_id": 0, "id": 1, "pagato": 1, "riconciliato": 1, 
         "prima_nota_cassa_id": 1, "prima_nota_banca_id": 1,
         "metodo_pagamento": 1, "provvisorio": 1}
    ).to_list(limit)
    
    risultato = {
        "migrate": 0,
        "in_attesa_conferma": 0,
        "confermata_cassa": 0,
        "confermata_banca": 0,
        "riconciliata": 0,
        "dettagli": []
    }
    
    for fattura in fatture:
        fattura_id = fattura.get("id")
        pagato = fattura.get("pagato", False)
        riconciliato = fattura.get("riconciliato", False)
        has_cassa = bool(fattura.get("prima_nota_cassa_id"))
        has_banca = bool(fattura.get("prima_nota_banca_id"))
        metodo = (fattura.get("metodo_pagamento") or "").lower()
        
        # Determina stato
        if riconciliato:
            nuovo_stato = StatoRiconciliazione.RICONCILIATA.value
            risultato["riconciliata"] += 1
        elif pagato and has_cassa:
            nuovo_stato = StatoRiconciliazione.CONFERMATA_CASSA.value
            risultato["confermata_cassa"] += 1
        elif pagato and has_banca:
            nuovo_stato = StatoRiconciliazione.CONFERMATA_BANCA.value
            risultato["confermata_banca"] += 1
        elif pagato:
            # Pagato ma senza riferimento prima nota
            if metodo in ["contanti", "cassa", "cash"]:
                nuovo_stato = StatoRiconciliazione.CONFERMATA_CASSA.value
                risultato["confermata_cassa"] += 1
            else:
                nuovo_stato = StatoRiconciliazione.CONFERMATA_BANCA.value
                risultato["confermata_banca"] += 1
        else:
            nuovo_stato = StatoRiconciliazione.IN_ATTESA_CONFERMA.value
            risultato["in_attesa_conferma"] += 1
        
        # Aggiorna fattura
        await db["invoices"].update_one(
            {"id": fattura_id},
            {"$set": {
                "stato_riconciliazione": nuovo_stato,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        risultato["migrate"] += 1
    
    logger.info(f"Migrazione completata: {risultato['migrate']} fatture migrate")
    
    return {
        "success": True,
        **risultato
    }


@router.post("/imposta-stato-fattura")
async def imposta_stato_fattura(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Imposta manualmente lo stato di una fattura.
    Utile per correzioni manuali.
    
    Payload:
    {
        "fattura_id": "uuid",
        "stato": "in_attesa_conferma" | "confermata_cassa" | etc.
    }
    """
    db = Database.get_db()
    
    fattura_id = payload.get("fattura_id")
    stato = payload.get("stato")
    
    if not fattura_id or not stato:
        raise HTTPException(status_code=400, detail="fattura_id e stato obbligatori")
    
    # Verifica stato valido
    stati_validi = [s.value for s in StatoRiconciliazione]
    if stato not in stati_validi:
        raise HTTPException(status_code=400, detail=f"Stato non valido. Stati ammessi: {stati_validi}")
    
    result = await db["invoices"].update_one(
        {"id": fattura_id},
        {"$set": {
            "stato_riconciliazione": stato,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    return {
        "success": True,
        "fattura_id": fattura_id,
        "nuovo_stato": stato
    }



# =============================================================================
# CASI ESTESI
# =============================================================================

@router.post("/pagamento-parziale")
async def registra_pagamento_parziale(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Registra un pagamento parziale su una fattura.
    
    Caso 19: Fattura €1.000, pago €500, residuo €500.
    
    Payload:
    {
        "fattura_id": "uuid",
        "importo_pagato": 500.00,
        "metodo": "cassa" | "banca",
        "data_pagamento": "YYYY-MM-DD" (opzionale),
        "note": "Note" (opzionale)
    }
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    fattura_id = payload.get("fattura_id")
    importo = payload.get("importo_pagato")
    metodo = payload.get("metodo", "").lower()
    data = payload.get("data_pagamento")
    note = payload.get("note", "")
    
    if not fattura_id or not importo or metodo not in ["cassa", "banca"]:
        raise HTTPException(status_code=400, detail="fattura_id, importo_pagato e metodo obbligatori")
    
    risultato = await service.registra_pagamento_parziale(
        fattura_id=fattura_id,
        importo_pagato=float(importo),
        metodo=metodo,
        data_pagamento=data,
        note=note
    )
    
    if not risultato.get("success"):
        raise HTTPException(status_code=400, detail=risultato.get("error"))
    
    return risultato


@router.post("/applica-nota-credito")
async def applica_nota_credito(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Applica una nota di credito a una fattura.
    
    Caso 21: Fattura €1.000, NC €200, dovuto €800.
    
    Payload:
    {
        "fattura_id": "uuid",
        "nota_credito_id": "uuid" (se in sistema),
        "importo_nc": 200.00 (se inserimento manuale),
        "numero_nc": "NC/123" (se inserimento manuale)
    }
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    risultato = await service.applica_nota_credito(
        fattura_id=payload.get("fattura_id"),
        nota_credito_id=payload.get("nota_credito_id"),
        importo_nc=payload.get("importo_nc"),
        numero_nc=payload.get("numero_nc")
    )
    
    if not risultato.get("success"):
        raise HTTPException(status_code=400, detail=risultato.get("error"))
    
    return risultato


@router.post("/cerca-bonifico-cumulativo")
async def cerca_bonifico_cumulativo(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cerca fatture che matchano un bonifico cumulativo.
    
    Caso 23: Bonifico €3.000 per 3 fatture.
    
    Payload:
    {
        "importo_movimento": 3000.00,
        "data_movimento": "2026-01-20",
        "descrizione_movimento": "BONIFICO FORNITORE XYZ"
    }
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    risultato = await service.cerca_bonifico_cumulativo(
        importo_movimento=payload.get("importo_movimento", 0),
        data_movimento=payload.get("data_movimento", ""),
        descrizione_movimento=payload.get("descrizione_movimento", "")
    )
    
    return {
        "success": True,
        **risultato
    }


@router.post("/riconcilia-bonifico-cumulativo")
async def riconcilia_bonifico_cumulativo(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Riconcilia un bonifico cumulativo con multiple fatture.
    
    Payload:
    {
        "movimento_id": "uuid",
        "fatture_ids": ["uuid1", "uuid2", "uuid3"]
    }
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    movimento_id = payload.get("movimento_id")
    fatture_ids = payload.get("fatture_ids", [])
    
    if not movimento_id or not fatture_ids:
        raise HTTPException(status_code=400, detail="movimento_id e fatture_ids obbligatori")
    
    risultato = await service.riconcilia_bonifico_cumulativo(
        movimento_id=movimento_id,
        fatture_ids=fatture_ids
    )
    
    if not risultato.get("success"):
        raise HTTPException(status_code=400, detail=risultato.get("error"))
    
    return risultato


@router.post("/pagamento-con-sconto")
async def registra_pagamento_con_sconto(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Registra un pagamento con sconto cassa.
    
    Caso 31: Fattura €1.000, pago €980 (sconto 2%).
    
    Payload:
    {
        "fattura_id": "uuid",
        "importo_pagato": 980.00,
        "metodo": "cassa" | "banca",
        "percentuale_sconto": 2.0 (opzionale, calcolata se omessa),
        "data_pagamento": "YYYY-MM-DD" (opzionale)
    }
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    fattura_id = payload.get("fattura_id")
    importo = payload.get("importo_pagato")
    metodo = payload.get("metodo", "").lower()
    percentuale = payload.get("percentuale_sconto")
    data = payload.get("data_pagamento")
    
    if not fattura_id or not importo or metodo not in ["cassa", "banca"]:
        raise HTTPException(status_code=400, detail="fattura_id, importo_pagato e metodo obbligatori")
    
    risultato = await service.registra_pagamento_con_sconto(
        fattura_id=fattura_id,
        importo_pagato=float(importo),
        metodo=metodo,
        percentuale_sconto=float(percentuale) if percentuale else None,
        data_pagamento=data
    )
    
    if not risultato.get("success"):
        raise HTTPException(status_code=400, detail=risultato.get("error"))
    
    return risultato


# =============================================================================
# FASE 3: CASI ESTESI (36-38)
# =============================================================================

@router.post("/assegni-multipli")
async def registra_assegni_multipli(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Registra pagamento con assegni multipli.
    
    Caso 36: 2 assegni (€1.028,82 + €1.421,77) → Fattura €2.450,00
    
    Payload:
    {
        "fattura_id": "uuid",
        "assegni": [
            {"numero": "123456", "importo": 1028.82, "data": "2026-01-15", "banca": "BPM"},
            {"numero": "123457", "importo": 1421.77, "data": "2026-01-15", "banca": "BPM"}
        ],
        "metodo": "banca" (opzionale, default: banca)
    }
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    fattura_id = payload.get("fattura_id")
    assegni = payload.get("assegni", [])
    metodo = payload.get("metodo", "banca")
    
    if not fattura_id:
        raise HTTPException(status_code=400, detail="fattura_id obbligatorio")
    
    if not assegni or len(assegni) < 1:
        raise HTTPException(status_code=400, detail="Specificare almeno un assegno")
    
    # Valida assegni
    for idx, ass in enumerate(assegni):
        if not ass.get("importo"):
            raise HTTPException(status_code=400, detail=f"Assegno {idx+1}: importo obbligatorio")
    
    risultato = await service.registra_assegni_multipli(
        fattura_id=fattura_id,
        assegni=assegni,
        metodo=metodo
    )
    
    if not risultato.get("success"):
        raise HTTPException(status_code=400, detail=risultato.get("error"))
    
    return risultato


@router.post("/riconcilia-con-arrotondamento")
async def riconcilia_con_arrotondamento(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Riconcilia fattura con tolleranza per arrotondamenti.
    
    Caso 37: Fattura €999.99, bonifico €1000.00 → riconcilia automaticamente
    
    Payload:
    {
        "fattura_id": "uuid",
        "importo_pagato": 1000.00,
        "metodo": "banca",
        "tolleranza": 1.00 (opzionale, default €1.00, max €5.00),
        "data_pagamento": "YYYY-MM-DD" (opzionale)
    }
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    fattura_id = payload.get("fattura_id")
    importo_pagato = payload.get("importo_pagato")
    metodo = payload.get("metodo", "").lower()
    tolleranza = payload.get("tolleranza")
    data_pagamento = payload.get("data_pagamento")
    
    if not fattura_id or not importo_pagato or metodo not in ["cassa", "banca"]:
        raise HTTPException(status_code=400, detail="fattura_id, importo_pagato e metodo (cassa/banca) obbligatori")
    
    risultato = await service.riconcilia_con_arrotondamento(
        fattura_id=fattura_id,
        importo_pagato=float(importo_pagato),
        metodo=metodo,
        tolleranza=float(tolleranza) if tolleranza else None,
        data_pagamento=data_pagamento
    )
    
    if not risultato.get("success"):
        raise HTTPException(status_code=400, detail=risultato.get("error"))
    
    return risultato


@router.post("/pagamento-anticipato")
async def registra_pagamento_anticipato(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Registra un pagamento anticipato (prima della fattura).
    
    Caso 38: Bonifico €500 il 10/01, Fattura €500 arriva il 15/01
    
    Payload:
    {
        "fornitore_id": "uuid" (opzionale),
        "fornitore_nome": "Nome Fornitore",
        "fornitore_piva": "01234567890" (opzionale),
        "importo": 500.00,
        "metodo": "banca",
        "data_pagamento": "2026-01-10" (opzionale),
        "riferimento": "Ordine 123" (opzionale),
        "note": "Note" (opzionale)
    }
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    importo = payload.get("importo")
    metodo = payload.get("metodo", "banca").lower()
    
    if not importo or float(importo) <= 0:
        raise HTTPException(status_code=400, detail="importo deve essere maggiore di zero")
    
    if metodo not in ["cassa", "banca"]:
        raise HTTPException(status_code=400, detail="metodo deve essere 'cassa' o 'banca'")
    
    risultato = await service.registra_pagamento_anticipato(
        fornitore_id=payload.get("fornitore_id"),
        fornitore_nome=payload.get("fornitore_nome"),
        fornitore_piva=payload.get("fornitore_piva"),
        importo=float(importo),
        metodo=metodo,
        data_pagamento=payload.get("data_pagamento"),
        riferimento=payload.get("riferimento", ""),
        note=payload.get("note", "")
    )
    
    if not risultato.get("success"):
        raise HTTPException(status_code=400, detail=risultato.get("error"))
    
    return risultato


@router.get("/pagamenti-anticipati")
async def get_pagamenti_anticipati() -> Dict[str, Any]:
    """
    Lista pagamenti anticipati in attesa di fattura.
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    return await service.get_pagamenti_anticipati_in_attesa()


@router.post("/cerca-pagamenti-anticipati")
async def cerca_pagamenti_anticipati_per_fattura(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cerca pagamenti anticipati che potrebbero corrispondere a una fattura.
    
    Payload:
    {
        "fattura_id": "uuid"
    }
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    fattura_id = payload.get("fattura_id")
    if not fattura_id:
        raise HTTPException(status_code=400, detail="fattura_id obbligatorio")
    
    return await service.cerca_pagamenti_anticipati_per_fattura(fattura_id)


@router.post("/collega-pagamento-anticipato")
async def collega_pagamento_anticipato(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Collega un pagamento anticipato a una fattura.
    
    Payload:
    {
        "pagamento_anticipato_id": "uuid",
        "fattura_id": "uuid",
        "importo_da_collegare": 500.00 (opzionale, default: tutto il residuo)
    }
    """
    db = Database.get_db()
    service = get_riconciliazione_service(db)
    
    pagamento_id = payload.get("pagamento_anticipato_id")
    fattura_id = payload.get("fattura_id")
    importo = payload.get("importo_da_collegare")
    
    if not pagamento_id or not fattura_id:
        raise HTTPException(status_code=400, detail="pagamento_anticipato_id e fattura_id obbligatori")
    
    risultato = await service.collega_pagamento_anticipato_a_fattura(
        pagamento_anticipato_id=pagamento_id,
        fattura_id=fattura_id,
        importo_da_collegare=float(importo) if importo else None
    )
    
    if not risultato.get("success"):
        raise HTTPException(status_code=400, detail=risultato.get("error"))
    
    return risultato