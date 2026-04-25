"""
Router TFR - Gestione Trattamento Fine Rapporto
Accantonamento, rivalutazione ISTAT, liquidazione TFR e gestione acconti
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from uuid import uuid4
import logging
import os
from pathlib import Path

from app.database import Database
from app.utils.error_handler import handle_errors

router = APIRouter()
logger = logging.getLogger(__name__)

# Cartella upload buste paga
PAYSLIPS_FOLDER = "/app/uploads/paghe"

# ============================================
# COSTANTI TFR
# ============================================

# Divisore per calcolo quota annuale TFR (art. 2120 c.c.)
TFR_DIVISORE = 13.5

# Rivalutazione minima ISTAT
RIVALUTAZIONE_FISSA = 1.5  # 1.5% fisso

# Aliquota tassazione separata TFR (approssimata al 23% per semplicità)
ALIQUOTA_TFR = 23.0


# ============================================
# MODELLI
# ============================================

class AccantonamentoTFRInput(BaseModel):
    dipendente_id: str
    anno: int
    retribuzione_annua: float
    indice_istat: Optional[float] = 0.0  # percentuale variazione ISTAT


class LiquidazioneTFRInput(BaseModel):
    dipendente_id: str
    data_liquidazione: str  # YYYY-MM-DD
    motivo: str  # "dimissioni", "licenziamento", "pensionamento", "anticipo"
    importo_richiesto: Optional[float] = None  # se anticipo, importo parziale
    note: Optional[str] = ""


# ============================================
# ENDPOINT
# ============================================

@router.get("/situazione/{dipendente_id}")
@handle_errors
async def get_situazione_tfr(dipendente_id: str) -> Dict[str, Any]:
    """
    Restituisce la situazione TFR completa di un dipendente.
    Include storico accantonamenti e rivalutazioni.
    """
    db = Database.get_db()
    
    # Recupera dipendente
    dipendente = await db["dipendenti"].find_one(
        {"id": dipendente_id},
        {"_id": 0}
    )
    
    if not dipendente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # TFR accantonato totale
    tfr_accantonato = float(dipendente.get("tfr_accantonato", 0))
    
    # Storico accantonamenti
    accantonamenti = await db["tfr_accantonamenti"].find(
        {"dipendente_id": dipendente_id},
        {"_id": 0}
    ).sort("anno", 1).to_list(100)
    
    # Storico liquidazioni/anticipi
    liquidazioni = await db["tfr_liquidazioni"].find(
        {"dipendente_id": dipendente_id},
        {"_id": 0}
    ).sort("data", -1).to_list(100)
    
    totale_liquidato = sum(l.get("importo_lordo", 0) for l in liquidazioni)
    
    return {
        "dipendente_id": dipendente_id,
        "dipendente_nome": dipendente.get("nome_completo", ""),
        "tfr_accantonato": round(tfr_accantonato, 2),
        "tfr_disponibile": round(tfr_accantonato - totale_liquidato, 2),
        "totale_liquidato": round(totale_liquidato, 2),
        "num_accantonamenti": len(accantonamenti),
        "accantonamenti": accantonamenti,
        "liquidazioni": liquidazioni
    }


@router.post("/accantonamento")
@handle_errors
async def registra_accantonamento_tfr(input_data: AccantonamentoTFRInput) -> Dict[str, Any]:
    """
    Registra l'accantonamento annuale TFR per un dipendente.
    
    Formula TFR (Art. 2120 Codice Civile):
    - Quota annuale = Retribuzione annua / 13.5
    - Rivalutazione = TFR accumulato precedente * (1.5% + 75% * indice ISTAT)
    - Imposta sostitutiva rivalutazione: 17% (non applicata qui, gestita in sede fiscale)
    
    Args:
        input_data: Dati per il calcolo (dipendente_id, anno, retribuzione_annua, indice_istat)
    
    Returns:
        Dettaglio dell'accantonamento registrato
    """
    db = Database.get_db()
    
    if input_data.retribuzione_annua <= 0:
        raise HTTPException(status_code=400, detail="La retribuzione annua deve essere positiva")
    
    if input_data.anno < 2020 or input_data.anno > 2030:
        raise HTTPException(status_code=400, detail="Anno non valido")
    
    # Recupera dipendente
    dipendente = await db["dipendenti"].find_one(
        {"id": input_data.dipendente_id},
        {"_id": 0}
    )
    
    if not dipendente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # Calcola quota annuale
    quota_annuale = input_data.retribuzione_annua / TFR_DIVISORE
    
    # Calcola rivalutazione sul TFR accumulato precedente
    tfr_precedente = float(dipendente.get("tfr_accantonato", 0))
    # Art. 2120 c.c.: 1.5% fisso + 75% dell'indice ISTAT
    tasso_rivalutazione = (RIVALUTAZIONE_FISSA + input_data.indice_istat * 0.75) / 100
    rivalutazione = tfr_precedente * tasso_rivalutazione
    
    # Totale accantonamento anno
    totale_accantonamento = quota_annuale + rivalutazione
    
    # Nuovo TFR totale
    nuovo_tfr_totale = tfr_precedente + totale_accantonamento
    
    # Registra accantonamento
    accantonamento = {
        "id": str(uuid4()),
        "dipendente_id": input_data.dipendente_id,
        "dipendente_nome": dipendente.get("nome_completo", ""),
        "anno": input_data.anno,
        "retribuzione_annua": input_data.retribuzione_annua,
        "quota_annuale": round(quota_annuale, 2),
        "tfr_precedente": round(tfr_precedente, 2),
        "indice_istat": input_data.indice_istat,
        "tasso_rivalutazione": round(tasso_rivalutazione * 100, 2),
        "rivalutazione": round(rivalutazione, 2),
        "totale_accantonamento": round(totale_accantonamento, 2),
        "nuovo_tfr_totale": round(nuovo_tfr_totale, 2),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["tfr_accantonamenti"].insert_one(accantonamento.copy())
    
    # Aggiorna TFR dipendente
    await db["dipendenti"].update_one(
        {"id": input_data.dipendente_id},
        {"$set": {"tfr_accantonato": round(nuovo_tfr_totale, 2)}}
    )
    
    # Registra movimento contabile
    movimento = {
        "id": str(uuid4()),
        "data": f"{input_data.anno}-12-31",
        "descrizione": f"Accantonamento TFR {input_data.anno} - {dipendente.get('nome_completo', '')}",
        "tipo": "tfr_accantonamento",
        "importo": round(totale_accantonamento, 2),
        "dipendente_id": input_data.dipendente_id,
        "anno": input_data.anno,
        "dettaglio": {
            "quota_annuale": round(quota_annuale, 2),
            "rivalutazione": round(rivalutazione, 2)
        },
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["movimenti_contabili"].insert_one(movimento.copy())
    
    return {
        "success": True,
        "accantonamento_id": accantonamento["id"],
        "messaggio": f"TFR {input_data.anno} accantonato per {dipendente.get('nome_completo', '')}",
        "dettaglio": {
            "quota_annuale": round(quota_annuale, 2),
            "rivalutazione": round(rivalutazione, 2),
            "totale_accantonato": round(totale_accantonamento, 2),
            "nuovo_tfr_totale": round(nuovo_tfr_totale, 2)
        }
    }


@router.post("/liquidazione")
@handle_errors
async def liquida_tfr(input_data: LiquidazioneTFRInput) -> Dict[str, Any]:
    """
    Liquida il TFR a un dipendente (totale o parziale).
    
    Calcola ritenute fiscali con tassazione separata (Art. 19 TUIR).
    L'aliquota media è calcolata come approssimazione semplificata al 23%.
    Per anticipi (max 70% del TFR maturato, Art. 2120 c.c. comma 6-8).
    
    Args:
        input_data: Dati liquidazione (dipendente_id, data, motivo, importo)
    
    Returns:
        Dettaglio della liquidazione con importo lordo, ritenute e netto
    """
    db = Database.get_db()
    
    # Recupera dipendente
    dipendente = await db["dipendenti"].find_one(
        {"id": input_data.dipendente_id},
        {"_id": 0}
    )
    
    if not dipendente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    tfr_disponibile = float(dipendente.get("tfr_accantonato", 0))
    
    # Determina importo da liquidare
    # Per anticipo è obbligatorio indicare un importo richiesto positivo.
    if input_data.motivo == "anticipo":
        if input_data.importo_richiesto is None:
            raise HTTPException(
                status_code=400,
                detail="Per anticipo TFR è obbligatorio specificare un importo richiesto"
            )
        if input_data.importo_richiesto <= 0:
            raise HTTPException(
                status_code=400,
                detail="Per anticipo TFR l'importo richiesto deve essere maggiore di zero"
            )

        max_anticipo = tfr_disponibile * 0.70
        if input_data.importo_richiesto > max_anticipo:
            raise HTTPException(
                status_code=400,
                detail=f"Anticipo TFR max 70%: richiesto €{input_data.importo_richiesto:.2f}, "
                       f"massimo consentito €{max_anticipo:.2f} (Art. 2120 c.c.)"
            )
        importo_lordo = min(input_data.importo_richiesto, tfr_disponibile)
    elif input_data.importo_richiesto is not None:
        if input_data.importo_richiesto <= 0:
            raise HTTPException(
                status_code=400,
                detail="L'importo richiesto deve essere maggiore di zero"
            )
        importo_lordo = min(input_data.importo_richiesto, tfr_disponibile)
    else:
        importo_lordo = tfr_disponibile
    
    if importo_lordo <= 0:
        raise HTTPException(status_code=400, detail="Nessun TFR disponibile da liquidare")
    
    # Calcola ritenute (tassazione separata semplificata)
    ritenute = importo_lordo * ALIQUOTA_TFR / 100
    importo_netto = importo_lordo - ritenute
    
    # Registra liquidazione
    liquidazione = {
        "id": str(uuid4()),
        "dipendente_id": input_data.dipendente_id,
        "dipendente_nome": dipendente.get("nome_completo", ""),
        "data": input_data.data_liquidazione,
        "motivo": input_data.motivo,
        "tfr_precedente": round(tfr_disponibile, 2),
        "importo_lordo": round(importo_lordo, 2),
        "aliquota_ritenuta": ALIQUOTA_TFR,
        "ritenute": round(ritenute, 2),
        "importo_netto": round(importo_netto, 2),
        "tfr_residuo": round(tfr_disponibile - importo_lordo, 2),
        "note": input_data.note,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["tfr_liquidazioni"].insert_one(liquidazione.copy())
    
    # Aggiorna TFR dipendente
    nuovo_tfr = tfr_disponibile - importo_lordo
    await db["dipendenti"].update_one(
        {"id": input_data.dipendente_id},
        {"$set": {"tfr_accantonato": round(nuovo_tfr, 2)}}
    )
    
    # Registra movimenti contabili
    # 1. Utilizzo fondo TFR
    movimento_fondo = {
        "id": str(uuid4()),
        "data": input_data.data_liquidazione,
        "descrizione": f"Liquidazione TFR - {dipendente.get('nome_completo', '')}",
        "tipo": "tfr_liquidazione",
        "importo": round(importo_lordo, 2),
        "dipendente_id": input_data.dipendente_id,
        "motivo": input_data.motivo,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["movimenti_contabili"].insert_one(movimento_fondo.copy())
    
    # 2. Ritenute
    if ritenute > 0:
        movimento_ritenute = {
            "id": str(uuid4()),
            "data": input_data.data_liquidazione,
            "descrizione": f"Ritenute TFR - {dipendente.get('nome_completo', '')}",
            "tipo": "ritenuta_tfr",
            "importo": round(ritenute, 2),
            "dipendente_id": input_data.dipendente_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db["movimenti_contabili"].insert_one(movimento_ritenute.copy())
    
    return {
        "success": True,
        "liquidazione_id": liquidazione["id"],
        "messaggio": f"TFR liquidato per {dipendente.get('nome_completo', '')}",
        "dettaglio": {
            "importo_lordo": round(importo_lordo, 2),
            "ritenute": round(ritenute, 2),
            "importo_netto": round(importo_netto, 2),
            "tfr_residuo": round(nuovo_tfr, 2)
        }
    }


@router.get("/riepilogo-aziendale")
@handle_errors
async def get_riepilogo_tfr_aziendale(anno: int = Query(None)) -> Dict[str, Any]:
    """
    Riepilogo TFR per tutti i dipendenti attivi.
    Utile per il bilancio e pianificazione finanziaria.
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Dipendenti attivi
    dipendenti = await db["dipendenti"].find(
        {"status": {"$in": ["attivo", "active"]}},
        {"_id": 0, "id": 1, "nome_completo": 1, "tfr_accantonato": 1}
    ).to_list(1000)
    
    # Accantonamenti dell'anno
    accantonamenti_anno = await db["tfr_accantonamenti"].aggregate([
        {"$match": {"anno": anno}},
        {"$group": {
            "_id": None,
            "totale_quota": {"$sum": "$quota_annuale"},
            "totale_rivalutazione": {"$sum": "$rivalutazione"},
            "totale_accantonato": {"$sum": "$totale_accantonamento"},
            "num_dipendenti": {"$sum": 1}
        }}
    ]).to_list(1)
    
    # Liquidazioni dell'anno
    liquidazioni_anno = await db["tfr_liquidazioni"].aggregate([
        {"$match": {"data": {"$regex": f"^{anno}"}}},
        {"$group": {
            "_id": None,
            "totale_lordo": {"$sum": "$importo_lordo"},
            "totale_ritenute": {"$sum": "$ritenute"},
            "totale_netto": {"$sum": "$importo_netto"},
            "num_liquidazioni": {"$sum": 1}
        }}
    ]).to_list(1)
    
    # Totale fondo TFR
    totale_fondo = sum(float(d.get("tfr_accantonato", 0)) for d in dipendenti)
    
    # Dettaglio per dipendente
    dettaglio_dipendenti = [
        {
            "dipendente_id": d["id"],
            "nome": d.get("nome_completo", ""),
            "tfr_accantonato": round(float(d.get("tfr_accantonato", 0)), 2)
        }
        for d in dipendenti
        if float(d.get("tfr_accantonato", 0)) > 0
    ]
    
    return {
        "anno": anno,
        "totale_fondo_tfr": round(totale_fondo, 2),
        "num_dipendenti_attivi": len(dipendenti),
        "accantonamenti_anno": {
            "totale_quota": round(accantonamenti_anno[0]["totale_quota"], 2) if accantonamenti_anno else 0,
            "totale_rivalutazione": round(accantonamenti_anno[0]["totale_rivalutazione"], 2) if accantonamenti_anno else 0,
            "totale_accantonato": round(accantonamenti_anno[0]["totale_accantonato"], 2) if accantonamenti_anno else 0,
            "num_dipendenti": accantonamenti_anno[0]["num_dipendenti"] if accantonamenti_anno else 0
        },
        "liquidazioni_anno": {
            "totale_lordo": round(liquidazioni_anno[0]["totale_lordo"], 2) if liquidazioni_anno else 0,
            "totale_ritenute": round(liquidazioni_anno[0]["totale_ritenute"], 2) if liquidazioni_anno else 0,
            "totale_netto": round(liquidazioni_anno[0]["totale_netto"], 2) if liquidazioni_anno else 0,
            "num_liquidazioni": liquidazioni_anno[0]["num_liquidazioni"] if liquidazioni_anno else 0
        },
        "dettaglio_dipendenti": sorted(dettaglio_dipendenti, key=lambda x: x["tfr_accantonato"], reverse=True)
    }


@router.post("/calcola-batch/{anno}")
@handle_errors
async def calcola_tfr_batch(anno: int) -> Dict[str, Any]:
    """
    Calcola TFR per tutti i dipendenti attivi per l'anno specificato.
    Usa i dati dei cedolini per determinare la retribuzione annua.
    """
    db = Database.get_db()
    
    # Dipendenti attivi
    dipendenti = await db["dipendenti"].find(
        {"status": {"$in": ["attivo", "active"]}},
        {"_id": 0}
    ).to_list(1000)
    
    risultati = []
    
    for dip in dipendenti:
        dip_id = dip["id"]
        
        # Verifica se già calcolato per quest'anno
        esistente = await db["tfr_accantonamenti"].find_one({
            "dipendente_id": dip_id,
            "anno": anno
        })
        
        if esistente:
            risultati.append({
                "dipendente": dip.get("nome_completo", ""),
                "stato": "già_calcolato",
                "importo": esistente.get("totale_accantonamento", 0)
            })
            continue
        
        # Calcola retribuzione annua dai cedolini
        cedolini = await db["cedolini"].aggregate([
            {"$match": {"dipendente_id": dip_id, "anno": anno}},
            {"$group": {"_id": None, "totale_lordo": {"$sum": "$lordo"}}}
        ]).to_list(1)
        
        if not cedolini or cedolini[0]["totale_lordo"] == 0:
            # Se non ci sono cedolini, usa una stima dalla prima nota salari
            salari = await db["prima_nota_salari"].aggregate([
                {"$match": {
                    "$or": [
                        {"dipendente_id": dip_id},
                        {"dipendente": dip.get("nome_completo", "")}
                    ],
                    "anno": anno
                }},
                {"$group": {"_id": None, "totale": {"$sum": "$importo_lordo"}}}
            ]).to_list(1)
            
            retribuzione_annua = salari[0]["totale"] if salari else 0
        else:
            retribuzione_annua = cedolini[0]["totale_lordo"]
        
        if retribuzione_annua <= 0:
            risultati.append({
                "dipendente": dip.get("nome_completo", ""),
                "stato": "nessuna_retribuzione",
                "importo": 0
            })
            continue
        
        # Registra accantonamento
        input_data = AccantonamentoTFRInput(
            dipendente_id=dip_id,
            anno=anno,
            retribuzione_annua=retribuzione_annua,
            indice_istat=0  # Può essere aggiornato con indice reale
        )
        
        try:
            result = await registra_accantonamento_tfr(input_data)
            risultati.append({
                "dipendente": dip.get("nome_completo", ""),
                "stato": "calcolato",
                "importo": result["dettaglio"]["totale_accantonato"]
            })
        except Exception as e:
            risultati.append({
                "dipendente": dip.get("nome_completo", ""),
                "stato": "errore",
                "errore": str(e)
            })
    
    totale_accantonato = sum(r.get("importo", 0) for r in risultati if r["stato"] == "calcolato")
    
    return {
        "anno": anno,
        "risultati": risultati,
        "totale_nuovo_accantonato": round(totale_accantonato, 2),
        "num_calcolati": len([r for r in risultati if r["stato"] == "calcolato"]),
        "num_già_esistenti": len([r for r in risultati if r["stato"] == "già_calcolato"]),
        "num_senza_retribuzione": len([r for r in risultati if r["stato"] == "nessuna_retribuzione"])
    }


# ============================================
# GESTIONE ACCONTI (TFR, Ferie, 13ima, 14ima, Prestiti)
# ============================================

class AccontoInput(BaseModel):
    dipendente_id: str
    # Tipi: "stipendio" | "tfr" | "ferie" | "tredicesima" | "quattordicesima" | "prestito"
    tipo: str
    importo: float
    data: str  # YYYY-MM-DD
    note: Optional[str] = ""

    # === CAMPI ESTESI (gestione completa flusso acconti) ===
    # Distinzione tra acconto su lavoro futuro vs su pregresso (lavoro già svolto).
    # Default "su_futuro" perché è il caso standard (anticipo su busta del mese).
    natura_acconto: Optional[str] = "su_futuro"  # "su_futuro" | "su_pregresso"

    # Tipo di bonifico bancario. Ceraldi Group eroga acconti SOLO via banca,
    # mai in contanti. Distinguere standard vs istantaneo aiuta nella
    # riconciliazione (task 2) perché i bonifici standard appaiono in
    # estratto conto in 1-2 giorni lavorativi, gli istantanei lo stesso
    # giorno (anche festivi).
    tipo_bonifico: Optional[str] = "standard"  # "standard" | "istantaneo"

    # Mese/anno del cedolino su cui questo acconto verrà scalato.
    # Per default: stesso mese della data dell'acconto. L'utente può forzare
    # un mese diverso (es. "anticipo dato il 30/04 ma scalato su busta di maggio")
    scalato_su_anno_mese: Optional[str] = None  # formato "YYYY-MM"


class AccontoUpdateInput(BaseModel):
    """Modello per PUT /acconti/{id}: tutti i campi opzionali per update parziale."""
    importo: Optional[float] = None
    data: Optional[str] = None
    tipo: Optional[str] = None
    note: Optional[str] = None
    natura_acconto: Optional[str] = None
    tipo_bonifico: Optional[str] = None
    scalato_su_anno_mese: Optional[str] = None
    stato: Optional[str] = None


# Costanti per validazione (esposte a livello modulo per riuso in altri router)
TIPI_ACCONTO_VALIDI = {
    "stipendio", "tfr", "ferie", "tredicesima", "quattordicesima", "prestito",
}
NATURE_VALIDE = {"su_futuro", "su_pregresso"}
TIPI_BONIFICO_VALIDI = {"standard", "istantaneo"}
STATI_VALIDI = {
    "registrato",            # appena inserito
    "riconciliato_banca",    # collegato a movimento estratto conto
    "scalato_su_cedolino",   # confermato sul cedolino paga
    "annullato",             # rimosso dal flusso (non eliminato per audit)
}


@router.get("/acconti/{dipendente_id}")
@handle_errors
async def get_acconti_dipendente(dipendente_id: str) -> Dict[str, Any]:
    """
    Restituisce tutti gli acconti di un dipendente raggruppati per tipo.
    Include: TFR, Ferie, 13ima, 14ima, Prestiti.
    """
    db = Database.get_db()
    
    # Verifica dipendente
    dipendente = await db["dipendenti"].find_one(
        {"id": dipendente_id},
        {"_id": 0, "id": 1, "nome_completo": 1, "tfr_accantonato": 1}
    )
    
    if not dipendente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # Recupera tutti gli acconti
    acconti = await db["acconti_dipendenti"].find(
        {"dipendente_id": dipendente_id},
        {"_id": 0}
    ).sort("data", -1).to_list(500)
    
    # Raggruppa per tipo
    acconti_per_tipo = {
        "tfr": [],
        "ferie": [],
        "tredicesima": [],
        "quattordicesima": [],
        "prestito": []
    }
    
    totali = {
        "tfr": 0,
        "ferie": 0,
        "tredicesima": 0,
        "quattordicesima": 0,
        "prestito": 0
    }
    
    for acc in acconti:
        tipo = acc.get("tipo", "altro")
        if tipo in acconti_per_tipo:
            acconti_per_tipo[tipo].append(acc)
            totali[tipo] += acc.get("importo", 0)
    
    # Calcola saldi
    tfr_totale = float(dipendente.get("tfr_accantonato", 0))
    
    return {
        "dipendente_id": dipendente_id,
        "dipendente_nome": dipendente.get("nome_completo", ""),
        "tfr_accantonato": round(tfr_totale, 2),
        "tfr_acconti": round(totali["tfr"], 2),
        "tfr_saldo": round(tfr_totale - totali["tfr"], 2),
        "ferie_acconti": round(totali["ferie"], 2),
        "tredicesima_acconti": round(totali["tredicesima"], 2),
        "quattordicesima_acconti": round(totali["quattordicesima"], 2),
        "prestiti_totale": round(totali["prestito"], 2),
        "acconti": acconti_per_tipo,
        "totale_acconti": round(sum(totali.values()), 2)
    }


@router.post("/acconti")
@handle_errors
async def registra_acconto(input_data: AccontoInput) -> Dict[str, Any]:
    """
    Registra un acconto per un dipendente.

    Tipi supportati: stipendio, tfr, ferie, tredicesima, quattordicesima, prestito.

    Nuovi campi:
    - natura_acconto: "su_futuro" (anticipo su busta prossima) | "su_pregresso"
      (ripianamento su lavoro già svolto). Default "su_futuro".
    - tipo_bonifico: "standard" | "istantaneo". Default "standard".
      Tutti gli acconti Ceraldi sono via banca: distinguere standard da
      istantaneo aiuta nella riconciliazione con l'estratto conto (i
      bonifici istantanei arrivano anche in giornata festiva).
    - scalato_su_anno_mese: mese cedolino su cui andrà scalato (es. "2026-04").
      Se non fornito, derivato dalla data dell'acconto.

    Stato lifecycle:
        registrato → riconciliato_banca → scalato_su_cedolino
                  ↘ annullato

    L'acconto viene creato in stato "registrato". Le transizioni di stato
    avvengono via endpoint dedicati (riconcilia, scala-su-cedolino) che
    saranno aggiunti nei task successivi.
    """
    db = Database.get_db()

    # Verifica dipendente
    dipendente = await db["dipendenti"].find_one(
        {"id": input_data.dipendente_id},
        {"_id": 0}
    )

    if not dipendente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")

    # Validazioni di dominio
    if input_data.tipo not in TIPI_ACCONTO_VALIDI:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo non valido. Usa: {', '.join(sorted(TIPI_ACCONTO_VALIDI))}",
        )
    if input_data.importo <= 0:
        raise HTTPException(status_code=400, detail="L'importo deve essere positivo")

    natura = input_data.natura_acconto or "su_futuro"
    if natura not in NATURE_VALIDE:
        raise HTTPException(
            status_code=400,
            detail=f"Natura acconto non valida. Usa: {', '.join(sorted(NATURE_VALIDE))}",
        )

    metodo = input_data.tipo_bonifico or "standard"
    if metodo not in TIPI_BONIFICO_VALIDI:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo bonifico non valido. Usa: {', '.join(sorted(TIPI_BONIFICO_VALIDI))}",
        )

    # Deriva scalato_su_anno_mese da data se non fornito
    scalato_su = input_data.scalato_su_anno_mese
    if not scalato_su:
        try:
            # input_data.data è in formato YYYY-MM-DD
            scalato_su = input_data.data[:7]  # estrae YYYY-MM
        except Exception:
            scalato_su = None

    # Estrae anno/mese numerici dalla data per query rapide su DB
    anno_int = mese_int = None
    try:
        if input_data.data and len(input_data.data) >= 7:
            anno_int = int(input_data.data[:4])
            mese_int = int(input_data.data[5:7])
    except Exception:
        pass

    now_iso = datetime.now(timezone.utc).isoformat()

    # Crea record acconto con schema esteso
    acconto = {
        "id": str(uuid4()),
        "dipendente_id": input_data.dipendente_id,
        "dipendente_nome": dipendente.get("nome_completo", ""),
        "tipo": input_data.tipo,
        "importo": round(input_data.importo, 2),
        "data": input_data.data,
        "anno": anno_int,
        "mese": mese_int,
        "note": input_data.note or "",

        # Nuovi campi
        "natura_acconto": natura,
        "tipo_bonifico": metodo,
        "scalato_su_anno_mese": scalato_su,

        # Stato lifecycle
        "stato": "registrato",
        "movimento_bancario_id": None,
        "riconciliato_il": None,
        "cedolino_id": None,
        "importo_scalato_effettivo": None,

        # Audit
        "source": "manuale",
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    await db["acconti_dipendenti"].insert_one(acconto.copy())

    # Se è un acconto TFR, aggiorna anche il TFR del dipendente (logica preesistente)
    if input_data.tipo == "tfr":
        tfr_attuale = float(dipendente.get("tfr_accantonato", 0))
        nuovo_tfr = max(0, tfr_attuale - input_data.importo)
        await db["dipendenti"].update_one(
            {"id": input_data.dipendente_id},
            {"$set": {"tfr_accantonato": round(nuovo_tfr, 2)}}
        )

        # Registra movimento contabile
        movimento = {
            "id": str(uuid4()),
            "data": input_data.data,
            "descrizione": f"Acconto TFR - {dipendente.get('nome_completo', '')}",
            "tipo": "acconto_tfr",
            "importo": round(input_data.importo, 2),
            "dipendente_id": input_data.dipendente_id,
            "note": input_data.note or "",
            "created_at": now_iso,
        }
        await db["movimenti_contabili"].insert_one(movimento.copy())

    return {
        "success": True,
        "acconto_id": acconto["id"],
        "messaggio": f"Acconto {input_data.tipo} ({natura}) registrato per {dipendente.get('nome_completo', '')}",
        "importo": round(input_data.importo, 2),
        "natura": natura,
        "tipo_bonifico": metodo,
        "scalato_su": scalato_su,
        "stato": "registrato",
    }


@router.put("/acconti/{acconto_id}")
@handle_errors
async def modifica_acconto(acconto_id: str, input_data: dict) -> Dict[str, Any]:
    """Modifica un acconto esistente.

    Accetta tutti i campi del modello esteso. Se viene cambiata la data,
    ricalcola anche `anno`, `mese` numerici e `scalato_su_anno_mese`
    (a meno che quest'ultimo sia stato fornito esplicitamente).
    """
    db = Database.get_db()

    # Trova acconto
    acconto = await db["acconti_dipendenti"].find_one({"id": acconto_id})
    if not acconto:
        raise HTTPException(status_code=404, detail="Acconto non trovato")

    # Prepara aggiornamento
    update_fields: Dict[str, Any] = {}

    if "importo" in input_data and input_data["importo"] is not None:
        vecchio_importo = acconto.get("importo", 0)
        nuovo_importo = float(input_data["importo"])
        if nuovo_importo <= 0:
            raise HTTPException(status_code=400, detail="L'importo deve essere positivo")
        update_fields["importo"] = round(nuovo_importo, 2)

        # Se è un acconto TFR, aggiorna il saldo del dipendente
        if acconto.get("tipo") == "tfr":
            dipendente = await db["dipendenti"].find_one({"id": acconto["dipendente_id"]})
            if dipendente:
                tfr_attuale = float(dipendente.get("tfr_accantonato", 0))
                # Ripristina il vecchio importo e sottrai il nuovo
                nuovo_tfr = tfr_attuale + vecchio_importo - nuovo_importo
                await db["dipendenti"].update_one(
                    {"id": acconto["dipendente_id"]},
                    {"$set": {"tfr_accantonato": round(nuovo_tfr, 2)}}
                )

    if "data" in input_data and input_data["data"]:
        nuova_data = input_data["data"]
        update_fields["data"] = nuova_data
        # Ricalcola anno/mese numerici dal nuovo valore
        try:
            if len(nuova_data) >= 7:
                update_fields["anno"] = int(nuova_data[:4])
                update_fields["mese"] = int(nuova_data[5:7])
        except Exception:
            pass
        # Se l'utente non ha forzato scalato_su_anno_mese, derivalo dalla nuova data
        if "scalato_su_anno_mese" not in input_data:
            update_fields["scalato_su_anno_mese"] = nuova_data[:7]

    if "note" in input_data:
        update_fields["note"] = input_data["note"] or ""

    if "tipo" in input_data and input_data["tipo"]:
        if input_data["tipo"] not in TIPI_ACCONTO_VALIDI:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo non valido. Usa: {', '.join(sorted(TIPI_ACCONTO_VALIDI))}",
            )
        update_fields["tipo"] = input_data["tipo"]

    if "natura_acconto" in input_data and input_data["natura_acconto"]:
        if input_data["natura_acconto"] not in NATURE_VALIDE:
            raise HTTPException(
                status_code=400,
                detail=f"Natura non valida. Usa: {', '.join(sorted(NATURE_VALIDE))}",
            )
        update_fields["natura_acconto"] = input_data["natura_acconto"]

    if "tipo_bonifico" in input_data and input_data["tipo_bonifico"]:
        if input_data["tipo_bonifico"] not in TIPI_BONIFICO_VALIDI:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo bonifico non valido. Usa: {', '.join(sorted(TIPI_BONIFICO_VALIDI))}",
            )
        update_fields["tipo_bonifico"] = input_data["tipo_bonifico"]

    if "scalato_su_anno_mese" in input_data:
        # Accetta None per "rimuovi binding"
        update_fields["scalato_su_anno_mese"] = input_data["scalato_su_anno_mese"]

    if "stato" in input_data and input_data["stato"]:
        if input_data["stato"] not in STATI_VALIDI:
            raise HTTPException(
                status_code=400,
                detail=f"Stato non valido. Usa: {', '.join(sorted(STATI_VALIDI))}",
            )
        update_fields["stato"] = input_data["stato"]

    if update_fields:
        update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db["acconti_dipendenti"].update_one(
            {"id": acconto_id},
            {"$set": update_fields}
        )

    return {
        "success": True,
        "messaggio": f"Acconto {acconto.get('tipo', '')} modificato",
        "acconto_id": acconto_id,
        "campi_aggiornati": sorted(update_fields.keys()),
    }


@router.delete("/acconti/{acconto_id}")
@handle_errors
async def elimina_acconto(acconto_id: str) -> Dict[str, Any]:
    """Elimina un acconto."""
    db = Database.get_db()
    
    # Trova acconto
    acconto = await db["acconti_dipendenti"].find_one({"id": acconto_id})
    if not acconto:
        raise HTTPException(status_code=404, detail="Acconto non trovato")
    
    # Se era un acconto TFR, ripristina il valore
    if acconto.get("tipo") == "tfr":
        dipendente = await db["dipendenti"].find_one({"id": acconto["dipendente_id"]})
        if dipendente:
            tfr_attuale = float(dipendente.get("tfr_accantonato", 0))
            nuovo_tfr = tfr_attuale + acconto.get("importo", 0)
            await db["dipendenti"].update_one(
                {"id": acconto["dipendente_id"]},
                {"$set": {"tfr_accantonato": round(nuovo_tfr, 2)}}
            )
    
    # Elimina acconto
    await db["acconti_dipendenti"].delete_one({"id": acconto_id})
    
    return {
        "success": True,
        "messaggio": f"Acconto {acconto.get('tipo', '')} eliminato"
    }


# ============================================
# RICONCILIAZIONE ACCONTO ↔ MOVIMENTO ESTRATTO CONTO
# ============================================

@router.get("/acconti/{acconto_id}/candidati-banca")
@handle_errors
async def candidati_banca_per_acconto(acconto_id: str) -> Dict[str, Any]:
    """Cerca movimenti dell'estratto conto compatibili con questo acconto.

    Logica di matching:
    - Solo movimenti uscita (importo < 0 o tipo='uscita')
    - Importo uguale a quello dell'acconto (tolleranza ±0.01€)
    - Range data dipende dal tipo_bonifico:
        * 'istantaneo' → stesso giorno della registrazione (±1gg margine)
        * 'standard' → entro 5 giorni dopo la registrazione (skip weekend non
          implementato perché alcuni istituti accreditano comunque il sabato)
    - Esclude movimenti già riconciliati con un altro acconto
    - La descrizione contiene il cognome o il nome del dipendente

    Restituisce candidati ordinati per "score" decrescente (best match prima).
    Score: data esatta=+50, importo esatto=+30, nome in descrizione=+20.
    """
    db = Database.get_db()

    acconto = await db["acconti_dipendenti"].find_one({"id": acconto_id}, {"_id": 0})
    if not acconto:
        raise HTTPException(status_code=404, detail="Acconto non trovato")

    if acconto.get("stato") == "riconciliato_banca":
        raise HTTPException(
            status_code=400,
            detail=f"Acconto già riconciliato. Movimento collegato: {acconto.get('movimento_bancario_id')}",
        )

    importo_target = abs(float(acconto.get("importo", 0)))
    if importo_target <= 0:
        raise HTTPException(status_code=400, detail="Acconto con importo non valido")

    data_acconto_str = acconto.get("data", "")
    try:
        data_acconto = datetime.strptime(data_acconto_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=f"Data acconto non valida: {data_acconto_str}",
        )

    tipo_bonifico = acconto.get("tipo_bonifico") or "standard"

    # Range temporale per la ricerca
    from datetime import timedelta
    if tipo_bonifico == "istantaneo":
        # Bonifico istantaneo: stesso giorno (±1gg margine per fusi orari/contabilità)
        data_min = data_acconto - timedelta(days=1)
        data_max = data_acconto + timedelta(days=1, hours=23, minutes=59)
    else:
        # Bonifico standard: range +0/+5gg dalla data registrazione
        # (alcuni istituti accreditano in giornata, altri D+1, raramente D+2/D+3)
        data_min = data_acconto - timedelta(days=1)
        data_max = data_acconto + timedelta(days=5, hours=23, minutes=59)

    # Recupera nome dipendente per matching descrizione
    dipendente_nome = (acconto.get("dipendente_nome") or "").strip()
    nome_parti = [p for p in dipendente_nome.split() if len(p) >= 3]

    # Query movimenti candidati
    # La collezione canonica è estratto_conto_movimenti.
    # data_contabile_obj è datetime per range query efficienti.
    query: Dict[str, Any] = {
        # Movimento di uscita: tipo='uscita' OR importo<0
        "$or": [
            {"tipo": "uscita"},
            {"importo": {"$lt": 0}},
        ],
        # Importo entro tolleranza ±0.01
        # NB: alcuni movimenti hanno importo negativo (uscite), altri positivo
        # con tipo='uscita' — facciamo confronto su valore assoluto via $expr
        "$and": [
            {"$expr": {
                "$lte": [
                    {"$abs": {"$subtract": [{"$abs": "$importo"}, importo_target]}},
                    0.01,
                ]
            }}
        ],
        # Range data
        "data_contabile_obj": {"$gte": data_min, "$lte": data_max},
        # Esclude movimenti già usati per altri acconti
        "$nor": [
            {"acconto_id": {"$exists": True, "$ne": None, "$ne": ""}},
        ],
    }

    movimenti = await db["estratto_conto_movimenti"].find(
        query, {"_id": 0}
    ).sort("data_contabile_obj", 1).limit(50).to_list(50)

    # Calcolo score per ranking
    candidati = []
    for m in movimenti:
        score = 0
        match_reasons = []

        # Data: esatta = +50, ±1gg = +30, oltre = +10
        try:
            data_mov = m.get("data_contabile_obj")
            if isinstance(data_mov, str):
                data_mov = datetime.fromisoformat(data_mov.replace("Z", ""))
            delta_giorni = abs((data_mov - data_acconto).days) if data_mov else 99
            if delta_giorni == 0:
                score += 50
                match_reasons.append("data esatta")
            elif delta_giorni <= 1:
                score += 30
                match_reasons.append(f"data ±{delta_giorni}gg")
            else:
                score += 10
                match_reasons.append(f"data +{delta_giorni}gg")
        except Exception:
            delta_giorni = None

        # Importo: già filtrato a tolleranza 0.01 → tutti hanno importo esatto
        score += 30
        match_reasons.append("importo esatto")

        # Nome dipendente in descrizione
        descrizione = (m.get("descrizione") or "").upper()
        if nome_parti:
            for parte in nome_parti:
                if parte.upper() in descrizione:
                    score += 20
                    match_reasons.append(f"nome '{parte}' in descrizione")
                    break

        candidati.append({
            "movimento_id": m.get("id"),
            "data": m.get("data") or (m.get("data_contabile_obj").strftime("%Y-%m-%d") if m.get("data_contabile_obj") else None),
            "descrizione": m.get("descrizione", ""),
            "importo": m.get("importo"),
            "categoria": m.get("categoria"),
            "fornitore": m.get("fornitore"),
            "score": score,
            "match_reasons": match_reasons,
            "delta_giorni": delta_giorni,
        })

    # Ordina per score desc
    candidati.sort(key=lambda c: c["score"], reverse=True)

    return {
        "success": True,
        "acconto": {
            "id": acconto.get("id"),
            "dipendente_nome": dipendente_nome,
            "importo": acconto.get("importo"),
            "data": data_acconto_str,
            "tipo_bonifico": tipo_bonifico,
        },
        "ricerca": {
            "data_min": data_min.strftime("%Y-%m-%d"),
            "data_max": data_max.strftime("%Y-%m-%d"),
            "tolleranza_importo": 0.01,
        },
        "totale_candidati": len(candidati),
        "candidati": candidati,
    }


class RiconciliaBancaInput(BaseModel):
    movimento_id: str


@router.post("/acconti/{acconto_id}/riconcilia-banca")
@handle_errors
async def riconcilia_acconto_banca(
    acconto_id: str, payload: RiconciliaBancaInput
) -> Dict[str, Any]:
    """Collega manualmente un acconto a un movimento dell'estratto conto.

    Effetti:
    - Acconto: stato='riconciliato_banca', movimento_bancario_id=<id>,
      riconciliato_il=<now>
    - Movimento: acconto_id=<id> (per evitare doppia riconciliazione)
    """
    db = Database.get_db()

    acconto = await db["acconti_dipendenti"].find_one({"id": acconto_id})
    if not acconto:
        raise HTTPException(status_code=404, detail="Acconto non trovato")

    if acconto.get("stato") == "riconciliato_banca":
        raise HTTPException(
            status_code=400,
            detail="Acconto già riconciliato. Annulla prima la riconciliazione esistente.",
        )

    movimento = await db["estratto_conto_movimenti"].find_one(
        {"id": payload.movimento_id}, {"_id": 0}
    )
    if not movimento:
        raise HTTPException(status_code=404, detail="Movimento estratto conto non trovato")

    if movimento.get("acconto_id"):
        raise HTTPException(
            status_code=409,
            detail=f"Movimento già collegato all'acconto {movimento.get('acconto_id')}",
        )

    now_iso = datetime.now(timezone.utc).isoformat()

    # Aggiorna acconto
    await db["acconti_dipendenti"].update_one(
        {"id": acconto_id},
        {"$set": {
            "movimento_bancario_id": payload.movimento_id,
            "riconciliato_il": now_iso,
            "stato": "riconciliato_banca",
            "updated_at": now_iso,
        }},
    )

    # Aggiorna movimento (link inverso per anti-doppia-riconciliazione)
    await db["estratto_conto_movimenti"].update_one(
        {"id": payload.movimento_id},
        {"$set": {
            "acconto_id": acconto_id,
            "categoria_acconto": acconto.get("tipo", "stipendio"),
            "dipendente_nome": acconto.get("dipendente_nome", ""),
            "updated_at": now_iso,
        }},
    )

    return {
        "success": True,
        "messaggio": f"Acconto riconciliato con movimento del {movimento.get('data', '?')}",
        "acconto_id": acconto_id,
        "movimento_id": payload.movimento_id,
        "stato": "riconciliato_banca",
    }


@router.post("/acconti/{acconto_id}/annulla-riconciliazione-banca")
@handle_errors
async def annulla_riconciliazione_banca(acconto_id: str) -> Dict[str, Any]:
    """Annulla la riconciliazione bancaria di un acconto.

    Riporta lo stato a 'registrato' e rimuove il link sul movimento.
    Utile in caso di errore di abbinamento.
    """
    db = Database.get_db()

    acconto = await db["acconti_dipendenti"].find_one({"id": acconto_id})
    if not acconto:
        raise HTTPException(status_code=404, detail="Acconto non trovato")

    if acconto.get("stato") != "riconciliato_banca":
        raise HTTPException(
            status_code=400,
            detail=f"Acconto non in stato riconciliato_banca (stato attuale: {acconto.get('stato')})",
        )

    movimento_id = acconto.get("movimento_bancario_id")
    now_iso = datetime.now(timezone.utc).isoformat()

    # Rimuovi link da acconto
    await db["acconti_dipendenti"].update_one(
        {"id": acconto_id},
        {
            "$set": {"stato": "registrato", "updated_at": now_iso},
            "$unset": {"movimento_bancario_id": "", "riconciliato_il": ""},
        },
    )

    # Rimuovi link da movimento
    if movimento_id:
        await db["estratto_conto_movimenti"].update_one(
            {"id": movimento_id},
            {
                "$unset": {"acconto_id": "", "categoria_acconto": ""},
                "$set": {"updated_at": now_iso},
            },
        )

    return {
        "success": True,
        "messaggio": "Riconciliazione bancaria annullata",
        "acconto_id": acconto_id,
        "movimento_id": movimento_id,
        "stato": "registrato",
    }


@router.get("/parse-payslips")
@handle_errors
async def parse_payslips_for_tfr() -> Dict[str, Any]:
    """
    Analizza i PDF delle buste paga per estrarre i dati TFR.
    Legge dalla cartella /app/uploads/paghe.
    """
    try:
        from app.services.payslip_pdf_parser import parse_all_payslips
        
        if not os.path.exists(PAYSLIPS_FOLDER):
            return {
                "success": False,
                "error": f"Cartella {PAYSLIPS_FOLDER} non trovata",
                "data": []
            }
        
        # Conta PDF disponibili
        pdf_files = list(Path(PAYSLIPS_FOLDER).glob("Libro*.pdf"))
        
        if not pdf_files:
            return {
                "success": False,
                "error": "Nessun file 'Libro Unico' trovato nella cartella",
                "data": []
            }
        
        # Parse tutti i PDF
        data = parse_all_payslips(PAYSLIPS_FOLDER)
        
        return {
            "success": True,
            "num_pdf_analizzati": len(pdf_files),
            "num_dipendenti_trovati": len(data),
            "dipendenti": data
        }
        
    except Exception as e:
        logger.error(f"Errore parsing buste paga: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": []
        }


@router.get("/storico-tfr/{dipendente_id}")
@handle_errors
async def get_storico_tfr(dipendente_id: str) -> Dict[str, Any]:
    """
    Restituisce lo storico completo del TFR di un dipendente.
    Include: accantonamenti, acconti, variazioni.
    """
    db = Database.get_db()
    
    # Verifica dipendente
    dipendente = await db["dipendenti"].find_one(
        {"id": dipendente_id},
        {"_id": 0}
    )
    
    if not dipendente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # Accantonamenti
    accantonamenti = await db["tfr_accantonamenti"].find(
        {"dipendente_id": dipendente_id},
        {"_id": 0}
    ).sort("anno", -1).to_list(100)
    
    # Liquidazioni
    liquidazioni = await db["tfr_liquidazioni"].find(
        {"dipendente_id": dipendente_id},
        {"_id": 0}
    ).sort("data", -1).to_list(100)
    
    # Acconti TFR
    acconti_tfr = await db["acconti_dipendenti"].find(
        {"dipendente_id": dipendente_id, "tipo": "tfr"},
        {"_id": 0}
    ).sort("data", -1).to_list(100)
    
    # Calcola totali
    totale_accantonato = sum(a.get("totale_accantonamento", 0) for a in accantonamenti)
    totale_liquidato = sum(l.get("importo_lordo", 0) for l in liquidazioni)
    totale_acconti = sum(acc.get("importo", 0) for acc in acconti_tfr)
    
    tfr_attuale = float(dipendente.get("tfr_accantonato", 0))
    
    return {
        "dipendente_id": dipendente_id,
        "dipendente_nome": dipendente.get("nome_completo", ""),
        "tfr_attuale": round(tfr_attuale, 2),
        "totale_accantonato": round(totale_accantonato, 2),
        "totale_liquidato": round(totale_liquidato, 2),
        "totale_acconti": round(totale_acconti, 2),
        "accantonamenti": accantonamenti,
        "liquidazioni": liquidazioni,
        "acconti": acconti_tfr
    }

