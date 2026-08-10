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
from app.models.stati import STATI_PAGATI
from app.routers.accounting.contabilita_gestionale import _bilancio_verifica_da_registro
from app.routers.prima_nota_module.common import (
    aggrega_saldo_prima_nota,
    filtro_saldo_prima_nota,
)
from app.services.registrazione_contabile import registra_scrittura_semplice
from app.utils.error_handler import handle_errors

router = APIRouter()
logger = logging.getLogger(__name__)


class ChiusuraEsercizioInput(BaseModel):
    anno: int
    conferma_scritture: bool = False
    conferma_quadrature: bool = False
    conferma_testo: Optional[str] = None
    note: Optional[str] = None


class AperturaEsercizioInput(BaseModel):
    anno_nuovo: int
    conferma_testo: Optional[str] = None


def _problema(tipo: str, messaggio: str, azione: str) -> Dict[str, str]:
    return {
        "tipo": tipo,
        "messaggio": messaggio,
        "gravita": "alta",
        "azione": azione,
    }


def _saldo_economico(conto: Dict[str, Any]) -> float:
    """Saldo economico positivo: ricavo in AVERE o costo in DARE."""
    if conto.get("tipo") == "ricavo":
        return round(float(conto.get("avere") or 0) - float(conto.get("dare") or 0), 2)
    return round(float(conto.get("dare") or 0) - float(conto.get("avere") or 0), 2)


@router.get("/verifica-preliminare/{anno}")
@handle_errors
async def verifica_preliminare_chiusura(anno: int) -> Dict[str, Any]:
    """Verifica le condizioni minime prima di consentire una chiusura reale."""
    db = Database.get_db()
    problemi: List[Dict[str, Any]] = []
    avvisi: List[Dict[str, Any]] = []
    completamenti: List[str] = []

    if anno >= datetime.now(timezone.utc).year:
        problemi.append(_problema(
            "esercizio_non_concluso",
            f"L'esercizio {anno} non è ancora concluso",
            "La chiusura è consentita solo dopo il 31 dicembre dell'anno selezionato",
        ))

    chiusura_esistente = await db["chiusure_esercizio"].find_one(
        {"anno": anno}, {"_id": 0, "id": 1, "created_at": 1}
    )
    if chiusura_esistente:
        problemi.append(_problema(
            "esercizio_gia_chiuso",
            f"L'esercizio {anno} risulta già chiuso",
            "Consultare lo storico; non generare una seconda chiusura",
        ))

    registro = await _bilancio_verifica_da_registro(db, anno, False)
    completezza = registro["completezza_registro"]
    qualita = registro["qualita_registro"]
    if completezza["scritture_registrate"] == 0:
        problemi.append(_problema(
            "registro_contabile_vuoto",
            "Nessuna scrittura valida in partita doppia è presente nel registro",
            "Registrare fatture e corrispettivi nel registro definitivo",
        ))
    if completezza["fatture_da_registrare"]:
        problemi.append(_problema(
            "fatture_non_contabilizzate",
            f"{completezza['fatture_da_registrare']} fatture non registrate in contabilità",
            "Registrare tutte le fatture nel registro definitivo",
        ))
    if completezza["corrispettivi_da_registrare"]:
        problemi.append(_problema(
            "corrispettivi_non_contabilizzati",
            f"{completezza['corrispettivi_da_registrare']} corrispettivi non registrati in contabilità",
            "Registrare tutti i corrispettivi nel registro definitivo",
        ))
    if not registro["quadratura"]:
        problemi.append(_problema(
            "registro_non_quadrato",
            "Il registro definitivo non è quadrato o contiene scritture non valide",
            "Correggere scritture sbilanciate, senza righe o con conti mancanti",
        ))
    if registro["quadratura"] and completezza["completo"] and completezza["scritture_registrate"]:
        completamenti.append(
            f"Registro definitivo completo e quadrato: {completezza['scritture_registrate']} scritture"
        )

    mesi = await db["corrispettivi"].aggregate([
        {"$match": {
            "data": {"$regex": f"^{anno}"},
            "entity_status": {"$ne": "deleted"},
        }},
        {"$group": {"_id": {"$substr": ["$data", 5, 2]}}},
        {"$sort": {"_id": 1}},
    ]).to_list(12)
    mesi_registrati = sorted({int(c["_id"]) for c in mesi if str(c.get("_id", "")).isdigit()})
    mesi_mancanti = [mese for mese in range(1, 13) if mese not in mesi_registrati]
    if mesi_mancanti:
        problemi.append(_problema(
            "mesi_corrispettivi_mancanti",
            f"Nessun corrispettivo nei mesi: {', '.join(map(str, mesi_mancanti))}",
            "Verificare i documenti RT mensili prima di chiudere",
        ))
    else:
        completamenti.append("Corrispettivi presenti in tutti i 12 mesi")

    # Cedolini e accantonamenti devono essere presenti quando l'azienda ha salari.
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
    
    tfr_anno = await db["tfr_accantonamenti"].find_one({"anno": anno})
    if (cedolini or prima_nota_salari) and not tfr_anno:
        problemi.append({
            "tipo": "tfr_non_accantonato",
            "messaggio": "TFR non accantonato per l'anno",
            "gravita": "alta",
            "azione": "Eseguire il calcolo TFR batch dall'endpoint /api/tfr/calcola-batch/{anno}"
        })
    elif tfr_anno:
        completamenti.append("TFR accantonato")

    ammortamenti_anno = await db["cespiti"].count_documents({
        "stato": "attivo",
        "piano_ammortamento": {"$elemMatch": {"anno": anno}}
    })
    cespiti_attivi = await db["cespiti"].count_documents({
        "stato": "attivo",
        "ammortamento_completato": False
    })
    if cespiti_attivi > 0 and ammortamenti_anno == 0:
        problemi.append({
            "tipo": "ammortamenti_non_calcolati",
            "messaggio": f"{cespiti_attivi} cespiti attivi senza ammortamento {anno}",
            "gravita": "alta",
            "azione": "Eseguire il calcolo ammortamenti dall'endpoint /api/cespiti/registra/{anno}"
        })
    else:
        completamenti.append(f"Ammortamenti registrati per {ammortamenti_anno} cespiti")

    movimenti_banca = await db["estratto_conto_movimenti"].count_documents({
        "data": {"$regex": f"^{anno}"},
        "status": {"$nin": ["deleted", "archived"]},
    })
    movimenti_non_riconciliati = await db["estratto_conto_movimenti"].count_documents({
        "data": {"$regex": f"^{anno}"},
        "status": {"$nin": ["deleted", "archived"]},
        "riconciliato": {"$ne": True},
    })
    if movimenti_banca == 0:
        problemi.append(_problema(
            "estratto_conto_mancante",
            "Nessun movimento bancario importato per l'anno",
            "Importare l'estratto conto bancario completo",
        ))
    elif movimenti_non_riconciliati:
        problemi.append(_problema(
            "movimenti_banca_non_riconciliati",
            f"{movimenti_non_riconciliati} movimenti bancari non sono riconciliati",
            "Riconciliare o classificare in nota provvisoria tutti i movimenti",
        ))
    else:
        completamenti.append(f"{movimenti_banca} movimenti bancari tutti riconciliati")

    controlli = len(completamenti) + len(problemi) + len(avvisi)
    score = len(completamenti) / controlli * 100 if controlli else 0
    pronto = len(problemi) == 0
    return {
        "anno": anno,
        "pronto_per_chiusura": pronto,
        "punteggio_completezza": round(score, 1),
        "problemi_bloccanti": problemi,
        "avvisi": avvisi,
        "completamenti": completamenti,
        "registro": {
            "fonte": registro["fonte"],
            "quadratura": registro["quadratura"],
            "completezza": completezza,
            "qualita": qualita,
            "totali": registro["totali"],
        },
        "step_successivo": "bilancino_verifica" if pronto else "risolvere_problemi"
    }


@router.get("/bilancino-verifica/{anno}")
@handle_errors
async def get_bilancino_verifica(anno: int) -> Dict[str, Any]:
    """Espone il risultato solo quando il registro canonico è completo e valido."""
    db = Database.get_db()
    chiusura = await db["chiusure_esercizio"].find_one(
        {"anno": anno}, {"_id": 0, "bilancino": 1, "registro": 1}
    )
    if chiusura and chiusura.get("bilancino"):
        return {
            "anno": anno,
            "disponibile": True,
            "fonte": "snapshot_chiusura",
            "bilancino": chiusura["bilancino"],
            "registro": chiusura.get("registro"),
            "step_successivo": "esercizio_chiuso",
        }

    registro = await _bilancio_verifica_da_registro(db, anno, True)
    completo = registro["completezza_registro"]["completo"]
    ha_scritture = registro["completezza_registro"]["scritture_registrate"] > 0
    if not (registro["quadratura"] and completo and ha_scritture):
        return {
            "anno": anno,
            "disponibile": False,
            "fonte": registro["fonte"],
            "motivo": (
                "Risultato non calcolabile: il registro definitivo deve contenere "
                "scritture valide, complete e quadrate."
            ),
            "registro": {
                "quadratura": registro["quadratura"],
                "completezza": registro["completezza_registro"],
                "qualita": registro["qualita_registro"],
                "totali": registro["totali"],
            },
            "bilancino": None,
            "step_successivo": "completare_registro",
        }

    conti_ricavo = [c for c in registro["conti"] if c.get("tipo") == "ricavo"]
    conti_costo = [c for c in registro["conti"] if c.get("tipo") == "costo"]
    totale_ricavi = round(sum(_saldo_economico(c) for c in conti_ricavo), 2)
    totale_costi = round(sum(_saldo_economico(c) for c in conti_costo), 2)
    risultato = round(totale_ricavi - totale_costi, 2)
    tipo = "utile" if risultato > 0 else "perdita" if risultato < 0 else "pareggio"
    bilancino = {
        "ricavi": {"totale": totale_ricavi, "conti": conti_ricavo},
        "costi": {"totale": totale_costi, "conti": conti_costo},
        "risultato": {
            "utile_perdita": risultato,
            "tipo": tipo,
            "margine_percentuale": round(risultato / totale_ricavi * 100, 1) if totale_ricavi else None,
        },
    }
    return {
        "anno": anno,
        "disponibile": True,
        "fonte": registro["fonte"],
        "bilancino": bilancino,
        "registro": {
            "quadratura": registro["quadratura"],
            "completezza": registro["completezza_registro"],
            "qualita": registro["qualita_registro"],
            "totali": registro["totali"],
        },
        "step_successivo": "conferma_chiusura",
    }


@router.post("/esegui-chiusura")
@handle_errors
async def esegui_chiusura_esercizio(input_data: ChiusuraEsercizioInput) -> Dict[str, Any]:
    """Chiude i conti economici con una scrittura idempotente e quadrata."""
    db = Database.get_db()

    frase_attesa = f"CHIUDI {input_data.anno}"
    if (
        not input_data.conferma_scritture
        or not input_data.conferma_quadrature
        or input_data.conferma_testo != frase_attesa
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Conferma incompleta: verificare le quadrature e digitare "
                f"esattamente '{frase_attesa}'"
            ),
        )

    esistente = await db["chiusure_esercizio"].find_one({"anno": input_data.anno})
    if esistente:
        raise HTTPException(
            status_code=409,
            detail=f"Esercizio {input_data.anno} già chiuso il {esistente.get('created_at', '')[:10]} "
                   f"(chiusura_id={esistente.get('id')})"
        )

    verifica = await verifica_preliminare_chiusura(input_data.anno)
    if not verifica["pronto_per_chiusura"]:
        raise HTTPException(
            status_code=400,
            detail=f"Impossibile procedere: {len(verifica['problemi_bloccanti'])} problemi bloccanti"
        )

    bilancino = await get_bilancino_verifica(input_data.anno)
    if not bilancino.get("disponibile") or not bilancino.get("bilancino"):
        raise HTTPException(status_code=400, detail="Bilancino canonico non disponibile")

    chiusura_id = str(uuid4())
    data_chiusura = f"{input_data.anno}-12-31"
    righe: List[Dict[str, Any]] = []
    for conto in bilancino["bilancino"]["ricavi"]["conti"]:
        saldo = _saldo_economico(conto)
        if saldo > 0:
            righe.append({
                "conto_codice": conto["codice"], "conto_nome": conto["nome"],
                "dare": saldo, "avere": 0, "centro_costo": None,
                "descrizione": "Chiusura conto ricavo",
            })
        elif saldo < 0:
            righe.append({
                "conto_codice": conto["codice"], "conto_nome": conto["nome"],
                "dare": 0, "avere": abs(saldo), "centro_costo": None,
                "descrizione": "Chiusura rettifica ricavo",
            })
    for conto in bilancino["bilancino"]["costi"]["conti"]:
        saldo = _saldo_economico(conto)
        if saldo > 0:
            righe.append({
                "conto_codice": conto["codice"], "conto_nome": conto["nome"],
                "dare": 0, "avere": saldo, "centro_costo": None,
                "descrizione": "Chiusura conto costo",
            })
        elif saldo < 0:
            righe.append({
                "conto_codice": conto["codice"], "conto_nome": conto["nome"],
                "dare": abs(saldo), "avere": 0, "centro_costo": None,
                "descrizione": "Chiusura rettifica costo",
            })

    totale_dare = round(sum(float(r["dare"]) for r in righe), 2)
    totale_avere = round(sum(float(r["avere"]) for r in righe), 2)
    differenza = round(totale_dare - totale_avere, 2)
    if differenza > 0:
        righe.append({
            "conto_codice": "03.03.01", "conto_nome": "Utile d'esercizio",
            "dare": 0, "avere": differenza, "centro_costo": None,
            "descrizione": "Destinazione utile d'esercizio",
        })
    elif differenza < 0:
        righe.append({
            "conto_codice": "03.03.01", "conto_nome": "Perdita d'esercizio",
            "dare": abs(differenza), "avere": 0, "centro_costo": None,
            "descrizione": "Rilevazione perdita d'esercizio",
        })
    if not righe:
        raise HTTPException(status_code=400, detail="Nessun conto economico da chiudere")

    movimento = await registra_scrittura_semplice(
        db,
        {
            "data": data_chiusura,
            "descrizione": f"Chiusura conti economici esercizio {input_data.anno}",
            "tipo": "chiusura_esercizio",
            "anno": input_data.anno,
            "chiusura_id": chiusura_id,
            "importo": abs(bilancino["bilancino"]["risultato"]["utile_perdita"]),
        },
        righe,
        {"tipo": "chiusura_esercizio", "anno": input_data.anno},
    )

    scrittura_chiusura = {
        "id": chiusura_id,
        "anno": input_data.anno,
        "data": data_chiusura,
        "tipo": "chiusura_esercizio",
        "descrizione": f"Chiusura esercizio {input_data.anno}",
        "bilancino": bilancino["bilancino"],
        "registro": bilancino["registro"],
        "fonte": bilancino["fonte"],
        "movimento_contabile_id": movimento["id"],
        "risultato_esercizio": bilancino["bilancino"]["risultato"]["utile_perdita"],
        "tipo_risultato": bilancino["bilancino"]["risultato"]["tipo"],
        "note": input_data.note,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": "sistema"
    }
    await db["chiusure_esercizio"].insert_one(scrittura_chiusura.copy())

    return {
        "success": True,
        "chiusura_id": chiusura_id,
        "movimento_contabile_id": movimento["id"],
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
            "risultato_esercizio": chiusura["risultato_esercizio"],
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
async def apertura_nuovo_esercizio(input_data: AperturaEsercizioInput) -> Dict[str, Any]:
    """
    Apre il nuovo esercizio riportando i saldi dall'anno precedente.
    
    Operazioni:
    1. Verifica che l'anno precedente sia chiuso
    2. Calcola i saldi finali dell'anno precedente
    3. Crea scritture di apertura per il nuovo anno
    4. Riporta:
       - Saldo cassa
       - Saldo banca
       - Debiti fornitori (fatture da pagare)
       - TFR accantonato
       - Assegni in portafoglio
    """
    anno_nuovo = input_data.anno_nuovo
    frase_attesa = f"APRI {anno_nuovo}"
    if input_data.conferma_testo != frase_attesa:
        raise HTTPException(
            status_code=400,
            detail=f"Digitare esattamente '{frase_attesa}' per confermare l'apertura",
        )

    db = Database.get_db()
    anno_precedente = anno_nuovo - 1

    apertura_esistente = await db["aperture_esercizio"].find_one(
        {"anno": anno_nuovo}, {"_id": 0, "id": 1}
    )
    if apertura_esistente:
        raise HTTPException(
            status_code=409,
            detail=f"L'esercizio {anno_nuovo} è già stato aperto",
        )

    # Verifica chiusura anno precedente
    chiusura = await db["chiusure_esercizio"].find_one({"anno": anno_precedente}, {"_id": 0})
    if not chiusura:
        raise HTTPException(
            status_code=400, 
            detail=f"L'esercizio {anno_precedente} non è ancora stato chiuso"
        )
    
    intervallo_prima_nota = {
        "$gte": f"{anno_precedente}-01-01",
        "$lte": f"{anno_precedente}-12-31",
    }
    query_cassa = filtro_saldo_prima_nota("prima_nota_cassa", data=intervallo_prima_nota)
    query_banca = filtro_saldo_prima_nota("prima_nota_banca", data=intervallo_prima_nota)
    saldo_cassa = (
        await aggrega_saldo_prima_nota(
            db, "prima_nota_cassa", query_cassa, anno=anno_precedente
        )
    )["saldo"]
    saldo_banca = (
        await aggrega_saldo_prima_nota(
            db, "prima_nota_banca", query_banca, anno=anno_precedente
        )
    )["saldo"]

    data_chiusura = f"{anno_precedente}-12-31"
    stati_completamente_pagati = [
        stato for stato in STATI_PAGATI if str(stato).lower() not in {"parziale", "partial"}
    ]
    fatture_da_pagare = await db["invoices"].aggregate([
        {"$match": {
            "invoice_date": {"$lte": data_chiusura},
            "status": {"$nin": stati_completamente_pagati + ["deleted", "archived"]},
            "pagato": {"$ne": True},
        }},
        {"$group": {"_id": None, "totale": {"$sum": {
            "$ifNull": ["$importo_residuo", "$total_amount"]
        }}}}
    ]).to_list(1)
    debiti_fornitori = fatture_da_pagare[0]["totale"] if fatture_da_pagare else 0
    
    # 4. Assegni in portafoglio non incassati
    assegni_portafoglio = await db["assegni"].aggregate([
        {"$match": {
            "stato": {"$in": ["emesso", "consegnato"]},
            "incassato": {"$ne": True},
            "$or": [
                {"data_emissione": {"$lte": data_chiusura}},
                {"data": {"$lte": data_chiusura}},
            ],
        }},
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}}
    ]).to_list(1)
    assegni_da_incassare = assegni_portafoglio[0]["totale"] if assegni_portafoglio else 0
    
    # 5. TFR accantonato. Bug corretto 15/07/2026 (stesso audit funzionale
    # del punto 15/07 sopra): il campo si chiama "quota" (canale email/Drive,
    # handler_aggiorna_tfr) o "quota_annuale" (import manuale Libro Unico) —
    # mai "importo". Un singolo documento ha sempre uno solo dei due schemi,
    # quindi sommarli entrambi con $ifNull non rischia doppio conteggio.
    tfr_accantonato = await db["tfr_accantonamenti"].aggregate([
        {"$match": {"anno": {"$lte": anno_precedente}}},
        {"$group": {"_id": None, "totale": {"$sum": {"$add": [
            {"$ifNull": ["$quota", 0]},
            {"$ifNull": ["$quota_annuale", 0]},
        ]}}}}
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
        "fonte_saldi": "prima_nota_canonica",
        "nessuna_scrittura_prima_nota_generata": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["aperture_esercizio"].insert_one(scrittura_apertura.copy())

    # Bug corretto 15/07/2026 (audit funzionale): qui PRIMA venivano creati due
    # movimenti "Riporto" in prima_nota_cassa/banca con il saldo dell'anno
    # precedente. Ma calcola_saldo_anni_precedenti() (prima_nota_module/common.py,
    # la funzione UNICA di saldo §6.4) calcola già il riporto sommando TUTTI i
    # movimenti reali con data < 1/1/anno — è automaticamente cumulativo, non
    # serve alcuna scrittura esplicita. Il movimento "Riporto" si sommava quindi
    # IN PIÙ al saldo già portato avanti dai movimenti reali, raddoppiando il
    # saldo cassa/banca ad ogni apertura d'esercizio (e l'errore si accumulava
    # ad ogni chiusura successiva, restando permanentemente nello storico).
    # Il riepilogo "saldi_riportati" resta comunque salvato in aperture_esercizio
    # per lo storico/audit (letto da GET /saldi-iniziali/{anno}), senza alcuna
    # scrittura contabile duplicata.

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

