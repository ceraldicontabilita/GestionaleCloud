"""
Modulo Prima Nota per il Ciclo Passivo.
Genera scritture contabili automatiche.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict

from .constants import (
    PRIMA_NOTA_COLLECTION,
    CONTI_DARE,
    CONTI_AVERE
)

logger = logging.getLogger(__name__)


async def genera_scrittura_prima_nota(
    db, 
    fattura_id: str, 
    fattura: Dict, 
    fornitore: Dict
) -> str:
    """
    Genera una scrittura di prima nota dalla fattura.
    
    Scrittura standard fattura acquisto:
    - DARE: Conto Costo (imponibile) + IVA Credito (iva)
    - AVERE: Debiti vs Fornitori (totale)
    
    Returns:
        ID della scrittura creata
    """
    # Estrai importi
    imponibile = float(fattura.get("total_amount") or fattura.get("imponibile") or 0)
    iva = float(fattura.get("iva_totale") or fattura.get("iva") or 0)
    totale = float(fattura.get("total_amount") or (imponibile + iva))
    
    # Se totale già include IVA, calcola imponibile
    if iva == 0 and totale > 0:
        # Stima IVA 22% se non presente
        iva = round(totale - (totale / 1.22), 2)
        imponibile = totale - iva
    
    # Determina conto dare in base alla categoria
    categoria = fattura.get("categoria_contabile") or fornitore.get("categoria") or "merci"
    conto_dare = CONTI_DARE.get(categoria, CONTI_DARE["diversi"])
    
    fornitore_nome = fornitore.get("ragione_sociale") or fornitore.get("denominazione") or ""
    numero_doc = fattura.get("invoice_number") or fattura.get("numero_documento") or ""
    data_doc = fattura.get("invoice_date") or fattura.get("data_documento") or datetime.now().strftime("%Y-%m-%d")
    
    # Crea scrittura
    scrittura = {
        "id": str(uuid.uuid4()),
        "tipo": "fattura_acquisto",
        "data_registrazione": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "data_documento": data_doc,
        "numero_documento": numero_doc,
        "fattura_id": fattura_id,
        "fornitore_id": fornitore.get("id"),
        "fornitore_piva": fornitore.get("partita_iva"),
        "fornitore_nome": fornitore_nome,
        "descrizione": f"Fattura {numero_doc} - {fornitore_nome}",
        
        # Righe contabili
        "righe": [
            {
                "conto": conto_dare,
                "descrizione": "Costo merci/servizi",
                "dare": round(imponibile, 2),
                "avere": 0
            },
            {
                "conto": CONTI_DARE["iva_credito"],
                "descrizione": "IVA a credito",
                "dare": round(iva, 2),
                "avere": 0
            },
            {
                "conto": CONTI_AVERE["fornitori"],
                "descrizione": f"Debito vs {fornitore_nome[:30]}",
                "dare": 0,
                "avere": round(totale, 2)
            }
        ],
        
        "totale_dare": round(imponibile + iva, 2),
        "totale_avere": round(totale, 2),
        "stato": "bozza",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Salva nel database
    await db[PRIMA_NOTA_COLLECTION].insert_one(scrittura.copy())
    logger.info(f"Prima nota creata: {scrittura['id']} per fattura {numero_doc}")
    
    return scrittura["id"]
