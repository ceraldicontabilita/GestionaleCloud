"""
Router Gestione IVA Speciale
- Evita duplicazione IVA per fatture già in corrispettivi
- Gestione Note di Credito (resi/sconti)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================
# MODELLI
# ============================================

class FatturaInCorrispettivoInput(BaseModel):
    """Marca una fattura emessa come già inclusa nei corrispettivi"""
    fattura_id: str
    data_corrispettivo: str  # Data del corrispettivo che la include
    note: Optional[str] = None


class NotaCreditoInput(BaseModel):
    """Registra una nota di credito (reso/storno)"""
    fattura_originale_id: Optional[str] = None  # ID fattura a cui si riferisce
    fornitore: str
    numero_nota: str
    data: str  # YYYY-MM-DD
    imponibile: float
    iva: float
    tipo: str  # "reso_merce", "sconto_finanziario", "storno_totale", "storno_parziale"
    descrizione: Optional[str] = None


# ============================================
# ENDPOINT DUPLICAZIONE IVA
# ============================================

@router.post("/marca-in-corrispettivo")
async def marca_fattura_in_corrispettivo(input_data: FatturaInCorrispettivoInput) -> Dict[str, Any]:
    """
    Marca una fattura emessa come già inclusa nei corrispettivi.
    Questo evita il doppio conteggio dell'IVA in liquidazione.
    
    Caso tipico: emetti fattura a cliente privato per €100+IVA,
    ma lo scontrino era già stato battuto nel registratore.
    """
    db = Database.get_db()
    
    # Verifica esistenza fattura
    fattura = await db["invoices"].find_one(
        {"id": input_data.fattura_id},
        {"_id": 0}
    )
    
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    # Verifica che sia una fattura emessa
    if fattura.get("tipo_documento") not in ["TD01", "TD24", "TD26"]:
        raise HTTPException(
            status_code=400, 
            detail="Solo fatture emesse possono essere marcate come in corrispettivo"
        )
    
    # Aggiorna fattura
    await db["invoices"].update_one(
        {"id": input_data.fattura_id},
        {"$set": {
            "inclusa_in_corrispettivo": True,
            "data_corrispettivo_riferimento": input_data.data_corrispettivo,
            "note_corrispettivo": input_data.note,
            "marcata_corrispettivo_il": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {
        "success": True,
        "messaggio": f"Fattura {fattura.get('invoice_number')} marcata come inclusa in corrispettivo del {input_data.data_corrispettivo}",
        "iva_esclusa_da_liquidazione": fattura.get("vat_amount", 0)
    }


@router.get("/fatture-in-corrispettivi")
async def lista_fatture_in_corrispettivi(
    anno: int = Query(...)
) -> Dict[str, Any]:
    """
    Lista fatture emesse marcate come già in corrispettivi.
    """
    db = Database.get_db()
    
    fatture = await db["invoices"].find({
        "invoice_date": {"$regex": f"^{anno}"},
        "inclusa_in_corrispettivo": True
    }, {"_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1, 
        "customer_name": 1, "total_amount": 1, "vat_amount": 1,
        "data_corrispettivo_riferimento": 1}).to_list(1000)
    
    totale_iva_esclusa = sum(f.get("vat_amount", 0) or 0 for f in fatture)
    
    return {
        "anno": anno,
        "num_fatture": len(fatture),
        "totale_iva_esclusa": round(totale_iva_esclusa, 2),
        "fatture": fatture
    }


@router.delete("/rimuovi-marca-corrispettivo/{fattura_id}")
async def rimuovi_marca_corrispettivo(fattura_id: str) -> Dict[str, Any]:
    """Rimuove la marcatura 'in corrispettivo' da una fattura."""
    db = Database.get_db()
    
    result = await db["invoices"].update_one(
        {"id": fattura_id},
        {"$unset": {
            "inclusa_in_corrispettivo": "",
            "data_corrispettivo_riferimento": "",
            "note_corrispettivo": "",
            "marcata_corrispettivo_il": ""
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    return {"success": True, "messaggio": "Marcatura rimossa"}


# ============================================
# ENDPOINT NOTE DI CREDITO / RESI
# ============================================

@router.post("/nota-credito")
async def registra_nota_credito(input_data: NotaCreditoInput) -> Dict[str, Any]:
    """
    Registra una nota di credito ricevuta.
    
    Tipi supportati:
    - reso_merce: il fornitore riprende la merce
    - sconto_finanziario: sconto per pagamento anticipato
    - storno_totale: annullamento fattura
    - storno_parziale: correzione parziale
    
    Contabilità (reso merce):
    - DARE: Debiti vs fornitori (riduco debito)
    - AVERE: Resi su acquisti (minor costo)
    - AVERE: IVA a credito (minor credito)
    """
    db = Database.get_db()
    
    totale = input_data.imponibile + input_data.iva
    
    nota = {
        "id": str(uuid4()),
        "tipo_documento": "nota_credito",
        "fattura_originale_id": input_data.fattura_originale_id,
        "fornitore": input_data.fornitore,
        "numero": input_data.numero_nota,
        "data": input_data.data,
        "anno": int(input_data.data[:4]),
        "imponibile": input_data.imponibile,
        "iva": input_data.iva,
        "totale": totale,
        "tipo": input_data.tipo,
        "descrizione": input_data.descrizione,
        "contabilizzata": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["note_credito"].insert_one(nota.copy())
    
    # Se specificata fattura originale, aggiorna il suo stato
    if input_data.fattura_originale_id:
        await db["invoices"].update_one(
            {"id": input_data.fattura_originale_id},
            {"$push": {"note_credito_collegate": nota["id"]},
             "$inc": {"totale_note_credito": totale}}
        )
    
    return {
        "success": True,
        "nota_id": nota["id"],
        "messaggio": f"Nota credito {input_data.numero_nota} registrata",
        "dettaglio": {
            "imponibile": input_data.imponibile,
            "iva": input_data.iva,
            "totale": totale,
            "tipo": input_data.tipo
        }
    }


@router.get("/note-credito")
async def lista_note_credito(
    anno: int = Query(None),
    tipo: str = Query(None),
    contabilizzate: bool = Query(None)
) -> Dict[str, Any]:
    """Lista note di credito con filtri."""
    db = Database.get_db()
    
    query = {}
    if anno:
        query["anno"] = anno
    if tipo:
        query["tipo"] = tipo
    if contabilizzate is not None:
        query["contabilizzata"] = contabilizzate
    
    note = await db["note_credito"].find(query, {"_id": 0}).sort("data", -1).to_list(1000)
    
    # Totali
    totale_imponibile = sum(n.get("imponibile", 0) for n in note)
    totale_iva = sum(n.get("iva", 0) for n in note)
    
    # Per tipo
    per_tipo = {}
    for n in note:
        t = n.get("tipo", "altro")
        if t not in per_tipo:
            per_tipo[t] = {"num": 0, "totale": 0}
        per_tipo[t]["num"] += 1
        per_tipo[t]["totale"] += n.get("totale", 0)
    
    return {
        "note": note,
        "riepilogo": {
            "num_note": len(note),
            "totale_imponibile": round(totale_imponibile, 2),
            "totale_iva": round(totale_iva, 2),
            "per_tipo": per_tipo
        }
    }


@router.post("/note-credito/{nota_id}/contabilizza")
async def contabilizza_nota_credito(nota_id: str) -> Dict[str, Any]:
    """
    Contabilizza una nota di credito registrando i movimenti.
    """
    db = Database.get_db()
    
    nota = await db["note_credito"].find_one({"id": nota_id}, {"_id": 0})
    if not nota:
        raise HTTPException(status_code=404, detail="Nota credito non trovata")
    
    if nota.get("contabilizzata"):
        raise HTTPException(status_code=400, detail="Nota già contabilizzata")
    
    # Registra movimento contabile
    movimento = {
        "id": str(uuid4()),
        "data": nota["data"],
        "descrizione": f"Nota credito {nota['numero']} - {nota['fornitore']}",
        "tipo": f"nota_credito_{nota['tipo']}",
        "importo": nota["totale"],
        "imponibile": nota["imponibile"],
        "iva": nota["iva"],
        "fornitore": nota["fornitore"],
        "nota_credito_id": nota_id,
        "anno": nota["anno"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["movimenti_contabili"].insert_one(movimento.copy())
    
    # Aggiorna nota come contabilizzata
    await db["note_credito"].update_one(
        {"id": nota_id},
        {"$set": {
            "contabilizzata": True,
            "movimento_id": movimento["id"],
            "contabilizzata_il": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {
        "success": True,
        "messaggio": "Nota credito contabilizzata",
        "movimento_id": movimento["id"]
    }


@router.get("/riepilogo-iva-rettificato/{anno}")
async def get_riepilogo_iva_rettificato(
    anno: int,
    mese: int = Query(None)
) -> Dict[str, Any]:
    """
    Calcola l'IVA rettificata tenendo conto di:
    - Fatture emesse marcate come già in corrispettivi (IVA esclusa)
    - Note di credito (riducono IVA credito)
    """
    db = Database.get_db()
    
    if mese:
        data_inizio = f"{anno}-{mese:02d}-01"
        if mese == 12:
            data_fine = f"{anno}-12-31"
        else:
            data_fine = f"{anno}-{mese+1:02d}-01"
    else:
        data_inizio = f"{anno}-01-01"
        data_fine = f"{anno}-12-31"
    
    # IVA vendite normale
    fatture_emesse = await db["invoices"].aggregate([
        {"$match": {
            "invoice_date": {"$gte": data_inizio, "$lt": data_fine},
            "tipo_documento": {"$in": ["TD01", "TD24", "TD26"]},
            "inclusa_in_corrispettivo": {"$ne": True}  # Escludi quelle marcate
        }},
        {"$group": {"_id": None, "iva": {"$sum": "$vat_amount"}}}
    ]).to_list(1)
    iva_vendite = fatture_emesse[0]["iva"] if fatture_emesse else 0
    
    # IVA fatture escluse (già in corrispettivi)
    fatture_escluse = await db["invoices"].aggregate([
        {"$match": {
            "invoice_date": {"$gte": data_inizio, "$lt": data_fine},
            "inclusa_in_corrispettivo": True
        }},
        {"$group": {"_id": None, "iva": {"$sum": "$vat_amount"}}}
    ]).to_list(1)
    iva_esclusa = fatture_escluse[0]["iva"] if fatture_escluse else 0
    
    # IVA corrispettivi (scorporata)
    corrispettivi = await db["corrispettivi"].aggregate([
        {"$match": {"data": {"$gte": data_inizio, "$lt": data_fine}}},
        {"$group": {"_id": None, "totale": {"$sum": "$totale"}}}
    ]).to_list(1)
    totale_corr = corrispettivi[0]["totale"] if corrispettivi else 0
    iva_corrispettivi = totale_corr * 10 / 110  # Scorporo 10%
    
    # IVA acquisti
    acquisti = await db["invoices"].aggregate([
        {"$match": {
            "invoice_date": {"$gte": data_inizio, "$lt": data_fine},
            "tipo_documento": {"$nin": ["TD01", "TD04", "TD24", "TD26"]}
        }},
        {"$group": {"_id": None, "iva": {"$sum": "$vat_amount"}}}
    ]).to_list(1)
    iva_acquisti = acquisti[0]["iva"] if acquisti else 0
    
    # Note credito (riducono IVA credito)
    note_credito = await db["note_credito"].aggregate([
        {"$match": {"anno": anno, "contabilizzata": True}},
        {"$group": {"_id": None, "iva": {"$sum": "$iva"}}}
    ]).to_list(1)
    iva_note_credito = note_credito[0]["iva"] if note_credito else 0
    
    # Calcoli finali
    iva_debito = iva_vendite + iva_corrispettivi
    iva_credito = iva_acquisti - iva_note_credito  # Ridotta dalle NC
    saldo = iva_debito - iva_credito
    
    return {
        "anno": anno,
        "mese": mese,
        "iva_debito": {
            "fatture_emesse": round(iva_vendite, 2),
            "fatture_escluse_per_corrispettivi": round(iva_esclusa, 2),
            "corrispettivi": round(iva_corrispettivi, 2),
            "totale": round(iva_debito, 2)
        },
        "iva_credito": {
            "acquisti": round(iva_acquisti, 2),
            "note_credito_dedotte": round(iva_note_credito, 2),
            "totale": round(iva_credito, 2)
        },
        "saldo": round(saldo, 2),
        "tipo_saldo": "a_debito" if saldo > 0 else "a_credito"
    }
