"""
Router Chiusura Esercizio - Wizard guidato per la chiusura annuale
Verifica completezza dati, genera scritture di chiusura, prepara nuovo anno
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

router = APIRouter()
logger = logging.getLogger(__name__)


class ChiusuraEsercizioInput(BaseModel):
    anno: int
    conferma_scritture: bool = False
    note: Optional[str] = None


@router.get("/verifica-preliminare/{anno}")
@handle_errors
async def verifica_preliminare_chiusura(anno: int) -> Dict[str, Any]:
    """
    Step 1: Verifica preliminare della completezza dei dati.
    Controlla se tutti i documenti sono stati registrati.
    """
    db = Database.get_db()
    
    problemi = []
    avvisi = []
    completamenti = []
    
    # 1. Verifica fatture non registrate
    fatture_non_contabilizzate = await db["invoices"].count_documents({
        "invoice_date": {"$regex": f"^{anno}"},
        "contabilizzata": {"$ne": True}
    })
    if fatture_non_contabilizzate > 0:
        problemi.append({
            "tipo": "fatture_non_contabilizzate",
            "messaggio": f"{fatture_non_contabilizzate} fatture non contabilizzate",
            "gravita": "alta",
            "azione": "Contabilizzare tutte le fatture prima della chiusura"
        })
    else:
        completamenti.append("Tutte le fatture sono contabilizzate")
    
    # 2. Verifica corrispettivi registrati
    corrispettivi_mancanti = await db["corrispettivi"].aggregate([
        {"$match": {"data": {"$regex": f"^{anno}"}}},
        {"$group": {"_id": {"$substr": ["$data", 5, 2]}}},
        {"$sort": {"_id": 1}}
    ]).to_list(12)
    
    mesi_registrati = [int(c["_id"]) for c in corrispettivi_mancanti]
    mesi_mancanti = [m for m in range(1, 13) if m not in mesi_registrati]
    
    if mesi_mancanti:
        avvisi.append({
            "tipo": "corrispettivi_mancanti",
            "messaggio": f"Corrispettivi mancanti per i mesi: {mesi_mancanti}",
            "gravita": "media",
            "azione": "Verificare se i corrispettivi sono stati importati"
        })
    else:
        completamenti.append("Corrispettivi registrati per tutto l'anno")
    
    # 3. Verifica cedolini/buste paga
    cedolini = await db["cedolini"].count_documents({"anno": anno})
    prima_nota_salari = await db["prima_nota_salari"].count_documents({"anno": anno})
    
    if cedolini == 0 and prima_nota_salari == 0:
        avvisi.append({
            "tipo": "salari_mancanti",
            "messaggio": "Nessun cedolino o salario registrato per l'anno",
            "gravita": "media",
            "azione": "Verificare la registrazione dei salari"
        })
    else:
        completamenti.append(f"Salari registrati: {max(cedolini, prima_nota_salari)} record")
    
    # 4. Verifica TFR accantonato
    tfr_anno = await db["tfr_accantonamenti"].find_one({"anno": anno})
    if not tfr_anno:
        avvisi.append({
            "tipo": "tfr_non_accantonato",
            "messaggio": "TFR non accantonato per l'anno",
            "gravita": "media",
            "azione": "Eseguire il calcolo TFR batch dall'endpoint /api/tfr/calcola-batch/{anno}"
        })
    else:
        completamenti.append("TFR accantonato")
    
    # 5. Verifica ammortamenti
    ammortamenti_anno = await db["cespiti"].count_documents({
        "stato": "attivo",
        "piano_ammortamento": {"$elemMatch": {"anno": anno}}
    })
    cespiti_attivi = await db["cespiti"].count_documents({
        "stato": "attivo",
        "ammortamento_completato": False
    })
    
    if cespiti_attivi > 0 and ammortamenti_anno == 0:
        avvisi.append({
            "tipo": "ammortamenti_non_calcolati",
            "messaggio": f"{cespiti_attivi} cespiti attivi senza ammortamento {anno}",
            "gravita": "media",
            "azione": "Eseguire il calcolo ammortamenti dall'endpoint /api/cespiti/registra/{anno}"
        })
    else:
        completamenti.append(f"Ammortamenti registrati per {ammortamenti_anno} cespiti")
    
    # 6. Verifica riconciliazione bancaria
    movimenti_banca = await db["estratto_conto_movimenti"].count_documents({
        "data": {"$regex": f"^{anno}"}
    })
    if movimenti_banca == 0:
        avvisi.append({
            "tipo": "estratto_conto_mancante",
            "messaggio": "Nessun movimento bancario importato per l'anno",
            "gravita": "bassa",
            "azione": "Importare l'estratto conto bancario"
        })
    else:
        completamenti.append(f"{movimenti_banca} movimenti bancari registrati")
    
    # Calcola punteggio completezza
    score = len(completamenti) / (len(completamenti) + len(problemi) + len(avvisi)) * 100 if (len(completamenti) + len(problemi) + len(avvisi)) > 0 else 0
    
    pronto = len(problemi) == 0
    
    return {
        "anno": anno,
        "pronto_per_chiusura": pronto,
        "punteggio_completezza": round(score, 1),
        "problemi_bloccanti": problemi,
        "avvisi": avvisi,
        "completamenti": completamenti,
        "step_successivo": "bilancino_verifica" if pronto else "risolvere_problemi"
    }


@router.get("/bilancino-verifica/{anno}")
@handle_errors
async def get_bilancino_verifica(anno: int) -> Dict[str, Any]:
    """
    Step 2: Genera un bilancino di verifica per la chiusura.
    Mostra totali ricavi/costi e risultato d'esercizio.
    """
    db = Database.get_db()
    
    data_inizio = f"{anno}-01-01"
    data_fine = f"{anno}-12-31"
    
    # RICAVI
    corrispettivi = await db["corrispettivi"].aggregate([
        {"$match": {"data": {"$gte": data_inizio, "$lte": data_fine}}},
        {"$group": {"_id": None, "totale": {"$sum": "$totale"}}}
    ]).to_list(1)
    
    fatture_emesse = await db["invoices"].aggregate([
        {"$match": {
            "invoice_date": {"$gte": data_inizio, "$lte": data_fine},
            "tipo_documento": {"$in": ["TD01", "TD24", "TD26"]}
        }},
        {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
    ]).to_list(1)
    
    totale_ricavi = (corrispettivi[0]["totale"] if corrispettivi else 0) + \
                    (fatture_emesse[0]["totale"] if fatture_emesse else 0)
    
    # COSTI
    acquisti = await db["invoices"].aggregate([
        {"$match": {
            "invoice_date": {"$gte": data_inizio, "$lte": data_fine},
            "tipo_documento": {"$nin": ["TD01", "TD04", "TD24", "TD26"]}
        }},
        {"$group": {"_id": None, "totale": {"$sum": "$total_amount"}}}
    ]).to_list(1)
    
    personale = await db["prima_nota_salari"].aggregate([
        {"$match": {"anno": anno}},
        {"$group": {"_id": None, "totale": {"$sum": "$costo_azienda"}}}
    ]).to_list(1)
    
    ammortamenti = await db["movimenti_contabili"].aggregate([
        {"$match": {"tipo": "ammortamento", "anno": anno}},
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}}
    ]).to_list(1)
    
    tfr = await db["movimenti_contabili"].aggregate([
        {"$match": {"tipo": "tfr_accantonamento", "anno": anno}},
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}}
    ]).to_list(1)
    
    totale_costi = (acquisti[0]["totale"] if acquisti else 0) + \
                   (personale[0]["totale"] if personale else 0) + \
                   (ammortamenti[0]["totale"] if ammortamenti else 0) + \
                   (tfr[0]["totale"] if tfr else 0)
    
    utile_perdita = totale_ricavi - totale_costi
    
    return {
        "anno": anno,
        "bilancino": {
            "ricavi": {
                "corrispettivi": round(corrispettivi[0]["totale"] if corrispettivi else 0, 2),
                "fatture_emesse": round(fatture_emesse[0]["totale"] if fatture_emesse else 0, 2),
                "totale": round(totale_ricavi, 2)
            },
            "costi": {
                "acquisti_merce": round(acquisti[0]["totale"] if acquisti else 0, 2),
                "personale": round(personale[0]["totale"] if personale else 0, 2),
                "ammortamenti": round(ammortamenti[0]["totale"] if ammortamenti else 0, 2),
                "tfr": round(tfr[0]["totale"] if tfr else 0, 2),
                "totale": round(totale_costi, 2)
            },
            "risultato": {
                "utile_perdita": round(utile_perdita, 2),
                "tipo": "utile" if utile_perdita > 0 else "perdita",
                "margine_percentuale": round(utile_perdita / totale_ricavi * 100, 1) if totale_ricavi > 0 else 0
            }
        },
        "step_successivo": "conferma_chiusura"
    }


@router.post("/esegui-chiusura")
@handle_errors
async def esegui_chiusura_esercizio(input_data: ChiusuraEsercizioInput) -> Dict[str, Any]:
    """
    Step 3: Esegue le scritture di chiusura dell'esercizio.
    Genera le scritture di epilogo e chiude i conti economici.
    """
    db = Database.get_db()
    
    if not input_data.conferma_scritture:
        raise HTTPException(
            status_code=400,
            detail="Devi confermare le scritture impostando conferma_scritture=true"
        )
    
    # Verifica preliminare
    verifica = await verifica_preliminare_chiusura(input_data.anno)
    if not verifica["pronto_per_chiusura"]:
        raise HTTPException(
            status_code=400,
            detail=f"Impossibile procedere: {len(verifica['problemi_bloccanti'])} problemi bloccanti"
        )
    
    # Genera bilancino
    bilancino = await get_bilancino_verifica(input_data.anno)
    
    # Registra scrittura di chiusura
    chiusura_id = str(uuid4())
    data_chiusura = f"{input_data.anno}-12-31"
    
    scrittura_chiusura = {
        "id": chiusura_id,
        "anno": input_data.anno,
        "data": data_chiusura,
        "tipo": "chiusura_esercizio",
        "descrizione": f"Chiusura esercizio {input_data.anno}",
        "bilancino": bilancino["bilancino"],
        "risultato_esercizio": bilancino["bilancino"]["risultato"]["utile_perdita"],
        "tipo_risultato": bilancino["bilancino"]["risultato"]["tipo"],
        "note": input_data.note,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "sistema"
    }
    
    await db["chiusure_esercizio"].insert_one(scrittura_chiusura.copy())
    
    # Registra movimento contabile per risultato d'esercizio
    movimento_risultato = {
        "id": str(uuid4()),
        "data": data_chiusura,
        "descrizione": f"Risultato d'esercizio {input_data.anno}",
        "tipo": "risultato_esercizio",
        "importo": abs(bilancino["bilancino"]["risultato"]["utile_perdita"]),
        "segno": "avere" if bilancino["bilancino"]["risultato"]["utile_perdita"] > 0 else "dare",
        "anno": input_data.anno,
        "chiusura_id": chiusura_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["movimenti_contabili"].insert_one(movimento_risultato.copy())
    
    return {
        "success": True,
        "chiusura_id": chiusura_id,
        "anno": input_data.anno,
        "messaggio": f"Chiusura esercizio {input_data.anno} completata",
        "risultato": {
            "tipo": bilancino["bilancino"]["risultato"]["tipo"],
            "importo": bilancino["bilancino"]["risultato"]["utile_perdita"]
        },
        "step_successivo": "apertura_nuovo_esercizio"
    }


@router.get("/stato/{anno}")
@handle_errors
async def get_stato_chiusura(anno: int) -> Dict[str, Any]:
    """
    Verifica lo stato di chiusura di un esercizio.
    """
    db = Database.get_db()
    
    chiusura = await db["chiusure_esercizio"].find_one(
        {"anno": anno},
        {"_id": 0}
    )
    
    if chiusura:
        return {
            "anno": anno,
            "stato": "chiuso",
            "data_chiusura": chiusura["created_at"],
            "risultato": chiusura["risultato_esercizio"],
            "tipo_risultato": chiusura["tipo_risultato"],
            "chiusura_id": chiusura["id"]
        }
    else:
        return {
            "anno": anno,
            "stato": "aperto",
            "messaggio": "Esercizio non ancora chiuso"
        }


@router.get("/storico")
@handle_errors
async def get_storico_chiusure() -> List[Dict[str, Any]]:
    """
    Restituisce lo storico delle chiusure esercizio.
    """
    db = Database.get_db()
    
    chiusure = await db["chiusure_esercizio"].find(
        {},
        {"_id": 0}
    ).sort("anno", -1).to_list(100)
    
    return chiusure


@router.post("/apertura-nuovo-esercizio")
@handle_errors
async def apertura_nuovo_esercizio(anno_nuovo: int) -> Dict[str, Any]:
    """
    Apre il nuovo esercizio riportando i saldi dall'anno precedente.
    
    Operazioni:
    1. Verifica che l'anno precedente sia chiuso
    2. Calcola i saldi finali dell'anno precedente
    3. Crea scritture di apertura per il nuovo anno
    4. Riporta:
       - Saldo cassa
       - Saldo banca
       - Crediti clienti (fatture non pagate)
       - Debiti fornitori (fatture da pagare)
       - TFR accantonato
       - Assegni in portafoglio
    """
    db = Database.get_db()
    anno_precedente = anno_nuovo - 1
    
    # Verifica chiusura anno precedente
    chiusura = await db["chiusure_esercizio"].find_one({"anno": anno_precedente}, {"_id": 0})
    if not chiusura:
        raise HTTPException(
            status_code=400, 
            detail=f"L'esercizio {anno_precedente} non è ancora stato chiuso"
        )
    
    # Calcola saldi da riportare
    
    # 1. Saldo Cassa
    cassa_entrate = await db["prima_nota_cassa"].aggregate([
        {"$match": {"anno": anno_precedente, "tipo": "entrata"}},
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}}
    ]).to_list(1)
    cassa_uscite = await db["prima_nota_cassa"].aggregate([
        {"$match": {"anno": anno_precedente, "tipo": "uscita"}},
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}}
    ]).to_list(1)
    
    saldo_cassa = (cassa_entrate[0]["totale"] if cassa_entrate else 0) - (cassa_uscite[0]["totale"] if cassa_uscite else 0)
    
    # 2. Saldo Banca
    banca_entrate = await db["prima_nota_banca"].aggregate([
        {"$match": {"anno": anno_precedente, "tipo": "entrata"}},
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}}
    ]).to_list(1)
    banca_uscite = await db["prima_nota_banca"].aggregate([
        {"$match": {"anno": anno_precedente, "tipo": "uscita"}},
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}}
    ]).to_list(1)
    
    saldo_banca = (banca_entrate[0]["totale"] if banca_entrate else 0) - (banca_uscite[0]["totale"] if banca_uscite else 0)
    
    # 3. Fatture da pagare (debiti fornitori)
    fatture_da_pagare = await db["invoices"].aggregate([
        {"$match": {"pagato": {"$ne": True}}},
        {"$group": {"_id": None, "totale": {"$sum": "$importo_totale"}}}
    ]).to_list(1)
    debiti_fornitori = fatture_da_pagare[0]["totale"] if fatture_da_pagare else 0
    
    # 4. Assegni in portafoglio non incassati
    assegni_portafoglio = await db["assegni"].aggregate([
        {"$match": {"stato": {"$in": ["emesso", "consegnato"]}, "incassato": {"$ne": True}}},
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}}
    ]).to_list(1)
    assegni_da_incassare = assegni_portafoglio[0]["totale"] if assegni_portafoglio else 0
    
    # 5. TFR accantonato
    tfr_accantonato = await db["tfr_accantonamenti"].aggregate([
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}}
    ]).to_list(1)
    totale_tfr = tfr_accantonato[0]["totale"] if tfr_accantonato else 0
    
    # Crea scrittura di apertura
    apertura_id = str(uuid4())
    data_apertura = f"{anno_nuovo}-01-01"
    
    scrittura_apertura = {
        "id": apertura_id,
        "anno": anno_nuovo,
        "data": data_apertura,
        "tipo": "apertura_esercizio",
        "descrizione": f"Apertura esercizio {anno_nuovo} - Riporto da {anno_precedente}",
        "saldi_riportati": {
            "saldo_cassa": saldo_cassa,
            "saldo_banca": saldo_banca,
            "debiti_fornitori": debiti_fornitori,
            "assegni_da_incassare": assegni_da_incassare,
            "tfr_accantonato": totale_tfr
        },
        "anno_precedente": anno_precedente,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["aperture_esercizio"].insert_one(scrittura_apertura.copy())
    
    # Crea movimento di apertura in Prima Nota Cassa (se c'è saldo)
    if saldo_cassa != 0:
        movimento_cassa = {
            "id": str(uuid4()),
            "data": data_apertura,
            "anno": anno_nuovo,
            "tipo": "entrata" if saldo_cassa > 0 else "uscita",
            "importo": abs(saldo_cassa),
            "descrizione": f"Saldo iniziale da esercizio {anno_precedente}",
            "categoria": "Riporto",
            "source": "apertura_esercizio",
            "apertura_id": apertura_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db["prima_nota_cassa"].insert_one(movimento_cassa.copy())
    
    # Crea movimento di apertura in Prima Nota Banca (se c'è saldo)
    if saldo_banca != 0:
        movimento_banca = {
            "id": str(uuid4()),
            "data": data_apertura,
            "anno": anno_nuovo,
            "tipo": "entrata" if saldo_banca > 0 else "uscita",
            "importo": abs(saldo_banca),
            "descrizione": f"Saldo iniziale da esercizio {anno_precedente}",
            "categoria": "Riporto",
            "source": "apertura_esercizio",
            "apertura_id": apertura_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db["prima_nota_banca"].insert_one(movimento_banca.copy())
    
    logger.info(f"Apertura esercizio {anno_nuovo} completata: Cassa={saldo_cassa}, Banca={saldo_banca}")
    
    return {
        "success": True,
        "apertura_id": apertura_id,
        "anno_nuovo": anno_nuovo,
        "anno_precedente": anno_precedente,
        "saldi_riportati": scrittura_apertura["saldi_riportati"],
        "messaggio": f"Esercizio {anno_nuovo} aperto con riporto saldi da {anno_precedente}"
    }


@router.get("/saldi-iniziali/{anno}")
@handle_errors
async def get_saldi_iniziali(anno: int) -> Dict[str, Any]:
    """
    Restituisce i saldi iniziali riportati per un anno.
    """
    db = Database.get_db()
    
    apertura = await db["aperture_esercizio"].find_one(
        {"anno": anno},
        {"_id": 0}
    )
    
    if apertura:
        return {
            "anno": anno,
            "saldi": apertura["saldi_riportati"],
            "data_apertura": apertura["data"],
            "anno_provenienza": apertura.get("anno_precedente")
        }
    else:
        return {
            "anno": anno,
            "saldi": None,
            "messaggio": "Nessuna apertura registrata per questo anno"
        }

