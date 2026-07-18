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
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import logging
import uuid

from app.database import Database
from app.utils.error_handler import handle_errors
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pos-corrispettivi", tags=["POS Corrispettivi Check"])

# Collection per chiusure POS manuali (da registratore di cassa)
COLLECTION_CHIUSURE_POS = "chiusure_pos_manuali"

# La descrizione degli accrediti NUMIA/BPM contiene il giorno di VENDITA:
# "INC.POS CARTE CREDIT - NUMIA-INTER DEL 02/04/26 PDV ..." → 2026-04-02
import re as _re
from app.services.scritture_contabili import scrivi_movimento
_GIORNO_POS_RE = _re.compile(r"DEL\s+(\d{2})/(\d{2})/(\d{2})\b")


def _giorno_operazione_pos(descrizione: str, data_accredito: str) -> str:
    m = _GIORNO_POS_RE.search(descrizione or "")
    if m:
        g, mese, anno = m.groups()
        return f"20{anno}-{mese}-{g}"
    return (data_accredito or "")[:10]


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
    #
    # FIX 2026-04-22: il regex precedente era troppo permissivo e intercettava falsi positivi come
    # "VOSTRA DISPOSIZIONE RIF. MB0B39504178/90144269" (bonifici in uscita) classificati come 
    # "Altre spese - Generico", "Risorse Umane - Salari e stipendi", ecc. semplicemente perché 
    # contenevano "POS" in una sottostringa. Risultato: pos_accreditato gonfiato ~4x, coerenza sballata.
    # Ora uso SOLO le due categorie esatte degli accrediti provider (NUMIA, Nexi, ecc.).
    # NB: escludo anche la categoria "Corrispettivi POS" perché sono chiusure contabili giornaliere 
    # che duplicano il dato pagato_elettronico già nei corrispettivi XML.
    # FIX 18/07/2026: gli accrediti POS reali vivono nell'ESTRATTO CONTO
    # (ora completo, import export banca), non in prima_nota_banca — lì per
    # modello c'è solo la quota "Corrispettivi POS" del registratore, che
    # duplicherebbe l'XML. In più la descrizione NUMIA contiene il GIORNO DI
    # VENDITA ("INC.POS ... NUMIA-INTER DEL 02/04/26"): l'accredito viene
    # attribuito a quel giorno, eliminando lo sfasamento weekend/festivi.
    CATEGORIE_POS_ACCREDITATI = [
        "Ricavi - Incasso tramite POS-Carte di credito",
        "Ricavi - Incasso tramite POS",
        "Incasso POS",
        "Accredito POS",
    ]
    data_a_estesa = (datetime.strptime(data_a, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
    accrediti_pos = await db["estratto_conto_movimenti"].find(
        {
            "data": {"$gte": data_da, "$lte": data_a_estesa},
            "tipo": {"$ne": "uscita"},
            "$or": [
                {"categoria": {"$in": CATEGORIE_POS_ACCREDITATI}},
                {"descrizione_originale": {"$regex": "NUMIA|INCAS\\. TRAMITE P\\.O\\.S|INC\\.POS", "$options": "i"}},
            ],
        },
        {"_id": 0, "data": 1, "importo": 1, "descrizione": 1, "descrizione_originale": 1, "categoria": 1}
    ).sort("data", 1).to_list(20000)
    
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
        descr = p.get("descrizione_originale") or p.get("descrizione") or ""
        # giorno di VENDITA dalla descrizione ("... DEL 02/04/26 ...");
        # fallback: data di accredito
        data = _giorno_operazione_pos(descr, p.get("data", ""))
        if not (data_da <= data <= data_a):
            continue  # vendita fuori periodo (es. accredito di fine anno precedente)
        if data not in pos_by_date:
            pos_by_date[data] = {"importo": 0, "movimenti": []}
        pos_by_date[data]["importo"] += abs(float(p.get("importo", 0) or 0))
        pos_by_date[data]["movimenti"].append(descr[:50])
    
    # 4. Calcola coerenza con logica calendario POS
    anomalie = []
    riepilogo_giornaliero = []
    totale_elettronico_xml = 0
    totale_pos_accreditato = 0
    giorni_ok = 0
    giorni_anomalia = 0
    non_battuto_progressivo = 0.0
    
    # Ordina le date
    tutte_le_date = sorted(set(list(corrispettivi_by_date.keys()) + list(pos_by_date.keys())))
    
    for data in tutte_le_date:
        corr = corrispettivi_by_date.get(data, {"totale": 0, "contanti": 0, "elettronico": 0, "non_riscosso": 0, "matricole": set()})
        pos = pos_by_date.get(data, {"importo": 0, "movimenti": []})
        
        elettronico_xml = corr["elettronico"]
        pos_accreditato = pos["importo"]
        pos_manuale = chiusure_by_date.get(data, 0)
        
        # REGOLA CANONICA (18/07/2026): la chiusura manuale serale è il POS
        # REALE; l'XML è il confronto fiscale. Il "non battuto" (reale - XML)
        # è quanto NON è stato battuto sul tasto elettronico del registratore:
        # va evidenziato e recuperato nei giorni successivi (saldo progressivo).
        riferimento_pos = pos_manuale if pos_manuale > 0 else elettronico_xml
        non_battuto = round(pos_manuale - elettronico_xml, 2) if pos_manuale > 0 else 0.0
        
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
        # FIX: datetime.now(timezone.utc) ritorna un datetime aware (con tz),
        # ma dt = datetime.strptime(data, "%Y-%m-%d") è naive (senza tz).
        # Il confronto dt >= oggi genera TypeError "can't compare offset-naive and offset-aware datetimes".
        # Soluzione: uso datetime.now() senza timezone per restare coerenti con dt.
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
        
        non_battuto_progressivo = round(non_battuto_progressivo + non_battuto, 2)
        giorno_info = {
            "data": data,
            "non_battuto": non_battuto,
            "non_battuto_progressivo": non_battuto_progressivo,
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
            "non_battuto_totale": non_battuto_progressivo,
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
        
        # POS BANCARI REALI del mese: stessa fonte e stessa logica della
        # verifica giornaliera (verifica_coerenza_pos_corrispettivi sopra) —
        # ESTRATTO CONTO, non prima_nota_banca. FIX 18/07/2026: questa
        # funzione non era stata migrata insieme alle altre e usava ancora
        # prima_nota_banca con una whitelist categorie senza "Corrispettivi
        # POS" (categoria scritta dal motore unico): il totale POS annuo
        # risultava gonfiato/svuotato in modo incoerente con la vista
        # giornaliera, che invece torna corretta — segnalato dall'utente
        # ("riepilogo mensile non usabile").
        CATEGORIE_POS_ACCREDITATI = [
            "Ricavi - Incasso tramite POS-Carte di credito",
            "Ricavi - Incasso tramite POS",
            "Incasso POS",
            "Accredito POS",
        ]
        pipeline_pos = [
            {"$match": {
                "data": {"$gte": data_da, "$lte": data_a},
                "tipo": {"$ne": "uscita"},
                "$or": [
                    {"categoria": {"$in": CATEGORIE_POS_ACCREDITATI}},
                    {"descrizione_originale": {"$regex": "NUMIA|INCAS\\. TRAMITE P\\.O\\.S|INC\\.POS", "$options": "i"}},
                ],
            }},
            {"$group": {
                "_id": None,
                "totale": {"$sum": {"$abs": "$importo"}},
                "count": {"$sum": 1}
            }}
        ]

        pos_result = await db["estratto_conto_movimenti"].aggregate(pipeline_pos).to_list(1)
        
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
    
    # FIX 18/07/2026: gli accrediti reali stanno nell'ESTRATTO CONTO e la
    # descrizione NUMIA riporta il giorno di VENDITA ("... DEL 02/04/26"):
    # si sommano TUTTI gli accrediti di quel giorno di vendita (bancomat,
    # carte, Amex arrivano separati) invece di cercarne uno solo ±5%.
    dt = datetime.strptime(data, "%Y-%m-%d")
    finestra_fine = (dt + timedelta(days=7)).strftime("%Y-%m-%d")
    candidati = await db["estratto_conto_movimenti"].find({
        "data": {"$gte": data, "$lte": finestra_fine},
        "tipo": {"$ne": "uscita"},
        "$or": [
            {"categoria": {"$regex": "Incasso tramite POS", "$options": "i"}},
            {"descrizione_originale": {"$regex": "NUMIA|INCAS\\. TRAMITE P\\.O\\.S|INC\\.POS", "$options": "i"}},
        ],
    }, {"_id": 0, "data": 1, "importo": 1, "descrizione_originale": 1, "descrizione": 1}).to_list(200)

    dettagli = []
    totale_accreditato = 0.0
    for p in candidati:
        descr = p.get("descrizione_originale") or p.get("descrizione") or ""
        if _giorno_operazione_pos(descr, p.get("data", "")) != data:
            continue
        totale_accreditato += abs(float(p.get("importo") or 0))
        dettagli.append({"data_accredito": p.get("data"), "importo": p.get("importo"),
                         "descrizione": descr[:70]})

    tolleranza = max(elettronico * 0.02, 5)
    if dettagli and abs(totale_accreditato - elettronico) <= tolleranza:
        await db["corrispettivi"].update_one(
            {"data": data},
            {"$set": {
                "pos_riconciliato": True,
                "pos_data_accredito": dettagli[0]["data_accredito"],
                "pos_importo_accredito": round(totale_accreditato, 2)
            }}
        )
        return {
            "success": True,
            "message": f"POS riconciliato: €{elettronico:.2f} → accreditati €{totale_accreditato:.2f} in {len(dettagli)} movimenti",
            "accrediti": dettagli
        }

    if dettagli:
        return {
            "success": False,
            "message": (f"Accrediti del giorno di vendita {data}: €{totale_accreditato:.2f} "
                        f"su €{elettronico:.2f} attesi (differenza €{abs(totale_accreditato - elettronico):.2f})"),
            "accrediti": dettagli,
            "importo_atteso": elettronico
        }
    return {
        "success": False,
        "message": f"Nessun accredito in estratto conto per il giorno di vendita {data}",
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


@router.put("/chiusura-giornaliera")
@handle_errors
async def upsert_chiusura_giornaliera(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Crea o aggiorna la chiusura POS giornaliera in prima_nota_banca.
    
    Body:
      - data: "YYYY-MM-DD" (obbligatorio)
      - importo: float >= 0 (obbligatorio)
      - note: str (opzionale) — annotazione libera
    
    Comportamento:
      - Cerca in prima_nota_banca un movimento con la stessa data + source='corrispettivo_pos' 
        o categoria='Corrispettivi POS'
      - Se ESISTE: aggiorna importo/amount, aggiunge audit fields (importo_originale, modificato_*)
      - Se NON ESISTE: crea nuovo movimento con source='chiusura_pos_mobile'
    
    Scrive un audit log in 'pos_chiusure_audit' con chi/quando/cosa ha modificato.
    """
    # Validazione input
    data_str = payload.get("data")
    importo_raw = payload.get("importo")
    note = payload.get("note", "") or ""
    
    if not data_str:
        raise HTTPException(status_code=400, detail="Campo 'data' obbligatorio (formato YYYY-MM-DD)")
    try:
        data_dt = datetime.strptime(data_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Data non valida: {data_str!r}. Usa YYYY-MM-DD")
    
    if importo_raw is None:
        raise HTTPException(status_code=400, detail="Campo 'importo' obbligatorio")
    try:
        importo = round(float(importo_raw), 2)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Importo non numerico: {importo_raw!r}")
    if importo < 0:
        raise HTTPException(status_code=400, detail="L'importo non può essere negativo")
    
    db = Database.get_db()
    user_id = current_user.get("sub") or current_user.get("user_id") or "unknown"
    user_email = current_user.get("email") or ""
    user_name = current_user.get("name") or user_email or user_id
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()
    
    # Cerca movimento esistente per quel giorno
    existing = await db["prima_nota_banca"].find_one({
        "data": data_str,
        "$or": [
            {"source": "corrispettivo_pos"},
            {"source": "chiusura_pos_mobile"},
            {"categoria": "Corrispettivi POS"}
        ]
    })
    
    action = ""
    movimento_id = None
    importo_precedente = None
    
    if existing:
        # AGGIORNA
        movimento_id = existing.get("id")
        importo_precedente = float(existing.get("importo") or existing.get("amount") or 0)
        
        # Se l'importo è identico non fare nulla (idempotenza)
        if abs(importo_precedente - importo) < 0.01:
            action = "noop"
        else:
            update_fields = {
                "importo": importo,
                "amount": importo,
                "modificato_da_mobile": True,
                "modificato_il": now_iso,
                "modificato_da_user_id": user_id,
                "modificato_da_email": user_email,
                "modificato_da_name": user_name,
                "updated_at": now_iso
            }
            # Traccia importo originale solo la prima volta che si modifica
            if "importo_originale" not in existing:
                update_fields["importo_originale"] = importo_precedente
            if note:
                update_fields["note_modifica"] = note
            
            await db["prima_nota_banca"].update_one(
                {"id": movimento_id},
                {"$set": update_fields}
            )
            action = "updated"
    else:
        # CREA nuovo movimento
        movimento_id = str(uuid.uuid4())
        nuovo_mov = {
            "id": movimento_id,
            "data": data_str,
            "date": data_str,
            "tipo": "entrata",
            "type": "entrata",
            "importo": importo,
            "amount": importo,
            "descrizione": f"POS corrispettivo {data_str} (chiusura da mobile)",
            "description": f"POS corrispettivo {data_str} (chiusura da mobile)",
            "categoria": "Corrispettivi POS",
            "category": "Corrispettivi POS",
            "source": "chiusura_pos_mobile",
            "anno": data_dt.year,
            "mese": data_dt.month,
            "riconciliato": False,
            "created_at": now_iso,
            "updated_at": now_iso,
            "creato_da_mobile": True,
            "creato_da_user_id": user_id,
            "creato_da_email": user_email,
            "creato_da_name": user_name,
        }
        if note:
            nuovo_mov["note_modifica"] = note
        
        await scrivi_movimento(db, "banca", nuovo_mov)
        action = "created"
        importo_precedente = 0.0
    
    # Audit log (solo se c'è stata una modifica reale)
    if action != "noop":
        audit_entry = {
            "id": str(uuid.uuid4()),
            "collection_target": "prima_nota_banca",
            "movimento_id": movimento_id,
            "data_riferimento": data_str,
            "action": action,  # 'created' | 'updated'
            "importo_precedente": round(importo_precedente or 0, 2),
            "importo_nuovo": importo,
            "delta": round(importo - (importo_precedente or 0), 2),
            "user_id": user_id,
            "user_email": user_email,
            "user_name": user_name,
            "note": note,
            "origine": "mobile_app",
            "timestamp": now_iso,
            "timestamp_epoch": int(now_utc.timestamp())
        }
        try:
            await db["pos_chiusure_audit"].insert_one(audit_entry)
        except Exception as e:
            logger.warning(f"Audit log pos_chiusure_audit fallito: {e}")
    
    return {
        "success": True,
        "action": action,
        "data": data_str,
        "importo": importo,
        "importo_precedente": round(importo_precedente or 0, 2),
        "movimento_id": movimento_id,
        "message": {
            "created": f"Chiusura POS creata per il {data_str}: €{importo:.2f}",
            "updated": f"Chiusura POS del {data_str} aggiornata: €{importo_precedente:.2f} → €{importo:.2f}",
            "noop": f"Chiusura POS del {data_str} già a €{importo:.2f}, nessuna modifica"
        }.get(action, "OK")
    }


@router.get("/chiusura-giornaliera/audit")
@handle_errors
async def list_chiusure_audit(
    anno: Optional[int] = Query(None, description="Filtro per anno"),
    data: Optional[str] = Query(None, description="Filtro per data YYYY-MM-DD"),
    limit: int = Query(100, description="Max risultati", le=500),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Restituisce l'audit log delle modifiche alle chiusure POS giornaliere.
    """
    db = Database.get_db()
    query: Dict[str, Any] = {}
    if data:
        query["data_riferimento"] = data
    elif anno:
        query["data_riferimento"] = {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}
    
    cursor = db["pos_chiusure_audit"].find(query, {"_id": 0}).sort("timestamp_epoch", -1).limit(limit)
    items = await cursor.to_list(limit)
    
    return {
        "count": len(items),
        "items": items
    }


# ═══════════════════════════════════════════════════════════════════════════
# CONTROLLO INCASSI A 2 FASI (v2 - aprile 2026)
# ═══════════════════════════════════════════════════════════════════════════
# Basato sulla specifica utente (spiegazione_coerenza.xlsx):
#
# FASE 1 - Controllo serale: RT XML vs POS manuale
#   diff_serale = pos_manuale_serale - pagato_elettronico_xml
#   Serve a rilevare ERRORI DI BATTITURA al registratore di cassa.
#   Se diff > 0: ieri ho battuto MENO elettronico al RT del reale → compensa +
#   Se diff < 0: ieri ho battuto PIÙ elettronico al RT del reale → compensa -
#
# FASE 2 - Controllo accrediti: POS manuale vs banca
#   diff_accredito = accredito_banca - pos_manuale_serale
#   Il POS manuale è la VERITÀ, la banca deve accreditare quell'importo.
#   Considera calendario bancario: lun-gio → +1gg, ven-sab-dom → lun successivo.
#
# Questo modulo SOSTITUISCE logicamente verifica_coerenza_pos_corrispettivi
# (che confrontava XML direttamente con banca, approccio sbagliato).
# L'endpoint vecchio è mantenuto per retrocompatibilità ma marcato deprecated.
# ═══════════════════════════════════════════════════════════════════════════


def _data_accredito_attesa(data_incasso_str: str) -> str:
    """Dato il giorno di incasso POS, ritorna il giorno atteso di accredito banca.

    Delega al calendario unico del gestionale (app/utils/pos_accredito.py):
    lun-gio → +1 lavorativo; ven → lunedì; sab/dom → lunedì o martedì secondo
    contratto (POS_ACCREDITO_WEEKEND); slittamento automatico sui festivi
    nazionali. Prima questa funzione aveva una copia locale della regola
    SENZA festivi: un accredito posticipato da una festività infrasettimanale
    generava un falso "mancante".
    """
    from app.utils.pos_accredito import data_accredito_prevista_str
    prevista = data_accredito_prevista_str(data_incasso_str)
    return prevista if prevista else data_incasso_str


async def _carica_pos_manuale_per_data(db) -> Dict[str, float]:
    """Carica il POS serale manuale per ogni data, unendo le due fonti:
      - chiusure_pos_manuali (import CSV storico)
      - prima_nota_banca con source='chiusura_pos_mobile' (inserimento da UI)

    Se una data è in entrambe, vince prima_nota_banca (è più recente e aggiornabile
    dall'utente). Ritorna un dizionario {data: importo}.
    """
    out: Dict[str, float] = {}

    # Fonte 1: chiusure_pos_manuali (import CSV)
    async for c in db["chiusure_pos_manuali"].find({}, {"_id": 0, "data": 1, "importo": 1, "totale": 1}):
        d = c.get("data")
        if not d:
            continue
        if isinstance(d, datetime):
            d = d.strftime("%Y-%m-%d")
        imp = float(c.get("importo") or c.get("totale") or 0)
        if d and imp:
            out[d[:10]] = imp

    # Fonte 2: prima_nota_banca con source chiusura_pos_mobile (sovrascrive)
    async for c in db["prima_nota_banca"].find(
        {"source": {"$in": ["chiusura_pos_mobile", "corrispettivo_pos"]}},
        {"_id": 0, "data": 1, "importo": 1, "amount": 1}
    ):
        d = c.get("data")
        if not d:
            continue
        if isinstance(d, datetime):
            d = d.strftime("%Y-%m-%d")
        imp = float(c.get("importo") or c.get("amount") or 0)
        if d and imp:
            out[d[:10]] = imp  # sovrascrive l'import CSV

    return out


async def _carica_accrediti_banca_pos(db, data_da: str, data_a: str) -> Dict[str, float]:
    """Carica gli accrediti POS in banca dall'estratto conto.

    Sono i movimenti in ENTRATA di prima_nota_banca che sono accrediti del
    provider POS (non chiusure manuali, non altri movimenti).

    Fonte reale degli accrediti Ceraldi: NUMIA (unico provider POS attivo;
    SumUp/Satispay NON sono usati — comparivano solo in una vecchia logica).
    Prima questo caricatore cercava solo POS/MONETICA/NEXI/PAGOBANCOMAT e non
    "NUMIA", e filtrava sul campo esatto tipo="entrata": così NON riconosceva
    gli accrediti NUMIA dell'estratto conto e la FASE 2 li segnava tutti come
    "mancanti" (falso disavanzo di ~126k su 41 giorni, 12/07/2026).

    Correzioni:
      1) aggiunta la keyword "NUMIA" (provider reale degli accrediti);
      2) entrate identificate per importo>0 (come gli altri loader del file),
         non per il campo "tipo" che alcune fonti non valorizzano.
    Restano le keyword generiche storiche per retrocompatibilità con eventuali
    diciture bancarie diverse; l'esclusione delle chiusure manuali evita di
    ricontare i POS interni come accrediti (bug falsi positivi del 22/04/2026).
    """
    out: Dict[str, float] = {}

    keywords_pos = [
        "NUMIA", "POS ", "MONETICA", "MULTIBANCA POS", "NEXI", "PAGOBANCOMAT",
        "INCASSO POS", "ACCREDITO POS", "BANCOMAT"
    ]

    # Regex OR su tutte le keyword
    regex_or = "|".join(keywords_pos)

    query = {
        "data": {"$gte": data_da, "$lte": data_a},
        # Entrate: importo positivo (robusto — non dipende dal campo "tipo",
        # che non tutte le fonti di prima_nota_banca valorizzano)
        "importo": {"$gt": 0},
        # Escludi le chiusure manuali (non sono accrediti bancari reali)
        "source": {"$nin": ["chiusura_pos_mobile", "corrispettivo_pos", "manuale_da_xml"]},
        "$or": [
            {"descrizione": {"$regex": regex_or, "$options": "i"}},
            {"categoria": {"$regex": "pos|monetica|numia", "$options": "i"}},
        ],
    }

    async for m in db["prima_nota_banca"].find(query, {"_id": 0, "data": 1, "importo": 1, "amount": 1}):
        d = m.get("data")
        if isinstance(d, datetime):
            d = d.strftime("%Y-%m-%d")
        if not d:
            continue
        imp = float(m.get("importo") or m.get("amount") or 0)
        d = d[:10]
        # Accumula (se più di un accredito nella stessa giornata)
        out[d] = out.get(d, 0.0) + imp

    return out


@router.get("/controllo-due-fasi")
@handle_errors
async def controllo_incassi_due_fasi(
    data_da: Optional[str] = Query(None, description="Data inizio YYYY-MM-DD"),
    data_a: Optional[str] = Query(None, description="Data fine YYYY-MM-DD"),
    anno: Optional[int] = Query(None, description="Anno di riferimento (alternativa a da/a)"),
    tolleranza_euro: float = Query(0.5, description="Tolleranza per considerare 'ok' una differenza"),
) -> Dict[str, Any]:
    """Controllo incassi giornaliero a 2 fasi (nuova logica v2 - aprile 2026).

    FASE 1: Rileva errori di battitura al registratore fiscale
      - Confronto: POS serale manuale − pagato_elettronico XML
      - Alert al giorno successivo con importo da compensare

    FASE 2: Verifica accrediti bancari
      - Confronto: accredito banca − POS serale manuale
      - Tiene conto del calendario bancario (ven-dom → lun)

    Ritorna giorno per giorno lo stato delle due fasi con alert attivi.
    """
    db = Database.get_db()

    if not anno and not data_da:
        anno = datetime.now().year
    if anno:
        data_da = f"{anno}-01-01"
        data_a = f"{anno}-12-31"
    elif not data_a:
        data_a = datetime.now().strftime("%Y-%m-%d")

    # Carica tutti i dati
    corrispettivi = await db["corrispettivi"].find(
        {"data": {"$gte": data_da, "$lte": data_a}},
        {
            "_id": 0, "data": 1,
            "pagato_elettronico": 1, "pagato_contanti": 1, "totale": 1,
            # v2: stato del corrispettivo + dati provvisori/ufficiali
            "stato": 1, "totale_manuale": 1, "totale_xml": 1,
            "source": 1, "data_inserimento_manuale": 1, "data_import_xml": 1,
        }
    ).sort("data", 1).to_list(10000)

    pos_manuali = await _carica_pos_manuale_per_data(db)
    accrediti = await _carica_accrediti_banca_pos(db, data_da, data_a)

    # Unione di tutte le date che hanno almeno un dato (corrispettivo o chiusura manuale)
    date_note = set()
    for c in corrispettivi:
        d = c.get("data")
        if isinstance(d, datetime):
            d = d.strftime("%Y-%m-%d")
        if d:
            date_note.add(d[:10])
    for d in pos_manuali.keys():
        if data_da <= d <= data_a:
            date_note.add(d)

    # Index corrispettivi per data
    corr_by_date: Dict[str, Dict] = {}
    for c in corrispettivi:
        d = c.get("data")
        if isinstance(d, datetime):
            d = d.strftime("%Y-%m-%d")
        if d:
            corr_by_date[d[:10]] = c

    oggi = datetime.now().strftime("%Y-%m-%d")
    soglia_alert_xml = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    giorni = []
    stats = {
        "tot_giorni": 0,
        # FASE 0 (nuovo in v3): stato corrispettivo
        "fase0_provvisori": 0,
        "fase0_definitivi_xml": 0,
        "fase0_manca_xml": 0,
        # FASE 1: errori di battitura
        "fase1_ok": 0, "fase1_diff_piu": 0, "fase1_diff_meno": 0,
        # FASE 2: accrediti banca
        "fase2_ok": 0, "fase2_attesa": 0, "fase2_mancante": 0, "fase2_diff": 0, "fase2_extra": 0,
        # Importi aggregati
        "importo_tot_da_compensare_piu": 0.0,
        "importo_tot_da_compensare_meno": 0.0,
        "importo_tot_mancante_banca": 0.0,
    }

    # Gli alert di compensazione si attivano il giorno DOPO quello della differenza.
    # Cioè: alert[data=X] = guarda diff_serale del giorno (X-1 lavorativo).
    # Per semplicità d'implementazione, calcolo la diff sul giorno X e marco
    # alert_attivo_il = giorno successivo in formato stringa.

    # ── FASE 2 (v4): raggruppamento per data di accredito ────────────────────
    # Ven/Sab/Dom maturano tutti nello stesso accredito del lunedì: la vecchia
    # logica confrontava il TOTALE del lunedì con OGNI singolo giorno,
    # producendo "EXTRA" fittizi ripetuti (lo stesso accredito contato 3 volte)
    # e falsi "MANCANTE". Ora: somma dei POS che maturano nella stessa data di
    # accredito vs accredito banca di quella data, consumato UNA volta sola.
    gruppi_accr: Dict[str, Dict[str, Any]] = {}
    for d in sorted(date_note):
        pos_v = float(pos_manuali.get(d) or 0)
        if pos_v <= 0:
            continue
        ga = _data_accredito_attesa(d)
        g = gruppi_accr.setdefault(ga, {"giorni": [], "pos_tot": 0.0, "dettaglio": []})
        g["giorni"].append(d)
        g["pos_tot"] += pos_v
        # Dettaglio giorno-per-giorno: quando l'accredito raggruppa più giorni
        # (es. venerdì+sabato+domenica → lunedì), qui teniamo traccia di quanto
        # ha inciso ciascun giorno sul totale, per poterlo mostrare in chiaro
        # invece di un unico importo cumulativo poco leggibile.
        g["dettaglio"].append({"data": d, "pos_manuale": round(pos_v, 2)})

    for ga, g in gruppi_accr.items():
        g["pos_tot"] = round(g["pos_tot"], 2)
        accr = float(accrediti.get(ga) or 0)
        if ga > oggi:
            g.update(stato="in_attesa", accredito=0.0, diff=0.0)
        elif accr == 0:
            g.update(stato="mancante", accredito=0.0, diff=round(-g["pos_tot"], 2))
        else:
            diff = round(accr - g["pos_tot"], 2)
            stato = "ok" if abs(diff) <= tolleranza_euro else ("differenza" if diff < 0 else "extra")
            g.update(stato=stato, accredito=round(accr, 2), diff=diff)

    saldo_progressivo = 0.0
    stats["fase2_pos_totale"] = 0.0
    stats["fase2_accrediti_totale"] = 0.0

    for d in sorted(date_note):
        c_row = corr_by_date.get(d, {})
        xml_el = float(c_row.get("pagato_elettronico") or 0)
        pos_man = float(pos_manuali.get(d) or 0)

        # FASE 0 v3: stato corrispettivo (provvisorio / definitivo_xml / manca_xml)
        stato_corr_raw = c_row.get("stato")
        totale_manuale_corr = c_row.get("totale_manuale")
        totale_xml_corr = c_row.get("totale_xml")
        if not stato_corr_raw:
            # Retrocompat: se non c'è stato esplicito, dedurlo dai campi
            has_xml = bool(c_row.get("pagato_elettronico") is not None or totale_xml_corr)
            is_manual_source = c_row.get("source") in ("manuale_serale", "manuale", "manual_entry")
            if has_xml:
                stato_corr = "definitivo_xml"
            elif is_manual_source:
                stato_corr = "manca_xml" if d < soglia_alert_xml else "provvisorio"
            else:
                stato_corr = "sconosciuto"
        else:
            # Ricalcolo dinamico manca_xml per evitare di dipendere solo dal job
            if stato_corr_raw == "provvisorio" and d < soglia_alert_xml:
                stato_corr = "manca_xml"
            else:
                stato_corr = stato_corr_raw

        if stato_corr == "provvisorio":
            stats["fase0_provvisori"] += 1
        elif stato_corr == "definitivo_xml":
            stats["fase0_definitivi_xml"] += 1
        elif stato_corr == "manca_xml":
            stats["fase0_manca_xml"] += 1

        # FASE 1: solo se abbiamo entrambi i dati, altrimenti non possiamo confrontare
        # Se il corrispettivo è provvisorio/manca_xml, non abbiamo xml_elettronico
        # → stato speciale "in_attesa_xml"
        if stato_corr in ("provvisorio", "manca_xml") and pos_man > 0:
            # Abbiamo il POS serale ma non i dati fiscali → aspettiamo XML
            diff_serale = 0.0
            stato_serale = "in_attesa_xml"
            alert_serale = None
        elif xml_el > 0 or pos_man > 0:
            diff_serale = round(pos_man - xml_el, 2)
            if abs(diff_serale) <= tolleranza_euro:
                stato_serale = "ok"
                alert_serale = None
            elif diff_serale > 0:
                stato_serale = "differenza_in_piu_da_registrare"
                alert_serale = {
                    "attivo": True,
                    "tipo": "registrare_di_piu",
                    "importo": diff_serale,
                    "messaggio": (
                        f"Il {d} hai battuto al registratore €{diff_serale:.2f} in MENO "
                        f"di pagamento elettronico rispetto al POS reale. "
                        f"Devi registrare €{diff_serale:.2f} in PIÙ come elettronico per compensare."
                    ),
                }
                stats["fase1_diff_piu"] += 1
                stats["importo_tot_da_compensare_piu"] += diff_serale
            else:
                stato_serale = "differenza_in_meno_da_registrare"
                alert_serale = {
                    "attivo": True,
                    "tipo": "registrare_di_meno",
                    "importo": abs(diff_serale),
                    "messaggio": (
                        f"Il {d} hai battuto al registratore €{abs(diff_serale):.2f} in PIÙ "
                        f"di pagamento elettronico rispetto al POS reale. "
                        f"Devi registrare €{abs(diff_serale):.2f} in MENO come elettronico per compensare."
                    ),
                }
                stats["fase1_diff_meno"] += 1
                stats["importo_tot_da_compensare_meno"] += abs(diff_serale)
        else:
            diff_serale = 0.0
            stato_serale = "no_dati"
            alert_serale = None

        if stato_serale == "ok":
            stats["fase1_ok"] += 1

        # FASE 2 (v4): confronto a livello di GRUPPO di accredito.
        # Il primo giorno del gruppo ("capogruppo") porta accredito, differenza
        # e saldo progressivo; gli altri giorni dello stesso gruppo sono marcati
        # "raggruppato" (il loro POS è già dentro il totale del capogruppo).
        data_accr_attesa = _data_accredito_attesa(d)
        gruppo = gruppi_accr.get(data_accr_attesa)
        capogruppo = bool(gruppo and pos_man > 0 and gruppo["giorni"][0] == d)
        pos_gruppo = 0.0
        giorni_gruppo = 0

        dettaglio_gruppo = None
        if pos_man <= 0 or not gruppo:
            diff_accr = 0.0
            accredito = 0.0
            stato_accr = "no_pos_manuale"
        elif not capogruppo:
            diff_accr = 0.0
            accredito = 0.0
            stato_accr = "raggruppato"
        else:
            stato_accr = gruppo["stato"]
            diff_accr = gruppo["diff"]
            accredito = gruppo["accredito"]
            pos_gruppo = gruppo["pos_tot"]
            giorni_gruppo = len(gruppo["giorni"])
            # Dettaglio per-giorno SOLO se il gruppo copre più di un giorno
            # (es. weekend): per un giorno singolo sarebbe ridondante col totale.
            if giorni_gruppo > 1:
                dettaglio_gruppo = gruppo["dettaglio"]
            # Statistiche e saldo: una volta per gruppo (solo sul capogruppo)
            if stato_accr == "in_attesa":
                stats["fase2_attesa"] += 1
            elif stato_accr == "mancante":
                stats["fase2_mancante"] += 1
                stats["importo_tot_mancante_banca"] += pos_gruppo
                saldo_progressivo += diff_accr
            elif stato_accr == "ok":
                stats["fase2_ok"] += 1
                saldo_progressivo += diff_accr
            elif stato_accr == "differenza":
                stats["fase2_diff"] += 1
                saldo_progressivo += diff_accr
            else:  # extra
                stats["fase2_extra"] += 1
                saldo_progressivo += diff_accr
            if stato_accr != "in_attesa":
                stats["fase2_pos_totale"] += pos_gruppo
                stats["fase2_accrediti_totale"] += accredito

        giorni.append({
            "data": d,
            # Fase 0 (v3): stato corrispettivo
            "stato_corrispettivo": stato_corr,
            "totale_manuale": totale_manuale_corr,
            "totale_xml": totale_xml_corr,
            # Fase 1
            "xml_elettronico": round(xml_el, 2),
            "pos_manuale": round(pos_man, 2),
            "diff_serale": diff_serale,
            "stato_serale": stato_serale,
            "alert_compensazione": alert_serale,
            # Fase 2 (v4, a gruppi di accredito)
            "data_accredito_attesa": data_accr_attesa,
            "accredito_banca": round(accredito, 2),
            "diff_accredito": diff_accr,
            "stato_accredito": stato_accr,
            "capogruppo": capogruppo,
            "pos_gruppo": round(pos_gruppo, 2),
            "giorni_gruppo": giorni_gruppo,
            "dettaglio_gruppo": dettaglio_gruppo,
            "saldo_progressivo": round(saldo_progressivo, 2) if capogruppo and stato_accr != "in_attesa" else None,
        })
        stats["tot_giorni"] += 1

    # Round stats
    stats["importo_tot_da_compensare_piu"] = round(stats["importo_tot_da_compensare_piu"], 2)
    stats["importo_tot_da_compensare_meno"] = round(stats["importo_tot_da_compensare_meno"], 2)
    stats["importo_tot_mancante_banca"] = round(stats["importo_tot_mancante_banca"], 2)
    stats["fase2_pos_totale"] = round(stats["fase2_pos_totale"], 2)
    stats["fase2_accrediti_totale"] = round(stats["fase2_accrediti_totale"], 2)
    stats["fase2_saldo_finale"] = round(saldo_progressivo, 2)

    # ── Riepilogo settimanale ─────────────────────────────────────────────────
    # Raggruppa per settimana ISO del giorno di INCASSO (non di accredito): la
    # domanda a cui risponde è "quanto abbiamo incassato questa settimana e
    # quanto ce ne ha accreditato la banca", non "quanto è arrivato in banca
    # questa settimana" — un venerdì di fine settimana porta il suo accredito
    # (con sabato/domenica) nel totale della SUA settimana anche se il bonifico
    # arriva materialmente il lunedì successivo (settimana ISO seguente).
    settimane: Dict[str, Dict[str, Any]] = {}
    for g in giorni:
        try:
            dt = datetime.strptime(g["data"], "%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        iso_anno, iso_settimana, _ = dt.isocalendar()
        chiave = f"{iso_anno}-W{iso_settimana:02d}"
        sw = settimane.setdefault(chiave, {
            "settimana": chiave,
            "data_inizio": None,
            "data_fine": None,
            "pos_totale": 0.0,
            "accredito_totale": 0.0,
            "num_giorni_con_pos": 0,
            "num_giorni_in_attesa": 0,
            "num_giorni_mancanti": 0,
            "num_giorni_differenza": 0,
        })
        if sw["data_inizio"] is None or g["data"] < sw["data_inizio"]:
            sw["data_inizio"] = g["data"]
        if sw["data_fine"] is None or g["data"] > sw["data_fine"]:
            sw["data_fine"] = g["data"]
        if g["pos_manuale"] > 0:
            sw["pos_totale"] += g["pos_manuale"]
            sw["num_giorni_con_pos"] += 1
        # L'accredito/diff sono già "una volta per gruppo" (solo sul capogruppo,
        # gli altri giorni del gruppo hanno accredito_banca=0), quindi sommarli
        # per ogni giorno della settimana non duplica nulla.
        if g["capogruppo"]:
            sw["accredito_totale"] += g["accredito_banca"]
            if g["stato_accredito"] == "in_attesa":
                sw["num_giorni_in_attesa"] += 1
            elif g["stato_accredito"] == "mancante":
                sw["num_giorni_mancanti"] += 1
            elif g["stato_accredito"] == "differenza":
                sw["num_giorni_differenza"] += 1

    riepilogo_settimanale = []
    for chiave in sorted(settimane.keys()):
        sw = settimane[chiave]
        sw["pos_totale"] = round(sw["pos_totale"], 2)
        sw["accredito_totale"] = round(sw["accredito_totale"], 2)
        sw["diff_totale"] = round(sw["accredito_totale"] - sw["pos_totale"], 2)
        if sw["num_giorni_in_attesa"] > 0:
            sw["stato"] = "in_attesa"
        elif sw["num_giorni_mancanti"] > 0:
            sw["stato"] = "mancante"
        elif abs(sw["diff_totale"]) > tolleranza_euro:
            sw["stato"] = "differenza"
        else:
            sw["stato"] = "ok"
        riepilogo_settimanale.append(sw)

    return {
        "success": True,
        "data_da": data_da,
        "data_a": data_a,
        "tolleranza_euro": tolleranza_euro,
        "statistiche": stats,
        "giorni": giorni,
        "riepilogo_settimanale": riepilogo_settimanale,
    }


async def _alert_pos_non_quadrato(db, data_incasso: str, dettaglio: str) -> None:
    """Genera l'alert RIC_POS_NON_QUADRATO quando l'accredito banca di un
    giorno/gruppo POS manca o differisce dall'atteso — definito in
    alert_engine.py ma mai generato (vedi memoria/moduli/RICONCILIAZIONE.md,
    gap #6). Idempotente, best-effort, non tocca il calcolo di
    controllo_incassi_due_fasi."""
    try:
        from app.services.alert_engine import genera_alert
        await genera_alert(
            "RIC_POS_NON_QUADRATO", data_incasso, "pos_corrispettivi_giorno", dettaglio, db,
        )
    except Exception:
        logger.exception(f"Errore generazione alert RIC_POS_NON_QUADRATO per {data_incasso}")


@router.get("/alert-oggi")
@handle_errors
async def alert_oggi(
    tolleranza_euro: float = Query(0.5)
) -> Dict[str, Any]:
    """Alert attivi OGGI per l'utente:
      - Compensazioni da fare al registratore per errori di battitura del giorno precedente
      - Accrediti bancari mancanti dei giorni scorsi

    Usato dalla dashboard / widget per mostrare cosa c'è da sistemare.
    """
    db = Database.get_db()
    oggi = datetime.now()
    # Guarda ultimi 30 giorni per prendere tutti gli alert attivi
    data_da = (oggi - timedelta(days=30)).strftime("%Y-%m-%d")
    data_a = oggi.strftime("%Y-%m-%d")

    # Riusa la logica del controllo completo. IMPORTANTE: passare anno=None
    # esplicitamente — senza, il parametro "anno" di controllo_incassi_due_fasi
    # riceve come default il sentinel Query(None, ...) non risolto (questa è
    # una chiamata Python diretta, non una richiesta HTTP, quindi FastAPI non
    # lo risolve), che è truthy: il ramo "if anno:" sovrascriveva data_da/data_a
    # con stringhe corrotte tipo "<fastapi.params.Query object...>-01-01",
    # rompendo silenziosamente la query Mongo e azzerando SEMPRE gli alert
    # (bug trovato lug 2026, riproducibile in modo deterministico).
    full = await controllo_incassi_due_fasi(data_da=data_da, data_a=data_a, anno=None, tolleranza_euro=tolleranza_euro)

    alerts_compensazione = []
    alerts_banca = []
    alerts_xml_mancante = []

    for g in full.get("giorni", []):
        if g.get("alert_compensazione"):
            alerts_compensazione.append({
                "data_errore": g["data"],
                **g["alert_compensazione"],
            })
        if g.get("stato_accredito") == "mancante":
            msg = (
                f"Accredito POS mancante: il {g['data']} hai incassato €{g['pos_manuale']:.2f} "
                f"ma la banca non l'ha ancora accreditato (atteso il {g['data_accredito_attesa']})."
            )
            alerts_banca.append({
                "data_incasso": g["data"],
                "data_accredito_attesa": g["data_accredito_attesa"],
                "importo_atteso": g["pos_manuale"],
                "messaggio": msg,
            })
            await _alert_pos_non_quadrato(db, g["data"], msg)
        elif g.get("stato_accredito") == "differenza":
            msg = (
                f"Accredito diverso dal previsto: il {g['data']} incasso POS €{g['pos_manuale']:.2f}, "
                f"banca ha accreditato €{g['accredito_banca']:.2f} (differenza €{g['diff_accredito']:.2f})."
            )
            alerts_banca.append({
                "data_incasso": g["data"],
                "data_accredito_attesa": g["data_accredito_attesa"],
                "importo_atteso": g["pos_manuale"],
                "importo_accreditato": g["accredito_banca"],
                "differenza": g["diff_accredito"],
                "messaggio": msg,
            })
            await _alert_pos_non_quadrato(db, g["data"], msg)
        # v3: alert XML mancante (>=7 giorni senza file ufficiale)
        if g.get("stato_corrispettivo") == "manca_xml":
            alerts_xml_mancante.append({
                "data": g["data"],
                "totale_manuale": g.get("totale_manuale") or g.get("pos_manuale") or 0,
                "messaggio": (
                    f"Manca il file XML dei corrispettivi per il {g['data']}. "
                    f"Hai ancora un corrispettivo provvisorio non sostituito da XML ufficiale."
                ),
            })

    return {
        "success": True,
        "oggi": data_a,
        "num_alert_compensazione": len(alerts_compensazione),
        "num_alert_banca": len(alerts_banca),
        "num_alert_xml_mancante": len(alerts_xml_mancante),
        "alert_compensazione": alerts_compensazione,
        "alert_banca": alerts_banca,
        "alert_xml_mancante": alerts_xml_mancante,
    }
