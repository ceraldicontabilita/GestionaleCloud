"""
Modulo Scadenziario per il Ciclo Passivo.
Gestisce scadenze pagamento fornitori.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from .constants import (
    SCADENZIARIO_COLLECTION,
    METODI_PAGAMENTO
)

logger = logging.getLogger(__name__)


async def crea_scadenza_pagamento(
    db, 
    fattura_id: str, 
    fattura: Dict, 
    fornitore: Dict
) -> Optional[str]:
    """
    Crea una scadenza di pagamento per la fattura.
    
    Calcola la data scadenza in base a:
    1. Dati pagamento XML (se presenti)
    2. Termini di pagamento fornitore (se impostati)
    3. Default 30 giorni fine mese
    
    Returns:
        ID della scadenza creata o None se errore
    """
    # Estrai dati
    totale = float(fattura.get("total_amount") or 0)
    if totale <= 0:
        return None
    
    numero_doc = fattura.get("invoice_number") or fattura.get("numero_documento") or ""
    data_doc_str = fattura.get("invoice_date") or fattura.get("data_documento") or ""
    
    # Parse data documento
    try:
        if data_doc_str:
            data_doc = datetime.strptime(data_doc_str[:10], "%Y-%m-%d")
        else:
            data_doc = datetime.now()
    except ValueError:
        data_doc = datetime.now()
    
    # Determina metodo e giorni pagamento
    pagamento_xml = fattura.get("pagamento", {})
    modalita = pagamento_xml.get("modalita") or "MP05"  # Default bonifico
    
    metodo_info = METODI_PAGAMENTO.get(modalita, METODI_PAGAMENTO["MP05"])
    giorni_pagamento = metodo_info.get("giorni_default", 30)
    
    # Override da termini fornitore se presenti
    termini_fornitore = fornitore.get("termini_pagamento_giorni")
    if termini_fornitore:
        giorni_pagamento = int(termini_fornitore)
    
    # Calcola data scadenza
    if pagamento_xml.get("data_scadenza"):
        try:
            data_scadenza = datetime.strptime(pagamento_xml["data_scadenza"][:10], "%Y-%m-%d")
        except ValueError:
            data_scadenza = data_doc + timedelta(days=giorni_pagamento)
    else:
        # Fine mese se giorni > 0
        if giorni_pagamento > 0:
            data_scadenza = data_doc + timedelta(days=giorni_pagamento)
            # Vai a fine mese se necessario
            if "fm" in (fornitore.get("termini_pagamento") or ""):
                ultimo_giorno = (data_scadenza.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                data_scadenza = ultimo_giorno
        else:
            data_scadenza = data_doc
    
    fornitore_nome = fornitore.get("ragione_sociale") or fornitore.get("denominazione") or ""
    
    # Crea scadenza
    scadenza = {
        "id": str(uuid.uuid4()),
        "fattura_id": fattura_id,
        "numero_documento": numero_doc,
        "data_documento": data_doc_str,
        "fornitore_id": fornitore.get("id"),
        "fornitore_piva": fornitore.get("partita_iva"),
        "fornitore_nome": fornitore_nome,
        "importo": round(totale, 2),
        "importo_residuo": round(totale, 2),
        "data_scadenza": data_scadenza.strftime("%Y-%m-%d"),
        "metodo_pagamento": metodo_info.get("tipo", "bonifico"),
        "modalita_sdi": modalita,
        "iban": pagamento_xml.get("iban") or fornitore.get("iban"),
        "stato": "da_pagare",
        "pagato": False,
        "data_pagamento": None,
        "transazione_id": None,
        "note": "",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Controlla se scadenza già esiste per questa fattura
    esistente = await db[SCADENZIARIO_COLLECTION].find_one({"fattura_id": fattura_id})
    
    if esistente:
        logger.debug(f"Scadenza già esistente per fattura {fattura_id}")
        return esistente.get("id")
    
    # Salva
    await db[SCADENZIARIO_COLLECTION].insert_one(scadenza.copy())
    logger.info(f"Scadenza creata: {scadenza['id']} - {fornitore_nome} - €{totale} - scade {data_scadenza.strftime('%d/%m/%Y')}")
    
    return scadenza["id"]
