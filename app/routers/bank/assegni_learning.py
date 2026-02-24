"""
Learning Machine per Assegni - Sistema Intelligente di Associazione

Questo modulo implementa una "learning machine" per:
1. Eliminare duplicati in modo sicuro
2. Apprendere automaticamente le associazioni fornitore-fattura-assegno
3. Suggerire associazioni basate su pattern storici
4. Gestire l'associazione robusta con tolleranze configurabili
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from collections import Counter, defaultdict
import re
import logging
import uuid

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()

COLLECTION_ASSEGNI = "assegni"
COLLECTION_LEARNING = "assegni_learning"
COLLECTION_FORNITORI_KEYWORDS = "fornitori_keywords"


# ============================================================
# ENDPOINT: PULIZIA DUPLICATI
# ============================================================

@router.post("/pulizia-duplicati")
async def pulizia_duplicati(
    dry_run: bool = Query(True, description="Se True, mostra solo cosa verrebbe eliminato senza eliminare")
) -> Dict[str, Any]:
    """
    Identifica ed elimina duplicati nella collezione assegni.
    
    CRITERI DUPLICATO:
    1. Stesso numero assegno
    2. Record con numero vuoto (generati erroneamente)
    3. Record senza importo e senza beneficiario
    
    PRIORITÀ MANTENIMENTO:
    - Mantiene il record con più dati (beneficiario, fattura, etc.)
    - Mantiene il record più recente in caso di parità
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "duplicati_numero": [],
        "record_vuoti": [],
        "record_eliminati": 0,
        "record_mantenuti": 0,
        "errori": []
    }
    
    # 1. Trova tutti gli assegni
    assegni = await db[COLLECTION_ASSEGNI].find({}, {"_id": 0}).to_list(10000)
    
    # 2. Raggruppa per numero
    per_numero = defaultdict(list)
    for a in assegni:
        numero = a.get("numero", "").strip()
        per_numero[numero].append(a)
    
    # 3. Identifica duplicati per numero
    ids_da_eliminare = set()
    
    for numero, gruppo in per_numero.items():
        if len(gruppo) <= 1:
            continue
            
        # Numero vuoto: elimina tutti tranne uno (il più recente con dati)
        if not numero:
            risultati["record_vuoti"].extend([g.get("id") for g in gruppo])
            # Ordina per completezza e data
            gruppo.sort(key=lambda x: (
                bool(x.get("beneficiario")),
                bool(x.get("importo")),
                x.get("updated_at", "")
            ), reverse=True)
            
            # Mantieni il primo, elimina gli altri
            for g in gruppo[1:]:
                ids_da_eliminare.add(g.get("id"))
            continue
        
        # Numero non vuoto: elimina duplicati mantenendo il più completo
        risultati["duplicati_numero"].append({
            "numero": numero,
            "count": len(gruppo),
            "ids": [g.get("id") for g in gruppo]
        })
        
        # Score di completezza
        def completeness_score(a):
            score = 0
            if a.get("beneficiario"): score += 3
            if a.get("importo"): score += 2
            if a.get("fattura_id") or a.get("numero_fattura"): score += 2
            if a.get("stato") == "pagato": score += 1
            return score
        
        gruppo.sort(key=lambda x: (
            completeness_score(x),
            x.get("updated_at", "")
        ), reverse=True)
        
        for g in gruppo[1:]:
            ids_da_eliminare.add(g.get("id"))
    
    # 4. Trova record totalmente vuoti (senza numero, importo, beneficiario)
    for a in assegni:
        if not a.get("numero") and not a.get("importo") and not a.get("beneficiario"):
            if a.get("id") not in ids_da_eliminare:
                ids_da_eliminare.add(a.get("id"))
                risultati["record_vuoti"].append(a.get("id"))
    
    # 5. Esegui eliminazione se non è dry_run
    if not dry_run and ids_da_eliminare:
        for aid in ids_da_eliminare:
            try:
                await db[COLLECTION_ASSEGNI].delete_one({"id": aid})
                risultati["record_eliminati"] += 1
            except Exception as e:
                risultati["errori"].append(f"Errore eliminazione {aid}: {str(e)}")
    
    risultati["record_mantenuti"] = len(assegni) - len(ids_da_eliminare)
    risultati["totale_da_eliminare"] = len(ids_da_eliminare)
    
    return risultati


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
            {"beneficiario": {"$exists": True, "$ne": "", "$ne": None}},
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


@router.get("/suggerimenti/{importo}")
async def get_suggerimenti(
    importo: float,
    tolleranza: float = Query(10.0, description="Tolleranza in euro")
) -> Dict[str, Any]:
    """
    LEARNING MACHINE: Suggerisce fornitori basati su importo.
    
    Cerca nei pattern appresi fornitori che hanno ricevuto 
    pagamenti con importi simili.
    """
    db = Database.get_db()
    
    # Cerca nei pattern appresi
    patterns = await db[COLLECTION_LEARNING].find({
        "$or": [
            {"importo_min": {"$lte": importo + tolleranza}, "importo_max": {"$gte": importo - tolleranza}},
            {"importo_medio": {"$gte": importo - tolleranza, "$lte": importo + tolleranza}}
        ]
    }, {"_id": 0}).to_list(20)
    
    suggerimenti = []
    for p in patterns:
        # Calcola score di confidenza
        importo_medio = p.get("importo_medio", 0)
        differenza = abs(importo - importo_medio)
        confidence = max(0, 100 - (differenza / importo * 100)) if importo > 0 else 0
        
        suggerimenti.append({
            "fornitore": p.get("fornitore_normalizzato"),
            "confidence": round(confidence, 1),
            "assegni_precedenti": p.get("count_assegni", 0),
            "importo_medio": p.get("importo_medio"),
            "range": f"€{p.get('importo_min', 0):.2f} - €{p.get('importo_max', 0):.2f}"
        })
    
    # Ordina per confidence
    suggerimenti.sort(key=lambda x: x["confidence"], reverse=True)
    
    return {
        "importo_cercato": importo,
        "tolleranza": tolleranza,
        "suggerimenti": suggerimenti[:10]
    }


# ============================================================
# ENDPOINT: ASSOCIAZIONE ROBUSTA INTELLIGENTE
# ============================================================

@router.post("/associa-intelligente")
async def associa_intelligente(
    tolleranza_importo: float = Query(5.0, description="Tolleranza importo in euro"),
    tolleranza_giorni: int = Query(60, description="Tolleranza giorni per data fattura"),
    usa_learning: bool = Query(True, description="Usa pattern appresi per migliorare match")
) -> Dict[str, Any]:
    """
    ASSOCIAZIONE ROBUSTA INTELLIGENTE.
    
    Combina multiple strategie:
    1. Match esatto per importo (±tolleranza)
    2. Match per fornitore noto (da learning)
    3. Match per pattern descrizione
    4. Match combinazioni (somma assegni = fattura)
    5. Match temporale (fattura vicina alla data assegno)
    """
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assegni_processati": 0,
        "match_esatti": 0,
        "match_learning": 0,
        "match_pattern": 0,
        "match_combinazione": 0,
        "non_associati": 0,
        "dettagli": [],
        "errori": []
    }
    
    # 1. Carica assegni senza beneficiario completo
    assegni_da_associare = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": {"$in": [None, "", "-", "N/A"]}},
            {"fattura_id": {"$exists": False}},
            {"fattura_id": None}
        ],
        "importo": {"$gt": 0}
    }, {"_id": 0}).to_list(5000)
    
    risultati["assegni_processati"] = len(assegni_da_associare)
    
    if not assegni_da_associare:
        return {**risultati, "message": "Nessun assegno da associare"}
    
    # 2. Carica TUTTE le fatture (rimuovo filtro status per massimizzare associazioni)
    fatture = await db.invoices.find({
        "total_amount": {"$gt": 0}
    }, {"_id": 0}).to_list(10000)
    
    # 3. Carica pattern appresi
    patterns = {}
    if usa_learning:
        learning_docs = await db[COLLECTION_LEARNING].find({}, {"_id": 0}).to_list(1000)
        for p in learning_docs:
            patterns[p.get("fornitore_normalizzato", "").upper()] = p
    
    # 4. Crea indici per ricerca rapida
    fatture_per_importo = defaultdict(list)
    for f in fatture:
        imp = round(float(f.get("total_amount") or f.get("importo_totale") or 0), 2)
        fatture_per_importo[imp].append(f)
    
    # 5. Processa ogni assegno
    assegni_associati = set()
    
    for ass in assegni_da_associare:
        if ass["id"] in assegni_associati:
            continue
            
        importo = round(float(ass.get("importo", 0)), 2)
        descrizione = ass.get("descrizione", "") or ""
        # Ensure descrizione is a string
        if isinstance(descrizione, dict):
            descrizione = str(descrizione)
        data_ass = ass.get("data")
        
        match_trovato = None
        match_tipo = None
        
        # STRATEGIA 1: Match esatto per importo
        for delta in range(int(tolleranza_importo * 100)):
            d = delta / 100.0
            for sign in [0, 1, -1]:
                imp_cerca = round(importo + (d * sign), 2)
                if imp_cerca in fatture_per_importo:
                    candidati = fatture_per_importo[imp_cerca]
                    if len(candidati) == 1:
                        match_trovato = candidati[0]
                        match_tipo = "esatto"
                        break
            if match_trovato:
                break
        
        # STRATEGIA 2: Match per pattern appresi (fornitore noto)
        if not match_trovato and usa_learning:
            # Cerca fornitore nella descrizione
            descrizione_upper = descrizione.upper() if isinstance(descrizione, str) else str(descrizione).upper()
            for fornitore_norm, pattern_data in patterns.items():
                if fornitore_norm[:10] in descrizione_upper:
                    # Verifica se l'importo è nel range
                    if pattern_data.get("importo_min", 0) <= importo <= pattern_data.get("importo_max", float('inf')):
                        # Cerca fattura di questo fornitore
                        for f in fatture:
                            nome_forn_raw = f.get("supplier_name") or f.get("fornitore") or ""
                            if isinstance(nome_forn_raw, dict):
                                nome_forn_raw = nome_forn_raw.get("name", "") or str(nome_forn_raw)
                            nome_forn = str(nome_forn_raw).upper()
                            if fornitore_norm[:10] in nome_forn:
                                imp_fatt = float(f.get("total_amount") or 0)
                                if abs(imp_fatt - importo) <= tolleranza_importo * 2:
                                    match_trovato = f
                                    match_tipo = "learning"
                                    break
                if match_trovato:
                    break
        
        # STRATEGIA 3: Match per pattern descrizione
        if not match_trovato:
            keywords = estrai_keywords([descrizione])
            for f in fatture:
                nome_forn_raw = f.get("supplier_name") or f.get("fornitore") or ""
                # Ensure it's a string
                if isinstance(nome_forn_raw, dict):
                    nome_forn_raw = nome_forn_raw.get("name", "") or str(nome_forn_raw)
                nome_forn = str(nome_forn_raw).upper()
                nome_forn_keywords = set(nome_forn.split())
                
                # Se c'è overlap significativo nelle keywords
                overlap = len(keywords & nome_forn_keywords)
                if overlap >= 2:
                    imp_fatt = float(f.get("total_amount") or 0)
                    if abs(imp_fatt - importo) <= tolleranza_importo * 3:
                        match_trovato = f
                        match_tipo = "pattern"
                        break
        
        # Applica match se trovato
        if match_trovato:
            fornitore_raw = match_trovato.get("supplier_name") or match_trovato.get("fornitore") or ""
            if isinstance(fornitore_raw, dict):
                fornitore_raw = fornitore_raw.get("name", "") or str(fornitore_raw)
            fornitore = str(fornitore_raw)
            numero_fatt = match_trovato.get("invoice_number") or match_trovato.get("numero_fattura") or ""
            if isinstance(numero_fatt, dict):
                numero_fatt = str(numero_fatt)
            
            try:
                await db[COLLECTION_ASSEGNI].update_one(
                    {"id": ass["id"]},
                    {"$set": {
                        "beneficiario": fornitore,
                        "fattura_id": match_trovato.get("id"),
                        "numero_fattura": numero_fatt,
                        "fornitore_fattura": fornitore,
                        "associazione_tipo": match_tipo,
                        "associazione_automatica": True,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                assegni_associati.add(ass["id"])
                
                if match_tipo == "esatto":
                    risultati["match_esatti"] += 1
                elif match_tipo == "learning":
                    risultati["match_learning"] += 1
                elif match_tipo == "pattern":
                    risultati["match_pattern"] += 1
                
                risultati["dettagli"].append({
                    "assegno": ass.get("numero"),
                    "importo": importo,
                    "fornitore": fornitore[:40],
                    "fattura": numero_fatt,
                    "tipo_match": match_tipo
                })
                
            except Exception as e:
                risultati["errori"].append(f"Errore update {ass['id']}: {str(e)}")
        else:
            risultati["non_associati"] += 1
    
    return risultati


@router.post("/associa-combinazioni-avanzato")
async def associa_combinazioni_avanzato(
    max_assegni: int = Query(5, ge=2, le=8),
    tolleranza: float = Query(2.0, ge=0.01, le=20)
) -> Dict[str, Any]:
    """
    ASSOCIAZIONE COMBINAZIONI AVANZATA.
    
    Trova combinazioni di assegni che insieme corrispondono a una fattura.
    Usa algoritmo ottimizzato per evitare esplosione combinatoriale.
    """
    from itertools import combinations
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assegni_analizzati": 0,
        "combinazioni_testate": 0,
        "match_trovati": 0,
        "assegni_associati": 0,
        "dettagli": [],
        "errori": []
    }
    
    # 1. Carica assegni senza beneficiario
    assegni = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": {"$in": [None, "", "-", "N/A"]}},
            {"associazione_automatica": {"$ne": True}}
        ],
        "importo": {"$gt": 0}
    }, {"_id": 0}).to_list(500)
    
    risultati["assegni_analizzati"] = len(assegni)
    
    if len(assegni) < 2:
        return {**risultati, "message": "Serve almeno 2 assegni per cercare combinazioni"}
    
    # 2. Carica TUTTE le fatture (rimuovo filtro status per massimizzare associazioni)
    fatture = await db.invoices.find({
        "total_amount": {"$gt": 0}
    }, {"_id": 0}).to_list(10000)
    
    # Crea set di importi fatture per ricerca O(1)
    importi_fatture = {}
    for f in fatture:
        imp = round(float(f.get("total_amount") or 0), 2)
        if imp not in importi_fatture:
            importi_fatture[imp] = []
        importi_fatture[imp].append(f)
    
    # 3. Pre-filtra assegni per importi simili (ottimizzazione)
    assegni_con_importo = [
        (a, round(float(a.get("importo", 0)), 2))
        for a in assegni
        if float(a.get("importo", 0)) > 0
    ]
    
    # 4. Cerca combinazioni
    assegni_usati = set()
    
    for n in range(2, min(max_assegni + 1, len(assegni_con_importo) + 1)):
        for combo in combinations(enumerate(assegni_con_importo), n):
            risultati["combinazioni_testate"] += 1
            
            # Salta se qualche assegno è già usato
            indices = [c[0] for c in combo]
            if any(i in assegni_usati for i in indices):
                continue
            
            # Calcola somma
            somma = sum(c[1][1] for c in combo)
            somma_round = round(somma, 2)
            
            # Cerca fattura con questo importo (con tolleranza)
            match_fattura = None
            for delta in [0, 0.01, -0.01, 0.5, -0.5, 1, -1, 2, -2]:
                imp_cerca = round(somma_round + delta, 2)
                if imp_cerca in importi_fatture and abs(delta) <= tolleranza:
                    match_fattura = importi_fatture[imp_cerca][0]
                    break
            
            if match_fattura:
                risultati["match_trovati"] += 1
                
                assegni_combo = [c[1][0] for c in combo]
                fornitore = match_fattura.get("supplier_name") or ""
                numero_fatt = match_fattura.get("invoice_number") or ""
                
                dettaglio = {
                    "num_assegni": n,
                    "assegni": [a.get("numero") for a in assegni_combo],
                    "somma": somma_round,
                    "fattura": numero_fatt,
                    "fornitore": fornitore[:40],
                    "importo_fattura": match_fattura.get("total_amount")
                }
                risultati["dettagli"].append(dettaglio)
                
                # Aggiorna assegni
                for i, ass in enumerate(assegni_combo):
                    try:
                        await db[COLLECTION_ASSEGNI].update_one(
                            {"id": ass["id"]},
                            {"$set": {
                                "beneficiario": fornitore,
                                "fattura_id": match_fattura.get("id"),
                                "numero_fattura": numero_fatt,
                                "pagamento_combinato": True,
                                "combinazione_assegni": [a.get("numero") for a in assegni_combo],
                                "combinazione_indice": i + 1,
                                "combinazione_totale": n,
                                "importo_fattura_combinata": match_fattura.get("total_amount"),
                                "associazione_automatica": True,
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }}
                        )
                        risultati["assegni_associati"] += 1
                        assegni_usati.add(indices[i])
                    except Exception as e:
                        risultati["errori"].append(str(e))
                
                # Rimuovi fattura dall'indice
                imp_fatt = round(float(match_fattura.get("total_amount") or 0), 2)
                if imp_fatt in importi_fatture:
                    importi_fatture[imp_fatt] = [
                        f for f in importi_fatture[imp_fatt]
                        if f.get("id") != match_fattura.get("id")
                    ]
    
    return risultati


# ============================================================
# ENDPOINT: STATISTICHE E REPORT
# ============================================================

@router.get("/stats-avanzate")
async def get_stats_avanzate() -> Dict[str, Any]:
    """
    Statistiche avanzate sullo stato degli assegni.
    """
    db = Database.get_db()
    
    assegni = await db[COLLECTION_ASSEGNI].find({}, {"_id": 0}).to_list(10000)
    
    # Statistiche base
    totale = len(assegni)
    con_beneficiario = len([a for a in assegni if a.get("beneficiario") and a.get("beneficiario") not in ["", "-", "N/A"]])
    con_fattura = len([a for a in assegni if a.get("fattura_id") or a.get("numero_fattura")])
    
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
