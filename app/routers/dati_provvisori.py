"""
DATI PROVVISORI - Nuova Logica Workflow
========================================

WORKFLOW CORRETTO:
1. Email Aruba → Dati Provvisori (nessuna decisione automatica)
2. Utente sceglie manualmente → CASSA o BANCA
3. Upload XML → Ricontrollo dati (IGNORO metodo pagamento)
4. Upload Estratto Conto → Riconciliazione automatica:
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
        "importo": -abs(float(data["importo"])),  # Negativo = uscita
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
        "data_valuta": data["data_documento"],
        "tipo": "uscita",
        "categoria": "fornitori",
        "descrizione_originale": f"{data['fornitore']} - Fattura {data['numero_documento']}",
        "importo": -abs(float(data["importo"])),  # Negativo = uscita
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
# SYNC EMAIL ARUBA → DATI PROVVISORI
# =============================================================================

@router.post("/dati-provvisori/sync-email")
@handle_errors
async def sync_email_to_dati_provvisori(days_back: int = 30) -> Dict[str, Any]:
    """
    Scarica email Aruba e le mette in DATI PROVVISORI.
    
    NON prende decisioni automatiche.
    L'utente sceglierà manualmente CASSA o BANCA.
    """
    from app.services.aruba_invoice_parser import ARUBA_SENDER
    from app.config import settings
    import imaplib
    import email as email_lib
    from bs4 import BeautifulSoup
    
    db = Database.get_db()
    
    gmail_email = settings.GMAIL_EMAIL or settings.EMAIL_USER
    gmail_password = settings.GMAIL_APP_PASSWORD or settings.EMAIL_PASSWORD
    
    if not gmail_email or not gmail_password:
        raise HTTPException(500, "Credenziali Gmail non configurate")
    
    logger.info(f"📥 Sync email Aruba → Dati Provvisori (ultimi {days_back} giorni)")
    
    try:
        # Connessione IMAP
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(gmail_email, gmail_password)
        imap.select("INBOX")
        
        since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
        search_criteria = f'(FROM "{ARUBA_SENDER}" SINCE {since_date})'
        status, messages = imap.search(None, search_criteria)
        
        if status != "OK":
            raise Exception("Errore ricerca email")
        
        email_ids = messages[0].split()
        nuovi_dati = 0
        gia_esistenti = 0
        
        for email_id in email_ids:
            try:
                status, msg_data = imap.fetch(email_id, "(RFC822)")
                if status != "OK":
                    continue
                
                raw_email = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw_email)
                
                # Estrai corpo HTML
                body_html = None
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/html":
                            body_html = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            break
                else:
                    if msg.get_content_type() == "text/html":
                        body_html = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                
                if not body_html:
                    continue
                
                # Parse dati fattura
                soup = BeautifulSoup(body_html, "html.parser")
                fattura_data = parse_aruba_email_simple(soup, body_html)
                
                if not fattura_data:
                    # Email illeggibile - NON creo dato provvisorio
                    # Aspetto che arrivi l'XML
                    logger.warning(f"Email {email_id}: parse fallito, attendo XML")
                    continue
                
                # Verifica se già esiste
                existing = await db.dati_provvisori.find_one({
                    "numero_documento": fattura_data["numero_documento"],
                    "fornitore": fattura_data["fornitore"]
                })
                
                if existing:
                    gia_esistenti += 1
                    continue
                
                # Crea dato provvisorio
                dato_provvisorio = {
                    "id": str(uuid.uuid4()),
                    **fattura_data,
                    "stato": "pending",
                    "data_ricezione": datetime.now(timezone.utc).isoformat(),
                    "fonte": "email_aruba",
                    "tipo": "fattura_elettronica"
                }
                
                await db.dati_provvisori.insert_one(dato_provvisorio)
                nuovi_dati += 1
                
                logger.info(f"📨 Nuovo dato provvisorio: {fattura_data['fornitore']} - €{fattura_data['importo']}")
                
            except Exception as e:
                logger.error(f"Errore processing email {email_id}: {e}")
        
        imap.logout()
        
        return {
            "success": True,
            "email_totali": len(email_ids),
            "nuovi_dati": nuovi_dati,
            "gia_esistenti": gia_esistenti,
            "message": f"Sync completato: {nuovi_dati} nuove fatture in Dati Provvisori"
        }
        
    except Exception as e:
        logger.error(f"❌ Errore sync email: {e}")
        raise HTTPException(500, f"Errore sync: {str(e)}")


def parse_aruba_email_simple(soup, html: str) -> Optional[Dict[str, Any]]:
    """Parse semplice email Aruba - IGNORA metodo pagamento."""
    import re
    
    try:
        # Fornitore
        fornitore = None
        fornitore_patterns = [
            r"(?:Cedente|Mittente|Fornitore)[\s:]+([A-Z][A-Za-z\s&\.]+?)(?:\s*-|\s*<|$)",
            r"<strong>([A-Z][A-Za-z\s&\.]+?)</strong>",
        ]
        for pattern in fornitore_patterns:
            match = re.search(pattern, html)
            if match:
                fornitore = match.group(1).strip()
                break
        
        # Numero fattura
        numero_documento = None
        numero_patterns = [
            r"(?:Numero|N\.|Nr\.)[\s:]+(\d+(?:/\d+)?)",
            r"Fattura[\s:]+(\d+(?:/\d+)?)",
        ]
        for pattern in numero_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                numero_documento = match.group(1).strip()
                break
        
        # Data
        data_documento = None
        data_patterns = [
            r"(?:Data|Del)[\s:]+(\d{2}[/-]\d{2}[/-]\d{4})",
        ]
        for pattern in data_patterns:
            match = re.search(pattern, html)
            if match:
                data_str = match.group(1).replace("/", "-")
                day, month, year = data_str.split("-")
                data_documento = f"{year}-{month}-{day}"
                break
        
        # Importo
        importo = None
        importo_patterns = [
            r"(?:Importo|Totale)[\s:]+€?\s*([\d.,]+)",
            r"€\s*([\d.,]+)",
        ]
        for pattern in importo_patterns:
            match = re.search(pattern, html)
            if match:
                importo_str = match.group(1).replace(".", "").replace(",", ".")
                importo = float(importo_str)
                break
        
        if not all([fornitore, numero_documento, importo]):
            return None
        
        return {
            "fornitore": fornitore,
            "numero_documento": numero_documento,
            "data_documento": data_documento or datetime.now().strftime("%Y-%m-%d"),
            "importo": importo,
            "descrizione": f"Fattura {numero_documento} da {fornitore}"
        }
        
    except Exception as e:
        logger.error(f"Errore parse: {e}")
        return None


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
