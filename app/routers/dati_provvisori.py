"""
DATI PROVVISORI - Nuova Logica Workflow
========================================

WORKFLOW CORRETTO:
1. Utente sceglie manualmente → CASSA o BANCA
2. Upload XML → Ricontrollo dati (IGNORO metodo pagamento)
3. Upload Estratto Conto → Riconciliazione automatica:
   - Trovato in banca → BANCA (se era in cassa, SPOSTO)
   - Non trovato → CASSA

Autore: Sistema Refactored
Data: 13 Febbraio 2026
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import uuid
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# DATI PROVVISORI - LISTA E GESTIONE
# =============================================================================

@router.get("/dati-provvisori")
@handle_errors
async def get_dati_provvisori(
    stato: Optional[str] = None
) -> Dict[str, Any]:
    """
    Lista tutti i dati provvisori (fatture da email).
    
    Stato:
    - pending: in attesa di classificazione
    - processed: già spostato in cassa/banca
    """
    db = Database.get_db()
    
    query = {"stato": stato} if stato else {"stato": {"$ne": "processed"}}
    
    dati = await db.dati_provvisori.find(
        query,
        {"_id": 0}
    ).sort("data_ricezione", -1).to_list(500)
    
    return {
        "success": True,
        "count": len(dati),
        "dati": dati
    }


@router.post("/dati-provvisori/sposta-cassa")
@handle_errors
async def sposta_in_cassa(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sposta dato provvisorio in Prima Nota CASSA.
    
    L'utente ha scelto manualmente: questo va in CASSA.
    """
    db = Database.get_db()
    
    dato_id = data.get("id")
    
    # Crea movimento in Prima Nota Cassa
    movimento_cassa = {
        "id": str(uuid.uuid4()),
        "data": data["data_documento"],
        "tipo": "uscita",
        "categoria": "fornitori",
        "descrizione": f"{data['fornitore']} - Fattura {data['numero_documento']}",
        # Convenzione della collection: importo SEMPRE positivo, il segno lo
        # dà "tipo" nelle aggregazioni (entrate - uscite). Salvarlo negativo
        # con tipo="uscita" faceva sì che le aggregate sottraessero un
        # numero negativo, AUMENTANDO il saldo invece di diminuirlo (bug #5
        # audit memoria/endpoints/README.md).
        "importo": abs(float(data["importo"])),
        "fornitore": data["fornitore"],
        "numero_documento": data["numero_documento"],
        "fonte": "dato_provvisorio",
        "dato_provvisorio_id": dato_id,
        "riconciliato": False,
        "metodo_scelto_manualmente": "cassa",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.prima_nota_cassa.insert_one(movimento_cassa)
    
    # Marca dato provvisorio come processato
    await db.dati_provvisori.update_one(
        {"id": dato_id},
        {
            "$set": {
                "stato": "processed",
                "destinazione": "cassa",
                "movimento_id": movimento_cassa["id"],
                "processato_il": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    logger.info(f"✅ Spostato in CASSA: {data['fornitore']} - €{data['importo']}")
    
    return {
        "success": True,
        "movimento_id": movimento_cassa["id"],
        "message": "Spostato in Prima Nota Cassa"
    }


@router.post("/dati-provvisori/sposta-banca")
@handle_errors
async def sposta_in_banca(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sposta dato provvisorio in Prima Nota BANCA.
    
    L'utente ha scelto manualmente: questo va in BANCA.
    """
    db = Database.get_db()
    
    dato_id = data.get("id")
    
    # Crea movimento in Prima Nota Banca
    movimento_banca = {
        "id": str(uuid.uuid4()),
        # "data" è il campo canonico letto da tutte le query su
        # estratto_conto_movimenti (piano conti, riconciliazione, prima
        # nota...): senza di esso il movimento era invisibile ovunque tranne
        # che nella sua stessa collection.
        "data": data["data_documento"],
        "data_valuta": data["data_documento"],
        "tipo": "uscita",
        "categoria": "fornitori",
        "descrizione_originale": f"{data['fornitore']} - Fattura {data['numero_documento']}",
        "descrizione": f"{data['fornitore']} - Fattura {data['numero_documento']}",
        # Importo sempre positivo, vedi commento in sposta_in_cassa.
        "importo": abs(float(data["importo"])),
        "fornitore": data["fornitore"],
        "numero_documento": data["numero_documento"],
        "fonte": "dato_provvisorio",
        "dato_provvisorio_id": dato_id,
        "riconciliato": False,
        "metodo_scelto_manualmente": "banca",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.estratto_conto_movimenti.insert_one(movimento_banca)
    
    # Marca dato provvisorio come processato
    await db.dati_provvisori.update_one(
        {"id": dato_id},
        {
            "$set": {
                "stato": "processed",
                "destinazione": "banca",
                "movimento_id": movimento_banca["id"],
                "processato_il": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    logger.info(f"✅ Spostato in BANCA: {data['fornitore']} - €{data['importo']}")
    
    return {
        "success": True,
        "movimento_id": movimento_banca["id"],
        "message": "Spostato in Prima Nota Banca"
    }


@router.delete("/dati-provvisori/{dato_id}")
@handle_errors
async def elimina_dato_provvisorio(dato_id: str) -> Dict[str, Any]:
    """
    Elimina dato provvisorio (scartato dall'utente).
    """
    db = Database.get_db()
    
    result = await db.dati_provvisori.delete_one({"id": dato_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Dato non trovato")
    
    return {
        "success": True,
        "message": "Dato eliminato"
    }


# =============================================================================
# UPLOAD XML - Crea o Aggiorna Dati Provvisori
# =============================================================================

@router.post("/dati-provvisori/upload-xml")
@handle_errors
async def upload_xml_fattura(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upload fattura XML.
    
    LOGICA:
    1. Parse XML → estrai dati
    2. Cerca se esiste già in dati_provvisori (stessa fattura da email)
    3. SE ESISTE → AGGIORNA con dati XML (più precisi)
    4. SE NON ESISTE → CREA nuovo dato provvisorio
    5. IGNORA sempre metodo pagamento XML (inaffidabile)
    
    L'utente sceglierà poi manualmente CASSA o BANCA.
    """
    db = Database.get_db()
    
    xml_content = data.get("xml_content")
    if not xml_content:
        raise HTTPException(400, "XML content mancante")
    
    # Parse XML
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(xml_content, "xml")
        
        # Estrai dati fattura
        fornitore = soup.find("CedentePrestatore").find("Denominazione").text if soup.find("CedentePrestatore") else None
        numero_documento = soup.find("Numero").text if soup.find("Numero") else None
        data_documento = soup.find("Data").text if soup.find("Data") else None
        
        # Importo totale
        importo_tag = soup.find("ImportoTotaleDocumento")
        importo = float(importo_tag.text) if importo_tag else 0.0
        
        # IGNORO metodo pagamento - non affidabile
        
        if not all([fornitore, numero_documento, importo]):
            raise HTTPException(400, "Dati fattura incompleti nell'XML")
        
    except Exception as e:
        logger.error(f"Errore parse XML: {e}")
        raise HTTPException(400, f"Errore parse XML: {str(e)}")
    
    # Cerca se esiste già in dati_provvisori (da email)
    existing = await db.dati_provvisori.find_one({
        "numero_documento": numero_documento,
        "fornitore": {"$regex": f"^{fornitore[:10]}", "$options": "i"}  # Match parziale
    })
    
    if existing:
        # AGGIORNA dato esistente con dati XML (più precisi)
        await db.dati_provvisori.update_one(
            {"id": existing["id"]},
            {
                "$set": {
                    "fornitore": fornitore,  # Aggiorna con dato XML preciso
                    "data_documento": data_documento,
                    "importo": importo,
                    "xml_caricato": True,
                    "xml_data": xml_content,
                    "aggiornato_da_xml": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        logger.info(f"✅ AGGIORNATO dato provvisorio con XML: {fornitore} - {numero_documento}")
        
        return {
            "success": True,
            "azione": "aggiornato",
            "message": f"Dato provvisorio aggiornato con XML: {fornitore}",
            "id": existing["id"]
        }
    
    else:
        # CREA nuovo dato provvisorio dall'XML
        nuovo_dato = {
            "id": str(uuid.uuid4()),
            "fornitore": fornitore,
            "numero_documento": numero_documento,
            "data_documento": data_documento,
            "importo": importo,
            "descrizione": f"Fattura {numero_documento} da {fornitore}",
            "stato": "pending",
            "fonte": "xml",
            "tipo": "fattura_elettronica",
            "xml_caricato": True,
            "xml_data": xml_content,
            "data_ricezione": datetime.now(timezone.utc).isoformat()
        }
        
        await db.dati_provvisori.insert_one(nuovo_dato)
        
        logger.info(f"✅ CREATO nuovo dato provvisorio da XML: {fornitore} - {numero_documento}")
        
        return {
            "success": True,
            "azione": "creato",
            "message": f"Nuova fattura da XML in Dati Provvisori: {fornitore}",
            "id": nuovo_dato["id"]
        }


# =============================================================================
# RICONCILIAZIONE ESTRATTO CONTO
# =============================================================================

@router.post("/dati-provvisori/riconcilia-estratto-conto")
@handle_errors
async def riconcilia_con_estratto_conto() -> Dict[str, Any]:
    """
    Riconciliazione automatica quando carichi estratto conto:
    
    1. Per ogni movimento in estratto conto (nuovo):
       - Cerca fattura in prima_nota_cassa con stesso importo/data
       - Se trovata → SPOSTA da cassa a banca
    
    2. Per ogni fattura in prima_nota_cassa:
       - Se NON trovata in estratto conto → resta in CASSA
       - Se trovata → SPOSTA in BANCA
    """
    db = Database.get_db()
    
    logger.info("🔄 Avvio riconciliazione estratto conto...")
    
    spostati_in_banca = 0
    
    # Trova movimenti in cassa che potrebbero essere in banca
    movimenti_cassa = await db.prima_nota_cassa.find({
        "tipo": "uscita",
        "riconciliato": {"$ne": True},
        "metodo_scelto_manualmente": "cassa"
    }).to_list(1000)
    
    for mov_cassa in movimenti_cassa:
        importo = abs(mov_cassa["importo"])
        data = mov_cassa["data"]
        
        # Cerca in estratto conto con tolleranza
        data_min = (datetime.fromisoformat(data) - timedelta(days=7)).strftime("%Y-%m-%d")
        data_max = (datetime.fromisoformat(data) + timedelta(days=7)).strftime("%Y-%m-%d")
        
        mov_banca = await db.estratto_conto_movimenti.find_one({
            "importo": {"$gte": -importo - 1, "$lte": -importo + 1},
            "data_valuta": {"$gte": data_min, "$lte": data_max},
            "riconciliato": {"$ne": True}
        })
        
        if mov_banca:
            # TROVATO! Sposta da cassa a banca
            
            # Marca movimento cassa come riconciliato
            await db.prima_nota_cassa.update_one(
                {"_id": mov_cassa["_id"]},
                {
                    "$set": {
                        "riconciliato": True,
                        "spostato_in_banca": True,
                        "movimento_banca_id": str(mov_banca["_id"]),
                        "riconciliato_il": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            # Aggiorna movimento banca
            await db.estratto_conto_movimenti.update_one(
                {"_id": mov_banca["_id"]},
                {
                    "$set": {
                        "riconciliato": True,
                        "fornitore": mov_cassa.get("fornitore"),
                        "numero_documento": mov_cassa.get("numero_documento"),
                        "movimento_cassa_id": str(mov_cassa["_id"]),
                        "riconciliato_il": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            spostati_in_banca += 1
            logger.info(f"✅ SPOSTATO cassa→banca: {mov_cassa.get('fornitore')} - €{importo}")
    
    return {
        "success": True,
        "spostati_in_banca": spostati_in_banca,
        "message": f"Riconciliazione completata: {spostati_in_banca} movimenti spostati da cassa a banca"
    }



# =============================================================================
# PROPOSTE AUTOMATICHE (Fatture ↔ Banca)
# =============================================================================

@router.post("/genera-proposte")
@handle_errors
async def genera_proposte(anno: int = 2026) -> Dict[str, Any]:
    """
    Analizza fatture bonifico non pagate e propone abbinamenti con estratto conto.
    Le proposte vanno in 'dati_provvisori' con stato 'da_confermare'.
    L'utente conferma prima dell'inserimento definitivo.
    """
    from app.services.dati_provvisori_service import genera_proposte_pagamento
    db = Database.get_db()
    return await genera_proposte_pagamento(db, anno)


@router.get("/proposte")
@handle_errors
async def lista_proposte(stato: str = "da_confermare") -> Dict[str, Any]:
    """Lista proposte di pagamento da confermare/rifiutare."""
    db = Database.get_db()
    
    query = {"tipo": "pagamento_fattura"}
    if stato:
        query["stato"] = stato
    
    proposte = await db["dati_provvisori"].find(
        query, {"_id": 0}
    ).sort("confidence", -1).to_list(200)
    
    totale_importo = sum(float(p.get("fattura_importo", 0)) for p in proposte)
    
    return {
        "proposte": proposte,
        "totale": len(proposte),
        "importo_totale": round(totale_importo, 2),
    }


@router.post("/conferma/{proposta_id}")
@handle_errors
async def conferma(proposta_id: str) -> Dict[str, Any]:
    """Conferma una proposta: registra pagamento in Prima Nota Banca."""
    from app.services.dati_provvisori_service import conferma_proposta
    db = Database.get_db()
    return await conferma_proposta(db, proposta_id)


@router.post("/conferma-tutte")
@handle_errors
async def conferma_tutte_endpoint() -> Dict[str, Any]:
    """Conferma TUTTE le proposte in sospeso."""
    from app.services.dati_provvisori_service import conferma_tutte
    db = Database.get_db()
    return await conferma_tutte(db)


@router.post("/rifiuta/{proposta_id}")
@handle_errors
async def rifiuta(proposta_id: str) -> Dict[str, Any]:
    """Rifiuta una proposta (match errato)."""
    from app.services.dati_provvisori_service import rifiuta_proposta
    db = Database.get_db()
    return await rifiuta_proposta(db, proposta_id)
