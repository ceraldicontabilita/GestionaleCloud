"""
Router Cedolini - Gestione semplificata buste paga
Calcola stima cedolino da ore/giorni lavoro e costo azienda totale
"""
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================
# COSTANTI CONTRIBUTIVE 2025
# ============================================

# Contributi INPS a carico azienda (circa 30% del lordo)
INPS_AZIENDA_PERCENT = 30.0

# Contributi INPS a carico dipendente (circa 9.19%)
INPS_DIPENDENTE_PERCENT = 9.19

# INAIL (varia per settore, ristorazione circa 1.5-3%)
INAIL_PERCENT = 2.0

# TFR mensile (retribuzione annua / 13.5 / 12)
TFR_DIVISORE = 13.5

# Aliquote IRPEF 2025 (scaglioni)
SCAGLIONI_IRPEF = [
    (28000, 0.23),   # Fino a 28.000€ -> 23%
    (50000, 0.35),   # Da 28.001 a 50.000€ -> 35%
    (float('inf'), 0.43)  # Oltre 50.000€ -> 43%
]

# Detrazioni lavoro dipendente 2025 (semplificate)
DETRAZIONE_BASE = 1955  # Annuale per redditi fino a 15.000€


# ============================================
# MODELLI
# ============================================

class CedolinoInput(BaseModel):
    dipendente_id: str
    mese: int  # 1-12
    anno: int
    ore_lavorate: Optional[float] = None  # Per paga oraria
    giorni_lavorati: Optional[float] = None  # Per paga giornaliera
    paga_oraria: Optional[float] = None  # Override paga oraria dal form
    straordinari_ore: float = 0
    festivita_ore: float = 0
    ore_domenicali: float = 0  # Ore lavorate di domenica (maggiorazione)
    ore_malattia: float = 0  # Ore in malattia
    giorni_malattia: int = 0  # Giorni di malattia
    assenze_ore: float = 0  # Ore di assenza non retribuite
    malattia_giorni: float = 0  # Deprecated - usa giorni_malattia
    ferie_giorni: float = 0
    note: str = ""


class CedolinoStima(BaseModel):
    dipendente_id: str
    dipendente_nome: str
    mese: int
    anno: int
    # Lordo
    retribuzione_base: float
    straordinari: float
    festivita: float
    maggiorazione_domenicale: float = 0
    indennita_malattia: float = 0
    lordo_totale: float
    # Trattenute dipendente
    inps_dipendente: float
    irpef_lorda: float
    detrazioni: float
    irpef_netta: float
    totale_trattenute: float
    # Netto
    netto_in_busta: float
    # Costo azienda
    inps_azienda: float
    inail: float
    tfr_mese: float
    costo_totale_azienda: float
    # Info
    ore_lavorate: float
    giorni_lavorati: float
    paga_oraria_usata: float = 0


# ============================================
# FUNZIONI DI CALCOLO
# ============================================

def calcola_irpef_annua(reddito_annuo: float) -> float:
    """Calcola IRPEF annua per scaglioni"""
    irpef = 0
    reddito_residuo = reddito_annuo
    limite_precedente = 0
    
    for limite, aliquota in SCAGLIONI_IRPEF:
        if reddito_residuo <= 0:
            break
        
        scaglione = min(reddito_residuo, limite - limite_precedente)
        irpef += scaglione * aliquota
        reddito_residuo -= scaglione
        limite_precedente = limite
    
    return irpef


def calcola_detrazioni_lavoro(reddito_annuo: float) -> float:
    """Calcola detrazioni lavoro dipendente (Art. 13 TUIR, riforma 2024-2025)"""
    if reddito_annuo <= 15000:
        return DETRAZIONE_BASE  # 1955
    elif reddito_annuo <= 28000:
        return 1910 + 1190 * (28000 - reddito_annuo) / 13000
    elif reddito_annuo <= 50000:
        return 1190 * (50000 - reddito_annuo) / 22000
    else:
        return 0


# ============================================
# ENDPOINT
# ============================================

@router.post("")
@handle_errors
async def crea_cedolino(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea un cedolino manuale."""
    db = Database.get_db()
    
    required = ["employee_id", "mese", "anno", "netto"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Campo obbligatorio mancante: {field}")
    
    cedolino = {
        "id": str(uuid.uuid4()),
        "employee_id": data["employee_id"],
        "mese": data["mese"],
        "anno": int(data["anno"]),
        "netto": float(data["netto"]),
        "data_emissione": data.get("data_emissione", datetime.now(timezone.utc).isoformat()[:10]),
        "note": data.get("note", ""),
        "source": "manual",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["cedolini"].insert_one(cedolino.copy())
    return {"success": True, "message": "Cedolino creato", "id": cedolino["id"]}


@router.get("")
@handle_errors
async def lista_cedolini(
    anno: Optional[int] = None,
    mese: Optional[int] = None,
    dipendente_id: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    solo_completi: bool = False
) -> Dict[str, Any]:
    """
    Lista tutti i cedolini con filtri opzionali e paginazione.
    
    Args:
        anno: Filtra per anno
        mese: Filtra per mese (1-12)
        dipendente_id: Filtra per dipendente
        limit: Numero massimo di risultati (default 100, max 500)
        skip: Offset per paginazione
        solo_completi: Se True, esclude cedolini con dati incompleti (solo netto)
    """
    db = Database.get_db()
    
    # Limita il massimo a 500
    limit = min(limit, 500)
    
    query = {}
    if anno:
        # Gestisce sia anno come int (2026) sia come stringa ("2026")
        query["$or"] = [{"anno": anno}, {"anno": str(anno)}]
    if mese:
        query["mese"] = mese
    if dipendente_id:
        query["dipendente_id"] = dipendente_id
    
    # Filtra cedolini incompleti se richiesto
    if solo_completi:
        query["$or"] = [
            {"lordo": {"$exists": True, "$gt": 0}},
            {"lordo_totale": {"$exists": True, "$gt": 0}}
        ]
    
    cedolini = await db["cedolini"].find(
        query,
        {"_id": 0, "pdf_data": 0}
    ).sort([("anno", -1), ("mese", -1)]).skip(skip).limit(limit).to_list(limit)
    
    total = await db["cedolini"].count_documents(query)
    
    # Conta cedolini incompleti (solo netto)
    incompleti_query = {
        "lordo": {"$exists": False},
        "lordo_totale": {"$exists": False},
        "netto": {"$exists": True}
    }
    cedolini_incompleti = await db["cedolini"].count_documents(incompleti_query)
    
    return {
        "cedolini": cedolini,
        "total": total,
        "cedolini_incompleti": cedolini_incompleti,
        "pagination": {
            "skip": skip,
            "limit": limit,
            "has_more": (skip + limit) < total
        },
        "filters": {"anno": anno, "mese": mese, "dipendente_id": dipendente_id, "solo_completi": solo_completi}
    }


@router.get("/incompleti")
@handle_errors
async def lista_cedolini_incompleti() -> Dict[str, Any]:
    """
    Lista cedolini con dati incompleti (solo campo netto).
    Utile per identificare record da correggere o completare.
    """
    db = Database.get_db()
    
    # Query per cedolini che hanno solo netto (senza lordo)
    query = {
        "$and": [
            {"netto": {"$exists": True, "$gt": 0}},
            {"$or": [
                {"lordo": {"$exists": False}},
                {"lordo": None},
                {"lordo": 0}
            ]},
            {"$or": [
                {"lordo_totale": {"$exists": False}},
                {"lordo_totale": None},
                {"lordo_totale": 0}
            ]}
        ]
    }
    
    cedolini = await db["cedolini"].find(
        query,
        {"_id": 0, "pdf_data": 0}
    ).sort([("anno", -1), ("mese", -1)]).to_list(100)
    
    total = await db["cedolini"].count_documents(query)
    
    # Calcola statistiche
    totale_netto = sum(c.get("netto", 0) for c in cedolini)
    
    return {
        "cedolini_incompleti": cedolini,
        "total": total,
        "totale_netto": totale_netto,
        "nota": "Questi cedolini hanno solo il campo 'netto' popolato. Potrebbero derivare da importazioni PDF parziali.",
        "suggerimento": "Verificare i PDF originali o completare manualmente i dati mancanti (lordo, trattenute, contributi)"
    }


@router.post("/incompleti/{cedolino_id}/completa")
@handle_errors
async def completa_cedolino_incompleto(
    cedolino_id: str,
    lordo: float,
    inps_dipendente: Optional[float] = None,
    irpef: Optional[float] = None
) -> Dict[str, Any]:
    """
    Completa un cedolino incompleto con i dati mancanti.
    Calcola automaticamente le trattenute se non fornite.
    """
    db = Database.get_db()
    
    cedolino = await db["cedolini"].find_one({"id": cedolino_id})
    if not cedolino:
        raise HTTPException(status_code=404, detail="Cedolino non trovato")
    
    netto_attuale = cedolino.get("netto", 0)
    
    # Calcola trattenute se non fornite (stima)
    if inps_dipendente is None:
        inps_dipendente = lordo * (INPS_DIPENDENTE_PERCENT / 100)
    
    if irpef is None:
        # Stima IRPEF dal lordo-inps
        imponibile = lordo - inps_dipendente
        irpef = imponibile * 0.23  # Aliquota base semplificata
    
    # Calcola netto teorico
    netto_calcolato = lordo - inps_dipendente - irpef
    
    update_data = {
        "lordo": lordo,
        "lordo_totale": lordo,
        "inps_dipendente": inps_dipendente,
        "irpef": irpef,
        "netto_calcolato": netto_calcolato,
        "completato_manualmente": True,
        "data_completamento": datetime.now(timezone.utc).isoformat()
    }
    
    await db["cedolini"].update_one(
        {"id": cedolino_id},
        {"$set": update_data}
    )
    
    return {
        "success": True,
        "cedolino_id": cedolino_id,
        "dati_aggiornati": update_data,
        "differenza_netto": netto_calcolato - netto_attuale if netto_attuale else None
    }



@router.post("/stima", response_model=CedolinoStima)
@handle_errors
async def calcola_stima_cedolino(input_data: CedolinoInput) -> CedolinoStima:
    """
    Calcola stima cedolino da ore/giorni lavorati.
    Restituisce netto dipendente e costo totale azienda.
    """
    db = Database.get_db()
    
    # Recupera dati dipendente
    dipendente = await db["employees"].find_one(
        {"id": input_data.dipendente_id},
        {"_id": 0}
    )
    
    if not dipendente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # Recupera contratto attivo
    contratto = await db["employee_contracts"].find_one(
        {"dipendente_id": input_data.dipendente_id, "attivo": True},
        {"_id": 0}
    )
    
    # Dati retributivi (da contratto o default, con possibile override)
    if input_data.paga_oraria and input_data.paga_oraria > 0:
        paga_oraria = input_data.paga_oraria
    elif contratto:
        paga_oraria = float(contratto.get("paga_oraria", dipendente.get("stipendio_orario", 10.0)))
    else:
        paga_oraria = float(dipendente.get("stipendio_orario", 10.0))
    
    paga_giornaliera = float(contratto.get("paga_giornaliera", paga_oraria * 8)) if contratto else paga_oraria * 8
    # ore_settimanali disponibile per calcoli futuri se necessario
    
    # Calcolo ore/giorni
    if input_data.ore_lavorate:
        ore_lavorate = input_data.ore_lavorate
        giorni_lavorati = ore_lavorate / 8
        retribuzione_base = ore_lavorate * paga_oraria
    elif input_data.giorni_lavorati:
        giorni_lavorati = input_data.giorni_lavorati
        ore_lavorate = giorni_lavorati * 8
        retribuzione_base = giorni_lavorati * paga_giornaliera
    else:
        # Default: mese pieno (22 giorni)
        giorni_lavorati = 22
        ore_lavorate = 176
        retribuzione_base = giorni_lavorati * paga_giornaliera
    
    # Deduzione ore assenza
    if input_data.assenze_ore > 0:
        deduzione_assenze = input_data.assenze_ore * paga_oraria
        retribuzione_base = max(0, retribuzione_base - deduzione_assenze)
    
    # Straordinari (maggiorazione 25%)
    straordinari = input_data.straordinari_ore * paga_oraria * 1.25
    
    # Festività (maggiorazione 50%)
    festivita = input_data.festivita_ore * paga_oraria * 1.50
    
    # Maggiorazione domenicale (15% extra)
    maggiorazione_domenicale = input_data.ore_domenicali * paga_oraria * 0.15
    
    # Indennità malattia (calcolo semplificato)
    # Primi 3 giorni: 100% a carico azienda
    # Dal 4° al 20° giorno: 75%
    # Oltre 20 giorni: 66%
    indennita_malattia = 0
    giorni_mal = input_data.giorni_malattia or int(input_data.malattia_giorni)
    if giorni_mal > 0:
        ore_per_giorno = 8
        # ore_malattia usate per tracciamento, calcolo usa giorni
        
        # Calcolo indennità per fasce
        giorni_100 = min(giorni_mal, 3)
        giorni_75 = min(max(0, giorni_mal - 3), 17)  # Dal 4° al 20°
        giorni_66 = max(0, giorni_mal - 20)  # Oltre il 20°
        
        indennita_malattia = (
            giorni_100 * ore_per_giorno * paga_oraria * 1.00 +
            giorni_75 * ore_per_giorno * paga_oraria * 0.75 +
            giorni_66 * ore_per_giorno * paga_oraria * 0.66
        )
    
    # Lordo totale
    lordo_totale = retribuzione_base + straordinari + festivita + maggiorazione_domenicale + indennita_malattia
    
    # --- TRATTENUTE DIPENDENTE ---
    
    # INPS dipendente (9.19% del lordo)
    inps_dipendente = lordo_totale * INPS_DIPENDENTE_PERCENT / 100
    
    # Imponibile fiscale
    imponibile_fiscale = lordo_totale - inps_dipendente
    
    # IRPEF (annualizzata e poi mensile)
    reddito_annuo_stimato = imponibile_fiscale * 12
    irpef_annua = calcola_irpef_annua(reddito_annuo_stimato)
    detrazioni_annue = calcola_detrazioni_lavoro(reddito_annuo_stimato)
    irpef_netta_annua = max(0, irpef_annua - detrazioni_annue)
    
    irpef_lorda = round(irpef_annua / 12, 2)
    detrazioni = round(detrazioni_annue / 12, 2)
    irpef_netta = round(irpef_netta_annua / 12, 2)
    
    # Totale trattenute
    totale_trattenute = inps_dipendente + irpef_netta
    
    # NETTO IN BUSTA
    netto_in_busta = lordo_totale - totale_trattenute
    
    # --- COSTO AZIENDA ---
    
    # INPS azienda (circa 30%)
    inps_azienda = lordo_totale * INPS_AZIENDA_PERCENT / 100
    
    # INAIL
    inail = lordo_totale * INAIL_PERCENT / 100
    
    # TFR mensile
    tfr_mese = lordo_totale / TFR_DIVISORE
    
    # COSTO TOTALE AZIENDA
    costo_totale_azienda = lordo_totale + inps_azienda + inail + tfr_mese
    
    return CedolinoStima(
        dipendente_id=input_data.dipendente_id,
        dipendente_nome=dipendente.get("nome_completo", ""),
        mese=input_data.mese,
        anno=input_data.anno,
        retribuzione_base=round(retribuzione_base, 2),
        straordinari=round(straordinari, 2),
        festivita=round(festivita, 2),
        maggiorazione_domenicale=round(maggiorazione_domenicale, 2),
        indennita_malattia=round(indennita_malattia, 2),
        lordo_totale=round(lordo_totale, 2),
        inps_dipendente=round(inps_dipendente, 2),
        irpef_lorda=irpef_lorda,
        detrazioni=detrazioni,
        irpef_netta=irpef_netta,
        totale_trattenute=round(totale_trattenute, 2),
        netto_in_busta=round(netto_in_busta, 2),
        inps_azienda=round(inps_azienda, 2),
        inail=round(inail, 2),
        tfr_mese=round(tfr_mese, 2),
        costo_totale_azienda=round(costo_totale_azienda, 2),
        ore_lavorate=round(ore_lavorate, 1),
        giorni_lavorati=round(giorni_lavorati, 1),
        paga_oraria_usata=round(paga_oraria, 2)
    )


@router.post("/conferma")
@handle_errors
async def conferma_cedolino(stima: CedolinoStima) -> Dict[str, Any]:
    """
    Conferma cedolino e lo registra in contabilità.
    Crea movimento in prima_nota_salari.
    """
    db = Database.get_db()
    
    # Crea record cedolino
    cedolino = {
        "id": str(uuid.uuid4()),
        "dipendente_id": stima.dipendente_id,
        "dipendente_nome": stima.dipendente_nome,
        "mese": stima.mese,
        "anno": stima.anno,
        "periodo": f"{stima.anno}-{str(stima.mese).zfill(2)}",
        # Importi
        "lordo": stima.lordo_totale,
        "netto": stima.netto_in_busta,
        "inps_dipendente": stima.inps_dipendente,
        "irpef": stima.irpef_netta,
        "inps_azienda": stima.inps_azienda,
        "inail": stima.inail,
        "tfr": stima.tfr_mese,
        "costo_azienda": stima.costo_totale_azienda,
        # Dettagli
        "ore_lavorate": stima.ore_lavorate,
        "giorni_lavorati": stima.giorni_lavorati,
        "straordinari": stima.straordinari,
        "festivita": stima.festivita,
        # Stato
        "stato": "confermato",
        "pagato": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["cedolini"].insert_one(cedolino.copy())
    
    # Registra in prima nota salari
    movimento_salario = {
        "id": str(uuid.uuid4()),
        "cedolino_id": cedolino["id"],
        "data": f"{stima.anno}-{str(stima.mese).zfill(2)}-28",  # Fine mese
        "dipendente": stima.dipendente_nome,
        "descrizione": f"Stipendio {stima.mese}/{stima.anno} - {stima.dipendente_nome}",
        "importo_lordo": stima.lordo_totale,
        "importo_netto": stima.netto_in_busta,
        "ritenute_inps": stima.inps_dipendente,
        "ritenute_irpef": stima.irpef_netta,
        "contributi_azienda": stima.inps_azienda + stima.inail,
        "tfr_accantonato": stima.tfr_mese,
        "costo_totale": stima.costo_totale_azienda,
        "tipo": "stipendio",
        "anno": stima.anno,
        "mese": stima.mese,
        "pagato": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["prima_nota_salari"].insert_one(movimento_salario.copy())
    
    # Aggiorna TFR dipendente
    await db["employees"].update_one(
        {"id": stima.dipendente_id},
        {"$inc": {"tfr_accantonato": stima.tfr_mese}}
    )
    
    return {
        "success": True,
        "cedolino_id": cedolino["id"],
        "movimento_id": movimento_salario["id"],
        "messaggio": f"Cedolino {stima.mese}/{stima.anno} confermato per {stima.dipendente_nome}",
        "riepilogo": {
            "netto_dipendente": stima.netto_in_busta,
            "costo_azienda": stima.costo_totale_azienda,
            "tfr_accantonato": stima.tfr_mese
        }
    }


@router.get("/lista/{anno}/{mese}")
@handle_errors
async def lista_cedolini_mese(anno: int, mese: int) -> List[Dict[str, Any]]:
    """Lista cedolini per mese con informazioni sui bonifici associati"""
    db = Database.get_db()
    
    cedolini = await db["cedolini"].find(
        {"anno": anno, "mese": mese},
        {"_id": 0}
    ).to_list(1000)
    
    # Arricchisci con info bonifici dalla prima_nota_salari
    for c in cedolini:
        dipendente_id = c.get("dipendente_id")
        if dipendente_id:
            # Cerca nella prima nota salari se c'è un bonifico associato per questo dipendente/mese
            prima_nota = await db["prima_nota_salari"].find_one(
                {
                    "dipendente_id": dipendente_id,
                    "anno": anno,
                    "mese": mese,
                    "bonifico_id": {"$exists": True, "$nin": [None, ""]}
                },
                {"_id": 0, "bonifico_id": 1, "bonifico_associato": 1}
            )
            if prima_nota and prima_nota.get("bonifico_id"):
                c["bonifico_id"] = prima_nota.get("bonifico_id")
                c["salario_associato"] = True
    
    return cedolini


@router.get("/dipendente/{dipendente_id}")
@handle_errors
async def cedolini_dipendente(dipendente_id: str, anno: Optional[int] = None) -> Dict[str, Any]:
    """
    Lista tutti i cedolini/buste paga di un dipendente.
    Se anno è specificato, filtra per quell'anno.
    """
    db = Database.get_db()
    
    # Verifica dipendente
    dipendente = await db["employees"].find_one({"id": dipendente_id}, {"_id": 0, "nome_completo": 1, "nome": 1})
    if not dipendente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    nome = dipendente.get("nome_completo") or dipendente.get("nome", "")
    
    # Query cedolini
    query = {"dipendente_id": dipendente_id}
    if anno:
        query["$or"] = [{"anno": anno}, {"anno": str(anno)}]
    
    cedolini = await db["cedolini"].find(
        query,
        {"_id": 0, "pdf_data": 0}
    ).sort([("anno", -1), ("mese", -1)]).to_list(500)
    
    # Calcola totali
    totale_lordo = sum(c.get("lordo", 0) for c in cedolini)
    totale_netto = sum(c.get("netto", 0) for c in cedolini)
    
    # Arricchisci con info bonifici
    for c in cedolini:
        prima_nota = await db["prima_nota_salari"].find_one(
            {
                "dipendente_id": dipendente_id,
                "anno": c.get("anno"),
                "mese": c.get("mese"),
                "bonifico_id": {"$exists": True, "$nin": [None, ""]}
            },
            {"_id": 0, "bonifico_id": 1}
        )
        if prima_nota and prima_nota.get("bonifico_id"):
            c["pagato"] = True
            c["bonifico_id"] = prima_nota.get("bonifico_id")
    
    return {
        "dipendente_id": dipendente_id,
        "dipendente_nome": nome,
        "totale_cedolini": len(cedolini),
        "totale_lordo": round(totale_lordo, 2),
        "totale_netto": round(totale_netto, 2),
        "cedolini": cedolini
    }



@router.get("/riepilogo-mensile/{anno}/{mese}")
@handle_errors
async def riepilogo_mensile(anno: int, mese: int) -> Dict[str, Any]:
    """Riepilogo costi del personale per mese.
    
    Gestisce cedolini con dati completi (da parser PDF) e cedolini
    con solo importo netto (da import Excel paghe/bonifici).
    """
    db = Database.get_db()
    
    # Usa $ifNull per gestire campi mancanti nei cedolini importati da Excel
    # Se lordo non esiste, usa netto come approssimazione
    pipeline = [
        {"$match": {"anno": anno, "mese": mese}},
        {"$group": {
            "_id": None,
            "totale_lordo": {"$sum": {"$ifNull": ["$lordo", {"$ifNull": ["$netto", 0]}]}},
            "totale_netto": {"$sum": {"$ifNull": ["$netto", {"$ifNull": ["$netto_mese", 0]}]}},
            "totale_inps_dipendente": {"$sum": {"$ifNull": ["$inps_dipendente", 0]}},
            "totale_irpef": {"$sum": {"$ifNull": ["$irpef", 0]}},
            "totale_inps_azienda": {"$sum": {"$ifNull": ["$inps_azienda", 0]}},
            "totale_inail": {"$sum": {"$ifNull": ["$inail", 0]}},
            "totale_tfr": {"$sum": {"$ifNull": ["$tfr", 0]}},
            "totale_costo_azienda": {"$sum": {"$ifNull": ["$costo_azienda", {"$ifNull": ["$netto", 0]}]}},
            "num_cedolini": {"$sum": 1},
            # Conta cedolini con dati completi vs parziali
            "cedolini_completi": {"$sum": {"$cond": [{"$ifNull": ["$lordo", False]}, 1, 0]}},
            "cedolini_parziali": {"$sum": {"$cond": [{"$ifNull": ["$lordo", False]}, 0, 1]}}
        }}
    ]
    
    result = await db["cedolini"].aggregate(pipeline).to_list(1)
    
    if result:
        data = result[0]
        del data["_id"]
        
        # Aggiungi nota se ci sono cedolini con dati parziali
        cedolini_parziali = data.pop("cedolini_parziali", 0)
        cedolini_completi = data.pop("cedolini_completi", 0)
        
        response = {
            "anno": anno,
            "mese": mese,
            **data
        }
        
        if cedolini_parziali > 0:
            response["nota"] = f"{cedolini_parziali} cedolini con dati parziali (solo netto)"
            response["dati_parziali"] = True
        
        return response
    
    return {
        "anno": anno,
        "mese": mese,
        "totale_lordo": 0,
        "totale_netto": 0,
        "totale_costo_azienda": 0,
        "num_cedolini": 0,
        "messaggio": "Nessun cedolino per questo periodo"
    }


# ==============================================
# ENDPOINT GENERICI (devono stare alla fine per evitare conflitti di routing)
# ==============================================

@router.get("/{cedolino_id}")
@handle_errors
async def get_cedolino_dettaglio(cedolino_id: str) -> Dict[str, Any]:
    """
    Recupera il dettaglio completo di un cedolino, incluso pdf_data per visualizzazione.
    """
    db = Database.get_db()
    
    cedolino = await db["cedolini"].find_one(
        {"id": cedolino_id},
        {"_id": 0}  # Include pdf_data per visualizzazione
    )
    
    if not cedolino:
        raise HTTPException(status_code=404, detail="Cedolino non trovato")
    
    return cedolino


@router.get("/{cedolino_id}/download")
@handle_errors
async def download_cedolino_pdf(cedolino_id: str):
    """Download PDF allegato al cedolino."""
    import base64
    from fastapi.responses import StreamingResponse
    import io

    db = Database.get_db()
    doc = await db["cedolini"].find_one({"id": cedolino_id}, {"_id": 0, "pdf_data": 1, "pdf_filename": 1, "dipendente": 1, "mese": 1, "anno": 1})
    
    pdf_data = doc.get("pdf_data") if doc else None
    filename = doc.get("pdf_filename") if doc else None
    
    # Fallback 1: Cerca in cedolini_email_attachments
    if not pdf_data and doc:
        dipendente = doc.get("dipendente", "")
        mese = doc.get("mese")
        anno = doc.get("anno")
        
        # Cerca per dipendente e periodo
        attachment = await db["cedolini_email_attachments"].find_one({
            "$or": [
                {"filename": {"$regex": dipendente, "$options": "i"}},
                {"$and": [{"mese": mese}, {"anno": anno}]}
            ],
            "associato": False
        })
        
        if attachment and attachment.get("pdf_data"):
            pdf_data = attachment["pdf_data"]
            filename = attachment.get("filename")
            # Copia il PDF nel cedolino
            await db["cedolini"].update_one(
                {"id": cedolino_id},
                {"$set": {"pdf_data": pdf_data, "pdf_filename": filename}}
            )
            # Marca attachment come associato
            await db["cedolini_email_attachments"].update_one(
                {"id": attachment["id"]},
                {"$set": {"associato": True, "documento_associato_id": cedolino_id}}
            )
    
    # Fallback 2: Cerca in payslips legacy
    if not pdf_data:
        payslip = await db["cedolini"].find_one({"id": cedolino_id}, {"pdf_data": 1, "filename": 1})
        if payslip and payslip.get("pdf_data"):
            pdf_data = payslip["pdf_data"]
            filename = payslip.get("filename")
    
    if not pdf_data:
        raise HTTPException(status_code=404, detail="PDF non disponibile")

    pdf_bytes = base64.b64decode(pdf_data)
    if not filename:
        filename = f"cedolino_{cedolino_id}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )


@router.post("/correggi-problematici")
@handle_errors
async def correggi_cedolini_problematici() -> Dict[str, Any]:
    """
    Corregge cedolini con netto=0 ma lordo>0.
    Calcola il netto stimato basandosi su lordo e trattenute standard.
    """
    db = Database.get_db()
    
    # Cerca cedolini problematici
    problematici = await db["cedolini"].find({
        "$or": [
            {"netto": 0, "lordo": {"$gt": 0}},
            {"netto": None, "lordo": {"$gt": 0}},
            {"netto": {"$exists": False}, "lordo": {"$gt": 0}}
        ]
    }).to_list(1000)
    
    corretti = 0
    errori = []
    
    for ced in problematici:
        try:
            lordo = float(ced.get("lordo", 0))
            trattenute = float(ced.get("trattenute", 0))
            irpef = float(ced.get("irpef", 0))
            ritenute_inps = float(ced.get("ritenute_dipendente", 0) or ced.get("contributi_dipendente", 0))
            
            # Se non ci sono trattenute specificate, calcola con aliquote standard
            if trattenute == 0:
                # INPS dipendente ~9.19%
                ritenute_inps = lordo * 0.0919
                
                # Imponibile fiscale
                imponibile = lordo - ritenute_inps
                
                # IRPEF approssimata (usando aliquota media 23%)
                irpef = imponibile * 0.23
                
                # Detrazioni base per lavoro dipendente (mensili)
                detrazioni_mensili = DETRAZIONE_BASE / 12
                irpef = max(0, irpef - detrazioni_mensili)
                
                trattenute = ritenute_inps + irpef
            
            # Calcola netto
            netto = lordo - trattenute
            
            if netto > 0:
                # Aggiorna il cedolino
                await db["cedolini"].update_one(
                    {"_id": ced["_id"]},
                    {"$set": {
                        "netto": round(netto, 2),
                        "trattenute": round(trattenute, 2),
                        "irpef_stimato": round(irpef, 2),
                        "ritenute_dipendente_stimate": round(ritenute_inps, 2),
                        "corretto_automaticamente": True,
                        "data_correzione": datetime.now(timezone.utc).isoformat()
                    }}
                )
                corretti += 1
            else:
                errori.append({
                    "id": str(ced.get("id") or ced.get("_id")),
                    "mese": ced.get("mese"),
                    "anno": ced.get("anno"),
                    "lordo": lordo,
                    "netto_calcolato": netto,
                    "errore": "Netto calcolato <= 0"
                })
        except Exception as e:
            errori.append({
                "id": str(ced.get("id") or ced.get("_id")),
                "errore": str(e)
            })
    
    return {
        "success": True,
        "cedolini_trovati": len(problematici),
        "corretti": corretti,
        "errori_count": len(errori),
        "errori": errori[:10],
        "message": f"Corretti {corretti} cedolini su {len(problematici)} trovati"
    }


@router.get("/problematici")
@handle_errors
async def get_cedolini_problematici() -> Dict[str, Any]:
    """
    Elenca cedolini con dati mancanti o problematici.
    """
    db = Database.get_db()
    
    problematici = await db["cedolini"].find({
        "$or": [
            {"netto": 0, "lordo": {"$gt": 0}},
            {"netto": None, "lordo": {"$gt": 0}},
            {"netto": {"$exists": False}, "lordo": {"$gt": 0}},
            {"dipendente": None},
            {"dipendente": "N/A"}
        ]
    }, {"_id": 0}).to_list(100)
    
    # Raggruppa per tipo di problema
    problemi = {
        "netto_mancante": [],
        "dipendente_mancante": [],
        "altri": []
    }
    
    for ced in problematici:
        netto = ced.get("netto")
        lordo = ced.get("lordo", 0)
        dip = ced.get("dipendente")
        
        if (netto == 0 or netto is None) and lordo > 0:
            problemi["netto_mancante"].append({
                "id": ced.get("id"),
                "mese": ced.get("mese"),
                "anno": ced.get("anno"),
                "lordo": lordo,
                "netto": netto,
                "dipendente": dip
            })
        elif not dip or dip == "N/A":
            problemi["dipendente_mancante"].append({
                "id": ced.get("id"),
                "mese": ced.get("mese"),
                "anno": ced.get("anno"),
                "lordo": lordo
            })
        else:
            problemi["altri"].append(ced)
    
    return {
        "totale_problematici": len(problematici),
        "netto_mancante": len(problemi["netto_mancante"]),
        "dipendente_mancante": len(problemi["dipendente_mancante"]),
        "altri": len(problemi["altri"]),
        "dettagli": problemi
    }

