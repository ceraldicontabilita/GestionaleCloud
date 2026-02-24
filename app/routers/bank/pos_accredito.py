"""
POS Accredito Router - API per calcolo sfasamento accrediti POS

Fornisce endpoint per:
- Calcolare data accredito da data pagamento
- Ottenere calendario sfasamento mensile
- Verificare quali pagamenti dovrebbero essere accreditati in una data
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any
from datetime import date, datetime
import logging

from app.database import Database
from app.utils.error_handler import handle_errors
from app.utils.pos_accredito import (
    calcola_data_accredito_pos,
    get_calendario_sfasamento_mese,
    get_festivi_anno,
    get_accrediti_attesi_per_data
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/calcola-accredito")
@handle_errors
async def calcola_accredito(
    data_pagamento: str = Query(..., description="Data pagamento formato YYYY-MM-DD")
) -> Dict[str, Any]:
    """
    Calcola la data di accredito POS per una specifica data di pagamento.
    
    Regole:
    - Lun-Gio: accredito il giorno lavorativo successivo
    - Venerdì: accredito Lunedì
    - Sabato: accredito Martedì
    - Domenica: accredito Martedì
    - Se il giorno cade in festivo, slitta al primo giorno lavorativo
    """
    try:
        data_pag = datetime.strptime(data_pagamento, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato data non valido. Usa YYYY-MM-DD")
    
    data_accredito, giorni_sfasamento, note = calcola_data_accredito_pos(data_pag)
    
    return {
        "data_pagamento": data_pag.isoformat(),
        "data_accredito": data_accredito.isoformat(),
        "giorno_pagamento": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"][data_pag.weekday()],
        "giorno_accredito": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"][data_accredito.weekday()],
        "giorni_sfasamento": giorni_sfasamento,
        "note": note
    }


@router.get("/calendario-mensile/{anno}/{mese}")
@handle_errors
async def get_calendario_mensile(
    anno: int,
    mese: int
) -> Dict[str, Any]:
    """
    Restituisce il calendario con lo sfasamento POS per ogni giorno del mese.
    Utile per pianificare la riconciliazione bancaria.
    """
    if mese < 1 or mese > 12:
        raise HTTPException(status_code=400, detail="Mese deve essere tra 1 e 12")
    
    return get_calendario_sfasamento_mese(anno, mese)


@router.get("/festivi/{anno}")
@handle_errors
async def get_festivi(anno: int) -> Dict[str, Any]:
    """
    Restituisce la lista dei giorni festivi per un anno specifico.
    Include festivi fissi + Pasqua e Lunedì dell'Angelo.
    """
    festivi = get_festivi_anno(anno)
    
    return {
        "anno": anno,
        "festivi": [
            {
                "data": f.isoformat(),
                "giorno": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"][f.weekday()],
                "nome": _get_nome_festivo(f)
            }
            for f in festivi
        ],
        "totale": len(festivi)
    }


def _get_nome_festivo(data: date) -> str:
    """Restituisce il nome del festivo per una data."""
    nomi = {
        (1, 1): "Capodanno",
        (6, 1): "Epifania",
        (25, 4): "Festa della Liberazione",
        (1, 5): "Festa dei Lavoratori",
        (2, 6): "Festa della Repubblica",
        (15, 8): "Ferragosto",
        (1, 11): "Ognissanti",
        (8, 12): "Immacolata Concezione",
        (25, 12): "Natale",
        (26, 12): "Santo Stefano"
    }
    
    nome = nomi.get((data.day, data.month))
    if nome:
        return nome
    
    # Controlla se è Pasqua o Pasquetta
    from app.utils.pos_accredito import _calcola_pasqua
    pasqua = _calcola_pasqua(data.year)
    if data == pasqua:
        return "Pasqua"
    if data == pasqua + timedelta(days=1):
        return "Lunedì dell'Angelo (Pasquetta)"
    
    return "Festivo"


from datetime import timedelta
from app.utils.error_handler import handle_errors


@router.get("/accrediti-attesi/{data_accredito}")
@handle_errors
async def get_accrediti_attesi(
    data_accredito: str
) -> Dict[str, Any]:
    """
    Dato una data di accredito, trova tutti i pagamenti POS che dovrebbero essere accreditati quel giorno.
    Cerca nei corrispettivi elettronici (pagato_elettronico > 0).
    """
    try:
        data_accr = datetime.strptime(data_accredito, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato data non valido. Usa YYYY-MM-DD")
    
    db = Database.get_db()
    
    # Cerca corrispettivi con pagato elettronico negli ultimi 10 giorni prima della data accredito
    data_inizio = (data_accr - timedelta(days=10)).isoformat()
    data_fine = data_accr.isoformat()
    
    corrispettivi = await db["corrispettivi"].find({
        "data": {"$gte": data_inizio, "$lte": data_fine},
        "pagato_elettronico": {"$gt": 0}
    }, {"_id": 0}).to_list(1000)
    
    # Filtra solo quelli che dovrebbero essere accreditati nella data richiesta
    accrediti = get_accrediti_attesi_per_data(data_accr, corrispettivi)
    
    totale_atteso = sum(a.get("pagato_elettronico", 0) for a in accrediti)
    
    return {
        "data_accredito": data_accredito,
        "giorno": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"][data_accr.weekday()],
        "accrediti_attesi": accrediti,
        "totale_atteso": round(totale_atteso, 2),
        "numero_operazioni": len(accrediti)
    }


@router.get("/riconciliazione-pos/{anno}/{mese}")
@handle_errors
async def get_riconciliazione_pos_mensile(
    anno: int,
    mese: int
) -> Dict[str, Any]:
    """
    Genera un report di riconciliazione POS mensile.
    Confronta i pagamenti elettronici dei corrispettivi con gli accrediti bancari attesi.
    """
    from calendar import monthrange
    
    if mese < 1 or mese > 12:
        raise HTTPException(status_code=400, detail="Mese deve essere tra 1 e 12")
    
    db = Database.get_db()
    _, ultimo_giorno = monthrange(anno, mese)
    
    data_inizio = f"{anno}-{mese:02d}-01"
    data_fine = f"{anno}-{mese:02d}-{ultimo_giorno}"
    
    # Ottieni corrispettivi del mese
    corrispettivi = await db["corrispettivi"].find({
        "data": {"$gte": data_inizio, "$lte": data_fine},
        "pagato_elettronico": {"$gt": 0}
    }, {"_id": 0}).to_list(1000)
    
    # Ottieni movimenti bancari POS del mese (e primi giorni mese successivo per sfasamento)
    data_fine_banca = (date(anno, mese, ultimo_giorno) + timedelta(days=5)).isoformat()
    
    movimenti_banca = await db["estratto_conto"].find({
        "data": {"$gte": data_inizio, "$lte": data_fine_banca},
        "$or": [
            {"descrizione": {"$regex": "POS|PDV|INCAS.*P\\.O\\.S", "$options": "i"}},
            {"causale": {"$regex": "POS|PDV", "$options": "i"}}
        ]
    }, {"_id": 0}).to_list(1000)
    
    # Raggruppa per data accredito attesa
    accrediti_per_data = {}
    
    for corr in corrispettivi:
        data_pag = datetime.strptime(corr["data"][:10], "%Y-%m-%d").date()
        data_accr, _, _ = calcola_data_accredito_pos(data_pag)
        data_accr_str = data_accr.isoformat()
        
        if data_accr_str not in accrediti_per_data:
            accrediti_per_data[data_accr_str] = {
                "data_accredito": data_accr_str,
                "pagamenti_originali": [],
                "totale_atteso": 0,
                "accreditato_banca": 0,
                "differenza": 0
            }
        
        accrediti_per_data[data_accr_str]["pagamenti_originali"].append({
            "data_pagamento": corr["data"],
            "importo": corr["pagato_elettronico"]
        })
        accrediti_per_data[data_accr_str]["totale_atteso"] += corr["pagato_elettronico"]
    
    # Associa movimenti bancari
    for mov in movimenti_banca:
        data_mov = mov.get("data", "")[:10]
        if data_mov in accrediti_per_data:
            importo = abs(float(mov.get("importo", 0) or mov.get("dare", 0) or 0))
            accrediti_per_data[data_mov]["accreditato_banca"] += importo
    
    # Calcola differenze
    for data_str in accrediti_per_data:
        rec = accrediti_per_data[data_str]
        rec["differenza"] = round(rec["accreditato_banca"] - rec["totale_atteso"], 2)
        rec["totale_atteso"] = round(rec["totale_atteso"], 2)
        rec["accreditato_banca"] = round(rec["accreditato_banca"], 2)
        rec["status"] = "OK" if abs(rec["differenza"]) < 1 else ("ECCEDENZA" if rec["differenza"] > 0 else "MANCANTE")
    
    # Ordina per data
    riconciliazione = sorted(accrediti_per_data.values(), key=lambda x: x["data_accredito"])
    
    # Totali
    totale_atteso = sum(r["totale_atteso"] for r in riconciliazione)
    totale_accreditato = sum(r["accreditato_banca"] for r in riconciliazione)
    
    return {
        "anno": anno,
        "mese": mese,
        "riconciliazione": riconciliazione,
        "totali": {
            "totale_atteso": round(totale_atteso, 2),
            "totale_accreditato": round(totale_accreditato, 2),
            "differenza": round(totale_accreditato - totale_atteso, 2)
        },
        "corrispettivi_analizzati": len(corrispettivi),
        "movimenti_banca_trovati": len(movimenti_banca)
    }
