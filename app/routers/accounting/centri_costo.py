"""
Centri di Costo e Utile Obiettivo Router
Sistema di contabilità analitica per bar-pasticceria
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, date
from app.database import Database, Collections

router = APIRouter()

# ============== CENTRI DI COSTO ==============

# Struttura standard TeamSystem per Bar/Pasticceria
CDC_STANDARD = {
    # Centri Operativi (generano ricavi)
    "CDC-01": {"nome": "BAR / CAFFETTERIA", "tipo": "operativo", "descrizione": "Vendita caffè, bevande calde/fredde, snack"},
    "CDC-02": {"nome": "PASTICCERIA", "tipo": "operativo", "descrizione": "Vendita dolci, torte, pasticcini"},
    "CDC-03": {"nome": "LABORATORIO", "tipo": "operativo", "descrizione": "Produzione interna dolci e semilavorati"},
    "CDC-04": {"nome": "ASPORTO / DELIVERY", "tipo": "operativo", "descrizione": "Vendite da asporto e consegne"},
    
    # Centri di Supporto (costi da ribaltare)
    "CDC-90": {"nome": "PERSONALE", "tipo": "supporto", "descrizione": "Costi del personale da ribaltare"},
    "CDC-91": {"nome": "AMMINISTRAZIONE", "tipo": "supporto", "descrizione": "Costi amministrativi e gestionali"},
    "CDC-92": {"nome": "MARKETING", "tipo": "supporto", "descrizione": "Pubblicità, promozioni, social"},
    
    # Centro Struttura (costi fissi)
    "CDC-99": {"nome": "COSTI GENERALI / STRUTTURA", "tipo": "struttura", "descrizione": "Affitto, utenze, manutenzione"}
}

# Mapping automatico categoria_contabile → centro di costo
CATEGORIA_TO_CDC = {
    # BAR / CAFFETTERIA
    "caffe": "CDC-01",
    "bevande": "CDC-01",
    "bevande_alcoliche": "CDC-01",
    "birra": "CDC-01",
    "vino": "CDC-01",
    "bibite": "CDC-01",
    "snack": "CDC-01",
    
    # PASTICCERIA
    "pasticceria": "CDC-02",
    "dolci": "CDC-02",
    "torte": "CDC-02",
    "gelato": "CDC-02",
    
    # LABORATORIO (materie prime per produzione)
    "alimentari": "CDC-03",
    "latticini": "CDC-03",
    "uova": "CDC-03",
    "farine": "CDC-03",
    "zucchero": "CDC-03",
    "surgelati": "CDC-03",
    "frutta": "CDC-03",
    "cioccolato": "CDC-03",
    
    # ASPORTO / DELIVERY
    "imballaggi": "CDC-04",
    "packaging": "CDC-04",
    "delivery": "CDC-04",
    
    # PERSONALE
    "stipendi": "CDC-90",
    "contributi": "CDC-90",
    "tfr": "CDC-90",
    
    # AMMINISTRAZIONE
    "consulenze": "CDC-91",
    "commercialista": "CDC-91",
    "software": "CDC-91",
    "canoni_abbonamenti": "CDC-91",
    
    # MARKETING
    "pubblicita": "CDC-92",
    "marketing": "CDC-92",
    
    # COSTI GENERALI
    "affitto": "CDC-99",
    "utenze_elettricita": "CDC-99",
    "utenze_gas": "CDC-99",
    "utenze_acqua": "CDC-99",
    "telefonia": "CDC-99",
    "manutenzione": "CDC-99",
    "pulizia": "CDC-99",
    "assicurazioni": "CDC-99",
    "noleggio_auto": "CDC-99",
    "carburante": "CDC-99",
    "ferramenta": "CDC-99",
    "materiale_edile": "CDC-99"
}

# Mapping fornitore → centro di costo (per fornitori specifici)
FORNITORE_TO_CDC = {
    "KIMBO": "CDC-01",  # Caffè
    "LAVAZZA": "CDC-01",
    "ILLY": "CDC-01",
    "COCA": "CDC-01",
    "PEPSI": "CDC-01",
    "PERONI": "CDC-01",
    "HEINEKEN": "CDC-01",
    "ENEL": "CDC-99",  # Utenze
    "EDISON": "CDC-99",
    "ENI": "CDC-99",
    "TELECOM": "CDC-99",
    "TIM": "CDC-99",
    "VODAFONE": "CDC-99",
    "ARVAL": "CDC-99",  # Noleggio auto
    "LEASYS": "CDC-99",
    "ALD": "CDC-99"
}


@router.get("")
async def list_centri_costo() -> List[Dict[str, Any]]:
    """Lista tutti i centri di costo con statistiche."""
    db = Database.get_db()
    
    # Verifica se esistono nel DB, altrimenti usa standard
    centri = await db["centri_costo"].find({}, {"_id": 0}).to_list(100)
    
    if not centri:
        # Inizializza con struttura standard
        centri = []
        for codice, dati in CDC_STANDARD.items():
            centro = {
                "codice": codice,
                **dati,
                "attivo": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            centri.append(centro.copy())  # Usa copy() per evitare che insert_many modifichi
        
        # Salva nel DB (crea copie per evitare mutazione con _id)
        centri_to_insert = [c.copy() for c in centri]
        await db["centri_costo"].insert_many(centri_to_insert)
    
    # Aggiungi statistiche per ogni centro
    for centro in centri:
        codice = centro["codice"]
        
        # Conta fatture associate
        fatture_count = await db[Collections.INVOICES].count_documents({"centro_costo": codice})
        fatture_totale = 0
        
        pipeline = [
            {"$match": {"centro_costo": codice}},
            {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
        ]
        result = await db[Collections.INVOICES].aggregate(pipeline).to_list(1)
        if result:
            fatture_totale = result[0].get("totale", 0)
        
        centro["fatture_count"] = fatture_count
        centro["fatture_totale"] = round(fatture_totale, 2)
    
    return centri


@router.post("")
async def create_centro_costo(data: Dict[str, Any] = Body(...)) -> Dict[str, str]:
    """Crea nuovo centro di costo."""
    db = Database.get_db()
    
    codice = data.get("codice")
    if not codice:
        raise HTTPException(status_code=400, detail="Codice centro di costo obbligatorio")
    
    # Verifica duplicato
    existing = await db["centri_costo"].find_one({"codice": codice})
    if existing:
        raise HTTPException(status_code=400, detail=f"Centro di costo {codice} già esistente")
    
    centro = {
        "codice": codice,
        "nome": data.get("nome", codice),
        "tipo": data.get("tipo", "operativo"),
        "descrizione": data.get("descrizione", ""),
        "attivo": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["centri_costo"].insert_one(centro.copy())
    return {"message": f"Centro di costo {codice} creato", "codice": codice}


@router.get("/mapping-categorie")
async def get_mapping_categorie() -> Dict[str, Any]:
    """Restituisce il mapping categoria → centro di costo."""
    return {
        "categoria_to_cdc": CATEGORIA_TO_CDC,
        "fornitore_to_cdc": FORNITORE_TO_CDC,
        "cdc_standard": CDC_STANDARD
    }


@router.post("/assegna-cdc-fatture")
async def assegna_cdc_fatture(
    anno: Optional[int] = Query(None),
    force: bool = Query(False, description="Sovrascrive assegnazioni esistenti")
) -> Dict[str, Any]:
    """
    Assegna automaticamente i centri di costo alle fatture
    basandosi su categoria_contabile e fornitore.
    """
    db = Database.get_db()
    
    query = {}
    if anno:
        query["invoice_date"] = {"$regex": f"^{anno}"}
    
    if not force:
        query["centro_costo"] = {"$exists": False}
    
    fatture = await db[Collections.INVOICES].find(query, {"_id": 1, "categoria_contabile": 1, "supplier_name": 1}).to_list(10000)
    
    updated = 0
    stats = {}
    
    for fatt in fatture:
        cdc = None
        
        # 1. Prima prova con categoria
        categoria = fatt.get("categoria_contabile", "").lower()
        if categoria in CATEGORIA_TO_CDC:
            cdc = CATEGORIA_TO_CDC[categoria]
        
        # 2. Se non trovato, prova con fornitore
        if not cdc:
            supplier = (fatt.get("supplier_name") or "").upper()
            for key, value in FORNITORE_TO_CDC.items():
                if key in supplier:
                    cdc = value
                    break
        
        # 3. Default: costi generali
        if not cdc:
            cdc = "CDC-99"
        
        # Aggiorna fattura
        await db[Collections.INVOICES].update_one(
            {"_id": fatt["_id"]},
            {"$set": {"centro_costo": cdc, "cdc_auto_assigned": True}}
        )
        updated += 1
        stats[cdc] = stats.get(cdc, 0) + 1
    
    return {
        "message": f"Assegnati {updated} centri di costo",
        "fatture_aggiornate": updated,
        "distribuzione": stats
    }


# ============== UTILE OBIETTIVO ==============

@router.get("/utile-obiettivo")
async def get_utile_obiettivo(anno: int = Query(...)) -> Dict[str, Any]:
    """
    Recupera il target di utile e calcola lo stato attuale.
    """
    db = Database.get_db()
    
    # Recupera target
    target = await db["utile_obiettivo"].find_one({"anno": anno}, {"_id": 0})
    
    if not target:
        # Default se non configurato
        target = {
            "anno": anno,
            "utile_target_annuo": 50000,
            "margine_medio_atteso": 0.35,
            "giorni_lavorativi_anno": 300,
            "configurato": False
        }
    
    # Calcola dati reali
    date_start = f"{anno}-01-01"
    date_end = f"{anno}-12-31"
    
    # Ricavi da corrispettivi
    ricavi_pipeline = [
        {"$match": {"data": {"$gte": date_start, "$lte": date_end}}},
        {"$group": {"_id": None, "totale": {"$sum": "$totale"}}}
    ]
    ricavi_result = await db[Collections.CORRISPETTIVI].aggregate(ricavi_pipeline).to_list(1)
    ricavi_totali = ricavi_result[0]["totale"] if ricavi_result else 0
    
    # Costi da fatture
    costi_pipeline = [
        {"$match": {"invoice_date": {"$gte": date_start, "$lte": date_end}}},
        {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
    ]
    costi_result = await db[Collections.INVOICES].aggregate(costi_pipeline).to_list(1)
    costi_totali = costi_result[0]["totale"] if costi_result else 0
    
    # Calcoli
    utile_corrente = ricavi_totali - costi_totali
    utile_target = target.get("utile_target_annuo", 50000)
    scostamento = utile_corrente - utile_target
    
    # Giorni trascorsi nell'anno
    oggi = date.today()
    if oggi.year == anno:
        giorni_trascorsi = (oggi - date(anno, 1, 1)).days + 1
    else:
        giorni_trascorsi = 365
    
    giorni_lavorativi = target.get("giorni_lavorativi_anno", 300)
    giorni_lavorativi_trascorsi = int(giorni_trascorsi * (giorni_lavorativi / 365))
    giorni_rimanenti = giorni_lavorativi - giorni_lavorativi_trascorsi
    
    # Utile target proporzionato
    utile_target_ad_oggi = (utile_target / giorni_lavorativi) * giorni_lavorativi_trascorsi
    scostamento_ad_oggi = utile_corrente - utile_target_ad_oggi
    
    # Proiezione fine anno
    if giorni_trascorsi > 0:
        utile_proiezione = (utile_corrente / giorni_trascorsi) * 365
    else:
        utile_proiezione = 0
    
    # Calcolo azioni necessarie
    margine_medio = target.get("margine_medio_atteso", 0.35)
    
    if scostamento < 0:
        # Siamo sotto target
        ricavi_necessari = abs(scostamento) / margine_medio
        costi_da_tagliare = abs(scostamento)
    else:
        ricavi_necessari = 0
        costi_da_tagliare = 0
    
    return {
        "anno": anno,
        "target": {
            "utile_target_annuo": utile_target,
            "utile_target_ad_oggi": round(utile_target_ad_oggi, 2),
            "margine_medio_atteso": margine_medio,
            "giorni_lavorativi_anno": giorni_lavorativi,
            "configurato": target.get("configurato", False)
        },
        "reale": {
            "ricavi_totali": round(ricavi_totali, 2),
            "costi_totali": round(costi_totali, 2),
            "utile_corrente": round(utile_corrente, 2),
            "margine_reale": round(utile_corrente / ricavi_totali, 4) if ricavi_totali > 0 else 0
        },
        "analisi": {
            "scostamento_target": round(scostamento, 2),
            "scostamento_ad_oggi": round(scostamento_ad_oggi, 2),
            "stato": "IN_TARGET" if scostamento_ad_oggi >= 0 else "SOTTO_TARGET",
            "percentuale_raggiungimento": round((utile_corrente / utile_target_ad_oggi) * 100, 1) if utile_target_ad_oggi > 0 else 0,
            "utile_proiezione_fine_anno": round(utile_proiezione, 2)
        },
        "tempo": {
            "giorni_trascorsi": giorni_trascorsi,
            "giorni_lavorativi_trascorsi": giorni_lavorativi_trascorsi,
            "giorni_rimanenti": giorni_rimanenti
        },
        "azioni_suggerite": {
            "ricavi_aggiuntivi_necessari": round(ricavi_necessari, 2) if scostamento < 0 else 0,
            "costi_da_ridurre": round(costi_da_tagliare, 2) if scostamento < 0 else 0,
            "utile_giornaliero_necessario": round(abs(scostamento) / max(giorni_rimanenti, 1), 2) if scostamento < 0 else 0
        }
    }


@router.post("/utile-obiettivo")
async def set_utile_obiettivo(data: Dict[str, Any] = Body(...)) -> Dict[str, str]:
    """Imposta il target di utile per un anno."""
    db = Database.get_db()
    
    anno = data.get("anno")
    if not anno:
        raise HTTPException(status_code=400, detail="Anno obbligatorio")
    
    target = {
        "anno": anno,
        "utile_target_annuo": data.get("utile_target_annuo", 50000),
        "utile_target_mensile": data.get("utile_target_annuo", 50000) / 12,
        "margine_medio_atteso": data.get("margine_medio_atteso", 0.35),
        "giorni_lavorativi_anno": data.get("giorni_lavorativi_anno", 300),
        "note": data.get("note", ""),
        "configurato": True,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["utile_obiettivo"].update_one(
        {"anno": anno},
        {"$set": target},
        upsert=True
    )
    
    return {"message": f"Target utile {anno} impostato: €{target['utile_target_annuo']:,.2f}"}


@router.get("/utile-obiettivo/suggerimenti")
async def get_suggerimenti_utile(anno: int = Query(...)) -> Dict[str, Any]:
    """
    Genera suggerimenti intelligenti per raggiungere l'utile obiettivo.
    Motore decisionale stile TeamSystem.
    """
    db = Database.get_db()
    
    # Recupera dati base
    stato = await get_utile_obiettivo(anno)
    
    suggerimenti = []
    priorita = "NORMALE"
    
    scostamento = stato["analisi"]["scostamento_ad_oggi"]
    ricavi = stato["reale"]["ricavi_totali"]
    costi = stato["reale"]["costi_totali"]
    
    if scostamento < 0:
        priorita = "ALTA" if abs(scostamento) > 5000 else "MEDIA"
        
        # Suggerimenti per recuperare
        ricavi_necessari = stato["azioni_suggerite"]["ricavi_aggiuntivi_necessari"]
        costi_da_ridurre = stato["azioni_suggerite"]["costi_da_ridurre"]
        
        suggerimenti.append({
            "tipo": "CRITICO",
            "messaggio": f"Per raggiungere l'utile target mancano €{abs(scostamento):,.2f}",
            "azione": None
        })
        
        suggerimenti.append({
            "tipo": "OPZIONE_A",
            "messaggio": f"Aumentare i ricavi di €{ricavi_necessari:,.2f} (con margine {stato['target']['margine_medio_atteso']*100:.0f}%)",
            "azione": "incremento_vendite"
        })
        
        suggerimenti.append({
            "tipo": "OPZIONE_B",
            "messaggio": f"Ridurre i costi di €{costi_da_ridurre:,.2f}",
            "azione": "riduzione_costi"
        })
        
        # Analisi per centro di costo
        cdc_pipeline = [
            {"$match": {"invoice_date": {"$regex": f"^{anno}"}, "centro_costo": {"$exists": True}}},
            {"$group": {"_id": "$centro_costo", "totale": {"$sum": "$total_amount"}}},
            {"$sort": {"totale": -1}}
        ]
        cdc_costi = await db[Collections.INVOICES].aggregate(cdc_pipeline).to_list(10)
        
        if cdc_costi:
            top_cdc = cdc_costi[0]
            cdc_nome = CDC_STANDARD.get(top_cdc["_id"], {}).get("nome", top_cdc["_id"])
            suggerimenti.append({
                "tipo": "ANALISI_CDC",
                "messaggio": f"Il centro di costo più costoso è {cdc_nome} con €{top_cdc['totale']:,.2f}",
                "azione": "analizza_cdc",
                "cdc": top_cdc["_id"]
            })
    
    else:
        priorita = "BASSA"
        suggerimenti.append({
            "tipo": "POSITIVO",
            "messaggio": f"Sei in linea con l'obiettivo! Surplus di €{scostamento:,.2f}",
            "azione": None
        })
        
        # Proiezione
        proiezione = stato["analisi"]["utile_proiezione_fine_anno"]
        target = stato["target"]["utile_target_annuo"]
        if proiezione > target:
            suggerimenti.append({
                "tipo": "PROIEZIONE",
                "messaggio": f"Proiezione fine anno: €{proiezione:,.2f} (+{((proiezione/target)-1)*100:.1f}% vs target)",
                "azione": None
            })
    
    return {
        "anno": anno,
        "priorita": priorita,
        "suggerimenti": suggerimenti,
        "stato_corrente": stato["analisi"]["stato"],
        "percentuale_raggiungimento": stato["analisi"]["percentuale_raggiungimento"]
    }


@router.get("/utile-obiettivo/per-cdc")
async def get_utile_per_cdc(anno: int = Query(...)) -> Dict[str, Any]:
    """
    Analisi utile/margine per centro di costo.
    """
    db = Database.get_db()
    
    date_start = f"{anno}-01-01"
    date_end = f"{anno}-12-31"
    
    # Costi per CDC
    costi_pipeline = [
        {"$match": {"invoice_date": {"$gte": date_start, "$lte": date_end}}},
        {"$group": {
            "_id": {"$ifNull": ["$centro_costo", "CDC-99"]},
            "totale_costi": {"$sum": "$total_amount"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"totale_costi": -1}}
    ]
    costi_per_cdc = await db[Collections.INVOICES].aggregate(costi_pipeline).to_list(20)
    
    # Ricavi totali (per ora tutti su CDC-01 e CDC-02)
    ricavi_result = await db[Collections.CORRISPETTIVI].aggregate([
        {"$match": {"data": {"$gte": date_start, "$lte": date_end}}},
        {"$group": {"_id": None, "totale": {"$sum": "$totale"}}}
    ]).to_list(1)
    ricavi_totali = ricavi_result[0]["totale"] if ricavi_result else 0
    
    # Costruisci report per CDC
    report = []
    costi_totali = sum(c["totale_costi"] for c in costi_per_cdc)
    
    for cdc in costi_per_cdc:
        codice = cdc["_id"]
        info = CDC_STANDARD.get(codice, {"nome": codice, "tipo": "altro"})
        
        # Stima ricavi proporzionali (semplificato)
        # In un sistema completo, i ricavi sarebbero tracciati per CDC
        peso_costi = cdc["totale_costi"] / costi_totali if costi_totali > 0 else 0
        
        # Solo CDC operativi hanno ricavi
        if info.get("tipo") == "operativo":
            ricavi_cdc = ricavi_totali * peso_costi * 1.5  # Stima
        else:
            ricavi_cdc = 0
        
        margine = ricavi_cdc - cdc["totale_costi"]
        margine_perc = (margine / ricavi_cdc * 100) if ricavi_cdc > 0 else 0
        
        report.append({
            "codice": codice,
            "nome": info.get("nome", codice),
            "tipo": info.get("tipo", "altro"),
            "costi": round(cdc["totale_costi"], 2),
            "ricavi_stimati": round(ricavi_cdc, 2),
            "margine": round(margine, 2),
            "margine_percentuale": round(margine_perc, 1),
            "fatture_count": cdc["count"],
            "stato": "PROFITTO" if margine > 0 else "PERDITA"
        })
    
    return {
        "anno": anno,
        "centri_costo": report,
        "totali": {
            "ricavi": round(ricavi_totali, 2),
            "costi": round(costi_totali, 2),
            "margine": round(ricavi_totali - costi_totali, 2)
        }
    }



# ============== RIBALTAMENTO CDC ==============

# Chiavi di ribaltamento standard per i centri di supporto
CHIAVI_RIBALTAMENTO = {
    "CDC-05": {  # Personale
        "descrizione": "Costo personale ribaltato sui centri operativi",
        "criteri": {
            "CDC-01": 0.50,  # 50% Bar
            "CDC-02": 0.50   # 50% Pasticceria
        }
    },
    "CDC-06": {  # Amministrazione
        "descrizione": "Costi amministrativi ribaltati sui centri operativi",
        "criteri": {
            "CDC-01": 0.50,
            "CDC-02": 0.50
        }
    },
    "CDC-03": {  # Utenze
        "descrizione": "Utenze ribaltate sui centri operativi",
        "criteri": {
            "CDC-01": 0.40,
            "CDC-02": 0.60
        }
    },
    "CDC-04": {  # Manutenzione
        "descrizione": "Manutenzione ribaltata sui centri operativi",
        "criteri": {
            "CDC-01": 0.35,
            "CDC-02": 0.65
        }
    },
    "CDC-07": {  # Marketing
        "descrizione": "Marketing ribaltato sui centri operativi",
        "criteri": {
            "CDC-01": 0.45,
            "CDC-02": 0.55
        }
    }
}


@router.get("/ribaltamento/chiavi")
async def get_chiavi_ribaltamento() -> Dict[str, Any]:
    """Restituisce le chiavi di ribaltamento configurate."""
    return {
        "chiavi": CHIAVI_RIBALTAMENTO,
        "centri_supporto": [k for k in CHIAVI_RIBALTAMENTO.keys()],
        "centri_operativi": ["CDC-01", "CDC-02"]
    }


@router.post("/ribaltamento/calcola")
async def calcola_ribaltamento(anno: int = Query(...)) -> Dict[str, Any]:
    """
    Calcola il ribaltamento dei costi dai centri di supporto ai centri operativi.
    Questo è il cuore della contabilità analitica TeamSystem.
    """
    db = Database.get_db()
    
    date_start = f"{anno}-01-01"
    date_end = f"{anno}-12-31"
    
    # 1. Recupera i costi per centro di costo
    costi_pipeline = [
        {"$match": {"invoice_date": {"$gte": date_start, "$lte": date_end}}},
        {"$group": {
            "_id": {"$ifNull": ["$centro_costo", "CDC-99"]},
            "totale": {"$sum": "$total_amount"},
            "count": {"$sum": 1}
        }}
    ]
    costi_per_cdc = await db[Collections.INVOICES].aggregate(costi_pipeline).to_list(50)
    costi_dict = {c["_id"]: c["totale"] for c in costi_per_cdc}
    
    # 2. Inizializza i totali per i centri operativi (prima del ribaltamento)
    costi_diretti = {
        "CDC-01": costi_dict.get("CDC-01", 0),
        "CDC-02": costi_dict.get("CDC-02", 0)
    }
    
    # 3. Calcola i ribaltamenti
    ribaltamenti = []
    totale_ribaltato = {"CDC-01": 0, "CDC-02": 0}
    
    for cdc_supporto, config in CHIAVI_RIBALTAMENTO.items():
        costo_supporto = costi_dict.get(cdc_supporto, 0)
        if costo_supporto == 0:
            continue
            
        for cdc_dest, quota in config["criteri"].items():
            importo = costo_supporto * quota
            totale_ribaltato[cdc_dest] = totale_ribaltato.get(cdc_dest, 0) + importo
            
            ribaltamenti.append({
                "da_cdc": cdc_supporto,
                "da_cdc_nome": CDC_STANDARD.get(cdc_supporto, {}).get("nome", cdc_supporto),
                "a_cdc": cdc_dest,
                "a_cdc_nome": CDC_STANDARD.get(cdc_dest, {}).get("nome", cdc_dest),
                "quota_percentuale": quota * 100,
                "importo_origine": round(costo_supporto, 2),
                "importo_ribaltato": round(importo, 2)
            })
    
    # 4. Calcola i costi pieni (diretti + ribaltati)
    costi_pieni = {
        "CDC-01": costi_diretti["CDC-01"] + totale_ribaltato.get("CDC-01", 0),
        "CDC-02": costi_diretti["CDC-02"] + totale_ribaltato.get("CDC-02", 0)
    }
    
    # 5. Recupera i ricavi per calcolare il margine
    ricavi_result = await db[Collections.CORRISPETTIVI].aggregate([
        {"$match": {"data": {"$gte": date_start, "$lte": date_end}}},
        {"$group": {"_id": None, "totale": {"$sum": "$totale"}}}
    ]).to_list(1)
    ricavi_totali = ricavi_result[0]["totale"] if ricavi_result else 0
    
    # Stima ricavi per CDC (da implementare con dati reali)
    ricavi_cdc = {
        "CDC-01": ricavi_totali * 0.40,  # 40% Bar
        "CDC-02": ricavi_totali * 0.60   # 60% Pasticceria
    }
    
    # 6. Calcola margini
    margini = {}
    for cdc in ["CDC-01", "CDC-02"]:
        margini[cdc] = {
            "cdc": cdc,
            "nome": CDC_STANDARD.get(cdc, {}).get("nome", cdc),
            "ricavi": round(ricavi_cdc[cdc], 2),
            "costi_diretti": round(costi_diretti[cdc], 2),
            "costi_ribaltati": round(totale_ribaltato.get(cdc, 0), 2),
            "costi_pieni": round(costi_pieni[cdc], 2),
            "margine_diretto": round(ricavi_cdc[cdc] - costi_diretti[cdc], 2),
            "margine_pieno": round(ricavi_cdc[cdc] - costi_pieni[cdc], 2),
            "margine_percentuale": round((ricavi_cdc[cdc] - costi_pieni[cdc]) / ricavi_cdc[cdc] * 100, 1) if ricavi_cdc[cdc] > 0 else 0
        }
    
    return {
        "anno": anno,
        "ribaltamenti": ribaltamenti,
        "totali_ribaltati": {k: round(v, 2) for k, v in totale_ribaltato.items()},
        "margini_per_cdc": list(margini.values()),
        "sintesi": {
            "ricavi_totali": round(ricavi_totali, 2),
            "costi_diretti_totali": round(sum(costi_diretti.values()), 2),
            "costi_ribaltati_totali": round(sum(totale_ribaltato.values()), 2),
            "margine_aziendale": round(ricavi_totali - sum(costi_pieni.values()), 2)
        }
    }


@router.post("/ribaltamento/aggiorna-chiavi")
async def aggiorna_chiavi_ribaltamento(chiavi: Dict[str, Any] = Body(...)) -> Dict[str, str]:
    """
    Aggiorna le chiavi di ribaltamento.
    Le chiavi vengono salvate nel database per persistenza.
    """
    db = Database.get_db()
    
    await db["config_ribaltamento"].update_one(
        {"_id": "chiavi_ribaltamento"},
        {"$set": {"chiavi": chiavi, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    
    return {"message": "Chiavi di ribaltamento aggiornate"}
