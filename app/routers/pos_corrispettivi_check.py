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
import asyncio
import logging
import re

from app.database import Database
from app.utils.error_handler import handle_errors
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pos-corrispettivi", tags=["POS Corrispettivi Check"])

# Collection per chiusure POS manuali (da registratore di cassa)
COLLECTION_CHIUSURE_POS = "chiusure_pos_manuali"

# La descrizione degli accrediti NUMIA/BPM contiene il giorno di VENDITA:
# "INC.POS CARTE CREDIT - NUMIA-INTER DEL 02/04/26 PDV ..." → 2026-04-02
from app.services.scritture_contabili import (
    GESTORE_POS_DEFAULT,
    ScritturaNonValida,
    registra_chiusura_pos_reale,
)
from app.services.pos_evidence import (
    _e_accredito_pos_numia_con_giorno,
    _giorno_operazione_pos,
)


def _coerenza_xml_pos(
    pagamento_elettronico_xml: float,
    pos_reale: float,
    tolleranza_euro: float,
) -> tuple[float, bool]:
    """Ritorna ``XML - POS`` e se l'XML copre il pagamento reale.

    Il confronto e' volutamente asimmetrico: un XML superiore al POS e'
    coerente, mentre un XML inferiore oltre tolleranza segnala pagamenti carta
    non coperti dal pagamento elettronico dichiarato negli scontrini.
    """
    differenza = round(float(pagamento_elettronico_xml) - float(pos_reale), 2)
    return differenza, differenza >= -abs(float(tolleranza_euro))


def _importo_elettronico_xml(corrispettivo: Dict[str, Any]) -> float:
    """Legge la quota elettronica sia dal modello canonico sia da quello Drive storico.

    Il vecchio ``CorrispettiviService`` usato dallo scheduler Drive salvava
    ``pagato_pos``. Gli upload diretti salvano invece ``pagato_elettronico``.
    La pagina Coerenza POS deve leggere entrambi senza migrare o inventare dati.
    """
    valore = corrispettivo.get("pagato_elettronico")
    if valore is None:
        valore = corrispettivo.get("pagato_pos")
    try:
        return float(valore or 0)
    except (TypeError, ValueError):
        return 0.0


def _e_corrispettivo_xml(corrispettivo: Dict[str, Any]) -> bool:
    """Riconosce gli XML canonici e gli XML Drive importati prima dell'unificazione."""
    if corrispettivo.get("stato") == "definitivo_xml":
        return True
    if corrispettivo.get("data_import_xml") or corrispettivo.get("totale_xml") is not None:
        return True
    source = str(corrispettivo.get("source") or "").strip().lower()
    if source in {
        "xml", "xml_import", "corrispettivo_import", "corrispettivo_xml",
        "sincronizzazione", "corrispettivi_sync", "zip_upload",
    }:
        return True
    filename = str(corrispettivo.get("filename") or "").strip().lower()
    return bool(corrispettivo.get("content_hash") and filename.endswith(".xml"))


def _id_movimento_pos(movimento: Dict[str, Any]) -> str:
    return str(movimento.get("id") or movimento.get("_id") or "")


def _chiave_evidenza_pos_banca(movimento: Dict[str, Any]) -> tuple:
    """Identifica una singola liquidazione POS gia registrata dalla banca.

    NUMIA produce al massimo una liquidazione per circuito, terminale e giorno
    vendita. La stessa riga puo pero essere importata piu volte da estratti
    sovrapposti. Data contabile, giorno vendita, centesimi, causale e rapporto
    permettono di unificare soltanto quelle copie, senza fondere circuiti o
    accrediti realmente distinti.
    """
    descrizione = str(
        movimento.get("descrizione_originale") or movimento.get("descrizione") or ""
    )
    try:
        centesimi = int(round(abs(float(
            movimento.get("importo") or movimento.get("amount") or 0
        )) * 100))
    except (TypeError, ValueError):
        centesimi = 0
    return (
        str(movimento.get("data") or movimento.get("data_contabile") or "")[:10],
        _giorno_operazione_pos(descrizione, ""),
        centesimi,
        re.sub(r"[^a-z0-9]+", "", descrizione.lower()),
        re.sub(r"[^a-z0-9]+", "", str(movimento.get("rapporto") or "").lower()),
    )


def _deduplica_evidenze_pos_banca(
    movimenti: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Restituisce una vista canonica mantenendo gli ID di tutte le fonti.

    Nessun record viene cancellato. Per ogni chiave bancaria deterministica
    viene scelta la rappresentazione piu completa e vengono esposti conteggio
    e identificativi delle copie, utili per audit e pulizie successive.
    """
    gruppi: Dict[tuple, List[Dict[str, Any]]] = {}
    for movimento in movimenti:
        gruppi.setdefault(_chiave_evidenza_pos_banca(movimento), []).append(movimento)

    canonici: List[Dict[str, Any]] = []
    for righe in gruppi.values():
        def rango(riga: Dict[str, Any]) -> tuple:
            return (
                int(bool(riga.get("rapporto"))),
                len(str(riga.get("descrizione_originale") or riga.get("descrizione") or "")),
                str(riga.get("updated_at") or riga.get("created_at") or ""),
            )

        scelta = max(righe, key=rango)
        item = dict(scelta)
        ids = [_id_movimento_pos(riga) for riga in righe if _id_movimento_pos(riga)]
        item["pos_duplicate_source_ids"] = ids
        item["pos_duplicate_sources_unified"] = len(righe) - 1
        canonici.append(item)

    canonici.sort(
        key=lambda riga: str(riga.get("data") or riga.get("data_contabile") or "")
    )
    return canonici


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
        {
            "data": {"$gte": data_da, "$lte": data_a},
            "entity_status": {"$ne": "deleted"},
            "status": {"$nin": ["deleted", "archived", "archiviata"]},
        },
        {"_id": 0, "data": 1, "totale": 1, "pagato_contanti": 1,
         "pagato_elettronico": 1, "pagato_pos": 1,
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
        {"_id": 0, "id": 1, "data": 1, "data_contabile": 1,
         "importo": 1, "descrizione": 1, "descrizione_originale": 1,
         "categoria": 1, "rapporto": 1, "created_at": 1, "updated_at": 1}
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
        corrispettivi_by_date[data]["elettronico"] += _importo_elettronico_xml(c)
        corrispettivi_by_date[data]["non_riscosso"] += float(c.get("pagato_non_riscosso", 0) or 0)
        if c.get("matricola_rt"):
            corrispettivi_by_date[data]["matricole"].add(c.get("matricola_rt"))
    
    pos_by_date = {}
    accrediti_pos_canonici = _deduplica_evidenze_pos_banca(accrediti_pos)
    for p in accrediti_pos_canonici:
        descr = p.get("descrizione_originale") or p.get("descrizione") or ""
        if not _e_accredito_pos_numia_con_giorno(descr):
            continue
        # Giorno operazione dalla descrizione ("... DEL 02/04/26 ...").
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
            "percentuale_coerenza": round((giorni_ok / max(len(tutte_le_date), 1)) * 100, 1),
            "movimenti_banca": len(accrediti_pos_canonici),
            "movimenti_banca_raw": len(accrediti_pos),
            "duplicati_banca_unificati": len(accrediti_pos) - len(accrediti_pos_canonici),
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

    # Un solo motore per giornaliero, mensile e controllo a due fasi. Il
    # precedente aggregate mensile usava la data contabile, sommava le copie
    # degli estratti sovrapposti e confrontava direttamente XML con banca.
    accrediti_anno = await _carica_accrediti_banca_pos(
        db, f"{anno}-01-01", f"{anno}-12-31"
    )
    pos_manuali = await _carica_pos_manuale_per_data(db)

    mesi = []
    totale_anno_elettronico = 0
    totale_anno_pos_terminale = 0
    totale_anno_pos = 0
    totale_movimenti_banca = 0
    totale_movimenti_banca_raw = 0
    totale_duplicati_unificati = 0
    
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
            {"$match": {
                "data": {"$gte": data_da, "$lte": data_a},
                "entity_status": {"$ne": "deleted"},
                "status": {"$nin": ["deleted", "archived", "archiviata"]},
            }},
            {"$group": {
                "_id": None,
                "totale": {"$sum": "$totale"},
                "contanti": {"$sum": "$pagato_contanti"},
                "elettronico": {"$sum": {"$ifNull": ["$pagato_elettronico", "$pagato_pos"]}},
                "count": {"$sum": 1}
            }}
        ]
        
        corr_result = await db["corrispettivi"].aggregate(pipeline_corr).to_list(1)
        
        elettronico = corr_result[0]["elettronico"] if corr_result else 0
        pos_terminale = round(sum(
            float(importo or 0)
            for data, importo in pos_manuali.items()
            if data_da <= data <= data_a
        ), 2)
        evidenze_mese = [
            evidenza for data, evidenza in accrediti_anno.items()
            if data_da <= data <= data_a
        ]
        pos = round(sum(float(e.get("totale") or 0) for e in evidenze_mese), 2)
        movimenti_banca = sum(int(e.get("numero_movimenti") or 0) for e in evidenze_mese)
        movimenti_banca_raw = sum(int(e.get("numero_movimenti_raw") or 0) for e in evidenze_mese)
        duplicati_unificati = sum(int(e.get("duplicati_unificati") or 0) for e in evidenze_mese)
        differenza_xml_pos = round(elettronico - pos_terminale, 2)
        differenza_pos_banca = round(pos - pos_terminale, 2)
        
        totale_anno_elettronico += elettronico
        totale_anno_pos_terminale += pos_terminale
        totale_anno_pos += pos
        totale_movimenti_banca += movimenti_banca
        totale_movimenti_banca_raw += movimenti_banca_raw
        totale_duplicati_unificati += duplicati_unificati
        
        nome_mese = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", 
                     "Lug", "Ago", "Set", "Ott", "Nov", "Dic"][mese-1]
        
        mesi.append({
            "mese": mese,
            "nome": nome_mese,
            "totale_corrispettivi": round(corr_result[0]["totale"] if corr_result else 0, 2),
            "contanti": round(corr_result[0]["contanti"] if corr_result else 0, 2),
            "elettronico_xml": round(elettronico, 2),
            "pos_terminale": pos_terminale,
            "pos_accreditato": round(pos, 2),
            "differenza_xml_pos": differenza_xml_pos,
            "differenza_pos_banca": differenza_pos_banca,
            # Alias retrocompatibile: la quadratura operativa e' banca - POS.
            "differenza": differenza_pos_banca,
            "stato": (
                "vuoto" if not corr_result and not pos_terminale and not pos
                else "ok" if differenza_xml_pos >= -0.5 and abs(differenza_pos_banca) <= 0.5
                else "warning" if differenza_xml_pos >= -5 and abs(differenza_pos_banca) <= 5
                else "error"
            ),
            "corrispettivi_count": corr_result[0]["count"] if corr_result else 0,
            "pos_count": movimenti_banca,
            "pos_count_raw": movimenti_banca_raw,
            "duplicati_banca_unificati": duplicati_unificati,
        })
    
    return {
        "anno": anno,
        "mesi": mesi,
        "totali": {
            "elettronico_xml": round(totale_anno_elettronico, 2),
            "pos_terminale": round(totale_anno_pos_terminale, 2),
            "pos_accreditato": round(totale_anno_pos, 2),
            "differenza_xml_pos": round(
                totale_anno_elettronico - totale_anno_pos_terminale, 2
            ),
            "differenza_pos_banca": round(
                totale_anno_pos - totale_anno_pos_terminale, 2
            ),
            "differenza": round(totale_anno_pos - totale_anno_pos_terminale, 2),
            "movimenti_banca": totale_movimenti_banca,
            "movimenti_banca_raw": totale_movimenti_banca_raw,
            "duplicati_banca_unificati": totale_duplicati_unificati,
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
    
    elettronico = _importo_elettronico_xml(corr)
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
        if not _e_accredito_pos_numia_con_giorno(descr):
            continue
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
    """Crea o corregge il POS reale letto dal terminale per una giornata.

    Il valore XML non viene modificato. Il motore unico salva la chiusura
    manuale e aggiorna insieme l'uscita in Cassa e il trasferimento atteso in
    Banca, che resta da riconciliare con l'estratto conto reale.
    """
    if payload.get("data") is None:
        raise HTTPException(status_code=400, detail="Campo 'data' obbligatorio (YYYY-MM-DD)")
    if payload.get("importo") is None:
        raise HTTPException(status_code=400, detail="Campo 'importo' obbligatorio")
    try:
        result = await registra_chiusura_pos_reale(
            Database.get_db(),
            payload.get("data"),
            payload.get("importo"),
            gestore=payload.get("gestore") or GESTORE_POS_DEFAULT,
            note=(payload.get("note") or "").strip(),
            actor=current_user,
        )
    except ScritturaNonValida as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Con un solo terminale i due importi coincidono; con Nexi + SumUp il
    # totale del giorno e' quello che finisce davvero in Prima Nota.
    totale = result.get("importo_totale_giorno", result["importo"])
    dettaglio = (
        "" if abs(totale - result["importo"]) < 0.01
        else f" Totale POS del giorno (tutti i terminali): EUR {totale:.2f}."
    )
    result["message"] = (
        f"POS reale {result['gestore'].upper()} del {result['data']} salvato: "
        f"EUR {result['importo']:.2f}.{dettaglio} "
        "Prima Nota Cassa e trasferimento atteso in Banca aggiornati."
    )
    return result


@router.post("/chiusure-giornaliere/batch")
@handle_errors
async def upsert_chiusure_giornaliere_batch(
    payload: Dict[str, Any] = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Importa piu' chiusure POS reali con una sola richiesta autenticata.

    Tutte le righe vengono validate prima di iniziare. Le scritture restano
    idempotenti per data e passano dallo stesso motore usato dall'editor
    giornaliero. Una concorrenza limitata evita sia i timeout sia un carico
    eccessivo sul database.
    """
    righe = payload.get("righe")
    if not isinstance(righe, list) or not righe:
        raise HTTPException(status_code=400, detail="Elenco 'righe' obbligatorio")
    if len(righe) > 400:
        raise HTTPException(status_code=400, detail="Massimo 400 giornate per importazione")

    validate: List[Dict[str, Any]] = []
    date_viste = set()
    for indice, riga in enumerate(righe, start=1):
        if not isinstance(riga, dict):
            raise HTTPException(status_code=400, detail=f"Riga {indice} non valida")
        data = str(riga.get("data") or "")[:10]
        try:
            datetime.strptime(data, "%Y-%m-%d")
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"Data non valida alla riga {indice}: {data!r}",
            )
        if data in date_viste:
            raise HTTPException(status_code=400, detail=f"Data duplicata: {data}")
        date_viste.add(data)
        try:
            importo = round(float(riga.get("importo")), 2)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"Importo non valido alla riga {indice}",
            )
        if importo < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Importo negativo alla riga {indice}",
            )
        validate.append({"data": data, "importo": importo})

    db = Database.get_db()
    note = str(payload.get("note") or "Importazione massiva POS").strip()
    # Un'importazione massiva e' l'export di UN terminale: il gestore vale per
    # tutte le righe. Cosi' resta valido anche il vincolo di data unica, che
    # serializza le scritture sullo stesso giorno.
    gestore = payload.get("gestore") or GESTORE_POS_DEFAULT
    semaforo = asyncio.Semaphore(8)

    async def salva(riga: Dict[str, Any]) -> Dict[str, Any]:
        async with semaforo:
            try:
                risultato = await registra_chiusura_pos_reale(
                    db,
                    riga["data"],
                    riga["importo"],
                    gestore=gestore,
                    note=note,
                    actor=current_user,
                )
                return {
                    "data": riga["data"],
                    "importo": riga["importo"],
                    "gestore": gestore,
                    "success": True,
                    "action": risultato.get("action"),
                }
            except Exception as exc:
                logger.exception("Importazione POS fallita per %s", riga["data"])
                return {
                    "data": riga["data"],
                    "importo": riga["importo"],
                    "success": False,
                    "errore": str(exc),
                }

    risultati = await asyncio.gather(*(salva(riga) for riga in validate))
    errori = [r for r in risultati if not r["success"]]
    salvati = [r for r in risultati if r["success"]]
    return {
        "success": not errori,
        "richiesti": len(validate),
        "salvati": len(salvati),
        "errori": len(errori),
        "totale": round(sum(r["importo"] for r in salvati), 2),
        "risultati": risultati,
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
#   diff_serale = pagato_elettronico_xml - pos_manuale_serale
#   Un valore positivo indica che l'XML copre tutti i pagamenti reali POS.
#   Solo un valore negativo oltre tolleranza segnala elettronico mancante nel RT.
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
    override_manuali: Dict[str, float] = {}

    # Fonte 1: chiusure_pos_manuali (import CSV)
    async for c in db["chiusure_pos_manuali"].find(
        {}, {"_id": 0, "data": 1, "importo": 1, "totale": 1, "source": 1}
    ):
        d = c.get("data")
        if not d:
            continue
        if isinstance(d, datetime):
            d = d.strftime("%Y-%m-%d")
        imp = float(c.get("importo") or c.get("totale") or 0)
        if d:
            # Anche 0,00 e' una chiusura manuale esplicita: non va confusa
            # con un dato mancante e non deve riattivare il fallback XML.
            giorno = d[:10]
            if c.get("source") == "inserimento_manuale_terminale":
                override_manuali[giorno] = imp
            else:
                # Gli import storici possono avere piu' componenti/circuiti
                # nello stesso giorno: prima dell'override vanno sommati.
                out[giorno] = out.get(giorno, 0.0) + imp

    out.update(override_manuali)

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
        if d and d[:10] not in override_manuali:
            out[d[:10]] = imp  # fallback storico, mai sopra l'override UI

    return out


async def _carica_accrediti_banca_pos(
    db, data_da: str, data_a: str
) -> Dict[str, Dict[str, Any]]:
    """Carica gli accrediti POS in banca dall'estratto conto.

    Fonte canonica: ``estratto_conto_movimenti``. La data contabile indica
    quando la banca ha registrato il movimento, ma la descrizione NUMIA contiene
    il giorno dell'operazione (``DEL gg/mm/aa``). La quadratura somma tutti i
    circuiti per quel giorno e li confronta con il POS manuale dello stesso
    giorno. Remunerazioni, commissioni, fatture e righe senza ``DEL`` restano
    escluse.
    """
    out: Dict[str, Dict[str, Any]] = {}
    data_a_estesa = (datetime.strptime(data_a, "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d")
    query = {
        "data": {"$gte": data_da, "$lte": data_a_estesa},
        "importo": {"$gt": 0},
        "$or": [
            {"descrizione_originale": {"$regex": "NUMIA", "$options": "i"}},
            {"descrizione": {"$regex": "NUMIA", "$options": "i"}},
        ],
    }

    projection = {
        "_id": 0, "id": 1, "data": 1, "data_contabile": 1,
        "importo": 1, "amount": 1,
        "descrizione": 1, "descrizione_originale": 1,
        "rapporto": 1, "created_at": 1, "updated_at": 1,
    }
    movimenti_raw: List[Dict[str, Any]] = []
    async for m in db["estratto_conto_movimenti"].find(query, projection):
        descrizione = m.get("descrizione_originale") or m.get("descrizione") or ""
        if not _e_accredito_pos_numia_con_giorno(descrizione):
            continue
        giorno_operazione = _giorno_operazione_pos(descrizione, "")
        if not (data_da <= giorno_operazione <= data_a):
            continue
        movimenti_raw.append(m)

    for m in _deduplica_evidenze_pos_banca(movimenti_raw):
        descrizione = m.get("descrizione_originale") or m.get("descrizione") or ""
        giorno_operazione = _giorno_operazione_pos(descrizione, "")
        imp = float(m.get("importo") or m.get("amount") or 0)
        evidenza = out.setdefault(giorno_operazione, {
            "totale": 0.0,
            "numero_movimenti": 0,
            "numero_movimenti_raw": 0,
            "duplicati_unificati": 0,
            "date_contabili": [],
            "fonti_movimento_ids": [],
            "origine": "estratto_conto_movimenti",
        })
        evidenza["totale"] += imp
        evidenza["numero_movimenti"] += 1
        duplicati = int(m.get("pos_duplicate_sources_unified") or 0)
        evidenza["numero_movimenti_raw"] += 1 + duplicati
        evidenza["duplicati_unificati"] += duplicati
        for movimento_id in m.get("pos_duplicate_source_ids") or []:
            if movimento_id not in evidenza["fonti_movimento_ids"]:
                evidenza["fonti_movimento_ids"].append(movimento_id)
        data_contabile = str(m.get("data") or "")[:10]
        if data_contabile and data_contabile not in evidenza["date_contabili"]:
            evidenza["date_contabili"].append(data_contabile)

    for evidenza in out.values():
        evidenza["totale"] = round(evidenza["totale"], 2)
        evidenza["date_contabili"].sort()
        evidenza["fonti_movimento_ids"].sort()

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

    FASE 1: Verifica che il registratore fiscale copra i pagamenti POS reali
      - Confronto: pagato_elettronico XML − POS serale manuale
      - Un risultato positivo e' coerente; un risultato negativo oltre
        tolleranza genera l'alert per l'importo elettronico mancante

    FASE 2: Verifica accrediti bancari
      - Confronto: accrediti con ``DEL gg/mm/aa`` − POS manuale dello stesso
        giorno ``gg/mm/aa``; la data contabile non decide l'abbinamento

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
        {
            "data": {"$gte": data_da, "$lte": data_a},
            "entity_status": {"$ne": "deleted"},
            "status": {"$nin": ["deleted", "archived", "archiviata"]},
        },
        {
            "_id": 0, "data": 1,
            "pagato_elettronico": 1, "pagato_pos": 1,
            "pagato_contanti": 1, "totale": 1, "totale_complessivo": 1,
            # v2: stato del corrispettivo + dati provvisori/ufficiali
            "stato": 1, "totale_manuale": 1, "totale_xml": 1,
            "source": 1, "data_inserimento_manuale": 1, "data_import_xml": 1,
            "content_hash": 1, "filename": 1,
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

    # Index corrispettivi per data. Possono esistere piu' XML nella stessa
    # giornata (piu' RT o sostituzione della matricola): vanno sommati, non
    # sovrascritti con l'ultimo documento restituito da Mongo.
    corr_by_date: Dict[str, Dict] = {}
    for c in corrispettivi:
        d = c.get("data")
        if isinstance(d, datetime):
            d = d.strftime("%Y-%m-%d")
        if not d:
            continue
        giorno = d[:10]
        aggregato = corr_by_date.setdefault(giorno, {
            "pagato_elettronico": 0.0,
            "totale_xml": None,
            "totale_manuale": None,
            "stato": None,
            "ha_xml": False,
        })
        aggregato["pagato_elettronico"] += _importo_elettronico_xml(c)
        if c.get("totale_manuale") is not None:
            aggregato["totale_manuale"] = c.get("totale_manuale")
        if _e_corrispettivo_xml(c):
            aggregato["ha_xml"] = True
            aggregato["stato"] = "definitivo_xml"
            aggregato["totale_xml"] = float(aggregato.get("totale_xml") or 0) + float(
                c.get("totale_xml")
                if c.get("totale_xml") is not None
                else c.get("totale") or c.get("totale_complessivo") or 0
            )
        elif aggregato.get("stato") != "definitivo_xml":
            aggregato["stato"] = c.get("stato")

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
        "fase2_movimenti_banca": sum(
            int(evidenza.get("numero_movimenti") or 0) for evidenza in accrediti.values()
        ),
        "fase2_movimenti_banca_raw": sum(
            int(evidenza.get("numero_movimenti_raw") or 0) for evidenza in accrediti.values()
        ),
        "fase2_duplicati_banca_unificati": sum(
            int(evidenza.get("duplicati_unificati") or 0) for evidenza in accrediti.values()
        ),
    }

    # Gli alert di compensazione si attivano il giorno DOPO quello della differenza.
    # Cioè: alert[data=X] = guarda diff_serale del giorno (X-1 lavorativo).
    # Per semplicità d'implementazione, calcolo la diff sul giorno X e marco
    # alert_attivo_il = giorno successivo in formato stringa.

    # FASE 2 (v5): il riferimento ``DEL gg/mm/aa`` nella descrizione bancaria
    # identifica il giorno POS. I circuiti dello stesso giorno sono già sommati
    # da _carica_accrediti_banca_pos e si confrontano col POS manuale del giorno.
    gruppi_accr: Dict[str, Dict[str, Any]] = {}
    for d in sorted(date_note):
        pos_v = float(pos_manuali.get(d) or 0)
        if pos_v <= 0:
            continue
        data_attesa = _data_accredito_attesa(d)
        evidenza_banca = accrediti.get(d) or {}
        accr = round(float(evidenza_banca.get("totale") or 0), 2)
        numero_movimenti_banca = int(evidenza_banca.get("numero_movimenti") or 0)
        g = {
            "giorni": [d],
            "pos_tot": round(pos_v, 2),
            "dettaglio": [{"data": d, "pos_manuale": round(pos_v, 2)}],
            "data_accredito_attesa": data_attesa,
        }
        if data_attesa > oggi:
            g.update(
                stato="in_attesa", accredito=0.0, diff=0.0,
                numero_movimenti_banca=numero_movimenti_banca,
                origine_accredito=evidenza_banca.get("origine"),
                date_contabili_banca=evidenza_banca.get("date_contabili", []),
                riconciliato_banca_reale=False,
            )
        elif accr == 0:
            g.update(
                stato="mancante", accredito=0.0, diff=round(-pos_v, 2),
                numero_movimenti_banca=0,
                origine_accredito=None,
                date_contabili_banca=[],
                riconciliato_banca_reale=False,
            )
        else:
            diff = round(accr - pos_v, 2)
            stato = "ok" if abs(diff) <= tolleranza_euro else ("differenza" if diff < 0 else "extra")
            # Il badge di riconciliazione e' ammesso solo se il dato arriva
            # davvero dall'estratto conto canonico e l'importo quadra.
            riconciliato_banca_reale = bool(
                stato == "ok"
                and numero_movimenti_banca > 0
                and evidenza_banca.get("origine") == "estratto_conto_movimenti"
            )
            g.update(
                stato=stato,
                accredito=round(accr, 2),
                diff=diff,
                numero_movimenti_banca=numero_movimenti_banca,
                origine_accredito=evidenza_banca.get("origine"),
                date_contabili_banca=evidenza_banca.get("date_contabili", []),
                riconciliato_banca_reale=riconciliato_banca_reale,
            )
        gruppi_accr[d] = g

    saldo_progressivo = 0.0
    stats["fase2_pos_totale"] = 0.0
    stats["fase2_accrediti_totale"] = 0.0

    for d in sorted(date_note):
        c_row = corr_by_date.get(d, {})
        xml_el = _importo_elettronico_xml(c_row)
        pos_man = float(pos_manuali.get(d) or 0)
        pos_man_presente = d in pos_manuali

        # FASE 0 v3: stato corrispettivo (provvisorio / definitivo_xml / manca_xml)
        stato_corr_raw = c_row.get("stato")
        totale_manuale_corr = c_row.get("totale_manuale")
        totale_xml_corr = c_row.get("totale_xml")
        if not stato_corr_raw:
            # Retrocompat: se non c'è stato esplicito, dedurlo dai campi
            has_xml = bool(c_row.get("ha_xml"))
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
        if stato_corr in ("provvisorio", "manca_xml") and pos_man_presente:
            # Abbiamo il POS serale ma non i dati fiscali → aspettiamo XML
            diff_serale = 0.0
            stato_serale = "in_attesa_xml"
            alert_serale = None
        elif xml_el > 0 or pos_man_presente:
            # Convenzione canonica: XML - POS reale. Se l'XML e' maggiore,
            # tutti i pagamenti carta risultano coperti dagli scontrini emessi.
            diff_serale, xml_copre_pos = _coerenza_xml_pos(
                xml_el, pos_man, tolleranza_euro
            )
            if xml_copre_pos:
                stato_serale = "ok"
                alert_serale = None
            else:
                importo_mancante_xml = abs(diff_serale)
                stato_serale = "differenza_in_piu_da_registrare"
                alert_serale = {
                    "attivo": True,
                    "tipo": "registrare_di_piu",
                    "importo": importo_mancante_xml,
                    "messaggio": (
                        f"Il {d} hai battuto al registratore €{importo_mancante_xml:.2f} in MENO "
                        f"di pagamento elettronico rispetto al POS reale. "
                        f"Devi registrare €{importo_mancante_xml:.2f} in PIÙ come elettronico per compensare."
                    ),
                }
                stats["fase1_diff_piu"] += 1
                stats["importo_tot_da_compensare_piu"] += importo_mancante_xml
        else:
            diff_serale = 0.0
            stato_serale = "no_dati"
            alert_serale = None

        if stato_serale == "ok":
            stats["fase1_ok"] += 1

        # FASE 2 (v5): stesso giorno operazione letto dalla descrizione bancaria.
        # La data attesa serve solo a distinguere un accredito non ancora dovuto.
        data_accr_attesa = _data_accredito_attesa(d)
        gruppo = gruppi_accr.get(d)
        capogruppo = bool(gruppo and pos_man > 0)
        pos_gruppo = 0.0
        giorni_gruppo = 0

        dettaglio_gruppo = None
        numero_movimenti_banca = 0
        numero_movimenti_banca_raw = 0
        duplicati_banca_unificati = 0
        fonti_movimento_ids: List[str] = []
        origine_accredito = None
        date_contabili_banca: List[str] = []
        riconciliato_banca_reale = False
        if pos_man <= 0 or not gruppo:
            diff_accr = 0.0
            accredito = 0.0
            stato_accr = "no_pos_manuale"
        else:
            stato_accr = gruppo["stato"]
            diff_accr = gruppo["diff"]
            accredito = gruppo["accredito"]
            numero_movimenti_banca = gruppo.get("numero_movimenti_banca", 0)
            evidenza_giorno = accrediti.get(d) or {}
            numero_movimenti_banca_raw = int(
                evidenza_giorno.get("numero_movimenti_raw") or numero_movimenti_banca
            )
            duplicati_banca_unificati = int(
                evidenza_giorno.get("duplicati_unificati") or 0
            )
            fonti_movimento_ids = list(evidenza_giorno.get("fonti_movimento_ids") or [])
            origine_accredito = gruppo.get("origine_accredito")
            date_contabili_banca = gruppo.get("date_contabili_banca", [])
            riconciliato_banca_reale = bool(gruppo.get("riconciliato_banca_reale"))
            pos_gruppo = gruppo["pos_tot"]
            giorni_gruppo = len(gruppo["giorni"])
            # Statistiche e saldo: una volta per giorno operazione.
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
            "pos_manuale_presente": pos_man_presente,
            "diff_serale": diff_serale,
            "stato_serale": stato_serale,
            "alert_compensazione": alert_serale,
            # Fase 2 (v4, a gruppi di accredito)
            "data_accredito_attesa": data_accr_attesa,
            "accredito_banca": round(accredito, 2),
            "diff_accredito": diff_accr,
            "stato_accredito": stato_accr,
            "riconciliato_banca_reale": riconciliato_banca_reale,
            "numero_movimenti_banca": numero_movimenti_banca,
            "numero_movimenti_banca_raw": numero_movimenti_banca_raw,
            "duplicati_banca_unificati": duplicati_banca_unificati,
            "fonti_movimento_ids": fonti_movimento_ids,
            "origine_accredito": origine_accredito,
            "date_contabili_banca": date_contabili_banca,
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
