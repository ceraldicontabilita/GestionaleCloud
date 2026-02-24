"""
Router Scadenzario Fornitori - Fatture da pagare
Solo fatture con scadenza, senza gestione effettiva pagamenti
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import logging

from app.database import Database
from app.routers.ciclo_passivo_integrato import cerca_match_bancario, esegui_riconciliazione
from app.utils.error_handler import handle_errors

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================
# MODELLI
# ============================================

class ScadenzaUpdate(BaseModel):
    fattura_id: str
    data_scadenza: str  # YYYY-MM-DD
    note: Optional[str] = None


# ============================================
# ENDPOINT
# ============================================

@router.get("/")
@handle_errors
async def get_scadenzario(
    anno: int = Query(None, description="Anno di riferimento"),
    fornitore: str = Query(None, description="Filtra per fornitore"),
    stato: str = Query("aperte", description="aperte, scadute, tutte"),
    giorni_scadenza: int = Query(None, description="Fatture che scadono entro X giorni")
) -> Dict[str, Any]:
    """
    Restituisce lo scadenzario fatture fornitori.
    Default: fatture aperte (non pagate).
    """
    db = Database.get_db()
    
    oggi = datetime.now().strftime("%Y-%m-%d")
    if not anno:
        anno = datetime.now().year
    
    # Query base: fatture non pagate
    query = {
        "$and": [
            {"pagato": {"$ne": True}},
            {"status": {"$ne": "paid"}},
            {"$or": [
                {"invoice_date": {"$regex": f"^{anno}"}},
                {"data_scadenza": {"$regex": f"^{anno}"}}
            ]}
        ]
    }
    
    # Filtra per fornitore
    if fornitore:
        query["$and"].append({
            "supplier_name": {"$regex": fornitore, "$options": "i"}
        })
    
    # Filtra per stato
    if stato == "scadute":
        query["$and"].append({
            "$or": [
                {"data_scadenza": {"$lt": oggi}},
                {"$and": [
                    {"data_scadenza": {"$exists": False}},
                    {"invoice_date": {"$lt": oggi}}
                ]}
            ]
        })
    elif stato == "aperte" and giorni_scadenza:
        data_limite = (datetime.now() + timedelta(days=giorni_scadenza)).strftime("%Y-%m-%d")
        query["$and"].append({
            "$or": [
                {"data_scadenza": {"$lte": data_limite}},
                {"$and": [
                    {"data_scadenza": {"$exists": False}},
                    {"invoice_date": {"$lte": data_limite}}
                ]}
            ]
        })
    
    # Recupera fatture
    fatture = await db["invoices"].find(
        query,
        {"_id": 0}
    ).sort("data_scadenza", 1).to_list(5000)
    
    # Calcola totali e organizza per scadenza
    totale_da_pagare = 0
    totale_scaduto = 0
    scadenze_per_periodo = {
        "scadute": [],
        "oggi": [],
        "prossimi_7_giorni": [],
        "prossimi_30_giorni": [],
        "oltre_30_giorni": []
    }
    
    try:
        data_oggi = datetime.strptime(oggi, "%Y-%m-%d")
    except ValueError:
        data_oggi = datetime.now()
        oggi = data_oggi.strftime("%Y-%m-%d")
    
    for f in fatture:
        importo = float(f.get("total_amount", 0))
        totale_da_pagare += importo
        
        # Determina data scadenza (usa invoice_date se manca data_scadenza)
        data_scad_str = f.get("data_scadenza") or f.get("invoice_date", oggi)
        try:
            data_scad = datetime.strptime(data_scad_str[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            data_scad = data_oggi
        
        f["data_scadenza_effettiva"] = data_scad.strftime("%Y-%m-%d")
        
        # Calcola giorni alla scadenza
        giorni = (data_scad - data_oggi).days
        f["giorni_alla_scadenza"] = giorni
        
        # Categorizza
        if giorni < 0:
            scadenze_per_periodo["scadute"].append(f)
            totale_scaduto += importo
        elif giorni == 0:
            scadenze_per_periodo["oggi"].append(f)
        elif giorni <= 7:
            scadenze_per_periodo["prossimi_7_giorni"].append(f)
        elif giorni <= 30:
            scadenze_per_periodo["prossimi_30_giorni"].append(f)
        else:
            scadenze_per_periodo["oltre_30_giorni"].append(f)
    
    # Riepilogo per fornitore
    fornitori_totali = {}
    for f in fatture:
        fornitore_nome = f.get("supplier_name", "Sconosciuto")
        if fornitore_nome not in fornitori_totali:
            fornitori_totali[fornitore_nome] = {
                "fornitore": fornitore_nome,
                "num_fatture": 0,
                "totale": 0
            }
        fornitori_totali[fornitore_nome]["num_fatture"] += 1
        fornitori_totali[fornitore_nome]["totale"] += float(f.get("total_amount", 0))
    
    fornitori_list = sorted(
        fornitori_totali.values(), 
        key=lambda x: x["totale"], 
        reverse=True
    )
    
    return {
        "anno": anno,
        "data_riferimento": oggi,
        "riepilogo": {
            "totale_fatture": len(fatture),
            "totale_da_pagare": round(totale_da_pagare, 2),
            "totale_scaduto": round(totale_scaduto, 2),
            "num_scadute": len(scadenze_per_periodo["scadute"]),
            "num_in_scadenza_oggi": len(scadenze_per_periodo["oggi"]),
            "num_prossimi_7gg": len(scadenze_per_periodo["prossimi_7_giorni"]),
            "num_prossimi_30gg": len(scadenze_per_periodo["prossimi_30_giorni"])
        },
        "scadenze": scadenze_per_periodo,
        "per_fornitore": fornitori_list[:20]  # Top 20 fornitori
    }


@router.get("/urgenti")
@handle_errors
async def get_scadenze_urgenti() -> Dict[str, Any]:
    """
    Fatture urgenti: scadute o in scadenza entro 7 giorni.
    Per dashboard e notifiche.
    """
    db = Database.get_db()
    
    oggi = datetime.now().strftime("%Y-%m-%d")
    tra_7_giorni = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    
    query = {
        "pagato": {"$ne": True},
        "status": {"$ne": "paid"},
        "$or": [
            {"data_scadenza": {"$lte": tra_7_giorni}},
            {"$and": [
                {"data_scadenza": {"$exists": False}},
                {"invoice_date": {"$lte": tra_7_giorni}}
            ]}
        ]
    }
    
    fatture = await db["invoices"].find(
        query,
        {"_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1, 
         "total_amount": 1, "invoice_date": 1, "data_scadenza": 1}
    ).sort("data_scadenza", 1).to_list(100)
    
    urgenti = []
    try:
        data_oggi = datetime.strptime(oggi, "%Y-%m-%d")
    except ValueError:
        data_oggi = datetime.now()
    
    for f in fatture:
        data_scad_str = f.get("data_scadenza") or f.get("invoice_date", oggi)
        try:
            data_scad = datetime.strptime(data_scad_str[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            data_scad = data_oggi
        
        giorni = (data_scad - data_oggi).days
        
        urgenti.append({
            "id": f.get("id"),
            "numero_fattura": f.get("invoice_number"),
            "fornitore": f.get("supplier_name"),
            "importo": round(float(f.get("total_amount", 0)), 2),
            "data_scadenza": data_scad.strftime("%Y-%m-%d"),
            "giorni_alla_scadenza": giorni,
            "stato": "scaduta" if giorni < 0 else ("oggi" if giorni == 0 else "in_scadenza")
        })
    
    totale = sum(u["importo"] for u in urgenti)
    scadute = [u for u in urgenti if u["stato"] == "scaduta"]
    
    return {
        "data_riferimento": oggi,
        "num_urgenti": len(urgenti),
        "totale_urgente": round(totale, 2),
        "num_scadute": len(scadute),
        "totale_scaduto": round(sum(s["importo"] for s in scadute), 2),
        "fatture": urgenti
    }


@router.get("/cash-flow-previsionale")
@handle_errors
async def get_cash_flow_previsionale(
    mesi: int = Query(3, description="Numero di mesi di previsione")
) -> Dict[str, Any]:
    """
    Previsione cash flow basata sulle scadenze fatture.
    Utile per pianificazione finanziaria.
    """
    db = Database.get_db()
    
    oggi = datetime.now()
    data_limite = (oggi + timedelta(days=mesi * 30)).strftime("%Y-%m-%d")
    
    # Fatture da pagare nei prossimi mesi
    fatture = await db["invoices"].find(
        {
            "pagato": {"$ne": True},
            "status": {"$ne": "paid"},
            "$or": [
                {"data_scadenza": {"$lte": data_limite}},
                {"invoice_date": {"$lte": data_limite}}
            ]
        },
        {"_id": 0, "total_amount": 1, "data_scadenza": 1, "invoice_date": 1}
    ).to_list(10000)
    
    # Organizza per mese
    cash_flow_mensile = {}
    
    for i in range(mesi + 1):
        mese_data = oggi + timedelta(days=i * 30)
        chiave = mese_data.strftime("%Y-%m")
        cash_flow_mensile[chiave] = {
            "mese": chiave,
            "uscite_previste": 0,
            "num_fatture": 0
        }
    
    for f in fatture:
        data_scad_str = f.get("data_scadenza") or f.get("invoice_date")
        if not data_scad_str:
            continue
        
        try:
            data_scad = datetime.strptime(data_scad_str[:10], "%Y-%m-%d")
            mese = data_scad.strftime("%Y-%m")
            
            if mese in cash_flow_mensile:
                cash_flow_mensile[mese]["uscite_previste"] += float(f.get("total_amount", 0))
                cash_flow_mensile[mese]["num_fatture"] += 1
        except Exception:
            continue
    
    # Ordina per mese
    previsioni = sorted(cash_flow_mensile.values(), key=lambda x: x["mese"])
    
    # Arrotonda
    for p in previsioni:
        p["uscite_previste"] = round(p["uscite_previste"], 2)
    
    totale_previsto = sum(p["uscite_previste"] for p in previsioni)
    
    return {
        "data_calcolo": oggi.strftime("%Y-%m-%d"),
        "periodo_analisi_mesi": mesi,
        "totale_uscite_previste": round(totale_previsto, 2),
        "previsioni_mensili": previsioni
    }


@router.put("/aggiorna-scadenza")
@handle_errors
async def aggiorna_data_scadenza(update: ScadenzaUpdate) -> Dict[str, Any]:
    """Aggiorna la data di scadenza di una fattura."""
    db = Database.get_db()
    
    result = await db["invoices"].update_one(
        {"id": update.fattura_id},
        {
            "$set": {
                "data_scadenza": update.data_scadenza,
                "note_scadenza": update.note,
                "scadenza_aggiornata_il": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    return {
        "success": True,
        "messaggio": f"Scadenza aggiornata a {update.data_scadenza}"
    }


@router.get("/aging")
@handle_errors
async def get_aging_fornitori() -> Dict[str, Any]:
    """
    Analisi aging crediti fornitori.
    Classifica i debiti per anzianità.
    """
    db = Database.get_db()
    
    oggi = datetime.now()
    oggi_str = oggi.strftime("%Y-%m-%d")
    
    fatture = await db["invoices"].find(
        {
            "pagato": {"$ne": True},
            "status": {"$ne": "paid"}
        },
        {"_id": 0}
    ).to_list(10000)
    
    aging = {
        "corrente": {"label": "Non scaduto", "importo": 0, "num": 0},
        "0_30": {"label": "0-30 giorni", "importo": 0, "num": 0},
        "31_60": {"label": "31-60 giorni", "importo": 0, "num": 0},
        "61_90": {"label": "61-90 giorni", "importo": 0, "num": 0},
        "oltre_90": {"label": "Oltre 90 giorni", "importo": 0, "num": 0}
    }
    
    for f in fatture:
        importo = float(f.get("total_amount", 0))
        data_scad_str = f.get("data_scadenza") or f.get("invoice_date")
        
        if not data_scad_str:
            continue
        
        try:
            data_scad = datetime.strptime(data_scad_str[:10], "%Y-%m-%d")
            giorni_ritardo = (oggi - data_scad).days
            
            if giorni_ritardo <= 0:
                aging["corrente"]["importo"] += importo
                aging["corrente"]["num"] += 1
            elif giorni_ritardo <= 30:
                aging["0_30"]["importo"] += importo
                aging["0_30"]["num"] += 1
            elif giorni_ritardo <= 60:
                aging["31_60"]["importo"] += importo
                aging["31_60"]["num"] += 1
            elif giorni_ritardo <= 90:
                aging["61_90"]["importo"] += importo
                aging["61_90"]["num"] += 1
            else:
                aging["oltre_90"]["importo"] += importo
                aging["oltre_90"]["num"] += 1
        except Exception:
            continue
    
    # Arrotonda
    for k in aging:
        aging[k]["importo"] = round(aging[k]["importo"], 2)
    
    totale = sum(a["importo"] for a in aging.values())
    
    return {
        "data_riferimento": oggi_str,
        "totale_debiti": round(totale, 2),
        "aging": aging,
        "percentuali": {
            k: round(v["importo"] / totale * 100, 1) if totale > 0 else 0
            for k, v in aging.items()
        }
    }



@router.get("/scadenze-integrate")
@handle_errors
async def get_scadenze_integrate(
    anno: int = Query(None, description="Anno di riferimento"),
    stato: str = Query("aperte", description="aperte, pagate, tutte")
) -> Dict[str, Any]:
    """
    Restituisce le scadenze dalla collezione scadenziario_fornitori 
    (create dall'integrazione ciclo passivo).
    """
    db = Database.get_db()
    
    oggi = datetime.now().strftime("%Y-%m-%d")
    if not anno:
        anno = datetime.now().year
    
    # Query base
    query = {
        "data_scadenza": {"$regex": f"^{anno}"}
    }
    
    if stato == "aperte":
        query["pagato"] = {"$ne": True}
    elif stato == "pagate":
        query["pagato"] = True
    
    scadenze = await db["scadenziario_fornitori"].find(
        query, {"_id": 0}
    ).sort("data_scadenza", 1).to_list(1000)
    
    # Calcola totali
    totale_da_pagare = 0
    totale_scaduto = 0
    data_oggi = datetime.strptime(oggi, "%Y-%m-%d")
    
    scadenze_per_periodo = {
        "scadute": [],
        "oggi": [],
        "prossimi_7_giorni": [],
        "prossimi_30_giorni": [],
        "oltre_30_giorni": []
    }
    
    for s in scadenze:
        importo = float(s.get("importo_totale", 0))
        totale_da_pagare += importo
        
        data_scad_str = s.get("data_scadenza", oggi)
        try:
            data_scad = datetime.strptime(data_scad_str[:10], "%Y-%m-%d")
        except Exception:
            data_scad = data_oggi
        
        giorni = (data_scad - data_oggi).days
        s["giorni_alla_scadenza"] = giorni
        
        # Normalizza campi per la UI
        s["importo"] = importo
        s["fornitore"] = s.get("fornitore_nome", "")
        s["numero_fattura"] = s.get("numero_fattura", "")
        
        if giorni < 0:
            scadenze_per_periodo["scadute"].append(s)
            totale_scaduto += importo
        elif giorni == 0:
            scadenze_per_periodo["oggi"].append(s)
        elif giorni <= 7:
            scadenze_per_periodo["prossimi_7_giorni"].append(s)
        elif giorni <= 30:
            scadenze_per_periodo["prossimi_30_giorni"].append(s)
        else:
            scadenze_per_periodo["oltre_30_giorni"].append(s)
    
    return {
        "anno": anno,
        "data_riferimento": oggi,
        "riepilogo": {
            "totale_scadenze": len(scadenze),
            "totale_da_pagare": round(totale_da_pagare, 2),
            "totale_scaduto": round(totale_scaduto, 2),
            "num_scadute": len(scadenze_per_periodo["scadute"]),
            "num_in_scadenza_oggi": len(scadenze_per_periodo["oggi"]),
            "num_prossimi_7gg": len(scadenze_per_periodo["prossimi_7_giorni"]),
            "num_prossimi_30gg": len(scadenze_per_periodo["prossimi_30_giorni"])
        },
        "scadenze": scadenze_per_periodo,
        "lista_completa": scadenze
    }



@router.post("/riconcilia-automatica")
@handle_errors
async def riconcilia_automatica_scadenze(
    anno: int = Query(None, description="Anno scadenze da riconciliare"),
    dry_run: bool = Query(True, description="Se True, mostra anteprima senza modificare")
) -> Dict[str, Any]:
    """
    Esegue la riconciliazione automatica cercando match tra scadenze e movimenti bancari.
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Trova scadenze aperte
    query = {
        "data_scadenza": {"$regex": f"^{anno}"},
        "pagato": {"$ne": True},
        "riconciliato": {"$ne": True}
    }
    
    scadenze = await db["scadenziario_fornitori"].find(query, {"_id": 0}).to_list(500)
    
    risultati = {
        "anno": anno,
        "scadenze_analizzate": len(scadenze),
        "match_trovati": 0,
        "riconciliazioni_eseguite": 0,
        "dettagli": []
    }
    
    for scadenza in scadenze:
        match = await cerca_match_bancario(db, scadenza)
        
        if match:
            risultati["match_trovati"] += 1
            
            dettaglio = {
                "scadenza_id": scadenza.get("id"),
                "fornitore": scadenza.get("fornitore_nome"),
                "importo_scadenza": scadenza.get("importo_totale"),
                "data_scadenza": scadenza.get("data_scadenza"),
                "match": {
                    "id": match.get("id"),
                    "importo": match.get("importo"),
                    "data": match.get("data"),
                    "descrizione": match.get("descrizione_originale", "")[:50],
                    "match_type": match.get("match_type", "unknown"),
                    "match_score": match.get("match_score")
                }
            }
            
            if not dry_run:
                try:
                    source_col = match.get("source_collection", "estratto_conto_movimenti")
                    await esegui_riconciliazione(db, scadenza.get("id"), match.get("id"), source_col)
                    risultati["riconciliazioni_eseguite"] += 1
                    dettaglio["riconciliato"] = True
                except Exception as e:
                    dettaglio["errore"] = str(e)
                    dettaglio["riconciliato"] = False
            else:
                dettaglio["dry_run"] = True
            
            risultati["dettagli"].append(dettaglio)
    
    return risultati


