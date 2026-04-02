"""
Router per importazione automatica fatture da PEC Aruba.
Legge la casella PEC, estrae gli allegati XML delle fatture elettroniche
e li importa usando la stessa logica di importa_fattura_xml del server.py.
"""

import os
import imaplib
import email
from email.header import decode_header
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Optional
import uuid
import re
import zipfile
import io

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
import logging

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/pec", tags=["PEC Import"])

# MongoDB connection
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# PEC Configuration
PEC_USER = os.environ.get("ARUBA_PEC_USER", "")
PEC_PASSWORD = os.environ.get("ARUBA_PEC_PASSWORD", "")
PEC_HOST = os.environ.get("ARUBA_PEC_HOST", "imaps.pec.aruba.it")
PEC_PORT = int(os.environ.get("ARUBA_PEC_PORT", "993"))

AZIENDA_ID = "b0295759-35ce-4b34-a6b4-f01b883234ad"
GESTIONALE_URL = os.environ.get("GESTIONALE_URL", "http://localhost:8001")


async def _notifica_gestionale(fattura_payload: dict):
    """
    Invia i dati della fattura appena importata al gestionale (azienda_erp_db).
    Fire-and-forget: se il gestionale non risponde, non blocca l'import.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(
                f"{GESTIONALE_URL}/api/erp/ponte/fattura-ricevuta",
                json=fattura_payload,
                headers={"X-Source": "tracciabilita", "X-Azienda": AZIENDA_ID},
            )
    except Exception as e:
        logger.warning(f"[PONTE] Gestionale non raggiungibile: {e}")


class PECStatus(BaseModel):
    connected: bool
    email: str
    total_messages: int
    unread_messages: int
    error: Optional[str] = None


class ImportResult(BaseModel):
    success: bool
    imported_count: int
    skipped_count: int
    skipped_already_present: int = 0  # Fatture già presenti nel DB
    skipped_excluded: int = 0         # Fatture di fornitori esclusi
    ignored_count: int = 0  # File non-fattura ignorati (daticert.xml, ecc.)
    errors: List[str]
    details: List[dict]


# ==================== FUNZIONI HELPER ====================

def estrai_quantita_da_descrizione(desc: str) -> tuple:
    """Estrai quantità e unità dalla descrizione prodotto"""
    patterns = [
        r'(\d+(?:[.,]\d+)?)\s*KG',
        r'(\d+(?:[.,]\d+)?)\s*G\b',
        r'(\d+(?:[.,]\d+)?)\s*LT',
        r'(\d+(?:[.,]\d+)?)\s*ML',
        r'KG\.?\s*(\d+(?:[.,]\d+)?)',
    ]
    
    desc_upper = desc.upper()
    for pattern in patterns:
        match = re.search(pattern, desc_upper)
        if match:
            qty = float(match.group(1).replace(',', '.'))
            if 'KG' in pattern:
                return qty, 'KG'
            elif 'G' in pattern:
                return qty, 'G'
            elif 'LT' in pattern:
                return qty, 'LT'
            elif 'ML' in pattern:
                return qty, 'ML'
    return None, None


def decode_mime_header(header_value):
    """Decodifica header MIME"""
    if not header_value:
        return ""
    decoded_parts = decode_header(header_value)
    result = ""
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            result += part.decode(encoding or "utf-8", errors="ignore")
        else:
            result += part
    return result


def extract_xml_from_p7m(p7m_content: bytes) -> Optional[bytes]:
    """Estrae XML da file .p7m (firma digitale)"""
    try:
        content_str = p7m_content.decode('latin-1', errors='ignore')
        
        # Cerca l'inizio del XML
        xml_start = content_str.find('<?xml')
        if xml_start == -1:
            xml_start = content_str.find('<p:FatturaElettronica')
        if xml_start == -1:
            xml_start = content_str.find('<ns')
        if xml_start == -1:
            xml_start = content_str.find('<FatturaElettronica')
            
        if xml_start != -1:
            xml_end = content_str.rfind('</FatturaElettronica>')
            if xml_end == -1:
                xml_end = content_str.rfind('</p:FatturaElettronica>')
            if xml_end == -1:
                xml_end = content_str.rfind('</ns')
                if xml_end != -1:
                    xml_end = content_str.find('>', xml_end) + 1
            else:
                xml_end += len('</FatturaElettronica>')
            
            if xml_end > xml_start:
                return content_str[xml_start:xml_end].encode('utf-8')
        return None
    except Exception:
        return None


def parse_fattura_xml(xml_content: bytes) -> dict:
    """Parse fattura XML - stessa logica di server.py"""
    try:
        if xml_content.startswith(b'\xef\xbb\xbf'):
            xml_content = xml_content[3:]
        
        # Prova diversi encoding
        root = None
        for encoding in ['utf-8', 'latin-1', 'iso-8859-1']:
            try:
                root = ET.fromstring(xml_content.decode(encoding))
                break
            except:
                continue
        
        if root is None:
            try:
                root = ET.fromstring(xml_content)
            except:
                return None
    except ET.ParseError:
        return None
    
    # Verifica che sia una fattura elettronica (non daticert.xml o altri)
    root_tag = root.tag.split('}')[-1] if '}' in root.tag else root.tag
    if 'FatturaElettronica' not in root_tag and 'fattura' not in root_tag.lower():
        # Cerca se c'è FatturaElettronica come figlio
        is_fattura = False
        for child in root:
            child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if 'Fattura' in child_tag or 'Header' in child_tag:
                is_fattura = True
                break
        if not is_fattura:
            return None  # Non è una fattura, skip
    
    result = {
        'fornitore': '',
        'piva': '',
        'numero_fattura': '',
        'data_fattura': '',
        'prodotti': []
    }
    
    # Cerca in modo generico (gestisce vari namespace)
    for elem in root.iter():
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        
        if tag == 'Denominazione' and not result['fornitore']:
            result['fornitore'] = elem.text or ''
        if tag == 'IdCodice' and not result['piva']:
            result['piva'] = elem.text or ''
        if tag == 'Numero' and not result['numero_fattura']:
            result['numero_fattura'] = elem.text or ''
        if tag == 'Data' and not result['data_fattura']:
            result['data_fattura'] = elem.text or ''
    
    # Cerca le linee dettaglio prodotti
    for elem in root.iter():
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag == 'DettaglioLinee':
            prodotto = {'descrizione': '', 'quantita': '', 'prezzo': '', 'unita_misura': ''}
            for child in elem:
                child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if child_tag == 'Descrizione':
                    prodotto['descrizione'] = (child.text or '').strip()
                if child_tag == 'Quantita':
                    prodotto['quantita'] = child.text or ''
                if child_tag == 'PrezzoUnitario':
                    prodotto['prezzo'] = child.text or ''
                if child_tag == 'UnitaMisura':
                    prodotto['unita_misura'] = (child.text or '').strip().upper()
            if prodotto['descrizione'] and _e_prodotto_valido_pec(prodotto):
                result['prodotti'].append(prodotto)
    
    return result


def _e_prodotto_valido_pec(prodotto: dict) -> bool:
    """Filtra righe XML che non sono prodotti reali (stesso filtro di server.py)"""
    desc = prodotto.get('descrizione', '').strip()
    if not desc:
        return False
    if desc.startswith('**') or desc.startswith('* '):
        return False
    PREFISSI_DA_SALTARE = [
        'LUOGO DI CONSEGNA', 'LUOGO CONSEGNA', 'INDIRIZZO DI CONSEGNA',
        'Rif. Doc.', 'Rif. Conferma', 'Rif. Ordine',
        'DESTINAZIONE MERCE', 'SEDE LEGALE',
    ]
    for prefisso in PREFISSI_DA_SALTARE:
        if desc.upper().startswith(prefisso.upper()) or prefisso in desc:
            return False
    # Pattern "(2 02/01/26) - (35 03/01/26)" — riferimenti ordini GIAL
    if re.match(r'^\s*\(\d+\s+\d{2}/\d{2}/\d{2,4}\)', desc):
        return False
    # Codice postale + città
    if re.match(r'^\d{5}\s+[A-Z]', desc):
        return False
    # Riga senza né prezzo né quantità
    try:
        prezzo = float(str(prodotto.get('prezzo', '0') or '0').replace(',', '.'))
        quantita = float(str(prodotto.get('quantita', '0') or '0').replace(',', '.'))
        if prezzo == 0 and quantita == 0:
            return False
    except (ValueError, TypeError):
        pass
    return True


# ==================== ENDPOINT PEC ====================

@router.get("/status", response_model=PECStatus)
async def get_pec_status():
    """Verifica stato connessione PEC"""
    if not PEC_USER or not PEC_PASSWORD:
        return PECStatus(
            connected=False, email="", total_messages=0, unread_messages=0,
            error="Credenziali PEC non configurate"
        )
    
    try:
        mail = imaplib.IMAP4_SSL(PEC_HOST, PEC_PORT)
        mail.login(PEC_USER, PEC_PASSWORD)
        status, messages = mail.select("INBOX")
        total = int(messages[0])
        status, unread = mail.search(None, "UNSEEN")
        unread_count = len(unread[0].split()) if unread[0] else 0
        mail.logout()
        
        return PECStatus(
            connected=True, email=PEC_USER,
            total_messages=total, unread_messages=unread_count
        )
    except Exception as e:
        return PECStatus(
            connected=False, email=PEC_USER,
            total_messages=0, unread_messages=0, error=str(e)
        )


@router.post("/import", response_model=ImportResult)
async def import_fatture_from_pec(
    only_unread: bool = True,
    max_messages: int = 50,
    mark_as_read: bool = True,
    force_reimport: bool = False  # Se True: ignora dedup e legge ALL (non solo UNSEEN)
):
    """
    Importa fatture dalla PEC usando la STESSA LOGICA di importa_fattura_xml.
    
    Processo:
    1. Legge email dalla PEC
    2. Estrae allegati XML (anche da .p7m e .zip)
    3. Parsa le fatture
    4. Salva fatture nel DB
    5. Crea/aggiorna fornitori
    6. Fuzzy matching con ingredienti ricette → aggiorna materie prime
    7. Aggiorna dizionario prodotti (food cost)
    """
    if not PEC_USER or not PEC_PASSWORD:
        raise HTTPException(status_code=400, detail="Credenziali PEC non configurate")
    
    risultati = {
        "fatture_processate": 0,
        "fatture_saltate_escluse": 0,
        "fatture_gia_presenti": 0,
        "file_ignorati": 0,
        "prodotti_trovati": 0,
        "errori": []
    }
    
    imported = []
    skipped = []
    ignored = []
    errors = []
    
    try:
        # ==================== 1. CONNESSIONE PEC ====================
        mail = imaplib.IMAP4_SSL(PEC_HOST, PEC_PORT)
        mail.login(PEC_USER, PEC_PASSWORD)
        mail.select("INBOX")
        
        search_criteria = "ALL" if (force_reimport or not only_unread) else "UNSEEN"
        status, message_ids = mail.search(None, search_criteria)
        
        if status != "OK":
            raise HTTPException(status_code=500, detail="Errore ricerca messaggi")
        
        ids = message_ids[0].split()
        ids = ids[-max_messages:] if len(ids) > max_messages else ids
        
        # ==================== 2. CARICA FORNITORI ESCLUSI ====================
        fornitori_esclusi_docs = await db.fornitori.find({"escluso": True}, {"nome": 1}).to_list(5000)
        fornitori_esclusi = [f["nome"].lower() for f in fornitori_esclusi_docs]
        
        # ==================== 3. PROCESSA OGNI EMAIL ====================
        for msg_id in ids:
            try:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue
                
                msg = email.message_from_bytes(msg_data[0][1])
                subject = decode_mime_header(msg.get("Subject", ""))
                from_addr = decode_mime_header(msg.get("From", ""))
                
                # Estrai allegati XML
                xml_files = []
                for part in msg.walk():
                    filename = part.get_filename()
                    if filename:
                        filename = decode_mime_header(filename)
                        filename_lower = filename.lower()
                        
                        if filename_lower.endswith('.xml') or filename_lower.endswith('.xml.p7m'):
                            payload = part.get_payload(decode=True)
                            if payload:
                                if filename_lower.endswith('.p7m'):
                                    xml_content = extract_xml_from_p7m(payload)
                                else:
                                    xml_content = payload
                                if xml_content:
                                    xml_files.append({'filename': filename, 'content': xml_content})
                        
                        elif filename_lower.endswith('.zip'):
                            try:
                                payload = part.get_payload(decode=True)
                                with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                                    for zip_filename in zf.namelist():
                                        if zip_filename.lower().endswith('.xml'):
                                            xml_files.append({
                                                'filename': zip_filename,
                                                'content': zf.read(zip_filename)
                                            })
                                        elif zip_filename.lower().endswith('.xml.p7m'):
                                            p7m_content = zf.read(zip_filename)
                                            xml_content = extract_xml_from_p7m(p7m_content)
                                            if xml_content:
                                                xml_files.append({
                                                    'filename': zip_filename,
                                                    'content': xml_content
                                                })
                            except Exception as e:
                                errors.append(f"Errore ZIP {filename}: {str(e)}")
                
                # ==================== 4. PROCESSA OGNI FATTURA XML ====================
                # Nomi file da ignorare esplicitamente (non sono fatture)
                FILENAMES_TO_SKIP = {"daticert.xml", "postacert.eml", "smime.p7s"}
                
                for xml_file in xml_files:
                    filename_lower = xml_file['filename'].lower()
                    base_filename = filename_lower.split("/")[-1]
                    
                    # Salta file che non sono fatture
                    if base_filename in FILENAMES_TO_SKIP:
                        risultati["file_ignorati"] += 1
                        ignored.append({'filename': xml_file['filename'], 'reason': 'File non-fattura (certificato PEC)'})
                        continue
                    # Salta file che sembrano certificati o notifiche PEC
                    if "daticert" in base_filename or "postacert" in base_filename or "smime" in base_filename:
                        risultati["file_ignorati"] += 1
                        ignored.append({'filename': xml_file['filename'], 'reason': 'File non-fattura (notifica/certificato PEC)'})
                        continue
                    
                    fattura_data = parse_fattura_xml(xml_file['content'])
                    
                    if not fattura_data or not fattura_data.get('fornitore'):
                        # File XML non riconosciuto come fattura — ignora silenziosamente
                        risultati["file_ignorati"] += 1
                        ignored.append({'filename': xml_file['filename'], 'reason': 'XML non riconosciuto come fattura'})
                        continue
                    
                    # Salta se fornitore escluso
                    if fattura_data['fornitore'].lower() in fornitori_esclusi:
                        risultati["fatture_saltate_escluse"] += 1
                        skipped.append({
                            'filename': xml_file['filename'],
                            'reason': f"Fornitore {fattura_data['fornitore']} escluso",
                            'numero': fattura_data['numero_fattura'],
                            'fornitore': fattura_data['fornitore']
                        })
                        continue
                    
                    # Verifica se fattura già importata (solo se numero_fattura non è vuoto)
                    if not force_reimport and fattura_data['numero_fattura']:
                        existing = await db.fatture.find_one({
                            "numero_fattura": fattura_data['numero_fattura'],
                            "fornitore": fattura_data['fornitore']
                        })
                        
                        if existing:
                            risultati["fatture_gia_presenti"] += 1
                            skipped.append({
                                'filename': xml_file['filename'],
                                'reason': 'Fattura già importata',
                                'numero': fattura_data['numero_fattura'],
                                'fornitore': fattura_data['fornitore']
                            })
                            continue
                    
                    # Formatta data
                    data_fmt = fattura_data['data_fattura']
                    if '-' in data_fmt:
                        try:
                            dt = datetime.strptime(data_fmt, "%Y-%m-%d")
                            data_fmt = dt.strftime("%d/%m/%Y")
                        except:
                            pass
                    
                    # ==================== 5. SALVA FATTURA ====================
                    fattura_doc = {
                        "id": str(uuid.uuid4()),
                        "fornitore": fattura_data['fornitore'],
                        "piva": fattura_data['piva'],
                        "numero_fattura": fattura_data['numero_fattura'],
                        "data_fattura": data_fmt,
                        "prodotti": fattura_data['prodotti'],
                        "importato_da": "PEC",
                        "email_subject": subject,
                        "data_importazione": datetime.now(timezone.utc).isoformat(),
                        "xml_raw": xml_file['content'].decode("utf-8", errors="replace")
                    }
                    
                    await db.fatture.insert_one(fattura_doc)
                    risultati["fatture_processate"] += 1
                    risultati["prodotti_trovati"] += len(fattura_data['prodotti'])

                    # ==================== PONTE GESTIONALE ====================
                    # Fire-and-forget verso azienda_erp_db
                    import asyncio as _asyncio
                    def _safe_float(v, default=0.0):
                        try:
                            return float(str(v or default).replace(',', '.'))
                        except Exception:
                            return default

                    _righe = [
                        {
                            "descrizione": p.get('descrizione', ''),
                            "prezzo_unitario": _safe_float(p.get('prezzo', 0)),
                            "quantita": _safe_float(p.get('quantita', 1), 1.0),
                        }
                        for p in fattura_data.get('prodotti', [])
                        if p.get('descrizione')
                    ]
                    _totale = sum(
                        r["prezzo_unitario"] * r["quantita"] for r in _righe
                    )
                    _ponte_payload = {
                        "numero_fattura": fattura_data['numero_fattura'],
                        "fornitore": fattura_data['fornitore'],
                        "partita_iva": fattura_data.get('piva', ''),
                        "data": fattura_data['data_fattura'],
                        "imponibile": round(_totale, 2),
                        "iva": 0.0,
                        "totale": round(_totale, 2),
                        "righe": _righe,
                    }
                    _asyncio.create_task(_notifica_gestionale(_ponte_payload))
                    
                    # ==================== 6. CREA/AGGIORNA FORNITORE ====================
                    fornitore_esistente = await db.fornitori.find_one({"nome": fattura_data['fornitore']})
                    if not fornitore_esistente:
                        # Fornitore NUOVO: metti in_attesa per approvazione
                        await db.fornitori.insert_one({
                            "id": str(uuid.uuid4()),
                            "nome": fattura_data['fornitore'],
                            "piva": fattura_data['piva'],
                            "escluso": False,
                            "in_attesa": True,  # Richiede approvazione
                            "first_seen": datetime.now(timezone.utc).isoformat(),
                            "created_at": datetime.now(timezone.utc).isoformat()
                        })
                        imported[-1]["nuovo_fornitore"] = True if imported else None
                    else:
                        # Aggiorna P.IVA se mancante
                        if fattura_data['piva'] and not fornitore_esistente.get('piva'):
                            await db.fornitori.update_one(
                                {"nome": fattura_data['fornitore']},
                                {"$set": {"piva": fattura_data['piva'], "updated_at": datetime.now(timezone.utc).isoformat()}}
                            )
                    
                    # ==================== 7. AGGIORNA DIZIONARIO PRODOTTI ====================
                    is_acquaviva = 'acquaviva' in fattura_data.get('fornitore', '').lower() or \
                                   'vandemoortele' in fattura_data.get('fornitore', '').lower()
                    for prodotto in fattura_data['prodotti']:
                        await aggiorna_dizionario_prodotto(prodotto, fattura_data, fattura_doc['id'])
                        # Per fatture Acquaviva, aggiorna anche il costo in prodotti_vendita
                        if is_acquaviva:
                            await aggiorna_costo_prodotto_vendita(
                                prodotto, fattura_data['fornitore'], fattura_doc['id']
                            )
                    
                    imported.append({
                        'filename': xml_file['filename'],
                        'numero': fattura_data['numero_fattura'],
                        'fornitore': fattura_data['fornitore'],
                        'totale_prodotti': len(fattura_data['prodotti'])
                    })
                
                # Marca come letto
                if mark_as_read and xml_files:
                    mail.store(msg_id, '+FLAGS', '\\Seen')
                    
            except Exception as e:
                errors.append(f"Errore email: {str(e)}")
        
        mail.logout()
        
        # ==================== PIPELINE AUTOMATICA ====================
        # Se sono state importate nuove fatture → aggiorna tutto il sistema
        if risultati["fatture_processate"] > 0:
            try:
                from routers.pipeline import esegui_pipeline_post_import
                from routers.haccp_manuale_auto import aggiorna_sezioni_manuale
                import asyncio
                asyncio.create_task(
                    esegui_pipeline_post_import(motivo=f"pec_auto_{risultati['fatture_processate']}_fatture")
                )
                asyncio.create_task(aggiorna_sezioni_manuale())
            except Exception as _pe:
                logger.warning(f"Pipeline post-import non avviata: {_pe}")
        
        return ImportResult(
            success=True,
            imported_count=len(imported),
            skipped_count=len(skipped),
            skipped_already_present=risultati["fatture_gia_presenti"],
            skipped_excluded=risultati["fatture_saltate_escluse"],
            ignored_count=risultati["file_ignorati"],
            errors=errors,
            details=imported + skipped
        )
        
    except imaplib.IMAP4.error as e:
        raise HTTPException(status_code=401, detail=f"Errore autenticazione PEC: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def aggiorna_dizionario_prodotto(prodotto: dict, fattura_data: dict, fattura_id: str):
    """Aggiorna dizionario prodotti per Food Cost"""
    descrizione = prodotto.get('descrizione', '').strip()
    if not descrizione:
        return
    
    nome_normalizzato = descrizione.lower()
    nome_normalizzato = re.sub(r'\s+', ' ', nome_normalizzato)
    
    # Calcola prezzo al kg
    try:
        quantita = float(str(prodotto.get('quantita', '1')).replace(',', '.'))
        prezzo = float(str(prodotto.get('prezzo', '0')).replace(',', '.'))
    except:
        quantita = 1
        prezzo = 0
    
    qty_desc, unita = estrai_quantita_da_descrizione(descrizione)
    
    prezzo_kg = None
    quantita_kg = 0
    
    if quantita > 0 and prezzo > 0:
        prezzo_totale = quantita * prezzo
        if unita == 'KG':
            prezzo_kg = prezzo
            quantita_kg = qty_desc or quantita
        elif unita == 'G':
            prezzo_kg = prezzo * 1000
            quantita_kg = (qty_desc or quantita) / 1000
        elif unita in ['LT', 'L']:
            prezzo_kg = prezzo
            quantita_kg = qty_desc or quantita
        elif unita == 'ML':
            prezzo_kg = prezzo * 1000
            quantita_kg = (qty_desc or quantita) / 1000
        else:
            # Default: assume prezzo unitario = prezzo kg
            prezzo_kg = prezzo
            quantita_kg = quantita
    
    # Aggiorna o crea prodotto
    prodotto_esistente = await db.dizionario_prodotti.find_one({"nome_normalizzato": nome_normalizzato})
    
    if prodotto_esistente:
        nuovo_totale = prodotto_esistente.get('quantita_totale_kg', 0) + quantita_kg
        await db.dizionario_prodotti.update_one(
            {"nome_normalizzato": nome_normalizzato},
            {"$set": {
                "quantita_totale_kg": round(nuovo_totale, 3),
                "quantita_disponibile_kg": round(nuovo_totale - prodotto_esistente.get('quantita_usata_kg', 0), 3),
                "ultimo_prezzo_kg": prezzo_kg,
                "ultima_fattura": fattura_id,
                "data_aggiornamento": datetime.now(timezone.utc).isoformat()
            }}
        )
    else:
        await db.dizionario_prodotti.insert_one({
            "id": str(uuid.uuid4()),
            "nome_originale": descrizione,
            "nome_normalizzato": nome_normalizzato,
            "fornitore": fattura_data.get('fornitore'),
            "fornitore_piva": fattura_data.get('piva'),
            "prezzo_kg": prezzo_kg,
            "ultimo_prezzo_kg": prezzo_kg,
            "quantita_totale_kg": round(quantita_kg, 3),
            "quantita_usata_kg": 0,
            "quantita_disponibile_kg": round(quantita_kg, 3),
            "ultima_fattura": fattura_id,
            "data_creazione": datetime.now(timezone.utc).isoformat()
        })


async def aggiorna_costo_prodotto_vendita(prodotto: dict, fornitore: str, fattura_id: str):
    """
    Se un prodotto in fattura ha un codice_articolo che corrisponde a un prodotto
    Acquaviva in prodotti_vendita, aggiorna il costo (prezzo_cartone / pezzi_cartone).
    Viene chiamato dopo ogni riga di fattura Acquaviva.
    """
    codice = (prodotto.get('codice_articolo') or '').strip()
    descrizione = (prodotto.get('descrizione') or '').strip()

    try:
        prezzo_cartone = float(str(prodotto.get('prezzo', '0')).replace(',', '.'))
    except Exception:
        prezzo_cartone = 0.0

    if prezzo_cartone <= 0:
        return

    now = datetime.now(timezone.utc).isoformat()

    # 1. Cerca per codice_prodotto esatto (più affidabile)
    db_prod = None
    if codice:
        db_prod = await db.prodotti_vendita.find_one(
            {'codice_prodotto': codice, 'fonte': 'acquaviva'},
            {'_id': 0}
        )

    # 2. Se non trovato per codice, cerca per nome (fuzzy semplice)
    if not db_prod and descrizione:
        desc_norm = descrizione.lower().strip()
        desc_norm = re.sub(r'\b\d+[\.,]?\d*\s*(g|kg|gr|ml|cl)\b', '', desc_norm)
        desc_norm = re.sub(r'\s+', ' ', desc_norm).strip()

        # Cerca nel DB usando le prime parole significative
        parole = [w for w in desc_norm.split() if len(w) > 3][:3]
        if parole:
            pattern = '.*'.join(parole[:2])
            db_prod = await db.prodotti_vendita.find_one(
                {
                    'nome': {'$regex': pattern, '$options': 'i'},
                    'fonte': 'acquaviva'
                },
                {'_id': 0}
            )

    if not db_prod:
        return  # Prodotto non trovato in prodotti_vendita

    pz_cart = int(db_prod.get('pezzi_cartone', 0) or 0)

    # Se pezzi_cartone non disponibile, prova a calcolarlo da peso_pezzo_g
    if pz_cart <= 0:
        peso_g = float(db_prod.get('peso_pezzo_g', 0) or 0)
        # Prova a recuperare il peso cartone dalla descrizione in fattura (es. "29G 7KG")
        # Cerca pattern "Xg YKG" nella descrizione
        kg_match = re.search(r'(\d+(?:[.,]\d+)?)\s*[kK][gG]', descrizione)
        if kg_match and peso_g > 0:
            peso_cartone_kg = float(kg_match.group(1).replace(',', '.'))
            pz_cart = round(peso_cartone_kg * 1000 / peso_g)

    if pz_cart <= 0:
        return  # Non sappiamo quanti pezzi per cartone → non possiamo calcolare il costo unitario

    costo_pezzo = round(prezzo_cartone / pz_cart, 4)

    update = {
        'costo_produzione': costo_pezzo,
        'costo_produzione_cartone': prezzo_cartone,
        'pezzi_cartone': pz_cart,
        'ultima_fattura_id': fattura_id,
        'updated_at': now,
    }

    # Ricalcola margine se c'è già un prezzo vendita
    pv = float(db_prod.get('prezzo_vendita', 0) or 0)
    if pv > 0 and costo_pezzo > 0:
        margine = pv - costo_pezzo
        update['margine_euro'] = round(margine, 2)
        update['margine_percentuale'] = round((margine / pv) * 100, 1)

    await db.prodotti_vendita.update_one(
        {'id': db_prod['id']},
        {'$set': update}
    )

    # Aggiorna anche il dizionario prodotti con il costo_per_pezzo corretto
    if costo_pezzo > 0:
        await db.dizionario_prodotti.update_many(
            {'nome_normalizzato': {'$regex': re.escape(descrizione.lower()[:15]), '$options': 'i'},
             'fornitore': {'$regex': 'acquaviva|vandemoortele', '$options': 'i'}},
            {'$set': {'costo_per_pezzo': costo_pezzo, 'pezzi_per_confezione': pz_cart}}
        )


@router.post("/ricalcola-costi-da-fatture")
async def ricalcola_costi_da_fatture():
    """
    Ricalcola i costi di tutti i prodotti Acquaviva usando le fatture già in DB.
    Utile per aggiornare i prodotti senza re-importare le fatture.
    Usa: prezzo_cartone / pezzi_cartone = costo per pezzo.
    """
    # Carica tutte le fatture Acquaviva
    cursor = db.fatture.find(
        {'fornitore': {'$regex': 'acquaviva|vandemoortele', '$options': 'i'}},
        {'_id': 0, 'prodotti': 1, 'id': 1, 'fornitore': 1}
    )
    fatture = await cursor.to_list(500)

    aggiornati = 0
    processati = 0
    for fattura in fatture:
        for prod in fattura.get('prodotti', []):
            processati += 1
            # Aggiunge codice_articolo vuoto se non presente (fatture vecchie)
            if 'codice_articolo' not in prod:
                prod['codice_articolo'] = ''
            await aggiorna_costo_prodotto_vendita(prod, fattura.get('fornitore', ''), fattura.get('id', ''))
            aggiornati += 1

    # Conta quanti hanno ora il costo > 0
    con_costo = await db.prodotti_vendita.count_documents({'fonte': 'acquaviva', 'costo_produzione': {'$gt': 0}})
    senza_costo = await db.prodotti_vendita.count_documents({'fonte': 'acquaviva', 'costo_produzione': {'$lte': 0}})

    return {
        'success': True,
        'fatture_processate': len(fatture),
        'righe_processate': processati,
        'prodotti_con_costo_ora': con_costo,
        'prodotti_senza_costo': senza_costo
    }

@router.get("/anteprima")
async def preview_pec_messages(max_messages: int = 10):
    """Anteprima messaggi PEC senza importare"""
    if not PEC_USER or not PEC_PASSWORD:
        raise HTTPException(status_code=400, detail="Credenziali PEC non configurate")
    
    messages = []
    
    try:
        mail = imaplib.IMAP4_SSL(PEC_HOST, PEC_PORT)
        mail.login(PEC_USER, PEC_PASSWORD)
        mail.select("INBOX")
        
        status, message_ids = mail.search(None, "UNSEEN")
        ids = message_ids[0].split()
        ids = ids[-max_messages:] if len(ids) > max_messages else ids
        
        for msg_id in ids:
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
            
            msg = email.message_from_bytes(msg_data[0][1])
            subject = decode_mime_header(msg.get("Subject", ""))
            from_addr = decode_mime_header(msg.get("From", ""))
            date_str = msg.get("Date", "")
            
            attachments = []
            for part in msg.walk():
                filename = part.get_filename()
                if filename:
                    filename = decode_mime_header(filename)
                    if filename.lower().endswith(('.xml', '.xml.p7m', '.zip')):
                        attachments.append(filename)
            
            messages.append({
                'id': msg_id.decode(),
                'subject': subject,
                'from': from_addr,
                'date': date_str,
                'attachments': attachments,
                'has_invoice': len(attachments) > 0
            })
        
        mail.logout()
        return {'total_unread': len(ids), 'messages': messages}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
