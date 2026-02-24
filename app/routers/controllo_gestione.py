"""
Router Controllo di Gestione e Budget
Analisi costi/ricavi, centri di costo, budget e confronti
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================
# MODELLI
# ============================================

class BudgetInput(BaseModel):
    anno: int
    voce: str  # es: "personale", "materie_prime", "utenze", "affitto", etc.
    categoria: str  # "costo" o "ricavo"
    importo_budget: float
    note: Optional[str] = None


class BudgetMensileInput(BaseModel):
    anno: int
    voce: str
    budget_mensili: Dict[int, float]  # {1: 1000, 2: 1200, ...}


# ============================================
# ENDPOINT CONTROLLO GESTIONE
# ============================================

@router.get("/costi-ricavi")
@handle_errors
async def get_analisi_costi_ricavi(
    anno: int,
    mese: int = None
) -> Dict[str, Any]:
    """
    Analisi dettagliata costi e ricavi.
    Aggrega dati da prima nota, cedolini, fatture.
    """
    db = Database.get_db()
    
    if mese:
        data_inizio = f"{anno}-{mese:02d}-01"
        if mese == 12:
            data_fine = f"{anno}-12-31"
        else:
            data_fine = f"{anno}-{mese+1:02d}-01"
        periodo = f"{mese:02d}/{anno}"
    else:
        data_inizio = f"{anno}-01-01"
        data_fine = f"{anno}-12-31"
        periodo = str(anno)
    
    # === RICAVI ===
    # Corrispettivi
    corrispettivi = await db["corrispettivi"].aggregate([
        {"$match": {"data": {"$gte": data_inizio, "$lt": data_fine}}},
        {"$group": {"_id": None, "totale": {"$sum": "$totale"}}}
    ]).to_list(1)
    totale_corrispettivi = corrispettivi[0]["totale"] if corrispettivi else 0
    
    # Fatture emesse
    fatture_emesse = await db["invoices"].aggregate([
        {"$match": {
            "invoice_date": {"$gte": data_inizio, "$lt": data_fine},
            "tipo_documento": {"$in": ["TD01", "TD24", "TD26"]}
        }},
        {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
    ]).to_list(1)
    totale_fatture_emesse = fatture_emesse[0]["totale"] if fatture_emesse else 0
    
    ricavi_totali = totale_corrispettivi + totale_fatture_emesse
    
    # === COSTI ===
    # Costo personale (cedolini)
    costo_personale = await db["cedolini"].aggregate([
        {"$match": {"anno": anno, **({"mese": mese} if mese else {})}},
        {"$group": {"_id": None, "totale": {"$sum": "$costo_azienda"}}}
    ]).to_list(1)
    totale_personale = costo_personale[0]["totale"] if costo_personale else 0
    
    # Se non ci sono cedolini, usa prima_nota_salari
    if totale_personale == 0:
        salari = await db["prima_nota_salari"].aggregate([
            {"$match": {"anno": anno, **({"mese": mese} if mese else {})}},
            {"$group": {"_id": None, "totale": {"$sum": "$costo_azienda"}}}
        ]).to_list(1)
        totale_personale = salari[0]["totale"] if salari else 0
    
    # Acquisti (fatture ricevute)
    acquisti = await db["invoices"].aggregate([
        {"$match": {
            "invoice_date": {"$gte": data_inizio, "$lt": data_fine},
            "tipo_documento": {"$nin": ["TD01", "TD04", "TD24", "TD26"]}
        }},
        {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
    ]).to_list(1)
    totale_acquisti = acquisti[0]["totale"] if acquisti else 0
    
    # Prima nota cassa (uscite)
    uscite_cassa = await db["prima_nota_cassa"].aggregate([
        {"$match": {
            "data": {"$gte": data_inizio, "$lt": data_fine},
            "tipo": "uscita"
        }},
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}}
    ]).to_list(1)
    totale_uscite_cassa = uscite_cassa[0]["totale"] if uscite_cassa else 0
    
    costi_totali = totale_personale + totale_acquisti + totale_uscite_cassa
    
    # Margine
    margine = ricavi_totali - costi_totali
    margine_percentuale = (margine / ricavi_totali * 100) if ricavi_totali > 0 else 0
    
    return {
        "periodo": periodo,
        "anno": anno,
        "mese": mese,
        "ricavi": {
            "corrispettivi": round(totale_corrispettivi, 2),
            "fatture_emesse": round(totale_fatture_emesse, 2),
            "totale": round(ricavi_totali, 2)
        },
        "costi": {
            "personale": round(totale_personale, 2),
            "acquisti_merce": round(totale_acquisti, 2),
            "altre_uscite": round(totale_uscite_cassa, 2),
            "totale": round(costi_totali, 2)
        },
        "margine": {
            "importo": round(margine, 2),
            "percentuale": round(margine_percentuale, 1),
            "tipo": "utile" if margine > 0 else "perdita"
        }
    }


@router.get("/trend-mensile")
@handle_errors
async def get_trend_mensile(anno: int) -> Dict[str, Any]:
    """
    Trend mensile di ricavi, costi e margine.
    """
    risultati = []
    
    for mese in range(1, 13):
        try:
            analisi = await get_analisi_costi_ricavi(anno=anno, mese=mese)
            risultati.append({
                "mese": mese,
                "mese_nome": ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", 
                             "Lug", "Ago", "Set", "Ott", "Nov", "Dic"][mese-1],
                "ricavi": analisi["ricavi"]["totale"],
                "costi": analisi["costi"]["totale"],
                "margine": analisi["margine"]["importo"]
            })
        except Exception:
            risultati.append({
                "mese": mese,
                "mese_nome": ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", 
                             "Lug", "Ago", "Set", "Ott", "Nov", "Dic"][mese-1],
                "ricavi": 0,
                "costi": 0,
                "margine": 0
            })
    
    return {
        "anno": anno,
        "trend": risultati,
        "totale_anno": {
            "ricavi": round(sum(r["ricavi"] for r in risultati), 2),
            "costi": round(sum(r["costi"] for r in risultati), 2),
            "margine": round(sum(r["margine"] for r in risultati), 2)
        }
    }


@router.get("/costi-per-categoria")
@handle_errors
async def get_costi_per_categoria(
    anno: int,
    mese: int = None
) -> Dict[str, Any]:
    """
    Breakdown dei costi per categoria.
    """
    db = Database.get_db()
    
    if mese:
        data_inizio = f"{anno}-{mese:02d}-01"
        if mese == 12:
            data_fine = f"{anno}-12-31"
        else:
            data_fine = f"{anno}-{mese+1:02d}-01"
    else:
        data_inizio = f"{anno}-01-01"
        data_fine = f"{anno}-12-31"
    
    # Acquisti per fornitore/categoria
    acquisti_per_fornitore = await db["invoices"].aggregate([
        {"$match": {
            "invoice_date": {"$gte": data_inizio, "$lt": data_fine},
            "tipo_documento": {"$nin": ["TD01", "TD04", "TD24", "TD26"]}
        }},
        {"$group": {
            "_id": "$supplier_name",
            "totale": {"$sum": "$total_amount"},
            "num_fatture": {"$sum": 1}
        }},
        {"$sort": {"totale": -1}},
        {"$limit": 20}
    ]).to_list(20)
    
    # Prima nota cassa per categoria
    uscite_per_categoria = await db["prima_nota_cassa"].aggregate([
        {"$match": {
            "data": {"$gte": data_inizio, "$lt": data_fine},
            "tipo": "uscita"
        }},
        {"$group": {
            "_id": "$categoria",
            "totale": {"$sum": "$importo"},
            "num_movimenti": {"$sum": 1}
        }},
        {"$sort": {"totale": -1}}
    ]).to_list(50)
    
    return {
        "anno": anno,
        "mese": mese,
        "acquisti_per_fornitore": [
            {
                "fornitore": a["_id"] or "Sconosciuto",
                "totale": round(a["totale"], 2),
                "num_fatture": a["num_fatture"]
            }
            for a in acquisti_per_fornitore
        ],
        "uscite_per_categoria": [
            {
                "categoria": u["_id"] or "Non categorizzato",
                "totale": round(u["totale"], 2),
                "num_movimenti": u["num_movimenti"]
            }
            for u in uscite_per_categoria
        ]
    }


# ============================================
# ENDPOINT BUDGET
# ============================================

@router.post("/budget")
@handle_errors
async def crea_budget(budget: BudgetInput) -> Dict[str, Any]:
    """Crea o aggiorna una voce di budget."""
    db = Database.get_db()
    
    # Verifica se esiste già
    esistente = await db["budget"].find_one({
        "anno": budget.anno,
        "voce": budget.voce
    })
    
    record = {
        "anno": budget.anno,
        "voce": budget.voce,
        "categoria": budget.categoria,
        "importo_budget": budget.importo_budget,
        "note": budget.note,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if esistente:
        await db["budget"].update_one(
            {"anno": budget.anno, "voce": budget.voce},
            {"$set": record}
        )
        return {"success": True, "messaggio": f"Budget '{budget.voce}' aggiornato"}
    else:
        record["id"] = str(uuid4())
        record["created_at"] = datetime.now(timezone.utc).isoformat()
        await db["budget"].insert_one(record.copy())
        return {"success": True, "messaggio": f"Budget '{budget.voce}' creato", "id": record["id"]}


@router.get("/budget/{anno}")
@handle_errors
async def get_budget(anno: int) -> Dict[str, Any]:
    """Recupera il budget per l'anno."""
    db = Database.get_db()
    
    budget_items = await db["budget"].find(
        {"anno": anno},
        {"_id": 0}
    ).to_list(100)
    
    totale_costi = sum(b["importo_budget"] for b in budget_items if b["categoria"] == "costo")
    totale_ricavi = sum(b["importo_budget"] for b in budget_items if b["categoria"] == "ricavo")
    
    return {
        "anno": anno,
        "voci": budget_items,
        "totali": {
            "costi_budget": round(totale_costi, 2),
            "ricavi_budget": round(totale_ricavi, 2),
            "margine_budget": round(totale_ricavi - totale_costi, 2)
        }
    }


@router.get("/budget-vs-consuntivo/{anno}")
@handle_errors
async def get_budget_vs_consuntivo(
    anno: int,
    mese: int = None
) -> Dict[str, Any]:
    """
    Confronto budget vs consuntivo.
    Evidenzia scostamenti.
    """
    db = Database.get_db()
    
    # Recupera budget
    budget_data = await get_budget(anno)
    
    # Recupera consuntivo
    consuntivo = await get_analisi_costi_ricavi(anno=anno, mese=mese)
    
    # Proporziona budget se mese specificato
    if mese:
        # Budget mensile = budget annuale / 12
        budget_costi = budget_data["totali"]["costi_budget"] / 12
        budget_ricavi = budget_data["totali"]["ricavi_budget"] / 12
    else:
        budget_costi = budget_data["totali"]["costi_budget"]
        budget_ricavi = budget_data["totali"]["ricavi_budget"]
    
    # Calcola scostamenti
    scostamento_costi = consuntivo["costi"]["totale"] - budget_costi
    scostamento_ricavi = consuntivo["ricavi"]["totale"] - budget_ricavi
    
    return {
        "anno": anno,
        "mese": mese,
        "periodo": consuntivo["periodo"],
        "confronto": {
            "ricavi": {
                "budget": round(budget_ricavi, 2),
                "consuntivo": consuntivo["ricavi"]["totale"],
                "scostamento": round(scostamento_ricavi, 2),
                "scostamento_pct": round(scostamento_ricavi / budget_ricavi * 100, 1) if budget_ricavi > 0 else 0,
                "valutazione": "positivo" if scostamento_ricavi >= 0 else "negativo"
            },
            "costi": {
                "budget": round(budget_costi, 2),
                "consuntivo": consuntivo["costi"]["totale"],
                "scostamento": round(scostamento_costi, 2),
                "scostamento_pct": round(scostamento_costi / budget_costi * 100, 1) if budget_costi > 0 else 0,
                "valutazione": "negativo" if scostamento_costi > 0 else "positivo"  # per i costi, > budget è negativo
            },
            "margine": {
                "budget": round(budget_ricavi - budget_costi, 2),
                "consuntivo": consuntivo["margine"]["importo"],
                "scostamento": round(consuntivo["margine"]["importo"] - (budget_ricavi - budget_costi), 2)
            }
        }
    }


@router.get("/kpi/{anno}")
@handle_errors
async def get_kpi_gestionali(anno: int) -> Dict[str, Any]:
    """
    KPI gestionali principali.
    """
    db = Database.get_db()
    
    # Dati annuali
    analisi = await get_analisi_costi_ricavi(anno=anno)
    
    # Calcola KPI
    ricavi = analisi["ricavi"]["totale"]
    costi = analisi["costi"]["totale"]
    costo_personale = analisi["costi"]["personale"]
    costo_merce = analisi["costi"]["acquisti_merce"]
    
    return {
        "anno": anno,
        "kpi": {
            "margine_operativo": {
                "valore": round(analisi["margine"]["importo"], 2),
                "percentuale": round(analisi["margine"]["percentuale"], 1),
                "descrizione": "Margine sui ricavi"
            },
            "incidenza_personale": {
                "valore": round(costo_personale / ricavi * 100, 1) if ricavi > 0 else 0,
                "descrizione": "% costo personale su ricavi",
                "benchmark": "< 35%"
            },
            "food_cost": {
                "valore": round(costo_merce / ricavi * 100, 1) if ricavi > 0 else 0,
                "descrizione": "% costo materie prime su ricavi",
                "benchmark": "25-35%"
            },
            "costo_medio_giornaliero": {
                "valore": round(costi / 365, 2),
                "descrizione": "Costo operativo medio giornaliero"
            },
            "ricavo_medio_giornaliero": {
                "valore": round(ricavi / 365, 2),
                "descrizione": "Ricavo medio giornaliero"
            }
        },
        "dettaglio": analisi
    }
