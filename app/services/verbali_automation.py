"""
Automazione Verbali da Fatture XML

Quando una fattura XML di un noleggiatore (ALD, Leasys, Arval, etc.) contiene
righe con verbali/ri-notifiche, questo servizio:

1. Estrae numero verbale e targa dalla descrizione
2. Trova il veicolo associato alla targa
3. Trova il driver associato al veicolo
4. Crea/aggiorna il record verbale
5. Crea voce costo per il dipendente

Il flusso completo:
- Vigile mette verbale su auto noleggio
- Noleggiatore riceve richiesta info targa
- Noleggiatore comunica intestatario (Ceraldi Group)
- Noleggiatore emette fattura ri-notifica
- Sistema associa automaticamente a driver
"""
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Noleggiatori riconosciuti
FORNITORI_NOLEGGIO = [
    "ALD", "LEASYS", "ARVAL", "LEASEPLAN", "ALPHABET", 
    "LOCAUTO", "AYVENS", "HERTZ", "EUROPCAR", "SIXT"
]


def is_fornitore_noleggio(fornitore_nome: str) -> bool:
    """Verifica se il fornitore è un noleggiatore."""
    if not fornitore_nome:
        return False
    fornitore_upper = fornitore_nome.upper()
    return any(n in fornitore_upper for n in FORNITORI_NOLEGGIO)


def extract_verbale_from_text(text: str) -> Optional[str]:
    """
    Estrae il numero verbale dal testo.
    Pattern comuni:
    - Verbale Nr: B23120067780
    - N. Verbale: A25111540620
    - verbale T23260589335
    """
    if not text:
        return None
    
    patterns = [
        r'Verbale\s*(?:Nr|N\.?|Numero)?[:\s]*([A-Z]\d{8,12})',
        r'N\.\s*Verbale[:\s]*([A-Z]\d{8,12})',
        r'verbale[:\s]+([A-Z]\d{8,12})',
        r'Nr[:\s]*([A-Z]\d{8,12})',
        r'\b([ABCDEFGHIJKLMNOPQRSTUVWXYZ]\d{10,12})\b',  # Pattern generico
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    return None


def extract_targa_from_text(text: str) -> Optional[str]:
    """
    Estrae la targa dal testo.
    Pattern targa italiana: AA000AA
    """
    if not text:
        return None
    
    patterns = [
        r'TARGA[:\s]*([A-Z]{2}\d{3}[A-Z]{2})',
        r'targa[:\s]*([A-Z]{2}\d{3}[A-Z]{2})',
        r'\b([A-Z]{2}\d{3}[A-Z]{2})\b',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    return None


def extract_data_verbale_from_text(text: str) -> Optional[str]:
    """Estrae la data del verbale dal testo."""
    if not text:
        return None
    
    patterns = [
        r'Data\s*Verbale[:\s]*(\d{2}/\d{2}/\d{2,4})',
        r'del\s+(\d{2}/\d{2}/\d{2,4})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data_str = match.group(1)
            # Converti in formato ISO
            try:
                parts = data_str.split('/')
                if len(parts) == 3:
                    giorno, mese, anno = parts
                    if len(anno) == 2:
                        anno = f"20{anno}"
                    return f"{anno}-{mese}-{giorno}"
            except:
                pass
    
    return None


async def processa_verbali_da_fattura(db, parsed_invoice: Dict[str, Any], invoice_id: str) -> Dict[str, Any]:
    """
    Processa una fattura XML per estrarre e associare verbali.
    
    Args:
        db: Database connection
        parsed_invoice: Fattura parsata
        invoice_id: ID della fattura salvata
    
    Returns:
        Dict con risultati del processamento
    """
    result = {
        "verbali_trovati": 0,
        "verbali_creati": 0,
        "verbali_aggiornati": 0,
        "driver_associati": 0,
        "costi_dipendente_creati": 0,
        "dettagli": []
    }
    
    # Verifica se è un fornitore di noleggio
    supplier_name = parsed_invoice.get("supplier_name", "")
    if not is_fornitore_noleggio(supplier_name):
        return result
    
    logger.info(f"🚗 Fattura noleggiatore rilevata: {supplier_name}")
    
    # Estrai dati dalla fattura
    invoice_number = parsed_invoice.get("invoice_number", "")
    invoice_date = parsed_invoice.get("invoice_date", "")
    supplier_vat = parsed_invoice.get("supplier_vat", "")
    linee = parsed_invoice.get("linee", []) or parsed_invoice.get("items", [])
    
    # Processa ogni linea cercando verbali
    for linea in linee:
        descrizione = linea.get("descrizione", "") or linea.get("description", "")
        importo = linea.get("prezzo_totale") or linea.get("importo") or linea.get("amount") or 0
        
        # Cerca numero verbale nella descrizione
        numero_verbale = extract_verbale_from_text(descrizione)
        
        if not numero_verbale:
            continue
        
        result["verbali_trovati"] += 1
        logger.info(f"📋 Verbale trovato in fattura: {numero_verbale}")
        
        # Estrai altri dati
        targa = extract_targa_from_text(descrizione)
        data_verbale = extract_data_verbale_from_text(descrizione)
        
        # Cerca/crea record verbale
        verbale_esistente = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})
        
        verbale_doc = {
            "numero_verbale": numero_verbale,
            "fattura_id": invoice_id,
            "fattura_numero": invoice_number,
            "data_fattura": invoice_date,
            "fornitore": supplier_name,
            "fornitore_piva": supplier_vat,
            "descrizione": descrizione,
            "importo_rinotifica": float(importo) if importo else 0,
            "updated_at": datetime.now(timezone.utc)
        }
        
        if targa:
            verbale_doc["targa"] = targa
        if data_verbale:
            verbale_doc["data_verbale"] = data_verbale
        
        # === TROVA VEICOLO E DRIVER ===
        driver_info = None
        if targa:
            veicolo = await db["veicoli_noleggio"].find_one({"targa": targa.upper()})
            
            if veicolo:
                verbale_doc["veicolo_id"] = veicolo.get("id") or str(veicolo.get("_id"))
                verbale_doc["marca"] = veicolo.get("marca")
                verbale_doc["modello"] = veicolo.get("modello")
                verbale_doc["contratto"] = veicolo.get("contratto")
                verbale_doc["codice_cliente"] = veicolo.get("codice_cliente")
                
                # Trova driver
                if veicolo.get("driver"):
                    verbale_doc["driver"] = veicolo["driver"]
                    verbale_doc["driver_nome"] = veicolo["driver"]
                    driver_info = {
                        "nome": veicolo["driver"],
                        "id": veicolo.get("driver_id")
                    }
                    result["driver_associati"] += 1
                    logger.info(f"👤 Driver associato: {veicolo['driver']}")
                
                if veicolo.get("driver_id"):
                    verbale_doc["driver_id"] = veicolo["driver_id"]
        
        # Determina stato
        if verbale_doc.get("driver_id") or verbale_doc.get("driver"):
            verbale_doc["stato"] = "identificato"
        else:
            verbale_doc["stato"] = "fattura_ricevuta"
        
        # Salva/aggiorna verbale
        if verbale_esistente:
            await db["verbali_noleggio"].update_one(
                {"numero_verbale": numero_verbale},
                {"$set": verbale_doc}
            )
            result["verbali_aggiornati"] += 1
        else:
            verbale_doc["id"] = str(uuid.uuid4())
            verbale_doc["created_at"] = datetime.now(timezone.utc)
            await db["verbali_noleggio"].insert_one(verbale_doc.copy())
            result["verbali_creati"] += 1
        
        # === CREA VOCE COSTO DIPENDENTE ===
        if driver_info and driver_info.get("id"):
            try:
                costo_dipendente = {
                    "id": str(uuid.uuid4()),
                    "dipendente_id": driver_info["id"],
                    "dipendente_nome": driver_info["nome"],
                    "tipo": "verbale",
                    "categoria": "Verbali/Multe",
                    "descrizione": f"Ri-notifica verbale {numero_verbale} - Targa {targa}",
                    "importo": float(importo) if importo else 0,
                    "data": invoice_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "verbale_id": numero_verbale,
                    "targa": targa,
                    "fattura_id": invoice_id,
                    "fattura_numero": invoice_number,
                    "source": "fattura_xml_automazione",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                
                # Verifica se esiste già
                existing_costo = await db["costi_dipendenti"].find_one({
                    "verbale_id": numero_verbale,
                    "dipendente_id": driver_info["id"]
                })
                
                if not existing_costo:
                    await db["costi_dipendenti"].insert_one(costo_dipendente.copy())
                    result["costi_dipendente_creati"] += 1
                    logger.info(f"💰 Costo dipendente creato: €{importo} per {driver_info['nome']}")
            except Exception as e:
                logger.warning(f"Errore creazione costo dipendente: {e}")
        
        result["dettagli"].append({
            "numero_verbale": numero_verbale,
            "targa": targa,
            "driver": driver_info.get("nome") if driver_info else None,
            "importo": float(importo) if importo else 0
        })
    
    return result


async def processa_quietanza_email(db, email_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processa un'email con quietanza di pagamento verbale.
    
    Cerca il numero verbale nell'oggetto o nel corpo dell'email,
    poi aggiorna il verbale come pagato.
    """
    result = {
        "verbale_trovato": False,
        "verbale_aggiornato": False,
        "numero_verbale": None
    }
    
    subject = email_data.get("subject", "")
    body = email_data.get("body", "")
    
    # Cerca numero verbale
    numero_verbale = extract_verbale_from_text(subject) or extract_verbale_from_text(body)
    
    if not numero_verbale:
        return result
    
    result["numero_verbale"] = numero_verbale
    
    # Trova verbale esistente
    verbale = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})
    
    if verbale:
        result["verbale_trovato"] = True
        
        # Aggiorna come pagato
        update_data = {
            "stato_pagamento": "pagato",
            "quietanza_ricevuta": True,
            "data_quietanza": datetime.now(timezone.utc).isoformat(),
            "email_quietanza_subject": subject[:200] if subject else None,
            "updated_at": datetime.now(timezone.utc)
        }
        
        # Se ha fattura, è riconciliato
        if verbale.get("fattura_id"):
            update_data["stato"] = "riconciliato"
            update_data["riconciliato"] = True
        else:
            update_data["stato"] = "pagato"
        
        await db["verbali_noleggio"].update_one(
            {"numero_verbale": numero_verbale},
            {"$set": update_data}
        )
        
        result["verbale_aggiornato"] = True
        logger.info(f"✅ Quietanza verbale {numero_verbale} registrata")
    
    return result
