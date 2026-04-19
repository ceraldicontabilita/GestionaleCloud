"""
Router per la verifica della coerenza tra POS e Corrispettivi XML.

IMPORTANTE - DISTINZIONE FONTI DATI:
- "POS BANCA" = Accrediti reali dall'estratto conto bancario (prima_nota_banca)
- "POS CHIUSURE" = Chiusure manuali dal registratore di cassa (chiusure_pos_manuali)
- "CORRISPETTIVI XML" = Dati dal telematico (corrispettivi)

La riconciliazione principale confronta:
- Corrispettivi XML (pagato_elettronico) vs Accrediti POS BANCARI reali

Le chiusure manuali sono un dato di supporto, NON sono movimenti bancari.

Normativa 2026:
- Obbligo di abbinamento RT-POS
- Verifica disallineamenti tra corrispettivi e transazioni POS
- Controllo campi XML (tracciato 7.0+)
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List
from datetime import datetime, timedelta
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pos-corrispettivi", tags=["POS Corrispettivi Check"])

# Collection per chiusure POS manuali (da registratore di cassa)
COLLECTION_CHIUSURE_POS = "chiusure_pos_manuali"


@router.get("/verifica-coerenza")
@handle_errors
async def verifica_coerenza_pos_corrispettivi(
    data_da: str = Query(None, description="Data inizio (YYYY-MM-DD)"),
    data_a: str = Query(None, description="Data fine (YYYY-MM-DD)"),
    anno: int = Query(None, description="Anno di riferimento")
) -> Dict[str, Any]:
    """
    Verifica la coerenza tra pagamenti elettronici (POS) e corrispettivi XML.
    
    Logica:
    - Per ogni giorno, confronta pagato_elettronico (dal corrispettivo XML)
    - con gli accrediti POS effettivi (dalla banca o da import POS)
    - Considera il ritardo di accredito POS (Lun-Gio: +1g, Ven-Dom: somma al Lun)
    
    Returns:
        Dict con anomalie e statistiche
    """
    db = Database.get_db()
    
    # Default: ultimo mese o anno corrente
    if not anno and not data_da:
        anno = datetime.now().year
    
    if anno:
        data_da = f"{anno}-01-01"
        data_a = f"{anno}-12-31"
    elif not data_a:
        data_a = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Carica corrispettivi nel periodo
    corrispettivi = await db["corrispettivi"].find(
        {"data": {"$gte": data_da, "$lte": data_a}},
        {"_id": 0, "data": 1, "totale": 1, "pagato_contanti": 1, "pagato_elettronico": 1, 
         "pagato_non_riscosso": 1, "matricola_rt": 1}
    ).sort("data", 1).to_list(10000)
    
    # 2. Carica accrediti POS BANCARI REALI (SOLO da estratto conto, NON da import manuali!)
    # IMPORTANTE: Escludiamo "source": "import_manuale_pos" perché quelli sono chiusure manuali,
    # NON accrediti bancari reali
    accrediti_pos = await db["prima_nota_banca"].find(
        {
            "data": {"$gte": data_da, "$lte": data_a},
            "importo": {"$gt": 0},  # Solo entrate
            "source": {"$ne": "import_manuale_pos"},  # ESCLUDI import manuali pos.xlsx
            "$or": [
                {"categoria": {"$in": ["POS", "pos", "Incasso POS", "Accredito POS"]}},
                {"descrizione": {"$regex": "POS|NEXI|SUMUP|SUM UP|STRIPE|SATISPAY|MYPOS|INCAS.*P\\.O\\.S|ACCREDITO.*POS|WORLDPAY|NUMIA|PGBNT", "$options": "i"}}
            ]
        },
        {"_id": 0, "data": 1, "importo": 1, "descrizione": 1, "categoria": 1, "source": 1}
    ).sort("data", 1).to_list(10000)
    
    # 3. Carica anche chiusure POS manuali per riferimento (opzionale)
    # Prima prova dalla collection dedicata, se vuota fallback a prima_nota_banca
    chiusure_manuali = await db[COLLECTION_CHIUSURE_POS].find(
        {"data": {"$gte": data_da, "$lte": data_a}},
        {"_id": 0, "data": 1, "importo": 1}
    ).sort("data", 1).to_list(10000)
    
    # Se collection dedicata è vuota, usa prima_nota_banca con source: import_manuale_pos
    if not chiusure_manuali:
        chiusure_manuali = await db["prima_nota_banca"].find(
            {
                "data": {"$gte": data_da, "$lte": data_a},
                "source": "import_manuale_pos"
            },
            {"_id": 0, "data": 1, "importo": 1}
        ).sort("data", 1).to_list(10000)
    
    chiusure_by_date = {}
    totale_chiusure_manuali = 0
    for c in chiusure_manuali:
        data = c.get("data", "")
        importo = float(c.get("importo", 0) or 0)
        chiusure_by_date[data] = chiusure_by_date.get(data, 0) + importo
        totale_chiusure_manuali += importo
    
    # 4. Costruisci dizionario per data
    corrispettivi_by_date = {}
    for c in corrispettivi:
        data = c.get("data", "")
        if data not in corrispettivi_by_date:
            corrispettivi_by_date[data] = {
                "totale": 0,
                "contanti": 0,
                "elettronico": 0,
                "non_riscosso": 0,
                "matricole": set()
            }
        corrispettivi_by_date[data]["totale"] += float(c.get("totale", 0) or 0)
        corrispettivi_by_date[data]["contanti"] += float(c.get("pagato_contanti", 0) or 0)
        corrispettivi_by_date[data]["elettronico"] += float(c.get("pagato_elettronico", 0) or 0)
        corrispettivi_by_date[data]["non_riscosso"] += float(c.get("pagato_non_riscosso", 0) or 0)
        if c.get("matricola_rt"):
            corrispettivi_by_date[data]["matricole"].add(c.get("matricola_rt"))
    
    pos_by_date = {}
    for p in accrediti_pos:
        data = p.get("data", "")
        if data not in pos_by_date:
            pos_by_date[data] = {"importo": 0, "movimenti": []}
        pos_by_date[data]["importo"] += abs(float(p.get("importo", 0) or 0))
        pos_by_date[data]["movimenti"].append(p.get("descrizione", "")[:50])
    
    # 4. Calcola coerenza con logica calendario POS
    anomalie = []
    riepilogo_giornaliero = []
    totale_elettronico_xml = 0
    totale_pos_accreditato = 0
    giorni_ok = 0
    giorni_anomalia = 0
    
    # Ordina le date
    tutte_le_date = sorted(set(list(corrispettivi_by_date.keys()) + list(pos_by_date.keys())))
    
    for data in tutte_le_date:
        corr = corrispettivi_by_date.get(data, {"totale": 0, "contanti": 0, "elettronico": 0, "non_riscosso": 0, "matricole": set()})
        pos = pos_by_date.get(data, {"importo": 0, "movimenti": []})
        
        elettronico_xml = corr["elettronico"]
        pos_accreditato = pos["importo"]
        pos_manuale = chiusure_by_date.get(data, 0)
        
        # Usa POS manuale (chiusure giornaliere) se disponibile, altrimenti XML
        riferimento_pos = pos_manuale if pos_manuale > 0 else elettronico_xml
        
        totale_elettronico_xml += elettronico_xml
        totale_pos_accreditato += pos_accreditato
        
        # Calcola data accredito attesa (logica calendario)
        try:
            dt = datetime.strptime(data, "%Y-%m-%d")
            giorno_settimana = dt.weekday()  # 0=Lun, 6=Dom
            
            # Logica accredito POS
            if giorno_settimana <= 3:  # Lun-Gio -> accredito +1 giorno
                data_accredito_attesa = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
            else:  # Ven-Dom -> accredito Lunedì
                giorni_al_lunedi = 7 - giorno_settimana + 1
                data_accredito_attesa = (dt + timedelta(days=giorni_al_lunedi)).strftime("%Y-%m-%d")
        except Exception:
            data_accredito_attesa = data
            dt = None
        
        # Verifica coerenza con tolleranza
        differenza = abs(riferimento_pos - pos_accreditato)
        tolleranza = max(riferimento_pos * 0.02, 5)  # 2% o €5 min
        
        stato = "ok"
        messaggio = ""
        
        # Nuovo stato: IN_TRANSITO per ultimi 2 giorni
        oggi = datetime.now()
        is_recente = dt and dt >= oggi - timedelta(days=2)
        
        if riferimento_pos > 0 and pos_accreditato == 0:
            if is_recente:
                stato = "in_transito"
                messaggio = f"POS in transito: €{riferimento_pos:.2f} (accredito atteso {data_accredito_attesa})"
            else:
                stato = "mancante"
                messaggio = f"POS non accreditato: attesi €{riferimento_pos:.2f}"
                giorni_anomalia += 1
        elif pos_accreditato > 0 and riferimento_pos == 0:
            stato = "extra"
            messaggio = "POS accreditato ma nessun corrispettivo elettronico"
            giorni_anomalia += 1
        elif differenza > tolleranza:
            stato = "differenza"
            messaggio = f"Differenza €{differenza:.2f} (atteso: €{riferimento_pos:.2f}, accreditato: €{pos_accreditato:.2f})"
            giorni_anomalia += 1
        else:
            giorni_ok += 1
        
        giorno_info = {
            "data": data,
            "giorno_settimana": ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"][dt.weekday()] if 'dt' in dir() else "",
            "totale_corrispettivo": round(corr["totale"], 2),
            "contanti_xml": round(corr["contanti"], 2),
            "elettronico_xml": round(elettronico_xml, 2),
            "non_riscosso": round(corr["non_riscosso"], 2),
            "pos_accreditato": round(pos_accreditato, 2),
            "pos_chiusura_manuale": round(chiusure_by_date.get(data, 0), 2),  # Aggiunto riferimento chiusure manuali
            "differenza": round(differenza, 2),
            "stato": stato,
            "messaggio": messaggio,
            "data_accredito_attesa": data_accredito_attesa
        }
        
        riepilogo_giornaliero.append(giorno_info)
        
        if stato != "ok":
            anomalie.append(giorno_info)
    
    # Converti set matricole in lista per serializzazione
    for data in corrispettivi_by_date:
        corrispettivi_by_date[data]["matricole"] = list(corrispettivi_by_date[data]["matricole"])
    
    differenza_totale = totale_elettronico_xml - totale_pos_accreditato
    
    return {
        "periodo": {"da": data_da, "a": data_a},
        "riepilogo": {
            "totale_elettronico_xml": round(totale_elettronico_xml, 2),
            "totale_pos_accreditato": round(totale_pos_accreditato, 2),
            "totale_chiusure_manuali": round(totale_chiusure_manuali, 2),  # Chiusure da registratore (pos.xlsx)
            "differenza_totale": round(differenza_totale, 2),
            "giorni_analizzati": len(tutte_le_date),
            "giorni_ok": giorni_ok,
            "giorni_anomalia": giorni_anomalia,
            "percentuale_coerenza": round((giorni_ok / max(len(tutte_le_date), 1)) * 100, 1)
        },
        "anomalie": anomalie[:100],  # Limita a 100
        "anomalie_count": len(anomalie),
        "riepilogo_giornaliero": riepilogo_giornaliero[-60:],  # Ultimi 60 giorni
        "note": "Logica accredito POS: Lun-Gio +1g, Ven-Dom -> Lunedì"
    }


@router.get("/riepilogo-mensile")
@handle_errors
async def riepilogo_mensile_pos_corrispettivi(
    anno: int = Query(..., description="Anno di riferimento")
) -> Dict[str, Any]:
    """
    Riepilogo mensile della coerenza POS/Corrispettivi per un anno.
    """
    db = Database.get_db()
    
    mesi = []
    totale_anno_elettronico = 0
    totale_anno_pos = 0
    
    for mese in range(1, 13):
        data_da = f"{anno}-{mese:02d}-01"
        if mese == 12:
            data_a = f"{anno}-12-31"
        else:
            data_a = f"{anno}-{mese+1:02d}-01"
            # Sottrai un giorno per avere l'ultimo del mese
            dt_fine = datetime.strptime(data_a, "%Y-%m-%d") - timedelta(days=1)
            data_a = dt_fine.strftime("%Y-%m-%d")
        
        # Corrispettivi del mese
        pipeline_corr = [
            {"$match": {"data": {"$gte": data_da, "$lte": data_a}}},
            {"$group": {
                "_id": None,
                "totale": {"$sum": "$totale"},
                "contanti": {"$sum": "$pagato_contanti"},
                "elettronico": {"$sum": "$pagato_elettronico"},
                "count": {"$sum": 1}
            }}
        ]
        
        corr_result = await db["corrispettivi"].aggregate(pipeline_corr).to_list(1)
        
        # POS BANCARI REALI del mese (ESCLUDI import manuali pos.xlsx!)
        pipeline_pos = [
            {"$match": {
                "data": {"$gte": data_da, "$lte": data_a},
                "importo": {"$gt": 0},  # Solo entrate
                "source": {"$ne": "import_manuale_pos"},  # ESCLUDI chiusure manuali
                "$or": [
                    {"categoria": {"$in": ["POS", "pos", "Incasso POS", "Accredito POS"]}},
                    {"descrizione": {"$regex": "POS|NEXI|SUMUP|INCAS.*P\\.O\\.S|ACCREDITO.*POS|NUMIA|PGBNT", "$options": "i"}}
                ]
            }},
            {"$group": {
                "_id": None,
                "totale": {"$sum": "$importo"},
                "count": {"$sum": 1}
            }}
        ]
        
        pos_result = await db["prima_nota_banca"].aggregate(pipeline_pos).to_list(1)
        
        elettronico = corr_result[0]["elettronico"] if corr_result else 0
        pos = pos_result[0]["totale"] if pos_result else 0
        differenza = elettronico - pos
        
        totale_anno_elettronico += elettronico
        totale_anno_pos += pos
        
        nome_mese = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", 
                     "Lug", "Ago", "Set", "Ott", "Nov", "Dic"][mese-1]
        
        mesi.append({
            "mese": mese,
            "nome": nome_mese,
            "totale_corrispettivi": round(corr_result[0]["totale"] if corr_result else 0, 2),
            "contanti": round(corr_result[0]["contanti"] if corr_result else 0, 2),
            "elettronico_xml": round(elettronico, 2),
            "pos_accreditato": round(pos, 2),
            "differenza": round(differenza, 2),
            "stato": "ok" if abs(differenza) < 50 else ("warning" if abs(differenza) < 200 else "error"),
            "corrispettivi_count": corr_result[0]["count"] if corr_result else 0,
            "pos_count": pos_result[0]["count"] if pos_result else 0
        })
    
    return {
        "anno": anno,
        "mesi": mesi,
        "totali": {
            "elettronico_xml": round(totale_anno_elettronico, 2),
            "pos_accreditato": round(totale_anno_pos, 2),
            "differenza": round(totale_anno_elettronico - totale_anno_pos, 2)
        }
    }


@router.post("/riconcilia-pos-giorno")
@handle_errors
async def riconcilia_pos_giorno(
    data: str = Query(..., description="Data da riconciliare (YYYY-MM-DD)")
) -> Dict[str, Any]:
    """
    Tenta la riconciliazione automatica POS per un giorno specifico.
    
    Cerca accrediti POS nei giorni successivi secondo la logica calendario.
    """
    db = Database.get_db()
    
    # Corrispettivo del giorno
    corr = await db["corrispettivi"].find_one(
        {"data": data},
        {"_id": 0}
    )
    
    if not corr:
        return {"success": False, "message": "Nessun corrispettivo per questa data"}
    
    elettronico = float(corr.get("pagato_elettronico", 0) or 0)
    if elettronico <= 0:
        return {"success": False, "message": "Nessun pagamento elettronico per questa data"}
    
    # Calcola date possibili di accredito
    dt = datetime.strptime(data, "%Y-%m-%d")
    giorno_settimana = dt.weekday()
    
    date_possibili = []
    if giorno_settimana <= 3:  # Lun-Gio
        date_possibili.append((dt + timedelta(days=1)).strftime("%Y-%m-%d"))
        date_possibili.append((dt + timedelta(days=2)).strftime("%Y-%m-%d"))
    else:  # Ven-Dom
        giorni_al_lunedi = 7 - giorno_settimana + 1
        date_possibili.append((dt + timedelta(days=giorni_al_lunedi)).strftime("%Y-%m-%d"))
        date_possibili.append((dt + timedelta(days=giorni_al_lunedi + 1)).strftime("%Y-%m-%d"))
    
    # Cerca accredito POS BANCARIO REALE nelle date possibili (NO import manuali!)
    accredito_trovato = None
    for data_accredito in date_possibili:
        pos = await db["prima_nota_banca"].find_one({
            "data": data_accredito,
            "source": {"$ne": "import_manuale_pos"},  # Escludi chiusure manuali
            "$or": [
                {"categoria": {"$in": ["POS", "pos", "Incasso POS"]}},
                {"descrizione": {"$regex": "POS|NEXI|SUMUP", "$options": "i"}}
            ],
            "importo": {"$gte": elettronico * 0.95, "$lte": elettronico * 1.05}
        }, {"_id": 0})
        
        if pos:
            accredito_trovato = {
                "data_accredito": data_accredito,
                "importo": pos.get("importo"),
                "descrizione": pos.get("descrizione")
            }
            break
    
    if accredito_trovato:
        # Aggiorna corrispettivo con riferimento
        await db["corrispettivi"].update_one(
            {"data": data},
            {"$set": {
                "pos_riconciliato": True,
                "pos_data_accredito": accredito_trovato["data_accredito"],
                "pos_importo_accredito": accredito_trovato["importo"]
            }}
        )
        
        return {
            "success": True,
            "message": f"POS riconciliato: €{elettronico:.2f} accreditato il {accredito_trovato['data_accredito']}",
            "accredito": accredito_trovato
        }
    
    return {
        "success": False,
        "message": f"Accredito POS non trovato. Cercato in: {', '.join(date_possibili)}",
        "date_cercate": date_possibili,
        "importo_atteso": elettronico
    }


@router.get("/anomalie-gravi")
@handle_errors
async def get_anomalie_gravi(
    anno: int = Query(..., description="Anno di riferimento"),
    soglia: float = Query(100, description="Soglia minima differenza (€)")
) -> Dict[str, Any]:
    """
    Restituisce solo le anomalie gravi che potrebbero generare 
    avvisi dall'Agenzia delle Entrate.
    """
    result = await verifica_coerenza_pos_corrispettivi(anno=anno)
    
    anomalie_gravi = [
        a for a in result.get("anomalie", [])
        if a.get("differenza", 0) >= soglia
    ]
    
    return {
        "anno": anno,
        "soglia_euro": soglia,
        "anomalie_gravi": anomalie_gravi,
        "count": len(anomalie_gravi),
        "totale_differenza": round(sum(a.get("differenza", 0) for a in anomalie_gravi), 2),
        "warning": "Queste anomalie potrebbero generare avvisi dall'Agenzia delle Entrate" if anomalie_gravi else None
    }
