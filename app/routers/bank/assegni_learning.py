"""
Learning Machine per Assegni: apprende i pattern fornitore dagli assegni gia'
collegati (``/learn``, che alimenta ``fornitori_keywords``) e ne mostra le
statistiche.

Qui non si abbina e non si cancella piu' niente. Il 28/09/2026 sono stati tolti
«Smart» (``associa-intelligente``: fatture scelte per importo con 5 EUR di
tolleranza, anche gia' pagate), ``associa-combinazioni-avanzato``, i
``suggerimenti`` a 10 EUR e la «Pulizia», che cancellava con ``delete_one``.
Gli abbinamenti li fa solo il motore con identita' e importo al centesimo
(``assegni_fattura_intent``, ``assegni_auto_match``); i doppioni li mette in
quarantena ``assegni_doppioni.unifica``, nel giro dell'estratto conto.
"""
from fastapi import APIRouter, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from collections import Counter, defaultdict
import re
import logging

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()

COLLECTION_ASSEGNI = "assegni"
COLLECTION_LEARNING = "assegni_learning"
COLLECTION_FORNITORI_KEYWORDS = "fornitori_keywords"


# ============================================================
# ENDPOINT: LEARNING MACHINE - APPRENDIMENTO
# ============================================================

@router.post("/learn")
async def learn_associazioni() -> Dict[str, Any]:
    """
    LEARNING MACHINE: Apprende dalle associazioni esistenti.
    
    Analizza gli assegni già associati per creare pattern:
    1. Fornitore → Range importi tipici
    2. Fornitore → Frequenza pagamenti
    3. Pattern descrizione → Fornitore
    4. Combinazioni assegni → Fatture
    
    I pattern appresi vengono salvati nella collection 'assegni_learning'.
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assegni_analizzati": 0,
        "pattern_appresi": 0,
        "fornitori_identificati": 0,
        "dettagli": []
    }
    
    # 1. Carica assegni con associazioni esistenti
    assegni = await db[COLLECTION_ASSEGNI].find({
        "$and": [
            {"beneficiario": {"$exists": True, "$nin": ["", None]}},
            {"$or": [
                {"importo": {"$gt": 0}},
                {"fattura_id": {"$exists": True}}
            ]}
        ]
    }, {"_id": 0}).to_list(10000)
    
    risultati["assegni_analizzati"] = len(assegni)
    
    # 2. Estrai pattern per fornitore
    pattern_fornitori = defaultdict(lambda: {
        "importi": [],
        "numeri_fattura": [],
        "descrizioni": [],
        "date": [],
        "count": 0
    })
    
    for ass in assegni:
        beneficiario = ass.get("beneficiario", "").strip().upper()
        if not beneficiario or len(beneficiario) < 3:
            continue
            
        # Normalizza nome fornitore
        beneficiario_norm = normalizza_nome_fornitore(beneficiario)
        
        pattern = pattern_fornitori[beneficiario_norm]
        pattern["count"] += 1
        
        if ass.get("importo"):
            pattern["importi"].append(float(ass.get("importo")))
        if ass.get("numero_fattura"):
            pattern["numeri_fattura"].append(ass.get("numero_fattura"))
        if ass.get("descrizione"):
            pattern["descrizioni"].append(ass.get("descrizione")[:100])
        if ass.get("data"):
            pattern["date"].append(ass.get("data"))
    
    # 3. Calcola statistiche e salva pattern
    for fornitore, data in pattern_fornitori.items():
        if data["count"] < 1:
            continue
            
        importi = data["importi"]
        
        learning_doc = {
            "id": f"learn_{fornitore[:30].replace(' ', '_')}",
            "fornitore_normalizzato": fornitore,
            "fornitore_originale": fornitore,
            "count_assegni": data["count"],
            "importo_min": min(importi) if importi else 0,
            "importo_max": max(importi) if importi else 0,
            "importo_medio": sum(importi) / len(importi) if importi else 0,
            "importi_frequenti": list(Counter([round(i, 2) for i in importi]).most_common(5)),
            "keywords": list(estrai_keywords(data["descrizioni"])),  # Convert set to list
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Upsert nel database
        await db[COLLECTION_LEARNING].update_one(
            {"id": learning_doc["id"]},
            {"$set": learning_doc},
            upsert=True
        )
        
        risultati["pattern_appresi"] += 1
        risultati["fornitori_identificati"] += 1
        risultati["dettagli"].append({
            "fornitore": fornitore,
            "assegni": data["count"],
            "range_importi": f"€{learning_doc['importo_min']:.2f} - €{learning_doc['importo_max']:.2f}"
        })
    
    # 4. Aggiorna anche fornitori_keywords con dati dagli assegni
    for fornitore, data in pattern_fornitori.items():
        if data["count"] >= 2:  # Solo se ha almeno 2 assegni
            await db[COLLECTION_FORNITORI_KEYWORDS].update_one(
                {"fornitore_nome_normalizzato": fornitore},
                {
                    "$set": {
                        "assegni_count": data["count"],
                        "importo_medio_assegno": sum(data["importi"]) / len(data["importi"]) if data["importi"] else 0,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                },
                upsert=False
            )
    
    return risultati




# ============================================================
# ENDPOINT: STATISTICHE E REPORT
# ============================================================

@router.get("/stats-avanzate")
async def get_stats_avanzate(
    anno: Optional[int] = Query(None, ge=2000, le=2100),
) -> Dict[str, Any]:
    """
    Statistiche avanzate sullo stato degli assegni.
    """
    db = Database.get_db()
    
    query: Dict[str, Any] = {"entity_status": {"$ne": "deleted"}}
    if anno:
        query["$and"] = [{"$or": [
            {"data_emissione": {"$regex": f"^{anno}"}},
            {"data": {"$regex": f"^{anno}"}},
            {"anno_creazione": anno},
            {"anno": anno},
            {"$and": [
                {"data_emissione": {"$in": [None, ""]}},
                {"data": {"$in": [None, ""]}},
                {"anno_creazione": {"$exists": False}},
                {"anno": {"$exists": False}},
                {"created_at": {"$regex": f"^{anno}"}},
            ]},
        ]}]
    tutti = await db[COLLECTION_ASSEGNI].find(query, {"_id": 0}).to_list(10000)

    # I fogli ancora vuoti del carnet sono scorte numerate, non pagamenti.
    # Includerli nel denominatore produceva l'Health Score 45,9% visto live.
    carnet_vuoti = [
        a for a in tutti
        if a.get("stato", "vuoto") == "vuoto" and float(a.get("importo") or 0) <= 0
    ]
    assegni = [a for a in tutti if a not in carnet_vuoti]
    
    # Statistiche base
    totale = len(assegni)
    con_beneficiario = len([a for a in assegni if a.get("beneficiario") and a.get("beneficiario") not in ["", "-", "N/A"]])
    con_fattura = len([
        a for a in assegni
        if a.get("fattura_id") or a.get("fattura_collegata")
        or a.get("numero_fattura") or a.get("fatture_collegate")
    ])
    
    # Per stato
    stati = Counter([a.get("stato", "unknown") for a in assegni])
    
    # Per tipo associazione
    tipi_associazione = Counter([a.get("associazione_tipo", "manuale") for a in assegni if a.get("beneficiario")])
    
    # Importo totale per stato
    importo_per_stato = defaultdict(float)
    for a in assegni:
        stato = a.get("stato", "unknown")
        importo = float(a.get("importo") or 0)
        importo_per_stato[stato] += importo
    
    # Duplicati
    numeri = [a.get("numero", "") for a in assegni]
    duplicati = {k: v for k, v in Counter(numeri).items() if v > 1 and k}
    
    return {
        "totale_assegni": totale,
        "totale_record": len(tutti),
        "carnet_vuoti": len(carnet_vuoti),
        "anno": anno,
        "con_beneficiario": con_beneficiario,
        "senza_beneficiario": totale - con_beneficiario,
        "con_fattura": con_fattura,
        "senza_fattura": totale - con_fattura,
        "per_stato": dict(stati),
        "per_tipo_associazione": dict(tipi_associazione),
        "importo_per_stato": {k: round(v, 2) for k, v in importo_per_stato.items()},
        "duplicati": len(duplicati),
        "health_score": round((con_beneficiario / totale * 100) if totale > 0 else 0, 1)
    }


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def normalizza_nome_fornitore(nome: str) -> str:
    """Normalizza il nome di un fornitore per matching."""
    if not nome:
        return ""
    
    nome = nome.upper().strip()
    
    # Rimuovi suffissi comuni
    suffissi = [" S.R.L.", " SRL", " S.P.A.", " SPA", " S.A.S.", " SAS", 
                " S.N.C.", " SNC", " DI ", " & ", " E "]
    for s in suffissi:
        nome = nome.replace(s, " ")
    
    # Rimuovi caratteri speciali
    nome = re.sub(r'[^\w\s]', '', nome)
    
    # Normalizza spazi
    nome = " ".join(nome.split())
    
    return nome


def estrai_keywords(testi: List[str]) -> set:
    """Estrae keywords significative da una lista di testi."""
    keywords = set()
    
    stopwords = {"DI", "DA", "A", "IN", "CON", "SU", "PER", "TRA", "FRA", 
                 "IL", "LO", "LA", "I", "GLI", "LE", "UN", "UNO", "UNA",
                 "E", "O", "MA", "SE", "CHE", "DEL", "DELLA", "DELLO",
                 "PRELIEVO", "ASSEGNO", "PAGAMENTO", "BONIFICO", "NUM", "CRA", "DM"}
    
    for testo in testi:
        if not testo:
            continue
        
        # Tokenizza
        parole = re.findall(r'\b[A-Za-z]{3,}\b', testo.upper())
        
        for p in parole:
            if p not in stopwords and len(p) >= 4:
                keywords.add(p)
    
    return keywords
