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
from app.utils.error_handler import handle_errors
from app.services.stato_pagamento_fattura import FILTRO_NON_PAGATE
from app.services.fattura_attiva import FILTRO_FATTURA_ATTIVA, importo_documento_con_segno

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

#: Le fatture fornitore NON hanno scadenza (decisione del titolare,
#: 19/09/2026: «decido io quando pagare»). Qui la «data di scadenza» ripiegava
#: su `invoice_date`, cosi' ogni fattura aperta risultava «scaduta» il giorno
#: dopo l'emissione; e `data_scadenza` sulle fatture e' in gran parte il «+30»
#: inventato dal vecchio import (`azzera-scadenze` e' ancora da lanciare), quindi
#: non la si legge nemmeno quando c'e'.
_NOTA_SENZA_SCADENZA = (
    "Le fatture fornitore non hanno scadenza: decide il titolare quando pagarle."
)


def _query_da_pagare(anno: int, fornitore: Optional[str] = None) -> Dict[str, Any]:
    """Fatture attive, non pagate (criterio unico), dell'anno richiesto."""
    condizioni = [
        dict(FILTRO_FATTURA_ATTIVA),
        dict(FILTRO_NON_PAGATE),
        {"invoice_date": {"$regex": f"^{anno}"}},
    ]
    if fornitore:
        condizioni.append({"supplier_name": {"$regex": fornitore, "$options": "i"}})
    return {"$and": condizioni}


@router.get("/")
@handle_errors
async def get_scadenzario(
    anno: int = Query(None, description="Anno di riferimento"),
    fornitore: str = Query(None, description="Filtra per fornitore"),
    stato: str = Query("aperte", description="aperte, scadute, tutte"),
    giorni_scadenza: int = Query(None, description="Ignorato: le fatture fornitore non hanno scadenza")
) -> Dict[str, Any]:
    """
    Fatture fornitori ancora da pagare.

    Nessuna categoria «scadute» o «in scadenza»: le fatture fornitore non
    hanno scadenza. `stato=scadute` restituisce quindi un elenco vuoto, e
    `giorni_scadenza` non filtra niente. Le note di credito pesano in negativo.
    """
    db = Database.get_db()

    oggi = datetime.now().strftime("%Y-%m-%d")
    if not anno:
        anno = datetime.now().year

    if stato == "scadute":
        fatture = []
    else:
        fatture = await db["invoices"].find(
            _query_da_pagare(anno, fornitore),
            {"_id": 0, "xml_raw": 0, "fattura_allegata": 0, "document_original_ref": 0, "foto": 0}
        ).sort("invoice_date", -1).to_list(5000)

    totale_da_pagare = 0.0
    fornitori_totali: Dict[str, Dict[str, Any]] = {}
    for f in fatture:
        importo = importo_documento_con_segno(f)
        f["importo_con_segno"] = importo
        totale_da_pagare += importo
        fornitore_nome = f.get("supplier_name") or "Sconosciuto"
        voce = fornitori_totali.setdefault(fornitore_nome, {
            "fornitore": fornitore_nome, "num_fatture": 0, "totale": 0.0,
        })
        voce["num_fatture"] += 1
        voce["totale"] += importo

    fornitori_list = sorted(
        ({**v, "totale": round(v["totale"], 2)} for v in fornitori_totali.values()),
        key=lambda x: x["totale"],
        reverse=True
    )

    return {
        "anno": anno,
        "data_riferimento": oggi,
        "nota": _NOTA_SENZA_SCADENZA,
        "riepilogo": {
            "totale_fatture": len(fatture),
            "totale_da_pagare": round(totale_da_pagare, 2),
            "totale_scaduto": 0,
            "num_scadute": 0,
            "num_in_scadenza_oggi": 0,
            "num_prossimi_7gg": 0,
            "num_prossimi_30gg": 0
        },
        "da_pagare": fatture,
        "per_fornitore": fornitori_list[:20]  # Top 20 fornitori
    }


@router.get("/urgenti")
@handle_errors
async def get_scadenze_urgenti() -> Dict[str, Any]:
    """
    Fatture fornitore urgenti: nessuna, per definizione.

    Senza scadenza non esiste una fattura «scaduta» o «in scadenza»: prima
    lo diventava ogni fattura aperta, perche' la data ripiegava su
    `invoice_date`. La risposta resta nella stessa forma per la pagina.
    """
    oggi = datetime.now().strftime("%Y-%m-%d")
    return {
        "data_riferimento": oggi,
        "nota": _NOTA_SENZA_SCADENZA,
        "num_urgenti": 0,
        "totale_urgente": 0,
        "num_scadute": 0,
        "totale_scaduto": 0,
        "fatture": []
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
    
    oggi = datetime.now(timezone.utc)
    data_limite = (oggi + timedelta(days=mesi * 30)).strftime("%Y-%m-%d")
    
    # Fatture da pagare nei prossimi mesi
    fatture = await db["invoices"].find(
        {
            **FILTRO_NON_PAGATE,
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
    
    oggi = datetime.now(timezone.utc)
    oggi_str = oggi.strftime("%Y-%m-%d")
    
    fatture = await db["invoices"].find(
        {
            **FILTRO_NON_PAGATE,
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
        importo = float(s.get("importo_totale", s.get("importo", 0)) or 0)
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





